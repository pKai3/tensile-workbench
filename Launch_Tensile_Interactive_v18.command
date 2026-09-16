#!/bin/zsh
set -eu
PROJECT_DIR="${0:A:h}"
ENV_DIR="${TENSILE_ENV_DIR:-$HOME/Library/Application Support/Tensile Workbench/venv}"
# Keep generated Python cache files out of the synced project too.
export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-$HOME/Library/Caches/Tensile Workbench/pycache}"
NOTEBOOK="$PROJECT_DIR/plot_tensile_interactive_v18.ipynb"
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
    'plot_tensile_interactive_v18.ipynb',
    'tensile_workbench_v18.py',
    'tensile_plot_view_v18.py',
    'tensile_plotly_v18.py',
    'tensile_core_v18.py',
    'tensile_properties_v18.py',
    'tensile_instron_v18.py',
    'tensile_tables_v18.py',
    'tensile_startup_v18.py',
    'launch_workbench.py',
    'migrate_tensile_v18.py',
    'workbench_project_v18.py',
    'tensile_workbench_defaults_v18.json',
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
"$ENV_DIR/bin/python" "$PROJECT_DIR/migrate_tensile_v18.py" || fail "Could not prepare v18 saved graph definitions."
"$ENV_DIR/bin/python" -c 'import plotly, anywidget' || fail "Plotly support is missing. Install requirements_tensile_interactive_v18.txt into the local workbench environment."
cd "$PROJECT_DIR"
print -r -- "Opening v18. In Jupyter, choose Run > Run All Cells to restore your saved workspace."
print -r -- "This server is local-only. Press Ctrl-C here to stop it."
exec "$ENV_DIR/bin/python" "$PROJECT_DIR/launch_workbench.py"
