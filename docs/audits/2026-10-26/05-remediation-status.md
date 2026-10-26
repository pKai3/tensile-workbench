# Audit remediation status — 26 October 2026

This is the implementation record following documents 01–04. The received PDFs
remain unchanged. Research data, personal settings, prior exports and the separate
OneDrive installation were not modified.

| Finding | Resolution |
| --- | --- |
| C1 — accidental group pooling | Nested groups remain separate despite stray parent files or empty export folders. Boundary notices explain the ambiguity. An explicit `.tensile-group` marker confirms intentionally combined runs; summary searches respect discovered boundaries. |
| C2 — duplicate exports | Content/export-row/summary-row collisions form connected review sets. Multiple included candidates contribute no results until Data use retains one. No source deletion or arbitrary first-file choice. |
| C3 — false sudden fracture | A single decrement must pass the five-times comparison, 5% of peak, twelve noise units and existing recovery checks. A later below-2% reading cannot waive these requirements. The multi-reading collapse path remains separate. |
| C4 — elastic fit in plastic region | Starting fit fractions are checked for slope stability; higher, lower and shorter ranges are searched. The initial downward-only search and rigid rejection thresholds were corrected after real-data review (see follow-up below). Insufficient/unstable data still yields unavailable automatic modulus/YS and review guidance. Manual fits remain available. |
| C5 — percent/fraction scaling | Explicit header/units-row conversion replaces magnitude guessing. Missing/conflicting units require correction. |
| C6 — stress units and true channels | Recognised units convert to MPa; true-only stress/strain is rejected. Prefer a simultaneous engineering channel. Conversion metadata is exported. |
| C7 — unverified reference contamination | Failed name/UTS verification withholds all candidate reference values from statistics, gauge reconstruction and automatic Location. Candidate values and evidence remain inspectable; no numerical rematching. |
| C8 — Location inference | Audit records the label/token, effective value and source. Ambiguous treatment/date/repeat tokens and values above the group count produce soft notices. Explicit Location remains authoritative; build-wide numbering is allowed. |
| C9 — Excel population mismatch | Main Specimens property columns contain eligible values only. Raw specimen values is a separate inspection sheet. Mean, sample SD and n are regression-checked against Summary for every mode. |
| C10 — hidden import failures | Failed files remain visible by name/reason, even with zero loaded curves. Tests found, curves loaded, duplicate candidates and import issues are distinct; Excel retains the counts and issues. |

Additional fixes: shared reversal-preserving preparation, `Time (s)` parsing,
decimal-comma precision, unambiguous representative overrides, variable-draft
three-way merge, reload draft preservation, explicit invalid-count errors, and
hourly backup retention. Long exact-maximum plateaux receive a uniform-elongation
review notice; no smoothing silently changes UTS or its location.

## Verification

- The full synthetic test suite passes: **433 tests** at the verification run.
- C3 has an independent grid of **1,980** smooth failures spanning noise,
  quantisation, sampling density, tail curvature and random seeds, plus **60**
  abrupt controls. The expected original measurement is asserted, not merely a
  successful status. Existing brittle, progressive, gap and manual-override
  regressions also pass.
- Elastic checks use known modulus/offset yield with varied strength ratios and
  strain-sampled Ramberg–Osgood exponents. They require accurate supported fits or
  an explicit unresolved result where the sampled linear region is insufficient.
- Integration checks exercise actual session loading, reference gating, counts,
  duplicate resolution, reconstruction, exports and state persistence in temporary
  fixtures. Existing landmark population and manual-override controls remain covered.
- A separate browser session using synthetic files confirms that import errors are
  visible above the tables and duplicate checks appear above the inspector plot.
  Excluding the unwanted copy releases the retained specimen: four loaded rows,
  three included, and no remaining duplicate-review items. No research session or
  saved personal analysis was used for this check.

## Qualifications and remaining evidence limits

- The reply's `tensile_audit_repro.zip` was not supplied. These are independent
  fixtures; the auditor's exact scripts and recorded results have not been rerun.
- Current licensed ASTM/ISO clause wording, especially the five-times attribution,
  remains unverified. Definitive clause citations were removed. UI/docs describe
  application rules; an observed low-load threshold is not standards certification.
- Automatic endpoint and elastic selection remain heuristics. No algorithm can
  restore an unrecorded fracture or insufficiently sampled elastic region. Review
  and source-fingerprinted manual controls remain necessary.
- No new signal-smoothing definition of uniform elongation is imposed. A unique
  noisy maximum can still shift its strain; plateau warnings expose one identifiable
  ambiguity without altering the recorded peak.
- Local locks and digest checks protect local/visible changes, not simultaneous
  offline edits on separate cloud-synced computers. Use one active editor and allow
  sync to finish. Hourly backups improve recovery, not distributed coordination.
- The withdrawn pointwise `ddof=0` finding required no change: those callers do not
  publish that intermediate SD.

## Follow-up — real-data elastic-fit regression

The first elastic-fit remediation passed the idealised fixtures but rejected
89 of 185 locally available real curves in a read-only numerical check. Searching
only lower loads moved into seating/tracking variation, while R² ≥ 0.995 and 2.5%
half-slope agreement were too restrictive as universal acceptance conditions.

Version 2 also searches above the starting range and uses shorter windows where
seating and yielding leave a limited linear interval. It prefers the stricter
conditions, with a second supported tier allowing R² ≥ 0.98 and 5% half-slope
agreement. A substantially steeper supported region supersedes a low-stiffness
seating or plastic-hardening region. The actual chosen range and support tier are
auditable. Noise/quantisation, seating and short-elastic-region regression tests
supplement the original known-modulus and curved-plastic controls. Obtaining a
finite fit is not itself validation of its physical accuracy.

Follow-up verification: **441 tests pass**. Using identical preparation and
automatic settings on 185 local raw curves, v1 accepts 96; v2 resolves modulus and
YS for 184. No previously accepted curve becomes rejected. One curve still fails
the automatic checks and remains available for manual fitting. The numerical
comparison bypassed personal overrides and exclusions to compare the algorithms;
it did not save settings or regenerate research plots/tables. No raw research data
or per-specimen results are included in the repository.

## Follow-up — local slope bias despite a finite fit

Subsequent visual review found that v2 could prefer a narrow, steeper patch over
a broader, straighter loading trend. Its high local R² and similar half-window
slopes did not validate extrapolation outside that patch. The earlier 184/185
availability result therefore did not establish that those fits were accurate.

Version 3 also searches wider loading intervals. Before a short interval can
supersede a wider fit, it is checked against wider supported lines on its own
readings, with a residual allowance for measurement variation. Prefer broad
supported regions and permit one limited boundary refinement. Keep the ability
to identify a distinct short elastic region amid seating or linear plastic flow;
do not replace this with an unconditional widest-window rule. The guide records
the thresholds and limitations. Instron summaries do not supply the target slope.

Synthetic coverage now includes correlated tracking drift with known modulus and
yield, across three drift periods and four phases, plus a short noisy elastic
region. These checks detect the local-slope bias missed by the earlier independent
noise fixtures. Existing modulus/yield accuracy limits are preserved. Read-only
checks use the same local raw-curve cohort; no research plots/tables, personal
overrides or analysis definitions are regenerated.

Verification: **443 tests pass**. The 185-curve read-only check confirms broader
selected regions for the two reported examples. All return finite E/YS; that
availability result is not a physical calibration of the individual fits.

## Follow-up — seating exclusion and group visual review

Further user review identified fits influenced by initial settling and narrow
low-load intervals. Version 4 excludes readings below 10% UTS from automatic
fits, while retaining the measured data and unrestricted manual ranges. Broad
high-R² windows receive a scatter-dependent half-slope allowance to avoid
mistaking correlated tracking variation for a distinct, steeper elastic region.
The guide records the exact conditions and heuristic limits. If the elastic
region appears to lie entirely below the cutoff, automatic E/YS are withheld
with a manual-review explanation rather than replaced by a plastic slope.

The new Group yield fits view supports visual comparison of every specimen's
curve, selected interval, fitted line, offset YS and matched Instron YS, with R²
on each plot. R² is explicitly described as local agreement, not validation of
the elastic-region choice. Synthetic preview curves exercise UI states and are
not evidence of physical fit accuracy. Focused numerical checks also use the
user-reported raw curves without writing research outputs or personal state.

Verification: **452 tests pass**. Existing accuracy bounds are retained for
elastic regions above the new cutoff; below-cutoff tests now require explicit
rejection and check that manual fitting recovers the known properties. Real-data
checks cover 168 unambiguously located curves plus the specifically identified
example paths. The checks do not establish calibration or universal fit accuracy.
