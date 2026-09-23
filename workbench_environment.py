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
PYTHON_VERSION = (3, 13)


def check_project_files(root):
    required = ('tensile_workbench.ipynb', 'tensile_workbench.py', 'tensile_core.py',
                'tensile_plot_view.py', 'tensile_plotly.py', 'tensile_group_plot.py', 'tensile_comparison.py', 'tensile_properties.py',
                'tensile_instron.py', 'tensile_tables.py', 'tensile_gauge.py', 'tensile_fracture.py', 'tensile_exports.py', 'tensile_selection.py', 'tensile_specimens.py', 'tensile_inspector.py', 'tensile_fit.py', 'tensile_startup.py',
                'workbench_project.py', 'migrate_tensile_project.py', 'launch_workbench.py',
                'workbench_environment.py', 'workbench_app.py', 'workbench_server.py',
                'web/templates/index.html.j2', 'web/static/tensile-favicon.svg',
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
        raise RuntimeError('Use standard 64-bit Python 3.13: Windows x86-64, or Mac Apple Silicon/Intel. '
                           'See SETUP.md. Free-threaded Python is not supported.')


def python_in(folder, system):
    return folder / ('Scripts/python.exe' if system == 'win32' else 'bin/python')


def legacy_windows_keys(raw):
    """Git may change LF/CRLF; both must find the original ZIP's environment."""
    lf = raw.replace(b'\r\n', b'\n')
    variants = (raw, lf, lf.replace(b'\n', b'\r\n'))
    return list(dict.fromkeys(hashlib.sha256(value).hexdigest()[:12] for value in variants))


def environment_folder(root=ROOT, system=None, environ=None, user_home=None):
    system = system or sys.platform
    environ = os.environ if environ is None else environ
    if environ.get('TENSILE_ENV_DIR'):
        folder = Path(environ['TENSILE_ENV_DIR']).expanduser()
        if not folder.is_absolute():
            raise ValueError('TENSILE_ENV_DIR must be an absolute path outside the project and cloud storage.')
        return folder
    if system == 'darwin':
        return Path(user_home or Path.home()) / 'Library/Application Support/Tensile Workbench/venv'
    if system != 'win32' or not environ.get('LOCALAPPDATA'):
        raise RuntimeError('Windows LOCALAPPDATA is missing, or this platform is unsupported. See SETUP.md.')
    base = Path(environ['LOCALAPPDATA']) / 'TensileWorkbench'
    canonical = base / 'venv'
    if canonical.exists():
        return canonical
    legacy = root / 'requirements-windows.txt'
    if legacy.is_file():
        for key in legacy_windows_keys(legacy.read_bytes()):
            folder = base / ('v17-py313-' + key) / 'venv'
            if python_in(folder, system).is_file():
                return folder
    return canonical


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
        raise RuntimeError(f'{requirement.name} {actual} does not satisfy {requirement}; run Setup again.')
from workbench_project import validate_project
for name in ('tensile_workbench_defaults.json', 'tensile_workbench.project.json'):
    path = root / name
    if path.is_file():
        validate_project(json.loads(path.read_text(encoding='utf-8')))
'''

QUICK_CHECK = PREFLIGHT_CHECK + r'''
print('Dependencies and saved definitions OK. No data processed.', flush=True)
'''

# Setup and explicit check still exercise imports to catch broken installations.
# Neither path constructs the UI, reads research data or calculates curves.
CHECK = PREFLIGHT_CHECK + r'''
import importlib
for module in ('numpy', 'pandas', 'matplotlib', 'openpyxl', 'ipywidgets',
               'jupyterlab', 'voila', 'ipykernel', 'plotly', 'anywidget',
               'tensile_core', 'tensile_properties', 'tensile_instron', 'tensile_tables',
               'tensile_plotly', 'tensile_plot_view', 'tensile_workbench', 'tensile_startup',
               'workbench_server'):
    importlib.import_module(module)
print('Dependencies, imports and saved definitions OK. No data processed.', flush=True)
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
    print('\nSetup complete. Open Launch_Tensile_Workbench.'
          + ('bat' if system == 'win32' else 'command') + '.', flush=True)


def main(argv=None, root=None):
    root = Path(root or ROOT).resolve()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('setup', 'launch', 'check'))
    action = parser.parse_args(argv).action
    require_runtime()
    check_project_files(root)
    folder = environment_folder(root)
    validate_environment_location(folder, root)
    if action == 'setup':
        setup(folder, root)
        return 0
    python = python_in(folder, sys.platform)
    if not python.is_file():
        raise RuntimeError('The workbench environment was not found. Run Setup_Tensile_Workbench.'
                           + ('bat' if sys.platform == 'win32' else 'command') + ' first. See SETUP.md.')
    print('Using environment:', folder, flush=True)
    env = child_environment(folder)
    verify(python, root, env, full=action == 'check')
    if action == 'launch':
        print('The web app opens automatically. Leave this window open; Ctrl-C stops the server.', flush=True)
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
