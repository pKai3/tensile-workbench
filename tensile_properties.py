"""Specimen properties, independent of every plot and averaging method."""
import numpy as np

DEFAULT_FIT_FRACTIONS = (.20, .50)


def prepared_curve(record):
    x = np.asarray(record.get('raw_strain_pct', record['strain_pct']), dtype=float)
    y = np.asarray(record.get('raw_stress_mpa', record['stress_mpa']), dtype=float)
    valid = np.isfinite(x) & np.isfinite(y)
    x, y = x[valid], y[valid]
    order = np.argsort(x, kind='stable')
    x, y = x[order], y[order]
    x, ix = np.unique(x, return_index=True)
    y = np.maximum.reduceat(y, ix) if len(ix) else y
    return x, y


def specimen_properties(record, fit_fractions=DEFAULT_FIT_FRACTIONS, r2_warning=.98):
    """Cache by specimen and elastic-fit settings; WH modulus is not used.

    A failed yield fit does not discard measured UTS/elongation/toughness.
    No post-UTS segment or landmark-aligned curve is needed for yield.
    """
    low, high = map(float, fit_fractions)
    if not 0 < low < high < 1:
        raise ValueError('yield fit fractions must satisfy 0 < low < high < 1')
    key = (low, high, float(r2_warning))
    cache = record.setdefault('_property_cache', {})
    if key in cache:
        return dict(cache[key])
    p = {'Sample': record['sample'], 'Raw source': record['source_file'],
         'Yield method': '0.2% offset, specimen-specific linear elastic fit',
         'Yield status': 'unresolved', 'Notes': ''}
    for field in ('Yield (MPa)', 'Yield strain (%)', 'UTS (MPa)', 'Uniform elongation (%)',
                  'Failure elongation (%)', 'Toughness (MJ/m^3)', 'Fitted E (GPa)',
                  'Elastic intercept (MPa)', 'Elastic fit R2', 'Fit lower stress (MPa)',
                  'Fit upper stress (MPa)'):
        p[field] = np.nan
    x, y = prepared_curve(record)
    if len(x):
        peak = int(np.argmax(y))
        p.update({'UTS (MPa)': float(y[peak]), 'Uniform elongation (%)': float(x[peak]),
                  'Failure elongation (%)': float(x[-1])})
        raw_x, raw_y = np.asarray(record['strain_pct']), np.asarray(record['stress_mpa'])
        valid = np.isfinite(raw_x) & np.isfinite(raw_y)
        if valid.sum() >= 2:
            p['Toughness (MJ/m^3)'] = float(np.trapezoid(raw_y[valid], raw_x[valid] / 100))
    try:
        if len(x) < 20:
            raise ValueError('fewer than 20 valid strain points')
        uts = p['UTS (MPa)']
        if uts <= 0 or peak < 3:
            raise ValueError('missing resolved loading segment')
        elastic = (np.arange(len(x)) < peak) & (y >= low * uts) & (y <= high * uts)
        p.update({'Fit lower stress (MPa)': low * uts, 'Fit upper stress (MPa)': high * uts})
        if elastic.sum() < 5 or np.ptp(x[elastic]) <= 0:
            raise ValueError('insufficient elastic data for offset yield')
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
        fraction = distance[i] / (distance[i] - distance[i + 1])
        p.update({'Yield (MPa)': float(y[i] + fraction * (y[i + 1] - y[i])),
                  'Yield strain (%)': float(x[i] + fraction * (x[i + 1] - x[i])),
                  'Yield status': 'resolved',
                  'Notes': 'Review elastic fit: low R2' if r2 < r2_warning else ''})
    except ValueError as error:
        p['Notes'] = str(error)
    cache[key] = dict(p)
    return p
