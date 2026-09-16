"""Open the web app by default; --notebook keeps advanced JupyterLab access."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--notebook', action='store_true', help='Open the advanced notebook editor instead')
    options, extra = parser.parse_known_args(sys.argv[1:] if argv is None else argv)
    env = os.environ.copy()
    env['TENSILE_WORKBENCH_DIR'] = str(ROOT)
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    if options.notebook:
        command = [sys.executable, '-m', 'jupyterlab', str(ROOT / 'tensile_workbench.ipynb'),
                   '--ServerApp.ip=127.0.0.1', '--ServerApp.root_dir=' + str(ROOT)]
        print('Opening advanced notebook mode. Choose Run > Run All Cells.', flush=True)
    else:
        command = [sys.executable, '-m', 'voila', str(ROOT / 'workbench_app.py'),
                   '--Voila.ip=127.0.0.1', '--token',
                   '--VoilaConfiguration.extension_language_mapping=.py=python',
                   '--VoilaConfiguration.language_kernel_mapping=python=python3',
                   '--MappingKernelManager.cull_interval=60',
                   '--MappingKernelManager.cull_idle_timeout=1800',
                   '--MappingKernelManager.cull_connected=False']
        print('Opening Tensile Workbench in your browser. The app starts automatically.', flush=True)
    return subprocess.call([*command, *extra], cwd=ROOT, env=env)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print('\nWorkbench launcher stopped.')
        raise SystemExit(130)
