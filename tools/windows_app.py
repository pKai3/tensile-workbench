"""Persistent Windows control window; the workbench itself stays in the browser."""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import queue
import re
import secrets
import subprocess
import sys
import threading
import time
from urllib.parse import parse_qs, urlsplit
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from workbench_environment import child_environment, environment_folder, validate_environment_location
from tools.windows_process import SingleInstance, WindowsJob
from tools.update_bridge import UpdateBridge

PROTOCOL = 'TENSILE_DESKTOP '
APP_ID = 'TensileWorkbench.Desktop'


def checkout_id(root):
    return hashlib.sha256(os.path.normcase(str(Path(root).resolve())).encode('utf-8')).hexdigest()[:16]


def log_path(root, environ=None):
    environ = os.environ if environ is None else environ
    if not environ.get('LOCALAPPDATA'):
        raise RuntimeError('Windows LOCALAPPDATA is unavailable.')
    return Path(environ['LOCALAPPDATA']) / 'TensileWorkbench' / 'logs' / checkout_id(root) / 'launcher.log'


def log_tail(path):
    try:
        with Path(path).open('rb') as stream:
            stream.seek(0, 2)
            stream.seek(max(0, stream.tell() - 131072))
            return stream.read().decode('utf-8', errors='replace')
    except OSError:
        return ''


def redact(text, token=''):
    if token:
        text = text.replace(token, '[hidden]')
    return re.sub(r'([?&]token=)[^\s&<>"\']+', r'\1[hidden]', text)


def ready_url(value, token):
    """Only the authenticated address belonging to this launch can be opened."""
    try:
        parts = urlsplit(value)
        if (parts.scheme == 'http' and parts.hostname == '127.0.0.1'
                and parts.port and not parts.username and not parts.password and not parts.fragment
                and parts.path == '/' and parse_qs(parts.query) == {'token': [token]}):
            return value
    except (ValueError, TypeError):
        pass
    return None


class ServerProcess:
    def __init__(self, root, folder, path, job_factory=WindowsJob):
        self.root, self.folder, self.log_path = Path(root), Path(folder), Path(path)
        self.job_factory = job_factory
        self.process = self.job = self.reader = None
        self.events = queue.SimpleQueue()
        self.url = None
        self.state = 'Stopped'
        self.stop_deadline = None
        self.started = 0
        self.token = ''
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.handler = RotatingFileHandler(self.log_path, maxBytes=2_000_000, backupCount=1, encoding='utf-8')
        self.logger = logging.Logger('tensile-desktop-' + checkout_id(root))
        self.logger.addHandler(self.handler)

    def start(self):
        if self.process is not None:
            return
        self.url, self.stop_deadline = None, None
        self.events = queue.SimpleQueue()
        self.token = secrets.token_urlsafe(32)
        self.state = 'Checking dependencies…'
        self.started = time.monotonic()
        self.logger.info('\nStarting Tensile Workbench · %s', self.root)
        env = child_environment(self.folder)
        env.update(TENSILE_WORKBENCH_DIR=str(self.root), TENSILE_DESKTOP_TOKEN=self.token,
                   PYTHONUNBUFFERED='1')
        try:
            validate_environment_location(self.folder, self.root)
            self.job = self.job_factory()
            self.process = subprocess.Popen(
                [str(self.folder / 'Scripts/python.exe'), str(self.root / 'tools/windows_server.py')],
                cwd=self.root, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace',
                bufsize=1, close_fds=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            self.job.assign(self.process)
            self.reader = threading.Thread(target=self._read, args=(self.process.stdout, self.events, self.token), daemon=True)
            self.reader.start()
            self._send('start')
        except Exception as error:
            self.logger.error('Could not start: %s', redact(str(error), self.token))
            self.state = 'Could not start — view log or rerun Install_Tensile_Workbench_App.bat.'
            self._dispose()

    def _send(self, command):
        self.process.stdin.write(command + '\n')
        self.process.stdin.flush()

    def _read(self, stream, events, token):
        try:
            while line := stream.readline(16384):
                if line.startswith(PROTOCOL):
                    try:
                        event = json.loads(line[len(PROTOCOL):])
                        if isinstance(event, dict):
                            events.put(event)
                    except ValueError:
                        self.logger.warning('Unreadable server status record.')
                else:
                    self.logger.info('%s', redact(line.rstrip(), token))
        except (OSError, ValueError):
            pass  # The owning process may have been closed during shutdown.

    def stop(self):
        if self.process is None or self.stop_deadline is not None:
            return
        self.url = None
        self.state = 'Stopping…'
        self.stop_deadline = time.monotonic() + 10
        try:
            self._send('stop')
        except (OSError, ValueError):
            pass

    def poll(self):
        if self.process is None:
            return
        while not self.events.empty():
            event = self.events.get()
            if self.stop_deadline is not None:
                continue
            phase = event.get('phase')
            if phase == 'starting':
                self.state = 'Starting…'
                self.started = time.monotonic()
            elif phase == 'ready':
                url = ready_url(event.get('url'), self.token)
                if url:
                    self.url, self.state = url, 'Running'
        code = self.process.poll()
        if code is not None:
            self.state = 'Stopped' if self.stop_deadline is not None or code == 0 else f'Stopped with error {code} — view log'
            self.url = None
            self._dispose()
        elif self.stop_deadline is not None and time.monotonic() >= self.stop_deadline:
            self.logger.warning('Stopping remaining server/kernel processes after the shutdown timeout.')
            if self._dispose():
                self.state = 'Stopped'
        elif self.url is None and self.stop_deadline is None and time.monotonic() - self.started > 120:
            self.logger.error('Startup timed out. Check the log, then rerun the installer if dependencies need repair.')
            self.stop()

    def _dispose(self):
        # Close the job even if the root already exited: its kernels may still live.
        if self.job is not None:
            try:
                self.job.close()
            except OSError as error:
                self.logger.error('Could not close managed processes: %s', redact(str(error), self.token))
                self.state = 'Could not finish stopping — view log'
                self.stop_deadline = time.monotonic() + 1
                return False
            self.job = None
        if self.process is not None:
            try:
                if self.process.poll() is None:
                    self.process.kill()  # Also covers assignment failing before the handshake.
                self.process.wait(timeout=.25)
            except (OSError, subprocess.TimeoutExpired) as error:
                self.logger.warning('Waiting for the server to finish stopping: %s', redact(str(error), self.token))
                self.state = 'Stopping…'
                self.stop_deadline = time.monotonic() + 1
                return False
            if self.reader:
                self.reader.join(timeout=1)
            for stream in (self.process.stdin, self.process.stdout):
                stream.close()
            self.process = None
        self.reader = None
        return True

    def close(self):
        self._dispose()
        self.handler.close()


def main(argv=None):
    if sys.platform != 'win32':
        raise RuntimeError('This control window is for Windows. Use the Mac app on macOS.')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--environment', type=Path)
    args = parser.parse_args(argv)
    folder = (environment_folder(ROOT) if (ROOT / '.tensile-environment.json').is_file()
              else args.environment or environment_folder(ROOT))
    validate_environment_location(folder, ROOT)
    import ctypes
    import tkinter as tk
    from tkinter import messagebox, ttk
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    instance = SingleInstance(checkout_id(ROOT))
    if instance.already_open:
        ctypes.windll.user32.MessageBoxW(None, 'Tensile Workbench is already open. Use its existing control window.',
                                       'Tensile Workbench', 0x40)
        instance.close()
        return 0
    server = None
    try:
        window = tk.Tk()
        window.title('Tensile Workbench')
        window.iconbitmap(default=str(ROOT / 'windows/TensileWorkbench.ico'))
        window.geometry('620x345')
        window.minsize(570, 345)
        window.configure(bg='#121c28')
        style = ttk.Style(window)
        style.theme_use('clam')
        style.configure('TFrame', background='#121c28')
        style.configure('TLabel', background='#121c28', foreground='#dce6ef', font=('Segoe UI', 10))
        style.configure('Title.TLabel', font=('Segoe UI', 18, 'bold'))
        style.configure('TButton', background='#172332', foreground='#edf5fc', bordercolor='#39495c',
                        font=('Segoe UI', 10), padding=(12, 8))
        style.map('TButton', background=[('active', '#275f61')], foreground=[('disabled', '#94a5b8')])
        frame = ttk.Frame(window, padding=22)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Tensile Workbench', style='Title.TLabel').pack(anchor='w')
        status = tk.StringVar(value='Starting…')
        ttk.Label(frame, textvariable=status, wraplength=520).pack(anchor='w', pady=(10, 16))
        controls = ttk.Frame(frame)
        controls.pack(anchor='w')
        server = ServerProcess(ROOT, folder, log_path(ROOT))
        closing, opened_url = False, None
        log_window = log_text = None
        last_log = None
        updates = UpdateBridge(ROOT, folder)
        updating = False

        def open_workbench():
            if server.url:
                try:
                    if not webbrowser.open(server.url):
                        raise RuntimeError('No default browser is available.')
                except Exception:
                    messagebox.showerror('Could not open browser', 'Set a default web browser in Windows, then use Open Workbench.', parent=window)

        def toggle():
            nonlocal opened_url
            if server.process:
                if messagebox.askyesno('Stop Tensile Workbench?', 'Stop this server and its running calculations? Saved settings and source data are kept.', parent=window):
                    server.stop()
            else:
                opened_url = None
                server.start()

        def view_log():
            nonlocal log_window, log_text, last_log
            if log_window is not None and log_window.winfo_exists():
                log_window.lift()
                return
            log_window = tk.Toplevel(window)
            log_window.title('Tensile Workbench — Live log')
            log_window.geometry('900x520')
            header = ttk.Frame(log_window, padding=8)
            header.pack(fill='x')
            ttk.Label(header, text='Recent output · updates live · access tokens hidden').pack(side='left')
            def copy_log():
                window.clipboard_clear()
                window.clipboard_append(log_text.get('1.0', 'end-1c'))
            ttk.Button(header, text='Copy log', command=copy_log).pack(side='right')
            log_text = tk.Text(log_window, wrap='word', bg='#0c121a', fg='#dce6ef',
                               font=('Consolas', 10), padx=12, pady=12, state='disabled')
            scroll = ttk.Scrollbar(log_window, command=log_text.yview)
            scroll.pack(side='right', fill='y')
            log_text.configure(yscrollcommand=scroll.set)
            log_text.pack(fill='both', expand=True)
            last_log = None

        start_button = ttk.Button(controls, text='Stop', command=toggle)
        start_button.pack(side='left', padx=(0, 8))
        open_button = ttk.Button(controls, text='Open Workbench', command=open_workbench)
        open_button.pack(side='left', padx=(0, 8))
        ttk.Button(controls, text='View log', command=view_log).pack(side='left')
        update_row = ttk.Frame(frame)
        update_row.pack(fill='x', pady=(16, 0))
        def show_updates():
            try:
                updates.open()
            except Exception as error:
                messagebox.showerror('Could not open updates', str(error), parent=window)
        update_button = ttk.Button(update_row, text='Check for updates', command=show_updates)
        update_button.pack(side='left')
        update_status = tk.StringVar(value='Checking for updates…')
        ttk.Label(update_row, textvariable=update_status, wraplength=300).pack(side='left', padx=12)
        ttk.Label(frame, text='Keep this window open or minimised while working.\nClosing it stops its server.',
                  foreground='#94a5b8').pack(anchor='w', pady=(16, 0))

        def close():
            nonlocal closing
            if server.process and not messagebox.askyesno('Close Tensile Workbench?',
                    'Close this window and stop its server and running calculations? Saved settings and source data are kept.', parent=window):
                return
            closing = True
            server.stop()

        def tick():
            nonlocal opened_url, last_log, closing, updating
            if not closing and updates.stop_requested():
                updating = closing = True
                server.stop()
            server.poll()
            if closing and server.process is None:
                if updating:
                    updates.acknowledge()
                window.destroy()
                return
            if updates.result:
                result = updates.result
                update_status.set(('Version ' + result['release']['version'] + ' is available.')
                                  if result.get('available') else result.get('message', ''))
            if not closing and (update_error := updates.error()):
                messagebox.showerror('Could not open updates', update_error, parent=window)
            update_button.configure(state='disabled' if closing else 'normal')
            status.set('Running · your workbench is open in the browser.' if server.url else server.state)
            start_button.configure(text='Stop' if server.process else 'Start',
                                   state='disabled' if closing or server.state == 'Stopping…' else 'normal')
            open_button.configure(state='normal' if server.url and not closing else 'disabled')
            if server.url and server.url != opened_url and not closing:
                opened_url = server.url
                open_workbench()
            if log_window is not None and log_window.winfo_exists():
                content = log_tail(server.log_path) or 'No log entries yet.'
                if content != last_log:
                    previous_view = log_text.yview()
                    at_end = previous_view[1] >= .99
                    log_text.configure(state='normal')
                    log_text.delete('1.0', 'end')
                    log_text.insert('end', content)
                    if at_end:
                        log_text.see('end')
                    else:
                        log_text.yview_moveto(previous_view[0])
                    log_text.configure(state='disabled')
                    last_log = content
            window.after(250, tick)

        window.protocol('WM_DELETE_WINDOW', close)
        server.start()
        updates.check()
        tick()
        window.mainloop()
        return 0
    finally:
        if server:
            server.close()
        instance.close()


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        # pythonw has no terminal; surface startup failures instead of disappearing.
        if sys.platform == 'win32':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, str(error) + '\n\nRerun Install_Tensile_Workbench_App.bat. '
                'Python must include Tcl/Tk.', 'Tensile Workbench could not start', 0x10)
        else:
            print(error, file=sys.stderr)
        raise SystemExit(1)
