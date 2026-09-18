# Tensile Workbench

## Open or update the workbench

1. Clone the repository, or close the app and stop its launcher before pulling an update into an existing checkout. Back up your personal graph-definition file before the one-time transition from tracked to ignored definitions (see README).
2. First-time users: run **Setup_Tensile_Workbench.bat** (Windows) or **Setup_Tensile_Workbench.command** (Mac). Then open **Launch_Tensile_Workbench.bat** or **Launch_Tensile_Workbench.command**. Existing users can launch directly; rerun Setup only when dependencies need installing/updating. See [setup instructions](SETUP.md).
3. The web app opens in your browser and starts automatically. No notebook or kernel commands are needed. Existing users upgrading from notebook-only mode should run Setup once to add Voilà.
4. On first run, choose data and output folders, defaulting to **./data** and **./output** relative to the workbench folder. Expand **Folders** at the top to change these later.

The current graph definitions live in ignored `tensile_workbench.project.json`; machine-specific folder choices live in ignored `.tensile-paths.json`. Generic defaults and three synthetic example groups are bundled, but no research data or generated outputs. Personal definitions are not uploaded: back them up or share them separately if desired. Existing environments can be reused. Use Git commits and tags for code history, not version suffixes on filenames.

Use **Show sample data** beside the sample-group selector. It adds **Ductile (sample)**, **Balanced (sample)** and **Strong (sample)** alongside your own groups, without changing either folder path. The toggle is remembered for this installation. Unticking it hides samples from the selector and excludes them from tables and plots; their saved graph selections and specimen exclusions remain intact and return when re-enabled. Fresh installations show samples by default and include a **Demo comparison** graph. Existing users can create a graph and tick the three sample groups. See [examples](examples/README.md) for provenance and scope.

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

Research exclusions use file paths relative to the data folder, not absolute machine paths or B-number names. Bundled samples use a separate `sample-data://` identity so they cannot collide with real specimens having the same names. Both survive moving their source folder to another computer. Renaming/moving individual CSVs within it changes their identity; review selections after reorganising source files. Missing-file exclusions remain saved in case those files return. Unticking Include does not rename or modify any source file.

### Calculations

Per-specimen properties are calculated independently of landmark alignment. A specimen may have valid YS/UTS/elongation/toughness even when its post-UTS segment is insufficient for a landmark curve. Each property keeps its own availability/valid count.

The existing YS calculation is preserved: fit an elastic line to the pre-UTS points between 20% and 50% of specimen UTS (or the graph's saved fit-fraction override), shift by 0.2% strain, and interpolate the first eligible crossing before UTS. Fit quality and fitted modulus are reported for review. This fitted modulus is not the fixed/group-specific modulus used in work-hardening calculations. Landmark plots consume the same specimen-property calculation.

Uniform elongation is engineering strain at the first maximum engineering stress. Failure elongation is the terminal recorded engineering strain, not a post-fracture gauge-length measurement. Toughness is the engineering stress–strain integral of the recorded curve. Instron may use different elastic fitting, break detection, filtering or reported precision; differences must be interpreted with those settings in mind. No calculation is replaced by an Instron summary value.

### Calculation inspector

Expand **Specimen properties**, open **Specimens**, and click a specimen name. The **Calculation inspector** tab shows the exact prepared curve and elastic-fit points used by the shared property calculation. You can also choose a specimen directly in that tab, or use **Previous / Next** to follow the current table's filtered/sorted order. Excluded specimens can be inspected without re-including them; hard-ignored files cannot.

**Yield detail** zooms to the elastic fit and 0.2% offset crossing. **Full curve** also shows the UTS/uniform-elongation point and terminal point used for failure EL. Drag to zoom; **Reset zoom** returns to the chosen view. The green points are the actual points used for fitting, not a representative average. The elastic and offset lines use the same specimen-specific modulus and intercept as the tables. An unresolved yield shows the available curve/fit and its reason instead of inventing a yield marker.

Calculated and available matched Instron properties are listed side by side. Instron YS is shown as a horizontal stress reference only: no Instron yield strain is inferred. Fit fractions, selected-point count, R², intercept, crossing bracket, source identity and preparation details are available below the chart. Failure EL remains the terminal recorded strain, not automatic fracture-onset detection. The inspector does not use WH filters or the WH modulus.

Changing the selected specimen or zoom does not change calculations. No specimen chart is generated until selected, and inspecting or adjusting a preview writes nothing to the output folder.

### Fit warnings and specimen overrides

The **R² warning threshold** box beside the fit warnings, above the collapsible **Specimen properties** section, is editable and saved for all graphs (default **0.98**). Enter a value and press Enter or leave the field to save. Fits below this threshold are flagged; it does not change the fit or specimen inclusion. The banner counts low-R², unresolved and stale-override fits in the selected groups, including excluded specimens. **Review fits** opens the inspector filtered to these specimens. Turn off **Only fits needing review** to return to the full table. A high R² alone does not establish that the selected region is elastic.

In the inspector, expand **Adjust elastic fit · preview before applying**:

- **Manual range:** enter start/end engineering strain (%) or click a purple range border, then drag its corner handles. Bounds snap to measured points; a least-squares line is fitted to all prepared points between them. At least five points are required, strictly before UTS.
- **Manual line:** enter strain/stress endpoint coordinates, or click the purple line and drag its endpoints. This sets slope and intercept directly. R² describes residual agreement with measured points between the endpoints, not a least-squares fit; it can be negative. A positive slope and a resolved 0.2% offset yield intersection are required.
- Inspect the resulting yield, modulus, R² and offset-line intersection against the measured curve and automatic baseline. Enter a reason, then select **Apply override · all graphs**. Until then, these are unsaved previews. **Cancel preview** discards edits; **Restore automatic fit** removes the saved override.

Overrides belong to specimens, not graphs. Tables show **Fit method** and **Override status**, with warning markers for fits needing review. Applying/restoring an override updates property tables and invalidates cached plots; select **Update plots** before exporting new figures. The shared yield calculation is used by summary/scatter plots and landmark curves, including landmark-derived work hardening. Measured UTS, elongation, toughness and the separately configured WH modulus are not changed by an elastic-fit override.

The ignored personal project JSON stores the specimen identity, raw-file fingerprint, bounds/endpoints, reason, timestamp, original automatic results and apply/restore history. Exported checks include the active definition and original automatic snapshot; export settings include relevant history. If a CSV's contents change, its override is flagged as stale and not applied: the automatic calculation is used until reviewed. Moving the data directory preserves relative identities; renaming a specimen does not silently transfer its override. Nothing edits the source CSVs.

### Instron summary CSVs

PDFs are not read. Place group summary CSVs in the corresponding `<chosen data folder>/<group>/` folder. Embedded summary tables in specimen CSVs are supported too. Summary rows are never treated as raw curve points.

Matching uses an embedded specimen summary, the Instron export dataset and row number, or an exact specimen label. Numeric similarity is never used to identify a specimen. Dataset summaries normally retain their original filename (`dataset.csv`, `dataset_1.csv` or `dataset_1_1.csv`) and raw exports remain inside `dataset.is_tens_Exports/`. Labels, row numbers, paths and match method are shown for checking. Unknown identities stay unmatched.

Conflicting values across summary revisions are left unavailable and flagged. An X-marked Instron row is identified but does not automatically exclude that specimen from this workbench. **Any `!` in a CSV filename or folder name inside the data tree is a hard ignore**, including nested folders and Instron summary CSVs. Such files are not loaded, shown in the selector, or exported, and Include cannot override that rule. Remove the marker and reload data if you want to manage that specimen through checkboxes instead.

## Gauge-length reconstruction

Expand **Gauge reconstruction · per sample group**. Each selected group has a
row with a **Target (mm)** field and **Reconstruct** checkbox. Enter a positive
target, then tick the checkbox to apply it. Changes save automatically; press
Enter or leave a target field to commit its value. Each group can have a different target
or remain measured within the same graph. These settings are saved with that
graph; each specimen still uses its own initial AVE dot spacing from **Strain 1
gauge length** in the matched Instron summary CSV, never a group-average spacing.
New groups default to off with an unset target (0). Existing graph-wide choices
are migrated to that graph's existing groups. Tables, the calculation log and
exports identify each group's active basis and target. Plot legends keep only
the configured group names and sample counts, without gauge-estimation suffixes.

To inspect before applying, save a target with reconstruction switched off.
Open a specimen's **Calculation inspector** and enable **Overlay measured /
reconstructed**. The measured curve is solid and the estimated curve dashed;
Full curve/Reset zoom includes both. The comparison shows measured and estimated
elongation/toughness, both lengths, the ratio, model warnings and the original
force-peak row/time. This toggle changes the display only, not the group's
calculation basis or any elastic-fit override.

At/before maximum force, engineering strain is unchanged. After maximum force,
the derived strain is `strain_at_peak + (AVE_spacing / target) *
(measured_strain - strain_at_peak)`. Stress is unchanged. Reconstruction is
performed per specimen before representative selection or averaging. Tensile
plots, failure-elongation statistics/scatter plots and integrated areas then
use the reconstructed curves. YS, UTS, modulus, uniform elongation and pre-peak
work-hardening plots remain measured and unchanged. Source CSVs are never edited.

Missing/conflicting gauge lengths or invalid endpoints require specimen review
before reconstructed plots can proceed. No specimen is automatically excluded
or silently replaced with its measured curve; inclusion checkboxes remain under
user control. Measured WH is unaffected. Tables retain measured and estimated values
separately; unavailable estimates are blank, never replaced with measured values.
Any finite positive target is permitted. A target longer than the measured dot
spacing applies the model as-is (a ratio below one reduces the post-peak
increment), with an explicit warning rather than exclusion. It assumes both
gauges capture the relevant localisation and cannot recover additional
post-peak extension outside the measured interval. Inspect gauge status,
ratio, original measurement row/time and strain at peak in Specimens. When no
force channel is supplied, maximum engineering stress is an explicitly recorded
proxy. The failure endpoint retains the existing maximum recorded retained
strain definition rather than claiming an independently detected fracture.
Peak strain is read from the original acquisition, even if the plotting cleanup
dropped that row. Local ordering changes after reconstruction are handled by
re-sorting intact strain/stress pairs for interpolation, without clipping strain
or inventing a replacement peak. Counts and notes remain in the specimen audit.

These are derived gauge-length estimates, not standards-compliant measured
elongations. They assign the measured post-peak extension to a neck-centred
target gauge, without resolving continued deformation or unloading elsewhere.
Derived toughness is the area of that reconstructed engineering
curve, not a newly measured gauge-independent property. Instron agreement checks
continue to compare measured calculations with measured Instron results.

### Publication plot annotations

Static figures, PNG exports and Plotly views omit explanatory footers and gauge
reconstruction notices. Landmark tensile plots retain only **○ Mean YS △ Mean
UTS × Mean failure elongation**; comparison plots show this key only when all
three marker types are displayed. Normal titles, axis labels, group legends and
sample counts are retained. Method descriptions, error-bar meanings and gauge
warnings remain in the calculation log, inspector and/or export metadata for
use in publication captions and methods sections.

## Consolidated Excel exports

**Export tables only** writes `{graph_name}_results.xlsx`: Summary, Specimens,
Checks, Instron comparison and Export info. Properties are available without
selecting any plot. Measured and estimated elongation/toughness remain separate,
and inclusion, source and override information is retained.

**Export plot set**, with Excel tables enabled, additionally writes
`{graph_name}_curves.xlsx` when curve plots are present. Only the exported plot
methods are included. Each group/specimen has adjacent strain/stress (or plastic
strain/WH-rate) columns with its own coordinates; shorter curves end in blanks.
Pointwise projected stress is separate from measured mean stress. With/without
individuals views share one copy of each average. Comparison plots include both
methods; scatter plots reuse the results workbook. Curve checks retain coverage,
area comparisons and landmark error-bar values. Different numerical curve
variants are distinguished, with their view settings in Export info.

Numeric cells retain full precision and display three decimals. Counts are
integers. Historical exports are not rewritten. Restart the running app to load
code changes before creating a new export.

## Strength versus elongation plots

Select **0.2% YS vs elongation** and/or **UTS vs elongation** under Plot views for any graph definition. Both use elongation at failure on the x-axis and strength in MPa on the y-axis. EL is the terminal recorded engineering strain used in the Specimens table, not uniform elongation or a post-fracture gauge-length measurement.

Diamonds show group means of calculated per-specimen properties. **Show individual specimens** adds faint circles for the individual specimens; the paired with/without-individuals option works too. Optional horizontal and vertical **±1 sample SD** bars show scatter in EL and strength, not confidence intervals. A single specimen has a mean point but no SD bars. Groups are not joined by lines or fitted to a trend.

Each point requires both properties to be available. If a yield fit is unresolved, that specimen is omitted from the YS–EL plot and its mean/SD, with a warning in the calculation log; it can still appear in UTS–EL. The legend's n is the number of valid paired specimens. These views use the same specimen-property calculations and Include selections as the tables, independently of landmark fitting, WH filters and the WH elastic modulus. They show **Calc**, not Instron summary values. Where a metric is unavailable, paired plot means may differ from table means that count each property separately.

Each view has its own title and independent x/y limits under Settings. The with/without-individuals versions of a given scatter plot always share automatic limits based on all included paired specimen values and any displayed SD bars; manual limits override these for both versions. Colours and group legend labels follow the graph's overrides. Static and Plotly views show the same values. Individual hover labels use compact group/specimen names (for example `Alloy A · specimen 3`), not long folder paths; full source identity remains in the tables. Exports are numbered `08_ys_vs_el` and `09_uts_vs_el`, with adjacent `with_individuals` / `without_individuals` filenames. Existing saved graphs gain these options without changing their current selected plots.

## Per-graph colours

Expand **Labels and colours · this graph, all plot types**, select a group, tick **Override colour for this graph**, choose a colour and click **Apply group overrides**. Untick it and apply to restore the automatic colour. Overrides are saved with the graph and apply to all static and Plotly views and exported plots. Different graph definitions can use different colours for the same group.

## Advanced notebook mode

The normal web app uses the **Tensile Workbench** browser-tab title and its own
tensile-curve favicon, served locally from the bundled `web/` assets. Restart
the launcher after an update; refresh the browser tab if it retains an old icon.

The normal Launch files open the web app. For the original JupyterLab editor, run `launch_workbench.py --notebook` with the workbench environment's Python, then use **Run > Run All Cells**. This remains optional; both interfaces share calculations and saved definitions. Avoid simultaneous editing sessions for the same project.

## History and the original installation

The original OneDrive installation was copied, not moved or edited. The `v18-baseline` Git tag preserves the imported software. No research plots or existing output tables are regenerated during installation or upgrade.
