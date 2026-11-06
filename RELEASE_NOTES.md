# Tensile Workbench 1.0.5

- Fix a Mac launcher hang during **Install update and restart** and quitting.
  Finish stopping the owned server before closing the launcher, while keeping
  the updater's acknowledgement and actual-exit checks.
- Reuse the installed Mac launcher when its source and build settings are
  unchanged. Routine updates refresh the app metadata and signature without
  recompiling Swift. Launcher changes still require a one-time rebuild.

Use **Check for updates → Install update and restart** in the desktop app.
Saved analyses, specimen overrides, data and output folders are preserved.
