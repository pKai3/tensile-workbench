"""Paired, measured Calc–Instron agreement; independent of publication plots."""
from html import escape
import numpy as np
import pandas as pd

COMPARISON_COLUMNS = ['Group', 'Property', 'Unit', 'Paired n', 'Mean difference (%)',
                      'SD difference (%)', 'Mean Calc', 'Mean Instron', 'SD Calc', 'SD Instron',
                      'SD change (%)', 'Pairs with checks']
PROPERTY_ORDER = ['0.2% yield strength', 'Uniform elongation', 'Failure elongation',
                  'Tensile toughness', 'Fitted elastic modulus']
PROPERTY_LABELS = {'0.2% yield strength': '0.2% YS', 'Uniform elongation': 'Uniform EL',
                   'Failure elongation': 'Failure EL', 'Fitted elastic modulus': 'Fitted E'}


def relative_comparison(frames):
    """Mean/SD of per-specimen 100*(Calc-Instron)/Instron, not ratio of means.

    Existing comparison rows use measured values. EL lives separately in the
    specimen source fields; never use the active/reconstructed EL here.
    Inclusion and existing reference assignments are preserved. Numerical
    disagreements and review flags are not silently removed from a comparison.
    """
    pairs = frames.get('instron_comparison', pd.DataFrame()).copy()
    samples = frames.get('tensile_samples', pd.DataFrame())
    el_columns = ['Included', 'Group', 'Specimen ID', 'CSV-derived fracture EL (%)', 'Instron summary EL (%)']
    if all(column in samples for column in el_columns):
        el = samples[el_columns].rename(columns={'CSV-derived fracture EL (%)': 'Calculated',
                                                'Instron summary EL (%)': 'Instron'}).copy()
        el['Property'], el['Unit'] = 'Failure elongation', '%'
        el['Checks'] = samples['Checks'] if 'Checks' in samples else ''
        pairs = pairs[pairs.Property.ne('Failure elongation')] if 'Property' in pairs else pairs
        pairs = pd.concat([pairs, el], ignore_index=True)
    required = {'Included', 'Group', 'Property', 'Unit', 'Calculated', 'Instron'}
    if pairs.empty or not required.issubset(pairs):
        return pd.DataFrame(columns=COMPARISON_COLUMNS)
    calc = pd.to_numeric(pairs['Calculated'], errors='coerce')
    instron = pd.to_numeric(pairs['Instron'], errors='coerce')
    valid = pairs['Included'].fillna(False).astype(bool) & np.isfinite(calc) & np.isfinite(instron) & instron.ne(0)
    pairs = pairs.loc[valid].copy()
    pairs['Calculated'], pairs['Instron'] = calc.loc[valid], instron.loc[valid]
    pairs['Relative difference'] = 100 * (pairs['Calculated'] - pairs['Instron']) / pairs['Instron']
    pairs = pairs[np.isfinite(pairs['Relative difference'])]
    if 'Specimen ID' in pairs:
        pairs = pairs.drop_duplicates(['Group', 'Property', 'Specimen ID'])
    rows = []
    for (group, prop, unit), data in pairs.groupby(['Group', 'Property', 'Unit'], sort=False):
        differences = data['Relative difference']
        checks = data['Checks'].fillna('').astype(str).str.strip().ne('') if 'Checks' in data else []
        calc_sd = data['Calculated'].std(ddof=1) if len(data) > 1 else np.nan
        instron_sd = data['Instron'].std(ddof=1) if len(data) > 1 else np.nan
        sd_change = 100 * (calc_sd / instron_sd - 1) if np.isfinite(instron_sd) and instron_sd > 0 else np.nan
        rows.append({'Group': group, 'Property': prop, 'Unit': unit, 'Paired n': len(data),
                     'Mean difference (%)': differences.mean(),
                     'SD difference (%)': differences.std(ddof=1) if len(data) > 1 else np.nan,
                     'Mean Calc': data['Calculated'].mean(), 'Mean Instron': data['Instron'].mean(),
                     'SD Calc': calc_sd, 'SD Instron': instron_sd,
                     'SD change (%)': sd_change if np.isfinite(sd_change) else np.nan,
                     'Pairs with checks': int(sum(checks))})
    return pd.DataFrame(rows, columns=COMPARISON_COLUMNS)


def comparison_properties(summary):
    # UTS is an identity/data-integrity check, not an agreement plot.
    available = summary.loc[summary['Property'].ne('UTS'), 'Property'].tolist()
    return list(dict.fromkeys([p for p in PROPERTY_ORDER if p in available] + available))


def comparison_columns(summary, width):
    return min(max(1, len(comparison_properties(summary))), 3 if width >= 1050 else 2 if width >= 700 else 1)


def size_comparison(figure, width):
    figure.update_layout(width=max(240, int(width)), height=280,
                         margin={'l': 58, 'r': 12, 't': 40, 'b': 60})


def comparison_figure(summary, *, width=360, groups=None):
    """One compact independent property panel; SD comparison lives below it."""
    import plotly.graph_objects as go
    from plotly.colors import qualitative
    from tensile_plotly import wrapped
    if summary['Property'].nunique() != 1 or not comparison_properties(summary):
        raise ValueError('Select one non-UTS property for a comparison panel.')
    prop = summary['Property'].iloc[0]
    groups = summary['Group'].drop_duplicates().tolist() if groups is None else list(groups)
    data = summary.set_index('Group').reindex(groups)
    custom = [[int(row['Paired n']), row['Mean Calc'], row['Mean Instron'], escape(str(row['Unit'])),
               int(row['Pairs with checks']),
               f"{row['SD difference (%)']:.5g}%" if np.isfinite(row['SD difference (%)']) else 'Unavailable (n=1)']
              if pd.notna(row['Paired n']) else [None] * 6 for _, row in data.iterrows()]
    figure = go.Figure(go.Bar(name=PROPERTY_LABELS.get(prop, prop), showlegend=False,
        x=[wrapped(str(group), 16) for group in groups], meta={'property': prop},
        y=[v if np.isfinite(v) else None for v in data['Mean difference (%)']],
        marker={'color': [qualitative.Plotly[i % len(qualitative.Plotly)] for i in range(len(groups))]},
        error_y={'type': 'data', 'array': [v if np.isfinite(v) else None for v in data['SD difference (%)']],
                 'visible': True, 'thickness': 1.2, 'width': 4}, customdata=custom,
        hovertemplate=PROPERTY_LABELS.get(prop, prop) + '<br>%{x}<br>Mean paired difference: %{y:.5g}%'
            '<br>SD of differences: %{customdata[5]}<br>Paired n: %{customdata[0]}'
            '<br>Mean Calc: %{customdata[1]:.2f} %{customdata[3]}'
            '<br>Mean Instron: %{customdata[2]:.2f} %{customdata[3]}'
            '<br>Pairs with review checks: %{customdata[4]}<extra></extra>'))
    figure.update_yaxes(title_text='Difference (%)', title_standoff=8, automargin=True,
        zeroline=True, zerolinewidth=2, zerolinecolor='#475569', rangemode='tozero', matches=None)
    figure.update_xaxes(title_text='Sample group', title_standoff=8, automargin=True, tickangle=0)
    figure.update_layout(template='plotly_white', bargap=.4, showlegend=False,
                         title={'text': escape(PROPERTY_LABELS.get(prop, prop)), 'x': .5, 'font': {'size': 14}},
                         font={'family': 'Arial, sans-serif', 'size': 11}, hovermode='closest', dragmode='zoom')
    size_comparison(figure, width)
    return figure


def spread_table(summary):
    """Original-unit sample SDs on exactly the same paired population."""
    def number(value, *, signed=False):
        if not np.isfinite(value):
            return '—'
        label = f'{value:+.2f}' if signed else f'{value:.2f}'
        if value != 0 and abs(value) < .005:
            label = ('−' if value < 0 else '+' if signed else '') + '<0.01'
        return '<span title="' + escape(f'{value:.10g}') + '">' + escape(label) + '</span>'

    unit = escape(str(summary['Unit'].iloc[0]))
    rows = []
    for _, row in summary.iterrows():
        rows.append('<tr><th scope="row">' + escape(str(row['Group'])) + '</th>'
                    f'<td>{int(row["Paired n"])}</td><td>' + number(row['SD Instron']) + '</td><td>'
                    + number(row['SD Calc']) + '</td><td>' + number(row['SD change (%)'], signed=True) + '</td></tr>')
    return ('<style>.tw-comparison-spread{font:11px/1.4 Arial,sans-serif;overflow-x:auto;padding:0 6px 8px}'
            '.tw-comparison-spread table{border-collapse:collapse;width:100%}'
            '.tw-comparison-spread caption{text-align:left;font-weight:600;padding:4px 0}'
            '.tw-comparison-spread th,.tw-comparison-spread td{padding:4px;border-bottom:1px solid #e2e8f0;text-align:right}'
            '.tw-comparison-spread th:first-child{text-align:left;overflow-wrap:anywhere}'
            '.tw-comparison-spread thead{background:#f1f5f9}</style>'
            '<div class="tw-comparison-spread"><table><caption>Spread · SD (' + unit + ')</caption>'
            '<thead><tr><th>Group</th><th>n</th><th>Instron</th><th>Calc</th><th>Δ SD (%)</th></tr></thead>'
            '<tbody>' + ''.join(rows) + '</tbody></table></div>')


class ComparisonView:
    """Lazy summary chart: opening the fold never reruns specimen calculations."""
    def __init__(self, widgets):
        self.w = widgets
        self.summary = pd.DataFrame(columns=COMPARISON_COLUMNS)
        self.charts, self.probe, self._owned = {}, None, []
        self.box = widgets.VBox(layout=widgets.Layout(width='100%', min_width='0'))
        self.grid = widgets.GridBox(layout=widgets.Layout(width='100%', min_width='0', grid_gap='12px',
                                                           align_items='flex-start'))
        self.note = widgets.HTML(
            '<p style="white-space:normal;line-height:1.5">Mean Calc–Instron differences ±1 SD; '
            '<b>independent scales per property.</b> UTS discrepancies remain in specimen Checks, not these plots.</p>'
            '<details><summary>How to read agreement and spread</summary>'
            '<p style="white-space:normal;line-height:1.5">For each included specimen with both values: '
            '<b>100 × (Calc − Instron) / Instron</b>. Bars show the group mean of these paired differences; '
            'error bars show ±1 sample SD, not confidence intervals. Zero means agreement; positive means Calc is higher. '
            'Hover for paired n and original-unit means. Missing, nonfinite and zero Instron values are omitted; n=1 has no SD bar. '
            'Below each chart, sample SDs use exactly the same paired specimens. '
            '<b>Δ SD (%) = 100 × (SD Calc / SD Instron − 1)</b>; negative means less scatter in Calc, '
            'not necessarily greater accuracy. This is distinct from the chart’s SD of paired differences. '
            'SDs are unavailable for n&lt;2; percentage change is also unavailable for zero Instron SD. '
            '<b>Measured values only:</b> gauge reconstruction is not compared with uncorrected Instron. '
            'Failure EL endpoints may differ between methods. Existing specimen checks remain applicable; '
            'disagreements are not automatically excluded.</p></details>')
        self.ui = widgets.Accordion(children=[widgets.VBox([self.note, self.box])], selected_index=None,
                                    layout=widgets.Layout(width='100%', min_width='0'))
        self.ui.set_title(0, 'Calc–Instron comparison · percentage differences')
        self.ui.observe(lambda _: self._render() if self.ui.selected_index is not None else None, names='selected_index')

    def _dispose(self):
        self.box.children = ()
        self.grid.children = ()
        for widget in reversed(self._owned):
            widget.close()
        self.charts, self.probe, self._owned = {}, None, []

    def clear(self):
        self._dispose()
        self.summary = pd.DataFrame(columns=COMPARISON_COLUMNS)

    def set_frames(self, frames, groups):
        summary = relative_comparison(frames)
        summary = summary[summary['Group'].isin(groups)].reset_index(drop=True)
        if summary.equals(self.summary):
            return
        self.summary = summary
        self._dispose()
        if self.ui.selected_index is not None:
            self._render()

    def _render(self):
        if self.charts:
            return
        properties = comparison_properties(self.summary)
        if not properties:
            self._dispose()
            message = self.w.HTML('No included specimens have usable non-UTS comparison pairs for these groups. '
                                 'UTS discrepancies are reported in specimen Checks.')
            self._owned.append(message)
            self.box.children = (message,)
            return
        try:
            import plotly.graph_objects as go
            from tensile_plotly import width_probe
            groups = self.summary['Group'].drop_duplicates().tolist()
            cards = []
            for prop in properties:
                data = self.summary[self.summary['Property'].eq(prop)]
                chart = go.FigureWidget(comparison_figure(data, groups=groups))
                chart._config = {**chart._config, 'displaylogo': False, 'responsive': True}
                spread = self.w.HTML(spread_table(data), layout=self.w.Layout(width='100%', min_width='0'))
                card = self.w.VBox([chart, spread], layout=self.w.Layout(
                    width='100%', min_width='0', border='1px solid #e2e8f0', overflow='hidden'))
                self._owned.extend([chart, spread, card])
                self.charts[prop] = chart
                cards.append(card)
            self.grid.children = tuple(cards)
            self.probe = width_probe(self._resize)
            self._owned.append(self.probe)
            self.box.children = (self.probe, self.grid)
            self._resize(1200)
        except Exception as error:
            self._dispose()
            message = self.w.HTML('Comparison chart unavailable: ' + escape(str(error)))
            self._owned.append(message)
            self.box.children = (message,)

    def _resize(self, width):
        if not self.charts:
            return
        self._columns = comparison_columns(self.summary, width)
        self.grid.layout.grid_template_columns = f'repeat({self._columns}, minmax(0, 1fr))'
        panel_width = (width - 12 * (self._columns - 1)) / self._columns - 2
        for chart in self.charts.values():
            size_comparison(chart, panel_width)
