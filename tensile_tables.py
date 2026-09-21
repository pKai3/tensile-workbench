"""Shared numeric tables for the viewer and Excel export. No plot dependencies."""
from html import escape
from datetime import datetime
import numpy as np
import pandas as pd
import uuid
import json
from tensile_selection import specimen_id, selection_state
from tensile_specimens import SpecimenTable
from tensile_properties import EL_SOURCE_FIELDS, elongation_report

PATH_COLUMNS = frozenset(('Source File', 'Instron Summary CSV'))


def _display_cell(value):
    """Escape ordinary cells before inserting our own path controls as HTML."""
    if pd.isna(value):
        return '—'
    if isinstance(value, (float, np.floating)):
        return f'{value:.2f}'
    return escape(str(value))


def _path_cell(value, column):
    """A width-limited path tail, expandable to the exact selectable full path."""
    if pd.isna(value) or not str(value).strip():
        return '—'
    path = escape(str(value))
    label = escape(f'Full {column} path')
    return ('<details class="tw-path">'
            '<summary title="Click to reveal the full path">'
            '<span class="tw-path-tail" dir="rtl"><bdi dir="ltr">' + path + '</bdi></span>'
            '</summary><div class="tw-path-expanded">'
            '<span class="tw-path-hint">Full path · select to copy</span>'
            '<textarea class="tw-path-full" readonly rows="4" wrap="soft" spellcheck="false" '
            'aria-label="' + label + '">' + path + '</textarea></div></details>')


def _override_cell(value):
    """Present the saved fit, not its machine-readable audit JSON, in the UI."""
    if pd.isna(value) or not str(value).strip():
        return '—'
    raw = str(value)
    try:
        saved = json.loads(raw)
        from tensile_fit import validate_override
        validate_override(saved)
    except (ValueError, TypeError):
        # Keep unexpected/legacy content inspectable, escaped and height-limited.
        return ('<details class="tw-fit"><summary>Unrecognised saved record</summary>'
                '<div class="tw-fit-body"><pre>' + escape(raw) + '</pre></div></details>')
    low, high = saved['strain_bounds']
    method = 'Manual range' if saved['mode'] == 'range' else 'Manual line'
    rows = [('Start strain (%)', f'{low:.2f}'), ('End strain (%)', f'{high:.2f}')]
    if saved['mode'] == 'line':
        rows.extend([('Start stress (MPa)', f'{saved["endpoints"][0][1]:.2f}'),
                     ('End stress (MPa)', f'{saved["endpoints"][1][1]:.2f}')])
    fractions = saved.get('automatic_fit_fractions')
    if (isinstance(fractions, list) and len(fractions) == 2 and
            all(isinstance(v, (int, float)) and np.isfinite(v) for v in fractions)):
        rows.append(('Automatic fit window', f'{fractions[0]*100:.2f}–{fractions[1]*100:.2f}% UTS'))
    original = saved.get('automatic_snapshot', {})
    if isinstance(original, dict):
        for key, label in [('Yield (MPa)', 'Original automatic YS (MPa)'),
                           ('Fitted E (GPa)', 'Original automatic E (GPa)'),
                           ('Elastic fit R2', 'Original automatic R²')]:
            value = original.get(key)
            if isinstance(value, (int, float)) and np.isfinite(value):
                rows.append((label, f'{value:.2f}'))
    return ('<details class="tw-fit"><summary title="Click to view the saved fit details">'
            + method + f'<span>{low:.2f}–{high:.2f}% strain</span></summary>'
            '<div class="tw-fit-body"><dl>' + ''.join('<dt>' + escape(label) + '</dt><dd>' +
                escape(text) + '</dd>' for label, text in rows) + '</dl></div></details>')


def _override_date_cell(value):
    """Short readable timestamp; preserve its exact value in the tooltip/export."""
    if pd.isna(value) or not str(value).strip():
        return '—'
    raw = str(value)
    try:
        date = datetime.fromisoformat(raw)
        text = date.strftime('%Y-%m-%d %H:%M')
    except ValueError:
        text = raw
    return '<span class="tw-fit-date" title="' + escape(raw, quote=True) + '">' + escape(text) + '</span>'

METRICS = [
    ('0.2% yield strength', 'MPa', 'Yield (MPa)', 'ys'),
    ('UTS', 'MPa', 'UTS (MPa)', 'uts'),
    ('Uniform elongation', '%', 'Uniform elongation (%)', 'uniform'),
    ('Failure elongation', '%', 'Failure elongation (%)', 'el'),
    ('Tensile toughness', 'MJ/m³', 'Toughness (MJ/m^3)', None),
    ('Fitted elastic modulus', 'GPa', 'Fitted E (GPa)', 'e'),
]

# The specimen view shares the summary's property order, not the internal
# acquisition/audit dictionary. New diagnostic fields must not leak into it.
SPECIMEN_METRIC_FIELDS = {
    'Yield (MPa)': '0.2% Offset Yield Strength (MPa)',
    'Uniform elongation (%)': 'Uniform Elongation (%)',
    'Failure elongation (%)': 'Failure Elongation (%)',
}
SPECIMEN_DETAIL_FIELDS = [
    ('Fit method', 'Fit method'), ('Elastic fit R²', 'Elastic Fit R2'),
    ('Width (mm)', 'Width (mm)'), ('Thickness (mm)', 'Thickness (mm)'),
    ('AVE gauge (mm)', 'AVE dot spacing (mm)'), ('Target gauge (mm)', 'Target gauge length (mm)'),
    ('EL source for plots', 'EL plot source'),
]


def property_table_sources(label):
    if label == 'Failure elongation':
        return tuple((label, label) for label, _ in EL_SOURCE_FIELDS)
    return (('Calculated', 'Calc'), ('Instron', 'Instron'))


def property_title(label):
    return {'0.2% yield strength': '0.2% YS', 'Failure elongation': 'Elongation'}.get(label, label)


def property_column(label, unit, source):
    """Flat numeric export header matching the viewer's grouped headers."""
    return f'{property_title(label)} ({unit}) · {source}'


def specimen_label(row):
    label = row.get('Instron Specimen Label', '')
    return str(label) if pd.notna(label) and str(label).strip() else str(row['Sample'])


def specimen_display_frame(samples, comparisons):
    """One numeric column definition shared by the specimen UI and Excel."""
    columns = ['Checks']
    for label, unit, _, _ in METRICS:
        columns.extend(property_column(label, unit, short) for _, short in property_table_sources(label))
    columns.extend(label for label, _ in SPECIMEN_DETAIL_FIELDS)
    reported = {(row['Specimen ID'], row['Property']): row['Instron']
                for _, row in comparisons.iterrows()}
    rows = []
    for _, row in samples.iterrows():
        values = [row['Checks']]
        for label, _, field, _ in METRICS:
            if label == 'Failure elongation':
                values.extend(row.get(field, np.nan) for _, field in EL_SOURCE_FIELDS)
            else:
                calculated = row.get(SPECIMEN_METRIC_FIELDS.get(field, field), np.nan)
                instron = reported.get((row['Specimen ID'], label), np.nan)
                values.extend(calculated if source == 'Calculated' else instron
                              for source, _ in property_table_sources(label))
        values.extend(row.get(field, np.nan) for _, field in SPECIMEN_DETAIL_FIELDS)
        rows.append(values)
    return pd.DataFrame(rows, columns=columns, index=samples.index)


def specimen_export_frame(samples, comparisons):
    """Keep screen order and full numeric precision; append the stable audit key."""
    identity = pd.DataFrame([
        {'Include': bool(row['Included']), 'Group': row['Group'], 'Specimen': specimen_label(row),
         'Applies to': 'This graph only' if row['Inclusion Scope'] == 'graph' else 'Global default',
         'Exclusion reason': row['Exclusion Reason']}
        for _, row in samples.iterrows()
    ], columns=['Include', 'Group', 'Specimen', 'Applies to', 'Exclusion reason'], index=samples.index)
    result = pd.concat([identity, specimen_display_frame(samples, comparisons)], axis=1)
    result['Specimen ID'] = samples.get('Specimen ID', pd.Series(index=samples.index, dtype=object))
    return result


def specimen_table_data(samples, comparisons):
    """Shared property/source columns; reconstructed EL is blank unless available."""
    columns, groups = ['Checks'], [{'label': 'Checks', 'span': 1}]
    for label, unit, _, _ in METRICS:
        title = property_title(label)
        groups.append({'label': f'{title} ({unit})', 'span': len(property_table_sources(label))})
        columns.extend(short for _, short in property_table_sources(label))
    for label, _ in SPECIMEN_DETAIL_FIELDS:
        groups.append({'label': label, 'span': 1})
        columns.append(label)
    display = specimen_display_frame(samples, comparisons)

    def text_value(value, places=2):
        if pd.isna(value):
            return '—'
        return f'{value:.{places}f}' if isinstance(value, (float, np.floating)) else str(value)

    rows = []
    for position, (_, row) in enumerate(samples.iterrows()):
        values = [('' if name == property_column('Failure elongation', '%', 'Reconstruct') and pd.isna(value) else
                   text_value(value))
                  for name, value in display.iloc[position].items()]
        rows.append({'id': row['Specimen ID'], 'included': bool(row['Included']), 'group': str(row['Group']),
                     'sample': specimen_label(row), 'reason': row['Exclusion Reason'],
                     'scope': row['Inclusion Scope'], 'global_included': bool(row['Global Included']),
                     'fit_warning': bool(row['Fit review required']), 'check_warning': bool(row['Checks']),
                     'values': values})
    return columns, groups, rows


def _stats(values):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    return {'n': len(values), 'Mean': float(np.mean(values)) if len(values) else np.nan,
            'SD': float(np.std(values, ddof=1)) if len(values) > 1 else np.nan,
            'Min': float(np.min(values)) if len(values) else np.nan,
            'Max': float(np.max(values)) if len(values) else np.nan}


def specimen_check_failures(properties, reference, gauge=None):
    """One failure-only message column; retain numeric audit fields separately."""
    failures = list(reference.get('check_failures', []))
    if properties.get('Fit review required'):
        if properties.get('Yield status') != 'resolved':
            failures.append('Yield fit: ' + (properties.get('Notes') or 'unresolved fit.'))
        r2 = properties.get('Elastic fit R2', np.nan)
        threshold = properties['R2 warning threshold']
        if not np.isfinite(r2):
            failures.append('Elastic fit: R² unavailable.')
        elif r2 < threshold:
            failures.append(f'Elastic fit: R² {r2:.2f} below threshold {threshold:.2f} (checked before rounding).')
        if str(properties.get('Override status', '')).startswith('Stale'):
            failures.append('Fit override: source changed; saved override was not applied.')
    gauge = gauge or {}
    if properties.get('Fracture detection status') == 'Not detected':
        failures.append('CSV fracture not detected: ' + properties.get('Fracture detection reason', '') +
                        '. Fracture EL/toughness unavailable; inspect the full curve.')
    if gauge.get('Elongation basis') == 'Estimated standard gauge':
        if gauge.get('Gauge correction status') != 'Applied':
            failures.append('Gauge reconstruction: ' + gauge.get('Gauge correction status', 'unavailable'))
        for key in ('Gauge model warning', 'Gauge reconstruction notes'):
            if gauge.get(key):
                failures.append('Gauge reconstruction: ' + gauge[key])
    return '\n'.join(dict.fromkeys(failures))


def property_tables(records, spec, engine, instron, project=None):
    samples, diagnostics, comparison, summaries, uniform = [], [], [], [], []
    fractions = spec.get('landmark_yield_fit_fractions', engine.LANDMARK_YIELD_FIT_FRACTIONS)
    for group, rows in records.items():
        properties, references = [], []
        elongations = []
        for row in rows:
            p = engine.specimen_properties(row, fractions, engine.LANDMARK_YIELD_R2_WARNING)
            measured = engine.specimen_properties(row.get('_measured_record', row), fractions, engine.LANDMARK_YIELD_R2_WARNING)
            reference = instron.match(group, row)
            selection = selection_state(row, spec, project)
            included = selection['included']
            el_report = elongation_report(row, reference, measured)
            if included:
                properties.append(p)
                references.append(reference)
                elongations.append(el_report)
            identity = {'Included': included, 'Group': group, 'Sample': row['sample'],
                        'Specimen ID': specimen_id(row),
                        'Exclusion Reason': selection['reason'], 'Inclusion Scope': selection['scope'],
                        'Global Included': selection['global_included'], 'Global Exclusion Reason': selection['global_reason']}
            checks = specimen_check_failures(p, reference, row.get('_gauge'))
            fit_fields = {key: p[key] for key in ('Fit method', 'Override status', 'Fit review required')}
            saved_fit = row.get('_fit_override') or {}
            samples.append({**identity, 'Checks': checks, 'Instron Specimen Label': reference['label'],
                            **fit_fields, '0.2% Offset Yield Strength (MPa)': p['Yield (MPa)'],
                            'UTS (MPa)': p['UTS (MPa)'], 'Uniform Elongation (%)': p['Uniform elongation (%)'],
                            'Failure Elongation (%)': p['Failure elongation (%)'],
                            'Toughness (MJ/m^3)': p['Toughness (MJ/m^3)'], 'Fitted E (GPa)': p['Fitted E (GPa)'],
                            'Yield Strain (%)': p['Yield strain (%)'], 'Elastic Fit R2': p['Elastic fit R2'],
                            'Yield Status': p['Yield status'], 'Yield Notes': p['Notes'], 'Source File': row['source_file']})
            samples[-1].update(row.get('_gauge', {}))
            samples[-1].pop('Estimated failure elongation (%)', None)
            samples[-1].update(el_report)
            samples[-1].update({'Measured failure elongation (%)': measured['Failure elongation (%)'],
                               'Measured toughness (MJ/m^3)': measured['Toughness (MJ/m^3)'],
                               'Width (mm)': reference['values'].get('width', np.nan),
                               'Thickness (mm)': reference['values'].get('thickness', np.nan)})
            diagnostics.append({**identity, 'Checks': checks, **reference.get('check_values', {}),
                                **fit_fields, 'Source File': row['source_file'], 'Source SHA256': row.get('source_sha256', ''),
                                'R2 warning threshold': p['R2 warning threshold'], 'Fit Point Count': p['Fit point count'],
                                'Fit Lower Strain (%)': p['Fit lower strain (%)'], 'Fit Upper Strain (%)': p['Fit upper strain (%)'],
                                'Automatic 0.2% YS (MPa)': p['Automatic Yield (MPa)'],
                                'Automatic E (GPa)': p['Automatic Fitted E (GPa)'],
                                'Automatic R2': p['Automatic Elastic fit R2'],
                                'Override Reason': saved_fit.get('reason', ''), 'Override Saved At': saved_fit.get('saved_at', ''),
                                'Override Definition': json.dumps(saved_fit, sort_keys=True) if saved_fit else '',
                                'Yield Method': p['Yield method'], 'Yield Status': p['Yield status'], 'Yield Notes': p['Notes'],
                                'Fitted E (GPa)': p['Fitted E (GPa)'], 'Elastic Fit R2': p['Elastic fit R2'],
                                'Elastic Intercept (MPa)': p['Elastic intercept (MPa)'],
                                'Fit Lower Stress (MPa)': p['Fit lower stress (MPa)'], 'Fit Upper Stress (MPa)': p['Fit upper stress (MPa)'],
                                'Instron Match': reference['status'], 'Instron Row': reference['index'],
                                'Instron Specimen Label': reference['label'], 'Instron Excluded': reference['excluded'],
                                'Instron Notes': reference['notes'], 'Instron Summary CSV': reference['source'],
                                'Instron Summary SHA256': reference['sha256'],
                                'Instron Thickness (mm)': reference['values'].get('thickness', np.nan),
                                'Instron Width (mm)': reference['values'].get('width', np.nan),
                                'Instron Gauge Length (mm)': reference['values'].get('gauge', np.nan)})
            for label, unit, field, ref_key in METRICS:
                if (ref_key is None or label == 'Failure elongation' or
                        not any(source == 'Instron' for source, _ in property_table_sources(label))):
                    continue
                calculated, reported = measured[field], reference['values'].get(ref_key, np.nan)
                paired = bool(np.isfinite(calculated) and np.isfinite(reported))
                difference = calculated - reported if paired else np.nan
                comparison.append({**identity, 'Checks': checks, 'Property': label, 'Unit': unit, 'Calculated': calculated, 'Instron': reported,
                                   'Difference (calc - Instron)': difference,
                                   'Difference Unit': 'percentage points' if unit == '%' else unit,
                                   'Difference (%)': 100 * difference / reported if paired and reported != 0 else np.nan,
                                   'Paired': paired, 'Instron Match': reference['status'],
                                   'Instron Specimen Label': reference['label'], 'Instron Row': reference['index'],
                                   'Notes': ' '.join(filter(None, [p['Notes'] if ref_key in ('ys', 'e') else '', reference['notes']])),
                                   'Source File': row['source_file'], 'Instron Summary CSV': reference['source']})
        for label, unit, field, ref_key in METRICS:
            sources = ([(source, [report[key] for report in elongations]) for source, key in EL_SOURCE_FIELDS]
                       if label == 'Failure elongation' else
                       [(source, [p[field] for p in properties] if source == 'Calculated' else
                         [r['values'].get(ref_key, np.nan) for r in references])
                        for source, _ in property_table_sources(label)])
            for source, values in sources:
                summaries.append({'Group': group, 'Property': label, 'Unit': unit, 'Source': source,
                                  'Selected Specimens': len(properties), 'Available Specimens': len(rows), **_stats(values)})
        stats = _stats([p['Uniform elongation (%)'] for p in properties])
        uniform.append({'Group': group, 'n': stats['n'], 'Uniform Elongation Mean (%)': stats['Mean'],
                        'Uniform Elongation SD (%)': stats['SD']})
    comparisons = pd.DataFrame(comparison)
    paired_stats = []
    if len(comparisons):
        for (group, metric, unit), frame in comparisons.groupby(['Group', 'Property', 'Difference Unit'], sort=False):
            pairs = frame[frame['Paired'] & frame['Included']]
            difference = pairs['Difference (calc - Instron)'].to_numpy(dtype=float)
            stats = _stats(difference)
            paired_stats.append({'Group': group, 'Property': metric, 'Unit': unit, 'n paired': stats['n'],
                                 'Mean Difference': stats['Mean'], 'SD Difference': stats['SD'],
                                 'Mean Absolute Difference': float(np.mean(np.abs(difference))) if len(difference) else np.nan,
                                 'Max Absolute Difference': float(np.max(np.abs(difference))) if len(difference) else np.nan})
    details = pd.DataFrame(summaries)
    summary = summary_wide(details)
    sample_frame = pd.DataFrame(samples)
    if not sample_frame.empty and 'Elongation basis' in sample_frame:
        for group, frame in sample_frame.groupby('Group', sort=False):
            mask = summary['Group'] == group
            summary.loc[mask, 'Elongation basis'] = frame['Elongation basis'].iloc[0]
            summary.loc[mask, 'Target gauge length (mm)'] = frame['Target gauge length (mm)'].iloc[0]
            for field in ('Measured toughness (MJ/m^3)', 'Estimated toughness (MJ/m^3)'):
                for stat, value in _stats(frame.loc[frame['Included'], field]).items():
                    if stat in ('Mean', 'SD', 'n'):
                        summary.loc[mask, field + ' · ' + stat] = value
    return {'tensile_samples': sample_frame, 'tensile_summary': summary,
            'tensile_summary_details': details,
            'instron_comparison': comparisons, 'instron_comparison_summary': pd.DataFrame(paired_stats),
            'specimen_diagnostics': pd.DataFrame(diagnostics), 'uniform_elongation_summary': pd.DataFrame(uniform)}


def summary_wide(details):
    """One group per row; keep numeric means/SD/n for Excel, not formatted strings."""
    rows = []
    if details.empty:
        return pd.DataFrame()
    for group, data in details.groupby('Group', sort=False):
        row = {'Group': group, 'Included n': int(data.iloc[0]['Selected Specimens']),
               'Available n': int(data.iloc[0]['Available Specimens'])}
        for label, unit, _, _ in METRICS:
            for source, short in property_table_sources(label):
                item = data[(data.Property == label) & (data.Source == source)].iloc[0]
                for statistic in ('Mean', 'SD', 'n'):
                    column = f'{property_column(label, unit, short)} · {statistic}'
                    row[column] = item[statistic]
        rows.append(row)
    return pd.DataFrame(rows)


def summary_html(details):
    if details.empty:
        return '<p>No matching groups.</p>'
    result = ['''<style>
      .tw-summary {overflow:auto;max-height:510px;border:1px solid #cbd5e1;}
      .tw-summary table {border-collapse:separate;border-spacing:0;font:12px/1.4 Arial,sans-serif;width:100%;}
      .tw-summary th,.tw-summary td {padding:8px 10px;border-bottom:1px solid #dce3e9;white-space:nowrap;text-align:right;}
      .tw-summary th {background:#e8eef4;color:#152c3f;text-align:center;position:sticky;top:0;z-index:2;}
      .tw-summary thead tr:nth-child(2) th {top:33px;}
      .tw-summary td {background:#fff;}
      .tw-summary tbody tr:nth-child(even) td {background:#f6f8fa;}
      .tw-summary td:first-child {position:sticky;left:0;text-align:left;z-index:1;}
      .tw-summary th:first-child[rowspan] {left:0;z-index:3;}
      .tw-summary small {display:block;color:#526170;}
      .tw-summary .property-start {border-left:1px solid #cbd5e1;}
      </style><div class="tw-summary"><table><thead><tr>
      <th rowspan="2" scope="col">Group</th><th rowspan="2" scope="col">Included n</th>''']
    for label, unit, _, _ in METRICS:
        result.append(f'<th colspan="{len(property_table_sources(label))}" scope="colgroup" class="property-start">{escape(property_title(label))} ({escape(unit)})</th>')
    result.append('</tr><tr>')
    for label, _, _, _ in METRICS:
        for index, (_, short) in enumerate(property_table_sources(label)):
            css = ' class="property-start"' if index == 0 else ''
            result.append(f'<th{css} scope="col">{escape(short)}</th>')
    result.append('</tr></thead><tbody>')
    for group, data in details.groupby('Group', sort=False):
        included = int(data.iloc[0]['Selected Specimens'])
        available = int(data.iloc[0]['Available Specimens'])
        result.append(f'<tr><td>{escape(str(group))}</td><td>{included}<small>of {available}</small></td>')
        for label, unit, _, _ in METRICS:
            for index, (source, _) in enumerate(property_table_sources(label)):
                item = data[(data.Property == label) & (data.Source == source)].iloc[0]
                n = int(item['n'])
                css = ' class="property-start"' if index == 0 else ''
                if source == 'Reconstruct' and n == 0:
                    result.append(f'<td{css}></td>')
                    continue
                value = _display_cell(item['Mean'])
                if n > 1:
                    value += ' ± ' + _display_cell(item['SD'])
                if n != included:
                    value += f'<small>n = {n}</small>'
                result.append(f'<td{css}>{value}</td>')
        result.append('</tr>')
    return ''.join(result) + '</tbody></table></div>'


class PropertyTablesView:
    """Filterable, sortable HTML tables inside the existing Jupyter workbench."""
    def __init__(self, widgets, on_selection=None, inspect_loader=None, on_fit_apply=None, on_threshold=None):
        from tensile_inspector import SpecimenInspector
        w = widgets
        self.frames = {}
        self._threshold_sync = False
        self.on_threshold = on_threshold
        self.threshold = w.BoundedFloatText(value=.98, min=0, max=1, step=.001,
            description='R² warning threshold:', continuous_update=False, style={'description_width': 'initial'},
            tooltip='Flag fits below this R² for review. Does not exclude specimens or change the fit.',
            layout=w.Layout(width='300px'))
        self.threshold_status = w.HTML('Applies to all graphs; warning only.')
        self.threshold.observe(self._threshold_changed, names='value')
        self.review_only = w.Checkbox(value=False, description='Only fits needing review', indent=False,
                                     layout=w.Layout(width='auto'))
        self.filter = w.Text(description='Filter:', placeholder='Group, specimen or filename', continuous_update=False)
        self.sort = w.Dropdown(description='Sort:', options=['Group', 'Sample', '0.2% Offset Yield Strength (MPa)',
                              'UTS (MPa)'], layout=w.Layout(width='300px'))
        self.descending = w.Checkbox(description='Descending', indent=False, layout=w.Layout(width='auto'))
        self.panels = [w.HTML(layout=w.Layout(width='100%', min_width='0', overflow='hidden', margin='0')) for _ in range(2)]
        for panel in self.panels:
            panel.add_class('tw18-table-panel')
        self.inspector = SpecimenInspector(w, loader=inspect_loader, on_apply=on_fit_apply)
        self.specimens = SpecimenTable(on_selection=on_selection, on_inspect=self.open_inspector,
                                      layout=w.Layout(width='100%', min_width='0', margin='0'))
        specimen_panel = w.VBox([self.panels[1], self.specimens], layout=w.Layout(width='100%', min_width='0', overflow='hidden', margin='0'))
        self.tabs = w.Tab(children=[self.panels[0], specimen_panel, self.inspector.ui],
                          layout=w.Layout(width='100%', min_width='0', margin='0'))
        for i, name in enumerate(['Summary', 'Specimens', 'Calculation inspector']):
            self.tabs.set_title(i, name)
        self.status = w.HTML('Select sample groups to load property tables.')
        self.ui = w.VBox([w.HTML('<p>Independent of plot selection. Group statistics use sample SD and valid n. '
                                'Instron comparisons use CSV summaries, not PDFs.</p>'),
                          w.HBox([self.filter, self.sort, self.descending, self.review_only], layout=w.Layout(flex_flow='row wrap')),
                          self.status, self.tabs], layout=w.Layout(width='100%', min_width='0', overflow='hidden'))
        for control in (self.filter, self.sort, self.descending, self.review_only):
            control.observe(lambda _: self.render(), names='value')

    def set_threshold(self, value):
        self._threshold_sync = True
        try:
            self.threshold.value = value
        finally:
            self._threshold_sync = False

    def _threshold_changed(self, change):
        if self._threshold_sync or self.on_threshold is None:
            return
        try:
            self.on_threshold(change['new'])
            self.threshold_status.value = 'Saved for all graphs; warning only.'
        except Exception as error:
            self.set_threshold(change['old'])
            self.threshold_status.value = '<b>Not saved:</b> ' + escape(str(error))

    def set_frames(self, frames):
        self.frames = frames
        self.render()

    def open_inspector(self, ident):
        self.show_inspector()
        self.inspector.select(ident)

    def show_inspector(self):
        self.tabs.selected_index = 2

    def clear(self, message='Select sample groups to load property tables.'):
        self.frames = {}
        self.status.value = message
        for panel in self.panels:
            panel.value = ''
        self.specimens.rows = []
        self.specimens.context = uuid.uuid4().hex
        self.inspector.clear()

    def _filtered(self, frame):
        if frame.empty:
            return frame
        if self.review_only.value and 'Specimen ID' in frame:
            samples = self.frames['tensile_samples']
            ids = set(samples.loc[samples['Fit review required'], 'Specimen ID'])
            frame = frame[frame['Specimen ID'].isin(ids)]
        text = self.filter.value.strip().casefold()
        if text:
            keys = [key for key in ('Group', 'Sample', 'Source File', 'Instron Specimen Label') if key in frame]
            mask = np.zeros(len(frame), dtype=bool)
            for key in keys:
                mask |= frame[key].astype(str).str.casefold().str.contains(text, regex=False, na=False).to_numpy()
            frame = frame.loc[mask]
        key = self.sort.value
        return frame.sort_values(key, ascending=not self.descending.value, kind='stable') if key in frame else frame

    @staticmethod
    def _html(frame):
        if frame.empty:
            return '<p>No matching rows.</p>'
        style = ('<style>.tw18-table-panel .widget-html-content{width:100%;min-width:0;box-sizing:border-box}'
                 '.tw18-table-panel p{white-space:normal;line-height:1.4}'
                 '.tw18-table{overflow:auto;max-height:510px;width:100%;border:1px solid #cbd5e1}'
                 '.tw18-table table{border-collapse:collapse;width:100%;font-size:12px}'
                 '.tw18-table th{position:sticky;top:0;background:#e8eef4;color:#152c3f;z-index:1;text-align:left}'
                 '.tw18-table th,.tw18-table td{padding:6px 9px;border-bottom:1px solid #dce3e9;min-width:70px;max-width:450px;overflow-wrap:anywhere}'
                 '.tw18-table tbody tr:nth-child(even){background:#f6f8fa}.tw18-table td{text-align:right}'
                 '.tw18-table .tw-fit{width:210px;text-align:left;line-height:1.4}'
                 '.tw18-table .tw-fit summary{cursor:pointer;color:#1767a5;white-space:normal}'
                 '.tw18-table .tw-fit summary span{display:block;padding-left:14px;font-size:11px}'
                 '.tw18-table .tw-fit-body{max-height:220px;overflow:auto;margin-top:8px;'
                 'padding:8px;background:#fff;border:1px solid #dce3e9}'
                 '.tw18-table .tw-fit-body dl{margin:0}.tw18-table .tw-fit-body dt{font-weight:600}'
                 '.tw18-table .tw-fit-body dd{margin:0 0 8px}.tw18-table .tw-fit-body pre{'
                 'white-space:pre-wrap;overflow-wrap:anywhere;font:11px/1.4 monospace;margin:0}'
                 '.tw18-table .tw-fit-date{white-space:nowrap}'
                 '.tw18-table .tw-checks{white-space:pre-line;text-align:left;min-width:260px;max-width:420px;color:#944900;line-height:1.4}'
                 '.tw18-table .tw-path{width:clamp(160px,24vw,280px);text-align:left;font-weight:normal}'
                 '.tw18-table .tw-path summary{display:block;list-style:none;cursor:pointer;color:#1767a5;border-radius:3px}'
                 '.tw18-table .tw-path summary::-webkit-details-marker{display:none}'
                 '.tw18-table .tw-path summary:hover{text-decoration:underline}'
                 '.tw18-table .tw-path summary:focus-visible{outline:2px solid #1767a5;outline-offset:2px}'
                 '.tw18-table .tw-path-tail{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;'
                 'text-align:left;font-family:ui-monospace,SFMono-Regular,Consolas,monospace}'
                 '.tw18-table .tw-path-expanded{margin-top:6px}'
                 '.tw18-table .tw-path-hint{display:block;font-size:11px;color:#526170;margin-bottom:4px}'
                 '.tw18-table .tw-path-full{display:block;box-sizing:border-box;width:100%;min-width:0;max-width:100%;'
                 'padding:6px;border:1px solid #aebdcb;border-radius:3px;background:#fff;color:#152c3f;'
                 'font:12px/1.4 ui-monospace,SFMono-Regular,Consolas,monospace;resize:vertical;'
                 'white-space:pre-wrap;overflow-wrap:anywhere;direction:ltr;text-align:left}</style>')
        # Keep the shared numeric frames untouched: only the viewer gets HTML.
        safe = frame.rename(columns=lambda column: escape(str(column)))
        formatters = {}
        for column in frame.columns:
            if column in PATH_COLUMNS:
                formatter = lambda value, name=column: _path_cell(value, name)
            elif column == 'Override Definition':
                formatter = _override_cell
            elif column == 'Override Saved At':
                formatter = _override_date_cell
            elif column == 'Checks':
                formatter = lambda value: '<div class="tw-checks">' + escape(str(value)) + '</div>' if value else ''
            else:
                formatter = _display_cell
            formatters[escape(str(column))] = formatter
        table = safe.to_html(index=False, escape=False, border=0, na_rep='—', formatters=formatters)
        return style + '<div class="tw18-table">' + table + '</div>'

    def render(self):
        if not self.frames:
            return
        samples = self._filtered(self.frames['tensile_samples'])
        summary = self._filtered(self.frames['tensile_summary_details'])
        basis_note = ''
        if not samples.empty and 'Elongation basis' in samples:
            labels = []
            for group, frame in samples.groupby('Group', sort=False):
                basis = str(frame['EL plot source'].iloc[0])
                target = frame['Target gauge length (mm)'].iloc[0]
                if frame['Elongation basis'].iloc[0] == 'Estimated standard gauge':
                    if np.isfinite(target):
                        basis += f' ({target:.2f} mm)'
                labels.append(escape(str(group)) + ': ' + escape(basis))
            basis_note = '<p><b>EL source used for plots by group:</b> ' + '; '.join(labels) + '. Instron EL is reported separately, never used for identity verification.</p>'
        self.panels[0].value = ('<p>Mean ± sample SD of included specimens, not properties of an average curve. '
                               'Instron uses available matched values; differing valid counts are shown in each cell. '
                               'SD requires at least two values. “—” means unavailable. '
                               'Elongation: Instron = reported break result; Calc = detected CSV fracture EL; '
                               'Reconstruct = its gauge reconstruction, blank unless enabled and available. '
                               'Instron columns remain available for uniform elongation and tensile toughness. Missing fracture detection is '
                               'flagged in Checks; no final-reading fallback is used. '
                               'Values display two decimals; calculations and checks retain full precision.</p>'
                               + basis_note + summary_html(summary))
        self.panels[1].value = ('<p><b>Include</b> changes the global default for statistics, averages, work hardening and all plots. '
                               'Choose <b>This graph only</b> for an explicit exception; choose <b>Global default</b> to remove it. '
                               'Other graphs’ explicit overrides are preserved. '
                               'Unchecked specimens stay here for review and in the specimen export. '
                               'Files/folders marked with ! are ignored entirely. '
                               '<b>Checks</b> shows failures/review items only; a blank cell means none were flagged. '
                               'Click a specimen name to inspect calculations and exact comparison values.</p>'
                               '<p>For elongation, <b>Instron</b> is the reported break result, <b>Calc</b> is the '
                               'detected CSV drop onset before any landmark shape setback, and <b>Reconstruct</b> '
                               'is its gauge reconstruction, blank unless enabled and available. '
                               'Uniform elongation and tensile toughness retain <b>Calc / Instron</b> columns; '
                               'Calc toughness uses the selected measured/reconstructed basis. “—” means unavailable. '
                               'Instron uniform elongation is imported when supplied; toughness import is not yet supported. '
                               'Not-detected endpoints are flagged, not replaced with the last reading. '
                               'EL differences do not generate specimen-matching failures.</p>' + basis_note)
        columns, groups, rows = specimen_table_data(samples, self.frames['instron_comparison'])
        with self.specimens.hold_sync():
            self.specimens.columns = columns
            self.specimens.column_groups = groups
            self.specimens.rows = rows
            self.specimens.context = uuid.uuid4().hex
        self.inspector.set_rows(rows)
        included = int(samples['Included'].sum()) if not samples.empty else 0
        flagged = int(samples['Checks'].fillna('').ne('').sum()) if not samples.empty else 0
        self.status.value = (f'{len(samples)} displayed specimens · {included} included · {flagged} needing review. '
                             'Search/sort only change the view; Include changes the analysis.')
