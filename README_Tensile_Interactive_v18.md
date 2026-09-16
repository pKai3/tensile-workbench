# Tensile Workbench v18

## Upgrade an existing working installation

1. Save and close the v17 notebook and stop its launcher.
2. Extract the v18 share patch **into the existing workbench folder**, alongside `data/` and the v17 saved project. This is a patch, not a full data package.
3. Windows: double-click **Launch_Tensile_Interactive_v18.bat**. Mac: double-click **Launch_Tensile_Interactive_v18.command**.
4. In the v18 notebook choose **Run > Run All Cells**.

The first launch copies your latest v17 graph definitions into a separate v18 project. Existing v18 definitions are never overwritten. No reinstall or new environment is needed. Keep the existing Windows `requirements-windows.txt`, setup files and local environment. The patch contains no raw data and does not replace anyone's existing data or exports.

## Property tables

The tables appear above the plot controls and work with **all plots switched off**. Changing selected sample groups updates the tables. **Update tables** refreshes the view without making plots; **Reload data** rereads files after source data or summaries change. **Export tables only** writes Excel tables without constructing any average curves or plots.

- **Summary:** mean, sample standard deviation, valid n, minimum and maximum for each property. These are statistics of individual specimens, not properties measured from the average curve. Instron statistics use the same selected specimens where summary values are available; valid counts can differ.
- **Specimens:** 0.2% offset YS, UTS, uniform elongation, terminal failure elongation, tensile toughness, fitted elastic modulus, elastic-fit R² and calculation notes.
- **Instron:** select YS, UTS, elongation or modulus. Absolute and relative differences are calculated minus Instron. Elongation differences are percentage points. Comparison is not an automatic pass/fail assessment.
- **Checks:** raw CSV and summary provenance, specimen identity, fit range/intercept, Instron dimensions, flags and missing/conflicting values. Source hashes are included in Excel exports.

Filtering and sorting affect only the displayed tables, not graph selection or exported populations. Excel numeric values retain full precision and display three decimals. Missing/unresolved results remain blank, never zero. Summary SD is unavailable for n=1.

### Calculations

Per-specimen properties are calculated independently of landmark alignment. A specimen may have valid YS/UTS/elongation/toughness even when its post-UTS segment is insufficient for a landmark curve. Each property keeps its own availability/valid count.

The existing YS calculation is preserved: fit an elastic line to the pre-UTS points between 20% and 50% of specimen UTS (or the graph's saved fit-fraction override), shift by 0.2% strain, and interpolate the first eligible crossing before UTS. Fit quality and fitted modulus are reported for review. This fitted modulus is not the fixed/group-specific modulus used in work-hardening calculations. Landmark plots consume the same specimen-property calculation.

Uniform elongation is engineering strain at the first maximum engineering stress. Failure elongation is the terminal recorded engineering strain, not a post-fracture gauge-length measurement. Toughness is the engineering stress–strain integral of the recorded curve. Instron may use different elastic fitting, break detection, filtering or reported precision; differences must be interpreted with those settings in mind. No calculation is replaced by an Instron summary value.

### Instron summary CSVs

PDFs are not read. Place group summary CSVs in the corresponding `data/<group>/` folder. Embedded summary tables in specimen CSVs are supported too. Summary rows are never treated as raw curve points.

Matching uses an embedded specimen summary, the Instron export dataset and row number, or an exact specimen label. Numeric similarity is never used to identify a specimen. Dataset summaries normally retain their original filename (`dataset.csv`, `dataset_1.csv` or `dataset_1_1.csv`) and raw exports remain inside `dataset.is_tens_Exports/`. Labels, row numbers, paths and match method are shown for checking. Unknown identities stay unmatched.

Conflicting values across summary revisions are left unavailable and flagged. An X-marked Instron row is identified but does not automatically exclude that specimen from this workbench. Automatic discovery continues to skip sample groups/files whose names start with `!`.

## Per-graph colours

Expand **Labels and colours · this graph, all plot types**, select a group, tick **Override colour for this graph**, choose a colour and click **Apply group overrides**. Untick it and apply to restore the automatic colour. Overrides are saved with the graph and apply to all static and Plotly views and exported plots. Different graph definitions can use different colours for the same group.

## Version separation

v18 uses `tensile_workbench_v18.project.json`. v17 remains recoverable from the local archive after cleanup. No research plots or existing output tables are regenerated during installation or upgrade.
