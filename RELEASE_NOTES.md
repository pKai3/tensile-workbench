# Tensile Workbench 1.0.0

This is the first numbered release for the built-in updater. It includes the
existing analysis tools and saved settings support, plus desktop updates for
Windows and macOS.

- Both desktop launchers check for published updates in the background.
- **Check for updates** shows release notes and **Install update and restart**.
- Windows ZIP installations update without Git or a GitHub account. Clean Git
  checkouts can advance to the release without overwriting local code changes.
- Updates preserve saved analyses, specimen overrides, variables, folder
  preferences, research data and output. Previous code and settings snapshots
  are retained for recovery. Changed dependencies are prepared in a separate
  environment; the current environment is kept.
- Downloads and package files are checked against SHA-256 hashes before use.

**One-time upgrade:** close Workbench, download and extract the
**Tensile-Workbench-1.0.0.zip** release asset into your existing application
folder, and rerun the app installer. Git users can pull and rerun the app
installer. Keep personal settings, data and output folders in place.
Subsequent numbered releases can be installed from the launcher.
