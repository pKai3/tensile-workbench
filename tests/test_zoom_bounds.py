"""Interactive zoom is bounded without changing trace values or exports."""
import unittest
import plotly.graph_objects as go
from tensile_plotly import limit_zoom, width_probe


class ZoomBoundsTests(unittest.TestCase):
    def test_explicit_limits_and_new_inspector_view(self):
        fig = go.FigureWidget(go.Figure(go.Scatter(x=[0, 1, 2], y=[0, 100, 80])))
        self.addCleanup(fig.close)
        fig.update_layout(xaxis_range=[-.1, 2.1], yaxis_range=[-5, 110],
                          yaxis2=dict(range=[20, 0], overlaying='y', side='right'))
        limit_zoom(fig)
        self.assertEqual((fig.layout.xaxis.minallowed, fig.layout.xaxis.maxallowed), (-.1, 2.1))
        self.assertEqual((fig.layout.yaxis2.minallowed, fig.layout.yaxis2.maxallowed), (0, 20))
        limit_zoom(fig, {'xaxis': [0, .5], 'yaxis': [0, 50]})
        self.assertEqual(fig.layout.xaxis.maxallowed, .5)
        self.assertEqual(list(fig.data[0].x), [0, 1, 2])
        self.assertEqual(list(fig.data[0].y), [0, 100, 80])

    def test_first_browser_autorange_cannot_replace_detail_bounds(self):
        fig = go.FigureWidget(go.Figure(go.Scatter(x=[0, 1], y=[0, 10])))
        self.addCleanup(fig.close)
        probe = width_probe(lambda _: None, charts=(fig,))
        self.addCleanup(probe.close)
        message = {'action': 'zoom_bounds', 'index': 0, 'axes': {'xaxis': [-.1, 1.1], 'yaxis': [-1, 11]}}
        probe._handle_custom_msg(message, [])
        self.assertEqual(fig.layout.xaxis.maxallowed, 1.1)
        limit_zoom(fig, {'xaxis': [0, .5]})
        probe._handle_custom_msg(message, [])
        self.assertEqual(fig.layout.xaxis.maxallowed, .5)
