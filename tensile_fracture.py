"""One auditable CSV drop-onset endpoint, independent of plots and fit settings."""
import numpy as np

FRACTURE_SLOPE_FRACTION = .10  # Existing landmark drop-detector sensitivity.
FRACTURE_METHOD = 'Terminal drop onset, uniform strain grid (v1); no terminal fallback'


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


def detect_drop_onset(strain, stress, slope_fraction=FRACTURE_SLOPE_FRACTION):
    """Existing sustained-drop heuristic, now explicitly distinguishing failure.

    The endpoint is the start of a qualifying grid interval, not a setback or
    an Instron break result. Interpolation does not imply an original CSV row.
    """
    result = {'status': 'Not detected', 'reason': 'No sustained terminal drop found',
              'method': FRACTURE_METHOD, 'slope_fraction': float(slope_fraction),
              'strain_pct': np.nan, 'stress_mpa': np.nan, 'grid_step_pct': np.nan}
    strain, stress = np.asarray(strain, float), np.asarray(stress, float)
    valid = np.isfinite(strain) & np.isfinite(stress)
    x, idx = np.unique(strain[valid], return_index=True)
    y = stress[valid][idx]
    if len(x) < 20 or x[-1] <= x[0]:
        result['reason'] = 'Fewer than 20 distinct valid strain points'
        return result
    grid = np.linspace(x[0], x[-1], min(5000, max(100, int((x[-1] - x[0]) / .01) + 1)))
    values = np.interp(grid, x, y)
    result['grid_step_pct'] = float(grid[1] - grid[0])
    slope = np.diff(values) / np.diff(grid)
    peak = int(np.argmax(values))
    end_region = max(peak + 1, int(.65 * len(slope)))
    baseline = slope[peak:end_region]
    if len(baseline) < 10:
        if slope_fraction >= .30:
            result['reason'] = 'Insufficient post-peak baseline for drop detection'
            return result
        median, mad = 0., 0.
    else:
        median = float(np.median(baseline))
        mad = float(1.4826 * np.median(np.abs(baseline - median)))
    limit = max(8 * abs(median), 8 * mad, slope_fraction * float(np.max(values)))
    result['slope_threshold_mpa_per_pct'] = median - limit
    drops = np.flatnonzero(slope[end_region:] < median - limit)
    lookahead = max(2, int(np.ceil(.15 / (grid[1] - grid[0]))))
    for drop in drops:
        i = end_region + drop
        later = values[i + 1:min(len(values), i + 1 + lookahead)]
        if (len(later) and later[-1] < values[i] - .01 * np.max(values)
                and grid[i] > x[int(np.argmax(y))]):
            result.update(status='Detected', reason='', strain_pct=float(grid[i]),
                          stress_mpa=float(values[i]))
            return result
    return result


def fracture_endpoint(record):
    """Detect once on the full measured curve; never re-detect a reconstruction."""
    if '_fracture' in record:
        return dict(record['_fracture'])
    if '_measured_record' in record:
        return fracture_endpoint(record['_measured_record'])
    if '_fracture_detection' not in record:
        x, y, ids = prepared_points(record)
        result = detect_drop_onset(x, y)
        result.update(row_before=np.nan, row_after=np.nan, fraction=np.nan, time_s=np.nan)
        if result['status'] == 'Detected':
            right = int(np.searchsorted(x, result['strain_pct'], side='left'))
            left = right if x[right] == result['strain_pct'] else right - 1
            fraction = ((result['strain_pct'] - x[left]) / (x[right] - x[left])
                        if right != left else 0.)
            a, b = int(ids[left]), int(ids[right])
            result.update(row_before=a + 1 if a >= 0 else np.nan,
                          row_after=b + 1 if b >= 0 else np.nan, fraction=float(fraction))
            times = np.asarray(record.get('_acquisition', {}).get('time', []), float)
            if 0 <= a <= b < len(times) and np.isfinite(times[[a, b]]).all():
                result['time_s'] = float(times[a] + fraction * (times[b] - times[a]))
        record['_fracture_detection'] = result
    return dict(record['_fracture_detection'])


def fracture_curve(record):
    """Curve through detected onset, including its interpolated endpoint.

    A synthetic endpoint has source ID -1; its real bracketing rows are stored
    separately in fracture_endpoint. Missing detection is never a terminal fallback.
    """
    endpoint = fracture_endpoint(record)
    if endpoint['status'] != 'Detected':
        raise ValueError('CSV fracture not detected: ' + endpoint['reason'])
    x, y, ids = prepared_points(record)
    end = endpoint['strain_pct']
    if not len(x) or not x[0] < end <= x[-1]:
        raise ValueError('Detected fracture endpoint is outside the analysis curve')
    before = x < end
    exact = np.flatnonzero(x == end)
    end_id = int(ids[exact[0]]) if len(exact) else -1
    return (np.r_[x[before], end], np.r_[y[before], endpoint['stress_mpa']],
            np.r_[ids[before], end_id])


def fracture_audit(record):
    end = fracture_endpoint(record)
    return {'Fracture detection status': end['status'], 'Fracture detection reason': end['reason'],
            'Fracture EL method': end['method'], 'Fracture detector slope fraction': end['slope_fraction'],
            'Fracture detector grid spacing (%)': end['grid_step_pct'],
            'Fracture detector slope threshold (MPa/%)': end.get('slope_threshold_mpa_per_pct', np.nan),
            'Fracture endpoint stress (MPa)': end['stress_mpa'],
            'Fracture bracket first row (1-based)': end.get('row_before', np.nan),
            'Fracture bracket second row (1-based)': end.get('row_after', np.nan),
            'Fracture interpolation fraction': end.get('fraction', np.nan),
            'Fracture interpolated time (s)': end.get('time_s', np.nan)}
