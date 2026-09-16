"""Portable entry point: use this environment's Python, from any working folder."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def main():
    env = os.environ.copy()
    env['TENSILE_WORKBENCH_DIR'] = str(ROOT)
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    print('Opening Tensile Workbench. On first run choose the data and output folders in the notebook.', flush=True)
    return subprocess.call([
        sys.executable, '-m', 'jupyterlab', str(ROOT / 'plot_tensile_interactive_v18.ipynb'),
        '--ServerApp.ip=127.0.0.1', '--ServerApp.root_dir=' + str(ROOT), *sys.argv[1:],
    ], cwd=ROOT, env=env)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print('\nWorkbench launcher stopped.')
        raise SystemExit(130)
