"""One auditable acquisition-order collapse endpoint, independent of Instron EL."""
import numpy as np

FRACTURE_METHOD = 'Acquisition-order load collapse (v2); last pre-collapse measurement'
MIN_DROP_FRACTION = .05       # Minimum sustained loss relative to maximum load.
DECLINE_CONTRAST = 6.0       # Collapse must be faster than preceding necking.
ONSET_RATE_FRACTION = .05    # Refine locally, relative to the selected rapid drop.


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
    Multi-size windows locate the event; raw increments refine its onset. The
    returned point is an actual measurement immediately before rapid collapse.
    The legacy slope_fraction argument is accepted for old callers only; the
    old strain-slope threshold is no longer used. No terminal/Instron fallback.
    """
    result = {'status': 'Not detected', 'reason': 'No distinct sustained load collapse found',
              'method': FRACTURE_METHOD, 'strain_pct': np.nan, 'stress_mpa': np.nan,
              'row_before': np.nan, 'row_after': np.nan, 'fraction': np.nan, 'time_s': np.nan,
              'minimum_drop_fraction': MIN_DROP_FRACTION, 'decline_contrast': DECLINE_CONTRAST,
              'onset_rate_fraction': ONSET_RATE_FRACTION, 'notes': ''}
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
        return result
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
                  candidate_window_rows=chosen['window'], notes=' '.join(notes))
    return result


def fracture_endpoint(record):
    """Detect once on the full measured curve; never re-detect a reconstruction."""
    if '_fracture' in record:
        return dict(record['_fracture'])
    if '_measured_record' in record:
        return fracture_endpoint(record['_measured_record'])
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
            if result['status'] == 'Detected':
                result['supplied_index'] = int(result['row_before']) - 1
                result.update(row_before=np.nan, row_after=np.nan)
        record['_fracture_detection'] = result
    return dict(record['_fracture_detection'])


def fracture_curve(record):
    """Prepared pre-collapse rows only; do not reintroduce post-break reversals."""
    endpoint = fracture_endpoint(record)
    if endpoint['status'] != 'Detected':
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
    return {'Fracture detection status': end['status'], 'Fracture detection reason': end['reason'],
            'Fracture EL method': end['method'],
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
