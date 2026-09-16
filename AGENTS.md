# Tensile Workbench

- Work in this Git checkout. The original OneDrive application is a separate installation; do not edit, move, or delete it unless explicitly requested.
- `data` and `output` may be symlinks to research folders outside the repository. Never treat their contents as disposable fixtures or commit them.
- Do not regenerate research plots or tables unless explicitly requested. Use focused numerical checks or synthetic fixtures for tests.
- The Python environment is outside the repository and outside OneDrive. Do not create an environment in a synced folder or copy one into Git.
- Preserve saved graph definitions and user edits. `tensile_workbench.project.json` is personal and ignored, along with its backups and locks. Only generic `tensile_workbench_defaults.json` is shared.
- The nine explicitly synthetic CSV files in `examples/data/Demo_*` are deployment fixtures, not research data. Do not broaden the CSV ignore exceptions to research folders.
- Keep notebook outputs clear before committing. Do not publish research data, generated results, credentials, or personal machine paths.
- Use stable filenames. Version history belongs in Git commits and tags, not `_vX` filenames or duplicate source copies.
- Data/output paths belong in ignored `.tensile-paths.json`, not in shared graph definitions. First-run defaults are `./data` and `./output`, resolved relative to the workbench folder, never the terminal's current directory.
- Bundled examples are a separate hidden source (`sample_data_directory`) with a persistent `show_sample_data` toggle in that same local settings file. Never change the user's data path to show examples; keep sample group/specimen identities separate from research data.
