"""Two-workbook exports; numeric, wide curve columns and no hidden plot methods."""
from datetime import datetime
from pathlib import Path
import json
import os
import tempfile
import numpy as np
import pandas as pd
from tensile_gauge import group_basis_label, group_policy


def write_workbook(path, sheets):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    path = Path(path)
    workbook = Workbook()
    workbook.remove(workbook.active)
    for name, frame in sheets.items():
        sheet = workbook.create_sheet(name[:31])
        sheet.sheet_view.showGridLines = False
        sheet.freeze_panes = 'B2' if name in ('Summary', 'Specimens', 'Audit') else 'A2'
        if frame.empty and not len(frame.columns):
            sheet.append(['No data available'])
            continue
        if len(frame) >= 1048576 or len(frame.columns) > 16384:
            raise ValueError(f'{name} exceeds Excel worksheet limits')
        headers = [str(c) for c in frame.columns]
        sheet.append(headers)
        for row in frame.itertuples(index=False, name=None):
            values = []
            for v in row:
                if isinstance(v, np.generic):
                    v = v.item()
                if v is None or (not isinstance(v, (list, dict)) and pd.isna(v)):
                    v = None
                elif isinstance(v, float) and not np.isfinite(v):
                    v = None
                elif isinstance(v, (dict, list, tuple)):
                    v = json.dumps(v)
                values.append(v)
            sheet.append(values)
        for cells in sheet.iter_rows():
            for cell in cells:
                cell.font = Font(name='Arial', size=10)
                if isinstance(cell.value, str):
                    cell.data_type = 's'  # literal names/paths, never formulas
                    if headers[cell.column - 1] == 'Checks':
                        cell.alignment = Alignment(wrap_text=True, vertical='top')
                if isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool):
                    header = headers[cell.column - 1].lower()
                    cell.number_format = '0' if (header.endswith(' n') or header in ('n', 'included n', 'available n') or 'row (1-based)' in header) else '0.00'
        for cell in sheet[1]:
            cell.font = Font(name='Arial', size=10, bold=True, color='FFFFFF')
            cell.fill = PatternFill('solid', fgColor='24445C')
            cell.alignment = Alignment(wrap_text=True, vertical='center')
        sheet.row_dimensions[1].height = 45
        for i, header in enumerate(headers, 1):
            sheet.column_dimensions[get_column_letter(i)].width = min(38, max(18, len(header) * .65))
            if header == 'Checks':
                sheet.column_dimensions[get_column_letter(i)].width = 65
        sheet.auto_filter.ref = sheet.dimensions
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.' + path.stem, suffix='.xlsx', delete=False) as f:
            temporary = Path(f.name)
        workbook.save(temporary)
        os.replace(temporary, path)
    finally:
        workbook.close()
        if temporary is not None and temporary.exists():
            temporary.unlink()


def flatten_info(metadata):
    rows = [{'Setting': 'Exported at', 'Value': datetime.now().astimezone().isoformat()}]
    def visit(key, value):
        if isinstance(value, dict):
            for k, v in value.items():
                visit(f'{key}.{k}' if key else k, v)
        elif isinstance(value, (list, tuple)):
            for i, v in enumerate(value):
                visit(f'{key}[{i}]', v)
        else:
            rows.append({'Setting': key, 'Value': value})
    visit('', metadata)
    return pd.DataFrame(rows)


def export_results(frames, path, metadata):
    from tensile_tables import specimen_export_frame, summary_wide, SPECIMEN_DETAIL_FIELDS
    from tensile_properties import EL_SOURCE_FIELDS
    samples = frames['tensile_samples']
    checks = frames['specimen_diagnostics'].copy()
    comparison = frames['instron_comparison']
    # Use exactly the UI's numeric schema, not its formatted strings or the
    # internal acquisition dictionaries. Search filters never change exports.
    specimens = specimen_export_frame(samples, comparison)
    summary = summary_wide(frames['tensile_summary_details'])
    # Provenance and acquisition bookkeeping belong only in the audit sheet.
    # Keep stable specimen IDs for joins; never depend on display row order.
    visible_fields = {'Included', 'Exclusion Reason', 'Inclusion Scope', 'Checks',
                      '0.2% Offset Yield Strength (MPa)', 'UTS (MPa)', 'Uniform Elongation (%)',
                      'Failure Elongation (%)', 'Measured failure elongation (%)', 'Reconstructed EL (%)',
                      'Toughness (MJ/m^3)', 'Fitted E (GPa)',
                      *(field for _, field in EL_SOURCE_FIELDS),
                      *(field for _, field in SPECIMEN_DETAIL_FIELDS)}
    if not samples.empty:
        source = samples.set_index('Specimen ID')
        for field in samples:
            if field not in visible_fields and field not in checks:
                checks[field] = checks['Specimen ID'].map(source[field])
        # These lengths are useful for auditing the gauge calculation even
        # though the corresponding display columns remain in Specimens.
        for field in ('AVE dot spacing (mm)', 'Target gauge length (mm)'):
            checks[field] = checks['Specimen ID'].map(source[field]) if field in source else np.nan
    if 'Estimated toughness (MJ/m^3)' in checks:
        applied = checks['Gauge correction status'].eq('Applied') & checks['Elongation basis'].eq('Estimated standard gauge')
        checks['Estimated toughness (MJ/m^3)'] = checks['Estimated toughness (MJ/m^3)'].where(applied)
        checks = checks.rename(columns={'Estimated toughness (MJ/m^3)': 'Reconstructed toughness (MJ/m^3)'})
    if 'Elongation basis' in checks:
        checks['Elongation basis'] = checks['Elongation basis'].replace({'Estimated standard gauge': 'Reconstructed gauge'})
    lookup = {'0.2% yield strength': '0.2% Offset Yield Strength (MPa)',
              'UTS': 'UTS (MPa)', 'Uniform elongation': 'Uniform Elongation (%)',
              'Fitted elastic modulus': 'Fitted E (GPa)'}
    for label, field in lookup.items():
        if comparison.empty or field not in samples:
            continue
        match = comparison[comparison['Property'].str.casefold() == label.casefold()].drop_duplicates('Specimen ID').set_index('Specimen ID')
        for key in ('Difference (calc - Instron)', 'Difference (%)'):
            checks[label + ' · ' + key] = checks['Specimen ID'].map(match[key])
    if 'Override Definition' in checks:
        def description(value):
            try:
                obj = json.loads(value) if value else {}
                return '; '.join(f'{key}: {obj[key]}' for key in ('mode', 'strain_bounds', 'endpoints') if key in obj)
            except (ValueError, TypeError):
                return str(value)
        checks['Override Definition'] = checks['Override Definition'].map(description)
    # Shared IDs are join keys; avoid repeating the main property values here.
    checks = checks.drop(columns=[c for c in (visible_fields | {'Elastic fit R2'}) if c in checks
                                 and c not in ('AVE dot spacing (mm)', 'Target gauge length (mm)')])
    metadata = {**metadata, 'definitions': {
        'calculated_basis': 'Tensile plots/statistics use detected CSV drop onset, or its gauge reconstruction when enabled. Toughness integrates only through that endpoint. Pre-peak properties and WH use measured data. No terminal-reading or Instron fallback when fracture is not detected.',
        'elongation_columns': 'Elongation columns are Instron (imported Strain 1 at break), Calc (last recorded point before a detected sustained load collapse, without a strain setback), and Reconstruct (its gauge reconstruction, blank unless enabled and available). Last valid CSV strain and maximum retained strain are audit-only; original endpoint rows, time, load-loss evidence, detector settings and status are retained.',
        'instron_comparison': 'Differences compare measured calculations with original Instron values, never reconstructed values.',
        'checks': 'Failure/review messages appear in the Specimens Checks column. Identity is verified by name/export row and original CSV UTS agreement within printed-digit rounding tolerance. EL is not an identity check and differences from Instron break EL are not matching failures. No automatic exclusion or numerical rematching.',
        'table_layout': 'Summary and Specimens share the viewer\'s property names, order, analysis basis and blank-value rules. Uniform elongation and tensile toughness retain Calc and Instron columns; unsupported or missing imports remain blank. Elongation has Instron, Calc and Reconstruct columns. Summary mean, SD and n are separate numeric columns. Specimens adds a stable Specimen ID to join Audit. Audit contains source, fit, gauge and comparison details, not an additional user table.',
        'selection': 'Global specimen exclusions apply unless this graph contains an explicit inclusion override. Hard-ignored ! files never load.',
        'gauge': 'Strain 1 gauge length is the AVE-measured initial dot spacing. Target and enabled state are per sample group within this graph.',
        'estimate': 'Post-peak reconstruction assumes both gauge intervals capture the localisation. Longer targets are allowed with warnings. Not a standards-compliant measurement.',
        'gauge_formula': 'r = L_dots / L_target; pre-peak strain unchanged; post-peak strain_est = strain_u + r * (strain_measured - strain_u). Failure EL_est = EL_u + r * (EL_measured - EL_u). All strains are total engineering strain in percent; stress unchanged throughout.',
        'failure_endpoint': 'Acquisition-order load-collapse detector (v2): a substantial non-recovering loss faster than preceding necking, refined to the last raw pre-collapse measurement. Force is preferred; engineering stress is the explicit fallback signal. No strain-grid interpolation, terminal-reading fallback, or use of Instron EL for detection. Heuristic selection requiring review, not a standards-compliant post-fracture measurement.',
        'precision': 'Full numeric precision stored; two decimal places displayed (counts and row identifiers remain integers).'}}
    write_workbook(path, {'Summary': summary, 'Specimens': specimens, 'Audit': checks,
                         'Export info': flatten_info(metadata)})


def export_curves(results, engine, path):
    sheets, seen, checks, names = {}, set(), [], {}
    def add(sheet, label, x, y, *, extra=None, info=None):
        x, y = np.asarray(x, float), np.asarray(y, float)
        signature = (sheet, label, x.tobytes(), y.tobytes(),
                     tuple((k, np.asarray(v, float).tobytes()) for k, v in (extra or {}).items()))
        if signature in seen:
            return
        seen.add(signature)
        key = (sheet, label)
        names[key] = names.get(key, 0) + 1
        if names[key] > 1:
            label += f' · variant {names[key]}'
        wh = sheet.startswith('WH')
        columns = sheets.setdefault(sheet, {})
        columns[label + (' · true plastic strain (%)' if wh else ' · strain (%)')] = pd.Series(x)
        y_label = (' · WH rate (MPa)' if wh else
                   ' · measured mean stress (MPa)' if sheet == 'Tensile pointwise' else ' · stress (MPa)')
        columns[label + y_label] = pd.Series(y)
        for suffix, values in (extra or {}).items():
            columns[label + ' · ' + suffix] = pd.Series(values)
        checks.append({'Sheet': sheet, 'Curve': label, 'Points': len(x),
                       'Start strain (%)': x[0] if len(x) else np.nan,
                       'End strain (%)': x[-1] if len(x) else np.nan, **(info or {})})

    for view_number, view in enumerate(results, 1):
        state, spec = view['state'], view['graph_spec']
        family = state['family']
        records, models = view.get('export_records', {}), view.get('export_models') or {}
        methods = {'landmark': ['landmark'], 'pointwise': ['pointwise'], 'comparison': ['pointwise', 'landmark']}.get(family, [])
        for group, model in models.items():
            basis = group_basis_label(state, spec, group)
            for method in methods:
                curve = model[method]
                if curve is None:
                    checks.append({'Sheet': 'Tensile ' + method, 'Curve': group, 'Status': model.get(method + '_diagnostic', 'Unavailable'), 'View': view_number})
                    continue
                x, y = curve['x'], curve['y']
                area = engine.compute_toughness_safe(x, y)
                specimen_areas = [engine.compute_toughness_safe(r['strain_pct'], r['stress_mpa']) for r in records[group]]
                mean = float(np.nanmean(specimen_areas))
                complete = method == 'landmark' or curve.get('complete', False)
                info = {'Group': group, 'Method': method, 'Basis': basis, 'View': view_number,
                        'Target gauge (mm)': group_policy(state, spec, group)['target_gauge_mm'] or np.nan,
                        'n': len(records[group]), 'Complete': complete,
                        'Curve toughness (MJ/m^3)': area, 'Mean specimen toughness (MJ/m^3)': mean,
                        'Difference (%)': 100 * (area - mean) / mean if complete and np.isfinite(mean) and mean else np.nan,
                        'Status': model.get(method + '_diagnostic', '')}
                extra = None
                if method == 'pointwise':
                    y = np.array(y, copy=True)
                    tail = np.array(y, copy=True)
                    split = len(curve['measured_x']) - 1
                    y[split + 1:] = np.nan
                    tail[:split] = np.nan
                    if not len(curve.get('predicted_x', [])):
                        tail[:] = np.nan
                    extra = {'projected stress (MPa)': tail}
                add('Tensile ' + method, group + ' · ' + basis, x, y, extra=extra, info=info)
                if method == 'landmark':
                    for point in curve.get('point_statistics', []):
                        entry = {'Sheet': 'Tensile landmark', 'Curve': group + ' · ' + basis,
                                 'Landmark': point['name'], 'Landmark strain (%)': point['x'],
                                 'Landmark stress (MPa)': point['y'], 'Strain SD (%)': point['x_sd'],
                                 'Stress SD (MPa)': point['y_sd'], 'Basis': basis}
                        if entry not in checks:
                            checks.append(entry)
        if family == 'representative':
            for group, rows in records.items():
                basis = group_basis_label(state, spec, group)
                record = engine.choose_representative_curve(group, rows, spec.get('representative_overrides', {}).get(group))
                if record is not None:
                    add('Tensile representatives', group + ' · ' + record['sample'] + ' · ' + basis,
                        record['strain_pct'], record['stress_mpa'], info={'Basis': basis, 'Specimen ID': record['specimen_id'], 'View': view_number})
        if state['show_individuals'] and family in ('landmark', 'pointwise', 'comparison', 'representative'):
            for group, rows in records.items():
                basis = group_basis_label(state, spec, group)
                for record in rows:
                    add('Tensile individuals', group + ' · ' + record['sample'] + ' · ' + basis,
                        record['strain_pct'], record['stress_mpa'], info={'Basis': basis, 'Specimen ID': record['specimen_id'], 'View': view_number})
        for sheet, group, index, x, y in getattr(view['figure'], '_export_wh', []):
            label = group if index is None else group + ' · ' + records[group][index]['sample']
            add(sheet, label, x, y, info={'Basis': 'Measured pre-peak response', 'View': view_number})
    if not sheets:
        return  # scatter plots already have their data in the results workbook
    frames = {name: pd.DataFrame(columns) for name, columns in sheets.items()}
    frames['Curve checks'] = pd.DataFrame(checks)
    write_workbook(path, frames)
