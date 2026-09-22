"""Automatic, auditable load-history endpoints, independent of Instron EL."""
import numpy as np
import re

FRACTURE_METHOD = 'Acquisition-order endpoint selection (v8)'
ISO_DROP_RATIO = 5.0
ISO_CONFIRM_FRACTION = .02
ASTM_END_FRACTION = .10
# Implementation safeguards, not thresholds specified by ASTM or ISO.
NOISE_MULTIPLIER = 6.0
MAX_TIME_GAP_RATIO = 10.0
PARTIAL_DROP_MIN_FRACTION = .05
TERMINAL_LOAD_FRACTION = .50
TERMINAL_DECLINE_WINDOW = 8
RAPID_RATE_CONTRAST = 6.0
RAPID_BACKGROUND_READINGS = 8


def _strain_collapse_evidence(x, z, onset, end, noise):
    """Corroborate a time-rate jump with load loss per additional strain.

    Localised stretching can accelerate both strain and force loss in time
    without creating a sharp load/strain break. Compare the same original
    increments in strain space; a force fall at fixed/receding strain passes.
    Missing/flat pre-event strain cannot establish a background comparison.
    """
    before = max(0, onset - RAPID_BACKGROUND_READINGS)
    previous_x = x[before:onset + 1]
    event_x = x[onset:end + 1]
    evidence = {'checked': False, 'contrast': np.nan, 'supported': True}
    if (len(previous_x) < 2 or len(event_x) < 2
            or not np.isfinite(previous_x).all() or not np.isfinite(event_x).all()):
        return evidence
    tolerance = 64 * np.finfo(float).eps * max(1., np.max(np.abs(x[before:end + 1])))
    previous_extension = float(x[onset] - x[before])
    if previous_extension <= tolerance:
        return evidence
    event_extension = max(0., float(np.max(event_x) - x[onset]))
    previous_loss = max(abs(float(z[before] - z[onset])), NOISE_MULTIPLIER * noise,
                        64 * np.finfo(float).eps)
    if event_extension <= tolerance:
        contrast = np.inf
    else:
        contrast = (max(0., float(z[onset] - z[end])) / event_extension
                    / (previous_loss / previous_extension))
    return {'checked': True, 'contrast': contrast, 'supported': contrast > RAPID_RATE_CONTRAST}


def _multi_reading_drop(z, t, peak, noise, last_start, strain):
    """Find rapid loss spread over multiple readings, not a 5% single jump.

    Input is one uninterrupted acquisition segment. Windows establish sustained
    event magnitude; a local change in load/time rate locates the leading edge.
    Additional strain must also support a sharp load/strain transition, when
    a finite advancing pre-event strain baseline is available. This is a
    heuristic, separate from ISO's adjacent-reading comparison.
    """
    n = len(z)
    if n - peak < 3:
        return None
    dt = np.diff(t)
    rates = -np.diff(z) / dt
    minimum_loss = max(PARTIAL_DROP_MIN_FRACTION, 12 * noise)
    background = np.zeros_like(rates)
    for i in range(1, min(RAPID_BACKGROUND_READINGS, len(rates))):
        background[i] = float(np.median(np.abs(rates[:i])))
    if len(rates) > RAPID_BACKGROUND_READINGS:
        preceding = np.lib.stride_tricks.sliding_window_view(rates, RAPID_BACKGROUND_READINGS)
        background[RAPID_BACKGROUND_READINGS:] = np.median(np.abs(preceding[:-1]), axis=1)
    abrupt = rates > RAPID_RATE_CONTRAST * background + NOISE_MULTIPLIER * noise / dt
    # Several successive increments can remain above the old background. They
    # are one leading edge, not competing later onsets inside the same fall.
    leading_edges = abrupt & ~np.r_[False, abrupt[:-1]]
    edge_counts = np.r_[0, np.cumsum(leading_edges)]
    # Three recovered readings reject an excursion; an isolated noisy rebound
    # does not erase an otherwise sustained collapse.
    min3 = np.minimum(np.minimum(z[:-2], z[1:-1]), z[2:])
    recovered = np.r_[np.maximum.accumulate(min3[::-1])[::-1], -np.inf, -np.inf]
    sums = np.r_[0., np.cumsum(z)]
    largest = min(512, n - peak - 1, max(4, int(np.ceil(.02 * n))))
    widths = [1]
    while widths[-1] < largest:
        widths.append(min(2 * widths[-1], largest))
    candidates = []
    for width in widths:
        starts = np.arange(peak, min(last_start, n - width))
        if not len(starts):
            continue
        stops = starts + width
        previous = np.maximum(0, starts - max(RAPID_BACKGROUND_READINGS, width))
        previous_span = t[starts] - t[previous]
        previous_rate = np.divide(z[previous] - z[starts], previous_span,
                                  out=np.zeros(len(starts)), where=previous_span > 0)
        loss = z[starts] - z[stops]
        rate = loss / (t[stops] - t[starts])
        follow_end = np.minimum(n, stops + max(3, width))
        following = (sums[follow_end] - sums[stops]) / (follow_end - stops)
        eligible = ((loss >= minimum_loss)
                    & (rate > RAPID_RATE_CONTRAST * np.maximum(0., previous_rate))
                    & (edge_counts[stops] > edge_counts[starts])
                    & (following < z[starts] - .6 * loss)
                    & (recovered[stops] < z[starts] - .5 * loss))
        choices = np.flatnonzero(eligible)
        # Bounded work per window on long CSVs; favour the largest event losses.
        if len(choices) > 32:
            choices = choices[np.argpartition(loss[choices], -32)[-32:]]
        for choice in choices:
            left, right = int(starts[choice]), int(stops[choice])
            seed = left + int(np.argmax(rates[left:right]))
            # An accelerating collapse starts slower than its fastest later
            # increment. The edge has already passed the local contrast/noise
            # check; imposing a fraction of the later maximum discards valid
            # onsets, especially when acquisition accelerates during the fall.
            edges = np.flatnonzero(leading_edges[left:seed + 1])
            if not len(edges):
                continue
            onset = left + int(edges[0])
            # A gradual accelerating lead-in can keep the rolling-background
            # test true through a later, distinct collapse. Look for a sharper
            # change *within* that run using consecutive time-normalised rates.
            # Keep the first increment of the final connected jump cluster,
            # never the fastest increment inside the fall. This also tolerates
            # an acquisition-rate change without treating it as a load event.
            ids = np.arange(max(1, onset), seed + 1)
            sharp = ((rates[ids] > RAPID_RATE_CONTRAST * np.abs(rates[ids - 1])
                      + NOISE_MULTIPLIER * noise / dt[ids]) & abrupt[ids])
            sharp_starts = ids[sharp & ~np.r_[False, sharp[:-1]]]
            if len(sharp_starts):
                onset = int(sharp_starts[-1])
            if onset >= last_start:
                continue
            event_loss = float(z[onset] - following[choice])
            if event_loss < minimum_loss or recovered[right] >= z[onset] - .5 * event_loss:
                continue
            strain_evidence = _strain_collapse_evidence(strain, z, onset, right, noise)
            if not strain_evidence['supported']:
                continue
            candidates.append({'onset': onset, 'end': right, 'window': width,
                               'loss': event_loss, 'rate': float(rates[seed]),
                               'onset_rate': float(rates[onset]), 'background_rate': float(background[onset]),
                               'strain_check': strain_evidence['checked'],
                               'strain_rate_contrast': strain_evidence['contrast']})
    return max(candidates, key=lambda c: (c['loss'], c['rate'], c['onset'])) if candidates else None


def endpoint_available(endpoint):
    """Detected onsets and review-flagged terminal estimates are both usable."""
    return endpoint['status'] in ('Detected', 'Estimated', 'Manual')


def validate_failure_override(override, *, saved=False):
    """A manual endpoint is an original measurement, never an invented stress."""
    if not isinstance(override, dict):
        raise ValueError('Failure EL override must specify a measurement row.')
    row = override.get('row')
    if isinstance(row, bool) or not isinstance(row, int) or row < 1:
        raise ValueError('Failure EL requires a positive original measurement row number.')
    if saved:
        if not isinstance(override.get('source_sha256'), str) or not re.fullmatch('[0-9a-f]{64}', override['source_sha256']):
            raise ValueError('Saved failure EL override requires a source fingerprint.')
        if not isinstance(override.get('reason'), str) or not override['reason'].strip() or len(override['reason']) > 2000:
            raise ValueError('Enter a short reason for the EL override (up to 2000 characters).')
        if not isinstance(override.get('saved_at'), str) or not override['saved_at']:
            raise ValueError('Saved failure EL override requires a timestamp.')
        if not isinstance(override.get('automatic_snapshot'), dict):
            raise ValueError('Saved failure EL override requires its automatic-result snapshot.')
    return override


def failure_measurements(record):
    """Eligible original rows after the recorded force/stress peaks, plus X/Y."""
    record = record.get('_measured_record', record)
    acquisition = record.get('_acquisition', {})
    x = np.asarray(acquisition.get('strain', []), float)
    y = np.asarray(acquisition.get('stress', []), float)
    if not len(x) or y.shape != x.shape or not np.isfinite(y).any():
        raise ValueError('Original acquisition strain/stress readings are required for an EL override.')
    stress_peak = int(np.nanargmax(y))
    force_peak = acquisition.get('peak')
    peak = max(stress_peak, int(force_peak) if force_peak is not None else stress_peak)
    valid = np.isfinite(x) & np.isfinite(y) & (x > 0) & (y >= 0)
    valid[:peak + 1] = False
    if np.isfinite(x[stress_peak]):
        valid &= x > x[stress_peak]
    if 0 <= peak < len(x) and np.isfinite(x[peak]):
        valid &= x >= x[peak]
    ids = np.flatnonzero(valid)
    if not len(ids):
        raise ValueError('No usable post-peak measurement is available for a failure EL override.')
    return ids, x, y


def failure_row_for_strain(record, strain):
    """Snap a numeric EL request to a measured post-peak point; never extrapolate."""
    ids, x, _ = failure_measurements(record)
    if not np.isfinite(strain) or not np.min(x[ids]) <= strain <= np.max(x[ids]):
        raise ValueError(f'EL must lie within the recorded post-peak range ({np.min(x[ids]):.5f}–{np.max(x[ids]):.5f}%).')
    distances = np.abs(x[ids] - strain)
    # Equal strains can have different stress/time. Prefer the later row; the
    # user can choose a different row directly or by clicking the original trace.
    return int(ids[np.flatnonzero(distances == distances.min())[-1]]) + 1


def manual_failure_endpoint(record, override):
    validate_failure_override(override)
    ids, x, y = failure_measurements(record)
    row = override['row'] - 1
    if row not in ids:
        raise ValueError('Choose a finite post-peak strain/stress measurement for failure EL.')
    clock = np.asarray(record.get('_acquisition', {}).get('time', []), float)
    return {'status': 'Manual', 'reason': '', 'method': FRACTURE_METHOD + ' · manual row selection',
            'strain_pct': float(x[row]), 'stress_mpa': float(y[row]), 'row_before': row + 1,
            'row_after': row + 2 if row + 1 < len(x) else np.nan, 'fraction': 0.,
            'time_s': float(clock[row]) if clock.shape == x.shape and np.isfinite(clock[row]) else np.nan,
            'endpoint_kind': 'Manual original measurement', 'review_required': False,
            'load_basis': 'Original measured stress', 'rate_basis': 'Manual measurement-row selection',
            'review_reason': '', 'notes': 'User-selected endpoint; automatic result retained in the audit.',
            'override_status': 'Applied'}


def prepared_points(record):
    """Finite, strain-sorted points; highest stress at duplicate strain; source IDs."""
    x = np.asarray(record.get('raw_strain_pct', record['strain_pct']), dtype=float)
    y = np.asarray(record.get('raw_stress_mpa', record['stress_mpa']), dtype=float)
    ids = np.asarray(record.get('_measurement_indices', np.full(len(x), -1)), dtype=int)
    valid = np.isfinite(x) & np.isfinite(y)
    x, y, ids = x[valid], y[valid], ids[valid]
    order = np.argsort(x, kind='stable')
    x, y, ids = x[order], y[order], ids[order]
    _, starts, counts = np.unique(x, return_index=True, return_counts=True)
    # Vectorised to avoid a Python loop per acquired point during table loading.
    if not len(starts):
        return x, y, ids
    maxima = np.maximum.reduceat(y, starts)
    candidates = np.where(y == np.repeat(maxima, counts), np.arange(len(y)), len(y))
    selected = np.minimum.reduceat(candidates, starts)
    return x[selected], y[selected], ids[selected]


def detect_drop_onset(strain, stress, slope_fraction=None, *, force=None, time=None):
    """Select a measured endpoint, distinguishing evidence from confirmation.

    ISO 6892-1:2019 informative A.3.6 supplies the >5x / <2% criterion;
    ASTM E8/E8M-25 7.11.3.4 supplies the no-sudden-drop 10% criterion.
    Exports may end before either threshold. Abrupt loss, including collapse
    spread over several readings, can then supply a detected pre-drop
    endpoint; progressive terminal unloading can supply a terminal estimate.
    Algorithmic detection is separate from ISO confirmation. Missing 2%
    confirmation alone is not an endpoint-review failure.
    The combined policy and safeguards are not a standards-compliance claim.
    No smoothing, resampling, strain sorting, interpolation or Instron EL input.
    slope_fraction remains accepted for legacy callers but is not used.
    """
    result = {'status': 'Not detected', 'reason': 'No supported load-history endpoint found',
              'method': FRACTURE_METHOD, 'strain_pct': np.nan, 'stress_mpa': np.nan,
              'row_before': np.nan, 'row_after': np.nan, 'fraction': np.nan, 'time_s': np.nan,
              'notes': '', 'criterion': '', 'iso_drop_ratio': ISO_DROP_RATIO,
              'iso_confirm_fraction': ISO_CONFIRM_FRACTION, 'astm_end_fraction': ASTM_END_FRACTION,
              'endpoint_kind': '', 'review_required': False, 'review_reason': '',
              'iso_confirmation_observed': False}
    x, y = np.asarray(strain, float), np.asarray(stress, float)
    if x.ndim != 1 or y.shape != x.shape:
        result['reason'] = 'Strain and stress arrays are not aligned'
        return result
    load = np.asarray(force, float) if force is not None else y
    if load.shape != x.shape:
        result['reason'] = 'Load channel is not aligned with strain/stress'
        return result
    ids = np.flatnonzero(np.isfinite(load))
    if len(ids) < 3:
        result['reason'] = 'Fewer than three finite load readings'
        return result
    z = load[ids]
    peak = int(np.argmax(z))
    maximum = float(z[peak])
    if maximum <= 0 or peak == len(z) - 1:
        result['reason'] = 'No positive load peak followed by recorded unloading'
        return result
    z = z / maximum
    n = len(z)
    clock = np.asarray(time, float) if time is not None else np.array([])
    clock_ok = (clock.shape == x.shape and np.isfinite(clock[ids]).all()
                and np.all(np.diff(clock[ids]) > 0))
    result['rate_basis'] = 'Consecutive original readings (not a time derivative)'
    contiguous = np.diff(ids) == 1
    if clock_ok:
        dt = np.diff(clock[ids])
        contiguous &= dt <= MAX_TIME_GAP_RATIO * np.median(dt)
    gaps = np.r_[0, np.cumsum(~contiguous)]
    # Do not silently skip missing load rows or a major time gap after peak.
    interrupted = np.flatnonzero(gaps[peak:] != gaps[peak])
    segment_end = peak + int(interrupted[0]) if len(interrupted) else n
    crossing10 = np.flatnonzero(z[peak + 1:segment_end] < ASTM_END_FRACTION) + peak + 1
    crossing2 = np.flatnonzero(z[peak + 1:segment_end] < ISO_CONFIRM_FRACTION) + peak + 1
    first10 = int(crossing10[0]) if len(crossing10) else None
    first2 = int(crossing2[0]) if len(crossing2) else None
    # Robust noise estimate from contiguous three-reading differences only.
    second = np.diff(z, n=2)[contiguous[:-1] & contiguous[1:]]
    noise = (float(1.4826 * np.median(np.abs(second - np.median(second))) / np.sqrt(6))
             if len(second) >= 5 else 0.)
    floor = max(NOISE_MULTIPLIER * noise, 64 * np.finfo(float).eps)
    drops = -np.diff(z)
    # Stop at the first 10% crossing: later fluctuations in the unloaded tail
    # must not replace the main event. Confirmation may occur later, at <2%.
    starts = np.arange(max(peak, 1), first10 if first10 is not None else segment_end - 1)
    previous = np.abs(drops[starts - 1])
    eligible = ((gaps[starts - 1] == gaps[starts + 1])
                & (drops[starts] > ISO_DROP_RATIO * previous) & (drops[starts] > floor))
    possible = starts[eligible]
    confirmation = first2 if first2 is not None else segment_end - 1
    future_max = np.maximum.accumulate(z[:confirmation + 1][::-1])[::-1]
    # Reject transient pings that subsequently recover more than half their
    # loss, allowing three noise units. This safeguard is not an ISO clause.
    possible = possible[future_max[possible + 1] <= z[possible] - .5 * drops[possible] + 3 * noise]
    notes = []
    if not clock_ok:
        notes.append('No complete increasing time channel; original measurement order used.')
    result.update(noise_floor_fraction=floor, candidate_count=int(len(possible)),
                  ten_percent_row=int(ids[first10]) + 1 if first10 is not None else np.nan,
                  confirmation_row=int(ids[first2]) + 1 if first2 is not None else np.nan)
    # A standards confirmation threshold is not a prerequisite for every usable
    # endpoint. A truncated sudden drop needs substantial loss, not just a large
    # ratio caused by a nearly-zero preceding increment.
    partial = possible[drops[possible] >= max(PARTIAL_DROP_MIN_FRACTION, 12 * noise)]
    # Preserve a separate event-level detector: highly sampled collapses often
    # have no individual decrement as large as 5% of peak. Never confuse that
    # sampling artefact with evidence for a purely progressive terminal event.
    rapid = None
    if not ((len(possible) and first2 is not None) or len(partial)):
        segment_time = clock[ids[:segment_end]] if clock_ok else ids[:segment_end].astype(float)
        rapid = _multi_reading_drop(z[:segment_end], segment_time, peak, noise,
                                    first10 if first10 is not None else segment_end - 1,
                                    x[ids[:segment_end]])
    selected_status = 'Detected'
    if (len(possible) and first2 is not None) or len(partial):
        # Largest supported consecutive loss, with the later reading breaking
        # exact ties. Do not retreat backwards through ordinary necking.
        confirmed = first2 is not None
        candidates = possible if confirmed else partial
        onset = max(map(int, candidates), key=lambda i: (drops[i], i))
        prior = float(abs(drops[onset - 1]))
        result.update(criterion=('ISO-style sudden drop (>5×; confirmed below 2%)' if confirmed else
                                 'Substantial sudden drop; below-2% confirmation not recorded'),
                      endpoint_kind='Before confirmed sudden drop' if confirmed else 'Before supported sudden drop',
                      iso_confirmation_observed=confirmed,
                      consecutive_drop_ratio=float(drops[onset] / prior) if prior else np.nan,
                      previous_change_fraction=prior)
        if not confirmed:
            notes.append('Pre-drop measurement retained despite incomplete unloading record; not an ISO-confirmed endpoint.')
        if prior == 0:
            notes.append('The preceding force change is zero; the ratio is undefined. The positive drop exceeds the noise floor.')
    elif rapid is not None:
        onset = rapid['onset']
        result.update(criterion='Rapid multi-reading load loss (heuristic)',
                      endpoint_kind='Before rapid multi-reading collapse',
                      event_loss_fraction=rapid['loss'], event_window_rows=rapid['window'],
                      event_end_row=int(ids[rapid['end']]) + 1,
                      event_onset_rate=rapid['onset_rate'], event_background_rate=rapid['background_rate'],
                      event_strain_check=rapid['strain_check'],
                      event_strain_rate_contrast=rapid['strain_rate_contrast'],
                      event_rate_basis='Acquisition time (s)' if clock_ok else 'Original measurement row')
        notes.append('Sustained load loss across multiple readings; selected its local rapid-change edge, '
                     'not the final reading or an earlier necking setback. '
                     'The event-level 5% loss check is not a single-reading requirement or an ISO clause. '
                     'Algorithmically detected; this heuristic is not ISO confirmation.')
        if rapid['strain_check']:
            notes.append('Additional-strain check supports a sharp load/strain transition, '
                         'not only faster progressive unloading in time.')
        else:
            result.update(review_required=True, review_reason=(
                'EL collapse detected from load history; no usable advancing strain baseline '
                'for the strain-shape check. Review Failure detail.'))
    elif first10 is not None:
        onset = first10 - 1
        result.update(criterion='ASTM-style 10% of peak crossing',
                      endpoint_kind='Before force falls below 10% of peak')
        if len(possible):
            result.update(review_required=True, review_reason=(
                'EL uses the 10% crossing, but a sudden-drop candidate lacks below-2% confirmation. '
                'Review the endpoint.'))
        notes.append('No confirmed sudden drop; selected the reading immediately before the first below-10% reading.')
    else:
        # Preserve a supported terminal estimate for progressive failures whose
        # export stops above 10%. Never use the end of a plateau/rising curve or
        # stop at a gap and pretend that it was the end of the recorded test.
        end = n - 1
        recent = end - TERMINAL_DECLINE_WINDOW
        terminal_supported = (
            segment_end == n and recent >= peak
            and 0 <= z[end] <= TERMINAL_LOAD_FRACTION
            and z[recent] - z[end] > max(6 * noise, .0001)
            and np.max(np.diff(z[recent:end + 1])) <= max(12 * noise, .02))
        if not terminal_supported:
            result['reason'] = 'No confirmed crossing, supported rapid collapse or terminal unloading'
            if segment_end < n:
                result['reason'] += '; acquisition gap prevents continuing the search'
            result['notes'] = ' '.join(notes + ['No unconditional final-reading fallback. Review or set a manual EL endpoint.'])
            return result
        onset = end
        selected_status = 'Estimated'
        result.update(criterion='Progressive terminal unloading; unconfirmed estimate',
                      endpoint_kind='Progressive load loss; final recorded measurement',
                      review_required=True, review_reason=(
                          'EL uses a terminal-unloading estimate; separation is not resolved in the export. '
                          'Review Failure detail.'))
        notes.append('Final recorded measurement used after substantial continuing unloading; neither 10% nor 2% was recorded.')
    row = int(ids[onset])
    next_row = int(ids[onset + 1]) if onset + 1 < n else None
    if not np.isfinite(x[row]) or not np.isfinite(y[row]):
        result['reason'] = 'Load criterion met, but the selected strain/stress reading is missing'
        return result
    if x[row] <= 0 or y[row] < 0 or (np.isfinite(x[ids[peak]]) and x[row] < x[ids[peak]]):
        result['reason'] = 'Load criterion met, but endpoint strain/stress is inconsistent; review tracking'
        return result
    if first10 is not None and np.any(z[first10 + 1:segment_end] > ASTM_END_FRACTION + floor):
        result.update(review_required=True, review_reason=(
            'Load recovers above 10% of peak after the crossing; review the selected EL endpoint.'))
    result.update(status=selected_status, reason='', strain_pct=float(x[row]), stress_mpa=float(y[row]),
                  row_before=row + 1, row_after=next_row + 1 if next_row is not None else np.nan, fraction=0.,
                  time_s=float(clock[row]) if clock.shape == x.shape and np.isfinite(clock[row]) else np.nan,
                  load_loss_fraction=float(drops[onset]) if next_row is not None else np.nan,
                  endpoint_load_fraction=float(z[onset]),
                  notes=' '.join(notes))
    return result


def automatic_fracture_endpoint(record):
    """Automatic result remains independent of saved manual endpoints."""
    if '_measured_record' in record:
        return automatic_fracture_endpoint(record['_measured_record'])
    if record.get('_fracture_detection', {}).get('method') != FRACTURE_METHOD:
        acquisition = record.get('_acquisition', {})
        if 'strain' in acquisition and 'stress' in acquisition:
            force = acquisition.get('force') if acquisition.get('force_channel') else None
            result = detect_drop_onset(acquisition['strain'], acquisition['stress'],
                                       force=force, time=acquisition.get('time'))
            result['load_basis'] = 'Force' if force is not None else 'Engineering stress (force proxy)'
        else:
            # Compatibility for in-memory records without acquisition metadata.
            # Supplied rows are all we have; never invent original row identities.
            x = record.get('raw_strain_pct', record['strain_pct'])
            y = record.get('raw_stress_mpa', record['stress_mpa'])
            result = detect_drop_onset(x, y)
            result['load_basis'] = 'Engineering stress; supplied row order'
            if endpoint_available(result):
                result['supplied_index'] = int(result['row_before']) - 1
                result.update(row_before=np.nan, row_after=np.nan)
        record['_fracture_detection'] = result
    return dict(record['_fracture_detection'])


def fracture_endpoint(record):
    """One effective endpoint for properties, curves and reconstruction."""
    if '_fracture' in record:
        return dict(record['_fracture'])
    if '_measured_record' in record:
        return fracture_endpoint(record['_measured_record'])
    automatic = automatic_fracture_endpoint(record)
    saved = record.get('_failure_override')
    if not saved:
        return {**automatic, 'override_status': 'None'}
    if saved.get('source_sha256') != record.get('source_sha256'):
        issue = 'EL override is stale: source data changed; automatic selection used. Review or restore automatic.'
        status = 'Stale — not applied'
    else:
        try:
            return manual_failure_endpoint(record, saved)
        except ValueError as error:
            issue = 'EL override not applied: ' + str(error)
            status = 'Invalid — not applied'
    return {**automatic, 'override_status': status, 'review_required': True,
            'review_reason': ' '.join(filter(None, [automatic.get('review_reason'), issue]))}


def fracture_curve(record):
    """Prepare only the selected prefix; never reintroduce discarded tail rows."""
    endpoint = fracture_endpoint(record)
    if not endpoint_available(endpoint):
        raise ValueError('CSV fracture not detected: ' + endpoint['reason'])
    if '_measured_record' in record:
        # A gauge-transformed view is already cut at the measured endpoint.
        x, y, ids = prepared_points(record)
    else:
        acquisition = record.get('_acquisition', {})
        if 'strain' in acquisition and np.isfinite(endpoint.get('row_before', np.nan)):
            stop = int(endpoint['row_before'])
            prefix = {'strain_pct': np.asarray(acquisition['strain'])[:stop],
                      'stress_mpa': np.asarray(acquisition['stress'])[:stop],
                      '_measurement_indices': np.arange(stop)}
        else:
            stop = endpoint.get('supplied_index', len(record['strain_pct']) - 1) + 1
            prefix = {'strain_pct': np.asarray(record.get('raw_strain_pct', record['strain_pct']))[:stop],
                      'stress_mpa': np.asarray(record.get('raw_stress_mpa', record['stress_mpa']))[:stop],
                      '_measurement_indices': np.full(stop, -1)}
        x, y, ids = prepared_points(prefix)
        starts = np.flatnonzero((x >= 0) & (y >= 0))
        if len(starts):
            x, y, ids = x[starts[0]:], y[starts[0]:], ids[starts[0]:]
    end = endpoint['strain_pct']
    if not len(x) or not x[0] < end <= x[-1]:
        raise ValueError('Detected fracture endpoint is outside the analysis curve')
    before = x < end
    exact = np.flatnonzero(x == end)
    end_id = (int(endpoint['row_before']) - 1 if np.isfinite(endpoint.get('row_before', np.nan))
              else int(ids[exact[0]]) if len(exact) else -1)
    return (np.r_[x[before], end], np.r_[y[before], endpoint['stress_mpa']],
            np.r_[ids[before], end_id])


def fracture_audit(record):
    end = fracture_endpoint(record)
    measured = record.get('_measured_record', record)
    automatic = automatic_fracture_endpoint(measured)
    saved = measured.get('_failure_override') or {}
    return {'Fracture detection status': end['status'], 'Fracture detection reason': end['reason'],
            'EL selection': ('Manual' if end['status'] == 'Manual' else
                             end.get('override_status') if saved else 'Automatic'),
            'EL override status': end.get('override_status', 'None'),
            'EL override reason': saved.get('reason', ''), 'EL override saved at': saved.get('saved_at', ''),
            'EL override measurement row': saved.get('row', np.nan),
            'Automatic EL (%)': automatic['strain_pct'], 'Automatic EL status': automatic['status'],
            'Automatic EL method': automatic['method'],
            'Automatic EL criterion': automatic.get('criterion', ''),
            'Fracture EL method': end['method'],
            'Fracture criterion': 'Manual measurement selection' if end['status'] == 'Manual' else end.get('criterion', ''),
            'Fracture endpoint kind': end.get('endpoint_kind', ''),
            'Fracture review required': end.get('review_required', False),
            'Fracture review reason': end.get('review_reason', ''),
            'Fracture ISO-style confirmation observed': end.get('iso_confirmation_observed', False),
            'Fracture endpoint load (% of peak)': 100 * end.get('endpoint_load_fraction', np.nan),
            'Fracture sudden-drop ratio threshold': ISO_DROP_RATIO,
            'Fracture sudden-drop confirmation threshold (% of peak)': 100 * ISO_CONFIRM_FRACTION,
            'Fracture gradual threshold (% of peak)': 100 * ASTM_END_FRACTION,
            'Fracture observed consecutive-drop ratio': end.get('consecutive_drop_ratio', np.nan),
            'Fracture preceding force change (% of peak)': 100 * end.get('previous_change_fraction', np.nan),
            'Fracture confirmation row (1-based)': end.get('confirmation_row', np.nan),
            'Fracture below-10% row (1-based)': end.get('ten_percent_row', np.nan),
            'Fracture qualifying sudden-drop candidates': end.get('candidate_count', np.nan),
            'Fracture noise floor (% of peak)': 100 * end.get('noise_floor_fraction', np.nan),
            'Fracture unconfirmed sudden-drop minimum (% of peak)': 100 * PARTIAL_DROP_MIN_FRACTION,
            'Fracture terminal estimate load ceiling (% of peak)': 100 * TERMINAL_LOAD_FRACTION,
            'Fracture terminal decline window (rows)': TERMINAL_DECLINE_WINDOW,
            'Fracture multi-reading event loss (% of peak)': 100 * end.get('event_loss_fraction', np.nan),
            'Fracture multi-reading event window (rows)': end.get('event_window_rows', np.nan),
            'Fracture multi-reading event end row (1-based)': end.get('event_end_row', np.nan),
            'Fracture event onset rate (fraction of peak / rate basis)': end.get('event_onset_rate', np.nan),
            'Fracture event background rate (fraction of peak / rate basis)': end.get('event_background_rate', np.nan),
            'Fracture event rate basis': end.get('event_rate_basis', ''),
            'Fracture event rate contrast threshold': RAPID_RATE_CONTRAST,
            'Fracture strain-shape check': ('Supported' if end['event_strain_check'] else 'Unavailable')
                                           if 'event_strain_check' in end else 'Not applicable',
            'Fracture load/strain rate contrast': end.get('event_strain_rate_contrast', np.nan),
            'Fracture load signal': end.get('load_basis', ''),
            'Fracture rate basis': end.get('rate_basis', ''),
            'Fracture detected load loss (%)': 100 * end.get('load_loss_fraction', np.nan),
            'Fracture detection notes': end.get('notes', ''),
            'Fracture endpoint stress (MPa)': end['stress_mpa'],
            'Fracture bracket first row (1-based)': end.get('row_before', np.nan),
            'Fracture bracket second row (1-based)': end.get('row_after', np.nan),
            'Fracture interpolation fraction': end.get('fraction', np.nan),
            'Fracture endpoint time (s)': end.get('time_s', np.nan)}
