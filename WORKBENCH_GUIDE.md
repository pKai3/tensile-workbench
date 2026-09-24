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

**Live preview (may be very slow)** defaults to off for fresh installations and newly created graphs. Click **Update plots** when ready. Existing graphs retain their saved preference, and duplicating a graph copies it. Enable live preview only if automatic recalculation is responsive enough on your computer.

Individual hover labels across tensile, representative, scatter and both WH plots use the matched **operator specimen name**, as in the specimen table. Without that label they use the actual CSV stem, never an arbitrary curve number. WH labels stay attached to the original specimen even if another specimen has no valid WH curve. Source IDs and filenames are unchanged; publication legends remain group-only. The inspector selector also uses specimen names.

## Property tables

Expand **Specimen properties · tables and calculation inspector** above the plot controls to see the tables and their update/export buttons. This section starts collapsed and can be folded away without clearing or recalculating its data. The tables work with **all plots switched off**. Changing selected sample groups updates the tables. **Update tables** refreshes the view without making plots; **Reload data** rereads files after source data or summaries change. **Export tables only** writes Excel tables without constructing any average curves or plots.

**Reload data** is available at the top of the specimen-properties section as well as beside **Update plots**. The tables button rereads source CSVs and summary files, refreshes the tables and clears stale plots without rebuilding them. The plot-area button also updates selected plots. Neither requires a page refresh. Source-code updates still require restarting the app. Reloading discards unsaved inspector previews; applied overrides remain saved (and are checked against the source fingerprint).

- **Summary:** one row per group, with properties as columns and adjacent **Calc / Instron** cells showing mean ± sample SD. **Uniform Elongation** and **Tensile Toughness** retain both columns; missing/unsupported Instron imports remain placeholders. The parser supports uniform elongation from Strain 1 at maximum force; Instron toughness import is not yet implemented. Elongation has **Instron / Calc / Reconstruct**: the reported break result, selected CSV endpoint, and its gauge reconstruction. Reconstruct is blank unless enabled for that group and available. Last valid CSV strain is not a main-table column. Included n is shown beside the group; each cell shows its own valid n when different. These are statistics of individual included specimens, not properties measured from an average curve. Missing values show “—”. Excel keeps means, SDs and counts in separate numeric columns, with the same property order and basis.
- **Specimens:** **Include** checkboxes at the far left and an **Applies to** selector, followed by the same properties and source-specific EL columns as Summary. Calc elongation always shows the unreconstructed detected endpoint; Reconstruct shows its correction separately. Calc toughness uses the group's selected measured/reconstructed basis. Instron remains the original reported value where provided. Peak-force row numbers, timestamps, final-reading bookkeeping and plotting-grid diagnostics remain in the inspector/audit data. Useful fit, geometry and **EL source for plots** fields remain at the right. Operator **Specimen text input** is displayed when available; the underlying CSV identity remains in the tooltip and export. A single **Checks** column contains only failures/review items, one per line; it is blank when nothing is flagged. Unchecked rows stay visible, dimmed, with an optional exclusion reason.
- **Calculation inspector:** click a specimen name to see its measured values, original Instron values and exact differences, plus fit and gauge details. **Original CSV ↔ Instron verification values** gives the values and tolerances used for matching checks. **Source and preparation details** contains full source paths and acquisition provenance. Separate Instron and Checks tabs are no longer needed; detailed diagnostic records remain available on the exported **Audit** sheet.

Filtering and sorting affect only the displayed tables, not graph selection or exported populations. Ordinary results display two decimals. Elastic-fit R², its warning threshold and fit/yield strain details display five decimals in tables, inspector readouts and Excel; yield-detail strain tooltips also use five decimals. Calculations, comparisons and Excel cell values retain full precision. Counts and row identifiers remain integers. Editable settings retain their entered precision. Missing/unresolved results remain blank, never zero. Summary SD is unavailable for n=1.

### Summary comparison and inspector layout

On **Summary**, expand **Calc–Instron comparison · percentage differences** below the table. For every included specimen with both values, it calculates `100 × (Calc − Instron) / Instron`. The bars show each group's mean paired percentage difference, with ±1 sample SD error bars. Compact panels run **three across** on wide screens, two or one on narrower screens. Each property has its own independent percentage-axis scale, so large discrepancies in one property do not hide small differences in another. **UTS is not plotted here:** differences beyond exported-value rounding tolerance remain flagged in specimen Checks. Zero means agreement; positive means Calc is higher. These are means of specimen-level differences, not ratios of group means, and SD shows specimen scatter rather than a confidence interval. Hover for paired n, original-unit means and the number of specimens carrying review checks. A single pair has no SD bar. Properties without usable comparisons are omitted, as are nonfinite values and zero Instron denominators.

The **Spread · SD** table directly below each panel shows Instron SD, Calc SD, paired n and `100 × (SD Calc / SD Instron − 1)` for each group. Both sample SDs use exactly the same paired specimens as that property's chart, in the original property units. Negative change means less scatter in Calc, not necessarily greater accuracy. This compares the spread of the two sets of values, distinct from the chart's SD of paired differences. For n<2 both SDs are unavailable; with zero Instron SD the percentage change is unavailable, not zero. Unavailable entries display a dash. Values smaller than the two-decimal display precision show `<0.01` instead of a misleading zero; hover reveals additional precision. These statistics are also included in the existing **Calc-Instron agreement** worksheet, where UTS is retained for audit only.

This comparison uses **measured** calculations even when gauge reconstruction is enabled. Failure EL compares the selected measured CSV endpoint with the imported Instron break result; their definitions can differ. Existing identity and calculation checks still require review—numerical discrepancies are not automatically discarded. The chart reuses existing tables and renders only when expanded; it does not generate publication plots or rerun tensile calculations. Summary group filtering affects the displayed chart, not the export population. The same numbers are available in the **Calc-Instron agreement** worksheet of the normal results workbook when paired data exist.

In the **Calculation inspector**, the selected specimen's check messages appear above the graph. They refresh during unsaved override previews and are hidden when nothing is flagged. **Adjust elastic fit** and **Adjust failure elongation** sit directly below these warnings and above the graph, each independently collapsible and outside the larger details fold. **Show on plot** stays directly below the graph as its visible checkbox legend; it is not inside a collapsible section. Expand **Inspector controls and calculation details** below the legend to access property comparisons, endpoint details, the gauge model, source information and method explanation. The specimen selector and view buttons also stay outside this fold.

### Include/exclude specimens

The explanatory text above **Specimens**, including inclusion rules, source labels
and the current EL basis by group, is under the initially collapsed **About the
specimen table · inclusion, checks and data sources** section. Filters, Include
controls and the specimen-specific Checks column remain visible outside it.

The **Include** checkbox is **global by default**, saved in the personal project file. Excluding a bad specimen applies to existing and future graphs, including statistics, Instron comparisons, both tensile averages, both work-hardening methods, representative selection and individual plots/exports.

For an exception, first change **Applies to** to **This graph only**, then set Include. This explicitly overrides the global setting for this specimen in this graph. Choosing **Global default** again removes the exception and restores the current global choice; it does not copy the local choice into the global setting. Changes to the global default leave other graphs' explicit exceptions untouched. The row shows whether the global default is included or excluded while an override is active.

On first opening this update, existing exclusions from active graphs are promoted to global exclusions, retaining their reasons. Deleted graphs' historical exclusions are kept as local overrides if those graphs are restored. A new graph inherits the global choices; duplicating a graph also copies its explicit exceptions. The previous project save remains in the normal backup. An excluded representative override falls back to an included specimen; a group with no included usable specimens has zero summary counts and is omitted from plots.

Unchecked specimens remain in per-specimen/diagnostic exports, with effective inclusion, inclusion scope, global default, specimen identity and reason; they never contribute to averages. Searching/sorting is display-only. With live preview off, changing Include clears the old plots and requires **Update plots**. With live preview on, plots update automatically. Tables update independently of plot selection. All selection settings are private/ignored, not shared deployment defaults.

Research exclusions use file paths relative to the data folder, not absolute machine paths or B-number names. Bundled samples use a separate `sample-data://` identity so they cannot collide with real specimens having the same names. Both survive moving their source folder to another computer. Renaming/moving individual CSVs within it changes their identity; review selections after reorganising source files. Missing-file exclusions remain saved in case those files return. Unticking Include does not rename or modify any source file.

### Calculations

Per-specimen properties are calculated independently of landmark alignment. A specimen may have valid YS/UTS/elongation/toughness even when its post-UTS segment is insufficient for a landmark curve. Each property keeps its own availability/valid count.

The existing YS calculation is preserved: fit an elastic line to the pre-UTS points between 20% and 50% of specimen UTS (or the graph's saved fit-fraction override), shift by 0.2% strain, and interpolate the first eligible crossing before UTS. Fit quality and fitted modulus are reported for review. This fitted modulus is not the fixed/group-specific modulus used in work-hardening calculations. Landmark plots consume the same specimen-property calculation.

Uniform elongation is engineering strain at the first maximum engineering stress. Analysis EL uses a selected original CSV measurement: before a supported sudden load drop, otherwise immediately before load falls below 10% of peak, or a valid manual endpoint. When an export stops before the confirmation thresholds, a supported sudden-drop or terminal-unloading estimate remains usable and review-flagged. Toughness and gauge reconstruction use the same selected measurement. No calculation is replaced by an Instron summary value.

EL provenance is explicit:

- **Instron:** the imported Strain 1 at break result.
- **Calc:** strain at the selected CSV endpoint, before any landmark shape setback. Audit identifies the sudden-drop criterion, 10% crossing, unconfirmed estimate or manual selection.
- **Reconstruct:** the gauge model applied to that same endpoint, only when enabled and available.
- **Last valid CSV strain:** the final finite strain reading in original acquisition order. Retained only in the inspector and Audit, along with its row/time.
- **Max retained CSV strain:** preserved in the inspector and Audit only. It is not a substitute for fracture EL.

#### Automatic failure-elongation selection

The inspector has a collapsible **How failure elongation is selected** explanation. Per-specimen **Fracture detection details** below the chart records which criterion was met, the selected original row and confirmation evidence. The method is **Acquisition-order endpoint selection (v8)**. Algorithmic detection is distinct from standards-derived confirmation: an export that ends above 10% or 2% of peak is not automatically unusable or an endpoint-review failure.

Detection uses original force readings, with engineering stress as an explicit proportional proxy if force is absent. It does not smooth, resample, sort by strain, merge duplicate strain readings or use work-hardening filters. The first maximum load defines the start of the post-peak search. No brittle/ductile selector is required.

1. **Confirmed sudden drop:** for consecutive readings, let `D = F[n] − F[n+1]` and `P = |F[n−1] − F[n]|`. A candidate requires `D > 5P`, followed by a recorded load below `0.02 Fmax`. Select the measured strain at `n`, before the drop. This criterion derives from **ISO 6892-1:2019, informative Annex A.3.6**. ASTM E8/E8M-25 §7.11.3.3 also uses the pre-drop strain for sudden failure, but does not define a numerical suddenness ratio.
2. **Sudden drop without recorded 2% confirmation:** retain its pre-drop reading as **Detected** if the decrement is at least 5% of peak and above twelve noise units, in addition to satisfying the >5× and non-recovery checks. Lack of confirmation is retained in the audit; it is not a review failure by itself or called ISO-confirmed. These extra evidence requirements are application safeguards. A tiny decrement following a near-zero change does not suffice.
3. **Rapid collapse spread across multiple readings:** a separate heuristic identifies sustained event-level loss of at least 5% of peak, even when every individual decrement is much smaller. It requires a local increase in unloading rate relative to recent background and persistent subsequent load loss. A load/strain shape check distinguishes sharp collapse from faster continued extension during progressive failure: acceleration in time alone is insufficient. Select the leading edge of a supported rapid fall, with **Detected** status. This is algorithmic detection, not the literal ISO adjacent-reading rule or confirmation of full standards compliance. It prevents highly sampled sudden failures from automatically falling through to the terminal point.
4. **No supported sudden event:** use the measurement immediately before the first post-peak load below `0.10 Fmax`, based on **ASTM E8/E8M-25 §7.11.3.4**. This is 10% of peak **remaining**, not a 10% loss. A smaller unresolved sudden-drop candidate makes this selection review-flagged.
5. **Progressive unloading but export ends above 10%:** a terminal estimate is permitted when load ends at or below 50% of peak, the preceding eight increments show continuing loss above noise, no load/time gap has occurred since peak, and no increment in that terminal window recovers more than the greater of 2% of peak or twelve noise units. Use the final recorded measurement, with **Estimated** status and a review warning. This does not establish actual separation or standards confirmation. Ordinary rising curves, plateaux and gap-truncated sequences do not qualify.
6. **No supported evidence:** automatic EL remains **Not detected**. There is no unconditional final-reading fallback. A missing strain/stress value at the selected row is not replaced by a neighbouring reading. Review the full curve or apply a manual EL override.

**Application safeguards (not additional standards clauses):**

- Do not search past a missing load row after peak, or a time interval exceeding ten times the median interval when a complete increasing time channel exists. Without such a time channel, use original row order and record that limitation.
- Estimate normalized force noise as `1.4826 × MAD(second differences) / sqrt(6)` using contiguous triples (at least five differences). A sudden decrement must exceed six noise units and a floating-point floor. No force values are changed by this check.
- Search sudden-drop candidates only through the first below-10% crossing, excluding fluctuations in the unloaded tail. Reject a candidate if the signal recovers more than half its decrement before the first below-2% reading (allowing three noise units). Without confirmation, check recovery through the end of the continuous segment.
- Among qualifying confirmed candidates, select the **largest consecutive loss**, preferring the later candidate on an exact tie. There is no backward onset refinement or strain setback. A preceding change of zero still permits an above-noise positive drop; its ratio is undefined and noted in Audit.
- The multi-reading heuristic compares load/time rates (or rates per original row when time is unavailable). A leading edge must exceed six times the median absolute rate of the preceding eight increments, plus a noise allowance. Consecutive qualifying increments count as one edge. Geometrically growing windows (bounded by 512 readings and approximately 2% of the continuous record, with a four-reading minimum when available) establish sustained event loss and contrast with preceding unloading. Three recovered readings reject a transient excursion. The largest supported persistent event wins. The leading edge is **not** required to reach a percentage of the later maximum rate: an accelerating collapse can start much more slowly. Within an accelerating lead-in, a further rate jump exceeding six times the immediately preceding rate magnitude (plus noise allowance and the rolling-background check) identifies a sharper transition. Select the first increment of the final consecutive jump cluster before the maximum unloading rate; otherwise retain the initial edge. There is no arbitrary backwards strain setback. The window, event-level loss, rate basis and selected-edge/background rates are recorded in Audit. These are heuristic safeguards, not ISO thresholds or a guarantee of sampling independence.
- Recovery above 10% of peak after the crossing is flagged. A selected strain below peak-load strain or unusable strain/stress makes the endpoint unavailable.
- For the multi-reading heuristic, compare force loss per additional strain across the candidate event with the preceding eight-increment baseline. The event uses original strain at the onset and the largest subsequent strain through the event window; the baseline uses net advancing strain and the magnitude of net load change, floored by six noise units. Require an event-to-background ratio greater than six. A force fall with negligible or negative additional strain passes this shape check. A finite advancing baseline is required for corroboration; absent one, retain the load-based candidate with a review warning. This safeguard rejects rapid load/time changes caused by continued ductile extension without altering the literal ISO adjacent-reading rule. It uses no fitted elastic modulus, strain smoothing, or user-assigned brittle/ductile category. The shape-check result and contrast are retained in Audit and inspector details.

This hybrid combines standards-derived criteria with application safeguards; it is **not a declaration of full ASTM or ISO compliance**. Sampling, quantisation, tracking errors and machine unloading can affect the result. Audit preserves criterion, ISO-style confirmation flag, review reason, original row/time, 10% and 2% rows, decrement evidence, noise floor and thresholds. Clear detected collapses are not review-flagged solely for lacking a recorded 2% confirmation. **Estimated** terminal endpoints remain available for EL, toughness, tensile curves and reconstruction, while their review flags persist; they are not automatically excluded. Selection is independent of Instron EL and precedes gauge reconstruction. The legacy `fracture_slope_fraction` setting is retained but unused.

References: [ASTM E8/E8M-25](https://store.astm.org/e0008_e0008m-25.html) and [ISO 6892-1:2019](https://www.iso.org/standard/78322.html).

In the landmark calculation, the pre-break **shape** endpoint is normally the selected endpoint minus 0.05 percentage points; its post-UTS shape is mapped back to the selected EL landmark. The setback does not reduce reported EL. With no supported endpoint, **Not detected** leaves EL/toughness and reconstruction unavailable. Specimens are not automatically excluded. YS, UTS, uniform elongation and both WH methods remain available when their own pre-peak requirements are satisfied; landmark WH needs no fracture endpoint.

### Calculation inspector

Expand **Specimen properties**, open **Specimens**, and click a specimen name. The **Calculation inspector** tab shows the exact prepared curve and elastic-fit points used by the shared property calculation. You can also choose a specimen directly in that tab, or use **Previous / Next** to follow the current table's filtered/sorted order. Excluded specimens can be inspected without re-including them; hard-ignored files cannot.

#### Manual failure elongation

Open **Adjust failure elongation · preview before applying**, then tick **Edit failure EL**. The inspector switches to **Failure detail**. Enter **Failure EL (%)**, click the measured curve, or select the original **Measurement row**. The numeric entry snaps to a finite recorded post-peak point; it does not extrapolate or invent a stress value. Repeated/reversing strain can have several matching rows, so check the displayed row and stress and use the row selector or curve click to distinguish them. Editing fit and EL are separate previews; only one is active at a time.

**Failure detail** sits beside **Yield detail** and **Full curve**. It zooms to the measured tail and the available Calc, automatic and Instron EL positions, with nearby necking context and local stress limits. With reconstruction overlaid, its endpoint is included too. **Reset zoom** returns to the chosen view. These view controls do not change endpoint selection or calculations.

The purple × previews the manual endpoint, and a grey open circle retains the automatic endpoint when available. Enter a reason and click **Apply EL override · all graphs**. **Cancel EL preview** discards unsaved edits. **Restore automatic EL** removes the override. Input is measured engineering strain, not reconstructed strain. The saved endpoint trims the raw acquisition prefix; Calc EL, specimen toughness, representative/average tensile curves, strength–EL plots and gauge reconstruction all use it. Pre-peak YS, UTS, uniform elongation and WH are unchanged. Click **Update plots** after saving; existing previews are invalidated rather than silently exported with old settings.

Overrides are specimen-wide and persist in the personal project JSON, independently of graph selection. **EL selection** in Specimens (and Excel) shows Manual, Automatic or an override problem. Audit retains automatic EL, selected row, reason and timestamp; exported policy/history retains the original automatic snapshot and source fingerprint. Changing the source file makes its override stale: it is not applied, automatic selection resumes, and the specimen is flagged for review. Original CSV and Instron results are never overwritten. Manual selection resolves the automatic endpoint warning but does not suppress unrelated checks.

**Yield detail** zooms to the elastic fit and 0.2% offset crossing. **Full curve** shows the original measurement in acquisition order, UTS/uniform elongation and a purple cross at the selected endpoint. Its selected criterion appears in **Fracture detection details**, not publication legends. Missing selection is stated explicitly. Fit markers remain the points actually used by the yield calculation; the reconstruction overlay ends at the corresponding transformed endpoint. Drag to zoom; **Reset zoom** returns to the chosen view. The elastic and offset lines use the specimen-specific fit, not the WH modulus. An unresolved yield shows its reason instead of inventing a marker.

**Show on plot** is a grouped checkbox legend below the chart, outside the axis-label area: **Curves**, **Yield & fit**, **Peak**, **Fracture** and **Diagnostics**. Fit lines/points default to visible in Yield detail and hidden in Full curve. Maximum retained strain, the fracture vertical guide and the Instron YS reference line are optional diagnostic layers. **Reset shown items** restores the current view's defaults. Visibility choices are remembered separately for each view during the session and never change calculations. Manual-fit edit handles remain visible while editing.

Calculated and available matched Instron properties are listed side by side. EL has a separate **Elongation sources** table rather than a calculated-minus-Instron comparison of different endpoint definitions. **Instron EL** is a magenta hollow diamond: its strain is imported from the summary and its stress is interpolated from the measured CSV curve, not an Instron fracture-stress result. If its strain lies just outside the CSV range within printed-digit rounding tolerance, the marker is snapped to that boundary. The original imported value remains in tables and hover, with the display adjustment explained. Tolerance is half the last printed summary unit, plus half the original CSV maximum-strain unit when applicable, and a tiny floating-point allowance; unavailable precision is not guessed. Larger discrepancies remain flagged without extrapolation. This changes neither calculations nor matching. UTS and maximum force share one marker when their coordinates agree; otherwise the original maximum-force point is a separate red open triangle under Diagnostics. It marks the reconstruction breakpoint, not fracture. Compare the Instron diamond against the purple Calc EL marker: the latter is selected independently of the reported Instron result. **Instron YS** has a magenta hollow diamond at the first ascending pre-UTS CSV crossing of the reported stress. Its strain is CSV-interpolated, not an Instron yield-strain result. Its horizontal stress reference is available under Diagnostics and shown by default if no crossing is available. Fit fractions, selected-point count, R², intercept, crossing bracket, source identity and preparation details are available below the chart. The inspector does not use WH filters or the WH modulus.

**EL source for plots** uses **Calc** or **Reconstruct** in the specimen table and Excel export. Detailed endpoint provenance remains in the audit data.

**Labels and colours** sits immediately above the displayed plots, below the plot selectors and update controls. Overrides still apply to every plot type in the selected graph definition.

Changing the selected specimen or zoom does not change calculations. No specimen chart is generated until selected, and inspecting or adjusting a preview writes nothing to the output folder.

### Fit warnings and specimen overrides

The **R² warning threshold** box beside the review warnings, above the collapsible **Specimen properties** section, is editable and saved for all graphs (default **0.98**). Enter a value and press Enter or leave the field to save. Fits below this threshold are flagged; it does not change the fit or specimen inclusion. The banner includes all specimens with **Checks** messages or fit warnings in the selected groups, including excluded specimens: low-R²/unresolved fits, stale overrides, missing fracture EL, gauge-reconstruction issues and Instron checks. **Review specimens** opens the inspector filtered to these specimens. Turn off **Only specimens needing review** to return to the full table. These are review flags, not automatic exclusions; a high R² or a detected endpoint does not by itself confirm a correct result.

In the inspector, expand **Adjust elastic fit · preview before applying**:

- **Manual range:** choose **Set start** or **Set end**, then click a measured point to fill that strain field. You can also type bounds or drag the purple range borders. Bounds snap to measured points; a least-squares line is fitted to all prepared points between them. At least five points are required, strictly before UTS.
- **Manual line:** choose **Set start** or **Set end**, then click a measured point to fill both its strain and stress coordinates. You can also type coordinates or drag the purple line endpoints. This sets slope and intercept directly. R² describes residual agreement with measured points between the endpoints, not a least-squares fit; it can be negative. A positive slope and a resolved 0.2% offset yield intersection are required.
- Inspect the resulting yield, modulus, R² and offset-line intersection against the measured curve and automatic baseline. Enter a reason, then select **Apply override · all graphs**. Until then, these are unsaved previews. **Cancel preview** discards edits; **Restore automatic fit** removes the saved override.

Entering either YS manual mode opens **Yield detail** and arms **Set start**. After choosing a start point the picker advances to **Set end**; after choosing the end it returns to **Not picking**. Re-arm either button to change that endpoint. Chart clicks outside manual editing never change a fit, and no click saves an override.

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

Each specimen now shows its actual **CSV filename** and **Assigned Instron row** beneath the displayed operator label. Click the filename to reveal/copy its full path. For a UTS mismatch, **Checks** also lists any UTS-compatible summary rows from the same named export dataset, including their operator labels, UTS and summary filenames. Every candidate must meet the existing printed-precision tolerance; conflicting summary revisions are not suggested. Multiple candidates stay visible rather than choosing one. These are file-review hints, not proof of identity: no file is renamed, no summary is reassigned, and EL is not used. CSV filename and assigned row are also included in the specimen Excel sheet. After correcting filenames yourself, use **Reload data** and review any saved overrides/exclusions affected by changed file identities.

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
proxy. The endpoint is the selected pre-drop, pre-10%-crossing, supported terminal estimate or manual measurement,
never the deliberately earlier landmark shape-trimming point.
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

Numeric cells retain full precision and display two decimals, except elastic-fit R², its threshold and fit/yield strain details, which display five. Counts are
integers. Historical exports are not rewritten. Restart the running app to load
code changes before creating a new export.

## Strength versus elongation plots

Select **0.2% YS vs elongation** and/or **UTS vs elongation** under Plot views for any graph definition. Both use the current analysis EL on the x-axis and strength in MPa on the y-axis. EL uses the selected CSV endpoint, or its gauge reconstruction—not Instron's break result, uniform elongation or a post-fracture gauge-length measurement.

Diamonds show group means of calculated per-specimen properties. **Show individual specimens** adds faint circles for the individual specimens; the paired with/without-individuals option works too. Optional horizontal and vertical **±1 sample SD** bars show scatter in EL and strength, not confidence intervals. A single specimen has a mean point but no SD bars. Groups are not joined by lines or fitted to a trend.

Each point requires both properties to be available. If a yield fit is unresolved, that specimen is omitted from the YS–EL plot and its mean/SD, with a warning in the calculation log; it can still appear in UTS–EL. The legend's n is the number of valid paired specimens. These views use the same specimen-property calculations and Include selections as the tables, independently of landmark fitting, WH filters and the WH elastic modulus. They show **Calc**, not Instron summary values. Where a metric is unavailable, paired plot means may differ from table means that count each property separately.

Each view has its own title and independent x/y limits under Settings. The with/without-individuals versions of a given scatter plot always share automatic limits based on all included paired specimen values and any displayed SD bars; manual limits override these for both versions. Colours and group legend labels follow the graph's overrides. Static and Plotly views show the same values. Individual hover labels use matched operator names, or CSV stems when unavailable, not long folder paths or arbitrary curve numbers. Full source identity remains in the tables. Exports are numbered `08_ys_vs_el` and `09_uts_vs_el`, with adjacent `with_individuals` / `without_individuals` filenames. Existing saved graphs gain these options without changing their current selected plots.

## YS, UTS and elongation by sample

Select **YS, UTS and elongation by sample** under Plot views. Sample groups run left to right on a categorical x-axis; **0.2% YS** and **UTS** use the left strength axis, and failure **EL** uses the right percentage axis. Three lines connect the group means as visual guides, not fitted trends. Each property uses its own available included specimens, so an unresolved YS does not discard a valid UTS or EL. Missing values leave a gap. EL follows each group's Calc/Reconstruct setting, including manual endpoint overrides.

Open this plot's **Settings** to select a group in **Sample order** and use **Move left / Move right**. The list runs top to bottom in x-axis order. The order is saved per graph, affects only this plot, and is remembered when groups are deselected or sample data is hidden. Newly selected groups append to the order. **Connecting lines** selects **Straight / solid**, **Dash**, **Dot** or **None · markers only**, applied equally to YS, UTS and EL. Selecting None retains the mean markers and any enabled SD bars. Settings also provide independent left/right axis limits, a title, property colours, and optional ±1 sample SD bars. A single specimen has no SD bar.

Under **X-axis labels · this plot only**, enter a short label beside each selected group (for example, `0% CO₂`). A blank entry uses the usual group display name. Explicit line breaks are supported, and labels are wrapped to fit the available category spacing without truncation. Static exports use measured text widths; Plotly rewraps labels when resized or enlarged and reserves space above the legend. These labels are saved per graph, survive deselection/reselection, and do not rename groups, files, tables or other plots. Plotly hover retains full group identification.

**Show individual specimens** adds faint, unconnected points; Plotly hover identifies specimens and reports the mean's n. Both display modes and with/without-individuals variants use the same values and axis limits. Colours identify properties here, not sample groups. Exported plots use `10_properties_by_group_with_individuals` / `without_individuals`. The existing results workbook supplies the underlying properties and mean/SD/n; no average tensile curves are fitted or exported for this view.

## Per-graph colours

Expand **Labels and colours · this graph, all plot types**, select a group, tick **Override colour for this graph**, choose a colour and click **Apply group overrides**. Untick it and apply to restore the automatic colour. Overrides are saved with the graph and apply to group-coloured static and Plotly views and exported plots. The dual-axis property plot instead has its own YS/UTS/EL colours under Settings. Different graph definitions can use different colours for the same group.

## Advanced notebook mode

The normal web app uses the **Tensile Workbench** browser-tab title and its own
tensile-curve favicon, served locally from the bundled `web/` assets. Restart
the launcher after an update; refresh the browser tab if it retains an old icon.

The normal Launch files open the web app. For the original JupyterLab editor, run `launch_workbench.py --notebook` with the workbench environment's Python, then use **Run > Run All Cells**. This remains optional; both interfaces share calculations and saved definitions. Avoid simultaneous editing sessions for the same project.

## History and the original installation

The original OneDrive installation was copied, not moved or edited. The `v18-baseline` Git tag preserves the imported software. No research plots or existing output tables are regenerated during installation or upgrade.
