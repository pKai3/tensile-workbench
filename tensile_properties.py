"""Specimen properties, independent of every plot and averaging method."""
import numpy as np
import json
from tensile_fit import validate_override, validate_threshold
from tensile_fracture import FRACTURE_METHOD, prepared_points, fracture_endpoint, fracture_curve, fracture_audit, endpoint_available

DEFAULT_FIT_FRACTIONS = (.20, .50)
USE_RECORD = object()

EL_SOURCE_FIELDS = (
    ('Instron', 'Instron summary EL (%)'),
    ('Calc', 'CSV-derived fracture EL (%)'),
    ('Reconstruct', 'Reconstructed EL (%)'),
)


def elongation_report(record, reference, measured_properties):
    """Report distinct endpoint sources without substituting one for another.

    Analysis uses the selected endpoint, not the landmark shape-trimming point.
    """
    measured = record.get('_measured_record', record)
    meta = measured.get('_acquisition', {})
    strain = np.asarray(meta.get('strain', []), dtype=float)
    finite = np.flatnonzero(np.isfinite(strain))
    last = int(finite[-1]) if len(finite) else None
    times = np.asarray(meta.get('time', []), dtype=float)
    gauge = record.get('_gauge', {})
    enabled = gauge.get('Elongation basis') == 'Estimated standard gauge'
    reconstructed = (gauge.get('Estimated failure elongation (%)', np.nan)
                     if enabled and gauge.get('Gauge correction status') == 'Applied' else np.nan)
    prepared_x, _ = prepared_curve(measured)
    end = fracture_endpoint(measured)
    return {
        'Instron summary EL (%)': reference.get('values', {}).get('el', np.nan),
        'Last valid CSV strain (%)': float(strain[last]) if last is not None else np.nan,
        'CSV endpoint EL (%)': float(prepared_x[-1]) if len(prepared_x) else np.nan,
        'Reconstructed EL (%)': reconstructed,
        'EL plot source': 'Reconstruct' if enabled else 'Calc',
        'EL analysis source': ('Reconstructed CSV-derived EL · ' if enabled else 'CSV-derived EL · ')
                               + end.get('endpoint_kind', end['status']),
        'Reconstructed EL endpoint source': end.get('endpoint_kind', end['status']) if enabled else '',
        'Last valid strain measurement row (1-based)': last + 1 if last is not None else np.nan,
        'Last valid strain time (s)': float(times[last]) if last is not None and last < len(times) else np.nan,
        'CSV-derived fracture EL (%)': end['strain_pct'],
        **fracture_audit(measured),
    }


def prepared_curve(record):
    x, y, _ = prepared_points(record)
    return x, y


def specimen_properties(record, fit_fractions=DEFAULT_FIT_FRACTIONS, r2_warning=.98):
    """Cache by specimen and elastic-fit settings; WH modulus is not used.

    A failed yield fit does not discard measured UTS/elongation/toughness.
    No post-UTS segment or landmark-aligned curve is needed for yield.
    """
    if '_measured_record' in record:
        p = specimen_properties(record['_measured_record'], fit_fractions, r2_warning)
        audit = record['_gauge']
        p['Measured failure elongation (%)'] = p['Failure elongation (%)']
        p['Measured toughness (MJ/m^3)'] = p['Toughness (MJ/m^3)']
        p.update(audit)
        if audit['Elongation basis'] == 'Estimated standard gauge':
            p['Failure elongation (%)'] = audit['Estimated failure elongation (%)']
            p['Toughness (MJ/m^3)'] = audit['Estimated toughness (MJ/m^3)']
        return p
    low, high = map(float, fit_fractions)
    if not 0 < low < high < 1:
        raise ValueError('yield fit fractions must satisfy 0 < low < high < 1')
    r2_warning = validate_threshold(record.get('_fit_r2_threshold', r2_warning))
    key = (low, high, r2_warning, json.dumps(record.get('_fit_override'), sort_keys=True),
           json.dumps(record.get('_failure_override'), sort_keys=True),
           record.get('source_sha256'), FRACTURE_METHOD)
    cache = record.setdefault('_property_cache', {})
    if key in cache:
        return dict(cache[key])
    p = specimen_calculation(record, (low, high), r2_warning)['properties']
    cache[key] = dict(p)
    return p


def specimen_calculation(record, fit_fractions=DEFAULT_FIT_FRACTIONS, r2_warning=.98, *, override=USE_RECORD):
    """Return the same properties plus the exact points/indices used to fit them.

    This is the single calculation path for tables, landmarks and inspection.
    Diagnostic arrays are built only on demand; the properties cache stays small.
    Specimen overrides take precedence over graph-level automatic fit fractions.
    A preview override can be passed explicitly without changing the record.
    """
    low, high = map(float, fit_fractions)
    if not 0 < low < high < 1:
        raise ValueError('yield fit fractions must satisfy 0 < low < high < 1')
    r2_warning = validate_threshold(record.get('_fit_r2_threshold', r2_warning))
    saved = record.get('_fit_override') if override is USE_RECORD else override
    stale = bool(saved and saved.get('source_sha256') != record.get('source_sha256'))
    active = saved if saved and not stale else None
    if active:
        validate_override(active)
    p = {'Sample': record['sample'], 'Raw source': record['source_file'],
         'Yield method': '0.2% offset, specimen-specific linear elastic fit',
         'Yield status': 'unresolved', 'Notes': '',
         'Fit method': ('Manual range' if active['mode'] == 'range' else 'Manual line') if active else 'Automatic',
         'Override status': 'Stale source — not applied' if stale else ('Applied' if active else 'None'),
         'R2 warning threshold': r2_warning, 'Fit point count': 0,
         'Fit lower strain (%)': np.nan, 'Fit upper strain (%)': np.nan}
    for field in ('Yield (MPa)', 'Yield strain (%)', 'UTS (MPa)', 'Uniform elongation (%)',
                  'Failure elongation (%)', 'Toughness (MJ/m^3)', 'Fitted E (GPa)',
                  'Elastic intercept (MPa)', 'Elastic fit R2', 'Fit lower stress (MPa)',
                  'Fit upper stress (MPa)'):
        p[field] = np.nan
    x, y = prepared_curve(record)
    calculation = {'properties': p, 'strain_pct': x, 'stress_mpa': y,
                   'elastic_mask': np.zeros(len(x), dtype=bool),
                   'uts_index': None, 'yield_bracket': None,
                   'fit_fractions': (low, high), 'override': active, 'saved_override': saved,
                   'r2_threshold': r2_warning}
    endpoint = fracture_endpoint(record)
    calculation['fracture'] = endpoint
    p.update(fracture_audit(record))
    if len(x):
        peak = int(np.argmax(y))
        calculation['uts_index'] = peak
        p.update({'UTS (MPa)': float(y[peak]), 'Uniform elongation (%)': float(x[peak]),
                  'Failure elongation (%)': endpoint['strain_pct']})
        if endpoint_available(endpoint):
            end_x, end_y, _ = fracture_curve(record)
            p['Toughness (MJ/m^3)'] = float(np.trapezoid(end_y, end_x / 100))
    try:
        if len(x) < 20:
            raise ValueError('fewer than 20 valid strain points')
        uts = p['UTS (MPa)']
        if uts <= 0 or peak < 3:
            raise ValueError('missing resolved loading segment')
        if active:
            left, right = active['strain_bounds']
            if left < x[0] or right >= x[peak]:
                raise ValueError('Fit bounds must lie on the measured loading curve strictly before UTS.')
            elastic = (np.arange(len(x)) < peak) & (x >= left) & (x <= right)
            p['Yield method'] = '0.2% offset, ' + p['Fit method'].lower()
        else:
            elastic = (np.arange(len(x)) < peak) & (y >= low * uts) & (y <= high * uts)
        calculation['elastic_mask'] = elastic
        p.update({'Fit lower stress (MPa)': low * uts, 'Fit upper stress (MPa)': high * uts})
        p['Fit point count'] = int(elastic.sum())
        if elastic.any():
            p.update({'Fit lower strain (%)': float(x[elastic][0]), 'Fit upper strain (%)': float(x[elastic][-1])})
            if active:
                p.update({'Fit lower stress (MPa)': float(y[elastic].min()), 'Fit upper stress (MPa)': float(y[elastic].max())})
        if elastic.sum() < 5 or np.ptp(x[elastic]) <= 0:
            raise ValueError('insufficient elastic data for offset yield')
        if active and active['mode'] == 'line':
            (x0, y0), (x1, y1) = active['endpoints']
            modulus = (y1 - y0) / ((x1 - x0) / 100)
            intercept = y0 - modulus * x0 / 100
        else:
            modulus, intercept = np.polyfit(x[elastic] / 100, y[elastic], 1)
        if not np.isfinite(modulus) or modulus <= 0:
            raise ValueError('elastic fit has non-positive or invalid modulus')
        residual = y[elastic] - (modulus * x[elastic] / 100 + intercept)
        total = np.sum((y[elastic] - np.mean(y[elastic])) ** 2)
        r2 = 1 - float(np.sum(residual ** 2) / total) if total > 0 else 0.0
        p.update({'Fitted E (GPa)': float(modulus / 1000), 'Elastic intercept (MPa)': float(intercept),
                  'Elastic fit R2': r2})
        distance = y - (modulus * (x / 100 - .002) + intercept)
        last_elastic = np.flatnonzero(elastic)[-1]
        crosses = np.flatnonzero((distance[:-1] >= 0) & (distance[1:] < 0))
        crosses = crosses[(crosses >= last_elastic) & (crosses < peak)]
        if not len(crosses):
            raise ValueError('no valid 0.2% offset yield crossing')
        i = int(crosses[0])
        calculation['yield_bracket'] = (i, i + 1)
        fraction = distance[i] / (distance[i] - distance[i + 1])
        p.update({'Yield (MPa)': float(y[i] + fraction * (y[i + 1] - y[i])),
                  'Yield strain (%)': float(x[i] + fraction * (x[i + 1] - x[i])),
                  'Yield status': 'resolved',
                  'Notes': 'Review elastic fit: low R2' if r2 < r2_warning else ''})
    except ValueError as error:
        p['Notes'] = str(error)
    if stale:
        p['Notes'] = ('Saved override does not match the current source; automatic fit used. ' + p['Notes']).strip()
    p['Fit review required'] = bool(stale or p['Yield status'] != 'resolved' or
                                   not np.isfinite(p['Elastic fit R2']) or p['Elastic fit R2'] < r2_warning)
    automatic = specimen_calculation(record, (low, high), r2_warning, override=None) if active else None
    baseline = automatic['properties'] if automatic else p
    for field in ('Yield (MPa)', 'Yield strain (%)', 'Fitted E (GPa)', 'Elastic fit R2', 'Elastic intercept (MPa)'):
        p['Automatic ' + field] = baseline[field]
    calculation['automatic_calculation'] = automatic
    return calculation
