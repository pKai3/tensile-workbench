"""The static plot gallery opens a fitted modal without changing plot results."""
import unittest

import ipywidgets as w

from tensile_plot_view import PlotView


class Figure:
    def get_size_inches(self):
        return (6, 4)


class StaticPlotPopupTests(unittest.TestCase):
    def test_fitted_popup_switches_and_returns_to_gallery(self):
        view = PlotView(w, w.Dropdown(options=[1, 2], value=1),
                        w.IntSlider(value=640, min=300, max=1200))
        self.addCleanup(view.clear)
        svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="600" height="400"/>'
        view.set_items([{'key': key, 'label': label, 'result': {'figure': Figure(), 'svg': svg}}
                        for key, label in [('one', 'First'), ('two', 'Second')]])

        view.open_focus('one')
        self.assertEqual(view.focus_popup.overlay.layout.display, 'flex')
        self.assertNotEqual(view.board.layout.display, 'none')
        self.assertEqual(view.viewport.layout.overflow, 'hidden')
        self.assertEqual(view.focus_popup.body.layout.overflow, 'hidden')
        self.assertIn('object-fit:contain', view.focus_image.value)
        self.assertIn('alt="First"', view.focus_image.value)

        view.choice.value = 'two'
        self.assertEqual(view._focused_key, 'two')
        self.assertIn('alt="Second"', view.focus_image.value)
        view.focus_popup.done.click()
        self.assertEqual(view.focus_popup.overlay.layout.display, 'none')
        self.assertIsNone(view._focused_key)
        self.assertNotEqual(view.board.layout.display, 'none')


if __name__ == '__main__':
    unittest.main()
