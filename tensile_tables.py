"""Shared numeric tables for the viewer and Excel export. No plot dependencies."""
from html import escape
import numpy as np
import pandas as pd

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
            properties.append(p)
            references.append(reference)
            identity = {'Group': group, 'Sample': row['sample']}
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
                if source == 'Instron' and ref_key is None:
                    continue
                summaries.append({'Group': group, 'Property': label, 'Unit': unit, 'Source': source,
                                  'Selected Specimens': len(rows), **_stats(values)})
        stats = _stats([p['Uniform elongation (%)'] for p in properties])
        uniform.append({'Group': group, 'n': stats['n'], 'Uniform Elongation Mean (%)': stats['Mean'],
                        'Uniform Elongation SD (%)': stats['SD']})
    comparisons = pd.DataFrame(comparison)
    paired_stats = []
    if len(comparisons):
        for (group, metric, unit), frame in comparisons.groupby(['Group', 'Property', 'Difference Unit'], sort=False):
            pairs = frame[frame['Paired']]
            difference = pairs['Difference (calc - Instron)'].to_numpy(dtype=float)
            stats = _stats(difference)
            paired_stats.append({'Group': group, 'Property': metric, 'Unit': unit, 'n paired': stats['n'],
                                 'Mean Difference': stats['Mean'], 'SD Difference': stats['SD'],
                                 'Mean Absolute Difference': float(np.mean(np.abs(difference))) if len(difference) else np.nan,
                                 'Max Absolute Difference': float(np.max(np.abs(difference))) if len(difference) else np.nan})
    return {'tensile_samples': pd.DataFrame(samples), 'tensile_summary': pd.DataFrame(summaries),
            'instron_comparison': comparisons, 'instron_comparison_summary': pd.DataFrame(paired_stats),
            'specimen_diagnostics': pd.DataFrame(diagnostics), 'uniform_elongation_summary': pd.DataFrame(uniform)}


class PropertyTablesView:
    """Filterable, sortable HTML tables inside the existing Jupyter workbench."""
    def __init__(self, widgets):
        w = widgets
        self.frames = {}
        self.filter = w.Text(description='Filter:', placeholder='Group, specimen or filename', continuous_update=False)
        self.metric = w.Dropdown(description='Compare:', options=[m[0] for m in METRICS if m[3]], value=METRICS[0][0],
                                 layout=w.Layout(width='330px'))
        self.sort = w.Dropdown(description='Sort:', options=['Group', 'Sample', '0.2% Offset Yield Strength (MPa)',
                              'UTS (MPa)', 'Difference (calc - Instron)', 'Difference (%)'], layout=w.Layout(width='300px'))
        self.descending = w.Checkbox(description='Descending', indent=False, layout=w.Layout(width='auto'))
        self.panels = [w.HTML(layout=w.Layout(width='100%', min_width='0', overflow='hidden')) for _ in range(4)]
        for panel in self.panels:
            panel.add_class('tw18-table-panel')
        self.tabs = w.Tab(children=self.panels, layout=w.Layout(width='100%', min_width='0'))
        for i, name in enumerate(['Summary', 'Specimens', 'Instron', 'Checks']):
            self.tabs.set_title(i, name)
        self.status = w.HTML('Select sample groups to load property tables.')
        self.ui = w.VBox([w.HTML('<h3>Specimen properties</h3><p>Independent of plot selection. Group statistics use sample SD and valid n. '
                                'Instron comparisons use CSV summaries, not PDFs.</p>'),
                          w.HBox([self.filter, self.sort, self.descending], layout=w.Layout(flex_flow='row wrap')),
                          self.metric, self.status, self.tabs], layout=w.Layout(width='100%'))
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
        summary = self._filtered(self.frames['tensile_summary'])
        comparison = self._filtered(self.frames['instron_comparison'])
        diagnostic = self._filtered(self.frames['specimen_diagnostics'])
        comparison = comparison[comparison['Property'] == self.metric.value] if not comparison.empty else comparison
        self.panels[0].value = '<p>Means of individual specimen properties, not properties of an average curve. Instron means use only matched selected specimens.</p>' + self._html(summary)
        self.panels[1].value = self._html(samples.drop(columns=['Source File'], errors='ignore'))
        unit = next(('pp' if m[1] == '%' else m[1]) for m in METRICS if m[0] == self.metric.value)
        shown = comparison.drop(columns=['Source File', 'Instron Summary CSV', 'Paired', 'Property', 'Unit',
                                          'Difference Unit', 'Instron Specimen Label', 'Instron Row'], errors='ignore')
        shown = shown.rename(columns={'Difference (calc - Instron)': f'Δ ({unit})', 'Difference (%)': 'Δ (%)', 'Instron Match': 'Match'})
        self.panels[2].value = ('<p>Δ = calculated − Instron; Δ (%) is relative to Instron. This is not a pass/fail test. '
                               'See Checks for identity, elastic-fit details and source files.</p>' + self._html(shown))
        self.panels[3].value = self._html(diagnostic.drop(columns=['Source SHA256', 'Instron Summary SHA256'], errors='ignore'))
        matched = int(comparison['Paired'].sum()) if not comparison.empty else 0
        self.status.value = f'{len(samples)} displayed specimens · {matched} paired comparisons for {self.metric.value}. Filtering is for display only; exports retain all selected specimens.'
