"""Launch the workbench using the existing Windows environment; no reinstall."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from migrate_tensile_project import migrate

ROOT = Path(__file__).resolve().parent


def main():
    if sys.platform != 'win32' or not os.environ.get('LOCALAPPDATA'):
        raise RuntimeError('Use Launch_Tensile_Workbench.command on macOS.')
    requirements = ROOT / 'requirements-windows.txt'
    if not requirements.is_file():
        raise RuntimeError('requirements-windows.txt is missing. Restore it from Git, or use launch_workbench.py with your Python environment.')
    key = hashlib.sha256(requirements.read_bytes()).hexdigest()[:12]
    home = Path(os.environ['LOCALAPPDATA']) / 'TensileWorkbench' / ('v17-py313-' + key)
    python = home / 'venv/Scripts/python.exe'
    if not python.is_file():
        raise RuntimeError('The existing Windows environment was not found. See README.md to create a separate environment and run launch_workbench.py.')
    migrate(ROOT)
    env = os.environ.copy()
    env.pop('PYTHONHOME', None)
    env.pop('PYTHONPATH', None)
    env.update(PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', JUPYTER_PREFER_ENV_PATH='1',
               JUPYTER_CONFIG_DIR=str(home / 'jupyter-config'), JUPYTER_DATA_DIR=str(home / 'jupyter-data'),
               JUPYTER_RUNTIME_DIR=str(home / 'jupyter-runtime'), IPYTHONDIR=str(home / 'ipython'),
               MPLCONFIGDIR=str(home / 'matplotlib'))
    check = "import tensile_core, tensile_instron, tensile_tables, tensile_workbench; print('Workbench imports OK. No data processed.')"
    subprocess.run([str(python), '-c', check], cwd=ROOT, env=env, check=True)
    print('Opening Tensile Workbench. Choose Run > Run All Cells. Press Ctrl-C here to stop.', flush=True)
    subprocess.run([str(python), str(ROOT / 'launch_workbench.py')], cwd=ROOT, env=env, check=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('\nCould not open Tensile Workbench:', error, file=sys.stderr)
        sys.exit(1)
