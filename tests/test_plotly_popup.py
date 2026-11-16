"""Interactive plots use the same dismissible gallery popup."""
import unittest

import ipywidgets as w
import matplotlib.pyplot as plt

from tensile_plotly import PlotlyView


class PlotlyPopupTests(unittest.TestCase):
    def test_popup_switches_plots_and_fits_viewport_height(self):
        figure, axis = plt.subplots()
        self.addCleanup(plt.close, figure)
        axis.plot([0, 1], [0, 1], label='Synthetic')
        axis.legend()
        view = PlotlyView(w, w.Dropdown(options=[1, 2], value=1),
                          w.IntSlider(value=640, min=300, max=1200))
        self.addCleanup(view.clear)
        view.set_items([{'key': key, 'label': label, 'result': {'figure': figure}}
                        for key, label in [('one', 'First'), ('two', 'Second')]])

        view.open_focus('one')
        self.assertEqual(view.focus_popup.overlay.layout.display, 'flex')
        self.assertEqual(view.board.layout.display, 'none')
        self.assertEqual(view.focus_popup.body.layout.overflow, 'hidden')
        view._set_viewport_height(700)
        self.assertLessEqual(view._charts['one'].layout.height, int(700 * .9) - 180)

        view.choice.value = 'two'
        self.assertEqual(view._focused_key, 'two')
        self.assertEqual(view.focus_popup.overlay.layout.display, 'flex')
        view.focus_popup.done.click()
        self.assertIsNone(view._focused_key)
        self.assertEqual(view.focus_popup.overlay.layout.display, 'none')
        self.assertEqual(view.board.layout.display, 'grid')


if __name__ == '__main__':
    unittest.main()
