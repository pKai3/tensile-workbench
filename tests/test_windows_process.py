"""Real Windows job ownership checks. No GUI, dependencies or data required."""
import ctypes
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from tools.windows_process import SingleInstance, WindowsJob


@unittest.skipUnless(sys.platform == 'win32', 'Requires native Windows process APIs')
class NativeWindowsProcessTests(unittest.TestCase):
    def test_duplicate_control_windows_share_only_their_checkout_mutex(self):
        first = SingleInstance('test-' + str(os.getpid()))
        second = SingleInstance('test-' + str(os.getpid()))
        other = SingleInstance('other-test-' + str(os.getpid()))
        try:
            self.assertFalse(first.already_open)
            self.assertTrue(second.already_open)
            self.assertFalse(other.already_open)
        finally:
            other.close()
            second.close()
            first.close()

    def test_job_closes_server_and_descendant_but_not_unrelated_process(self):
        with tempfile.TemporaryDirectory(prefix='tensile job test ') as directory:
            pidfile = Path(directory) / 'child.pid'
            script = ('import subprocess,sys,time; sys.stdin.readline(); '
                      'child=subprocess.Popen([sys.executable,"-c","import time; time.sleep(60)"]); '
                      'open(sys.argv[1],"w").write(str(child.pid)); time.sleep(60)')
            unrelated = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'],
                                          creationflags=subprocess.CREATE_NO_WINDOW)
            process = subprocess.Popen([sys.executable, '-c', script, str(pidfile)], stdin=subprocess.PIPE,
                                        creationflags=subprocess.CREATE_NO_WINDOW)
            job = WindowsJob()
            handle = None
            try:
                job.assign(process)
                process.stdin.write(b'start\n')
                process.stdin.flush()
                deadline = time.monotonic() + 10
                child_pid = ''
                while time.monotonic() < deadline:
                    child_pid = pidfile.read_text() if pidfile.exists() else ''
                    if child_pid:
                        break
                    time.sleep(.05)
                self.assertTrue(child_pid, 'Managed child did not start')
                api = job.api
                handle = api.OpenProcess(0x00100000, False, int(child_pid))  # SYNCHRONIZE
                self.assertTrue(handle)
                wait = api.WaitForSingleObject
                wait.argtypes, wait.restype = [ctypes.c_void_p, ctypes.c_uint32], ctypes.c_uint32
                job.close()
                process.wait(timeout=5)
                self.assertEqual(wait(handle, 5000), 0, 'Kernel descendant survived job closure')
                self.assertIsNone(unrelated.poll())
            finally:
                if handle:
                    job.api.CloseHandle(handle)
                job.close()
                for child in (process, unrelated):
                    if child.poll() is None:
                        child.kill()
                    child.wait(timeout=5)
                process.stdin.close()


if __name__ == '__main__':
    unittest.main()
