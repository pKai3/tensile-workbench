"""Presentation-only inspector checks on temporary synthetic specimens."""
from contextlib import redirect_stdout
from copy import deepcopy
from html import escape
from html.parser import HTMLParser
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from selection_fixture import make_fixture
from tensile_inspector import inspection_checks, inspection_summary
from tensile_tables import specimen_check_failures
from tensile_workbench import TensileWorkbench


class DetailParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.depth, self.minimum, self.style = 0, 0, False
        self.open_sections, self.outside = [], []

    def handle_starttag(self, tag, attrs):
        if tag == 'details':
            self.depth += 1
            if 'open' in dict(attrs):
                self.open_sections.append(attrs)
        if tag == 'style':
            self.style = True

    def handle_endtag(self, tag):
        if tag == 'details':
            self.depth -= 1
            self.minimum = min(self.minimum, self.depth)
        if tag == 'style':
            self.style = False

    def handle_data(self, data):
        if data.strip() and not self.depth and not self.style:
            self.outside.append(data)


class InspectorLayoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='inspector-layout-synthetic-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        make_fixture(self.root)
        with redirect_stdout(io.StringIO()):
            self.app = TensileWorkbench(self.root)
        self.inspector = self.app.tables.inspector
        self.addCleanup(self.inspector.clear)
        self.inspector.select('Alloy A/coupon_1.csv')
        self.payload = deepcopy(self.inspector._payload)

    def test_editors_below_checks_above_plot_and_outside_details_fold(self):
        children = list(self.inspector.ui.children)
        start = children.index(self.inspector.checks)
        self.assertEqual(children[start:start + 4], [self.inspector.checks, self.inspector.editor,
                                                   self.inspector.failure_editor, self.inspector.chart_box])
        self.assertIs(children[children.index(self.inspector.chart_box) + 1], self.inspector.layers_panel)
        self.assertEqual(self.inspector.layers_panel.layout.display, '')
        self.assertIs(children[-1], self.inspector.details_panel)
        self.assertIsNone(self.inspector.details_panel.selected_index)
        nested = self.inspector.details_panel.children[0].children
        self.assertNotIn(self.inspector.layers_panel, nested)
        for child in (self.inspector.editor, self.inspector.failure_editor):
            self.assertNotIn(child, nested)
            self.assertIn(child, children)
            self.assertIsNone(child.selected_index)
        self.assertIn(self.inspector.summary, nested)
        self.assertNotIn(self.inspector.summary, children)

    def test_check_text_matches_table_and_updates_without_stale_messages(self):
        data = self.payload
        data['reference']['check_failures'] = ['Synthetic identity mismatch <review>']
        expected = specimen_check_failures(data['calculation']['properties'], data['reference'])
        self.inspector._paint(data)
        self.assertIn(escape(expected), self.inspector.checks.value)
        self.assertNotIn('Synthetic identity mismatch', self.inspector.summary.value)
        self.assertEqual(self.inspector.checks.layout.display, '')
        self.inspector._step(1)
        self.assertNotIn('Synthetic identity mismatch', self.inspector.checks.value)
        self.inspector.clear()
        self.assertEqual(self.inspector.checks.value, '')
        self.assertEqual(self.inspector.checks.layout.display, 'none')

    def test_clean_checks_hidden_and_preview_label_is_explicit(self):
        data = self.payload
        data['reference']['check_failures'] = []
        data['gauge_policy'] = {'enabled': False}
        p = data['calculation']['properties']
        p.update({'Fit review required': False, 'Fracture detection status': 'Detected',
                  'Fracture review required': False})
        self.assertEqual(inspection_checks(data), '')
        self.inspector._paint(data)
        self.assertEqual(self.inspector.checks.layout.display, 'none')
        p.update({'Fit review required': True, 'Elastic fit R2': .8, 'R2 warning threshold': .98})
        html = inspection_checks(data, preview=True)
        self.assertIn('unsaved preview', html)
        self.assertIn('0.80000 below threshold 0.98000', html)
        data['gauge_policy']['enabled'] = True
        data['gauge_preview']['_gauge'].update({'Elongation basis': 'Estimated standard gauge',
                                               'Gauge correction status': 'Missing dots'})
        self.assertIn('Gauge reconstruction: Missing dots', inspection_checks(data))

    def test_report_sections_closed_balanced_and_no_unfolded_prose(self):
        self.payload['reference']['check_values'] = {'Original CSV UTS': 800.}
        html = inspection_summary(self.payload)
        parser = DetailParser()
        parser.feed(html)
        self.assertEqual(parser.depth, 0)
        self.assertEqual(parser.minimum, 0)
        self.assertFalse(parser.open_sections)
        self.assertFalse(parser.outside)
        for heading in ('Specimen identity and inclusion', 'Calculated and Instron properties',
                        'Elongation sources and endpoint selection', 'Gauge reconstruction',
                        'Elastic fit and calculation details', 'Source and preparation details'):
            self.assertIn('<summary>' + heading + '</summary>', html)

    def test_folding_never_changes_saved_data_or_reruns_calculations(self):
        before = self.app.store.path.read_bytes()
        with patch('tensile_inspector.specimen_calculation', side_effect=AssertionError('recalculated')):
            self.inspector.editor.selected_index = 0
            self.inspector.failure_editor.selected_index = 0
            self.assertIsNone(self.inspector.details_panel.selected_index)
            self.inspector.details_panel.selected_index = 0
            self.inspector.details_panel.selected_index = None
            self.assertEqual(self.inspector.editor.selected_index, 0)
            self.assertEqual(self.inspector.failure_editor.selected_index, 0)
            self.assertEqual(self.inspector.layers_panel.layout.display, '')
        self.assertEqual(self.app.store.path.read_bytes(), before)
        self.assertFalse((self.root / 'output').exists())

    def test_visible_legend_toggles_chart_with_details_closed_without_recalculation(self):
        before = self.app.store.path.read_bytes()
        checkbox = next(widget for widget in self.inspector._layer_widgets
                        if isinstance(widget, self.app.w.Checkbox) and not widget.disabled)
        trace = next(trace for trace in self.inspector.chart.data if trace.name == checkbox.description)
        original = checkbox.value
        self.assertIsNone(self.inspector.details_panel.selected_index)
        with patch('tensile_inspector.specimen_calculation', side_effect=AssertionError('recalculated')):
            checkbox.value = not original
            self.assertEqual(trace.visible, not original)
            checkbox.value = original
            self.assertEqual(trace.visible, original)
        self.assertEqual(self.inspector.layers_panel.layout.display, '')
        self.assertEqual(self.app.store.path.read_bytes(), before)
        self.inspector.clear()
        self.assertEqual(self.inspector.layers_panel.layout.display, 'none')


if __name__ == '__main__':
    unittest.main()
