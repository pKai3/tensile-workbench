"""Lazy, read-only group overview of the same fits used by the inspector."""
from html import escape
import re
import uuid

import numpy as np

from tensile_activity import busy
from tensile_inspector import inspection_figure, inspection_ranges, layer_swatch
from tensile_properties import DEFAULT_FIT_FRACTIONS, specimen_calculation
from tensile_selection import DATA_MODES, specimen_id


FIT_LAYERS = {'measured', 'fit_points', 'elastic_fit', 'offset', 'yield_calc', 'yield_instron'}


def yield_fit_figure(record, calculation, *, crop_range=None):
    """Reuse inspector traces and exact fit diagnostics; only the view is reduced."""
    figure = inspection_figure({'record': record, 'calculation': calculation,
                                'reference': record.get('_review_reference', {'values': {}})}, mode='yield')
    figure.data = tuple(trace for trace in figure.data
                        if (trace.meta or {}).get('inspector_layer') in FIT_LAYERS)
    figure.layout.shapes = tuple(shape for shape in figure.layout.shapes
                                if shape.name == 'inspector:fit_points')
    # Keep acquisition order, reversals and gaps in the displayed yield region.
    # Include neighbours at crop boundaries and insert a gap between disjoint
    # runs, so reducing the display payload never draws invented connections.
    left, right = crop_range or figure.layout.xaxis.range
    measured = next(trace for trace in figure.data if trace.meta['inspector_layer'] == 'measured')
    x, y = np.asarray(measured.x, float), np.asarray(measured.y, float)
    keep = np.isfinite(x) & (x >= left) & (x <= right)
    keep = keep | np.r_[False, keep[:-1]] | np.r_[keep[1:], False] if len(keep) else keep
    ids = np.flatnonzero(keep)
    gaps = np.flatnonzero(np.diff(ids) > 1) + 1
    measured.x = np.insert(x[ids], gaps, np.nan)
    measured.y = np.insert(y[ids], gaps, np.nan)
    measured.connectgaps = False
    measured.line.simplify = True
    p = calculation['properties']
    r2 = p['Elastic fit R2']
    label = f'R² = {r2:.5f}' if np.isfinite(r2) else 'R² unavailable'
    if p['Fit review required']:
        label += ' · Review fit'
    figure.add_annotation(text=label, x=0, y=1, xref='paper', yref='paper',
                          xanchor='left', yanchor='bottom', yshift=8, showarrow=False,
                          font={'size': 12, 'color': '#a65b00' if p['Fit review required'] else '#334155'})
    figure.update_layout(height=300, width=380, autosize=False, showlegend=False,
                         margin={'l': 60, 'r': 12, 't': 34, 'b': 52},
                         font={'size': 11},
                         xaxis_title={'text': 'Engineering strain (%)', 'standoff': 8},
                         yaxis_title={'text': 'Stress (MPa)', 'standoff': 6})
    return figure


class GroupYieldReview:
    def __init__(self, widgets, loader=None, on_inspect=None):
        self.w, self.loader, self.on_inspect = widgets, loader, on_inspect
        self.rows, self.entries, self._owned = [], [], []
        self.active, self.dirty, self.syncing = False, True, False
        self.generation, self._width = None, 1200
        w = widgets
        self.group = w.Dropdown(description='Group:', layout=w.Layout(width='min(100%, 480px)'))
        self.show_excluded = w.Checkbox(description='Show fully excluded specimens', value=True, indent=False,
                                       layout=w.Layout(width='auto'))
        self.shared_axes = w.Checkbox(description='Use the same axes', value=True, indent=False,
                                     layout=w.Layout(width='auto'))
        self.columns = w.Dropdown(description='Columns:', options=[1, 2, 3], value=3,
                                  layout=w.Layout(width='150px'))
        self.reset = w.Button(description='Reset zoom', layout=w.Layout(width='auto'))
        self.status = w.HTML()
        legend = ' &nbsp; '.join(layer_swatch(color, symbol, dash) + ' ' + label for label, color, symbol, dash in [
            ('Measured CSV', '#334155', None, None), ('Fit points', '#16a085', 'circle', None),
            ('Elastic fit', '#16a085', None, 'dash'), ('0.2% offset', '#d97706', None, 'dash'),
            ('Calc YS', '#d97706', 'diamond', None), ('Instron YS', '#be185d', 'diamond-open', None)])
        self.grid = w.GridBox(layout=w.Layout(width='100%', min_width='0', grid_gap='14px',
                                              grid_template_columns='repeat(3, minmax(0, 1fr))'))
        self.plot = w.VBox(layout=w.Layout(width='100%', min_width='0'))
        self.ui = w.VBox([
            w.HTML('<p>Compare the saved yield fits for one sample group. R² describes agreement inside the '
                   'selected interval; check the fitted line against the surrounding curve too. '
                   'Use <b>Inspect / adjust</b> to open the specimen inspector. '
                   'Exclusions remain visible for review and are labelled on each card.</p>'),
            w.HBox([self.group, self.show_excluded], layout=w.Layout(flex_flow='row wrap', align_items='center')),
            w.HBox([self.shared_axes, self.columns, self.reset],
                   layout=w.Layout(flex_flow='row wrap', align_items='center', grid_gap='12px')),
            w.HTML(legend), self.status, self.plot,
        ], layout=w.Layout(width='100%', min_width='0'))
        self.group.observe(self._changed, names='value')
        self.show_excluded.observe(self._changed, names='value')
        self.shared_axes.observe(lambda _: self._update_axes(), names='value')
        self.columns.observe(lambda _: self._resize(self._width), names='value')
        self.reset.on_click(lambda _: self._update_axes())

    def set_rows(self, rows):
        self.rows = list(rows)
        self.syncing = True
        try:
            previous = self.group.value
            groups = list(dict.fromkeys(row['group'] for row in self.rows))
            self.group.options = groups
            self.group.value = previous if previous in groups else groups[0] if groups else None
        finally:
            self.syncing = False
        self.dirty, self.generation = True, None
        if self.active:
            self.render()

    def set_active(self, value):
        self.active = bool(value)
        if self.active and self.dirty:
            self.render()

    def _changed(self, _):
        if not self.syncing:
            self.dirty = True
            if self.active:
                self.render()

    def _dispose(self):
        self.generation = None
        self.plot.children = self.grid.children = ()
        for widget in reversed(self._owned):
            widget.close()
        self._owned, self.entries = [], []

    def clear(self):
        self.set_rows([])
        self._dispose()
        self.status.value = 'Select sample groups to review their yield fits.'

    def _resize(self, width):
        self._width = max(200, int(width))
        columns = min(self.columns.value, max(1, self._width // 350))
        self.grid.layout.grid_template_columns = f'repeat({columns}, minmax(0, 1fr))'
        chart_width = self._chart_width = max(180, (self._width - 14 * (columns - 1)) // columns - 22)
        for entry in self.entries:
            entry['figure'].update_layout(width=chart_width)

    def _update_axes(self):
        if not self.entries:
            return
        common = [[min(entry['ranges'][axis][0] for entry in self.entries),
                   max(entry['ranges'][axis][1] for entry in self.entries)] for axis in (0, 1)]
        for entry in self.entries:
            x, y = common if self.shared_axes.value else entry['ranges']
            with entry['figure'].batch_update():
                entry['figure'].update_xaxes(range=x, autorange=False)
                entry['figure'].update_yaxes(range=y, autorange=False)

    @busy('Loading group yield fits…')
    def render(self):
        self._dispose()
        self.dirty = False
        token = self.generation = uuid.uuid4().hex
        rows = sorted((row for row in self.rows if row['group'] == self.group.value
                       and (self.show_excluded.value or row['included'])),
                      key=lambda row: tuple(int(part) if part.isdecimal() else part.casefold()
                                            for part in re.split(r'(\d+)', str(row['sample']))))
        if not rows or self.loader is None:
            self.status.value = 'No specimens to display.'
            return
        try:
            records = {specimen_id(record): record for record in self.loader(self.group.value)}
        except Exception as error:
            self.status.value = '<b>Yield fits unavailable:</b> ' + escape(str(error))
            return
        calculated, failures = [], {}
        for row in rows:
            try:
                record = records[row['id']]
                calculation = specimen_calculation(record, record.get('_review_fit_fractions', DEFAULT_FIT_FRACTIONS))
                ranges = inspection_ranges(calculation, 'yield',
                    reported_ys=record.get('_review_reference', {}).get('values', {}).get('ys', np.nan))
                calculated.append((row, record, calculation, ranges))
            except Exception as error:
                failures[row['id']] = str(error)
        # Crop only the display arrays, to the union of yield-detail regions.
        # This retains everything needed when switching shared/individual axes.
        crop = ([min(item[3][0][0] for item in calculated), max(item[3][0][1] for item in calculated)]
                if calculated else None)
        by_id = {item[0]['id']: item for item in calculated}
        common = [[min(item[3][axis][0] for item in calculated),
                   max(item[3][axis][1] for item in calculated)] for axis in (0, 1)] if calculated else None
        self._resize(self._width)
        cards = []
        w = self.w
        import plotly.graph_objects as go
        from tensile_plotly import width_probe
        for row in rows:
            mode = row.get('mode', 'all' if row['included'] else 'exclude')
            info = '<b>' + escape(row['sample']) + '</b>'
            if mode != 'all':
                info += '<br><span style="color:#64748b">' + escape(DATA_MODES[mode]) + '</span>'
            if row.get('withheld'):
                info += '<br><span style="color:#a65b00">Duplicate review · results withheld</span>'
            content = []
            if row['id'] in by_id:
                _, record, calculation, ranges = by_id[row['id']]
                p = calculation['properties']
                number = lambda value: f'{value:.2f}' if np.isfinite(value) else '—'
                info += ('<br>' + escape(p['Fit method']) + ' · E ' + number(p['Fitted E (GPa)']) +
                         ' GPa · YS ' + number(p['Yield (MPa)']) + ' MPa')
                if p['Fit review required']:
                    sensitivity = (p.get('Automatic fit sensitivity warning', '')
                                   if p['Fit method'] == 'Automatic' else '')
                    review_label = 'Fit sensitive to selected range' if sensitivity else 'Fit needs review · inspect for details'
                    info += ('<br><span style="color:#a65b00" title="' + escape(sensitivity or p['Notes'], quote=True) +
                             '">' + review_label + '</span>')
                figure = yield_fit_figure(record, calculation, crop_range=crop)
                x_range, y_range = common if self.shared_axes.value else ranges
                # Serialize the intended initial scales before mounting. Early
                # widget relayout messages can otherwise be lost in Voilà.
                figure.update_layout(width=self._chart_width,
                                     xaxis_range=x_range, yaxis_range=y_range)
                figure = go.FigureWidget(figure)
                self.entries.append({'id': row['id'], 'figure': figure, 'ranges': ranges, 'calculation': calculation})
                content.append(figure)
            else:
                content.append(w.HTML('<b>Fit unavailable:</b> ' + escape(failures[row['id']])))
            heading = w.HTML('<div style="line-height:1.45;overflow-wrap:anywhere">' + info + '</div>',
                             layout=w.Layout(width='100%', min_width='0', height='84px', overflow='auto', margin='0'))
            button = w.Button(description='Inspect / adjust', disabled=self.on_inspect is None,
                              layout=w.Layout(width='auto', align_self='flex-start'))
            def inspect(_, ident=row['id'], generation=token):
                if generation == self.generation and self.on_inspect:
                    self.on_inspect(ident)
            button.on_click(inspect)
            card = w.VBox([heading, *content, button], layout=w.Layout(width='100%', min_width='0',
                          overflow='hidden', padding='10px', border='1px solid #cbd5e1'))
            self._owned.extend([heading, *content, button, card])
            cards.append(card)
        probe = width_probe(self._resize)
        self._owned.append(probe)
        self.grid.children = tuple(cards)
        self.plot.children = (probe, self.grid)
        review_count = sum(entry['calculation']['properties']['Fit review required'] for entry in self.entries)
        self.status.value = f'{len(rows)} specimens · {review_count} fit' + (' needs' if review_count == 1 else 's need') + ' review.'
        if failures:
            self.status.value += f' {len(failures)} could not be loaded; see their cards.'
        self._resize(self._width)
