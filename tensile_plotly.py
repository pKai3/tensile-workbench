"""Plotly view of already-calculated Matplotlib artists; no analysis or file I/O."""
from html import escape
import textwrap
import numpy as np
from matplotlib.colors import to_hex
from matplotlib.container import ErrorbarContainer, BarContainer
from tensile_display import preview_indices
from tensile_plot_theme import apply_plot_theme


def width_probe(on_resize, *, on_theme=None, charts=()):
    """Sync browser size/appearance to display-only callbacks, never calculations."""
    import anywidget
    import traitlets
    for chart in charts:
        chart.add_class('tw-themed-plot')
    class WidthProbe(anywidget.AnyWidget):
        pixels = traitlets.Int(0).tag(sync=True)
        theme = traitlets.Enum(['light', 'dark'], default_value='light').tag(sync=True)
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
          let fallback, paint, drawing;
          const plots = () => el.closest('.tw-plot-theme-host')?.querySelectorAll('.tw-themed-plot') || [];
          const painted = () => {
            const theme=document.documentElement.dataset.twTheme === 'dark' ? 'dark' : 'light';
            plots().forEach(plot => {
              const svg=plot.querySelector('.main-svg');
              const background=svg && getComputedStyle(svg).backgroundColor;
              const expected=theme === 'dark' ? 'rgb(18, 28, 40)' : 'rgb(255, 255, 255)';
              if(background === expected) {
                plot.classList.remove('tw-theme-light','tw-theme-dark');
                plot.classList.add('tw-theme-' + theme);
              }
            });
          };
          const watchPaint = () => {
            const host=el.closest('.tw-plot-theme-host');
            if(!el.isConnected || !host) {paint=requestAnimationFrame(watchPaint); return;}
            drawing=new MutationObserver(() => {
              cancelAnimationFrame(paint); paint=requestAnimationFrame(painted);
            });
            drawing.observe(host,{subtree:true,childList:true,attributes:true,attributeFilter:['style']});
            painted();
          };
          const appearance = () => {
            const theme = document.documentElement.dataset.twTheme === 'dark' ? 'dark' : 'light';
            clearTimeout(fallback); cancelAnimationFrame(paint); drawing?.disconnect();
            plots().forEach(plot => plot.classList.remove('tw-theme-fallback','tw-theme-light','tw-theme-dark'));
            watchPaint();
            fallback = setTimeout(() => {
              cancelAnimationFrame(paint); drawing?.disconnect(); painted();
              plots().forEach(plot => {
                if(!plot.classList.contains('tw-theme-' + theme)) plot.classList.add('tw-theme-fallback');
              });
            }, 5000);
            if(theme !== model.get('theme')) {model.set('theme',theme); model.save_changes();}
          };
          const themes = new MutationObserver(appearance);
          themes.observe(document.documentElement,{attributes:true,attributeFilter:['data-tw-theme']});
          appearance();
          return () => {observer.disconnect(); themes.disconnect(); drawing?.disconnect(); cancelAnimationFrame(frame); cancelAnimationFrame(paint); clearTimeout(fallback);};
        }};
        """
    probe = WidthProbe()
    probe.observe(lambda change: on_resize(change['new']) if change['new'] > 150 else None, names='pixels')
    if on_theme is not None:
        probe.observe(lambda change: on_theme(change['new']), names='theme')
    return probe


def visibility_probe(on_visible):
    """Create a chart only when its gallery card approaches the viewport."""
    import anywidget
    import traitlets
    class VisibilityProbe(anywidget.AnyWidget):
        visible = traitlets.Bool(False).tag(sync=True)
        _esm = """
        export default {render({model, el}) {
          el.style.height='1px'; el.style.minHeight='1px'; el.style.margin='0'; el.style.width='100%';
          let observer, frame, done=false, target;
          const stop = () => {
            observer?.disconnect(); cancelAnimationFrame(frame);
            window.removeEventListener('scroll', schedule, true);
            window.removeEventListener('resize', schedule);
          };
          const reveal = () => {
            if(done) return;
            done=true; stop();
            model.set('visible',true); model.save_changes();
          };
          const nearby = () => {
            const rect=target.getBoundingClientRect();
            if(rect.width > 0 && rect.height > 0 && rect.top < window.innerHeight + 1000 && rect.bottom > -1000) reveal();
          };
          const schedule = () => {cancelAnimationFrame(frame); frame=requestAnimationFrame(nearby);};
          const attach = () => {
            // Observe the entire reserved chart area. A one-pixel sentinel can
            // be missed when scrolling/jumping into the middle of a tall card.
            target=el.closest('.tw-lazy-plot');
            if(!el.isConnected || !target) {frame=requestAnimationFrame(attach); return;}
            if(typeof IntersectionObserver === 'undefined') {reveal(); return;}
            observer=new IntersectionObserver(entries => {
              if(entries.some(entry => entry.isIntersecting)) reveal();
            }, {rootMargin:'1000px 0px'});
            observer.observe(target);
            // Widget scroll containers can clip IntersectionObserver's margin.
            // This throttled viewport check also covers those nested scrollers.
            window.addEventListener('scroll', schedule, true);
            window.addEventListener('resize', schedule);
            nearby();
          };
          attach();
          return () => {done=true; stop();};
        }};
        """
    probe = VisibilityProbe()
    probe.observe(lambda change: on_visible() if change['new'] else None, names='visible')
    return probe


def plain(text):
    return str(text).replace(r'$\Theta$', 'Θ').replace('$', '')


def wrapped(text, width=75):
    return '<br>'.join(escape(part) for line in plain(text).splitlines()
                      for part in (textwrap.wrap(line, width) or ['']))


def resize_chart(chart, width, *, focused=False):
    """Reserve actual pixel space for the axes and every wrapped legend row."""
    width = max(200, int(width))
    left, right, top = 85, (85 if 'yaxis2' in chart.layout else 25), 20
    plot_height = 500 if focused else max(260, int(width * 2 / 3) - 85)
    legend_columns = 2 if width - left - right >= 240 else 1
    label_columns = max(4, int(((width - left - right) / legend_columns - 55) / 6.5))
    legend_rows = []
    categories = (chart.layout.meta or {}).get('category_labels')
    axis_footer = 76
    with chart.batch_update():
        if categories is not None:
            # Reflow category labels when a card is resized or enlarged, not
            # just when the numerical figure is first rendered.
            slot = max(1, (width - left - right) / max(1, len(categories)))
            columns = max(1, min(22, int(slot * .85 / 6.5)))
            labels = [wrapped(label, columns) for label in categories]
            axis_footer = 60 + 14 * max((label.count('<br>') + 1 for label in labels), default=1)
            chart.update_xaxes(ticktext=labels, tickangle=0)
        for trace in sorted(chart.data, key=lambda trace: trace.legendrank if trace.legendrank is not None else 1000):
            if trace.showlegend:
                label = trace.meta['legend_label']
                display_label = wrapped(label, label_columns)
                trace.name = display_label
                # FigureWidget batches assignments until the context exits.
                legend_rows.append(18 * (display_label.count('<br>') + 1) + 8)
        legend_height = sum(max(legend_rows[start:start + legend_columns])
                            for start in range(0, len(legend_rows), legend_columns))
        bottom = axis_footer + legend_height + 14
        chart.update_layout(width=width, height=plot_height + top + bottom,
            margin=dict(l=left, r=right, t=top, b=bottom),
            legend=dict(y=-axis_footer / plot_height, orientation='h',
                        entrywidth=1 / legend_columns, entrywidthmode='fraction',
                        traceorder='normal', tracegroupgap=0))
        if hasattr(chart.layout.legend, 'maxheight'):
            chart.layout.legend.maxheight = max(30, legend_height + 10)


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
    """Translate calculated artists, using a simple subset for dense lines.

    Conversion is intentionally one-way: view zoom, legend clicks and resizing
    never modify the canonical figure, analysis settings or exported data.
    """
    if len(figure.axes) == 1:
        return _axis_to_plotly(figure.axes[0], width=width)
    if len(figure.axes) != 2 or not getattr(figure, '_tensile_group_plot', False):
        raise ValueError('Unsupported multi-axis figure; use Static plots.')
    result = _axis_to_plotly(figure.axes[0], width=width, allow_empty=True)
    secondary = _axis_to_plotly(figure.axes[1], width=width, allow_empty=True)
    for trace in secondary.data:
        trace.yaxis = 'y2'
        trace.legendgroup = 'right-' + trace.legendgroup
        result.add_trace(trace)
    right_axis = secondary.layout.yaxis.to_plotly_json()
    right_axis.update(overlaying='y', side='right', showgrid=False, mirror=False)
    result.update_layout(yaxis2=right_axis, yaxis_mirror=False)
    resize_chart(result, width)
    return result


def _axis_to_plotly(ax, *, width=640, allow_empty=False):
    """Convert one axis, including categorical labels when supplied by a plot."""
    import plotly.graph_objects as go
    categories = getattr(ax, '_tensile_category_labels', None)
    category_hover = getattr(ax, '_tensile_category_hover_labels', categories)
    error_by_line, caps, bars = {}, set(), []
    for container in ax.containers:
        if isinstance(container, BarContainer):
            bars.append(container)
            continue
        if not isinstance(container, ErrorbarContainer):
            raise ValueError('Unsupported artist container; use Static plots.')
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
    for index, container in enumerate(bars):
        patches = container.patches
        if not patches:
            continue
        label = str(container.get_label())
        centers = [p.get_x() + p.get_width() / 2 for p in patches]
        locations = getattr(container, '_tensile_locations', centers)
        labels = getattr(container, '_tensile_point_labels', [''] * len(patches))
        places = getattr(ax, '_tensile_x_places', 2)
        x_hover = (escape(plain(ax.get_xlabel())) + ': %{customdata[1]:.' + str(places) + 'f}'
                   if categories is None else '')
        traces.append(go.Bar(x=centers, y=[p.get_height() for p in patches],
            base=[p.get_y() for p in patches], width=[p.get_width() for p in patches],
            marker=dict(color=[to_hex(p.get_facecolor()) for p in patches]),
            opacity=1 if patches[0].get_alpha() is None else patches[0].get_alpha(),
            name=plain(label), meta=dict(legend_label=plain(label)), showlegend=not label.startswith('_'),
            legendgroup=getattr(container, '_tensile_series_key', f'bar-{index}'),
            legendrank=getattr(container, '_tensile_legend_rank', 1000),
            customdata=[[escape(plain(name)), value] for name, value in zip(labels, locations)],
            hovertemplate=(escape(plain(label)) + '<br>Specimen: %{customdata[0]}'
                           + ('<br>' + x_hover if x_hover else '') + '<br>'
                           + escape(plain(ax.get_ylabel())) + ': %{y:.2f}<extra></extra>')))
    public = [(i, str(line.get_label())) for i, line in enumerate(ax.lines)
              if not str(line.get_label()).startswith('_')]
    group_ids = {i: f'group-{j}' for j, (i, _) in enumerate(public)}
    markers = {'o': 'circle', '^': 'triangle-up', 'v': 'triangle-down', 'x': 'x',
               '+': 'cross', 's': 'square', 'D': 'diamond', 'd': 'diamond', '*': 'star', '.': 'circle'}
    dashes = {'-': 'solid', '--': 'dash', ':': 'dot', '-.': 'dashdot'}
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
        group = getattr(line, '_tensile_series_key', group)
        name = label if visible_label else parent[1]
        marker = str(line.get_marker())
        if faint:
            name = getattr(line, '_tensile_hover_label', None) or name + ' · specimen (name unavailable)'
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
        hover_name = getattr(line, '_tensile_hover_label', None) or name
        counts = getattr(line, '_tensile_counts', None)
        custom = ([[escape(category_hover[int(value)]), counts[i] if counts is not None else None]
                   for i, value in enumerate(x)] if categories is not None else None)
        point_labels = getattr(line, '_tensile_point_labels', None)
        if point_labels is not None:
            custom = [[escape(label), counts[i] if counts is not None else None]
                      for i, label in enumerate(point_labels)]
        count_hover = '<br>n=%{customdata[1]}' if counts is not None else ''
        landmark_counts = getattr(line, '_tensile_landmark_counts', None)
        if landmark_counts is not None:
            custom = [[landmark_counts['x'], landmark_counts['y']] for _ in x]
            count_hover = '<br>Strain n=%{customdata[0]}<br>Stress n=%{customdata[1]}'
        places = getattr(ax, '_tensile_x_places', 2)
        x_hover = ('Sample group: %{customdata[0]}' if categories is not None else
                   escape(plain(ax.get_xlabel())) + ': %{x:.' + str(places) + 'f}')
        if point_labels is not None:
            kind = escape(getattr(line, '_tensile_point_kind', 'Sample group'))
            x_hover = kind + ': %{customdata[0]}' + ('<br>' + x_hover if categories is None else '')
        # Dense lines only: individual property dots, landmarks and error bars
        # keep their exact values. The source artists/export arrays stay intact.
        if has_line and not has_marker and id(line) not in error_by_line:
            ids = preview_indices(x, y)
            x, y = x[ids], y[ids]
            if custom is not None:
                custom = [custom[i] for i in ids]
        trace = go.Scatter(x=x.tolist(), y=y.tolist(), mode=mode, name=plain(name),
            customdata=custom,
            meta=dict(legend_label=plain(name)),
            showlegend=visible_label, legendgroup=group, connectgaps=False,
            legendrank=getattr(line, '_tensile_legend_rank', 1000),
            opacity=1 if line.get_alpha() is None else float(line.get_alpha()),
            line=dict(color=color, width=float(line.get_linewidth()) * 1.3, dash=dashes.get(line.get_linestyle(), 'solid')),
            marker=dict(color=color, size=float(line.get_markersize()) * 1.3, symbol=markers.get(marker, 'circle')),
            hovertemplate=(escape(plain(hover_name)) + '<br>' + x_hover + '<br>'
                           + escape(plain(ax.get_ylabel())) + ': %{y:.2f}'
                           + count_hover + '<extra></extra>'),
            **error_by_line.get(id(line), {}))
        traces.append(trace)
    if not traces and not allow_empty:
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
    if bars:
        # Offsets are already explicit, including bars on the secondary axis.
        result.update_layout(barmode='overlay')
    if categories is not None:
        result.update_layout(meta={'category_labels': list(categories)})
        result.update_xaxes(tickmode='array', tickvals=list(range(len(categories))),
                            ticktext=[wrapped(label, 22) for label in categories])
    elif hasattr(ax, '_tensile_numeric_ticks'):
        result.update_xaxes(tickmode='array', tickvals=list(ax._tensile_numeric_ticks))
    if getattr(ax, '_tensile_x_places', None) == 0:
        result.update_xaxes(tickformat='.0f', hoverformat='.0f')
    resize_chart(result, width)
    return result


class PlotlyView:
    """Widget gallery with an enlarged view; navigation never reruns analysis."""
    def __init__(self, widgets, columns, plot_width):
        self.w, self.columns, self.plot_width = widgets, columns, plot_width
        w = widgets
        self._items, self._owned, self._charts, self._frames = [], [], {}, {}
        self._focused_key = None
        self.toolbar = w.HBox([columns, plot_width], layout=w.Layout(flex_flow='row wrap', grid_gap='12px'))
        self.hint = w.HTML('Drag to zoom; use the plot toolbar to pan or reset. Click legend entries to hide/show groups. '
                          'Dense lines show every Nth reading; use the specimen inspector for full detail. '
                          'Calculations and publication exports use the full data.')
        self.empty = w.HTML('Choose plots and click Update plots.')
        self.board = w.GridBox(layout=w.Layout(width='100%', grid_gap='16px', align_items='flex-start'))
        self.board.add_class('tw-plot-board')
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
        self.clear()
        self._items = list(items)
        cards = []
        for item in items:
            heading = self.w.HTML('<b>' + escape(item['label']) + '</b>')
            self._owned.append(heading)
            if item.get('result') is not None:
                frame = self.w.VBox(layout=self.w.Layout(width='100%', min_width='0'))
                frame.add_class('tw-lazy-plot')
                frame.add_class('tw-plot-theme-host')
                self._frames[item['key']] = frame
                probe = visibility_probe(lambda key=item['key'], owner=frame: self._ensure_chart(key, owner))
                placeholder = self.w.HTML('Plot loads when visible.', layout=self.w.Layout(
                    height=f'{max(300, int(self.plot_width.value * 2 / 3))}px'))
                frame.children = (probe, placeholder)
                button = self.w.Button(description='Enlarge plot', icon='expand', layout=self.w.Layout(width='auto'))
                button.on_click(lambda _, key=item['key']: self.open_focus(key))
                body = [heading, button, frame]
                self._owned += [button, probe, placeholder, frame]
            else:
                message = self.w.HTML('Unavailable: ' + escape(item.get('error', 'No valid curves.')))
                self._owned.append(message)
                body = [heading, message]
            if item.get('warning'):
                warning = self.w.HTML('<div style="background:var(--tw-warning-bg,#fff7e6);color:var(--tw-warning-text,inherit);'
                                      'border-left:3px solid var(--tw-warning-border,#d97706);padding:8px;white-space:normal">'
                                      + escape(item['warning']) + '</div>')
                body.insert(1, warning)
                self._owned.append(warning)
            card = self.w.VBox(body, layout=self.w.Layout(width='100%', min_width='0'))
            self._owned.append(card)
            cards.append(card)
        self.board.children = tuple(cards)
        self._selecting = True
        self.choice.options = [(item['label'], item['key']) for item in items if item['key'] in self._frames]
        self._selecting = False
        self.empty.layout.display = 'none' if items else ''
        self.apply_layout()

    def _ensure_chart(self, key, owner=None):
        frame = self._frames.get(key)
        if frame is None or (owner is not None and frame is not owner):
            return False  # Ignore a visibility message from a replaced gallery.
        if key in self._charts:
            return True
        import plotly.graph_objects as go
        item = next(item for item in self._items if item['key'] == key)
        old = frame.children
        try:
            figure = item['result']['figure']
            chart = go.FigureWidget(figure_to_plotly(figure, width=self.plot_width.value))
            chart._config = {**chart._config, 'displaylogo': False, 'scrollZoom': True,
                             'responsive': True, 'modeBarButtonsToRemove': ['toImage', 'select2d', 'lasso2d']}
            self._charts[key] = chart
            probe = width_probe(lambda width: self._resize(key, width),
                                on_theme=lambda theme: apply_plot_theme(chart, theme), charts=(chart,))
            title = text_block(self.w, figure.axes[0].get_title(), title=True)
            notes = '\n'.join(text.get_text() for text in figure.texts if text.get_text())
            caption = text_block(self.w, notes)
            caption.layout.display = '' if notes else 'none'
            frame.children = (probe, title, chart, caption)
            self._owned += [chart, probe, title, caption]
            return True
        except Exception as error:
            message = self.w.HTML('<b>Plotly unavailable:</b> ' + escape(str(error)) + '. Switch to Static plots.')
            frame.children = (message,)
            self._owned.append(message)
            return False
        finally:
            for widget in old:
                widget.close()

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
        if not self._ensure_chart(key):
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
