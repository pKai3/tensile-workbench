"""Windows launcher checks without installing packages or touching research data."""
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import queue
import shutil
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import workbench_environment as environment
from tools import install_windows_app as installer
from tools import windows_app as app
from tools import windows_server as server

ROOT = Path(__file__).resolve().parents[1]


class WindowsLauncherTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='tensile windows test ')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root = self.base / 'code & quotes\' checkout'
        self.root.mkdir()
        self.folder = self.base / 'external environment' / 'venv'
        self.path = self.base / 'logs' / 'launcher.log'
        self.job = Mock()
        self.controller = app.ServerProcess(self.root, self.folder, self.path,
                                             job_factory=Mock(return_value=self.job))
        self.addCleanup(self.controller.close)

    def fake_process(self, code=None):
        process = Mock()
        process.poll.return_value = code
        process.stdout = io.StringIO('')
        process.stdin = Mock()
        return process

    def start(self, process=None):
        process = process or self.fake_process()
        with patch.object(app.subprocess, 'Popen', return_value=process) as spawn:
            self.controller.start()
        return process, spawn

    def test_handshake_follows_job_assignment_and_uses_external_python(self):
        process = self.fake_process()
        order = []
        self.job.assign.side_effect = lambda p: order.append('assign')
        process.stdin.write.side_effect = lambda text: order.append(text)
        process, spawn = self.start(process)
        self.assertEqual(order, ['assign', 'start\n'])
        self.assertEqual(spawn.call_args.args[0], [str(self.folder / 'Scripts/python.exe'),
                                                  str(self.root / 'tools/windows_server.py')])
        self.assertEqual(spawn.call_args.kwargs['cwd'], self.root)
        self.assertTrue(spawn.call_args.kwargs['close_fds'])
        self.assertNotIn('shell', spawn.call_args.kwargs)
        self.assertEqual(spawn.call_args.kwargs['env']['TENSILE_WORKBENCH_DIR'], str(self.root))
        self.assertNotIn(self.controller.token, self.path.read_text())
        with patch.object(app.subprocess, 'Popen') as again:
            self.controller.start()
            again.assert_not_called()

    def test_assignment_failure_never_releases_child_and_cleans_up(self):
        self.job.assign.side_effect = OSError('Cannot contain process')
        process, _ = self.start()
        process.stdin.write.assert_not_called()
        process.kill.assert_called_once()
        self.job.close.assert_called_once()
        self.assertIsNone(self.controller.process)
        self.assertIn('Could not start', self.controller.state)

    def test_readiness_accepts_only_our_authenticated_loopback_url(self):
        self.start()
        for url in ('https://example.com/', 'http://127.0.0.1:8888/?token=wrong',
                    'http://user@127.0.0.1:8888/?token=' + self.controller.token):
            self.controller.events.put({'phase': 'ready', 'url': url})
            self.controller.poll()
            self.assertIsNone(self.controller.url)
        url = 'http://127.0.0.1:8888/?token=' + self.controller.token
        self.controller.events.put({'phase': 'starting'})
        self.controller.poll()
        self.assertEqual(self.controller.state, 'Starting…')
        self.controller.events.put({'phase': 'ready', 'url': url})
        self.controller.poll()
        self.assertEqual(self.controller.url, url)
        self.assertEqual(self.controller.state, 'Running')

    def test_stop_ignores_late_ready_and_cleans_up_descendants_on_root_exit(self):
        process, _ = self.start()
        self.controller.stop()
        self.controller.events.put({'phase': 'ready', 'url': 'http://127.0.0.1:8888/?token=' + self.controller.token})
        self.controller.poll()
        self.assertIsNone(self.controller.url)
        self.assertEqual(self.controller.state, 'Stopping…')
        process.stdin.write.assert_called_with('stop\n')
        process.poll.return_value = 0
        self.controller.poll()
        self.job.close.assert_called_once()
        self.assertIsNone(self.controller.process)
        self.assertEqual(self.controller.state, 'Stopped')
        self.start()
        self.assertEqual(self.controller.state, 'Checking dependencies…')

    def test_failed_preflight_is_visible_and_closes_job(self):
        process, _ = self.start()
        process.poll.return_value = 1
        self.controller.poll()
        self.assertIn('error 1', self.controller.state)
        self.job.close.assert_called_once()
        self.assertIsNone(self.controller.url)

    def test_shutdown_timeout_kills_only_owned_job(self):
        process, _ = self.start()
        with patch.object(app.time, 'monotonic', return_value=10):
            self.controller.stop()
        with patch.object(app.time, 'monotonic', return_value=21):
            self.controller.poll()
        self.job.close.assert_called_once()
        self.assertIsNone(self.controller.process)
        process.kill.assert_called_once()

    def test_slow_process_exit_keeps_shutdown_pending_until_next_poll(self):
        process, _ = self.start()
        process.wait.side_effect = subprocess.TimeoutExpired('server', .25)
        self.controller.stop()
        self.controller.stop_deadline = 0
        self.controller.poll()
        self.assertIs(self.controller.process, process)
        self.assertEqual(self.controller.state, 'Stopping…')
        process.wait.side_effect = None
        process.poll.return_value = -1
        self.controller.poll()
        self.assertIsNone(self.controller.process)
        self.job.close.assert_called_once()

    def test_log_reader_consumes_private_protocol_and_redacts_tokens(self):
        events = queue.SimpleQueue()
        content = ('Normal startup\n' + app.PROTOCOL + json.dumps({'phase': 'ready',
                   'url': 'http://127.0.0.1:8888/?token=secret'}) + '\n'
                   'An error at http://127.0.0.1:8888/?token=secret and secret\n')
        self.controller._read(io.StringIO(content), events, 'secret')
        self.assertEqual(events.get()['phase'], 'ready')
        log = self.path.read_text()
        self.assertIn('Normal startup', log)
        self.assertNotIn(app.PROTOCOL, log)
        self.assertNotIn('secret', log)
        self.assertIn('[hidden]', log)

    def test_log_tail_is_bounded_and_installations_use_different_paths(self):
        self.path.write_bytes(b'a' * 180000 + 'last line'.encode())
        tail = app.log_tail(self.path)
        self.assertEqual(len(tail), 131072)
        self.assertTrue(tail.endswith('last line'))
        env = {'LOCALAPPDATA': str(self.base / 'local app data')}
        first = app.log_path(self.root, env)
        second = app.log_path(self.base / 'another checkout', env)
        self.assertNotEqual(first, second)
        self.assertFalse(first.is_relative_to(self.root))

    def test_control_pipe_stops_loop_on_stop_or_parent_disappearance(self):
        for content in ('stop\n', ''):
            loop = Mock()
            server.watch_control(io.StringIO(content), loop)
            loop.add_callback.assert_called_once_with(loop.stop)

    def test_child_requires_handshake_before_importing_or_verifying(self):
        with patch.object(server.sys, 'stdin', io.StringIO('')), \
             patch.object(environment, 'verify') as verify:
            self.assertEqual(server.main(), 1)
        verify.assert_not_called()


class WindowsInstallerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='tensile app installer ')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root = self.base / "workbench & O'Brien"
        self.folder = self.base / 'external environment' / 'venv'
        for name in installer.APP_FILES:
            destination = self.root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, destination)
        (self.folder / 'Scripts').mkdir(parents=True)
        (self.folder / 'Scripts/pythonw.exe').touch()

    def test_shortcuts_pass_paths_as_data_and_preserve_custom_environment(self):
        env = installer.shortcut_environment(self.root, self.folder, {})
        self.assertEqual(env['TW_SHORTCUT_PYTHON'], str(self.folder / 'Scripts/pythonw.exe'))
        self.assertEqual(env['TW_SHORTCUT_ROOT'], str(self.root))
        self.assertEqual(env['TW_SHORTCUT_ARGUMENTS'], subprocess.list2cmdline([
            str(self.root / 'tools/windows_app.py'), '--environment', str(self.folder)]))
        self.assertNotIn(str(self.root), installer.SHORTCUT_SCRIPT)
        self.assertIn("SpecialFolders.Item('Desktop')", installer.SHORTCUT_SCRIPT)
        self.assertIn("SpecialFolders.Item('Programs')", installer.SHORTCUT_SCRIPT)

    def test_installer_checks_tk_before_creating_shortcuts_without_policy_changes(self):
        with patch.object(installer, 'require_runtime'), patch.object(installer.sys, 'platform', 'win32'), \
             patch.object(installer.subprocess, 'run') as run, redirect_stdout(io.StringIO()):
            installer.install(self.root, self.folder)
        self.assertEqual(run.call_count, 2)
        self.assertIn('tkinter', run.call_args_list[0].args[0][-1])
        command = run.call_args_list[1].args[0]
        self.assertEqual(command[0], 'powershell.exe')
        self.assertNotIn('-ExecutionPolicy', command)
        self.assertNotIn('shell', run.call_args_list[1].kwargs)
        self.assertFalse((self.root / 'tensile_workbench.project.json').exists())

    def test_missing_tk_does_not_create_shortcuts(self):
        with patch.object(installer, 'require_runtime'), patch.object(installer.sys, 'platform', 'win32'), \
             patch.object(installer.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'tk')) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                installer.install(self.root, self.folder)
        self.assertEqual(run.call_count, 1)

    def test_custom_reinstall_updates_selection_used_by_old_pinned_shortcuts(self):
        pointer = self.root / installer.POINTER
        pointer.write_text(json.dumps({'schema_version': 1, 'environment': str(self.base / 'previous')}))
        with patch.object(installer, 'require_runtime'), patch.object(installer.sys, 'platform', 'win32'), \
             patch.object(installer.subprocess, 'run'), redirect_stdout(io.StringIO()):
            installer.install(self.root, self.folder)
        self.assertEqual(json.loads(pointer.read_bytes())['environment'], str(self.folder))

    def test_missing_app_file_is_actionable_and_icon_contains_multiple_sizes(self):
        (self.root / 'tools/windows_server.py').unlink()
        with self.assertRaisesRegex(RuntimeError, 'windows_server.py'):
            installer.shortcut_environment(self.root, self.folder, {})
        raw = (ROOT / 'windows/TensileWorkbench.ico').read_bytes()
        reserved, kind, count = struct.unpack_from('<HHH', raw)
        self.assertEqual((reserved, kind), (0, 1))
        self.assertEqual(count, 7)
        self.assertEqual([raw[6 + index * 16] or 256 for index in range(count)],
                         [16, 24, 32, 48, 64, 128, 256])


if __name__ == '__main__':
    unittest.main()
