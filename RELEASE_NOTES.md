# Tensile Workbench 1.0.2

- Fix Windows updates failing with “Git could not safely update this checkout”
  and “WinError 2” when a copied installation includes a `.git` folder but Git
  is not installed. Colleagues do not need Git or a GitHub account.
- Verify and install the release package directly when Git is unavailable,
  preserving settings, data and Git history. Subsequent updates for that
  installation continue to use release packages.
- Accept ordinary Windows line-ending differences when verifying original
  release files. Actual code edits still stop the update. Rollback retains the
  exact original files.
- Existing Git installations can still update through Git; standard Windows
  and GitHub Desktop locations are detected when absent from PATH.

Use **Check for updates → Install update and restart** normally.

**Already blocked by WinError 2?** The old updater cannot install its own fix.
Close Workbench, extract **Tensile-Workbench-1.0.2.zip** into the existing
application folder, replacing the application files, and run
**Install_Tensile_Workbench_App.bat**. Keep the existing folder, personal settings,
data and output. After this one-time repair, use the app's update button.
