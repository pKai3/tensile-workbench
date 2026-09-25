"""Lazy, measured-curve review. Display visibility never changes analysis policy."""
from html import escape
import uuid
import re
import numpy as np
from tensile_selection import specimen_id, DATA_MODES, property_allowed
from tensile_specimens import SpecimenTable
from tensile_properties import specimen_properties
from tensile_fracture import fracture_endpoint, endpoint_available, prepared_points


# Short labels belong in the view's key; the exact saved policy stays in hover.
MODE_STYLES = {
    'all': ('', 'solid', 1.),
    'after_uts': ('EL excluded', 'dash', .9),
    'after_yield': ('Post-yield strain excluded', 'dot', .9),
    'no_strain': ('All strain excluded', 'dashdot', .8),
    'exclude': ('Fully excluded', 'longdash', .35),
}
# Fixed screen-pixel patterns shared with the specimen key. Plotly's named
# dash patterns scale with stroke width, so highlighting used to change them.
DASH_PIXELS = {'solid': '', 'dash': '8 4', 'dot': '2 4', 'dashdot': '8 3 2 3', 'longdash': '12 5'}
MARKERS = {'YS': ('circle', 'ys'), 'UTS': ('triangle-up', 'uts'), 'EL': ('x', 'el')}


def review_marker_points(record, axis='strain'):
    """Measured diagnostic landmarks, not reconstructed or policy-masked values.

    UTS and EL use their actual acquisition rows. Yield is interpolated at the
    calculated crossing; on the time axis, interpolate those same strain brackets.
    Missing coordinates remain absent, never moved to another measurement.
    """
    p = record.get('_review_properties')
    if p is None:
        p = specimen_properties(record, apply_policy=False)
    acquisition = record.get('_acquisition', {})
    stress = np.asarray(acquisition.get('stress', record['stress_mpa']), dtype=float)
    coords = np.asarray(acquisition.get(axis, record['strain_pct'] if axis == 'strain' else []), dtype=float)
    points = {}

    def add(name, x, y):
        if np.isfinite(x) and np.isfinite(y):
            points[name] = (float(x), float(y))

    yield_x, yield_y = p.get('Yield strain (%)', np.nan), p.get('Yield (MPa)', np.nan)
    if axis == 'strain':
        add('YS', yield_x, yield_y)
    elif np.isfinite(yield_x):
        x, _, ids = prepared_points(record)
        right = int(np.searchsorted(x, yield_x))
        if right < len(x) and x[right] == yield_x and 0 <= ids[right] < len(coords):
            add('YS', coords[ids[right]], yield_y)
        elif 0 < right < len(x) and 0 <= ids[right - 1] < ids[right] < len(coords):
            t0, t1 = coords[ids[right - 1]], coords[ids[right]]
            if np.isfinite(t0) and np.isfinite(t1) and t1 >= t0:
                fraction = (yield_x - x[right - 1]) / (x[right] - x[right - 1])
                add('YS', t0 + fraction * (t1 - t0), yield_y)
    valid_stress = np.flatnonzero(np.isfinite(stress) & (stress >= 0))
    if len(valid_stress):
        peak = int(valid_stress[np.argmax(stress[valid_stress])])
        if peak < len(coords):
            add('UTS', coords[peak], stress[peak])
    end = fracture_endpoint(record)
    if endpoint_available(end):
        if axis == 'strain':
            add('EL', end['strain_pct'], end['stress_mpa'])
        elif np.isfinite(end.get('row_before', np.nan)):
            index = int(end['row_before']) - 1
            if 0 <= index < len(coords):
                add('EL', coords[index], end['stress_mpa'])
    return points


class GroupCurveReview:
    def __init__(self, widgets, loader=None, on_selection=None, on_inspect=None):
        self.w, self.loader, self.on_inspect = widgets, loader, on_inspect
        self.rows, self.figure = [], None
        self.active, self.dirty, self.syncing = False, True, False
        self.selected, self.generation = None, None
        self._owned, self._legend_buttons, self._marker_data = [], {}, {}
        self.group = widgets.Dropdown(description='Group:', layout=widgets.Layout(width='350px'))
        self.axis = widgets.Dropdown(description='X axis:', options=[('Recorded strain (%)', 'strain'), ('Time (s)', 'time')],
                                     layout=widgets.Layout(width='260px'))
        self.show_excluded = widgets.Checkbox(value=True, description='Show fully excluded specimens', indent=False)
        self.show_excluded.tooltip = 'Display only. Exclusions are changed with Data use in the table below.'
        self.markers = {name: widgets.Checkbox(value=False, description=label, indent=False,
                        layout=widgets.Layout(width='auto'))
                        for name, label in [('YS', '○ YS'), ('UTS', '△ UTS'), ('EL', '× EL')]}
        self.inspect = widgets.Button(description='Inspect highlighted specimen', disabled=True,
                                      layout=widgets.Layout(width='auto'))
        self.status = widgets.HTML()
        self.plot = widgets.VBox(layout=widgets.Layout(width='100%', min_width='0'))
        self.legend = widgets.GridBox(layout=widgets.Layout(width='100%', min_width='0', grid_gap='3px 14px',
            grid_template_columns='repeat(auto-fit, minmax(min(100%, 260px), 1fr))'))
        self.table = SpecimenTable(on_selection=on_selection, on_inspect=self.select,
                                   layout=widgets.Layout(width='100%'))
        self.ui = widgets.VBox([
            widgets.HTML('<p>Raw measured curves. '
                         'Click a curve or specimen name to highlight it, not exclude it. '
                         'Use <b>Data use</b> in the table below to change analysis contributions. '
                         'Line styles and labels show exclusions.</p>'
                         '<details><summary>About this view and markers</summary><p>'
                         'Curves include AVE glitches and unloading; fully excluded curves are faint. '
                         'Markers show measured Calc values (including manual overrides), not reconstruction or Instron. '
                         'Hollow markers identify excluded properties; hover for the mode. Unavailable markers are omitted. '
                         '“Broke outside dots” assumes strain was reliable through UTS. '
                         'This view does not require fracture detection or reconstruction.</p></details>'),
            widgets.HBox([self.group, self.axis, self.show_excluded], layout=widgets.Layout(flex_flow='row wrap')),
            widgets.HBox([widgets.HTML('<b>Markers:</b>'), *self.markers.values()],
                         layout=widgets.Layout(flex_flow='row wrap', align_items='center', gap='12px')),
            self.status, widgets.HTML('<b>Specimens · click to highlight</b>'),
            self.legend, self.plot, self.inspect, self.table], layout=widgets.Layout(width='100%', min_width='0'))
        for control in (self.group, self.axis, self.show_excluded):
            control.observe(self._changed, names='value')
        for control in self.markers.values():
            control.observe(lambda _: self._update_markers(), names='value')
        self.inspect.on_click(lambda _: self.on_inspect(self.selected) if self.selected and self.on_inspect else None)

    def set_rows(self, rows):
        self.rows = list(rows)
        self.syncing = True
        try:
            old = self.group.value
            groups = list(dict.fromkeys(r['group'] for r in rows))
            self.group.options = groups
            self.group.value = old if old in groups else groups[0] if groups else None
        finally:
            self.syncing = False
        self.dirty = True
        self.generation = None  # invalidate callbacks from the old figure immediately
        self.table.context = uuid.uuid4().hex
        self.table.rows = []
        self.inspect.disabled = True
        if self.active:
            self.render()

    def set_active(self, value):
        self.active = value
        if value and self.dirty:
            self.render()

    def _changed(self, _):
        if not self.syncing:
            self.dirty = True
            if self.active:
                self.render()

    def clear(self):
        self.set_rows([])
        self._dispose()
        self.table.rows = []
        self.table.context = uuid.uuid4().hex
        self.selected = None
        self.inspect.disabled = True

    def _dispose(self):
        self.plot.children = ()
        self.legend.children = ()
        for widget in reversed(self._owned):
            widget.close()
        self._owned, self._legend_buttons, self._marker_data = [], {}, {}
        if self.figure is not None:
            self.figure.close()
            self.figure = None

    def select(self, ident):
        if ident not in {r['id'] for r in self.rows if r['group'] == self.group.value}:
            return
        self.selected = ident
        self.inspect.disabled = False
        row = next(r for r in self.rows if r['id'] == ident)
        mode = row.get('mode', 'all' if row['included'] else 'exclude')
        self.status.value = ('<b>Highlighted:</b> ' + escape(row['sample']) + ' · ' + escape(row.get('csv_filename', ident))
                            + ' · <b>' + escape(DATA_MODES[mode]) + '</b>')
        for key, button in self._legend_buttons.items():
            if key == ident:
                button.add_class('tw-review-highlighted')
            else:
                button.remove_class('tw-review-highlighted')
        if self.figure is not None:
            with self.figure.batch_update():
                for trace in self.figure.data:
                    if trace.meta.get('kind') == 'curve':
                        trace.line.width = 3.5 if trace.meta['id'] == ident else 1.3

    def _legend_entry(self, row, color, mode, token):
        short, dash, _ = MODE_STYLES[mode]
        label = row['sample'] + (' · ' + short if short else '')
        button = self.w.Button(description=label,
            tooltip=DATA_MODES[mode] + '. Click to highlight, not exclude. Use Data use below for exclusions.',
            layout=self.w.Layout(width='100%', min_width='0', height='auto', min_height='28px'))
        scope = 'tw-review-key-' + token
        button.add_class(scope)
        if row['id'] == self.selected:
            button.add_class('tw-review-highlighted')
        css = self.w.HTML('<style>.' + scope + '{white-space:normal!important;line-height:1.25!important;'
                         'text-align:left;text-overflow:clip;background:transparent;border:1px solid transparent;'
                         'box-shadow:none;padding:3px 5px;}.' + scope + ':hover{background:#eef3f8;}.' + scope +
                         '.tw-review-highlighted{font-weight:600;background:#e8f0f8;border-color:#b9cede;}</style>',
                         layout=self.w.Layout(height='0px', width='0px', overflow='hidden'))
        swatch = self.w.HTML('<svg width="30" height="16" aria-hidden="true"><line x1="0" x2="30" y1="8" y2="8" '
            f'stroke="{color}" stroke-width="3" stroke-dasharray="{DASH_PIXELS[dash]}"/></svg>',
            layout=self.w.Layout(width='32px', flex='0 0 32px'))
        def clicked(_):
            if token == self.generation:
                self.select(row['id'])
        button.on_click(clicked)
        entry = self.w.HBox([css, swatch, button], layout=self.w.Layout(align_items='center', min_width='0'))
        self._owned.extend([button, css, swatch, entry])
        self._legend_buttons[row['id']] = button
        return entry

    def _bind_click(self, trace, ident, token):
        def clicked(trace, points, state):
            if token == self.generation and points.point_inds:
                self.select(ident)
        trace.on_click(clicked)

    def _marker_traces(self):
        import plotly.graph_objects as go
        if not any(control.value for control in self.markers.values()):
            return
        for ident, entry in self._marker_data.items():
            row, color, mode = entry['row'], entry['color'], entry['mode']
            if entry.get('points') is None:
                entry['points'] = review_marker_points(entry['record'], self.axis.value)
            for name, (x, y) in entry['points'].items():
                if not self.markers[name].value:
                    continue
                symbol, field = MARKERS[name]
                eligible = property_allowed(mode, field)
                caption = escape(row['sample'] + ' · ' + name)
                yield go.Scatter(x=[x], y=[y], mode='markers', name=caption,
                    showlegend=False, visible=True,
                    meta={'id': ident, 'kind': 'marker', 'property': name, 'eligible': eligible},
                    marker={'symbol': symbol if eligible else symbol + '-open', 'size': 10,
                            'color': color, 'line': {'width': 1.6, 'color': color}},
                    hovertemplate=caption + '<br>' + escape(DATA_MODES[mode]) +
                        ('<br>Excluded from analysis' if not eligible else '') +
                        ('<br>Strain: %{x:.3f}%' if self.axis.value == 'strain' else '<br>Time: %{x:.3f} s') +
                        '<br>Stress: %{y:.2f} MPa<extra></extra>')

    def _update_markers(self):
        if self.figure is None or self.generation is None:
            return
        # Keep the same figure and line traces: marker toggles must not reset
        # zoom or change specimen visibility or analysis settings.
        with self.figure.batch_update():
            self.figure.data = tuple(t for t in self.figure.data if t.meta.get('kind') == 'curve')
            for trace in self._marker_traces():
                self.figure.add_trace(trace)
                self._bind_click(self.figure.data[-1], trace.meta['id'], self.generation)

    def render(self):
        self._dispose()
        self.dirty = False
        token = self.generation = uuid.uuid4().hex
        # Use the displayed/operator specimen name, not the CSV export-row name.
        # Natural ordering keeps specimen 2 before specimen 10; stable sorting
        # preserves source order for duplicate names and equivalent zero padding.
        rows = sorted((r for r in self.rows if r['group'] == self.group.value),
                      key=lambda r: tuple(int(part) if part.isdecimal() else part.casefold()
                                          for part in re.split(r'(\d+)', str(r['sample']))))
        self.table.columns = ['Checks']
        self.table.column_groups = [{'label': 'Checks', 'span': 1}]
        self.table.context = token
        self.table.rows = [{**r, 'values': r['values'][:1], 'excluded_values': []} for r in rows]
        self.status.value = ''
        if not rows or self.loader is None:
            self.inspect.disabled = True
            return
        import plotly.graph_objects as go
        from plotly.colors import qualitative
        try:
            records = {specimen_id(r): r for r in self.loader(self.group.value)}
            # Serialize a complete initial figure. Updating an empty widget
            # before its front end mounts can lose the initial add/restyle
            # messages in Voilà and leave an empty or incorrectly sized plot.
            figure = go.Figure()
            if self.selected not in {r['id'] for r in rows}:
                self.selected = rows[0]['id']
            legend = []
            for index, row in enumerate(rows):
                record = records.get(row['id'])
                if record is None or (not row['included'] and not self.show_excluded.value):
                    continue
                acquisition = record.get('_acquisition', {})
                stress = np.asarray(acquisition.get('stress', record['stress_mpa']), dtype=float)
                key = 'strain' if self.axis.value == 'strain' else 'time'
                x = np.asarray(acquisition.get(key, record['strain_pct'] if key == 'strain' else np.full(len(stress), np.nan)), dtype=float)
                # Do not sort, trim, smooth or bridge invalid readings.
                valid = np.isfinite(x) & np.isfinite(stress)
                x, y = np.where(valid, x, np.nan), np.where(valid, stress, np.nan)
                color = qualitative.Dark24[index % len(qualitative.Dark24)]
                mode = row.get('mode', 'all' if row['included'] else 'exclude')
                _, dash, opacity = MODE_STYLES[mode]
                # SVG strokes keep dash spacing stable along densely sampled
                # curves; WebGL can stipple the dense sections while rendering
                # the sparse fracture drop correctly. Keep every raw point and
                # gap. Plotly simplifies only the display path at the current
                # zoom, not the measurements or analysis arrays.
                figure.add_trace(go.Scatter(x=x, y=y, mode='lines', name=row['sample'], connectgaps=False,
                    opacity=opacity, visible=True, showlegend=False,
                    line={'color': color, 'width': 3.5 if row['id'] == self.selected else 1.3,
                          'dash': DASH_PIXELS[dash] or 'solid', 'simplify': True, 'shape': 'linear'},
                    meta={'id': row['id'], 'kind': 'curve', 'mode': mode},
                    hovertemplate=escape(row['sample']) + '<br>' + escape(DATA_MODES[mode]) +
                        ('<br>Strain: %{x:.3f}%' if key == 'strain' else '<br>Time: %{x:.3f} s') +
                        '<br>Stress: %{y:.2f} MPa<extra></extra>'))
                legend.append(self._legend_entry(row, color, mode, token))
                self._marker_data[row['id']] = {'row': row, 'record': record, 'color': color, 'mode': mode}
            figure.update_layout(template='plotly_white', height=480, autosize=True,
                margin={'l': 65, 'r': 20, 't': 15, 'b': 65}, hovermode='closest', dragmode='zoom',
                showlegend=False, uirevision=token,
                xaxis={'automargin': True}, yaxis={'automargin': True},
                xaxis_title='Recorded engineering strain (%)' if self.axis.value == 'strain' else 'Recorded time (s)',
                yaxis_title='Engineering stress (MPa)')
            figure.add_traces(list(self._marker_traces()))
            figure = go.FigureWidget(figure)
            self.figure = figure
            for trace in figure.data:
                self._bind_click(trace, trace.meta['id'], token)
            from tensile_plotly import width_probe
            def resize(width):
                if token == self.generation and self.figure is figure:
                    figure.update_layout(width=max(200, int(width)), autosize=False)
            probe = width_probe(resize)
            self._owned.append(probe)
            self.legend.children = tuple(legend)
            self.plot.children = (probe, figure)
            self.select(self.selected)
        except Exception as error:
            self.status.value = '<b>Curve review unavailable:</b> ' + escape(str(error))
