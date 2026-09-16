# Tensile Workbench

Interactive tensile-data analysis in Jupyter, with static and Plotly views, specimen-property tables, Instron CSV comparisons, and saved graph definitions.

This repository starts from the working **v18** application. The original OneDrive installation is a separate, unchanged copy. No research data, generated results, or Python environment is stored in Git.

## Open the existing installation

- **macOS:** double-click `Launch_Tensile_Interactive_v18.command` in this repository, then choose **Run → Run All Cells** in the notebook. The launcher reuses the environment outside OneDrive, under `~/Library/Application Support/Tensile Workbench/venv`.
- **Windows with the existing v17 environment:** double-click `Launch_Tensile_Interactive_v18.bat`. The unchanged `requirements-windows.txt` identifies that existing environment; no reinstall is required.
- Detailed application usage: [v18 guide](README_Tensile_Interactive_v18.md).

On the original Mac, ignored `data` and `output` links point to the existing OneDrive folders. They do not duplicate those folders. Exports from either installation therefore reach the same output folder. The copied graph settings are independent: changing them here does not update the OneDrive installation.

## Another computer or a fresh clone

The local data/output links are **not** included in a clone. Create a local `data` folder, or select an existing data folder in the workbench settings. Set a suitable output folder as well. The tracked v18 project supplies the initial graph definitions; no v17 project is needed when that v18 project is present.

If the launcher's existing environment is unavailable, create a Python 3.13 virtual environment **outside a cloud-synced folder**, install `requirements_tensile_interactive_v18.txt` into it, and run:

```text
python -m jupyterlab plot_tensile_interactive_v18.ipynb
```

Run that command from this repository using the new environment's Python. The Mac launcher can use a different environment through `TENSILE_ENV_DIR`. The supplied Windows launcher specifically targets the existing v17 environment; the direct Jupyter command works with a fresh environment.

## Version control

- Source code, documentation, the clean notebook, defaults, and `tensile_workbench_v18.project.json` are tracked. Saved graph settings can therefore be reviewed and committed too.
- Research files, output folders, environments, previous-save backups, archives and share ZIPs are ignored.
- Before committing a notebook, clear its outputs and save it. Do not commit exported tables or embedded research plots. Review changes in GitHub Desktop before committing and pushing.
- Use ordinary Git commits for ongoing edits. Retain the existing versioned filenames for now; this repository setup does not change the calculation methods.
- Close the notebook before switching branches or pulling changes that modify its saved project. Restart its kernel after code updates.

No licence has been added; this is a private repository, not a public software release.

