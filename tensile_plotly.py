"""Plotly view of already-calculated Matplotlib artists; no analysis or file I/O."""
from html import escape
import textwrap
import numpy as np
from matplotlib.colors import to_hex
from matplotlib.container import ErrorbarContainer


def width_probe(on_resize):
    """Measure the displayed container; resize only the disposable Plotly view."""
    import anywidget
    import traitlets
    class WidthProbe(anywidget.AnyWidget):
        pixels = traitlets.Int(0).tag(sync=True)
        _esm = """
        export default {render({model, el}) {
          el.style.height = '0px'; el.style.overflow = 'hidden';
          el.style.width = '100%';
          // render may run before attachment, so observe this element itself.
          const target = el;
          let frame;
          const measure = () => {
            cancelAnimationFrame(frame);
            frame = requestAnimationFrame(() => {
              const width = Math.floor(target.getBoundingClientRect().width);
              if (width > 150 && width !== model.get('pixels')) {
                model.set('pixels', width); model.save_changes();
              }
            });
          };
          const observer = new ResizeObserver(measure);
          observer.observe(target); measure();
          return () => {observer.disconnect(); cancelAnimationFrame(frame);};
        }};
        """
    probe = WidthProbe()
    probe.observe(lambda change: on_resize(change['new']) if change['new'] > 150 else None, names='pixels')
    return probe


def plain(text):
    return str(text).replace(r'$\Theta$', 'Θ').replace('$', '')


def wrapped(text, width=75):
    return '<br>'.join(escape(part) for line in plain(text).splitlines()
                      for part in (textwrap.wrap(line, width) or ['']))


def resize_chart(chart, width, *, focused=False):
    """Reserve actual pixel space for the axes and every wrapped legend row."""
    width = max(200, int(width))
    left, right, top = 85, 25, 20
    plot_height = 500 if focused else max(260, int(width * 2 / 3) - 85)
    label_columns = max(12, int((width - left - right - 55) / 6.5))
    legend_height = 0
    with chart.batch_update():
        for trace in chart.data:
            if trace.showlegend:
                label = trace.meta['legend_label']
                display_label = wrapped(label, label_columns)
                trace.name = display_label
                # FigureWidget batches assignments until the context exits.
                legend_height += 18 * (display_label.count('<br>') + 1) + 8
        bottom = 76 + legend_height + 14
        chart.update_layout(width=width, height=plot_height + top + bottom,
            margin=dict(l=left, r=right, t=top, b=bottom),
            legend=dict(y=-76 / plot_height))


def text_block(widgets, text, *, title=False):
    """HTML flow prevents titles/captions colliding with the Plotly axes."""
    size, align, padding = (17, 'center', '8px 12px 0') if title else (11, 'left', '4px 12px 10px')
    content = '<br>'.join(escape(line) for line in plain(text).splitlines())
    block = widgets.HTML(
        f'<div style="font: {size}px/1.45 Arial,sans-serif; text-align:{align}; '
        f'white-space:normal; overflow-wrap:anywhere; padding:{padding}">{content}</div>',
        layout=widgets.Layout(width='100%', min_width='0'))
    block.add_class('tensile-plotly-title' if title else 'tensile-plotly-caption')
    return block


def figure_to_plotly(figure, *, width=640):
    """Translate the known 2D line/landmark plots, retaining every data point.

    Conversion is intentionally one-way: view zoom, legend clicks and resizing
    never modify the canonical figure, graph settings or exported data.
    """
    import plotly.graph_objects as go
    if len(figure.axes) != 1:
        raise ValueError('This Plotly view supports the workbench single-axis plots only.')
    ax = figure.axes[0]
    error_by_line, caps = {}, set()
    for container in ax.containers:
        if not isinstance(container, ErrorbarContainer):
            raise ValueError('Unsupported artist container; use Current static plots.')
        data_line, caplines, collections = container.lines
        caps.update(id(line) for line in caplines)
        errors, index = {}, 0
        for dim, active in (('x', container.has_xerr), ('y', container.has_yerr)):
            if not active:
                continue
            segments = collections[index].get_segments()
            index += 1
            coordinate = 0 if dim == 'x' else 1
            errors['error_' + dim] = dict(type='data', symmetric=True,
                array=[abs(float(seg[-1, coordinate] - seg[0, coordinate])) / 2 if len(seg) else 0 for seg in segments],
                thickness=1, width=4, visible=True)
        error_by_line[id(data_line)] = errors

    traces = []
    public = [(i, str(line.get_label())) for i, line in enumerate(ax.lines)
              if not str(line.get_label()).startswith('_')]
    group_ids = {i: f'group-{j}' for j, (i, _) in enumerate(public)}
    markers = {'o': 'circle', '^': 'triangle-up', 'v': 'triangle-down', 'x': 'x',
               '+': 'cross', 's': 'square', 'D': 'diamond', 'd': 'diamond', '*': 'star', '.': 'circle'}
    dashes = {'-': 'solid', '--': 'dash', ':': 'dot', '-.': 'dashdot'}
    individual_count = {}
    for index, line in enumerate(ax.lines):
        if id(line) in caps:
            continue
        x = np.asarray(line.get_xdata(), dtype=float)
        y = np.asarray(line.get_ydata(), dtype=float)
        if not len(x):
            continue
        label = str(line.get_label())
        visible_label = not label.startswith('_')
        faint = line.get_alpha() is not None and line.get_alpha() < .5
        before = [(i, name) for i, name in public if i <= index]
        after = [(i, name) for i, name in public if i >= index]
        # Specimens precede their group's mean; tails/landmarks follow it.
        parent = (after[0] if after else None) if faint else (before[-1] if before else None)
        parent = parent or (after[0] if after else (index, 'Curve'))
        group = group_ids.get(parent[0], f'curve-{index}')
        name = label if visible_label else parent[1]
        marker = str(line.get_marker())
        if faint:
            individual_count[group] = individual_count.get(group, 0) + 1
            name += f' · individual curve {individual_count[group]}'
        elif not visible_label:
            if marker in ('o', '^', 'x'):
                name += ' · ' + {'o': 'yield landmark', '^': 'UTS landmark', 'x': 'endpoint'}[marker]
            elif line.get_linestyle() == ':':
                name += ' · fitted tail'
            elif line.get_linestyle() == '--':
                name += ' · landmark average'
        has_line = line.get_linestyle() not in ('None', '', ' ', 'none')
        has_marker = marker not in ('None', '', ' ', 'none')
        mode = 'lines+markers' if has_line and has_marker else 'markers' if has_marker else 'lines'
        color = to_hex(line.get_color())
        trace = go.Scatter(x=x.tolist(), y=y.tolist(), mode=mode, name=plain(name),
            meta=dict(legend_label=plain(name)),
            showlegend=visible_label, legendgroup=group, connectgaps=False,
            opacity=1 if line.get_alpha() is None else float(line.get_alpha()),
            line=dict(color=color, width=float(line.get_linewidth()) * 1.3, dash=dashes.get(line.get_linestyle(), 'solid')),
            marker=dict(color=color, size=float(line.get_markersize()) * 1.3, symbol=markers.get(marker, 'circle')),
            hovertemplate=(escape(plain(name)) + '<br>' + escape(plain(ax.get_xlabel())) + ': %{x:.4f}<br>'
                           + escape(plain(ax.get_ylabel())) + ': %{y:.3f}<extra></extra>'),
            **error_by_line.get(id(line), {}))
        traces.append(trace)
    if not traces:
        raise ValueError('No curves available for the Plotly view.')
    result = go.Figure(data=traces)
    # Titles and notes belong to the surrounding widget flow, not to fixed
    # paper coordinates that compete with axis titles and the legend.
    result.update_layout(template='plotly_white', autosize=True,
        xaxis=dict(title=dict(text=plain(ax.get_xlabel()), standoff=15), automargin=True,
                   range=list(ax.get_xlim()), showline=True, mirror=True, zeroline=False),
        yaxis=dict(title=dict(text=plain(ax.get_ylabel()), standoff=15), automargin=True,
                   range=list(ax.get_ylim()), showline=True, mirror=True, zeroline=False),
        font=dict(family='Arial, sans-serif', size=12),
        legend=dict(orientation='v', x=0, xanchor='left', yanchor='top',
                    tracegroupgap=8, groupclick='togglegroup', font=dict(size=11)),
        dragmode='zoom', hovermode='closest', uirevision='exploration')
    resize_chart(result, width)
    return result


class PlotlyView:
    """Widget gallery with an enlarged view; navigation never reruns analysis."""
    def __init__(self, widgets, columns, plot_width):
        self.w, self.columns, self.plot_width = widgets, columns, plot_width
        w = widgets
        self._items, self._owned, self._charts, self._frames = [], [], {}, {}
        self._focused_key = None
        self.toolbar = w.HBox([columns, plot_width], layout=w.Layout(flex_flow='row wrap', gap='12px'))
        self.hint = w.HTML('Drag to zoom; use the plot toolbar to pan or reset. Click legend entries to hide/show groups. '
                          'View changes do not change averages or publication exports.')
        self.empty = w.HTML('Choose plots and click Update plots.')
        self.board = w.GridBox(layout=w.Layout(width='100%', grid_gap='16px', align_items='flex-start'))
        self.back = w.Button(description='Back to all plots', layout=w.Layout(width='auto'))
        self.choice = w.Dropdown(description='Plot:', layout=w.Layout(width='min(100%, 650px)'))
        self.focus_content = w.VBox(layout=w.Layout(width='100%'))
        self.focus = w.VBox([w.HBox([self.back, self.choice], layout=w.Layout(flex_flow='row wrap')),
                            self.focus_content], layout=w.Layout(display='none', width='100%'))
        self.ui = w.VBox([self.toolbar, self.hint, self.empty, self.board, self.focus], layout=w.Layout(width='100%'))
        self.back.on_click(lambda _: self.close_focus())
        self.choice.observe(self._choose, names='value')
        self._selecting = False

    def clear(self, message='Choose plots and click Update plots.'):
        self.close_focus()
        self.board.children = ()
        self.focus_content.children = ()
        self._selecting = True
        self.choice.options = []
        self._selecting = False
        for widget in reversed(self._owned):
            widget.close()
        self._owned, self._items, self._charts, self._frames = [], [], {}, {}
        self.empty.value = escape(message)
        self.empty.layout.display = ''

    def set_items(self, items):
        import plotly.graph_objects as go
        self.clear()
        self._items = list(items)
        cards = []
        for item in items:
            heading = self.w.HTML('<b>' + escape(item['label']) + '</b>')
            self._owned.append(heading)
            if item.get('result') is not None:
                try:
                    chart = go.FigureWidget(figure_to_plotly(item['result']['figure'], width=self.plot_width.value))
                    chart._config = {**chart._config, 'displaylogo': False, 'scrollZoom': True,
                                     'responsive': True, 'modeBarButtonsToRemove': ['toImage', 'select2d', 'lasso2d']}
                    self._charts[item['key']] = chart
                    probe = width_probe(lambda width, key=item['key']: self._resize(key, width))
                    figure = item['result']['figure']
                    title = text_block(self.w, figure.axes[0].get_title(), title=True)
                    notes = '\n'.join(text.get_text() for text in figure.texts if text.get_text())
                    caption = text_block(self.w, notes)
                    caption.layout.display = '' if notes else 'none'
                    frame = self.w.VBox([probe, title, chart, caption], layout=self.w.Layout(width='100%', min_width='0'))
                    self._frames[item['key']] = frame
                    button = self.w.Button(description='Enlarge plot', icon='expand', layout=self.w.Layout(width='auto'))
                    button.on_click(lambda _, key=item['key']: self.open_focus(key))
                    body = [heading, button, frame]
                    self._owned += [button, chart, probe, title, caption, frame]
                except Exception as error:
                    message = self.w.HTML('<b>Plotly unavailable:</b> ' + escape(str(error)) + '. Switch to Current static plots.')
                    self._owned.append(message)
                    body = [heading, message]
            else:
                message = self.w.HTML('Unavailable: ' + escape(item.get('error', 'No valid curves.')))
                self._owned.append(message)
                body = [heading, message]
            card = self.w.VBox(body, layout=self.w.Layout(width='100%', min_width='0'))
            self._owned.append(card)
            cards.append(card)
        self.board.children = tuple(cards)
        self._selecting = True
        self.choice.options = [(item['label'], item['key']) for item in items if item['key'] in self._charts]
        self._selecting = False
        self.empty.layout.display = 'none' if items else ''
        self.apply_layout()

    def apply_layout(self):
        columns, width = self.columns.value, self.plot_width.value
        self.board.layout.max_width = 'none' if columns == 0 else f'{columns * width + (columns - 1) * 16}px'
        self.board.layout.grid_template_columns = ('minmax(0, 1fr)' if columns == 1 else
            f'repeat(auto-fit, minmax(min(100%, {width}px), 1fr))')
        for card in self.board.children:
            card.layout.max_width = f'{width}px'
        for key, chart in self._charts.items():
            self._resize(key, chart.layout.width or width)

    def _resize(self, key, width):
        if key in self._charts:
            resize_chart(self._charts[key], width, focused=key == self._focused_key)

    def open_focus(self, key):
        if key not in self._charts:
            return
        self._focused_key = key
        self._selecting = True
        self.choice.value = key
        self._selecting = False
        self.focus_content.children = (self._frames[key],)
        self.board.layout.display = self.toolbar.layout.display = 'none'
        self.focus.layout.display = ''
        self.apply_layout()

    def close_focus(self):
        self._focused_key = None
        self.focus_content.children = ()
        self.board.layout.display = 'grid'
        self.toolbar.layout.display = 'flex'
        self.focus.layout.display = 'none'
        self.apply_layout()

    def _choose(self, _):
        if not self._selecting and self.choice.value is not None:
            self.open_focus(self.choice.value)
