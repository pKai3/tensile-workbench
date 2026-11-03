#!/bin/zsh
# Existing Dock launchers use this entry point to start their owned server.
if [[ "${TENSILE_DESKTOP_APP:-}" == "1" ]]; then
    exec /bin/zsh "${0:A:h}/tools/run_macos.sh" launch
fi
exec /bin/zsh "${0:A:h}/tools/run_macos.sh" desktop
