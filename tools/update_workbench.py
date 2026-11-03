"""Shared desktop update window; can also recover an interrupted installation."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import uuid

SOURCE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE_ROOT))
from workbench_updates import (LOCK, UpdateError, apply_update, assert_no_servers, check_release,
    prepare_update, process_alive, rollback_update, run_logged,
    update_directory, wait_for_shutdown, write_json)


def module_at(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def prepare_launcher(plan, session, progress):
    if sys.platform != 'darwin':
        return
    progress('Preparing the Mac launcher…')
    # Compile from the verified staged source, but embed the stable installed path.
    code = ('from tools.install_macos_app import build_bundle; from pathlib import Path; '
            'import sys; build_bundle(Path(sys.argv[1]), Path(sys.argv[2]), '
            'launch_root=Path(sys.argv[3]))')
    folder = Path(plan['environment'])
    env = os.environ.copy()
    env['TENSILE_ENV_DIR'] = str(folder)
    env['PYTHONPATH'] = plan['stage']
    run_logged([folder / 'bin/python', '-c', code, plan['stage'],
                str(Path(plan['directory']) / 'app-build'), plan['root']], plan['directory'], env)
    plan['app'] = session['app']
    write_json(Path(plan['directory']) / 'transaction.json', plan)


def activate(plan):
    root, folder = Path(plan['root']), Path(plan['environment'])
    if sys.platform == 'win32':
        env = os.environ.copy()
        env['TENSILE_ENV_DIR'] = str(folder)
        run_logged([folder / 'Scripts/python.exe', root / 'tools/install_windows_app.py'], plan['directory'], env)
    else:
        installer = module_at(root / 'tools/install_macos_app.py', 'update_macos_installer')
        installer.install_bundle(Path(plan['directory']) / 'app-build/Tensile Workbench.app',
                                 Path(plan['app']), Path(plan['directory']) / 'launcher-backup')


def restore_launcher(plan):
    if sys.platform == 'win32':
        old = dict(plan, environment=plan['previous_environment'])
        activate(old)
    elif plan.get('app'):
        backup = Path(plan['directory']) / 'launcher-backup'
        candidates = sorted(backup.glob('before-update-*/Contents'))
        if candidates:
            installer = module_at(Path(plan['root']) / 'tools/install_macos_app.py', 'restore_macos_installer')
            staged = Path(plan['directory']) / 'restore-app/Tensile Workbench.app'
            staged.mkdir(parents=True, exist_ok=True)
            shutil.copytree(candidates[-1], staged / 'Contents', dirs_exist_ok=True)
            installer.install_bundle(staged, Path(plan['app']), Path(plan['directory']) / 'recovery-launcher-backup')


def restart(root, environment, app=None):
    if sys.platform == 'win32':
        subprocess.Popen([str(Path(environment) / 'Scripts/pythonw.exe'),
                          str(Path(root) / 'tools/windows_app.py'), '--environment', str(environment)],
                         cwd=root, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, close_fds=True,
                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    else:
        subprocess.run(['/usr/bin/open', str(app)], check=True)


def freeze_helper(session):
    """Recovery must still work if the application source is only half replaced."""
    root = Path(session['root'])
    directory = update_directory(root) / ('helper-' + uuid.uuid4().hex[:12])
    (directory / 'tools').mkdir(parents=True, mode=0o700)
    shutil.copyfile(root / 'workbench_updates.py', directory / 'workbench_updates.py')
    shutil.copyfile(root / 'tools/update_workbench.py', directory / 'tools/update_workbench.py')
    return directory / 'tools/update_workbench.py'


def recovery_launchers(plan, helper):
    """Explicit recovery commands are outside the folder being replaced."""
    folder = Path(plan['previous_environment'])
    directory = Path(plan['directory'])
    arguments = [str(helper), 'recover', '--transaction', str(directory / 'transaction.json')]
    if sys.platform == 'win32':
        # Quote every argument, escape percent expansion, and disable delayed
        # expansion so &, %, and ! in a Windows user's paths stay literal.
        command = ' '.join('"' + arg.replace('%', '%%') + '"' for arg in
                           [str(folder / 'Scripts/pythonw.exe'), *arguments])
        (directory / 'Recover Tensile Workbench.bat').write_text(
            '@echo off\nsetlocal DisableDelayedExpansion\nchcp 65001 >nul\n' + command + '\n', encoding='utf-8')
    else:
        import shlex
        path = directory / 'Recover Tensile Workbench.command'
        path.write_text('#!/bin/sh\nexec ' + shlex.join([str(folder / 'bin/python'), *arguments]) + '\n')
        path.chmod(0o755)
    plan['helper'] = str(helper)
    write_json(directory / 'transaction.json', plan)


def show_dialog(session_path=None, transaction_path=None):
    try:
        import tkinter as tk
    except ImportError as error:
        raise UpdateError('The update window needs Python with Tcl/Tk. Use the full Python.org '
                          'installation, or update this checkout manually with Git.') from error
    from tkinter import messagebox, ttk
    session = json.loads(Path(session_path).read_bytes()) if session_path else None
    plan = json.loads(Path(transaction_path).read_bytes()) if transaction_path else None
    root = Path(session['root'] if session else plan['root'])
    sys.path.insert(0, str(root))
    # Python has loaded this helper into memory. Keep a separate copy as well,
    # so recovery does not depend on source files that might be half replaced.
    recovery_helper = freeze_helper(session) if session else Path(__file__)
    window = tk.Tk()
    window.title('Tensile Workbench — Updates')
    window.geometry('650x470')
    window.minsize(570, 400)
    frame = ttk.Frame(window, padding=20)
    frame.pack(fill='both', expand=True)
    ttk.Label(frame, text='Tensile Workbench updates', font=('Helvetica', 17, 'bold')).pack(anchor='w')
    status = tk.StringVar(value='Checking for updates…')
    ttk.Label(frame, textvariable=status, wraplength=600).pack(anchor='w', pady=(12, 8))
    notes = tk.Text(frame, height=10, wrap='word', padx=10, pady=10, state='disabled')
    notes.pack(fill='both', expand=True)
    ttk.Label(frame, text='Saved analyses, overrides, custom variables and data are kept.\n'
              'Installing will stop running calculations and restart the app.', wraplength=600).pack(anchor='w', pady=12)
    progress = ttk.Progressbar(frame, mode='indeterminate')
    progress.pack(fill='x')
    row = ttk.Frame(frame)
    row.pack(fill='x', pady=(12, 0))
    messages = queue.Queue()
    busy, applying, release, helper, stopped = False, False, None, recovery_helper, False

    def set_notes(value):
        notes.configure(state='normal')
        notes.delete('1.0', 'end')
        notes.insert('end', value)
        notes.configure(state='disabled')

    def work(action):
        nonlocal busy
        busy = True
        install_button.configure(state='disabled')
        check_button.configure(state='disabled')
        progress.start(12)
        def run():
            try:
                action()
            except Exception as error:
                messages.put(('error', str(error)))
        threading.Thread(target=run, name='update-worker', daemon=True).start()

    def check():
        def action():
            if (root / LOCK).is_file():
                pending = json.loads((root / LOCK).read_bytes())
                if process_alive(pending.get('pid')):
                    raise UpdateError('An update is already running. Wait for its window to finish.')
                messages.put(('recovery', json.loads(Path(pending['transaction']).read_bytes())))
            else:
                messages.put(('checked', check_release(root)))
        work(action)

    def install():
        nonlocal applying
        if not messagebox.askokcancel('Install update and restart?',
                'Save pending edits in the workbench first. Running calculations will stop after the update has been prepared.', parent=window):
            return
        applying = True
        def action():
            nonlocal plan, stopped
            report = lambda value: messages.put(('progress', value))
            if plan is None:
                plan = prepare_update(root, release, session['environment'], report)
                prepare_launcher(plan, session, report)
                recovery_launchers(plan, helper)
            report('Stopping Workbench before replacing files…')
            if session:
                wait_for_shutdown(session_path)
            elif (root / LOCK).is_file() and process_alive(json.loads((root / LOCK).read_bytes()).get('pid')):
                raise UpdateError('An update is still running.')
            stopped = True
            assert_no_servers(root)
            if plan['state'] == 'prepared':
                report('Installing update…')
                apply_update(plan, activate, restore_launcher)
            else:
                report('Restoring the previous working version…')
                rollback_update(plan, restore_launcher)
            report('Starting Tensile Workbench…')
            environment = plan['environment'] if plan['state'] == 'complete' else plan['previous_environment']
            restart(root, environment, plan.get('app') or (session or {}).get('app'))
            messages.put(('done', None))
        work(action)

    install_button = ttk.Button(row, text='Install update and restart', command=install, state='disabled')
    install_button.pack(side='left')
    check_button = ttk.Button(row, text='Check again', command=check)
    check_button.pack(side='left', padx=10)

    def close():
        if applying and busy:
            messagebox.showinfo('Update in progress', 'Please let the update finish. Your previous version is being kept for recovery.', parent=window)
        else:
            window.destroy()
    ttk.Button(row, text='Close', command=close).pack(side='right')

    def poll():
        nonlocal busy, applying, release, plan
        while not messages.empty():
            kind, value = messages.get_nowait()
            if kind == 'progress':
                status.set(value)
                continue
            busy = False
            progress.stop()
            check_button.configure(state='normal')
            if kind == 'checked':
                plan = None
                release = value.get('release')
                status.set(f"Installed: {value['current']}" +
                           (f"  ·  Available: {release['version']}" if value['available'] else '  ·  ' + value['message']))
                set_notes(release['notes'] if release else value['message'])
                install_button.configure(state='normal' if value['available'] else 'disabled')
            elif kind == 'recovery':
                plan = value
                status.set('An interrupted update needs recovery.')
                set_notes('Restore the previous code and launcher. Saved settings and research files are kept.\n\nBackup: ' + plan['directory'])
                install_button.configure(text='Restore previous version and restart', state='normal')
            elif kind == 'error':
                applying = False
                status.set('Update did not finish.')
                set_notes(value + ('\n\nLog and recovery files: ' + plan['directory'] if plan else ''))
                if plan and plan.get('state') in ('rolled-back', 'prepared') and stopped and not (root / LOCK).exists():
                    try:
                        restart(root, plan['previous_environment'], plan.get('app') or (session or {}).get('app'))
                        status.set('Update failed; the previous version has been restored and restarted.')
                    except Exception as error:
                        set_notes(value + '\n\nCould not restart: ' + str(error))
                elif plan and plan.get('state') in ('applying', 'activating'):
                    install_button.configure(text='Restore previous version and restart', state='normal')
            elif kind == 'done':
                window.destroy()
                return
        window.after(150, poll)

    window.protocol('WM_DELETE_WINDOW', close)
    if plan:
        messages.put(('recovery', plan))
    else:
        check()
    poll()
    window.mainloop()
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('check', 'dialog', 'recover'))
    parser.add_argument('--root', type=Path)
    parser.add_argument('--result', type=Path)
    parser.add_argument('--session', type=Path)
    parser.add_argument('--transaction', type=Path)
    args = parser.parse_args(argv)
    if args.action == 'check':
        try:
            value = check_release(args.root or SOURCE_ROOT)
        except Exception:
            value = {'available': False, 'message': 'Update check unavailable. Try again later.'}
        if args.result:
            write_json(args.result, value)
        else:
            print(json.dumps(value))
        return 0
    if args.action == 'dialog' and args.session:
        try:
            return show_dialog(args.session)
        except Exception as error:
            write_json(args.session.with_name('error.json'), {'message': str(error)})
            return 1
    if args.action == 'recover' and args.transaction:
        return show_dialog(transaction_path=args.transaction)
    parser.error('Specify the launcher session or recovery transaction.')


if __name__ == '__main__':
    raise SystemExit(main())
