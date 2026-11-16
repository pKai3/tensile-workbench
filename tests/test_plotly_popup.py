"""Interactive plots use the same dismissible gallery popup."""
import unittest

import ipywidgets as w
import matplotlib.pyplot as plt

from tensile_plotly import PlotlyView
from tensile_plot_theme import DARK_BACKGROUND


class PlotlyPopupTests(unittest.TestCase):
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
