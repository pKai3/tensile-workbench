# Tensile Workbench

## Open or update the workbench

1. Clone the repository, or close the app and stop its launcher before pulling an update into an existing checkout. Review and commit your saved graph-definition edits before pulling.
2. First-time users: run **Setup_Tensile_Workbench.bat** (Windows) or **Setup_Tensile_Workbench.command** (Mac). Then open **Launch_Tensile_Workbench.bat** or **Launch_Tensile_Workbench.command**. Existing users can launch directly; rerun Setup only when dependencies need installing/updating. See [setup instructions](SETUP.md).
3. The web app opens in your browser and starts automatically. No notebook or kernel commands are needed. Existing users upgrading from notebook-only mode should run Setup once to add Voilà.
4. On first run, choose data and output folders, defaulting to **./data** and **./output** relative to the workbench folder. Expand **Folders** at the top to change these later.

The current graph definitions live in `tensile_workbench.project.json`; machine-specific folder choices live in ignored `.tensile-paths.json`. Git contains no raw data or generated outputs. Existing environments can be reused. Use Git commits and tags for history, not version suffixes on filenames.

## Choosing graphs

The Graph selector lists named graphs first, then unnamed drafts. **＋ Create new graph…** is always the last option; choose it, give the graph a name, then select sample groups and plot views. Existing unnamed `New graph` entries are displayed as **Untitled graph (draft)**, without deleting or renaming their saved definitions. **Duplicate graph** starts from the current graph's settings. Changes save automatically; hover over the saved-status message for revision/file details.

**Delete graph** asks for confirmation naming the current graph. It removes only the definition, never data or exported files. **Undo delete** restores the most recently deleted graph (and its specimen selections), even after reopening the app; repeat to restore earlier deletions. Deleting the last graph leaves a blank draft. Undo removes that automatic draft only if you have not edited it. A name collision during restoration gets a “restored” suffix rather than replacing another graph.

Select sample groups using the exact-name checkboxes. There is no numbered-range helper; any naming format is supported. The plot-display selector offers **Static plots** and **Interactive Plotly**.

## Property tables

Expand **Specimen properties · tables and Instron comparison** above the plot controls to see the tables and their update/export buttons. This section starts collapsed and can be folded away without clearing or recalculating its data. The tables work with **all plots switched off**. Changing selected sample groups updates the tables. **Update tables** refreshes the view without making plots; **Reload data** rereads files after source data or summaries change. **Export tables only** writes Excel tables without constructing any average curves or plots.

- **Summary:** one row per group, with properties as columns and adjacent **Calc / Instron** cells showing mean ± sample SD. Included n is shown beside the group; each cell shows its own valid n when different. These are statistics of individual included specimens, not properties measured from an average curve. Missing Instron values show “—”. The wide Excel summary keeps numeric means, SDs and counts in separate columns; `tensile_summary_details.xlsx` retains the long-form statistics including min/max.
- **Specimens:** **Include** checkboxes at the far left, then per-specimen 0.2% offset YS, UTS, uniform elongation, terminal failure elongation, tensile toughness, fitted elastic modulus, elastic-fit R² and calculation notes. Unchecked rows stay visible, dimmed, with an optional exclusion reason.
- **Instron:** select YS, UTS, elongation or modulus. Absolute and relative differences are calculated minus Instron. Elongation differences are percentage points. Comparison is not an automatic pass/fail assessment.
- **Checks:** raw CSV and summary provenance, specimen identity, fit range/intercept, Instron dimensions, flags and missing/conflicting values. Source-path cells show the end of each path within a compact column. Click a path (or focus it and press Enter) to reveal a selectable full path; click again to collapse. Excel exports retain complete paths and source hashes.

Filtering and sorting affect only the displayed tables, not graph selection or exported populations. Excel numeric values retain full precision and display three decimals. Missing/unresolved results remain blank, never zero. Summary SD is unavailable for n=1.

### Include/exclude specimens

The **Include** checkbox is saved **per graph**. It controls group statistics, Instron summary/difference statistics, both tensile averages, both work-hardening methods, representative-curve selection, and individual curves in static/Plotly plots and exports. Duplicating a graph copies its inclusion choices; a new graph starts without exclusions. An excluded representative override falls back to automatic selection among included specimens. A group with no included usable specimens is omitted from plots and retains zero counts in its summary.

Unchecked specimens remain in the per-specimen/diagnostic exports, with `Included`, `Specimen ID` and `Exclusion Reason` columns; they never contribute to averages. Searching/sorting is display-only and does not change these choices. With live preview off, changing Include clears the old plots and requires **Update plots**, so an old population cannot be mistaken for the new one. With live preview on, plots update automatically. Tables update independently of plot selection.

Exclusions use file paths relative to the data folder, not absolute machine paths or B-number names. They survive moving the entire data folder to another computer. Renaming/moving individual CSVs within it changes their identity; review selections after reorganising source files. Missing-file exclusions remain saved in case those files return. Unticking Include does not rename or modify any source file.

### Calculations

Per-specimen properties are calculated independently of landmark alignment. A specimen may have valid YS/UTS/elongation/toughness even when its post-UTS segment is insufficient for a landmark curve. Each property keeps its own availability/valid count.

The existing YS calculation is preserved: fit an elastic line to the pre-UTS points between 20% and 50% of specimen UTS (or the graph's saved fit-fraction override), shift by 0.2% strain, and interpolate the first eligible crossing before UTS. Fit quality and fitted modulus are reported for review. This fitted modulus is not the fixed/group-specific modulus used in work-hardening calculations. Landmark plots consume the same specimen-property calculation.

Uniform elongation is engineering strain at the first maximum engineering stress. Failure elongation is the terminal recorded engineering strain, not a post-fracture gauge-length measurement. Toughness is the engineering stress–strain integral of the recorded curve. Instron may use different elastic fitting, break detection, filtering or reported precision; differences must be interpreted with those settings in mind. No calculation is replaced by an Instron summary value.

### Instron summary CSVs

PDFs are not read. Place group summary CSVs in the corresponding `<chosen data folder>/<group>/` folder. Embedded summary tables in specimen CSVs are supported too. Summary rows are never treated as raw curve points.

Matching uses an embedded specimen summary, the Instron export dataset and row number, or an exact specimen label. Numeric similarity is never used to identify a specimen. Dataset summaries normally retain their original filename (`dataset.csv`, `dataset_1.csv` or `dataset_1_1.csv`) and raw exports remain inside `dataset.is_tens_Exports/`. Labels, row numbers, paths and match method are shown for checking. Unknown identities stay unmatched.

Conflicting values across summary revisions are left unavailable and flagged. An X-marked Instron row is identified but does not automatically exclude that specimen from this workbench. **Any `!` in a CSV filename or folder name inside the data tree is a hard ignore**, including nested folders and Instron summary CSVs. Such files are not loaded, shown in the selector, or exported, and Include cannot override that rule. Remove the marker and reload data if you want to manage that specimen through checkboxes instead.

## Per-graph colours

Expand **Labels and colours · this graph, all plot types**, select a group, tick **Override colour for this graph**, choose a colour and click **Apply group overrides**. Untick it and apply to restore the automatic colour. Overrides are saved with the graph and apply to all static and Plotly views and exported plots. Different graph definitions can use different colours for the same group.

## Advanced notebook mode

The normal Launch files open the web app. For the original JupyterLab editor, run `launch_workbench.py --notebook` with the workbench environment's Python, then use **Run > Run All Cells**. This remains optional; both interfaces share calculations and saved definitions. Avoid simultaneous editing sessions for the same project.

## History and the original installation

The original OneDrive installation was copied, not moved or edited. The `v18-baseline` Git tag preserves the imported software. No research plots or existing output tables are regenerated during installation or upgrade.
