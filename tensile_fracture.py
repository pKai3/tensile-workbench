"""Automatic, auditable load-history endpoints, independent of Instron EL."""
import numpy as np
import re

FRACTURE_METHOD = 'Acquisition-order endpoint selection (v3)'
MIN_DROP_FRACTION = .05       # Minimum sustained loss relative to maximum load.
DECLINE_CONTRAST = 6.0       # Collapse must be faster than preceding necking.
ONSET_RATE_FRACTION = .05    # Refine locally, relative to the selected rapid drop.
LOCAL_RATE_WINDOW = 8       # Local abruptness check, not a specimen-type selector.
TERMINAL_LOAD_FRACTION = .50  # Support a terminal estimate only after substantial unloading.


def endpoint_available(endpoint):
    """Estimated terminal endpoints are usable, but must remain review-flagged."""
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


def _terminal_endpoint(result, x, y, z, ids, clock, clock_ok, peak, noise, gaps, recovered):
    """Use a supported terminal reading, not maximum strain or a fitted onset.

    No abrupt break was resolved. A substantial, ongoing, non-recovering load
    loss can support a provisional endpoint. Remove a sustained near-zero-load
    tail if present, but do not claim that this identifies physical separation.
    """
    n = len(z)
    floor = max(.001, 12 * noise)
    end = n - 1
    kind = 'Progressive load loss; final recorded measurement'
    # Three near-zero readings plus no sustained recovery: exclude the trailing
    # unloaded acquisition, including later strain drift. Do not bridge gaps.
    low3 = np.maximum(np.maximum(z[:-2], z[1:-1]), z[2:]) <= floor
    zero_starts = np.flatnonzero(low3 & (recovered[:-2] <= floor))
    for start in zero_starts:
        if start > peak and gaps[start + 2] == gaps[start - 1]:
            end = int(start - 1)
            kind = 'Progressive load loss; before unloaded tail'
            break
    if end <= peak or end - peak < LOCAL_RATE_WINDOW:
        return result
    # A truncated plateau/ordinary necking trace does not get a terminal fallback.
    # These conservative evidence checks are heuristics, not a fracture standard.
    recent = end - LOCAL_RATE_WINDOW
    if (z[end] > TERMINAL_LOAD_FRACTION or z[end] < -floor
            or gaps[end] != gaps[peak]
            or z[recent] - z[end] <= max(6 * noise, .0001)
            or recovered[end] > z[end] + max(12 * noise, .02)):
        return result
    row = int(ids[end])
    if not np.isfinite(x[row]) or not np.isfinite(y[row]):
        result['reason'] = 'Terminal load loss found, but its strain/stress reading is missing'
        return result
    if np.isfinite(x[ids[peak]]) and x[row] <= x[ids[peak]]:
        result['reason'] = 'Terminal strain does not extend beyond peak-load strain; review tracking'
        return result
    reason = 'EL uses a terminal-load endpoint; physical separation is not resolved. Review the full curve.'
    result.update(status='Estimated', reason='', endpoint_kind=kind,
                  review_required=True, review_reason=reason,
                  strain_pct=float(x[row]), stress_mpa=float(y[row]), row_before=row + 1,
                  row_after=int(ids[end + 1]) + 1 if end + 1 < n else np.nan, fraction=0.,
                  time_s=float(clock[row]) if clock.shape == x.shape and np.isfinite(clock[row]) else np.nan,
                  load_loss_fraction=float(1 - z[end]), terminal_load_fraction=float(z[end]),
                  notes=('No distinct abrupt break; terminal estimate used. '
                         + ('Unloaded trailing readings excluded.' if end < n - 1 else
                            'Recording ends while carrying load; there may be no recorded separation.')
                         + ('' if clock_ok else ' No complete increasing time channel; original row order used.')))
    return result


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
    """Find a dominant, non-recovering rapid loss in the supplied row order.

    Never sort by strain, merge repeated strain values, or resample the drop.
    Multi-size windows locate the event; raw increments refine its onset.
    An abrupt event selects its last pre-collapse reading. If none is resolved,
    supported progressive terminal unloading can supply a review-flagged estimate.
    The legacy slope_fraction argument is accepted for old callers only; the
    old strain-slope threshold is no longer used. No Instron substitution.
    """
    result = {'status': 'Not detected', 'reason': 'No distinct sustained load collapse found',
              'method': FRACTURE_METHOD, 'strain_pct': np.nan, 'stress_mpa': np.nan,
              'row_before': np.nan, 'row_after': np.nan, 'fraction': np.nan, 'time_s': np.nan,
              'minimum_drop_fraction': MIN_DROP_FRACTION, 'decline_contrast': DECLINE_CONTRAST,
              'onset_rate_fraction': ONSET_RATE_FRACTION, 'notes': '',
              'endpoint_kind': '', 'review_required': False, 'review_reason': ''}
    x, y = np.asarray(strain, float), np.asarray(stress, float)
    if x.ndim != 1 or y.shape != x.shape:
        result['reason'] = 'Strain and stress arrays are not aligned'
        return result
    load = np.asarray(force, float) if force is not None else y
    if load.shape != x.shape:
        result['reason'] = 'Load channel is not aligned with strain/stress'
        return result
    ids = np.flatnonzero(np.isfinite(load))
    if len(ids) < 8:
        result['reason'] = 'Fewer than eight finite load readings'
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
    t = clock[ids] if clock_ok else ids.astype(float)
    result['rate_basis'] = 'Acquisition time (s)' if clock_ok else 'Original measurement row'
    dt = np.diff(t)
    contiguous = np.diff(ids) == 1
    if clock_ok:
        contiguous &= dt <= 10 * np.median(dt)
    gaps = np.r_[0, np.cumsum(~contiguous)]
    rates = -np.diff(z) / dt  # Positive means unloading, not work-hardening rate.
    second = np.diff(z, n=2)
    noise = float(1.4826 * np.median(np.abs(second - np.median(second))) / np.sqrt(6))
    minimum_loss = max(MIN_DROP_FRACTION, 12 * noise)
    local_background = np.zeros_like(rates)
    for count in range(1, min(LOCAL_RATE_WINDOW, len(rates))):
        local_background[count] = max(0., float(np.median(rates[:count])))
    if len(rates) > LOCAL_RATE_WINDOW:
        preceding = np.lib.stride_tricks.sliding_window_view(rates, LOCAL_RATE_WINDOW)
        local_background[LOCAL_RATE_WINDOW:] = np.maximum(0., np.median(preceding[:-1], axis=1))
    abrupt_steps = rates > DECLINE_CONTRAST * local_background + 6 * noise / np.median(dt)
    # A small spike within a broad decline is not itself the breaking event.
    # Require substantial loss close to the sharp step, not only over a long window.
    step_starts = np.arange(len(rates))
    abrupt_steps &= z[step_starts] - z[np.minimum(step_starts + LOCAL_RATE_WINDOW, n - 1)] >= minimum_loss
    # Three consecutive recovered readings reject transient pings. A single
    # isolated rebound is not allowed to decide the whole detection result.
    min3 = np.minimum(np.minimum(z[:-2], z[1:-1]), z[2:])
    recovered = np.r_[np.maximum.accumulate(min3[::-1])[::-1], -np.inf, -np.inf]
    sums = np.r_[0., np.cumsum(z)]
    largest_window = min(512, n - peak - 1, max(4, int(np.ceil(.02 * n))))
    windows = [1]
    while windows[-1] < largest_window:
        windows.append(min(2 * windows[-1], largest_window))
    candidates = {}
    for width in windows:
        starts = np.arange(peak, n - width)
        stops = starts + width
        previous = np.maximum(0, starts - max(8, width))
        previous_span = t[starts] - t[previous]
        previous_rate = np.divide(z[previous] - z[starts], previous_span,
                                  out=np.zeros(len(starts)), where=previous_span > 0)
        loss = z[starts] - z[stops]
        rate = loss / (t[stops] - t[starts])
        follow_end = np.minimum(n, stops + max(3, width))
        following = (sums[follow_end] - sums[stops]) / (follow_end - stops)
        eligible = ((loss >= minimum_loss) & (gaps[stops] == gaps[starts])
                    & (rate > DECLINE_CONTRAST * np.maximum(0., previous_rate))
                    & (following < z[starts] - .6 * loss)
                    & (recovered[stops] < z[starts] - .5 * loss))
        choices = np.flatnonzero(eligible)
        if len(choices) > 32:
            choices = choices[np.argpartition(loss[choices], -32)[-32:]]
        for choice in choices:
            left, right = int(starts[choice]), int(stops[choice])
            seed = left + int(np.argmax(rates[left:right]))
            # A long window can make progressive necking look like a sudden
            # break relative to a much earlier plateau. Demand local evidence
            # of abruptness too, rather than returning that early bend as EL.
            if not np.any(abrupt_steps[left:seed + 1] & (rates[left:seed + 1] >= .2 * rates[seed])):
                continue
            baseline = rates[max(0, left - max(8, width)):left]
            background = float(np.median(baseline)) if len(baseline) else 0.
            spread = float(1.4826 * np.median(np.abs(baseline - background))) if len(baseline) else 0.
            threshold = max(max(0., background) + 6 * spread,
                            max(0., background) + ONSET_RATE_FRACTION * max(0., rates[seed] - background))
            if rates[seed] <= threshold:
                continue
            onset = seed
            # Refine backwards only within the rapid decline, not all the way
            # through ordinary necking. No constant strain setback is applied.
            while onset > peak and contiguous[onset - 1] and rates[onset - 1] > threshold:
                onset -= 1
            actual_loss = float(z[onset] - following[choice])
            if actual_loss < minimum_loss or recovered[right] >= z[onset] - .5 * actual_loss:
                continue
            candidate = {'onset': onset, 'end': right, 'loss': actual_loss,
                         'rate': float(rates[seed]), 'threshold': float(threshold), 'window': width}
            previous_candidate = candidates.get(onset)
            if previous_candidate is None or actual_loss > previous_candidate['loss']:
                candidates[onset] = candidate
    if not candidates:
        return _terminal_endpoint(result, x, y, z, ids, clock, clock_ok,
                                  peak, noise, gaps, recovered)
    # Prefer the substantial persistent collapse over smaller earlier changes.
    # Later onset breaks equal-score ties, not the first qualifying bend.
    chosen = max(candidates.values(), key=lambda c: (c['loss'], c['rate'], c['onset']))
    onset = chosen['onset']
    row, next_row = int(ids[onset]), int(ids[onset + 1])
    if not np.isfinite(x[row]) or not np.isfinite(y[row]):
        result['reason'] = 'Load collapse found, but its pre-collapse strain/stress reading is missing'
        return result
    notes = []
    if n - chosen['end'] < 3:
        notes.append('Recording ends during the drop; limited post-drop confirmation.')
    if not clock_ok:
        notes.append('No complete increasing time channel; detection used original row order.')
    result.update(status='Detected', reason='', strain_pct=float(x[row]), stress_mpa=float(y[row]),
                  row_before=row + 1, row_after=next_row + 1, fraction=0.,
                  time_s=float(clock[row]) if clock.shape == x.shape and np.isfinite(clock[row]) else np.nan,
                  load_loss_fraction=chosen['loss'], rate_threshold=chosen['threshold'],
                  candidate_window_rows=chosen['window'], notes=' '.join(notes),
                  endpoint_kind='Abrupt load collapse; last pre-collapse measurement')
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
            'Fracture EL method': end['method'],
            'Fracture endpoint kind': end.get('endpoint_kind', ''),
            'Fracture review required': end.get('review_required', False),
            'Fracture review reason': end.get('review_reason', ''),
            'Fracture terminal load (% of peak)': 100 * end.get('terminal_load_fraction', np.nan),
            'Fracture terminal estimate load ceiling (% of peak)': 100 * TERMINAL_LOAD_FRACTION,
            'Fracture local abruptness window (rows)': LOCAL_RATE_WINDOW,
            'Fracture load signal': end.get('load_basis', ''),
            'Fracture rate basis': end.get('rate_basis', ''),
            'Fracture minimum load loss (%)': 100 * MIN_DROP_FRACTION,
            'Fracture detected load loss (%)': 100 * end.get('load_loss_fraction', np.nan),
            'Fracture decline contrast': DECLINE_CONTRAST,
            'Fracture onset rate fraction': ONSET_RATE_FRACTION,
            'Fracture rate threshold (fraction of peak / rate basis)': end.get('rate_threshold', np.nan),
            'Fracture candidate window (rows)': end.get('candidate_window_rows', np.nan),
            'Fracture detection notes': end.get('notes', ''),
            'Fracture endpoint stress (MPa)': end['stress_mpa'],
            'Fracture bracket first row (1-based)': end.get('row_before', np.nan),
            'Fracture bracket second row (1-based)': end.get('row_after', np.nan),
            'Fracture interpolation fraction': end.get('fraction', np.nan),
            'Fracture endpoint time (s)': end.get('time_s', np.nan)}
