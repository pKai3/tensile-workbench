"""Read-only, on-demand inspection of the shared specimen-property calculation."""
from html import escape

import numpy as np


def inspection_ranges(calculation, mode='yield'):
    """Explicit reset ranges, independent of the publication plot settings."""
    x, y = calculation['strain_pct'], calculation['stress_mpa']
    if not len(x):
        return [0, 1], [0, 1]
    p = calculation['properties']
    left, right = min(0., float(x[0])), float(x[-1])
    if mode == 'yield':
        candidates = x[calculation['elastic_mask']].tolist()
        if np.isfinite(p['Yield strain (%)']):
            candidates.append(p['Yield strain (%)'])
        # With an unresolved yield, show the fit plus some material beyond it.
        right = min(right, max(candidates) * 1.3 + .2 if candidates else max(1., right * .15))
    span = max(right - left, .1)
    upper = max(1., float(np.max(y)))
    lower = min(0., float(np.min(y)))
    return [left - .02 * span, right + .04 * span], [lower - .03 * upper, upper * 1.12]


def inspection_figure(payload, mode='yield'):
    """Plot exact prepared points, not a mean/landmark or WH-filtered curve."""
    import plotly.graph_objects as go

    calculation = payload['calculation']
    x, y = calculation['strain_pct'], calculation['stress_mpa']
    p = calculation['properties']
    fig = go.Figure()

    def line(name, xs, ys, color, **kwargs):
        fig.add_trace(go.Scatter(x=np.asarray(xs).tolist(), y=np.asarray(ys).tolist(),
            name=name, mode='lines', line=dict(color=color, **kwargs),
            hovertemplate=escape(name) + '<br>Strain: %{x:.4f}%<br>Stress: %{y:.3f} MPa<extra></extra>'))

    def points(name, xs, ys, color, symbol='circle', size=9):
        fig.add_trace(go.Scatter(x=np.asarray(xs).tolist(), y=np.asarray(ys).tolist(),
            name=name, mode='markers', marker=dict(color=color, symbol=symbol, size=size),
            hovertemplate=escape(name) + '<br>Strain: %{x:.4f}%<br>Stress: %{y:.3f} MPa<extra></extra>'))

    line('Measured curve (prepared)', x, y, '#334155', width=2)
    mask = calculation['elastic_mask']
    if mask.any():
        points('Elastic-fit points', x[mask], y[mask], '#16a085', size=6)
        fig.add_shape(type='rect', x0=float(x[mask].min()), x1=float(x[mask].max()),
            y0=p['Fit lower stress (MPa)'], y1=p['Fit upper stress (MPa)'],
            fillcolor='rgba(22,160,133,0.10)', line_width=0, layer='below')
    modulus = p['Fitted E (GPa)'] * 1000
    if np.isfinite(modulus) and modulus > 0:
        # Define the lines over the visible stress range, not to full fracture strain.
        stresses = np.array([0., max(1., p['UTS (MPa)']) * 1.10])
        strains = (stresses - p['Elastic intercept (MPa)']) / modulus * 100
        line('Elastic fit', strains, stresses, '#16a085', dash='dash', width=1.8)
        line('0.2% offset line', strains + .2, stresses, '#d97706', dash='dash', width=1.8)
    if p['Yield status'] == 'resolved':
        points('Calculated 0.2% YS', [p['Yield strain (%)']], [p['Yield (MPa)']], '#d97706', 'diamond', 12)
    if calculation['uts_index'] is not None:
        peak = calculation['uts_index']
        points('UTS / uniform elongation', [x[peak]], [y[peak]], '#2563eb', 'circle', 11)
        points('Terminal point / failure EL', [x[-1]], [y[-1]], '#9333ea', 'x', 11)
    reported = payload['reference'].get('values', {}).get('ys', np.nan)
    if np.isfinite(reported) and len(x):
        line('Instron YS (stress only)', [min(0., x[0]), x[-1]], [reported, reported],
             '#be185d', dash='dot', width=1.8)
    xrange, yrange = inspection_ranges(calculation, mode)
    fig.update_layout(template='plotly_white', autosize=True, height=620,
        margin=dict(l=72, r=25, t=22, b=190), font=dict(family='Arial, sans-serif', size=12),
        xaxis=dict(title='Engineering strain (%)', range=xrange, automargin=True),
        yaxis=dict(title='Engineering stress (MPa)', range=yrange, automargin=True),
        legend=dict(orientation='h', x=0, xanchor='left', y=-.23, yanchor='top',
                    entrywidth=240, font=dict(size=11)), hovermode='closest', dragmode='zoom')
    return fig


def inspection_summary(payload):
    """Display fit provenance and available Instron values without inventing matches."""
    calculation, reference = payload['calculation'], payload['reference']
    p, values = calculation['properties'], reference.get('values', {})

    def number(value, places=3):
        return f'{value:.{places}f}' if np.isfinite(value) else '—'

    metrics = [('0.2% YS (MPa)', 'Yield (MPa)', 'ys'),
               ('UTS (MPa)', 'UTS (MPa)', 'uts'),
               ('Uniform elongation (%)', 'Uniform elongation (%)', 'uniform'),
               ('Failure EL (%)', 'Failure elongation (%)', 'el'),
               ('Fitted E (GPa)', 'Fitted E (GPa)', 'e')]
    result = ['<style>.tw-inspect-summary{font:13px/1.5 Arial,sans-serif;white-space:normal;overflow-wrap:anywhere}'
              '.tw-inspect-summary table{border-collapse:collapse;width:100%;max-width:850px}'
              '.tw-inspect-summary th,.tw-inspect-summary td{padding:6px 12px;border-bottom:1px solid #dce3e9;text-align:right}'
              '.tw-inspect-summary th:first-child,.tw-inspect-summary td:first-child{text-align:left}'
              '.tw-inspect-summary th{background:#e8eef4}.tw-inspect-summary details{margin:8px 0}'
              '.tw-inspect-warning{padding:8px;background:#fff4dc;border-left:3px solid #d97706}</style>',
              '<div class="tw-inspect-summary">',
              '<p><b>' + escape(payload['group'] + ' · ' + payload['sample']) + '</b> · ' +
              ('Included in this graph' if payload['included'] else 'Excluded from this graph; inspection only') + '</p>']
    if payload.get('exclusion_reason'):
        result.append('<p>Exclusion reason: ' + escape(payload['exclusion_reason']) + '</p>')
    result.append('<table><thead><tr><th>Property</th><th>Calculated</th><th>Instron</th>'
                  '<th>Δ (Calc − Instron)</th></tr></thead><tbody>')
    for label, field, key in metrics:
        calculated, reported = p[field], values.get(key, np.nan)
        result.append('<tr><td>' + escape(label) + '</td><td>' + number(calculated) + '</td><td>' +
                      number(reported) + '</td><td>' + number(calculated - reported) + '</td></tr>')
    result.append('</tbody></table><p>Δ uses the displayed units; elongation differences are percentage points. '
                  'Instron YS is drawn as a horizontal reference only; its yield strain is not inferred.</p>')
    if p['Yield status'] != 'resolved' or p['Notes']:
        result.append('<p class="tw-inspect-warning"><b>Yield ' + escape(p['Yield status']) + ':</b> ' +
                      escape(p['Notes']) + '</p>')
    low, high = calculation['fit_fractions']
    result.append(f'<p>Elastic fit: {100 * low:g}–{100 * high:g}% of this specimen’s UTS, before the first UTS point '
                  f'({number(p["Fit lower stress (MPa)"])}–{number(p["Fit upper stress (MPa)"])} MPa); '
                  f'<b>{int(calculation["elastic_mask"].sum())} selected points</b>. '
                  f'R² = {number(p["Elastic fit R2"], 5)}; intercept = {number(p["Elastic intercept (MPa)"])} MPa. '
                  'This fitted E is independent of the WH modulus.</p>')
    bracket = calculation['yield_bracket']
    if bracket is not None:
        xs = calculation['strain_pct'][list(bracket)]
        result.append(f'<p>0.2% YS is interpolated between {xs[0]:.5f}% and {xs[1]:.5f}% strain, '
                      'at the first eligible crossing after the elastic-fit region and before UTS.</p>')
    result.append('<p>Uniform elongation uses the first maximum engineering stress. Failure EL is the terminal '
                  'recorded strain—not an independently detected fracture onset or a post-fracture gauge measurement.</p>')
    result.append('<details><summary>Source and preparation details</summary><p>Source: ' +
                  escape(payload['source_file']) + '</p><p>SHA256: ' + escape(payload.get('source_sha256', '')) +
                  '</p><p>Curve uses the workbench’s existing CSV loading and property preparation: finite pairs, '
                  'sorted by strain, with the maximum stress retained for repeated strain values. '
                  'No WH filters, averaging, extrapolation or landmark alignment are applied.</p><p>Instron match: ' +
                  escape(reference.get('status', 'Unavailable')) + '. ' + escape(reference.get('notes', '')) +
                  '</p><p>Instron source: ' + escape(reference.get('source', '') or 'Unavailable') +
                  '</p></details></div>')
    return ''.join(result)


class SpecimenInspector:
    """Create one disposable interactive figure only when a specimen is selected."""
    def __init__(self, widgets, loader=None):
        self.w, self.loader = widgets, loader
        self._updating, self._payload, self.chart, self._probe = False, None, None, None
        w = widgets
        self.choice = w.Dropdown(description='Specimen:', options=[('Choose a specimen…', '')],
                                 layout=w.Layout(width='min(100%, 720px)'))
        self.previous = w.Button(description='Previous', layout=w.Layout(width='95px'), disabled=True)
        self.next = w.Button(description='Next', layout=w.Layout(width='75px'), disabled=True)
        self.view = w.ToggleButtons(options=[('Yield detail', 'yield'), ('Full curve', 'full')], value='yield')
        self.reset = w.Button(description='Reset zoom', layout=w.Layout(width='110px'))
        self.status = w.HTML('Click a specimen name in the Specimens table, or choose one above.')
        self.summary = w.HTML(layout=w.Layout(width='100%', min_width='0'))
        self.chart_box = w.VBox(layout=w.Layout(width='100%', min_width='0'))
        self.ui = w.VBox([w.HBox([self.choice, self.previous, self.next],
                                layout=w.Layout(flex_flow='row wrap', grid_gap='6px')),
                          self.status, w.HBox([self.view, self.reset], layout=w.Layout(flex_flow='row wrap')),
                          self.chart_box, self.summary], layout=w.Layout(width='100%', min_width='0'))
        self.choice.observe(self._selected, names='value')
        self.view.observe(lambda _: self._reset_zoom(), names='value')
        self.reset.on_click(lambda _: self._reset_zoom())
        self.previous.on_click(lambda _: self._step(-1))
        self.next.on_click(lambda _: self._step(1))
        self._navigation()

    def _dispose(self):
        self.chart_box.children = ()
        if self.chart is not None:
            self.chart.close()
        if self._probe is not None:
            self._probe.close()
        self._probe = None
        self.chart, self._payload = None, None
        self.summary.value = ''

    def clear(self):
        self._updating = True
        try:
            self.choice.options = [('Choose a specimen…', '')]
            self.choice.value = ''
        finally:
            self._updating = False
        self._dispose()
        self._navigation()
        self.status.value = 'Click a specimen name in the Specimens table, or choose one above.'

    def set_rows(self, rows):
        selected = self.choice.value
        options = [('Choose a specimen…', '')]
        for row in rows:
            # Relative ID disambiguates identical basenames without using absolute paths.
            label = row['id'] + ('' if row['included'] else ' (excluded)')
            options.append((label, row['id']))
        self._updating = True
        try:
            self.choice.options = options
            self.choice.value = selected if selected in {value for _, value in options} else ''
        finally:
            self._updating = False
        self._selected()

    def select(self, ident):
        if ident not in {value for _, value in self.choice.options}:
            return
        if self.choice.value == ident:
            self._selected()
        else:
            self.choice.value = ident

    def _navigation(self):
        ids = [value for _, value in self.choice.options if value]
        index = ids.index(self.choice.value) if self.choice.value in ids else -1
        self.previous.disabled = index <= 0
        self.next.disabled = not ids or index >= len(ids) - 1
        self.view.disabled = self.chart is None
        self.reset.disabled = self.chart is None

    def _step(self, direction):
        ids = [value for _, value in self.choice.options if value]
        index = ids.index(self.choice.value) if self.choice.value in ids else -1
        if 0 <= index + direction < len(ids):
            self.choice.value = ids[index + direction]

    def _selected(self, _=None):
        if self._updating:
            return
        self._dispose()
        if not self.choice.value or self.loader is None:
            self.status.value = 'Click a specimen name in the Specimens table, or choose one above.'
            self._navigation()
            return
        self.status.value = 'Loading specimen calculation…'
        try:
            import plotly.graph_objects as go
            from tensile_plotly import width_probe
            payload = self.loader(self.choice.value)
            self.chart = go.FigureWidget(inspection_figure(payload, self.view.value))
            self._payload = payload
            self._probe = width_probe(self._resize)
            self.chart_box.children = (self._probe, self.chart)
            self.summary.value = inspection_summary(payload)
            self.status.value = ('Read-only inspection · drag to zoom; use Reset zoom to return. '
                                 'No graph settings, exclusions or results are changed.')
        except Exception as error:
            self._dispose()
            self.status.value = '<b>Inspection unavailable:</b> ' + escape(str(error))
        self._navigation()

    def _resize(self, width):
        if self.chart is None:
            return
        width = max(240, int(width))
        columns = max(1, (width - 100) // 255)
        rows = int(np.ceil(len(self.chart.data) / columns))
        plot_height = 420
        bottom = 85 + 28 * rows
        with self.chart.batch_update():
            self.chart.update_layout(width=width, height=plot_height + 22 + bottom,
                margin=dict(l=72, r=25, t=22, b=bottom),
                legend=dict(entrywidth=min(240, max(130, width - 100)), y=-70 / plot_height))

    def _reset_zoom(self):
        if self.chart is None or self._payload is None:
            return
        xrange, yrange = inspection_ranges(self._payload['calculation'], self.view.value)
        with self.chart.batch_update():
            self.chart.update_xaxes(range=xrange, autorange=False)
            self.chart.update_yaxes(range=yrange, autorange=False)
