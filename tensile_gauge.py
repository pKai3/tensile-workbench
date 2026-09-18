"""Per-group post-peak AVE gauge reconstruction; never mutate measurements."""
from copy import deepcopy
import math

def validate_group_policy(policy):
    if not isinstance(policy, dict) or not isinstance(policy.get('enabled', False), bool):
        raise ValueError('Each group gauge setting needs an enabled on/off value.')
    target = policy.get('target_gauge_mm', 0)
    if (isinstance(target, bool) or not isinstance(target, (int, float)) or
            not math.isfinite(target) or target < 0 or (policy.get('enabled') and target <= 0)):
        raise ValueError('Enter a positive target gauge length before enabling a group.')
    return {'enabled': policy.get('enabled', False), 'target_gauge_mm': float(target)}


def group_policy(state, spec, group):
    """One resolver for calculations, inspector, labels, caches and exports."""
    if 'gauge_reconstruction' in spec:
        return validate_group_policy(spec['gauge_reconstruction'].get(group, {}))
    # Compatibility for a headless caller with an older graph definition.
    return validate_group_policy({'enabled': state.get('gauge_correction', False),
                                  'target_gauge_mm': state.get('target_gauge_mm', 0)})


def migrate_group_gauges(project):
    """Preserve legacy choices for existing groups; newly added groups stay off."""
    project = deepcopy(project)
    for graph in project['graphs']:
        settings, spec = graph['settings'], graph['definition']
        if 'gauge_reconstruction' not in spec:
            legacy = group_policy(settings, spec, '')
            spec['gauge_reconstruction'] = {g: dict(legacy) for g in settings['groups']}
        settings.pop('gauge_correction', None)
        settings.pop('target_gauge_mm', None)
    return project


def group_basis_label(state, spec, group):
    policy = group_policy(state, spec, group)
    return (f"Estimated gauge {policy['target_gauge_mm']:g} mm" if policy['enabled'] else 'Measured AVE')


def acquisition_metadata(engine, frame, units, strain, stress):
    import numpy as np
    x, y = np.asarray(strain, float), np.asarray(stress, float)
    force_col = engine.find_first_col(frame, engine.FORCE_COLS)
    time_col = engine.find_first_col(frame, ['Time', 'Test time', 'Time (s)'])
    force = np.asarray(frame[force_col], float) if force_col else y
    time = np.asarray(frame[time_col], float) if time_col else np.full(len(x), np.nan)
    time_unit = str(units.get(time_col, '')).lower().strip()
    time = time * {'s': 1, 'sec': 1, 'min': 60, 'ms': .001}.get(time_unit, np.nan)
    valid_force = np.isfinite(force)
    peak = int(np.argmax(np.where(valid_force, force, -np.inf))) if valid_force.any() else None
    return {'strain': x.copy(), 'stress': y.copy(), 'force': force.copy(),
            'time': time.copy(), 'peak': peak,
            'peak_basis': 'Maximum force' if force_col else 'Maximum engineering stress (force proxy)',
            'force_channel': force_col or '', 'time_channel': time_col or '',
            'strain_channel': engine.find_first_col(frame, engine.STRAIN_COLS) or ''}


def prepared_indices(metadata):
    """Mirror legacy loading cleanup while retaining original acquisition rows."""
    import numpy as np
    x, y = metadata['strain'], metadata['stress']
    ids = np.flatnonzero(np.isfinite(x) & np.isfinite(y))
    starts = np.flatnonzero((x[ids] >= 0) & (y[ids] >= 0))
    if not len(starts):
        return np.array([], dtype=int)
    ids = ids[starts[0]:]
    ids = ids[np.r_[True, np.diff(x[ids]) >= 0]]
    return ids[np.argsort(x[ids], kind='stable')]


def gauge_record(record, reference, enabled, target):
    """Return a separate analysis view with a measured baseline and audit fields."""
    import numpy as np
    dots = reference.get('values', {}).get('gauge', np.nan)
    audit = {'Elongation basis': 'Estimated standard gauge' if enabled else 'Measured AVE',
             'AVE dot spacing (mm)': dots, 'Target gauge length (mm)': target if target > 0 else np.nan,
             'Gauge ratio': np.nan, 'Gauge correction status': 'Unavailable',
             'Gauge model warning': '',
             'Gauge source': reference.get('source', ''),
             'Estimated failure elongation (%)': np.nan, 'Estimated toughness (MJ/m^3)': np.nan,
             'Peak-force measurement row (1-based)': np.nan, 'Peak-force time (s)': np.nan,
             'Strain at peak force (%)': np.nan, 'Failure measurement row (1-based)': np.nan,
             'Failure time (s)': np.nan, 'Failure endpoint': 'Maximum retained recorded strain (legacy endpoint)'}
    view = dict(record)
    view.pop('_property_cache', None)
    view['_measured_record'] = record
    view['_gauge'] = audit
    try:
        if not np.isfinite(dots) or dots <= 0:
            raise ValueError('Missing or conflicting Strain 1 gauge length in Instron summary')
        if not np.isfinite(target) or target <= 0:
            raise ValueError('Enter a positive target gauge length')
        if target > dots + 1e-9:
            audit['Gauge model warning'] = (
                f'Target {target:g} mm exceeds AVE spacing {dots:g} mm. Model applied as-is: '
                'assumes both gauges contain the localisation and ignores additional post-peak '
                'extension outside the measured interval. Derived estimate, not a validated conversion.')
        meta, ids = record['_acquisition'], record['_measurement_indices']
        peak = meta['peak']
        # Peak detection belongs to the original acquisition, not the cleaned
        # plotting grid. A finite peak may have been dropped solely because the
        # previous strain reading was slightly higher.
        if peak is None or not np.isfinite(meta['strain'][peak]):
            raise ValueError('Maximum-force point has no usable matching strain')
        if not len(ids) or ids[-1] < peak:
            raise ValueError('Failure endpoint precedes maximum force')
        end = int(ids[-1])
        eu, ef = float(meta['strain'][peak]), float(meta['strain'][end])
        if ef < eu:
            raise ValueError('Failure strain is below peak-force strain')
        ratio = dots / target
        corrected = meta['strain'][ids].copy()
        post = ids > peak
        corrected[post] = eu + ratio * (corrected[post] - eu)
        # Reapplying a piecewise transform to a strain-sorted plotting grid can
        # locally change its order near the breakpoint. Preserve every retained
        # X/Y pair and the actual peak anchor; do not clamp or fabricate strain.
        reversals = int(np.count_nonzero(np.diff(corrected) < 0))
        below_peak = int(np.count_nonzero(corrected[post] < eu))
        order = np.argsort(corrected, kind='stable')
        corrected = corrected[order]
        corrected_stress = np.asarray(record['stress_mpa'])[order]
        estimate = eu + ratio * (ef - eu)
        area = float(np.trapezoid(corrected_stress, corrected / 100))
        if not np.all(np.isfinite(corrected)) or not np.isfinite(estimate) or not np.isfinite(area):
            raise ValueError('Gauge ratio produces nonfinite reconstructed values')
        audit.update({'Gauge ratio': ratio, 'Gauge correction status': 'Available',
                      'Estimated failure elongation (%)': estimate, 'Estimated toughness (MJ/m^3)': area,
                      'Peak-force measurement row (1-based)': peak + 1, 'Peak-force time (s)': meta['time'][peak],
                      'Peak retained in plotting grid': bool(peak in ids),
                      'Reconstructed grid order reversals': reversals,
                      'Post-peak points below peak strain': below_peak,
                      'Gauge reconstruction notes': ('Retained X/Y pairs re-sorted by reconstructed strain; no values clipped. '
                          'Post-peak readings below peak strain are preserved.' if reversals or below_peak else ''),
                      'Peak identification': meta['peak_basis'], 'Strain channel': meta['strain_channel'],
                      'Strain at peak force (%)': eu, 'Measured endpoint strain (%)': ef,
                      'Failure measurement row (1-based)': end + 1, 'Failure time (s)': meta['time'][end]})
        if enabled:
            view.update(strain_pct=corrected, raw_strain_pct=corrected,
                        stress_mpa=corrected_stress, raw_stress_mpa=corrected_stress,
                        _measurement_indices=ids[order],
                        failure_elongation_pct=estimate)
            audit['Gauge correction status'] = 'Applied'
    except (ValueError, KeyError) as error:
        audit['Gauge correction status'] = str(error)
        if enabled:
            view['failure_elongation_pct'] = np.nan
    return view
