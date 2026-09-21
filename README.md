# Tensile Workbench

Browser-based tensile-data analysis, with static and Plotly views, specimen-property tables, Instron CSV comparisons, and saved graph definitions. Launch opens the ready-to-use web app: no notebook commands, cells or kernel selection are needed.

This repository starts from the working **v18** application. The original OneDrive installation is a separate, unchanged copy. Current deployments contain no research data, personal graph definitions, generated results, or Python environment. Only the small, explicitly synthetic examples are bundled.

## Install and open the workbench

1. Clone this repository or download and **extract** the ZIP to a writable folder.
2. Install standard **Python 3.13, 64-bit** if needed (Windows x86-64; Mac Apple Silicon or Intel). See [setup instructions](SETUP.md) for download links and troubleshooting.
3. First-time users: double-click **`Setup_Tensile_Workbench.bat`** on Windows or **`Setup_Tensile_Workbench.command`** on Mac. Setup downloads dependencies and creates or reuses an environment outside the code/data folders. Close running workbench sessions before rerunning Setup.
4. Double-click **`Launch_Tensile_Workbench.bat`** on Windows or **`Launch_Tensile_Workbench.command`** on Mac. The web app opens and starts automatically.

Existing users upgrading from notebook-only mode should run Setup once to add Voilà, then use Launch normally. The original Windows v17 environment and Mac environment are recognised and reused. If dependencies need updating, rerun Setup; compatible installed packages are kept. Ordinary Launch never downloads packages or creates an environment.

- Detailed application usage: [workbench guide](WORKBENCH_GUIDE.md).

Graph definitions support confirmed deletion with persistent Undo. The Specimens table has **global Include defaults with explicit per-graph overrides**, controlling statistics and every plot method without renaming source files. Excluded rows remain available for review. A single **Checks** column lists only failed/incomplete identity, original-data agreement and fit checks. The Summary tab compares **Calc / Instron** side by side under each property. `!` remains a hard-ignore marker anywhere in data filenames or nested folder names. See the guide for export/audit details.

On first run the app asks for **Data folder** and **Output folder** before loading data. Defaults are **`./data`** and **`./output`**, relative to the folder containing the workbench code, not the terminal's current directory. Either location can be an absolute path elsewhere on the computer or an accessible external/network drive.

Click **Save folders and open** to confirm. Missing folders are created; existing files are not moved or copied. Expand **Folders · data and output locations** at the top of the workbench to change them later. Paths are saved in the ignored, installation-local `.tensile-paths.json`, separate from the shared graph definitions. An unavailable folder or invalid settings file brings the setup form back instead of silently choosing another location.

Three lightweight synthetic groups (three specimens each) are available alongside your own data. Use **Show sample data** beside the sample-group selector to show or hide them. The setting is remembered across sessions. No folder switching is required: your data and output paths remain unchanged, and the bundled sample source is managed separately in the background. Fresh installations start with samples visible and a simple **Demo comparison** graph. Hiding samples removes them from the selector, calculations and plots while retaining their saved graph selections for next time. See [the example description](examples/README.md) for the invented inputs and curve construction. They are not experimental material properties.

On the original Mac, ignored `data` and `output` links point to the existing OneDrive folders. They do not duplicate those folders. Accepting the defaults uses these links; another location can be chosen instead. The copied graph settings are independent: changing them here does not update the OneDrive installation.

## Another computer or a fresh clone

The local data/output links and chosen paths are **not** included in a clone. The new user gets the first-run folder form. The shared `tensile_workbench_defaults.json` supplies only the generic demo graph and a blank-new-graph template. Personal graphs are saved in ignored `tensile_workbench.project.json`. If no current project exists, `migrate_tensile_project.py` can copy an older v18/v17 project from the same folder, or seed one from the defaults; it never overwrites an existing current project.

**One-time update for existing clones:** before pulling the change that stops tracking personal definitions, copy your `tensile_workbench.project.json` outside the checkout. Git may remove a formerly tracked file during that update. Restore your copy afterwards if needed. Future edits are local-only; keep your own backups or share that file separately by choice. Older Git commits may still contain historical definitions; this update does not rewrite history.

Use the supplied Setup for a new computer. Environments, research data, outputs and machine-specific folder choices are not downloaded from GitHub. Setup validates dependencies and saved definitions but does **not** process data, regenerate plots, or rewrite graph settings.

Advanced/manual installation: create a Python 3.13 virtual environment **outside a cloud-synced folder**, install `requirements.txt` into it, and run:

```text
python /path/to/tensile-workbench/launch_workbench.py
```

Use the environment's Python; the command works from any working directory. On Windows, use the corresponding Windows path. `launch_workbench.py` locates its own folder and starts the app there. Both supplied launchers support an absolute `TENSILE_ENV_DIR` override for an environment outside the code and cloud-storage folders. See [SETUP.md](SETUP.md) for environment locations, recovery and checks.

## Advanced notebook access

The original notebook remains available for developers and advanced users. Use the workbench environment's Python:

```text
python /path/to/tensile-workbench/launch_workbench.py --notebook
```

Only this optional mode uses JupyterLab and **Run → Run All Cells**. The normal web app is served by Voilà from `workbench_app.py`, not your saved notebook. Both modes use the same calculations, data settings and graph JSON. Avoid editing the same project in multiple tabs/sessions; autosave detects conflicting edits. Restart the launcher after code updates. Do not expose the local service directly to the internet.

## Version control

- Source code, documentation, the clean notebook, generic defaults, and the nine synthetic demo CSVs are tracked.
- Personal graph definitions (`tensile_workbench.project.json`), chosen folder paths, research files, output folders, environments, previous-save backups, archives and share ZIPs are ignored. Back up personal definitions independently of Git.
- Before committing a notebook, clear its outputs and save it. Do not commit exported tables or embedded research plots. Review changes in GitHub Desktop before committing and pushing.
- Use stable filenames and ordinary Git commits for ongoing edits. The `v18-baseline` tag preserves the pre-migration application; do not create `_vX` source copies. The naming and folder setup changes do not change calculation methods.
- Close the app/notebook and stop its launcher before switching branches or pulling updates. Restart the launcher after code updates (or the kernel in notebook mode).

## Checks without research plots

```text
python -m unittest discover -s tests -v
```

These use temporary synthetic data and check first-run behaviour, saved locations, path changes, launching from another working directory, and output routing. They do not process research datasets or regenerate their plots.

No licence has been added; this is a private repository, not a public software release.
