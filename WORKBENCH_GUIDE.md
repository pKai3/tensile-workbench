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

Expand **Specimen properties · tables and calculation inspector** above the plot controls to see the tables and their update/export buttons. This section starts collapsed and can be folded away without clearing or recalculating its data. The tables work with **all plots switched off**. Changing selected sample groups updates the tables. **Update tables** refreshes the view without making plots; **Reload data** rereads files after source data or summaries change. **Export tables only** writes Excel tables without constructing any average curves or plots.

- **Summary:** one row per group, with properties as columns and adjacent **Calc / Instron** cells showing mean ± sample SD. **Uniform Elongation** and **Tensile Toughness** retain both columns; missing/unsupported Instron imports remain placeholders. The parser supports uniform elongation from Strain 1 at maximum force; Instron toughness import is not yet implemented. Elongation has **Instron / Calc / Reconstruct**: the reported break result, calculated CSV drop onset, and its gauge reconstruction. Reconstruct is blank unless enabled for that group and available. Last valid CSV strain is not a main-table column. Included n is shown beside the group; each cell shows its own valid n when different. These are statistics of individual included specimens, not properties measured from an average curve. Missing values show “—”. Excel keeps means, SDs and counts in separate numeric columns, with the same property order and basis.
- **Specimens:** **Include** checkboxes at the far left and an **Applies to** selector, followed by the same properties and source-specific EL columns as Summary. Calc elongation always shows the unreconstructed detected endpoint; Reconstruct shows its correction separately. Calc toughness uses the group's selected measured/reconstructed basis. Instron remains the original reported value where provided. Peak-force row numbers, timestamps, final-reading bookkeeping and plotting-grid diagnostics remain in the inspector/audit data. Useful fit, geometry and **EL source for plots** fields remain at the right. Operator **Specimen text input** is displayed when available; the underlying CSV identity remains in the tooltip and export. A single **Checks** column contains only failures/review items, one per line; it is blank when nothing is flagged. Unchecked rows stay visible, dimmed, with an optional exclusion reason.
- **Calculation inspector:** click a specimen name to see its measured values, original Instron values and exact differences, plus fit and gauge details. **Original CSV ↔ Instron verification values** gives the values and tolerances used for matching checks. **Source and preparation details** contains full source paths and acquisition provenance. Separate Instron and Checks tabs are no longer needed; detailed diagnostic records remain available on the exported **Audit** sheet.

Filtering and sorting affect only the displayed tables, not graph selection or exported populations. Tables, inspector readouts, plot tooltips and Excel quantities display two decimals; calculations, comparisons and Excel cell values retain full precision. Counts and row identifiers remain integers. Editable settings retain their entered precision. Missing/unresolved results remain blank, never zero. Summary SD is unavailable for n=1.

### Include/exclude specimens

The **Include** checkbox is **global by default**, saved in the personal project file. Excluding a bad specimen applies to existing and future graphs, including statistics, Instron comparisons, both tensile averages, both work-hardening methods, representative selection and individual plots/exports.

For an exception, first change **Applies to** to **This graph only**, then set Include. This explicitly overrides the global setting for this specimen in this graph. Choosing **Global default** again removes the exception and restores the current global choice; it does not copy the local choice into the global setting. Changes to the global default leave other graphs' explicit exceptions untouched. The row shows whether the global default is included or excluded while an override is active.

On first opening this update, existing exclusions from active graphs are promoted to global exclusions, retaining their reasons. Deleted graphs' historical exclusions are kept as local overrides if those graphs are restored. A new graph inherits the global choices; duplicating a graph also copies its explicit exceptions. The previous project save remains in the normal backup. An excluded representative override falls back to an included specimen; a group with no included usable specimens has zero summary counts and is omitted from plots.

Unchecked specimens remain in per-specimen/diagnostic exports, with effective inclusion, inclusion scope, global default, specimen identity and reason; they never contribute to averages. Searching/sorting is display-only. With live preview off, changing Include clears the old plots and requires **Update plots**. With live preview on, plots update automatically. Tables update independently of plot selection. All selection settings are private/ignored, not shared deployment defaults.

Research exclusions use file paths relative to the data folder, not absolute machine paths or B-number names. Bundled samples use a separate `sample-data://` identity so they cannot collide with real specimens having the same names. Both survive moving their source folder to another computer. Renaming/moving individual CSVs within it changes their identity; review selections after reorganising source files. Missing-file exclusions remain saved in case those files return. Unticking Include does not rename or modify any source file.

### Calculations

Per-specimen properties are calculated independently of landmark alignment. A specimen may have valid YS/UTS/elongation/toughness even when its post-UTS segment is insufficient for a landmark curve. Each property keeps its own availability/valid count.

The existing YS calculation is preserved: fit an elastic line to the pre-UTS points between 20% and 50% of specimen UTS (or the graph's saved fit-fraction override), shift by 0.2% strain, and interpolate the first eligible crossing before UTS. Fit quality and fitted modulus are reported for review. This fitted modulus is not the fixed/group-specific modulus used in work-hardening calculations. Landmark plots consume the same specimen-property calculation.

Uniform elongation is engineering strain at the first maximum engineering stress. Analysis EL is **CSV-derived fracture EL**, the detected onset of the terminal stress drop. Toughness is the engineering stress–strain integral through that endpoint, including an interpolated endpoint where necessary. With gauge reconstruction enabled, EL and toughness use the reconstructed curve through the corresponding transformed endpoint. No calculation is replaced by an Instron summary value.

EL provenance is explicit:

- **Instron:** the imported Strain 1 at break result.
- **Calc:** CSV-derived fracture EL at detected terminal-drop onset, before any landmark shape setback.
- **Reconstruct:** the gauge model applied to that same detected endpoint, only when enabled and available.
- **Last valid CSV strain:** the final finite strain reading in original acquisition order. Retained only in the inspector and Audit, along with its row/time.
- **Max retained CSV strain:** preserved in the inspector and Audit only. It is not a substitute for fracture EL.

Detection reuses the existing landmark heuristic at slope fraction 0.10 on the full measured, prepared curve. It selects the first sufficiently steep decline that passes its subsequent stress-loss check, using a uniform strain grid and the existing post-UTS baseline/noise thresholds. It does not verify that this is the final fracture collapse, so it can misidentify earlier necking. The grid interval's start is the reported onset. Audit records the method, sensitivity, grid spacing, slope threshold, bracketing original rows, interpolation fraction and interpolated time where available. This remains a heuristic estimate for review, not Instron's break result or a standards-compliant post-fracture measurement. It is computed before reconstruction and is not re-detected on transformed curves.

In the landmark calculation, the pre-break **shape** endpoint is normally detected onset minus 0.05 percentage points; its post-UTS shape is mapped to the detected onset landmark. The setback does not reduce reported EL. **Not detected** is explicit: fracture EL/toughness and reconstruction are unavailable rather than replaced by terminal strain. Tensile plots require review of unresolved included specimens, without automatically excluding them. YS, UTS, uniform elongation and both WH methods remain available when their own pre-peak requirements are satisfied. Landmark WH now builds only the start-to-yield and yield-to-UTS stages, so it needs no fracture endpoint.

### Calculation inspector

Expand **Specimen properties**, open **Specimens**, and click a specimen name. The **Calculation inspector** tab shows the exact prepared curve and elastic-fit points used by the shared property calculation. You can also choose a specimen directly in that tab, or use **Previous / Next** to follow the current table's filtered/sorted order. Excluded specimens can be inspected without re-including them; hard-ignored files cannot.

**Yield detail** zooms to the elastic fit and 0.2% offset crossing. **Full curve** shows the entire prepared measurement, UTS/uniform elongation and a purple cross at detected fracture onset. Missing detection is stated explicitly. The reconstruction overlay ends at the transformed detected endpoint. Drag to zoom; **Reset zoom** returns to the chosen view. The green points are the actual points used for fitting, not a representative average. The elastic and offset lines use the same specimen-specific modulus and intercept as the tables. An unresolved yield shows the available curve/fit and its reason instead of inventing a yield marker.

**Show on plot** is a grouped checkbox legend below the chart, outside the axis-label area: **Curves**, **Yield & fit**, **Peak**, **Fracture** and **Diagnostics**. Fit lines/points default to visible in Yield detail and hidden in Full curve. Maximum retained strain, the fracture vertical guide and the Instron YS reference line are optional diagnostic layers. **Reset shown items** restores the current view's defaults. Visibility choices are remembered separately for each view during the session and never change calculations. Manual-fit edit handles remain visible while editing.

Calculated and available matched Instron properties are listed side by side. EL has a separate **Elongation sources** table rather than a calculated-minus-Instron comparison of different endpoint definitions. **Instron EL** is a magenta hollow diamond: its strain is imported from the summary and its stress is interpolated from the measured CSV curve, not an Instron fracture-stress result. No marker is extrapolated when reported strain lies outside the prepared CSV range. UTS and maximum force share one marker when their coordinates agree; otherwise the original maximum-force point is a separate red open triangle under Diagnostics. It marks the reconstruction breakpoint, not fracture. Compare the Instron diamond against the purple Calc EL marker: the detector can select an earlier decline instead of the final collapse. This is distinct from the landmark shape setback. **Instron YS** has a magenta hollow diamond at the first ascending pre-UTS CSV crossing of the reported stress. Its strain is CSV-interpolated, not an Instron yield-strain result. Its horizontal stress reference is available under Diagnostics and shown by default if no crossing is available. Fit fractions, selected-point count, R², intercept, crossing bracket, source identity and preparation details are available below the chart. The inspector does not use WH filters or the WH modulus.

**EL source for plots** uses **Calc** or **Reconstruct** in the specimen table and Excel export. Detailed endpoint provenance remains in the audit data.

Changing the selected specimen or zoom does not change calculations. No specimen chart is generated until selected, and inspecting or adjusting a preview writes nothing to the output folder.

### Fit warnings and specimen overrides

The **R² warning threshold** box beside the fit warnings, above the collapsible **Specimen properties** section, is editable and saved for all graphs (default **0.98**). Enter a value and press Enter or leave the field to save. Fits below this threshold are flagged; it does not change the fit or specimen inclusion. The banner counts low-R², unresolved and stale-override fits in the selected groups, including excluded specimens. **Review fits** opens the inspector filtered to these specimens. Turn off **Only fits needing review** to return to the full table. A high R² alone does not establish that the selected region is elastic.

In the inspector, expand **Adjust elastic fit · preview before applying**:

- **Manual range:** enter start/end engineering strain (%) or click a purple range border, then drag its corner handles. Bounds snap to measured points; a least-squares line is fitted to all prepared points between them. At least five points are required, strictly before UTS.
- **Manual line:** enter strain/stress endpoint coordinates, or click the purple line and drag its endpoints. This sets slope and intercept directly. R² describes residual agreement with measured points between the endpoints, not a least-squares fit; it can be negative. A positive slope and a resolved 0.2% offset yield intersection are required.
- Inspect the resulting yield, modulus, R² and offset-line intersection against the measured curve and automatic baseline. Enter a reason, then select **Apply override · all graphs**. Until then, these are unsaved previews. **Cancel preview** discards edits; **Restore automatic fit** removes the saved override.

Overrides belong to specimens, not graphs. Tables show **Fit method**; stale overrides and low-R²/unresolved fits appear in the single **Checks** column. The inspector/export retain full override status and provenance. Applying/restoring an override updates tables and invalidates cached plots; select **Update plots** before exporting. The shared yield calculation is used by summary/scatter plots and landmark curves, including landmark-derived work hardening. Measured UTS, elongation, toughness and the separately configured WH modulus are not changed by an elastic-fit override.

The ignored personal project JSON stores the specimen identity, raw-file fingerprint, bounds/endpoints, reason, timestamp, original automatic results and apply/restore history. Exported checks include the active definition and original automatic snapshot; export settings include relevant history. If a CSV's contents change, its override is flagged as stale and not applied: the automatic calculation is used until reviewed. Moving the data directory preserves relative identities; renaming a specimen does not silently transfer its override. Nothing edits the source CSVs.

### Instron summary CSVs

PDFs are not read. Place group summary CSVs in the corresponding `<chosen data folder>/<group>/` folder. Embedded summary tables in specimen CSVs are supported too. Summary rows are never treated as raw curve points.

Candidate matching uses an embedded specimen summary, the Instron export dataset and row number, or an exact specimen label. It then independently verifies the name/row association and original recorded data. Numeric similarity never selects or reassigns a specimen. Dataset summaries normally retain their original filename (`dataset.csv`, `dataset_1.csv` or `dataset_1_1.csv`) and raw exports remain inside `dataset.is_tens_Exports/`. Unknown identities are flagged even if data values happen to agree.

**“Dataset + Instron row number”** uses the dataset name from the immediate export
folder (`<dataset>.is_tens_Exports` or `<dataset>.id_tens_Exports`) and the specimen
number from `<dataset>_<number>.csv` or `<dataset>_<number>_1.csv`. It searches the
same sample-group folder for summaries named after that dataset, optionally with
one or two numeric suffixes, and selects the row whose first column contains
that specimen number. This is the printed Instron specimen ID, not a physical
CSV/Excel line number, the specimen’s text label or a raw time-series row.
For example, `B11.is_tens_Exports/B11_3.csv` matches specimen `3` in a summary
such as `B11.csv`, `B11_1.csv` or `B11_1_1.csv`. Preserve these export names and
the immediate export folder if relying on this matching method.

An embedded summary in the raw CSV takes priority: a single summary row is used
directly, or a multi-row summary is selected using the export specimen number.
Without an embedded summary, if dataset/number matching finds no candidates,
the fallback is an exact, case-insensitive match between the raw filename stem
and the summary’s **Specimen text input**. It does not use fuzzy names, list
order, test-property similarity or PDFs. Multiple candidate summaries are
compared field by field; conflicting fields remain blank rather than choosing
the newest file or the closest result. Renamed or mixed datasets can break this
name-based identity convention; numerical agreement does not prove identity.

**Verification** compares the summary UTS with the maximum finite engineering stress in the untouched CSV acquisition, including rows removed from the plotting grid. No elastic fit, smoothing, average curve or gauge reconstruction is used. **EL is not used for matching or numerical identity verification.** Instron's strain-at-break and a CSV endpoint need not be the same quantity; an EL difference does not trigger a matching failure.

UTS allows half the least significant printed digit from each CSV, after unit conversion, plus `1e-9 × max(1, |raw|, |summary|)` for floating-point arithmetic. Trailing zeros and scientific notation are preserved when reading precision. Missing/conflicting source values, unverified/ambiguous names, conflicting labels, UTS mismatches and Instron X flags remain in the single **Checks** column. No pass messages or separate pass/fail columns are shown. Exact UTS comparison values and tolerance are available under **Original CSV ↔ Instron verification values** in the inspector and in Audit. The former EL tolerance is no longer used.

Flagging does not automatically exclude a specimen, replace its data, select a different summary or suppress available candidate values. Review flagged rows before relying on their Instron comparisons or dimensions; use the inclusion controls if you decide to exclude them. Calculated YS differences are not used to establish identity.

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
reconstructed**. The measured curve is solid and the reconstructed curve dashed;
Full curve/Reset zoom includes both. The comparison shows measured and reconstructed
elongation/toughness, both lengths, the ratio and model warnings. The original
force-peak row/time is retained under the collapsed **Source and preparation details**.
This toggle changes the display only, not the group's
calculation basis or any elastic-fit override.

Immediately below the derived-model notice, **Gauge reconstruction:
formula and assumptions** is open by default. It contains the pre-/post-peak equations,
variable definitions, a worked example and the localisation, endpoint and toughness
limitations. The same help is available beside the group reconstruction controls.
It is not printed on plots. With all strains expressed in percent,
`ΔL_post = L_dots × (EL_measured − EL_at_peak) / 100` in mm, and
`EL_estimated = EL_at_peak + (L_dots / L_target) × (EL_measured − EL_at_peak)`.

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
proxy. The failure endpoint is detected CSV drop onset, not the final recorded
strain or the deliberately earlier landmark shape-trimming point.
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

**Export tables only** writes `{graph_name}_results.xlsx` with **Summary**, **Specimens**,
**Audit** and **Export info** sheets. Properties are available without selecting any plot.
The first two sheets use the same property definitions, ordering and analysis basis as
the on-screen tables. Summary mean, SD and n remain separate numeric columns; grouped
screen headers are flattened into unique Excel headers for filtering and plotting.
Specimens uses the same operator labels and inclusion scope, with a stable Specimen ID
at the end to join audit records. The four source-specific EL columns match the UI;
Reconstructed EL cells stay blank for disabled groups or unavailable results.
Source paths/hashes, original CSV–Instron differences, fit overrides, dimensions and gauge
endpoint metadata are retained on Audit rather than mixed into the main property sheets.
The old duplicate Instron comparison sheet is no longer exported. Export info records
the endpoint-source definitions, UTS-only identity check and reconstruction assumptions.

**Export plot set**, with Excel tables enabled, additionally writes
`{graph_name}_curves.xlsx` when curve plots are present. Only the exported plot
methods are included. Each group/specimen has adjacent strain/stress (or plastic
strain/WH-rate) columns with its own coordinates; shorter curves end in blanks.
Pointwise projected stress is separate from measured mean stress. With/without
individuals views share one copy of each average. Comparison plots include both
methods; scatter plots reuse the results workbook. Curve checks retain coverage,
area comparisons and landmark error-bar values. Different numerical curve
variants are distinguished, with their view settings in Export info.

Numeric cells retain full precision and display two decimals. Counts are
integers. Historical exports are not rewritten. Restart the running app to load
code changes before creating a new export.

## Strength versus elongation plots

Select **0.2% YS vs elongation** and/or **UTS vs elongation** under Plot views for any graph definition. Both use the current analysis EL on the x-axis and strength in MPa on the y-axis. EL is CSV-derived fracture EL at detected drop onset, or its gauge reconstruction when enabled—not Instron's break result, uniform elongation or a post-fracture gauge-length measurement.

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
