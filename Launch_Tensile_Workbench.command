#!/bin/zsh
set -eu
PROJECT_DIR="${0:A:h}"
ENV_DIR="${TENSILE_ENV_DIR:-$HOME/Library/Application Support/Tensile Workbench/venv}"
# Keep generated Python cache files out of the synced project too.
export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-$HOME/Library/Caches/Tensile Workbench/pycache}"
fail() {
    print -r -- "$1"
    read -r "reply?Press Return to close. "
    exit 1
}
[[ -x "$ENV_DIR/bin/python" ]] || fail "The local workbench environment is missing: $ENV_DIR"
# Check availability without opening cloud-only files and hanging OneDrive.
"$ENV_DIR/bin/python" - "$PROJECT_DIR" <<'PY' || fail "Download the listed workbench files in Finder, then reopen this launcher."
from pathlib import Path
import stat
import sys
root = Path(sys.argv[1])
required = (
    'tensile_workbench.ipynb',
    'tensile_workbench.py',
    'tensile_plot_view.py',
    'tensile_plotly.py',
    'tensile_core.py',
    'tensile_properties.py',
    'tensile_instron.py',
    'tensile_tables.py',
    'tensile_startup.py',
    'launch_workbench.py',
    'migrate_tensile_project.py',
    'workbench_project.py',
    'tensile_workbench_defaults.json',
)
unavailable = []
for name in required:
    try:
        info = (root / name).stat()
    except FileNotFoundError:
        unavailable.append(f'{name} (missing)')
        continue
    if getattr(info, 'st_flags', 0) & getattr(stat, 'SF_DATALESS', 0):
        unavailable.append(f'{name} (online-only)')
if unavailable:
    print('These workbench files must be available locally:')
    print('\n'.join('  ' + name for name in unavailable))
    print('Your data folder also needs to be available locally for plotting.')
    sys.exit(1)
PY
"$ENV_DIR/bin/python" "$PROJECT_DIR/migrate_tensile_project.py" || fail "Could not prepare saved graph definitions."
"$ENV_DIR/bin/python" -c 'import plotly, anywidget' || fail "Plotly support is missing. Install requirements.txt into the local workbench environment."
cd "$PROJECT_DIR"
print -r -- "Opening Tensile Workbench. In Jupyter, choose Run > Run All Cells to restore your saved workspace."
print -r -- "This server is local-only. Press Ctrl-C here to stop it."
exec "$ENV_DIR/bin/python" "$PROJECT_DIR/launch_workbench.py"
