"""Per-group post-peak AVE gauge reconstruction; never mutate measurements."""
from copy import deepcopy
import math
from tensile_fracture import fracture_endpoint, fracture_curve

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
    return (f"Reconstructed CSV-derived fracture EL · target {policy['target_gauge_mm']:.2f} mm"
            if policy['enabled'] else 'CSV-derived fracture EL · detected drop onset')


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
             'Failure time (s)': np.nan, 'Failure endpoint': 'Detected CSV drop onset (interpolated)'}
    view = dict(record)
    view.pop('_property_cache', None)
    view['_measured_record'] = record
    view['_gauge'] = audit
    endpoint = fracture_endpoint(record)
    view['_fracture'] = endpoint
    view['failure_elongation_pct'] = endpoint['strain_pct']
    # Uncorrected and reconstructed tensile views share this exact endpoint.
    # Keep the original full curve on _measured_record for inspection and WH.
    if endpoint['status'] == 'Detected':
        measured_x, measured_y, ids = fracture_curve(record)
        view.update(strain_pct=measured_x, raw_strain_pct=measured_x,
                    stress_mpa=measured_y, raw_stress_mpa=measured_y,
                    _measurement_indices=ids)
    try:
        if endpoint['status'] != 'Detected':
            raise ValueError('CSV fracture not detected: ' + endpoint['reason'])
        if not np.isfinite(dots) or dots <= 0:
            raise ValueError('Missing or conflicting Strain 1 gauge length in Instron summary')
        if not np.isfinite(target) or target <= 0:
            raise ValueError('Enter a positive target gauge length')
        if target > dots + 1e-9:
            audit['Gauge model warning'] = (
                'Target gauge exceeds AVE spacing; reconstructed EL will be lower.')
        meta = record['_acquisition']
        peak = meta['peak']
        # Peak detection belongs to the original acquisition, not the cleaned
        # plotting grid. A finite peak may have been dropped solely because the
        # previous strain reading was slightly higher.
        if peak is None or not np.isfinite(meta['strain'][peak]):
            raise ValueError('Maximum-force point has no usable matching strain')
        if not len(ids) or endpoint.get('row_after', np.nan) < peak + 1:
            raise ValueError('Failure endpoint precedes maximum force')
        eu, ef = float(meta['strain'][peak]), endpoint['strain_pct']
        if ef < eu:
            raise ValueError('Failure strain is below peak-force strain')
        ratio = dots / target
        corrected = measured_x.copy()
        # ID -1 is the synthetic interpolated fracture endpoint, after peak.
        post = (ids > peak) | (ids == -1)
        corrected[post] = eu + ratio * (corrected[post] - eu)
        # Reapplying a piecewise transform to a strain-sorted plotting grid can
        # locally change its order near the breakpoint. Preserve every retained
        # X/Y pair and the actual peak anchor; do not clamp or fabricate strain.
        reversals = int(np.count_nonzero(np.diff(corrected) < 0))
        below_peak = int(np.count_nonzero(corrected[post] < eu))
        notes = []
        if reversals:
            notes.append('Corrected points reordered by strain for plotting; values unchanged.')
        if below_peak:
            notes.append('Some readings after maximum force have lower strain than at maximum force; kept unchanged.')
        order = np.argsort(corrected, kind='stable')
        corrected = corrected[order]
        corrected_stress = measured_y[order]
        estimate = eu + ratio * (ef - eu)
        if corrected[-1] > estimate + 1e-10:
            raise ValueError('A retained pre-peak strain exceeds reconstructed fracture EL; review the curve')
        area = float(np.trapezoid(corrected_stress, corrected / 100))
        if not np.all(np.isfinite(corrected)) or not np.isfinite(estimate) or not np.isfinite(area):
            raise ValueError('Gauge ratio produces nonfinite reconstructed values')
        audit.update({'Gauge ratio': ratio, 'Gauge correction status': 'Available',
                      'Estimated failure elongation (%)': estimate, 'Estimated toughness (MJ/m^3)': area,
                      'Peak-force measurement row (1-based)': peak + 1, 'Peak-force time (s)': meta['time'][peak],
                      'Peak retained in plotting grid': bool(peak in ids),
                      'Reconstructed grid order reversals': reversals,
                      'Post-peak points below peak strain': below_peak,
                      'Gauge reconstruction notes': ' '.join(notes),
                      'Peak identification': meta['peak_basis'], 'Strain channel': meta['strain_channel'],
                      'Strain at peak force (%)': eu, 'Measured endpoint strain (%)': ef,
                      'Failure measurement row (1-based)': (endpoint['row_before']
                          if endpoint['row_before'] == endpoint['row_after'] else np.nan),
                      'Failure time (s)': endpoint['time_s'],
                      'Failure time basis': 'Interpolated at detected drop onset',
                      'Failure endpoint stress (MPa)': endpoint['stress_mpa']})
        if enabled:
            view.update(strain_pct=corrected, raw_strain_pct=corrected,
                        stress_mpa=corrected_stress, raw_stress_mpa=corrected_stress,
                        _measurement_indices=ids[order],
                        failure_elongation_pct=estimate)
            view['_fracture'] = {**endpoint, 'strain_pct': estimate}
            audit['Gauge correction status'] = 'Applied'
    except (ValueError, KeyError) as error:
        audit['Gauge correction status'] = str(error)
        if enabled:
            view['failure_elongation_pct'] = np.nan
    return view
