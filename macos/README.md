# Native Mac launcher

`Launcher.swift` is the small AppKit application hosting the launcher and live
log window, not the browser workbench itself. Its child process starts the
`Launch Tensile Workbench - macOS.command` with `TENSILE_DESKTOP_APP=1` in an isolated process group. Without that flag, the same file opens the installed desktop app. Stop
and Quit affect only that group. The app does not embed Python or research data.

`Info.plist` is a portable template. `tools/install_macos_app.py` writes the
checkout path and optional `TENSILE_ENV_DIR` only into the temporary/installed
bundle. Never put personal paths in this template.

`TensileWorkbench.icns` is the source icon asset, rendered from
`web/static/tensile-favicon.svg`. Keep its design in sync with that vector icon.
The icon is intentionally tracked; generated `.app` bundles are not.

## Build or update

On macOS 13+, use Python 3.14 and Apple Command Line Tools (or Xcode), then
run `Install Tensile Workbench - macOS.command` from the repository. If Python is
missing, the wrapper offers the official installer. It checks launcher/build
prerequisites, sets up Workbench packages and builds the app. Quit the existing
Dock app first. For a developer-only rebuild without package setup, use
`/bin/zsh tools/run_macos.sh app`.
See [SETUP.md](../SETUP.md#mac-dock-app) for the end-user workflow.

The installer compiles for the current Mac's architecture when the launcher
changes. Otherwise it reuses the installed executable after checking its source,
build recipe, signature, architecture and installation path. Every update
refreshes the bundle metadata/resources, signs the app ad-hoc, verifies it, and
installs it to the current user's Applications folder.
Compilation and module caches use a temporary directory that is cleaned up on
success or failure. A staged replacement and backup preserve the existing app
directory (and its Dock reference); the old Contents are restored if replacement
fails. The bundle-building step does not launch Workbench, run pip or process data.

The generated bundle includes this Swift source and the repository licence for
inspection/recovery. Git remains the source of truth. The bundle version comes
from `VERSION`; bump `BUILD_RECIPE` when compiler flags or deployment targets
change. For public prebuilt downloads,
Apple signing/notarisation and release packaging would be a separate workflow;
do not commit a locally generated personal app as a release.
