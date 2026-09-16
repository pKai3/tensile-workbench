"""Shared numeric tables for the viewer and Excel export. No plot dependencies."""
from html import escape
import numpy as np
import pandas as pd
import uuid
from tensile_selection import specimen_id, is_included
from tensile_specimens import SpecimenTable

PATH_COLUMNS = frozenset(('Source File', 'Instron Summary CSV'))


def _display_cell(value):
    """Escape ordinary cells before inserting our own path controls as HTML."""
    if pd.isna(value):
        return '—'
    if isinstance(value, (float, np.floating)):
        return f'{value:.3f}'
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

METRICS = [
    ('0.2% yield strength', 'MPa', 'Yield (MPa)', 'ys'),
    ('UTS', 'MPa', 'UTS (MPa)', 'uts'),
    ('Uniform elongation', '%', 'Uniform elongation (%)', 'uniform'),
    ('Failure elongation', '%', 'Failure elongation (%)', 'el'),
    ('Tensile toughness', 'MJ/m³', 'Toughness (MJ/m^3)', None),
    ('Fitted elastic modulus', 'GPa', 'Fitted E (GPa)', 'e'),
]


def _stats(values):
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    return {'n': len(values), 'Mean': float(np.mean(values)) if len(values) else np.nan,
            'SD': float(np.std(values, ddof=1)) if len(values) > 1 else np.nan,
            'Min': float(np.min(values)) if len(values) else np.nan,
            'Max': float(np.max(values)) if len(values) else np.nan}


def property_tables(records, spec, engine, instron):
    samples, diagnostics, comparison, summaries, uniform = [], [], [], [], []
    fractions = spec.get('landmark_yield_fit_fractions', engine.LANDMARK_YIELD_FIT_FRACTIONS)
    for group, rows in records.items():
        properties, references = [], []
        for row in rows:
            p = engine.specimen_properties(row, fractions, engine.LANDMARK_YIELD_R2_WARNING)
            reference = instron.match(group, row)
            included = is_included(row, spec)
            if included:
                properties.append(p)
                references.append(reference)
            identity = {'Included': included, 'Group': group, 'Sample': row['sample'],
                        'Specimen ID': specimen_id(row),
                        'Exclusion Reason': spec.get('specimen_exclusions', {}).get(specimen_id(row), '')}
            samples.append({**identity, '0.2% Offset Yield Strength (MPa)': p['Yield (MPa)'],
                            'UTS (MPa)': p['UTS (MPa)'], 'Uniform Elongation (%)': p['Uniform elongation (%)'],
                            'Failure Elongation (%)': p['Failure elongation (%)'],
                            'Toughness (MJ/m^3)': p['Toughness (MJ/m^3)'], 'Fitted E (GPa)': p['Fitted E (GPa)'],
                            'Yield Strain (%)': p['Yield strain (%)'], 'Elastic Fit R2': p['Elastic fit R2'],
                            'Yield Status': p['Yield status'], 'Yield Notes': p['Notes'], 'Source File': row['source_file']})
            diagnostics.append({**identity, 'Source File': row['source_file'], 'Source SHA256': row.get('source_sha256', ''),
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
                if ref_key is None:
                    continue
                calculated, reported = p[field], reference['values'].get(ref_key, np.nan)
                paired = bool(np.isfinite(calculated) and np.isfinite(reported))
                difference = calculated - reported if paired else np.nan
                comparison.append({**identity, 'Property': label, 'Unit': unit, 'Calculated': calculated, 'Instron': reported,
                                   'Difference (calc - Instron)': difference,
                                   'Difference Unit': 'percentage points' if unit == '%' else unit,
                                   'Difference (%)': 100 * difference / reported if paired and reported != 0 else np.nan,
                                   'Paired': paired, 'Instron Match': reference['status'],
                                   'Instron Specimen Label': reference['label'], 'Instron Row': reference['index'],
                                   'Notes': ' '.join(filter(None, [p['Notes'] if ref_key in ('ys', 'e') else '', reference['notes']])),
                                   'Source File': row['source_file'], 'Instron Summary CSV': reference['source']})
        for label, unit, field, ref_key in METRICS:
            for source, values in [('Calculated', [p[field] for p in properties]),
                                   ('Instron', [r['values'].get(ref_key, np.nan) for r in references])]:
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
    return {'tensile_samples': pd.DataFrame(samples), 'tensile_summary': summary_wide(details),
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
            for source, short in [('Calculated', 'Calc'), ('Instron', 'Instron')]:
                item = data[(data.Property == label) & (data.Source == source)].iloc[0]
                for statistic in ('Mean', 'SD', 'n'):
                    row[f'{label} ({unit}) · {short} {statistic}'] = item[statistic]
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
        result.append(f'<th colspan="2" scope="colgroup" class="property-start">{escape(label)} ({escape(unit)})</th>')
    result.append('</tr><tr>' + '<th class="property-start" scope="col">Calc</th><th scope="col">Instron</th>' * len(METRICS) + '</tr></thead><tbody>')
    for group, data in details.groupby('Group', sort=False):
        included = int(data.iloc[0]['Selected Specimens'])
        available = int(data.iloc[0]['Available Specimens'])
        result.append(f'<tr><td>{escape(str(group))}</td><td>{included}<small>of {available}</small></td>')
        for label, unit, _, _ in METRICS:
            for source in ('Calculated', 'Instron'):
                item = data[(data.Property == label) & (data.Source == source)].iloc[0]
                n = int(item['n'])
                value = _display_cell(item['Mean'])
                if n > 1:
                    value += ' ± ' + _display_cell(item['SD'])
                if n != included:
                    value += f'<small>n = {n}</small>'
                css = ' class="property-start"' if source == 'Calculated' else ''
                result.append(f'<td{css}>{value}</td>')
        result.append('</tr>')
    return ''.join(result) + '</tbody></table></div>'


class PropertyTablesView:
    """Filterable, sortable HTML tables inside the existing Jupyter workbench."""
    def __init__(self, widgets, on_selection=None):
        w = widgets
        self.frames = {}
        self.filter = w.Text(description='Filter:', placeholder='Group, specimen or filename', continuous_update=False)
        self.metric = w.Dropdown(description='Compare:', options=[m[0] for m in METRICS if m[3]], value=METRICS[0][0],
                                 layout=w.Layout(width='330px'))
        self.sort = w.Dropdown(description='Sort:', options=['Group', 'Sample', '0.2% Offset Yield Strength (MPa)',
                              'UTS (MPa)', 'Difference (calc - Instron)', 'Difference (%)'], layout=w.Layout(width='300px'))
        self.descending = w.Checkbox(description='Descending', indent=False, layout=w.Layout(width='auto'))
        self.panels = [w.HTML(layout=w.Layout(width='100%', min_width='0', overflow='hidden', margin='0')) for _ in range(4)]
        for panel in self.panels:
            panel.add_class('tw18-table-panel')
        self.specimens = SpecimenTable(on_selection=on_selection, layout=w.Layout(width='100%', min_width='0', margin='0'))
        specimen_panel = w.VBox([self.panels[1], self.specimens], layout=w.Layout(width='100%', min_width='0', overflow='hidden', margin='0'))
        self.tabs = w.Tab(children=[self.panels[0], specimen_panel, *self.panels[2:]],
                          layout=w.Layout(width='100%', min_width='0', margin='0'))
        for i, name in enumerate(['Summary', 'Specimens', 'Instron', 'Checks']):
            self.tabs.set_title(i, name)
        self.status = w.HTML('Select sample groups to load property tables.')
        self.ui = w.VBox([w.HTML('<p>Independent of plot selection. Group statistics use sample SD and valid n. '
                                'Instron comparisons use CSV summaries, not PDFs.</p>'),
                          w.HBox([self.filter, self.sort, self.descending], layout=w.Layout(flex_flow='row wrap')),
                          self.metric, self.status, self.tabs], layout=w.Layout(width='100%', min_width='0', overflow='hidden'))
        for control in (self.filter, self.sort, self.descending, self.metric):
            control.observe(lambda _: self.render(), names='value')

    def set_frames(self, frames):
        self.frames = frames
        self.render()

    def clear(self, message='Select sample groups to load property tables.'):
        self.frames = {}
        self.status.value = message
        for panel in self.panels:
            panel.value = ''
        self.specimens.rows = []
        self.specimens.context = uuid.uuid4().hex

    def _filtered(self, frame):
        if frame.empty:
            return frame
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
        formatters = {escape(str(column)): ((lambda value, name=column: _path_cell(value, name))
                                            if column in PATH_COLUMNS else _display_cell)
                      for column in frame.columns}
        table = safe.to_html(index=False, escape=False, border=0, na_rep='—', formatters=formatters)
        return style + '<div class="tw18-table">' + table + '</div>'

    def render(self):
        if not self.frames:
            return
        samples = self._filtered(self.frames['tensile_samples'])
        summary = self._filtered(self.frames['tensile_summary_details'])
        comparison = self._filtered(self.frames['instron_comparison'])
        diagnostic = self._filtered(self.frames['specimen_diagnostics'])
        comparison = comparison[comparison['Property'] == self.metric.value] if not comparison.empty else comparison
        self.panels[0].value = ('<p>Mean ± sample SD of included specimens, not properties of an average curve. '
                               'Instron uses available matched values; differing valid counts are shown in each cell. '
                               'SD requires at least two values. “—” means unavailable.</p>' + summary_html(summary))
        self.panels[1].value = ('<p><b>Include</b> applies to this graph only: statistics, averages, work hardening and all plots. '
                               'Unchecked specimens stay here for review and in the specimen export. '
                               'Files/folders marked with ! are ignored entirely.</p>')
        hidden = {'Included', 'Group', 'Sample', 'Specimen ID', 'Exclusion Reason', 'Source File'}
        columns = [column for column in samples.columns if column not in hidden]
        def text_value(value):
            if pd.isna(value):
                return '—'
            return f'{value:.3f}' if isinstance(value, (float, np.floating)) else str(value)
        rows = [{'id': row['Specimen ID'], 'included': bool(row['Included']), 'group': str(row['Group']),
                 'sample': str(row['Sample']), 'reason': row['Exclusion Reason'],
                 'values': [text_value(row[column]) for column in columns]} for _, row in samples.iterrows()]
        with self.specimens.hold_sync():
            self.specimens.columns = ['0.2% YS (MPa)' if column == '0.2% Offset Yield Strength (MPa)' else column
                                      for column in columns]
            self.specimens.rows = rows
            self.specimens.context = uuid.uuid4().hex
        unit = next(('pp' if m[1] == '%' else m[1]) for m in METRICS if m[0] == self.metric.value)
        shown = comparison.drop(columns=['Source File', 'Instron Summary CSV', 'Specimen ID', 'Paired', 'Property', 'Unit',
                                          'Difference Unit', 'Instron Specimen Label', 'Instron Row'], errors='ignore')
        shown = shown.rename(columns={'Difference (calc - Instron)': f'Δ ({unit})', 'Difference (%)': 'Δ (%)', 'Instron Match': 'Match'})
        self.panels[2].value = ('<p>Δ = calculated − Instron; Δ (%) is relative to Instron. This is not a pass/fail test. '
                               'See Checks for identity, elastic-fit details and source files.</p>' + self._html(shown))
        self.panels[3].value = self._html(diagnostic.drop(columns=['Specimen ID', 'Source SHA256', 'Instron Summary SHA256'], errors='ignore'))
        matched = int((comparison['Paired'] & comparison['Included']).sum()) if not comparison.empty else 0
        included = int(samples['Included'].sum()) if not samples.empty else 0
        self.status.value = (f'{len(samples)} displayed specimens · {included} included · {matched} included paired comparisons '
                             f'for {self.metric.value}. Search/sort only change the view; Include changes the analysis.')
