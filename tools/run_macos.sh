#!/bin/zsh
set -u
PROJECT_DIR="${0:A:h:h}"
ACTION="${1:-}"
[[ "$ACTION" == setup || "$ACTION" == launch ]] || exit 2
export PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1
ENV_DIR="${TENSILE_ENV_DIR:-$HOME/Library/Application Support/Tensile Workbench/venv}"
# Finder may not inherit Homebrew's PATH. Prefer the existing environment,
# then check standard Python.org and Homebrew install locations explicitly.
candidates=("$ENV_DIR/bin/python" "/opt/homebrew/bin/python3.13"
            "/usr/local/bin/python3.13"
            "/Library/Frameworks/Python.framework/Versions/3.13/bin/python3")
for name in python3.13 python3; do
    found="$(command -v "$name" 2>/dev/null)" || continue
    candidates+=("$found")
done
PYTHON_BIN=""
for candidate in "${candidates[@]}"; do
    [[ -x "$candidate" ]] || continue
    if "$candidate" -c 'import sys,struct,sysconfig; sys.exit(not (sys.version_info[:2]==(3,13) and struct.calcsize("P")==8 and not sysconfig.get_config_var("Py_GIL_DISABLED")))' >/dev/null 2>&1; then
        PYTHON_BIN="$candidate"
        break
    fi
done
if [[ -z "$PYTHON_BIN" ]]; then
    print -r -- "Install standard Python 3.13 for macOS from https://www.python.org/downloads/macos/"
    print -r -- "Choose the macOS 64-bit universal2 installer (Apple Silicon and Intel). See SETUP.md."
    RESULT=1
else
    "$PYTHON_BIN" "$PROJECT_DIR/workbench_environment.py" "$ACTION"
    RESULT=$?
fi
if (( RESULT != 0 )); then
    print -r -- "Setup/launch stopped. Read the error above and SETUP.md."
fi
if [[ "$ACTION" == setup || "$RESULT" != 0 ]]; then
    read -r "reply?Press Return to close. "
fi
exit "$RESULT"
