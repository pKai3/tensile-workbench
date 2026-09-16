# Tensile Workbench

- Work in this Git checkout. The original OneDrive application is a separate installation; do not edit, move, or delete it unless explicitly requested.
- `data` and `output` may be symlinks to research folders outside the repository. Never treat their contents as disposable fixtures or commit them.
- Do not regenerate research plots or tables unless explicitly requested. Use focused numerical checks or synthetic fixtures for tests.
- The Python environment is outside the repository and outside OneDrive. Do not create an environment in a synced folder or copy one into Git.
- Preserve saved graph definitions and user edits. `tensile_workbench.project.json` is intentionally tracked; its previous-save backups and locks are not.
- Keep notebook outputs clear before committing. Do not publish research data, generated results, credentials, or personal machine paths.
- Use stable filenames. Version history belongs in Git commits and tags, not `_vX` filenames or duplicate source copies.
- Data/output paths belong in ignored `.tensile-paths.json`, not in shared graph definitions. First-run defaults are `./data` and `./output`, resolved relative to the workbench folder, never the terminal's current directory.
