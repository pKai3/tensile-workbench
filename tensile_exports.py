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
        sheet.freeze_panes = 'B2' if name in ('Summary', 'Specimens', 'Checks') else 'A2'
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
                if isinstance(cell.value, (int, float)) and not isinstance(cell.value, bool):
                    header = headers[cell.column - 1].lower()
                    cell.number_format = '0' if (header.endswith(' n') or header in ('n', 'included n', 'available n') or 'row (1-based)' in header) else '0.000'
        for cell in sheet[1]:
            cell.font = Font(name='Arial', size=10, bold=True, color='FFFFFF')
            cell.fill = PatternFill('solid', fgColor='24445C')
            cell.alignment = Alignment(wrap_text=True, vertical='center')
        sheet.row_dimensions[1].height = 45
        for i, header in enumerate(headers, 1):
            sheet.column_dimensions[get_column_letter(i)].width = min(38, max(18, len(header) * .65))
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
    specimens = frames['tensile_samples'].copy()
    checks = frames['specimen_diagnostics'].copy()
    comparison = frames['instron_comparison']
    # Move Instron results next to the corresponding calculated property.
    lookup = {'0.2% yield strength': '0.2% Offset Yield Strength (MPa)',
              'UTS': 'UTS (MPa)', 'Uniform elongation': 'Uniform Elongation (%)',
              'Failure elongation': 'Failure Elongation (%)', 'Fitted elastic modulus': 'Fitted E (GPa)'}
    for label, field in lookup.items():
        if comparison.empty or field not in specimens:
            continue
        match = comparison[comparison['Property'].str.casefold() == label.casefold()].drop_duplicates('Specimen ID').set_index('Specimen ID')
        ref = specimens['Specimen ID'].map(match['Instron'])
        specimens.insert(specimens.columns.get_loc(field) + 1, field + ' · Instron', ref)
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
    checks = checks.drop(columns=[c for c in ('Fitted E (GPa)', 'Yield Status', 'Yield Notes',
        'Included', 'Exclusion Reason', 'Fit method', 'Override status') if c in checks])
    metadata = {**metadata, 'definitions': {
        'calculated_basis': 'Failure elongation/toughness use each group\'s selected basis within this graph; measured and estimated values are also retained separately.',
        'instron_comparison': 'Differences compare measured calculations with original Instron values, never reconstructed values.',
        'gauge': 'Strain 1 gauge length is the AVE-measured initial dot spacing. Target and enabled state are per sample group within this graph.',
        'estimate': 'Post-peak reconstruction assumes both gauge intervals capture the localisation. Longer targets are allowed with warnings. Not a standards-compliant measurement.',
        'failure_endpoint': 'Maximum retained recorded strain (legacy endpoint), not independently detected fracture.',
        'precision': 'Full numeric precision stored; three decimal places displayed.'}}
    write_workbook(path, {'Summary': frames['tensile_summary'], 'Specimens': specimens,
                         'Checks': checks, 'Instron comparison': frames['instron_comparison_summary'],
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
