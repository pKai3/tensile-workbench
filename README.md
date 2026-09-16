# Tensile Workbench

Interactive tensile-data analysis in Jupyter, with static and Plotly views, specimen-property tables, Instron CSV comparisons, and saved graph definitions.

This repository starts from the working **v18** application. The original OneDrive installation is a separate, unchanged copy. No research data, generated results, or Python environment is stored in Git.

## Open the workbench

- **macOS:** double-click `Launch_Tensile_Workbench.command` in this repository, then choose **Run → Run All Cells** in the notebook. The launcher reuses the environment outside OneDrive, under `~/Library/Application Support/Tensile Workbench/venv`.
- **Windows with the existing v17 environment:** double-click `Launch_Tensile_Workbench.bat`. The unchanged `requirements-windows.txt` identifies that existing environment; no reinstall is required.
- Detailed application usage: [workbench guide](WORKBENCH_GUIDE.md).

On first run the notebook asks for **Data folder** and **Output folder** before loading data. Defaults are **`./data`** and **`./output`**, relative to the folder containing the workbench code, not the terminal's current directory. Either location can be an absolute path elsewhere on the computer or an accessible external/network drive.

Click **Save folders and open** to confirm. Missing folders are created; existing files are not moved or copied. Expand **Folders · data and output locations** at the top of the workbench to change them later. Paths are saved in the ignored, installation-local `.tensile-paths.json`, separate from the shared graph definitions. An unavailable folder or invalid settings file brings the setup form back instead of silently choosing another location.

On the original Mac, ignored `data` and `output` links point to the existing OneDrive folders. They do not duplicate those folders. Accepting the defaults uses these links; another location can be chosen instead. The copied graph settings are independent: changing them here does not update the OneDrive installation.

## Another computer or a fresh clone

The local data/output links and chosen paths are **not** included in a clone. The new user gets the first-run folder form. The tracked project supplies the initial graph definitions. If no current project exists, `migrate_tensile_project.py` can copy an older v18/v17 project from the same folder, or seed one from the defaults; it never overwrites an existing current project.

If the launcher's existing environment is unavailable, create a Python 3.13 virtual environment **outside a cloud-synced folder**, install `requirements.txt` into it, and run:

```text
python /path/to/tensile-workbench/launch_workbench.py
```

Use the new environment's Python; the command works from any working directory. On Windows, use the corresponding Windows path. `launch_workbench.py` locates its own folder and starts the notebook there. The Mac launcher can use a different environment through `TENSILE_ENV_DIR`. The supplied Windows launcher specifically targets the existing v17 environment; the portable Python entry point works with a fresh environment.

## Version control

- Source code, documentation, the clean notebook, defaults, and `tensile_workbench.project.json` are tracked. Saved graph settings can therefore be reviewed and committed too.
- Research files, output folders, environments, previous-save backups, archives and share ZIPs are ignored.
- Before committing a notebook, clear its outputs and save it. Do not commit exported tables or embedded research plots. Review changes in GitHub Desktop before committing and pushing.
- Use stable filenames and ordinary Git commits for ongoing edits. The `v18-baseline` tag preserves the pre-migration application; do not create `_vX` source copies. The naming and folder setup changes do not change calculation methods.
- Close the notebook before switching branches or pulling changes that modify its saved project. Restart its kernel after code updates.

## Checks without research plots

```text
python -m unittest discover -s tests -v
```

These use temporary synthetic data and check first-run behaviour, saved locations, path changes, launching from another working directory, and output routing. They do not process research datasets or regenerate their plots.

No licence has been added; this is a private repository, not a public software release.
