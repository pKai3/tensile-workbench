"""Non-blocking Windows launcher/update-helper handshake. No GUI imports."""
import json
import os
from pathlib import Path
import secrets
import subprocess
import threading

from workbench_updates import check_release, update_directory, write_json


class UpdateBridge:
    def __init__(self, root, environment):
        self.root, self.environment = Path(root), Path(environment)
        self.directory = update_directory(root) / ('session-' + secrets.token_hex(12))
        self.directory.mkdir(parents=True, mode=0o700)
        self.nonce = secrets.token_hex(24)
        self.session = self.directory / 'session.json'
        write_json(self.session, {'root': str(root), 'environment': str(environment),
                                 'pid': os.getpid(), 'nonce': self.nonce})
        self.result = None
        self.checking = False
        self.helper = None
        self.reported_helper_error = False

    def check(self):
        if self.checking:
            return
        self.checking = True
        def run():
            try:
                self.result = check_release(self.root)
            except Exception:
                self.result = {'available': False, 'message': 'Update check unavailable. Try again later.'}
            finally:
                self.checking = False
        threading.Thread(target=run, name='release-check', daemon=True).start()

    def open(self):
        if self.helper and self.helper.poll() is None:
            return
        for name in ('request.json', 'stopped.json', 'error.json'):
            (self.directory / name).unlink(missing_ok=True)
        self.reported_helper_error = False
        self.helper = subprocess.Popen([
            str(self.environment / 'Scripts/pythonw.exe'),
            str(self.root / 'tools/update_workbench.py'), 'dialog', '--session', str(self.session)],
            cwd=self.root, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, close_fds=True,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))

    def stop_requested(self):
        if not self.helper or self.helper.poll() is not None:
            return False
        try:
            value = json.loads((self.directory / 'request.json').read_bytes())
            return value == {'nonce': self.nonce, 'action': 'stop-for-update'}
        except (OSError, ValueError):
            return False

    def acknowledge(self):
        write_json(self.directory / 'stopped.json', {'nonce': self.nonce})

    def error(self):
        if not self.helper or self.helper.poll() in (None, 0) or self.reported_helper_error:
            return ''
        self.reported_helper_error = True
        try:
            return json.loads((self.directory / 'error.json').read_bytes())['message']
        except (OSError, ValueError, KeyError):
            return 'The update window could not open. Rerun the app installer and try again.'
