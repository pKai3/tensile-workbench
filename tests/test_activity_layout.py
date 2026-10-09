"""Busy-state and fixed-layout regressions; no tensile data needed."""
import unittest
from pathlib import Path

from tensile_activity import BusyOverlay, busy
from tensile_page_layout import ContentWidth


class ActivityLayoutTests(unittest.TestCase):
    def setUp(self):
        self.activity = BusyOverlay()
        self.addCleanup(self.activity.close)

    def test_nested_scopes_keep_page_busy_until_outer_completion(self):
        with self.activity.operation('Loading'):
            self.assertTrue(self.activity.state['busy'])
            with self.activity.operation('Calculating'):
                self.assertEqual(self.activity.state['message'], 'Calculating')
            self.assertEqual(self.activity.state, {'busy':True, 'message':'Loading'})
        self.assertEqual(self.activity.state, {'busy':False, 'message':''})

    def test_exceptions_always_clear_activity(self):
        with self.assertRaisesRegex(ValueError, 'Synthetic failure'):
            with self.activity.operation('Loading'):
                with self.activity.operation('Parsing'):
                    raise ValueError('Synthetic failure')
        self.assertFalse(self.activity.state['busy'])
        self.assertEqual(self.activity._operations, [])

    def test_decorator_preserves_return_and_supports_headless_callers(self):
        class Worker:
            @busy('Working')
            def execute(self, value):
                if hasattr(self, 'activity'):
                    self.seen = self.activity.state['busy']
                return value
        worker = Worker()
        self.assertEqual(worker.execute(5), 5)
        worker.activity = self.activity
        self.assertEqual(worker.execute(7), 7)
        self.assertTrue(worker.seen)
        self.assertFalse(self.activity.state['busy'])
        worker._paused = True
        worker.execute(9)
        self.assertFalse(worker.seen)

    def test_width_never_measures_or_observes_loaded_content(self):
        script = ContentWidth._esm
        self.assertNotIn('MutationObserver', script)
        self.assertNotIn('getBoundingClientRect', script)
        self.assertNotIn('cloneNode', script)
        self.assertIn('localStorage', script)
        self.assertIn('Page width', script)
        self.assertIn('min-width:max-content', ContentWidth._css)
        self.assertIn('white-space:nowrap', ContentWidth._css)

    def test_overlay_restores_input_state_without_toggling_scrollbars(self):
        self.assertIn('host.inert=true', BusyOverlay._esm)
        self.assertIn('host.inert=priorInert', BusyOverlay._esm)
        self.assertIn('preventScroll:true', BusyOverlay._esm)
        self.assertNotIn('body.style.overflow', BusyOverlay._esm)
        source = (Path(__file__).resolve().parents[1] / 'workbench_app.py').read_text()
        self.assertIn('scrollbar-gutter: stable', source)

    def test_outer_tab_rules_outrank_widget_defaults(self):
        # ipywidgets uses four-class selectors for a fixed flex basis and label
        # clipping. Our previous three-class selectors lost regardless of order.
        css = ContentWidth._css
        for prefix in ('p', 'lm'):
            root = f'.tw-page-tabs.jupyter-widgets.jupyter-widget-tab > .{prefix}-TabBar'
            for element in ('tab', 'tabLabel'):
                selector = f'{root} .{prefix}-TabBar-{element}'
                self.assertIn(selector, css)
                self.assertGreater(selector.count('.'), 4)
                rule = css.split(selector, 1)[1].split('{', 1)[1].split('}', 1)[0]
                self.assertIn('flex:0 0 auto', rule)
                if element == 'tab':
                    self.assertIn('min-width:max-content', rule)


if __name__ == '__main__':
    unittest.main()
