"""Shared Mac/Windows setup and launch. Never read or process research data."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import stat
import struct
import subprocess
import sys
import sysconfig
import venv

ROOT = Path(__file__).resolve().parent
PYTHON_VERSION = (3, 14)
ENVIRONMENT_TAG = 'py314'


def retire_legacy_entrypoints(root):
    """Clear stock duplicate wrappers left by copying an old ZIP in place.

    Preserve modified scripts and symlinks. Keep exact originals in local update
    storage, so this installer cleanup remains reversible.
    """
    batch = '@echo off\nsetlocal EnableExtensions DisableDelayedExpansion\ncall "%~dp0tools\\run_windows.bat" {action}\nexit /b %ERRORLEVEL%\n'
    known = {'Setup_Tensile_Workbench.bat': batch.format(action='setup'),
             'Launch_Tensile_Workbench.bat': batch.format(action='launch'),
             'Setup_Tensile_Workbench.command': '#!/bin/zsh\nexec /bin/zsh "${0:A:h}/tools/run_macos.sh" setup\n'}
    renamed = {
        'Install_Tensile_Workbench_App.bat': ('Install Tensile Workbench - Windows.bat', batch.format(action='install-app')),
        'Launch_Tensile_Workbench_App.bat': ('Launch Tensile Workbench - Windows.bat', batch.format(action='desktop')),
        'Install_Tensile_Workbench_App.command': ('Install Tensile Workbench - macOS.command',
            '#!/bin/zsh\nexec /bin/zsh "${0:A:h}/tools/run_macos.sh" install-app\n'),
        'Launch_Tensile_Workbench.command': ('Launch Tensile Workbench - macOS.command',
            '#!/bin/zsh\n# Existing Dock launchers use this entry point to start their owned server.\n'
            'if [[ "${TENSILE_DESKTOP_APP:-}" == "1" ]]; then\n'
            '    exec /bin/zsh "${0:A:h}/tools/run_macos.sh" launch\nfi\n'
            'exec /bin/zsh "${0:A:h}/tools/run_macos.sh" desktop\n'),
    }
    known.update({old: content for old, (replacement, content) in renamed.items()
                  if (Path(root) / replacement).is_file()})
    for name, expected in known.items():
        path = Path(root) / name
        if not path.is_file() or path.is_symlink():
            continue
        raw = path.read_bytes()
        if raw.replace(b'\r\n', b'\n') != expected.encode('utf-8'):
            print('Kept modified legacy launcher: ' + name, flush=True)
            continue
        from workbench_updates import update_directory, atomic_write
        backup = update_directory(root) / 'legacy-launchers' / (hashlib.sha256(raw).hexdigest()[:12] + '-' + name)
        atomic_write(backup, raw)
        if path.read_bytes() == raw:
            path.unlink()


def check_project_files(root):
    if (root / '.tensile-update.lock').exists():
        raise RuntimeError('An update is in progress or needs recovery. Open Check for updates '
                           'in the desktop launcher to restore the previous version before starting.')
    required = ('tensile_workbench.ipynb', 'tensile_workbench.py', 'tensile_core.py',
                'tensile_display.py', 'tensile_plot_theme.py',
                'tensile_plot_view.py', 'tensile_plot_picker.py', 'tensile_group_picker.py', 'tensile_moves.py', 'tensile_move_review.py', 'tensile_overrides.py', 'tensile_override_view.py', 'tensile_plotly.py', 'tensile_group_plot.py', 'tensile_group_review.py', 'tensile_comparison.py', 'tensile_colors.py', 'tensile_properties.py',
                'tensile_instron.py', 'tensile_instron_pdf.py', 'tensile_columns.py', 'tensile_tables.py', 'tensile_gauge.py', 'tensile_fracture.py', 'tensile_exports.py', 'tensile_selection.py', 'tensile_specimens.py', 'tensile_inspector.py', 'tensile_fit.py', 'tensile_startup.py',
                'workbench_project.py', 'workbench_backups.py', 'tensile_backup_ui.py', 'migrate_tensile_project.py', 'launch_workbench.py',
                'workbench_environment.py', 'workbench_app.py', 'workbench_server.py',
                'tensile_activity.py', 'tensile_page_layout.py', 'tensile_order.py', 'tensile_variables.py', 'tensile_variable_table.py', 'tensile_property_variants.py', 'tensile_specimen_plot.py', 'tensile_specimen_charts.py', 'tensile_locations.py', 'tensile_settings.py',
                'web/templates/index.html.j2', 'web/templates/spinner.macro.html.j2',
                'web/static/tensile-favicon.svg', 'web/static/tensile-loading.svg',
                'web/static/tensile-theme.css', 'web/static/tensile-theme.js',
                'tensile_workbench_defaults.json', 'requirements.txt')
    unavailable = []
    for name in required:
        try:
            info = (root / name).stat()
            if not stat.S_ISREG(info.st_mode):
                unavailable.append(name + ' (not a file)')
            elif getattr(info, 'st_flags', 0) & getattr(stat, 'SF_DATALESS', 0):
                unavailable.append(name + ' (online-only)')
        except FileNotFoundError:
            unavailable.append(name + ' (missing)')
    if unavailable:
        raise RuntimeError('Restore/download these workbench files before continuing: '
                           + ', '.join(unavailable))


def require_runtime():
    supported = {'win32': ('amd64', 'x86_64'), 'darwin': ('arm64', 'aarch64', 'x86_64')}
    if (sys.platform not in supported or sys.version_info[:2] != PYTHON_VERSION
            or struct.calcsize('P') != 8 or sysconfig.get_config_var('Py_GIL_DISABLED')
            or platform.machine().lower() not in supported[sys.platform]):
        raise RuntimeError('Use standard 64-bit Python 3.14: Windows x86-64, or Mac Apple Silicon/Intel. '
                           'See SETUP.md. Free-threaded Python is not supported.')


def python_in(folder, system):
    return folder / ('Scripts/python.exe' if system == 'win32' else 'bin/python')


def environment_folder(root=ROOT, system=None, environ=None, user_home=None):
    system = system or sys.platform
    environ = os.environ if environ is None else environ
    if environ.get('TENSILE_ENV_DIR'):
        folder = Path(environ['TENSILE_ENV_DIR']).expanduser()
        if not folder.is_absolute():
            raise ValueError('TENSILE_ENV_DIR must be an absolute path outside the project and cloud storage.')
        return folder
    pointer = Path(root) / '.tensile-environment.json'
    if pointer.is_file():
        try:
            value = json.loads(pointer.read_bytes())
            folder = Path(value['environment']).expanduser()
            if value.get('schema_version') != 1 or not folder.is_absolute():
                raise ValueError('invalid environment path')
            validate_environment_location(folder, Path(root), environ)
        except (ValueError, KeyError, TypeError) as error:
            raise RuntimeError('The saved update environment is invalid. Use update recovery or rerun the app installer.') from error
        return folder
    if system == 'darwin':
        base = Path(user_home or Path.home()) / 'Library/Application Support/Tensile Workbench'
    elif system == 'win32' and environ.get('LOCALAPPDATA'):
        base = Path(environ['LOCALAPPDATA']) / 'TensileWorkbench'
    else:
        raise RuntimeError('Windows LOCALAPPDATA is missing, or this platform is unsupported. See SETUP.md.')
    # Python environments cannot be upgraded by moving/copying them. Keep the
    # previous interpreter and its caches intact and build this version beside it.
    return base / ENVIRONMENT_TAG / 'venv'


def validate_environment_location(folder, root=ROOT, environ=None):
    """Refuse project/cloud environments; never move or delete an existing one."""
    environ = os.environ if environ is None else environ
    target, code = folder.resolve(), root.resolve()
    if target == code or target.is_relative_to(code) or code.is_relative_to(target):
        raise ValueError('The Python environment must be separate from the workbench code folder.')
    parts = [part.casefold() for part in target.parts]
    if any(part == 'cloudstorage' or part.startswith(('onedrive', 'dropbox'))
           or part in ('mobile documents', 'google drive', 'googledrive', 'icloud drive') for part in parts):
        raise ValueError('The Python environment must be outside OneDrive and other cloud-synced folders.')
    for name in ('OneDrive', 'OneDriveConsumer', 'OneDriveCommercial'):
        if environ.get(name) and target.is_relative_to(Path(environ[name]).expanduser().resolve()):
            raise ValueError('The Python environment must be outside OneDrive.')


def child_environment(folder):
    env = os.environ.copy()
    for name in ('PYTHONHOME', 'PYTHONPATH', 'PYTHONPYCACHEPREFIX'):
        env.pop(name, None)
    base = folder.parent
    env.update(PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1',
               JUPYTER_PREFER_ENV_PATH='1', MPLBACKEND='Agg',
               JUPYTER_CONFIG_DIR=str(base / 'jupyter-config'),
               JUPYTER_DATA_DIR=str(base / 'jupyter-data'),
               JUPYTER_RUNTIME_DIR=str(base / 'jupyter-runtime'),
               IPYTHONDIR=str(base / 'ipython'), MPLCONFIGDIR=str(base / 'matplotlib'))
    return env


# Check the target before pip can make any changes, even with a custom location.
RUNTIME_CHECK = r'''
import sys
from pathlib import Path
root = Path(sys.argv[1])
sys.path.insert(0, str(root))
from workbench_environment import require_runtime
require_runtime()
if sys.prefix == sys.base_prefix or Path(sys.prefix).resolve() != Path(sys.argv[2]).resolve():
    raise RuntimeError('Expected an isolated virtual environment, not system Python.')
'''

# Ordinary launch validates installed versions and definitions without importing the
# numerical/UI stack in a throwaway process before the server imports it again.
PREFLIGHT_CHECK = RUNTIME_CHECK + r'''
import importlib.metadata, json
from packaging.requirements import Requirement
for line in (root / 'requirements.txt').read_text(encoding='utf-8').splitlines():
    line = line.strip()
    if not line or line.startswith('#'):
        continue
    requirement = Requirement(line)
    if requirement.marker and not requirement.marker.evaluate():
        continue
    actual = importlib.metadata.version(requirement.name)
    if actual not in requirement.specifier:
        raise RuntimeError(f'{requirement.name} {actual} does not satisfy {requirement}; rerun the app installer.')
from workbench_project import validate_project, decode_project
personal_recovery = False
for name in ('tensile_workbench_defaults.json', 'tensile_workbench.project.json'):
    path = root / name
    if path.is_file():
        if name == 'tensile_workbench_defaults.json':
            validate_project(json.loads(path.read_text(encoding='utf-8')))
        else:
            try:
                decode_project(path.read_bytes())
            except Exception as error:
                personal_recovery = True
                print(f'Settings recovery needed: {error}. Open Backups & restore in the workbench. '
                      'The existing file has not been changed.', flush=True)
'''

QUICK_CHECK = PREFLIGHT_CHECK + r'''
print('Dependencies OK. Personal settings need recovery; no data processed.' if personal_recovery else
      'Dependencies and saved definitions OK. No data processed.', flush=True)
'''

# Setup and explicit check still exercise imports to catch broken installations.
# Neither path constructs the UI, reads research data or calculates curves.
CHECK = PREFLIGHT_CHECK + r'''
import importlib
for module in ('numpy', 'pandas', 'matplotlib', 'openpyxl', 'ipywidgets',
               'jupyterlab', 'voila', 'ipykernel', 'plotly', 'anywidget', 'pdfplumber',
               'tensile_core', 'tensile_properties', 'tensile_instron', 'tensile_tables',
               'tensile_plotly', 'tensile_plot_view', 'tensile_workbench', 'tensile_startup',
               'workbench_server'):
    importlib.import_module(module)
print('Dependencies and imports OK. Personal settings need recovery; no data processed.' if personal_recovery else
      'Dependencies, imports and saved definitions OK. No data processed.', flush=True)
'''


def run(command, root, env):
    return subprocess.run([str(part) for part in command], cwd=root, env=env, check=True)


def verify(python, root, env, full=True):
    run([python, '-c', CHECK if full else QUICK_CHECK, root, python.parent.parent], root, env)


def setup(folder, root=ROOT, system=None):
    system = system or sys.platform
    python = python_in(folder, system)
    env = child_environment(folder)
    print('Setting up Tensile Workbench. Close any running workbench kernels first.', flush=True)
    print('Environment:', folder, flush=True)
    if not python.is_file():
        if folder.exists() and any(folder.iterdir()):
            raise RuntimeError('An incomplete or broken environment already exists at ' + str(folder)
                               + '. It was not overwritten. See SETUP.md for recovery.')
        print('Creating an environment outside the project folder...', flush=True)
        venv.EnvBuilder(with_pip=True).create(folder)
    else:
        print('Reusing the existing environment; no duplicate will be created.', flush=True)
    run([python, '-c', RUNTIME_CHECK, root, folder], root, env)
    # Keep compatible packages; do not retain a download cache or compile wheels.
    run([python, '-m', 'pip', 'install', '--no-cache-dir', '--only-binary=:all:',
         '-r', root / 'requirements.txt'], root, env)
    run([python, '-m', 'pip', 'check'], root, env)
    verify(python, root, env)
    run([python, '-m', 'ipykernel', 'install', '--sys-prefix', '--name', 'python3',
         '--display-name', 'Tensile Workbench'], root, env)
    installed = subprocess.check_output([str(python), '-m', 'pip', 'freeze'],
                                        cwd=root, env=env, text=True)
    (folder.parent / 'installed-packages.txt').write_text(installed, encoding='utf-8')
    (folder.parent / 'setup-complete.json').write_text(json.dumps({
        'completed': datetime.now().astimezone().isoformat(),
        'requirements_sha256': hashlib.sha256((root / 'requirements.txt').read_bytes()).hexdigest(),
        'environment': str(folder),
    }, indent=2) + '\n', encoding='utf-8')
    print('\nEnvironment ready. The app installer creates the desktop launcher.', flush=True)


def main(argv=None, root=None):
    root = Path(root or ROOT).resolve()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('setup', 'launch', 'check', 'install-app', 'desktop'))
    action = parser.parse_args(argv).action
    require_runtime()
    check_project_files(root)
    folder = environment_folder(root)
    validate_environment_location(folder, root)
    if action in ('install-app', 'desktop') and sys.platform != 'win32':
        raise RuntimeError('Use Install Tensile Workbench - macOS.command for the Mac app.')
    if action in ('setup', 'install-app'):
        setup(folder, root)
        if action == 'install-app':
            run([python_in(folder, 'win32'), root / 'tools/install_windows_app.py'], root, child_environment(folder))
        return 0
    python = python_in(folder, sys.platform)
    if not python.is_file():
        installer = ('Install Tensile Workbench - Windows.bat' if sys.platform == 'win32'
                     else 'Install Tensile Workbench - macOS.command')
        raise RuntimeError(f'The workbench environment was not found. Run {installer} first. See SETUP.md.')
    print('Using environment:', folder, flush=True)
    env = child_environment(folder)
    if action == 'desktop':
        pythonw = folder / 'Scripts/pythonw.exe'
        launcher = root / 'tools/windows_app.py'
        if not pythonw.is_file() or not launcher.is_file():
            raise RuntimeError('Run Install Tensile Workbench - Windows.bat first.')
        # The control window performs preflight in its managed child and shows errors.
        subprocess.Popen([str(pythonw), str(launcher), '--environment', str(folder)],
                         cwd=root, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, close_fds=True,
                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return 0
    verify(python, root, env, full=action == 'check')
    if action == 'launch':
        print('The web app opens automatically. '
              + ('Use the Dock app to view logs or stop the server.' if os.environ.get('TENSILE_DESKTOP_APP') == '1'
                 else 'Leave this window open; Ctrl-C stops the server.'), flush=True)
        run([python, root / 'launch_workbench.py'], root, env)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print('\nStopped.')
        raise SystemExit(130)
    except Exception as error:
        print('\nCould not complete setup/launch:', error, file=sys.stderr)
        print('See SETUP.md. No research data or plots were processed.', file=sys.stderr)
        raise SystemExit(1)
