"""Interactive plots use the same dismissible gallery popup."""
import unittest
from unittest.mock import patch

import ipywidgets as w
import matplotlib.pyplot as plt
import plotly.graph_objects as go

from tensile_plotly import PlotlyView, rendered_trace_colors, restore_trace_colors
from tensile_plot_theme import DARK_BACKGROUND, dark_color


class PlotlyPopupTests(unittest.TestCase):
    def test_property_popup_keeps_each_group_colour_and_sd_bars(self):
        figure, axis = plt.subplots()
        self.addCleanup(plt.close, figure)
        palette = [('AB', '#d55e00'), ('SR', '#009e73'),
                   ('STA', '#a94f8b'), ('ST', '#0072b2')]
        for index, (name, color) in enumerate(palette):
            for specimen in range((8, 7, 8, 8)[index]):
                axis.plot([index + specimen * .03], [650 + index], 'o',
                          color=color, alpha=.3)
            bars = axis.errorbar([index], [650 + index], xerr=[.2], yerr=[5],
                                 fmt='D', color=color, label='_nolegend_')
            bars.lines[0].set_label(name)
        view = PlotlyView(w, w.Dropdown(options=[1], value=1),
                          w.IntSlider(value=640, min=300, max=1200))
        self.addCleanup(view.clear)
        view.set_items([{'key': 'properties', 'label': 'Properties',
                         'result': {'figure': figure}}])
        view._ensure_chart('properties')
        view._frames['properties'].children[0].theme = 'dark'
        view.open_focus('properties')
        means = {trace.meta['legend_label']: trace for trace in view._popup_chart.data
                 if trace.showlegend}
        self.assertEqual(set(means), {name for name, _ in palette})
        for name, color in palette:
            trace = means[name]
            self.assertEqual(trace.marker.color, dark_color(color))
            self.assertEqual(trace.error_x.color, trace.marker.color)
            self.assertEqual(trace.error_y.color, trace.marker.color)
        styles = rendered_trace_colors(view._base_figures['properties'], theme='dark')
        self.assertEqual(len(styles), 35)
        self.assertTrue(all('marker.line.color' not in style for style in styles))
        with patch.object(go.FigureWidget, '_send_restyle_msg') as send:
            restore_trace_colors(view._popup_chart)
        sent = {}
        for call in send.call_args_list:
            for position, index in enumerate(call.kwargs['trace_indexes']):
                for path, values in call.args[0].items():
                    sent[index, path] = values[position]
        for name in ('SR', 'STA'):
            trace = means[name]
            index = list(view._popup_chart.data).index(trace)
            self.assertEqual(sent[index, 'marker.color'], trace.marker.color)
            self.assertEqual(sent[index, 'error_x.color'], trace.error_x.color)
        sr_index = list(view._popup_chart.data).index(means['SR'])
        self.assertEqual(sr_index, 16)
        view._popup_chart.data[sr_index].marker.color = '#FF6692'
        view._popup_widgets[1].theme = 'dark'
        self.assertEqual(view._popup_widgets[1].trace_styles[sr_index]['marker.color'], '#009e73')

    def test_explicit_colours_are_restyled_even_when_model_is_unchanged(self):
        chart = go.FigureWidget(data=[
            go.Scatter(y=[1, 2], line_color='#009e73', marker_color='#009e73'),
            go.Scatter(y=[2, 3], line_color='#d55e00', marker_color='#d55e00'),
        ])
        self.addCleanup(chart.close)
        with patch.object(go.FigureWidget, '_send_restyle_msg') as send:
            restore_trace_colors(chart)
        self.assertEqual(send.call_count, 1)
        styles = send.call_args.args[0]
        self.assertEqual(styles['line.color'], ['#009e73', '#d55e00'])
        self.assertEqual(styles['marker.color'], ['#009e73', '#d55e00'])
        self.assertEqual(send.call_args.kwargs['trace_indexes'], [0, 1])
        self.assertEqual(chart.data[0].line.color, '#009e73')

    def test_popup_switches_plots_and_fits_viewport_height(self):
        figure, axis = plt.subplots()
        self.addCleanup(plt.close, figure)
        axis.plot([0, 1], [0, 1], label='Synthetic', color='#009e73')
        axis.legend()
        view = PlotlyView(w, w.Dropdown(options=[1, 2], value=1),
                          w.IntSlider(value=640, min=300, max=1200))
        self.addCleanup(view.clear)
        view.set_items([{'key': key, 'label': label, 'result': {'figure': figure}}
                        for key, label in [('one', 'First'), ('two', 'Second')]])

        first_card, second_card = view.board.children
        first_frame, second_frame = view._frames['one'], view._frames['two']
        self.assertIn(first_frame, first_card.children)
        view._ensure_chart('one')
        self.assertIsNone(first_frame.children[1].layout.width)
        first_frame.children[0].theme = 'dark'
        original_colour = view._charts['one'].data[0].line.color
        view._charts['one'].update_xaxes(range=[.2, .8])
        view.open_focus('one')
        self.assertEqual(view.focus_popup.overlay.layout.display, 'flex')
        self.assertIn(first_frame, first_card.children)
        self.assertIsNot(view._popup_chart, view._charts['one'])
        self.assertIs(view.focus_content.children[0].children[2], view._popup_chart)
        self.assertEqual(view._charts['one'].data[0].line.color, original_colour)
        self.assertEqual(view._popup_chart.data[0].line.color, original_colour)
        self.assertEqual(view._popup_chart.layout.paper_bgcolor, DARK_BACKGROUND)
        self.assertEqual(view._popup_chart.layout.xaxis.range, (.2, .8))
        self.assertEqual(view._popup_chart.layout.xaxis.minallowed,
                         view._charts['one'].layout.xaxis.minallowed)
        self.assertEqual(view._popup_chart.layout.xaxis.maxallowed,
                         view._charts['one'].layout.xaxis.maxallowed)
        view._popup_chart.data[0].line.color = '#FF6692'  # Simulate a frontend fallback.
        self.assertEqual(view._charts['one'].data[0].line.color, original_colour)
        self.assertEqual(view.focus_popup.body.layout.overflow, 'hidden')
        view._set_viewport_height(700)
        self.assertLessEqual(view._popup_chart.layout.height, int(700 * .9) - 180)

        view.choice.value = 'two'
        self.assertEqual(view._focused_key, 'two')
        self.assertIn(first_frame, first_card.children)
        self.assertIn(second_frame, second_card.children)
        self.assertIsNot(view._popup_chart, view._charts['two'])
        self.assertEqual(view.focus_popup.overlay.layout.display, 'flex')
        view.focus_popup.done.click()
        self.assertIsNone(view._focused_key)
        self.assertIn(second_frame, second_card.children)
        self.assertEqual(view.focus_popup.overlay.layout.display, 'none')
        self.assertIsNone(view._popup_chart)
        self.assertEqual(view._charts['one'].data[0].line.color, original_colour)
        self.assertNotEqual(view.board.layout.display, 'none')


if __name__ == '__main__':
    unittest.main()
