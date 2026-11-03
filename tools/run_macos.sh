#!/bin/zsh
set -u
PROJECT_DIR="${${(%):-%x}:A:h:h}"

find_python() {
    local env_dir="${TENSILE_ENV_DIR:-$HOME/Library/Application Support/Tensile Workbench/py314/venv}"
    # Finder may not inherit Homebrew's PATH. Prefer the existing environment.
    local -a candidates=("$env_dir/bin/python" "/opt/homebrew/bin/python3.14"
        "/opt/homebrew/opt/python@3.14/bin/python3.14" "/usr/local/bin/python3.14"
        "/usr/local/opt/python@3.14/bin/python3.14"
        "/Library/Frameworks/Python.framework/Versions/3.14/bin/python3")
    local name found candidate
    for name in python3.14 python3; do
        found="$(command -v "$name" 2>/dev/null)" || continue
        candidates+=("$found")
    done
    PYTHON_BIN=""
    for candidate in "${candidates[@]}"; do
        [[ -x "$candidate" ]] || continue
        if "$candidate" -c 'import sys,struct,sysconfig; sys.exit(not (sys.version_info[:2]==(3,14) and struct.calcsize("P")==8 and not sysconfig.get_config_var("Py_GIL_DISABLED")))' >/dev/null 2>&1; then
            PYTHON_BIN="$candidate"
            return 0
        fi
    done
    return 1
}

bootstrap_python() {
    /bin/zsh "$PROJECT_DIR/tools/install_python_macos.sh"
}

ensure_python() {
    PYTHON_INSTALLED=0
    find_python && return 0
    bootstrap_python || return 1
    PYTHON_INSTALLED=1
    find_python || { print -u2 -r -- 'Python 3.14 was not found after installation. Rerun Setup, or see SETUP.md.'; return 1; }
}

run_macos_main() {
    local action="${1:-}" result=0
    if [[ "$action" == update-check || "$action" == update-dialog ]]; then
        shift
        find_python || return 1
        if [[ "$action" == update-check ]]; then
            exec "$PYTHON_BIN" "$PROJECT_DIR/tools/update_workbench.py" check "$@"
        else
            exec "$PYTHON_BIN" "$PROJECT_DIR/tools/update_workbench.py" dialog "$@"
        fi
    fi
    [[ "$action" == setup || "$action" == launch || "$action" == app ]] || return 2
    export PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1
    if ensure_python; then
        # A first launch with no Python also needs the isolated Workbench packages.
        if [[ "$PYTHON_INSTALLED" == 1 && "$action" != setup ]]; then
            "$PYTHON_BIN" "$PROJECT_DIR/workbench_environment.py" setup
            result=$?
        fi
        if (( result == 0 )); then
            if [[ "$action" == app ]]; then
                "$PYTHON_BIN" "$PROJECT_DIR/tools/install_macos_app.py"
                result=$?
            else
                "$PYTHON_BIN" "$PROJECT_DIR/workbench_environment.py" "$action"
                result=$?
                if [[ "$action" == setup && "$result" == 0 ]]; then
                    if ! "$PYTHON_BIN" "$PROJECT_DIR/tools/install_macos_app.py"; then
                        print -r -- 'Python setup succeeded, but the Dock app was not installed/updated.'
                        print -r -- 'Follow the message above, then run Install_Tensile_Workbench_App.command.'
                        print -r -- 'Launch_Tensile_Workbench.command remains available.'
                    fi
                fi
            fi
        fi
    else
        result=1
    fi
    if (( result != 0 )); then
        print -r -- 'Setup/launch stopped. Read the message above and SETUP.md.'
    fi
    if [[ "$action" == setup || "$action" == app || "$result" != 0 ]]; then
        read -r 'reply?Press Return to close. '
    fi
    return "$result"
}

if [[ "$ZSH_EVAL_CONTEXT" == toplevel ]]; then
    run_macos_main "$@"
    exit $?
fi
