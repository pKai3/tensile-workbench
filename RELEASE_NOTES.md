# Tensile Workbench 1.0.6

- Fix a Mac launcher hang during **Install update and restart** and quitting.
  Finish stopping the owned server before closing the launcher, while keeping
  the updater's acknowledgement and actual-exit checks.
- Reuse the installed Mac launcher when its source and build settings are
  unchanged. Routine updates refresh the app metadata and signature without
  recompiling Swift. Launcher changes still require a one-time rebuild.
- Label the four source-folder entry files explicitly: **Install/Launch Tensile
  Workbench - Windows.bat** and **Install/Launch Tensile Workbench - macOS.command**.
  Installed Dock, desktop and Start menu app names stay **Tensile Workbench**.

Use **Check for updates → Install update and restart** in the desktop app.
Saved analyses, specimen overrides, data and output folders are preserved.

For an older Mac launcher, click **Stop** and wait for **Workbench stopped**
before installing this update. This avoids its old shutdown hang during the
one-time upgrade to the fixed launcher.
