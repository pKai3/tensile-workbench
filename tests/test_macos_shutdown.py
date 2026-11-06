"""Native event-loop regression: no windows, real server, packages or user files.

Run explicitly with TENSILE_NATIVE_LAUNCHER_TESTS=1 on macOS. The desktop CI
job does this separately from the ordinary fast, cross-platform test suite.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]

# Exercise the actual poll/update/quit methods with a short-lived owned process.
# A delegate proxy avoids applicationDidFinishLaunching: no production server,
# browser, windows or log files are opened. Private state is accessible only in
# this temporary same-file extension, never in the shipped executable.
HARNESS = r'''
extension LauncherDelegate {
    func probe(_ directory: URL, mode: String) throws {
        let child = Process()
        child.executableURL = URL(fileURLWithPath: CommandLine.arguments[0])
        child.arguments = ["--server-child", directory.appendingPathComponent("server.command").path]
        child.standardOutput = FileHandle.nullDevice
        child.standardError = FileHandle.nullDevice
        child.terminationHandler = { [weak self] finished in
            DispatchQueue.main.async {
                self?.rootExited = true
                self?.exitCode = finished.terminationStatus
                self?.poll()
            }
        }
        if mode != "stopped-update" {
            try child.run()
            process = child
            processGroup = child.processIdentifier
            try String(child.processIdentifier).write(to: directory.appendingPathComponent("server.pid"), atomically: true, encoding: .utf8)
        }
        if mode != "quit" {
            let helper = Process()
            helper.executableURL = URL(fileURLWithPath: "/bin/sleep")
            helper.arguments = ["30"]
            helper.standardInput = FileHandle.nullDevice
            helper.standardOutput = FileHandle.nullDevice
            helper.standardError = FileHandle.nullDevice
            try helper.run()
            updateHelper = helper
            try String(helper.processIdentifier).write(to: directory.appendingPathComponent("helper.pid"), atomically: true, encoding: .utf8)
            updateSession = directory.appendingPathComponent("session.json")
            let request = ["nonce": updateNonce, "action": "stop-for-update"]
            try JSONSerialization.data(withJSONObject: request).write(to: directory.appendingPathComponent("request.json"))
        }
        timer = Timer(timeInterval: 0.05, repeats: true) { [weak self] _ in
            guard let self else { return }
            if mode != "stopped-update" && !FileManager.default.fileExists(atPath: directory.appendingPathComponent("ready").path) { return }
            if mode == "quit" && !self.quitting {
                // A quit after Stop has already been requested needs no prompt.
                self.requestStop()
                NSApp.terminate(nil)
            } else { self.poll() }
        }
        RunLoop.main.add(timer!, forMode: .common)
    }
}
final class ProbeDelegate: NSObject, NSApplicationDelegate {
    let launcher = LauncherDelegate()
    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        launcher.applicationShouldTerminate(sender)
    }
}
let application = NSApplication.shared
application.setActivationPolicy(.prohibited)
let delegate = ProbeDelegate()
application.delegate = delegate
try delegate.launcher.probe(URL(fileURLWithPath: CommandLine.arguments[1]), mode: CommandLine.arguments[2])
application.run()
'''


@unittest.skipUnless(sys.platform == 'darwin' and os.environ.get('TENSILE_NATIVE_LAUNCHER_TESTS') == '1',
                     'Explicit native Mac shutdown check')
class NativeShutdownTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='tensile native shutdown ')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.base = Path(cls.temporary.name)
        source = (ROOT / 'macos/Launcher.swift').read_text().rsplit('let application = NSApplication.shared', 1)[0]
        main = cls.base / 'main.swift'
        main.write_text(source + HARNESS)
        cls.executable = cls.base / 'shutdown-probe'
        subprocess.run(['/usr/bin/xcrun', 'swiftc', '-framework', 'AppKit',
                        '-module-cache-path', str(cls.base / 'module-cache'), str(main),
                        '-o', str(cls.executable)], check=True, capture_output=True, text=True)

    def probe(self, mode):
        directory = self.base / mode
        directory.mkdir()
        (directory / 'server.command').write_text(
            '#!/bin/zsh\ntrap "exit 0" TERM\n'
            'touch "${0:A:h}/ready"\nwhile true; do /bin/sleep 0.1; done\n')
        try:
            result = subprocess.run([str(self.executable), str(directory), mode],
                                    timeout=10, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            if mode != 'quit':
                ack = json.loads((directory / 'stopped.json').read_text())
                request = json.loads((directory / 'request.json').read_text())
                self.assertEqual(ack['nonce'], request['nonce'])
            if (directory / 'server.pid').exists():
                with self.assertRaises(ProcessLookupError):
                    os.killpg(int((directory / 'server.pid').read_text()), 0)
        finally:
            # Only the disposable processes started by this probe are affected.
            for name, group in (('server.pid', True), ('helper.pid', False)):
                if (directory / name).exists():
                    try:
                        (os.killpg if group else os.kill)(int((directory / name).read_text()), signal.SIGTERM)
                    except ProcessLookupError:
                        pass

    def test_update_from_poll_timer_exits_and_acknowledges_after_shutdown(self):
        self.probe('update')

    def test_quit_keeps_event_loop_running_until_owned_server_stops(self):
        self.probe('quit')

    def test_update_with_server_already_stopped_exits_and_acknowledges(self):
        self.probe('stopped-update')
