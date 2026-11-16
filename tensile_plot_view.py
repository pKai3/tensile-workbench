"""Resolution-independent gallery of static SVG previews.

No data access, calculations or exports. Thumbnails are native buttons with
SVG backgrounds; a shared popup shell fits the selected image to the viewport.
"""
from base64 import b64encode
from html import escape
from tensile_help import help_widget, control_row
import uuid

from tensile_group_picker import GroupCheckboxes
from tensile_activity import busy
from tensile_popup import SettingsPopup


class PlotView:
    def __init__(self, widgets, columns, plot_width):
        w = self.w = widgets
        self.columns, self.plot_width = columns, plot_width
        self._items, self._cards, self._owned = [], [], []
        self._setting_focus = False
        self._focused_key = None
        self._scope = 'tensile-view-' + uuid.uuid4().hex
        self.board = w.GridBox(layout=w.Layout(width='100%', grid_gap='16px', align_items='flex-start'))
        self.board.add_class('tw-plot-board')
        self.empty = w.HTML('Choose plots and click <b>Update plots</b> to see them here.')
        self.choice = w.Dropdown(description='Plot:', layout=w.Layout(width='min(100%, 560px)'))
        self.choice.tooltip = 'Switch the enlarged plot without recalculating the results.'
        # A self-contained data URI avoids binary-widget transfer differences
        # between Jupyter kernel/manager versions. It remains a real SVG image.
        self.focus_image = w.HTML(layout=w.Layout(width='100%', height='100%', min_height='0', margin='0', overflow='hidden'))
        self.viewport = w.Box([self.focus_image], layout=w.Layout(width='100%', min_height='0',
                              flex='1 1 0%', overflow='hidden', align_items='center', justify_content='center'))
        self.viewport.add_class('tw-static-plot-viewport')
        self.focus = w.VBox([self.choice, self.viewport], layout=w.Layout(
            width='100%', min_width='0', min_height='0', flex='1 1 0%', overflow='hidden', grid_gap='10px'))
        self.focus_popup = SettingsPopup(w, on_close=self._focus_closed, width='1600px')
        self.focus_popup.ui.add_class('tw-dismiss-outside-media')
        self.focus_popup.done.description = 'Close'
        self.focus_popup.done.tooltip = 'Return to all plots.'
        self.focus_popup.dialog.add_class('tw-static-plot-dialog')
        self.focus_popup.dialog.layout.width = 'min(1600px, 96vw)'
        self.focus_popup.dialog.layout.max_height = '92dvh'
        self.focus_popup.dialog.layout.padding = '16px'
        self.focus_popup.body.layout.overflow = 'hidden'
        self.hint = help_widget(w, 'Viewing plots', 'Click a plot to enlarge it. Vector previews stay sharp at any size.')
        self.toolbar = control_row(w, [columns, plot_width, self.hint])
        self.ui = w.VBox([self.toolbar, self.empty, self.board, self.focus_popup.ui], layout=w.Layout(width='100%'))
        self.ui.add_class(self._scope)
        self.choice.observe(self._select_focus, names='value')
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
                    '.' + scope + '.jupyter-button:focus-visible{outline:2px solid var(--tw-accent,var(--jp-brand-color1,#1976d2));outline-offset:2px;}'
                    '</style>', layout=self.w.Layout(height='0px', min_height='0px', margin='0', overflow='hidden'))
                thumb = self.w.Button(description='Enlarge ' + item['label'], tooltip='Click to enlarge: ' + item['label'],
                                     layout=self.w.Layout(width='100%', height='auto', margin='0'))
                thumb.add_class(scope)
                thumb.add_class('tw-plot-thumbnail')
                thumb.on_click(lambda _, key=item['key']: self.open_focus(key))
                card = self.w.VBox([heading, css, thumb], layout=self.w.Layout(width='100%', min_width='0'))
                self._owned.extend([css, thumb, card])
            if item.get('warning'):
                warning = self.w.HTML('<div style="background:var(--tw-warning-bg,#fff7e6);color:var(--tw-warning-text,inherit);'
                                      'border-left:3px solid var(--tw-warning-border,#d97706);padding:8px;white-space:normal">'
                                      + escape(item['warning']) + '</div>')
                card.children = (card.children[0], warning, *card.children[1:])
                self._owned.append(warning)
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
                '" style="display:block;width:auto;height:auto;max-width:100%;max-height:100%;object-fit:contain;margin:auto;">')
        finally:
            self._setting_focus = False
        if self.focus_popup.overlay.layout.display == 'none':
            self.focus_popup.open('Static plot preview', [self.focus], height='92dvh')

    def close_focus(self):
        self.focus_popup.close()

    def _focus_closed(self):
        self._focused_key = None

    def _select_focus(self, _):
        if not self._setting_focus and self.choice.value is not None:
            self.open_focus(self.choice.value)


class DualPlotView:
    """Switch between the static SVG gallery and a lazy Plotly alternative."""
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

    @busy('Preparing plot view…')
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
