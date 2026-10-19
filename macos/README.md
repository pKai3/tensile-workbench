# Native Mac launcher

`Launcher.swift` is the small AppKit application hosting the launcher and live
log window, not the browser workbench itself. Its child process starts the
existing `Launch_Tensile_Workbench.command` in an isolated process group. Stop
and Quit affect only that group. The app does not embed Python or research data.

`Info.plist` is a portable template. `tools/install_macos_app.py` writes the
checkout path and optional `TENSILE_ENV_DIR` only into the temporary/installed
bundle. Never put personal paths in this template.

`TensileWorkbench.icns` is the source icon asset, rendered from
`web/static/tensile-favicon.svg`. Keep its design in sync with that vector icon.
The icon is intentionally tracked; generated `.app` bundles are not.

## Build or update

On macOS 13+, install Python 3.13 and Apple Command Line Tools (or Xcode), then
run `Install_Tensile_Workbench_App.command` from the repository. Setup also calls
the installer after Python setup succeeds. Quit the existing Dock app first.
See [SETUP.md](../SETUP.md#mac-dock-app) for the end-user workflow.

The installer compiles for the current Mac's architecture, signs the app
ad-hoc, verifies it, and installs it to the current user's Applications folder.
Compilation and module caches use a temporary directory that is cleaned up on
success or failure. A staged replacement and backup preserve the existing app
directory (and its Dock reference); the old Contents are restored if replacement
fails. Installation does not launch Workbench, run pip or process data.

The generated bundle includes this Swift source and the repository licence for
inspection/recovery. Git remains the source of truth. Change the template's
bundle version when releasing launcher changes. For public prebuilt downloads,
Apple signing/notarisation and release packaging would be a separate workflow;
do not commit a locally generated personal app as a release.
