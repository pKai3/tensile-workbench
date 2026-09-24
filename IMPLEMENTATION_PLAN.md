# Implementation record

## Change notes — 2026-09-24

### Property-specific specimen exclusions — requested for later

- Allow a specimen's individual properties to be excluded without discarding its
  valid remaining measurements. Keep whole-specimen exclusion available.
- Record the property, reason and scope against the stable specimen identity;
  default to specimen-wide persistence across graphs, with explicit graph
  exceptions consistent with the existing inclusion policy.
- Preserve imported/calculated values for inspection and audit; mark them as
  excluded rather than deleting or overwriting them. Atypical values alone are
  not automatically invalidated.
- Apply exclusions consistently to statistics, plots, comparisons and Excel
  exports, with separate valid n per property and paired n for paired analyses.
- Define dependency rules before implementing: excluding an unreliable EL must
  also affect reconstructed EL, endpoint-dependent toughness and affected
  average/representative curves, without needlessly discarding valid pre-peak
  YS, UTS, uniform elongation or WH. Avoid silently retaining an invalid input
  in downstream results. Clarify any distinction between an invalid measurement
  segment and excluding only a reported result.
- UI, dependency behaviour and export schema require a separate implementation
  request. No property-specific exclusion logic is added in this change.

### Summary-page Instron/Calc comparison — implemented after design approval

- The user selected percentage differences around zero instead of paired
  100%-normalised bars. Calculate 100 × (Calc − Instron) / Instron for each
  included specimen/property pair; show group mean ±1 sample SD of those
  percentages. This is not the percentage difference between group means.
- The collapsible chart below Summary renders only when opened. Properties
  use compact panels three across (two/one on narrow screens) with independent percentage-axis ranges, so larger
  discrepancies cannot hide small ones. Hover reports paired n,
  original-unit means and the count of pairs carrying specimen checks.
- UTS is omitted from these charts and their spread tables. Its existing
  original-CSV-versus-summary check still flags disagreements beyond exported
  precision tolerance; no matching logic or tolerances were relaxed.
- Each panel has a spread table below it: paired n, Instron sample SD, Calc
  sample SD and 100 × (SD Calc / SD Instron − 1). The two SDs use exactly the
  same paired specimens as that panel. n<2 has no SD, and zero Instron SD
  leaves percentage change unavailable. Less scatter is not proof of accuracy.
  This is distinct from the chart's SD of paired percentage differences.
- Use existing reference assignments and include decisions; require both
  finite values and a nonzero Instron denominator. Do not filter out numerical
  disagreement or existing review warnings to improve apparent agreement.
- Omit properties without comparison data; n=1 gets no SD bar. Explain that
  the bars show specimen spread, not uncertainty of the paired difference.
- Compare measured Calc with Instron on the original gauge basis, not
  reconstructed EL/toughness against uncorrected Instron values. EL endpoint
  definitions may differ; label that distinction rather than treating all
  differences as calculation errors.
- The same aggregate values are included in a Calc-Instron agreement sheet
  in the existing results workbook when usable comparison pairs exist,
  including the SD comparison and audit-only UTS aggregates.

### Inspector layout — implemented

- Specimen check messages now sit above the graph and update with
  specimen selection and unsaved fit/EL previews; an empty check list is hidden.
- Show on plot stays directly below the chart as an always-visible checkbox
  legend whenever a specimen chart is present; it is outside all folds.
- Adjust elastic fit and Adjust failure elongation are individually collapsible
  directly below specimen warnings and above the plot, outside the details fold.
- Calculation/source/gauge reports and method explanations are collapsible
  within one outer Inspector controls and calculation details fold. The selector
  and view toolbar remain visible.

## Historical implementation notes

The notes below describe earlier change sets and are not a current test report.

Status: Excel consolidation, per-group gauge reconstruction and inspector
measured/reconstructed overlays implemented. Runtime verification not performed.
Tests and output generation deliberately not run, at the user's request.
The runtime uses each specimen's imported Strain 1 gauge length as confirmed
AVE initial dot spacing. Each sample group has its own persistent toggle and
target gauge length within each graph. Invalid metadata in enabled groups
blocks reconstructed plots rather than silently substituting measured curves.
No specimen geometry or manual peak/endpoint editor has been added.

## Latest change set — implemented, not tested

The user subsequently authorised implementation, explicitly without tests.
The following scope supersedes the historical design notes farther below.

- Gauge controls are compact auto-saving rows (group, target, checkbox), not a
  one-group-at-a-time dropdown. The editable project-wide R² warning threshold
  is visible beside fit warnings above the collapsible specimen tables.
- Publication plots omit explanatory footers and gauge labels. Only the
  landmark marker key is retained where its three marker types are displayed.
  Gauge basis/targets and method notes remain in logs, tables and metadata.
- Replace the former all-groups reconstruction controls with controls for each
  sample group: enabled/disabled and target gauge length in mm. Storage
  is per-group settings inside each graph definition, alongside the existing
  per-group overrides. This permits two groups with different targets in one
  comparison without changing the imported specimen metadata.
- Preserve existing graph-wide choices through explicit legacy fallback or
  migration to the graph's existing groups. Newly added groups should default to
  measured/off, not silently inherit an unrelated target.
- Resolve one effective group policy centrally for plots, properties, caches,
  inspector previews and exports. Retain each specimen's own AVE dot spacing;
  never replace it with a group-average spacing. Exports and UI audit fields
  expose each group's active basis and target, including mixed measured/derived
  views, without adding them to publication plot legends.
- Replace the hard longer-target rejection with a documented model warning.
  The algebra is defined for any finite positive gauge ratio: ratios below one
  reduce the post-peak increment, while ratios above one increase it. This is
  an extension of the proposed localisation model, not a standards-validated
  conversion. Both gauge intervals must capture the relevant localisation;
  deformation outside the measured interval is not recovered by the formula.
  Invalid lengths, missing strain at the actual force peak, incompatible strain
  channels and invalid endpoints remain review errors, with no automatic
  exclusions or measured fallbacks.
- Add a display-only "Overlay measured / reconstructed" toggle to the existing
  specimen inspector. Show a dashed, labelled estimated curve over the measured
  curve and expand full-curve axes to include both. The preview may be inspected
  before enabling reconstruction for that group, provided a target is entered.
  It must not change saved settings, fit selections or measured properties.
- Show AVE spacing, target, ratio, model warning/status, measured/estimated
  failure elongation and toughness, and the actual acquisition peak marker and
  row/time. Keep elastic-fit controls and the measured baseline unchanged. When
  preview is unavailable, display the specific reason rather than a fake curve.
- The earlier peak error incorrectly depended on survival of the peak row in a
  plotting-cleanup grid. That check has already been removed. Subsequent review
  must distinguish a valid original peak removed by cleanup from a genuinely
  absent/nonfinite strain at maximum force; never guess a replacement peak.
- Peak/endpoint manual repair tools discussed earlier remain a separate planned
  feature, not implemented by adding the overlay.
- Do not run tests or regenerate research outputs under the current instruction.

## 1. Consolidated Excel exports — approved

Produce at most two Excel workbooks per graph export in the existing snapshot
folder. Do not regenerate historical research outputs or change source files.

### `{graph_name}_results.xlsx`

- **Summary:** one row per sample group; properties as columns with calculated
  and Instron results adjacent. Retain separate numeric mean, SD and valid n.
- **Specimens:** one row per specimen; inclusion status and reason, stable ID,
  group/name, calculated/Instron property pairs, yield strain, pre-break stress
  and explicit manual-fit override status.
- **Checks:** specimen fit quality and bounds, warnings, automatic-fit baseline,
  readable override fields, Calc–Instron differences and source references.
  Do not expose raw override JSON as a wrapping table column.
- **Instron comparison:** paired group-level agreement statistics, including
  paired n, mean/SD difference and mean/max absolute difference.
- **Export info:** export identity/time, graph and calculation settings, units,
  software identification and source provenance. Distinguish fitted specimen
  modulus from the modulus configured for work hardening.

Excluded specimens remain visible and flagged, but do not enter summaries.
The existing hard-ignore rule for files/directories containing `!` remains.
Remove redundant standalone property, uniform-elongation and landmark-summary
workbooks; preserve their nonredundant fields in the consolidated tables.

### `{graph_name}_curves.xlsx`

Conditional sheets, only for methods in the views actually being exported:

- **Tensile landmark**
- **Tensile pointwise**
- **Tensile representatives**
- **WH specimen average**
- **WH landmark**
- **Tensile individuals** and **WH individuals**, when requested by an exported
  view; export each underlying dataset only once.
- **Curve checks:** group/method, contributing n, curve coverage/completeness,
  diagnostics and integrated mean-curve toughness versus mean specimen
  toughness. Do not report a full-curve percentage error for an incomplete mean.

Use adjacent X/Y column pairs per curve with unmerged, single-row headers and
explicit units. Keep each curve's own coordinates and length; leave trailing
cells blank rather than extrapolating, padding or resampling for table layout.
Pointwise curves use strain, measured-stress and projected-stress columns so
external software can draw measured and projected portions separately.

Export-selection rules:

- A landmark-only export must not produce pointwise curves or pointwise area
  statistics merely because shared computation currently builds both models.
- Comparison plots require both methods, once each.
- Static/interactive and with/without-individuals views must not duplicate data.
- Distinct calculation settings in separate views must produce distinctly
  identified datasets. Do not recompute all exported data using the first view's
  settings.
- A table-only export creates only the results workbook and does not calculate
  average curves.
- Strength–elongation scatter plots reuse Summary and Specimens properties.
- Preserve full numerical precision while displaying three decimal places;
  counts are integers, missing numeric results are blank, and missing-data
  reasons/statuses remain explicit. Freeze identifying columns/headers as needed.

## 2. Gauge-length elongation estimate — requested; full reconstruction selected

Add an opt-in choice between measured failure elongation and a derived
standard-gauge elongation estimate. Default to measured data. Never overwrite
source measurements or imply that the estimate is a standards-compliant test.

Using total engineering strain consistently, for each specimen:

    ratio = actual_dot_spacing_mm / target_gauge_length_mm
    estimated_failure_strain_pct = peak_force_strain_pct + ratio * (
        measured_failure_strain_pct - peak_force_strain_pct)

Only the post-peak increment is scaled. Calculate at specimen level before
forming group statistics; do not apply one ratio to group-average properties.

### Dimensions and persistence

- The current summary importer recognises Thickness, Width and Strain 1 gauge
  length (with supported-unit conversion to mm). These are currently exposed
  through diagnostic exports, not a separate editable geometry model.
- Preserve imported values and their provenance independently of overrides.
- Add explicit actual AVE dot spacing and target gauge length in mm. Do not
  silently equate an arbitrary instrument gauge field with confirmed dot
  spacing, or confuse either with overall specimen/reduced-section length.
- Overall specimen length and parallel-section length are distinct optional
  metadata; neither is an input to this formula.
- Allow persistent specimen-level entries/overrides shared across graphs, with
  convenient group/bulk entry and specimen exceptions. Bind overrides to stable
  specimen/source identity and flag changed sources rather than silently reuse
  stale overrides. Personal values remain in ignored local settings.
- Record target-standard identification when provided, but do not infer a
  standard or hard-code a required length from the example values.
- The display/analysis basis selection is persistent per graph. Show the active
  basis clearly in tables, axes, tooltips and exports.

### Import and endpoint audit

- Preserve original acquisition order, original measurement-row identity, time,
  force and the selected strain/stress channels before cleaning/sorting.
- Use the actual maximum-force point, retaining its original row/index and time.
  Validate finite matching strain at that point; do not silently select another
  peak because its strain is more convenient.
- Where force is unavailable, only permit an explicitly identified maximum
  engineering-stress proxy when the stress channel is confirmed to use a fixed
  original cross-sectional area. Document this fallback and peak-tie policy.
- Preserve the selected failure endpoint's original row/time and selection
  method. The existing final prepared strain is not proof of an independently
  identified physical fracture event; avoid silently changing the historical
  endpoint definition while adding the correction.
- Store measured total engineering strain at peak and at the failure endpoint,
  both lengths and sources, ratio, estimate, basis and validation status.
- If post-peak extension in mm is exported, convert percent to a fraction:
  `post_peak_extension_mm = L_dots * (epsilon_f_pct - epsilon_u_pct) / 100`.

### Validation and interpretation

- Require positive, finite lengths, a confirmed compatible engineering-strain
  basis, a valid peak and a valid failure endpoint at/after that peak.
- Missing or conflicting metadata gives an unavailable estimate with a reason,
  never a silently substituted raw value in a corrected-only group statistic.
- Equal lengths give the measured value; zero post-peak increment is unchanged.
  Warn/block requests outside the supported shorter-target-gauge scenario.
- Preserve raw and derived elongation side by side, with valid n for each.
  Instron agreement checks continue comparing like-for-like measured results;
  do not score the derived estimate against an uncorrected Instron value as a
  calculation error.
- Explain the model assumption: the post-peak extension is assigned to a shorter
  gauge centred on the neck/fracture. Deformation/unloading outside that gauge
  cannot be resolved from a single gauge history. Reprocessing spatial/video
  measurements is preferable when available.
- This estimate remains a total engineering-strain quantity at the chosen test
  endpoint; it is not automatically permanent elongation measured after fracture.

### Full reconstruction scope — user selected

Apply the relation to every point after maximum force, using acquisition order
to identify the segment:

    epsilon_estimated(i) = epsilon_measured(i)  # at/before peak force
    epsilon_estimated(i) = epsilon_u + ratio * (epsilon_measured(i) - epsilon_u)
                                             # after peak force

Stress/force values are unchanged. Preserve original measurements and construct
a separate derived curve; the correction must not mutate raw arrays.

When the derived basis is selected, consistently rebuild individual tensile
curves, representative selection/curves, pointwise and landmark averages,
failure-elongation summaries, strength–elongation plots, curve-area statistics
and the corresponding Excel datasets from the per-specimen derived curves.
Do not move just the terminal point or correct an already averaged curve.
Explicit representative overrides continue to select the same specimen.

The pre-peak response, YS, UTS, fitted E and uniform elongation are unchanged by
this correction. Pre-peak work-hardening calculations and their averaged or
landmark-derived outputs must remain unchanged; test against indirect effects
from sorting, resampling, smoothing and property-cache dependencies.

Maintain separate measured and estimated elongation/toughness properties in the
results workbook and identify the active basis in curve headers/metadata.
The corrected area is an integral of a reconstructed engineering curve, not a
new directly measured or gauge-independent material toughness. Compare the area
of a derived average curve with the mean of the derived specimen areas, never
with a mismatched measured population/basis.

For a selected derived basis, specimens without a valid correction must not be
silently plotted/averaged using raw post-peak data. Report availability and
explicit omissions, require consistent populations for method comparisons and
make missing metadata actionable in the specimen editor. Their unaffected raw
properties remain inspectable. A missing length must not trigger silent changes
to the specimen inclusion flags or unrelated YS/UTS/WH calculations.

### Verification before release

Use synthetic fixtures, not regenerated research outputs:

- The supplied 10% peak / 18% failure / 50 mm dots / 25 mm target example gives
  26%, while peak strain stays 10%.
- Equal gauges, zero post-peak increment, invalid/missing lengths, missing force,
  unavailable peak strain, duplicate strain values, nonmonotonic acquisition
  histories and explicit endpoint selection.
- No pre-peak/WH changes; no alteration of imported Instron values; corrected
  statistics never mix raw fallbacks without explicit labeling.
- Persistence across graphs/restarts, source-change invalidation and cache
  invalidation when lengths or the selected basis change.
- Excel sheet selection, wide numeric curve layout, preserved precision and
  agreement between exported arrays/settings and the displayed views.
