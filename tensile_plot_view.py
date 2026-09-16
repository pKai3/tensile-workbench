"""Resolution-independent gallery using only built-in ipywidgets.

No data access, calculations or exports. Thumbnails are native buttons with
SVG backgrounds; no browser extension or executable HTML is required.
"""
from base64 import b64encode
from html import escape
import uuid


class GroupCheckboxes:
    """Checkbox presentation of the existing exact-group selection model."""
    def __init__(self, widgets, selection, display_names=None):
        self.w, self.selection = widgets, selection
        self.display_names = display_names or {}
        self.boxes = {}
        self._syncing = False
        scope = 'tensile-groups-' + uuid.uuid4().hex
        self.summary = widgets.HTML()
        self.clear_button = widgets.Button(description='Clear selection', layout=widgets.Layout(width='auto'))
        # CSS columns preserve sequential top-to-bottom reading order and
        # naturally reduce the column count in narrower notebook panels.
        self.grid = widgets.Box(layout=widgets.Layout(display='block', width='100%', max_width='760px'))
        self.grid.add_class(scope)
        compact = widgets.HTML('<style>.' + scope + '{column-width:150px;column-gap:16px;column-fill:balance;}'
            '.' + scope + '>.widget-checkbox{break-inside:avoid;page-break-inside:avoid;'
            'width:100%;height:auto;min-height:0;margin:0;padding:2px 0;line-height:1.1;}'
            '.' + scope + '>.widget-checkbox label,.' + scope + '>.widget-checkbox span{line-height:1.1;}'
            '</style>', layout=widgets.Layout(height='0px', min_height='0px', margin='0', overflow='hidden'))
        self.ui = widgets.VBox([
            widgets.HTML('<b>Sample groups</b>'), compact, self.grid,
            widgets.HBox([self.summary, self.clear_button], layout=widgets.Layout(flex_flow='row wrap', gap='12px', align_items='center')),
        ], layout=widgets.Layout(width='100%'))
        selection.observe(self._options_changed, names='options')
        selection.observe(self._value_changed, names='value')
        self.clear_button.on_click(lambda _: setattr(selection, 'value', ()))
        self._options_changed()

    def _options_changed(self, _=None):
        for box in self.boxes.values():
            box.close()
        self.boxes = {}
        for option in self.selection.options:
            label, group = option if isinstance(option, tuple) else (option, option)
            box = self.w.Checkbox(value=group in self.selection.value, description=label, indent=False,
                                 tooltip=self.display_names.get(group, label), layout=self.w.Layout(width='auto'))
            box.observe(self._checked, names='value')
            self.boxes[group] = box
        self.grid.children = tuple(self.boxes.values())
        self._value_changed()

    def _value_changed(self, _=None):
        self._syncing = True
        try:
            for group, box in self.boxes.items():
                box.value = group in self.selection.value
        finally:
            self._syncing = False
        selected = self.selection.value
        self.summary.value = ('<b>Selected (' + str(len(selected)) + '):</b> ' +
                              escape(' · '.join(selected) if selected else 'None'))
        self.clear_button.disabled = not selected

    def _checked(self, _):
        if not self._syncing:
            self.selection.value = tuple(group for group, box in self.boxes.items() if box.value)


class PlotView:
    def __init__(self, widgets, columns, plot_width):
        w = self.w = widgets
        self.columns, self.plot_width = columns, plot_width
        self._items, self._cards, self._owned = [], [], []
        self._setting_focus = False
        self._focused_key = None
        self._scope = 'tensile-view-' + uuid.uuid4().hex
        self.board = w.GridBox(layout=w.Layout(width='100%', grid_gap='16px', align_items='flex-start'))
        self.empty = w.HTML('Choose plots and click <b>Update plots</b> to see them here.')
        self.back = w.Button(description='Back to all plots', icon='th-large', layout=w.Layout(width='auto'))
        self.choice = w.Dropdown(description='Plot:', layout=w.Layout(width='min(100%, 560px)'))
        self.zoom = w.IntSlider(value=100, min=100, max=300, step=25, description='Zoom (%)',
                               continuous_update=False, style={'description_width': 'initial'},
                               layout=w.Layout(width='300px'))
        self.fit = w.Button(description='Fit width', layout=w.Layout(width='auto'))
        # A self-contained data URI avoids binary-widget transfer differences
        # between Jupyter kernel/manager versions. It remains a real SVG image.
        self.focus_image = w.HTML(layout=w.Layout(width='100%', max_width='none', height='auto', margin='0', overflow='visible'))
        self.viewport = w.Box([self.focus_image], layout=w.Layout(display='block', width='100%',
                              max_height='78vh', overflow='auto'))
        self.focus = w.VBox([
            w.HBox([self.back, self.choice, self.zoom, self.fit],
                   layout=w.Layout(flex_flow='row wrap', gap='8px', align_items='center')),
            w.HTML('Zoom enlarges the image only; scroll to inspect it. Axes and exports are unchanged.'),
            self.viewport,
        ], layout=w.Layout(display='none', width='100%'))
        self.toolbar = w.HBox([columns, plot_width], layout=w.Layout(flex_flow='row wrap', gap='12px'))
        self.hint = w.HTML('Click a plot to enlarge it. Vector previews stay sharp at any size.')
        self.ui = w.VBox([self.toolbar, self.hint, self.empty, self.board, self.focus], layout=w.Layout(width='100%'))
        self.ui.add_class(self._scope)
        self.back.on_click(lambda _: self.close_focus())
        self.choice.observe(self._select_focus, names='value')
        self.zoom.observe(self._zoom, names='value')
        self.fit.on_click(lambda _: setattr(self.zoom, 'value', 100))
        self.apply_layout()

    def _dispose_cards(self):
        for widget in reversed(self._owned):
            widget.close()
        self._owned = []
        self._cards = []

    def clear(self, message='Choose plots and click Update plots.'):
        self.close_focus()
        self.board.children = ()
        self._dispose_cards()
        self._items = []
        self.choice.options = []
        self.focus_image.value = ''
        self.empty.value = escape(message)
        self.empty.layout.display = ''

    def set_items(self, items):
        """Each item has key, label and result (or error). Reuse computed figures."""
        previous = self._focused_key
        self.board.children = ()
        self._dispose_cards()
        self._items = list(items)
        for index, item in enumerate(items):
            heading = self.w.HTML('<b>' + escape(item['label']) + '</b>')
            self._owned.append(heading)
            if item.get('result') is None:
                body = self.w.HTML('Unavailable: ' + escape(item.get('error', 'No valid curves.')))
                card = self.w.VBox([heading, body], layout=self.w.Layout(width='100%', min_width='0'))
                self._owned.extend([body, card])
            else:
                result = item['result']
                scope = self._scope + '-plot-' + str(index)
                width, height = result['figure'].get_size_inches()
                source = b64encode(result['svg']).decode('ascii')
                css = self.w.HTML('<style>.' + scope + '.jupyter-button {'
                    'background-image:url("data:image/svg+xml;base64,' + source + '");'
                    'background-repeat:no-repeat;background-position:center;background-size:contain;'
                    'background-color:white;border:0;border-radius:0;box-shadow:none;'
                    'padding:0;display:block;width:100%;height:auto;min-height:0;'
                    f'aspect-ratio:{float(width)}/{float(height)};'
                    'font-size:0;cursor:zoom-in;}'
                    '.' + scope + '.jupyter-button:focus-visible{outline:2px solid var(--jp-brand-color1,#1976d2);outline-offset:2px;}'
                    '</style>', layout=self.w.Layout(height='0px', min_height='0px', margin='0', overflow='hidden'))
                thumb = self.w.Button(description='Enlarge ' + item['label'], tooltip='Click to enlarge: ' + item['label'],
                                     layout=self.w.Layout(width='100%', height='auto', margin='0'))
                thumb.add_class(scope)
                thumb.on_click(lambda _, key=item['key']: self.open_focus(key))
                card = self.w.VBox([heading, css, thumb], layout=self.w.Layout(width='100%', min_width='0'))
                self._owned.extend([css, thumb, card])
            self._cards.append(card)
        self.board.children = tuple(self._cards)
        self.empty.layout.display = 'none' if items else ''
        self._setting_focus = True
        try:
            self.choice.options = [(item['label'], item['key']) for item in items if item.get('result') is not None]
        finally:
            self._setting_focus = False
        self.apply_layout()
        if previous in [value for _, value in self.choice.options]:
            self.open_focus(previous)
        else:
            self.close_focus()

    def apply_layout(self):
        columns, width = self.columns.value, self.plot_width.value
        # Selected columns are an upper bound: narrow notebooks must not crush
        # scientific labels or acquire a horizontal gallery scrollbar.
        self.board.layout.max_width = 'none' if columns == 0 else f'{columns*width + (columns-1)*16}px'
        self.board.layout.grid_template_columns = (
            'minmax(0, 1fr)' if columns == 1 else
            f'repeat(auto-fit, minmax(min(100%, {width}px), 1fr))')
        for card in self._cards:
            card.layout.max_width = f'{width}px'

    def open_focus(self, key):
        item = next((item for item in self._items if item['key'] == key and item.get('result') is not None), None)
        if item is None:
            return
        self._focused_key = key
        self._setting_focus = True
        try:
            self.choice.value = key
            source = b64encode(item['result']['svg']).decode('ascii')
            self.focus_image.value = ('<img alt="' + escape(item['label'], quote=True) +
                '" src="data:image/svg+xml;base64,' + source +
                '" style="display:block;width:100%;max-width:none;height:auto;margin:0;">')
        finally:
            self._setting_focus = False
        self.board.layout.display = 'none'
        self.toolbar.layout.display = 'none'
        self.hint.layout.display = 'none'
        self.focus.layout.display = ''
        self._zoom()

    def close_focus(self):
        self._focused_key = None
        self.focus.layout.display = 'none'
        self.board.layout.display = 'grid'
        self.toolbar.layout.display = 'flex'
        self.hint.layout.display = ''

    def _select_focus(self, _):
        if not self._setting_focus and self.choice.value is not None:
            self.open_focus(self.choice.value)

    def _zoom(self, _=None):
        self.focus_image.layout.width = f'{self.zoom.value}%'


class DualPlotView:
    """Keep the existing SVG viewer unchanged and add a lazy Plotly alternative."""
    def __init__(self, widgets, columns, plot_width, renderer):
        self.w, self.columns, self.plot_width, self.renderer = widgets, columns, plot_width, renderer
        self.static = PlotView(widgets, columns, plot_width)
        self.plotly = None
        self._items = []
        self._plotly_current = False
        self.ui = widgets.VBox([self.static.ui], layout=widgets.Layout(width='100%'))
        renderer.observe(self._switch, names='value')

    @property
    def board(self):
        return self.active.board

    @property
    def active(self):
        return self.plotly if self.renderer.value == 'plotly' and self.plotly else self.static

    def _switch(self, _=None):
        if self.renderer.value == 'plotly':
            if self.plotly is None:
                from tensile_plotly import PlotlyView
                self.plotly = PlotlyView(self.w, self.columns, self.plot_width)
            if not self._plotly_current:
                self.plotly.set_items(self._items)
                self._plotly_current = True
        self.ui.children = (self.active.ui,)
        self.apply_layout()

    def set_items(self, items):
        self._items = list(items)
        self.static.set_items(items)
        if self.plotly is not None:
            self.plotly.clear()
        self._plotly_current = False
        self._switch()

    def clear(self, message='Choose plots and click Update plots.'):
        self._items = []
        self.static.clear(message)
        if self.plotly is not None:
            self.plotly.clear(message)
        self._plotly_current = False

    def apply_layout(self):
        self.static.apply_layout()
        if self.plotly is not None:
            self.plotly.apply_layout()
