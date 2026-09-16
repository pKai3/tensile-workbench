"""Launch v18 using the existing Windows v17 environment; no new environment."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from migrate_tensile_v18 import migrate

ROOT = Path(__file__).resolve().parent


def main():
    if sys.platform != 'win32' or not os.environ.get('LOCALAPPDATA'):
        raise RuntimeError('Use Launch_Tensile_Interactive_v18.command on macOS.')
    requirements = ROOT / 'requirements-windows.txt'
    if not requirements.is_file():
        raise RuntimeError('Extract this patch into the existing working v17 Windows folder, not a new empty folder.')
    key = hashlib.sha256(requirements.read_bytes()).hexdigest()[:12]
    home = Path(os.environ['LOCALAPPDATA']) / 'TensileWorkbench' / ('v17-py313-' + key)
    python = home / 'venv/Scripts/python.exe'
    if not python.is_file():
        raise RuntimeError('The existing v17 environment was not found. Run the original 1_Setup_Windows.bat first.')
    migrate(ROOT)
    env = os.environ.copy()
    env.pop('PYTHONHOME', None)
    env.pop('PYTHONPATH', None)
    env.update(PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1', JUPYTER_PREFER_ENV_PATH='1',
               JUPYTER_CONFIG_DIR=str(home / 'jupyter-config'), JUPYTER_DATA_DIR=str(home / 'jupyter-data'),
               JUPYTER_RUNTIME_DIR=str(home / 'jupyter-runtime'), IPYTHONDIR=str(home / 'ipython'),
               MPLCONFIGDIR=str(home / 'matplotlib'))
    check = "import tensile_core_v18, tensile_instron_v18, tensile_tables_v18, tensile_workbench_v18; print('v18 imports OK. No data processed.')"
    subprocess.run([str(python), '-c', check], cwd=ROOT, env=env, check=True)
    print('Opening v18. Choose Run > Run All Cells. Press Ctrl-C here to stop.', flush=True)
    subprocess.run([str(python), '-m', 'jupyterlab', str(ROOT / 'plot_tensile_interactive_v18.ipynb'),
                    '--ServerApp.ip=127.0.0.1', '--ServerApp.root_dir=' + str(ROOT)], cwd=ROOT, env=env, check=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('\nCould not open v18:', error, file=sys.stderr)
        sys.exit(1)
