# Implementation record

## Change notes — 2026-10-23

### Fast individual-specimen variable catalogue — implemented

- Build the location/name editor from bounded CSV header and summary reads,
  using the same identity-matching rules as analysis. Do not load numeric curves,
  hash entire files, fit properties or run fracture detection to list specimens.
- Cache the catalogue until data reload. Render the editor once per scope
  change, paginate the single-variable editor at 100 rows, and coalesce table
  redraws. Preserve unsaved values across pages and selected/all-group switches.
- Verification: 38 focused synthetic catalogue, variable, clipboard and plotting
  tests pass, including 1,000 editable specimen identities and a guard that
  fails if Show all invokes curve loading or property calculations.

### Individual specimen properties versus location — trial implemented

- Add Group means / Individual specimens modes to independent YS/UTS/EL chart
  variants. Existing saved group charts retain their behaviour. Specimen mode
  starts with markers only and the operator specimen number as the numeric X-axis;
  CSV acquisition indices and ambiguous names are never inferred as locations.
- Add separate Sample groups / Individual specimens tabs under Custom variables.
  Reuse single/table editing, clipboard paste and confirmed deletion. Seed the
  initial editable Location draft from operator numbers, with a fill-blanks
  action. Load the specimen catalogue lazily; include excluded specimens for
  editing, retain stable IDs, shared group order and natural specimen ordering.
- Preserve untested locations with a per-chart Planned locations field (inclusive
  integer range or numeric list), without inventing measurements or statistical
  weight. Optional linear/quadratic trends fit only real eligible observations;
  dashed in-range segments become dotted extrapolations beyond each property's
  measured range. Keep repeated locations separate and fits/connections per group.
- Respect partial exclusions, fit/EL overrides and gauge reconstruction through
  the existing property pipeline. Show no SD bars or duplicate with/without views
  for individual charts. Preserve specimen identities in interactive hovers and
  planned numeric ticks in static and interactive plots.
- Persist shared specimen variables separately from group variables. Include
  cache/export invalidation, project validation, approved move/forget handling,
  sample-data namespace migration and a numeric Specimen variables export sheet.
- Verification: 83 focused tests pass covering synthetic numerical/UI,
  clipboard, persistence, partial exclusions, moves and setup. A browser trial
  confirmed operator-number defaults, a two-column TSV paste/save and locations
  1–10 with real points only at 1, 4 and 7 and dotted extrapolation to 10. No
  research data, outputs or personal settings were changed.

### Animated tensile-coupon loaders — implemented

- Replace the circular busy indicator and initial Voilà spinner with one bundled
  cartoon dogbone SVG: stretch, snap, recoil and reset, with a surprised face.
  Use CSS animation only; no image service, new dependency or animation timers.
- Keep the initial loader's existing streaming/removal hooks and progress text.
  Preserve the busy overlay's nested operations, input lock, focus restoration
  and short-operation delay. Use a static intact coupon for reduced motion.
- Include the artwork inline in both contexts so it works before widgets load,
  in notebook mode and under a non-root server URL. Validate the new bundled
  files during launch checks.
- Verification: 38 focused tests pass (artwork/template streaming, activity,
  browser launch and setup). Synthetic browser preview checked both loaders,
  changing stretch/break states and normal page/control restoration. No research
  data or personal settings were used.

### Custom-variable deletion — implemented

- Add Delete variable in the single editor and an accessible × button per
  table column. Require confirmation, list affected chart variants (including
  deleted graphs), and allow cancellation without writes.
- Remove only the selected variable and its group values globally; preserve
  other unsaved edits. Unsaved-column removal does not write the project.
  Keep existing chart references explicitly unavailable rather than silently
  changing axes. Invalidate stale exports and require a new X-axis selection.
- Reject deletion if the saved target changed after confirmation was opened;
  leave drafts intact on failed saves and cancel pending deletion on graph or
  editor switches. Document the workflow and use synthetic regression checks.
- Verification: 67 focused synthetic tests pass (variables, clipboard, group
  ordering/property plots and setup). Browser checks confirm table-column
  deletion, cancellation, affected-chart warnings and the single-editor control;
  no personal project variables were changed.

### Property plot and custom-variable labels — implemented

- Rename the plot-view label to "YS, UTS and elongation by sample & by custom
  variable" and update the matching documentation. The internal plot ID, saved
  definitions and generated/custom chart titles are unchanged.
- Rename the editor section to "Custom variables · shared by all graphs" and
  keep navigation guidance and messages consistent.

### Automatic title units — implemented

- Put units in parentheses in both the property-chart automatic title and its
  grey placeholder, matching the variable-axis label: Heat Treat Time (h).
  Omit parentheses when units are blank; retain script formatting and custom
  title overrides. Verify with synthetic title/editor/plot regression checks.

### Variable table, clipboard editing and automatic chart titles — implemented

- Add a Table / One variable editor switch. The table shows editable names in
  row 1, units in row 2 and group values below, with fixed group identities,
  sticky headers, scrolling, Add variable (column) and Save all variables.
  Both editors share drafts; row order follows the graph and Show all includes
  unselected groups. Saving validates the entire batch before updating shared
  variables; hidden-group values and stable variable IDs are preserved.
- Support rectangular CSV/TSV/Excel paste at a chosen cell, quoted fields,
  blank units/values, zero and scientific notation. Grow variable columns as
  needed, but reject row overflow, ragged/invalid blocks or nonfinite data
  without partial edits. Copy variable cells as TSV for spreadsheet use.
  Clipboard edits remain drafts until explicitly saved.
- Use the same automatic property-chart title for plotting and the grey title
  placeholder: YS/UTS/EL vs. variable name and unit. Follow selected variables,
  enabled properties and chart variants without persisting generated text or
  overwriting custom titles. Format numeric sub/superscripts (CO_2, mm^2,
  m^{-3}) as Unicode in these titles and variable-axis labels only; keep saved
  text, numeric data and spreadsheet exports unchanged.
- Verification: all 63 focused synthetic editor/clipboard/plot/order/setup
  tests passed, plus an actual browser preview including a three-column paste,
  invalid-block rejection, save, TSV copy, editor switching and 60-group scrolling. No research outputs or
  personal settings changed.

### Show all sample groups scrolling — implemented

- Prevent variable-entry rows from shrinking into the capped list viewport;
  keep readable inputs and scroll through all groups. Allow wrapping on narrow
  screens and keep the save button compact. Clarify that Show all does not
  change the graph's selected groups.
- Verification: 19 synthetic variable/order tests passed. A standalone browser
  preview with 60 fake groups confirmed readable rows and scrolling to the
  final group. Draft values and selection remain unchanged when toggling.

### Setup-test fixtures and lightweight preflight — implemented

- Include the required template and favicon in synthetic installation fixtures
  so launch/check/missing-environment tests reach their intended checks.
- Move gauge, failure-override and property-chart settings validation into a
  shared standard-library-only module. Keep existing calculation-module imports
  compatible via re-exports. Route active, disabled and historical saved
  policies through the same validators without loading the numerical/UI stack.
- Property-chart colours use the project's existing six-digit hex rule,
  including nested chart variants, without importing Matplotlib to validate.
  Keep full setup/check imports intact; ordinary launch remains lightweight.
- Strengthen the cold-process import guard and test populated saved projects,
  disabled overrides, histories, variables and chart variants. Invalid values
  must still fail with useful messages and leave saved files untouched.
- Verification: all 24 setup tests and the final 63-test setup/variable/plot/
  order/saved-override run passed. A broader 115-test synthetic run had
  111 passes and four unrelated failures reproduced on pre-fix commit 0c5bffe:
  two old fit tests expect the retired workbook filename/fit-only review count;
  two fracture tests expect different detection statuses around missing force
  or time gaps. No detector algorithm or test expectation was altered to hide
  those failures. These four remain for a separate regression review.
- No research data processed, user environment replaced, or personal settings
  changed. The five setup failures previously recorded below are resolved.

### Variable editor follows sample group order — implemented

- Apply the shared per-graph order to variable-entry rows, including the
  Show all sample groups view; append unranked groups alphabetically.
- Refresh on order changes and graph load without discarding unsaved numeric
  entries. Preserve zero, deselected-group values and the variable name/units.
  Numeric plot X positions still use their actual numeric values.
- Verification: 18 synthetic variable/order tests passed, including reorder,
  Show all toggling, draft preservation, save/reopen and switching graphs.

### Sample-group variables and multiple property charts — implemented

- Add a collapsed Sample-group variables editor below sample selection/order.
  Save named numeric variables with optional units and per-group values across
  all graphs. Blank means missing, zero remains valid; reject nonfinite values
  and duplicate names. Keep values in the ignored personal project, preserve
  unselected groups and remap/forget them with approved folder operations.
- Extend the YS/UTS/EL chart to choose sample names or a numeric variable.
  Use real numeric spacing and ascending X order, with separate groups at
  equal X values. Flag missing values/overlap outside publication figures.
  Keep group/specimen identities and valid n in interactive hover text.
- Add any number of separately configured chart variants within one graph.
  Each has independent X variable, YS/UTS/EL switches, title, axis limits,
  short categorical labels, connecting lines, colours and SD bars. The editor
  switches between saved variants; Add copies the current one, Remove deletes
  only that chart. Existing graphs load as one compatible chart. Only EL or
  only strength uses a single axis; mixed charts retain dual axes.
- Preserve property eligibility, independent means, sample SDs, reconstruction
  policy and shared limits with/without individuals. Variables affect display,
  not specimen calculations. Invalidate cached numeric plots when values
  change and reject exports from stale variable settings.
- Render/export every variant with unique readable filenames and complete
  settings provenance. Include a numeric Group variables workbook sheet;
  do not generate unselected average curves or duplicate property tables.
- Verification: 57 focused synthetic checks passed across numeric plotting,
  all property-switch combinations, two independent numeric X variables,
  static/Plotly conversion, control save/reopen, legacy categorical behaviour,
  folder moves, export values/filenames and related colour/order/writer tests.
  Visually inspected a synthetic dual-axis numeric plot. No research outputs
  regenerated; personal graph definitions and data were not edited.
- Broader setup checks: five existing failures reproduced unchanged from
  commit 33b1c1d (four fixtures omit required web assets; one test forbids a
  NumPy import already made by project validation). They are not caused or
  repaired by this feature.

### Shared group order — implemented

- Add a saved per-graph Group order list with Move up/down in a collapsible
  Sample group order panel directly below the sample selector, above the tables.
  Group legends follow it in static and Plotly plots and both specimen
  display variants; WH comparisons keep the two methods adjacent per group.
- Summary/specimen tables use it for their default Group sort; explicit other
  sorts and filters remain available. Apply the same order to Calc–Instron
  charts/SD tables and numeric Excel table rows. The categorical YS/UTS/EL
  chart now uses this same order for its x-axis; its property legend stays fixed.
- Preserve colours, calculations, curve geometry, specimen eligibility and
  within-group row order. Reorder cached table frames without recalculating.
  Remember deselected/hidden groups, append new selections, remap on approved
  folder moves and remove the saved reference when a group is forgotten.
- Verification: five focused ordering tests and 49 related regressions passed
  with synthetic data only (including all nine group-legend plot families,
  both individual variants, Plotly conversion, table/export-frame invariance,
  autosave/reopen, folder moves and the sample-data toggle). Updated one stale
  sample-data test assertion to check the existing global exclusion store.
  No research plots/tables regenerated.
- Placement follow-up: move the order controls out of Labels and colours into
  their own collapsed panel below sample selection. Layout and saved-order
  persistence checks passed; ordering behaviour is unchanged.
- Single-order follow-up: remove the triple-property plot's separate selector
  and move buttons. Remove the old setting entirely, with no migration/fallback
  into the shared order. Ignore it on load and strip it from active/deleted
  graphs and new-graph defaults on normal saves. Only shared order participates
  in folder-move tracking. No shared order means alphabetical folder order.
  Update the triple-plot cache key and short-label editor to follow shared order.
  Twenty-nine focused synthetic plot/control/persistence/move checks passed,
  including obsolete-setting removal and x-axis cache invalidation.

### Aligned summary statistics — implemented

- Render summary means, ± symbols and SDs in separate aligned tracks, sized
  consistently down each property/source column. Use tabular digits and
  right-aligned numeric values so decimal places line up without padding text.
- Preserve singleton means without SD, missing-value dashes, blank unavailable
  reconstruction cells and per-cell n notes. Keep intrinsic table sizing and
  horizontal scrolling; no changes to calculations or numeric Excel exports.
- Verification: four focused synthetic HTML/data-integrity tests passed and
  the rendered table was visually checked in a temporary browser preview.
  No research data loaded or research outputs regenerated.

## Change notes — 2026-10-21

### Excel export performance and compact scatter counts — implemented

- Stream workbook rows with shared immutable styles and per-column number
  formats. Remove the second cell-formatting pass and omit styled blank
  padding between unequal-length curves. Retain all numerical points, full
  precision, sheet/column order, headings, filters and freeze panes.
- Preserve literal text (including formula-like labels), native booleans and
  dates, missing-value handling and atomic replacement. Clean streaming XML
  and incomplete workbook files on failure. No new dependency or progress UI.
- Scatter legends use one n when strength and EL counts match; split counts
  only when they differ. Applies to YS–EL and UTS–EL, static/Plotly and both
  individual-display variants. Means, SDs and population selection unchanged.
- Verification: 12 focused synthetic writer/plot/export checks passed.
  A 24-curve, 5,000-row, 48-column benchmark (171,000 populated values) fell
  from 4.777 s to 1.459 s on this machine, about 3.3× faster. This is not a
  timing guarantee for research datasets. No research outputs regenerated.

### Landmark population labels — implemented

- Show a single n only when the shape population and all relevant landmark
  coordinate counts match. Otherwise use shape n plus separate YS/UTS/EL n
  in tensile landmark/comparison legends, identically with/without individuals.
- Follow-up: landmark-derived WH legends show only shape n, including the WH
  comparison view. Keep YS/UTS/UE input-population counts in the calculation
  log and curve export; do not add anchor error bars to WH plots. Apply to both
  static/Plotly and with/without-individuals views. Pointwise-only labels unchanged.
- Attach strain/stress counts to landmark marker artists for Plotly hover,
  regardless of whether SD bars are shown. Also expose them on group-review
  aligned mean markers. Preserve existing Curve checks count columns.
- Display-only change: no alterations to eligibility, calculations, curve
  geometry, error bars, saved definitions or property/shape populations.
- Verification: eight new display/hover tests and two existing population/
  unchanged-shape regression tests passed using synthetic data only. No
  research plots/tables regenerated and no workbench server started.
- WH simplification follow-up: all nine updated count/hover tests passed,
  covering equal/split/legacy populations and the WH comparison legend in
  static and Plotly views, with and without individuals. Synthetic data only.

## Change notes — 2026-10-19

### Reproducible Mac Dock launcher — implemented

- Track the native launcher/live-log source, generic bundle metadata and icon.
  Keep machine-specific launcher/environment paths out of shared source; fill
  them in only when building the local app. Ignore built apps and runtime logs.
- Mac Setup attempts app installation after successful Python setup. Add a
  separate Install_Tensile_Workbench_App.command to rebuild/update the app
  without installing dependencies, starting servers or reading research data.
- Build on macOS 13+ for the current Mac architecture using Apple Command Line
  Tools/Xcode. Missing tools do not invalidate successful Python setup; explain
  installation and retain the existing Terminal launcher as a fallback.
- Install under the current user's Applications folder, preserve the app
  directory for Dock references, refuse running/unrecognised app replacements,
  back up old Contents and roll back failed replacement. Remove temporary
  compilation caches. Preserve data, environments and private settings.
- Retain the launcher controls, owned-process shutdown and in-app live log
  (auto-scroll toggle, jump to latest, copying and bounded recent text).
- Document installation, Dock usage, updates, moving the checkout and custom
  environment paths. Windows setup/launch remains unchanged.
- Verification: ten focused installer tests and two existing shell-wrapper
  tests passed. Native Apple Silicon compilation, local installation and
  signature verification succeeded; the temporary compiler cache was removed.
  No server launch, research plots or table generation. Intel compilation and
  interactive runtime testing remain unverified.

## Change notes — 2026-10-09

### Strength–EL mean populations — implemented, not runtime-tested

- Add **Group means** to each YS–EL / UTS–EL plot's Settings, independently
  persisted per graph: all eligible values per property (default), consistent
  with summary-table means, or paired specimens. Apply the default to fresh
  graphs and missing settings; preserve explicit saved choices. Update the
  starter definitions, renderer/UI fallbacks and export documentation together.
- Remove the README's B-number naming reference; describe arbitrary sample
  names and the new scatter default for external users.
- Keep individual dots paired in both modes. Independent means use each axis's
  own count and sample SD; omit that axis's SD below n=2, and omit the group
  marker if either coordinate has no eligible values. Show separate counts.
- Apply identically to static/Plotly and with/without-individuals views; preserve
  shared axis limits. Update omission warnings, export provenance and guide.
- Leave tables, landmark anchors and exclusions unchanged. Add regression
  coverage for differing populations, SDs, empty/disjoint populations, plot
  caching, settings persistence and exports. Source review only; no tests run
  or research plots/tables generated.

### Stable sizing, loading feedback and comparison identities — implemented, not runtime-tested

- Replace intrinsic table/plot width measurement with an explicit **Page width**
  selector (default 1600 px, capped to the viewport). Remember the selection in
  browser storage for this app address. Loading, clearing and switching samples
  must never change the preferred page width; wide tables scroll locally.
- Give the outer Analysis / Saved specimen overrides tabs content-sized labels;
  retain horizontal navigation scrolling for narrow windows. Follow-up: increase
  selector specificity above ipywidgets' fixed-width tab and clipping rules so
  the full label fits regardless of stylesheet load order; inner tabs unchanged.
- Add a shared loading overlay for long UI operations: folder changes, data
  reloads, property/plot calculation, inspector previews, comparisons, group
  review, move checks and exports. Use nested exception-safe scopes; lock
  pointer/keyboard interaction while active and restore previous focus/state.
  Delay the visible spinner briefly to avoid flicker for quick actions. Do not
  alter measurement calculations or generate outputs merely to show activity.
- Use formal sample-group names in Calc–Instron chart ticks/hover, ignoring
  publication aliases. Preserve full internal IDs for grouping and leave
  publication labels and comparison numbers unchanged.
- Source review only; no tests, app launch or research outputs generated.

### Nested groups and move review — implemented, runtime verification deferred

- Discover/select sample groups in arbitrarily nested organisational folders.
  Preserve full relative paths as identities, but default publication labels to
  the final group name; retain explicit custom labels.
- Require approval for content-verified moves before transferring saved settings.
  For deliberately removed groups, a compact **Forget group** button opens a
  confirmation and clears references, overrides and tracking without a deletion
  log. Never delete source data or exports.
- Keep page width stable across specimen-table tabs; wide tables scroll within
  their panel rather than expanding the page.

### Saved specimen overrides page — implemented, runtime verification deferred

- Show current overrides across all specimens and graphs, including unavailable
  data, independently of the current graph selection. This is a settings view,
  not an event/history log.
- One row per override: group, specimen, type, global/graph scope, setting,
  reason, active/disabled status and data availability. Search and filter rows.
- Provide selection tickboxes, select/clear visible selection, and bulk Disable,
  Enable and Remove actions. Disable must retain values while preventing their
  use in calculations; Remove requires confirmation and restores inheritance or
  automatic behaviour. Never modify raw data.
- Persist disabled settings in the ignored personal project file; cover move
  migration and forgetting as well as cache invalidation and refreshed UI.
- Keep graph-wide colour/gauge settings in their existing editors.
- Add a top-level **Saved specimen overrides** page beside **Analysis**. Opening
  it reads settings and cached identities only, without processing specimen data.
  Refresh on entry; clearly distinguish unavailable data and CSV-name fallbacks.
- Disabled entries are moved out of active maps into a per-scope
  `disabled_specimen_overrides` mapping. Existing calculations, tables and exports
  therefore see only active policies; re-enabling preserves the original values
  and source fingerprint. A new explicit edit replaces any parked old setting.
- Confirm bulk removal, reject stale selections/conflicting re-enables, use the
  existing atomic save, and clear stale previews after changes. Do not trigger
  plotting or export from the settings page, even with live preview enabled.
- Do not regenerate research outputs or run tests under the current instruction.

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
