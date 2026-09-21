"""On-demand specimen inspection and explicitly applied fit-override previews."""
from copy import deepcopy
from html import escape

import numpy as np
from tensile_properties import specimen_calculation


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


def overlay_ranges(payload, mode='yield', show_gauge=False):
    xrange, yrange = inspection_ranges(payload['calculation'], mode)
    preview = payload.get('gauge_preview')
    if show_gauge and mode == 'full' and preview and preview['_gauge']['Gauge correction status'] == 'Applied':
        x = np.asarray(preview['strain_pct'])
        finite = x[np.isfinite(x)]
        if len(finite):
            left, right = min(xrange[0], float(finite.min())), max(xrange[1], float(finite.max()))
            padding = .04 * max(right - left, .1)
            xrange = [left, right + padding]
    return xrange, yrange


def inspection_figure(payload, mode='yield', edit=None, show_gauge=False):
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

    if show_gauge:
        measured = payload['record']
        line('Measured AVE curve', measured['strain_pct'], measured['stress_mpa'], '#334155', width=2)
        preview = payload.get('gauge_preview')
        if preview and preview['_gauge']['Gauge correction status'] == 'Applied':
            target = preview['_gauge']['Target gauge length (mm)']
            line(f'Estimated curve · target {target:g} mm', preview['strain_pct'], preview['stress_mpa'], '#e76f00', dash='dash', width=2)
            endpoint = int(preview['_gauge']['Failure measurement row (1-based)']) - 1
            points('Estimated failure endpoint', [preview['_gauge']['Estimated failure elongation (%)']],
                   [measured['_acquisition']['stress'][endpoint]], '#e76f00', 'x', 12)
        acquisition = measured.get('_acquisition', {})
        peak = acquisition.get('peak')
        if peak is not None and np.isfinite(acquisition['strain'][peak]) and np.isfinite(acquisition['stress'][peak]):
            points(acquisition['peak_basis'] + ' · original row ' + str(peak + 1),
                   [acquisition['strain'][peak]], [acquisition['stress'][peak]], '#dc2626', 'diamond-open', 13)
    else:
        line('Measured curve (prepared)', x, y, '#334155', width=2)
    mask = calculation['elastic_mask']
    if mask.any():
        points('Elastic-fit points', x[mask], y[mask], '#16a085', size=6)
        fig.add_shape(type='rect', x0=float(x[mask].min()), x1=float(x[mask].max()),
            y0=p['Fit lower stress (MPa)'], y1=p['Fit upper stress (MPa)'],
            fillcolor='rgba(22,160,133,0.10)', line_width=0, layer='below', editable=False)
    modulus = p['Fitted E (GPa)'] * 1000
    if np.isfinite(modulus) and modulus > 0:
        # Define the lines over the visible stress range, not to full fracture strain.
        stresses = np.array([0., max(1., p['UTS (MPa)']) * 1.10])
        strains = (stresses - p['Elastic intercept (MPa)']) / modulus * 100
        line('Elastic fit', strains, stresses, '#16a085', dash='dash', width=1.8)
        line('0.2% offset line', strains + .2, stresses, '#d97706', dash='dash', width=1.8)
    automatic = calculation.get('automatic_calculation')
    if automatic and np.isfinite(automatic['properties']['Fitted E (GPa)']):
        ap = automatic['properties']
        stresses = np.array([0., max(1., p['UTS (MPa)'])])
        strains = (stresses - ap['Elastic intercept (MPa)']) / (ap['Fitted E (GPa)'] * 1000) * 100
        line('Automatic elastic fit', strains, stresses, '#94a3b8', dash='dot', width=1.3)
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
    if edit:
        if edit['mode'] == 'range':
            fig.add_shape(type='rect', name='fit-range', editable=True, x0=edit['strain_bounds'][0],
                x1=edit['strain_bounds'][1], y0=0, y1=1, yref='paper',
                line=dict(color='#7c3aed', width=3), fillcolor='rgba(124,58,237,.04)')
        else:
            (x0, y0), (x1, y1) = edit['endpoints']
            fig.add_shape(type='line', name='fit-line', editable=True, x0=x0, x1=x1, y0=y0, y1=y1,
                          line=dict(color='#7c3aed', width=4))
            points('Manual line endpoints', [x0, x1], [y0, y1], '#7c3aed', 'circle-open', 12)
    xrange, yrange = overlay_ranges(payload, mode, show_gauge)
    fig.update_layout(template='plotly_white', autosize=True, height=620,
        margin=dict(l=72, r=25, t=22, b=190), font=dict(family='Arial, sans-serif', size=12),
        xaxis=dict(title='Engineering strain (%)', range=xrange, automargin=True),
        yaxis=dict(title='Engineering stress (MPa)', range=yrange, automargin=True),
        legend=dict(orientation='h', x=0, xanchor='left', y=-.23, yanchor='top',
                    entrywidth=240, font=dict(size=11)), hovermode='closest', dragmode='zoom',
        activeshape=dict(fillcolor='rgba(124,58,237,.12)', opacity=.9))
    return fig


def gauge_model_help():
    """Inspector-only model explanation; plain HTML needs no MathJax or network."""
    return '''<details><summary>Gauge reconstruction: formula and assumptions</summary>
      <p>Define <b>r = L<sub>dots</sub> / L<sub>target</sub></b>.</p>
      <div class="tw-gauge-equations">
        <div>At or before maximum force: <b>ε<sub>est</sub> = ε<sub>measured</sub></b></div>
        <div>After maximum force: <b>ε<sub>est</sub> = ε<sub>u</sub> +
          r (ε<sub>measured</sub> − ε<sub>u</sub>)</b></div>
        <div>At the selected failure endpoint: <b>ε<sub>f,est</sub> = ε<sub>u</sub> +
          r (ε<sub>f,measured</sub> − ε<sub>u</sub>)</b></div>
      </div>
      <p><b>L<sub>dots</sub></b> is this specimen’s initial AVE dot spacing, imported from
      <i>Strain 1 gauge length</i>; <b>L<sub>target</sub></b> is the saved target for its group.
      Both lengths are in mm. <b>ε<sub>u</sub></b> is total engineering strain at the original
      maximum-force reading. All strains use the same engineering-strain definition and are
      expressed in percent, including the elastic component. The breakpoint is applied by
      acquisition order, not by testing whether a strain value exceeds ε<sub>u</sub>.
      Maximum engineering stress is used as a recorded proxy only if no force channel exists.</p>
      <p><b>Example:</b> 10% strain at peak force, 18% measured failure strain, 50 mm dots
      and a 25 mm target give 10 + (50 / 25) × (18 − 10) = <b>26%</b>.</p>
      <p><b>Assumptions and limits</b></p>
      <ul>
        <li>Deformation before maximum force is assumed approximately uniform, so the
          uniform-strain component is not rescaled.</li>
        <li>Both gauges are assumed to contain the same neck/fracture region. The model
          assigns all measured post-peak extension to the neck-centred target gauge.</li>
        <li>Continued deformation and elastic unloading outside the target gauge cannot
          be separated from this single gauge history. For targets longer than the AVE
          spacing, additional post-peak extension outside the measured interval is not recovered.</li>
        <li>The failure endpoint is the maximum retained recorded strain used by the
          workbench, not an independently detected fracture onset or a post-fracture gauge measurement.</li>
        <li>Stress values stay unchanged throughout. Reconstructed toughness is the area
          under the estimated engineering curve, not a newly measured material property.</li>
      </ul>
      <p>This is a derived estimate, not a standards-compliant measurement. If the original
      video or spatial-strain data are available, reprocessing with the correct virtual gauge
      is preferable.</p>
    </details>'''


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
              '.tw-inspect-summary summary{cursor:pointer}'
              '.tw-gauge-equations{padding:10px 12px;background:#f2f6fa;border-radius:5px;line-height:1.8}'
              '.tw-inspect-summary li{margin:5px 0}'
              '.tw-inspect-warning{padding:8px;background:#fff4dc;border-left:3px solid #d97706}</style>',
              '<div class="tw-inspect-summary">',
              '<p><b>' + escape(payload['group'] + ' · ' + payload['sample']) + '</b> · ' +
              ('Included in this graph' if payload['included'] else 'Excluded from this graph') + '</p>']
    if payload.get('exclusion_reason'):
        result.append('<p>Exclusion reason: ' + escape(payload['exclusion_reason']) + '</p>')
    show_automatic = bool(calculation.get('automatic_calculation'))
    result.append('<p><b>Fit method: ' + escape(p.get('Fit method', 'Automatic')) + '</b> · ' +
                  escape(p.get('Override status', 'None')) + '</p>')
    result.append('<table><thead><tr><th>Property</th><th>Calculated</th>' +
                  ('<th>Automatic</th>' if show_automatic else '') + '<th>Instron</th>'
                  '<th>Δ (Calc − Instron)</th></tr></thead><tbody>')
    for label, field, key in metrics:
        calculated, reported = p[field], values.get(key, np.nan)
        auto = calculation['automatic_calculation']['properties'][field] if show_automatic else np.nan
        result.append('<tr><td>' + escape(label) + '</td><td>' + number(calculated) + '</td>' +
                      ('<td>' + number(auto) + '</td>' if show_automatic else '') + '<td>' +
                      number(reported) + '</td><td>' + number(calculated - reported) + '</td></tr>')
    result.append('</tbody></table><p>Δ uses the displayed units; elongation differences are percentage points. '
                  'Instron YS is drawn as a horizontal reference only; its yield strain is not inferred.</p>')
    preview = payload.get('gauge_preview')
    if preview:
        audit = preview['_gauge']
        enabled = payload.get('gauge_policy', {}).get('enabled', False)
        result.append('<p><b>Gauge reconstruction for this group: ' + ('on' if enabled else 'off — preview only') + '</b>. '
                      'The calculations and Instron comparison above remain measured. Overlaying a curve does not apply it.</p>')
        result.append('<table><tr><th>AVE dot spacing (mm)</th><th>Group target (mm)</th><th>Ratio</th></tr>'
                      '<tr><td>' + number(audit['AVE dot spacing (mm)']) + '</td><td>' +
                      number(audit['Target gauge length (mm)']) + '</td><td>' + number(audit['Gauge ratio']) + '</td></tr></table>')
        result.append('<table><tr><th>Property</th><th>Measured</th><th>Estimated</th></tr>')
        for label, raw_key, estimated_key in (
                ('Failure EL (%)', 'Failure elongation (%)', 'Estimated failure elongation (%)'),
                ('Tensile toughness (MJ/m³)', 'Toughness (MJ/m^3)', 'Estimated toughness (MJ/m^3)')):
            result.append('<tr><td>' + label + '</td><td>' + number(p[raw_key]) + '</td><td>' + number(audit[estimated_key]) + '</td></tr>')
        result.append('</table><p>Derived localisation model, not a standards-compliant measurement. '
                      'Pre-peak strain is unchanged; stress values are unchanged throughout.</p>')
        result.append(gauge_model_help())
        if audit['Gauge correction status'] != 'Applied':
            result.append('<p class="tw-inspect-warning"><b>Overlay unavailable:</b> ' + escape(audit['Gauge correction status']) +
                          '. Set and save a target under Gauge reconstruction · per sample group.</p>')
        for key in ('Gauge model warning', 'Gauge reconstruction notes'):
            if audit.get(key):
                result.append('<p class="tw-inspect-warning">' + escape(audit[key]) + '</p>')
        acquisition = payload['record'].get('_acquisition', {})
        peak = acquisition.get('peak')
        if peak is not None:
            result.append('<p>' + escape(acquisition['peak_basis']) + f': original measurement row {peak + 1}, '
                          + 'time ' + number(acquisition['time'][peak]) + ' s, strain ' + number(acquisition['strain'][peak]) + '%. '
                          'Peak comes from the original acquisition, independently of plotting cleanup.</p>')
    if p['Yield status'] != 'resolved' or p['Notes']:
        result.append('<p class="tw-inspect-warning"><b>Yield ' + escape(p['Yield status']) + ':</b> ' +
                      escape(p['Notes']) + '</p>')
    low, high = calculation['fit_fractions']
    description = (f'Automatic elastic fit: {100 * low:g}–{100 * high:g}% of this specimen’s UTS'
                   if p.get('Fit method', 'Automatic') == 'Automatic' else
                   f'{p["Fit method"]}: {number(p["Fit lower strain (%)"], 5)}–{number(p["Fit upper strain (%)"], 5)}% strain')
    result.append(f'<p>{description}, before the first UTS point '
                  f'({number(p["Fit lower stress (MPa)"])}–{number(p["Fit upper stress (MPa)"])} MPa); '
                  f'<b>{int(calculation["elastic_mask"].sum())} selected points</b>. '
                  f'R² = {number(p["Elastic fit R2"], 5)}; intercept = {number(p["Elastic intercept (MPa)"])} MPa. '
                  'This fitted E is independent of the WH modulus.</p>')
    result.append(f'<p>Review threshold: R² &lt; {calculation.get("r2_threshold", .98):g}. '
                  'A high R² alone does not establish that a region is elastic.</p>')
    if p.get('Fit method') == 'Manual line':
        result.append('<p>Manual line is not a least-squares fit. R² measures residual agreement with the selected '
                      'data points between the endpoint strains and can be negative.</p>')
    saved = calculation.get('saved_override') or {}
    if saved.get('saved_at'):
        result.append('<p>Override saved: ' + escape(saved['saved_at']) + ' · ' + escape(saved.get('reason', '')) + '</p>')
        original = saved.get('automatic_snapshot', {})
        result.append('<details><summary>Automatic result when this override was applied</summary><p>' +
                      '<br>'.join(escape(str(k)) + ': ' + escape(str(v) if v is not None else 'Unavailable')
                                  for k, v in original.items()) + '</p></details>')
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
    def __init__(self, widgets, loader=None, on_apply=None):
        self.w, self.loader = widgets, loader
        self.on_apply = on_apply
        self._painting, self._editing, self._draft = False, False, None
        self._updating, self._payload, self.chart, self._probe = False, None, None, None
        w = widgets
        self.choice = w.Dropdown(description='Specimen:', options=[('Choose a specimen…', '')],
                                 layout=w.Layout(width='min(100%, 720px)'))
        self.previous = w.Button(description='Previous', layout=w.Layout(width='95px'), disabled=True)
        self.next = w.Button(description='Next', layout=w.Layout(width='75px'), disabled=True)
        self.view = w.ToggleButtons(options=[('Yield detail', 'yield'), ('Full curve', 'full')], value='yield')
        self.reset = w.Button(description='Reset zoom', layout=w.Layout(width='110px'))
        self.gauge_overlay = w.Checkbox(description='Overlay measured / reconstructed', value=False, indent=False,
                                       layout=w.Layout(width='auto'))
        self.gauge_status = w.HTML()
        self.status = w.HTML('Click a specimen name in the Specimens table, or choose one above.')
        self.summary = w.HTML(layout=w.Layout(width='100%', min_width='0'))
        self.chart_box = w.VBox(layout=w.Layout(width='100%', min_width='0'))
        self.mode = w.Dropdown(description='Fit:', options=[('Inspect saved fit', 'inspect'),
            ('Manual range', 'range'), ('Manual line', 'line')], value='inspect', layout=w.Layout(width='300px'))
        self.x0 = w.FloatText(description='Start strain (%)', continuous_update=False, style={'description_width': 'initial'})
        self.x1 = w.FloatText(description='End strain (%)', continuous_update=False, style={'description_width': 'initial'})
        self.y0 = w.FloatText(description='Start stress (MPa)', continuous_update=False, style={'description_width': 'initial'})
        self.y1 = w.FloatText(description='End stress (MPa)', continuous_update=False, style={'description_width': 'initial'})
        self.line_fields = w.HBox([self.y0, self.y1], layout=w.Layout(flex_flow='row wrap', display='none'))
        self.reason = w.Text(description='Reason:', placeholder='Why is the fit being adjusted?', continuous_update=True,
                             layout=w.Layout(width='min(100%, 800px)'))
        self.apply_button = w.Button(description='Apply override · all graphs', button_style='primary',
                                     layout=w.Layout(width='auto'), disabled=True)
        self.cancel_button = w.Button(description='Cancel preview', disabled=True)
        self.restore_button = w.Button(description='Restore automatic fit', layout=w.Layout(width='auto'), disabled=True)
        self.edit_status = w.HTML('Select a specimen to review or adjust its elastic fit.')
        self.editor = w.Accordion(children=[w.VBox([self.mode,
            w.HBox([self.x0, self.x1], layout=w.Layout(flex_flow='row wrap')), self.line_fields, self.reason,
            w.HBox([self.apply_button, self.cancel_button, self.restore_button], layout=w.Layout(flex_flow='row wrap')),
            self.edit_status])], selected_index=None)
        self.editor.set_title(0, 'Adjust elastic fit · preview before applying')
        self.ui = w.VBox([w.HBox([self.choice, self.previous, self.next],
                                layout=w.Layout(flex_flow='row wrap', grid_gap='6px')),
                          self.status, self.editor, w.HBox([self.view, self.reset, self.gauge_overlay], layout=w.Layout(flex_flow='row wrap')),
                          self.gauge_status, self.chart_box, self.summary], layout=w.Layout(width='100%', min_width='0'))
        self.choice.observe(self._selected, names='value')
        self.view.observe(lambda _: self._reset_zoom(), names='value')
        self.reset.on_click(lambda _: self._reset_zoom())
        self.gauge_overlay.observe(self._overlay_changed, names='value')
        self.previous.on_click(lambda _: self._step(-1))
        self.next.on_click(lambda _: self._step(1))
        self.mode.observe(self._mode_changed, names='value')
        for control in (self.x0, self.x1, self.y0, self.y1):
            control.observe(lambda _: self._preview(), names='value')
        self.reason.observe(lambda _: self._buttons(), names='value')
        self.apply_button.on_click(lambda _: self._apply())
        self.cancel_button.on_click(lambda _: self._selected())
        self.restore_button.on_click(lambda _: self._apply(restore=True))
        self._navigation()

    def _dispose(self):
        self.chart_box.children = ()
        if self.chart is not None:
            self.chart.close()
        if self._probe is not None:
            self._probe.close()
        self._probe = None
        self.chart, self._payload = None, None
        self._draft = None
        self.summary.value = ''
        self.gauge_status.value = ''

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
        self.gauge_overlay.disabled = self.chart is None
        self.mode.disabled = self.chart is None or self.on_apply is None
        self._buttons()

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
            payload = self.loader(self.choice.value)
            self._editing = True
            self.mode.value = 'inspect'
            self._editing = False
            self._saved_payload = payload
            self._seed_editor(payload)
            self._paint(payload)
            self.status.value = ('Read-only until Apply override · drag to zoom; use Reset zoom to return. '
                                 'Fit overrides apply to this specimen in every graph.')
            self.edit_status.value = 'Choose Manual range or Manual line to start an unsaved preview.'
        except Exception as error:
            self._dispose()
            self.status.value = '<b>Inspection unavailable:</b> ' + escape(str(error))
        self._navigation()

    def _seed_editor(self, payload):
        calc = payload['calculation']
        saved = calc.get('override')
        mask, x, y = calc['elastic_mask'], calc['strain_pct'], calc['stress_mpa']
        if saved:
            low, high = saved['strain_bounds']
        elif mask.any():
            low, high = float(x[mask][0]), float(x[mask][-1])
        elif len(x) > 5:
            end = max(4, min(len(x)-1, (calc['uts_index'] or len(x)) // 3))
            low, high = float(x[0]), float(x[end])
        else:
            low, high = 0., .2
        p = calc['properties']
        self._editing = True
        try:
            self.x0.value, self.x1.value = low, high
            if saved and saved['mode'] == 'line':
                self.y0.value, self.y1.value = saved['endpoints'][0][1], saved['endpoints'][1][1]
            elif np.isfinite(p['Fitted E (GPa)']):
                self.y0.value, self.y1.value = [p['Fitted E (GPa)'] * 10 * v + p['Elastic intercept (MPa)'] for v in (low, high)]
            elif len(x):
                self.y0.value, self.y1.value = np.interp([low, high], x, y)
            self.reason.value = (calc.get('saved_override') or {}).get('reason', '')
        finally:
            self._editing = False

    def _buttons(self):
        editing = self._payload is not None and self.mode.value != 'inspect'
        self.x0.disabled = self.x1.disabled = self.reason.disabled = not editing
        self.y0.disabled = self.y1.disabled = not editing or self.mode.value != 'line'
        self.line_fields.layout.display = '' if self.mode.value == 'line' else 'none'
        self.cancel_button.disabled = not editing
        self.apply_button.disabled = not (editing and self._draft and self.reason.value.strip() and
            self._payload['calculation']['properties']['Yield status'] == 'resolved' and self.on_apply)
        self.restore_button.disabled = not (self._payload and self.on_apply and
            self._saved_payload['calculation'].get('saved_override'))

    def _mode_changed(self, _=None):
        if self._editing or self._payload is None:
            return
        if self.mode.value == 'inspect':
            self._selected()
        else:
            self._preview()

    def _preview(self):
        if self._editing or self._payload is None or self.mode.value == 'inspect':
            return
        self._draft = None
        try:
            record = self._saved_payload['record']
            bounds = [self.x0.value, self.x1.value]
            if self.mode.value == 'range':
                # Snap range handles/numerical bounds to actual prepared measurement points.
                x = self._saved_payload['calculation']['strain_pct']
                if len(x):
                    bounds = [float(x[np.argmin(abs(x-v))]) for v in bounds]
            candidate = {'mode': self.mode.value, 'strain_bounds': bounds,
                         'source_sha256': self._saved_payload['source_sha256']}
            if self.mode.value == 'line':
                candidate['endpoints'] = [[bounds[0], self.y0.value], [bounds[1], self.y1.value]]
            calc = specimen_calculation(record, self._saved_payload['calculation']['fit_fractions'], override=candidate)
            calc['properties']['Override status'] = 'Unsaved preview'
            self._editing = True
            self.x0.value, self.x1.value = bounds
            self._editing = False
            self._draft = candidate
            self._paint({**self._saved_payload, 'calculation': calc}, edit=candidate, keep_zoom=True)
            instruction = ('Click a purple range border, then drag its corner handles; all measured points between them are refitted.'
                           if self.mode.value == 'range' else 'Click the purple line, then drag either endpoint; this directly changes slope/intercept.')
            self.edit_status.value = '<b>Unsaved preview.</b> ' + instruction + ' Enter a reason, then Apply override to use it in every graph.'
            if calc['properties']['Yield status'] != 'resolved':
                self.edit_status.value += '<br><b>Cannot apply:</b> ' + escape(calc['properties']['Notes'])
        except Exception as error:
            self.edit_status.value = '<b>Invalid preview:</b> ' + escape(str(error)) + ' The chart retains the last valid view; nothing has been saved.'
        finally:
            self._editing = False
            self._buttons()

    def _overlay_changed(self, _=None):
        if self._painting or self._updating or self._payload is None:
            return
        if self.gauge_overlay.value:
            self.view.value = 'full'
        self._paint(self._payload, edit=self._draft if self.mode.value != 'inspect' else None)

    def _paint(self, payload, edit=None, keep_zoom=False):
        import plotly.graph_objects as go
        from tensile_plotly import width_probe
        fig = inspection_figure(payload, self.view.value, edit=edit, show_gauge=self.gauge_overlay.value)
        self._painting = True
        try:
            if self.chart is None:
                self.chart = go.FigureWidget(fig)
                self.chart.layout.on_change(self._dragged, 'shapes')
                self._probe = width_probe(self._resize)
                self.chart_box.children = (self._probe, self.chart)
            else:
                if keep_zoom:
                    fig.update_xaxes(range=self.chart.layout.xaxis.range)
                    fig.update_yaxes(range=self.chart.layout.yaxis.range)
                with self.chart.batch_update():
                    self.chart.data = []
                    self.chart.add_traces(fig.data)
                    self.chart.layout.shapes = fig.layout.shapes
                    self.chart.update_xaxes(range=fig.layout.xaxis.range)
                    self.chart.update_yaxes(range=fig.layout.yaxis.range)
            self._payload = payload
            self.summary.value = inspection_summary(payload)
            preview = payload.get('gauge_preview')
            audit = preview['_gauge'] if preview else {}
            self.gauge_status.value = ''
            if self.gauge_overlay.value:
                if audit.get('Gauge correction status') != 'Applied':
                    self.gauge_status.value = '<b>Measured curve only — reconstruction unavailable:</b> ' + escape(
                        audit.get('Gauge correction status', 'No gauge preview available'))
                else:
                    self.gauge_status.value = 'Display-only overlay: solid measured; dashed estimated. No settings or measurements changed.'
                    if audit.get('Gauge model warning'):
                        self.gauge_status.value += '<br><b>Model warning:</b> ' + escape(audit['Gauge model warning'])
            if self._probe and self._probe.pixels:
                self._resize(self._probe.pixels)
        finally:
            self._painting = False

    def _dragged(self, layout, shapes):
        if self._painting or self.chart is None or layout is not self.chart.layout or self.mode.value == 'inspect':
            return
        shape = next((shape for shape in shapes if shape.name in ('fit-line', 'fit-range')), None)
        if shape is None:
            return
        self._editing = True
        try:
            self.x0.value, self.x1.value = shape.x0, shape.x1
            if shape.name == 'fit-line':
                self.y0.value, self.y1.value = shape.y0, shape.y1
        finally:
            self._editing = False
        self._preview()

    def _apply(self, restore=False):
        if not self.on_apply or not self._payload or (not restore and self.apply_button.disabled):
            return
        try:
            self.on_apply(self.choice.value, self._saved_payload['source_sha256'],
                          None if restore else deepcopy(self._draft), self.reason.value)
            self._selected()
            self.edit_status.value = 'Automatic fit restored in all graphs.' if restore else 'Override saved for this specimen in all graphs.'
        except Exception as error:
            self.edit_status.value = '<b>Not applied:</b> ' + escape(str(error))

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
        xrange, yrange = overlay_ranges(self._payload, self.view.value, self.gauge_overlay.value)
        with self.chart.batch_update():
            self.chart.update_xaxes(range=xrange, autorange=False)
            self.chart.update_yaxes(range=yrange, autorange=False)
