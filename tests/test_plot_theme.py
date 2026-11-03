"""Interactive appearance must not change calculations, exports or manual edits."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import ipywidgets as w
import matplotlib.pyplot as plt
import numpy as np
import plotly.graph_objects as go

from selection_fixture import make_fixture
from test_relative_comparison import frames
from tensile_plot_theme import apply_plot_theme, dark_color, DARK_BACKGROUND, source_color
from tensile_plotly import PlotlyView, figure_to_plotly, resize_chart
from tensile_workbench import TensileWorkbench


class PlotAppearanceTests(unittest.TestCase):
    def test_dark_light_roundtrip_preserves_data_zoom_visibility_and_shape_geometry(self):
        fig = go.FigureWidget(go.Figure([
            go.Scatter(x=[0, 1, 2], y=[0, 2, 3], line_color='#334155',
                       marker={'color': '#7c3aed', 'symbol': 'diamond-open'}, visible='legendonly',
                       error_y={'array': [.1, .2, .3]}, meta={'specimen': 'Synthetic'}),
            go.Bar(x=[0, 1], y=[2, 3], marker_color=['#003366', '#ffcc00'], yaxis='y2')],
            layout=go.Layout(template='plotly_white', xaxis_range=[.1, 1.5], yaxis_range=[1, 4],
                             yaxis2={'overlaying': 'y', 'side': 'right', 'range': [0, 5]},
                             annotations=[{'text': 'R² = 0.99800', 'font': {'color': '#334155'}, 'x': 0, 'y': 1}],
                             shapes=[{'type': 'line', 'name': 'fit-line', 'editable': True, 'x0': .1,
                                      'x1': .4, 'y0': 100, 'y1': 400, 'line': {'color': '#7c3aed'}}])))
        self.addCleanup(fig.close)
        def content(value):
            # Plotly leaves empty style containers after resetting their fields.
            if isinstance(value, dict):
                return {key: clean for key, item in value.items() if (clean := content(item)) != {}}
            return [content(item) for item in value] if isinstance(value, list) else value
        before = content(json.loads(fig.to_json()))
        for _ in range(2):
            apply_plot_theme(fig, 'dark')
            self.assertEqual(fig.layout.paper_bgcolor, DARK_BACKGROUND)
            self.assertNotEqual(fig.data[0].line.color, '#334155')
            self.assertEqual(source_color(fig.data[0].line), '#334155')
            self.assertEqual(fig.data[0].visible, 'legendonly')
            self.assertEqual(fig.layout.xaxis.range, (.1, 1.5))
            self.assertEqual(fig.layout.yaxis2.range, (0, 5))
            self.assertEqual(fig.layout.shapes[0].x0, .1)
            apply_plot_theme(fig, 'light')
            self.assertEqual(content(json.loads(fig.to_json())), before)
        self.assertEqual(dark_color('#ffcc00'), '#ffcc00')
        self.assertEqual(dark_color([1., 2.]), [1., 2.])
        self.assertTrue(dark_color('rgba(20,30,40,0.1)').endswith(',0.1)'))

    def test_two_column_gallery_legend_wraps_and_leaves_export_artists_untouched(self):
        fig, ax = plt.subplots()
        self.addCleanup(plt.close, fig)
        labels = [f'Synthetic treatment {i} with a long explanatory name (n=8)' for i in range(6)]
        for index, label in enumerate(labels):
            ax.plot([0, 1, 2], [index, index + 1, index + 2], label=label, color='#334155')
        chart = figure_to_plotly(fig, width=640)
        self.assertEqual(chart.layout.legend.orientation, 'h')
        self.assertEqual(chart.layout.legend.entrywidthmode, 'fraction')
        self.assertEqual(chart.layout.legend.entrywidth, .5)
        self.assertTrue(all('<br>' in trace.name for trace in chart.data))
        for trace, label in zip(chart.data, labels):
            self.assertEqual(trace.meta['legend_label'], label)
        before = [line.get_color() for line in ax.lines]
        apply_plot_theme(chart, 'dark')
        self.assertEqual([line.get_color() for line in ax.lines], before)
        self.assertEqual([line.get_label() for line in ax.lines], labels)
        chart.update_xaxes(range=[.5, 1.5])
        resize_chart(chart, 1000, focused=True)
        self.assertEqual(chart.layout.xaxis.range, (.5, 1.5))
        self.assertEqual(chart.layout.legend.entrywidth, .5)
        self.assertGreater(chart.layout.margin.b, 100)
        resize_chart(chart, 300)
        self.assertEqual(chart.layout.legend.entrywidth, 1.)

    def test_live_views_restyle_without_refits_or_changing_saved_or_draft_state(self):
        with tempfile.TemporaryDirectory(prefix='tw-theme-synthetic-') as temp:
            root = Path(temp)
            make_fixture(root)
            with redirect_stdout(io.StringIO()):
                app = TensileWorkbench(root)
            self.addCleanup(app.tables.clear)
            inspector = app.tables.inspector
            inspector.select('Alloy A/coupon_1.csv')
            inspector.mode.value = 'range'
            draft = deepcopy(inspector._draft)
            inspector.chart.update_xaxes(range=[.1, .45])
            group = app.tables.group_review
            group.set_active(True)
            yields = app.tables.yield_review
            yields.set_active(True)
            comparison = app.tables.comparison
            comparison.set_frames(frames(), ['A', 'B'])
            comparison.ui.selected_index = 0
            before = app.store.path.read_bytes()
            with patch('tensile_inspector.specimen_calculation', side_effect=AssertionError('Theme refitted specimen')), \
                    patch('tensile_yield_review.specimen_calculation', side_effect=AssertionError('Theme refitted group')):
                inspector._probe.theme = 'dark'
                group.plot.children[0].theme = 'dark'
                yields.plot.children[0].theme = 'dark'
                comparison.probe.theme = 'dark'
                for chart in [inspector.chart, group.figure, *[entry['figure'] for entry in yields.entries],
                              *comparison.charts.values()]:
                    self.assertEqual(chart.layout.plot_bgcolor, DARK_BACKGROUND)
                self.assertEqual(inspector._draft, draft)
                self.assertEqual(inspector.chart.layout.xaxis.range, (.1, .45))
                # New marker traces inherit the currently active plot theme.
                group.markers['YS'].value = True
                self.assertEqual(group.figure._tw_theme, 'dark')
                inspector._probe.theme = 'light'
                self.assertEqual(inspector._draft, draft)
            self.assertEqual(app.store.path.read_bytes(), before)
            self.assertFalse((root / 'output').exists())

    def test_gallery_theme_bridge_also_applies_to_lazily_created_chart(self):
        fig, ax = plt.subplots()
        self.addCleanup(plt.close, fig)
        ax.plot([0, 1], [0, 1], color='black', label='Synthetic')
        view = PlotlyView(w, w.Dropdown(options=[1, 2], value=1), w.IntSlider(value=640, max=1200))
        self.addCleanup(view.clear)
        view.set_items([{'key': 'one', 'label': 'Synthetic', 'result': {'figure': fig}}])
        self.assertFalse(view._charts)
        view.open_focus('one')
        probe = view._frames['one'].children[0]
        probe.theme = 'dark'  # browser supplies its current theme on mount
        self.assertEqual(view._charts['one'].layout.paper_bgcolor, DARK_BACKGROUND)
        self.assertNotEqual(view._charts['one'].data[0].line.color, '#000000')
        probe.theme = 'light'
        self.assertEqual(view._charts['one'].data[0].line.color, '#000000')


if __name__ == '__main__':
    unittest.main()
