"""Synthetic-only calculation parity, figure and viewer-integration checks."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from selection_fixture import make_fixture
from tensile_properties import specimen_properties, specimen_calculation
from tensile_inspector import inspection_figure, inspection_ranges, inspection_summary
from tensile_workbench import TensileWorkbench


def bilinear_record():
    x = np.linspace(0, 8, 1601)
    y = np.where(x <= .4, 7 + 1000 * x, 407 + 20 * (x - .4))
    x, y = np.r_[x, 9, 10], np.r_[y, 520, 100]
    return {'sample': 'coupon', 'source_file': 'synthetic/coupon.csv',
            'strain_pct': x, 'stress_mpa': y}


def payload(record=None):
    return {'group': 'Synthetic', 'sample': 'coupon', 'included': True,
            'source_file': 'synthetic/coupon.csv', 'exclusion_reason': '',
            'calculation': specimen_calculation(record or bilinear_record()),
            'reference': {'status': 'Unavailable', 'values': {}, 'source': '', 'notes': ''}}


class CalculationTests(unittest.TestCase):
    def test_analytical_offset_yield_and_all_markers(self):
        record = bilinear_record()
        calculation = specimen_calculation(record)
        p = calculation['properties']
        self.assertEqual(p, specimen_properties(record))
        self.assertAlmostEqual(p['Fitted E (GPa)'], 100.)
        self.assertAlmostEqual(p['Elastic intercept (MPa)'], 7.)
        self.assertAlmostEqual(p['Elastic fit R2'], 1.)
        expected_strain = 592 / 98000 * 100
        expected_stress = 399 + 20 * expected_strain
        self.assertAlmostEqual(p['Yield strain (%)'], expected_strain)
        self.assertAlmostEqual(p['Yield (MPa)'], expected_stress)
        self.assertEqual(p['UTS (MPa)'], 559.)
        self.assertEqual(p['Uniform elongation (%)'], 8.)
        self.assertEqual(p['Failure elongation (%)'], 10.)
        mask = calculation['elastic_mask']
        self.assertTrue(np.all(calculation['stress_mpa'][mask] >= .2 * 559))
        self.assertTrue(np.all(calculation['stress_mpa'][mask] <= .5 * 559))
        i, j = calculation['yield_bracket']
        self.assertLessEqual(calculation['strain_pct'][i], expected_strain)
        self.assertGreaterEqual(calculation['strain_pct'][j], expected_strain)

    def test_figures_use_exact_diagnostics_and_reference_not_inferred_strain(self):
        data = payload()
        data['reference']['values']['ys'] = 418.5
        calc = data['calculation']
        fig = inspection_figure(data)
        traces = {trace.name: trace for trace in fig.data}
        np.testing.assert_array_equal(traces['Measured curve (prepared)'].x, calc['strain_pct'])
        np.testing.assert_array_equal(traces['Elastic-fit points'].y, calc['stress_mpa'][calc['elastic_mask']])
        self.assertEqual(traces['Instron YS (stress only)'].mode, 'lines')
        self.assertEqual(tuple(traces['Instron YS (stress only)'].y), (418.5, 418.5))
        elastic = traces['Elastic fit']
        offset = traces['0.2% offset line']
        np.testing.assert_allclose(np.asarray(offset.x) - elastic.x, .2)
        np.testing.assert_allclose(offset.y, elastic.y)
        self.assertEqual(traces['Terminal point / failure EL'].x[0], 10)
        self.assertLess(inspection_ranges(calc, 'yield')[0][1], inspection_ranges(calc, 'full')[0][1])
        self.assertIn('418.500', inspection_summary(data))

    def test_unresolved_crossing_retains_fit_and_other_properties(self):
        record = bilinear_record()
        record['stress_mpa'] = record['strain_pct'] * 1000
        data = payload(record)
        p = data['calculation']['properties']
        self.assertEqual(p['Yield status'], 'unresolved')
        self.assertTrue(np.isfinite(p['Fitted E (GPa)']))
        self.assertTrue(np.isfinite(p['UTS (MPa)']))
        names = {trace.name for trace in inspection_figure(data).data}
        self.assertNotIn('Calculated 0.2% YS', names)
        self.assertIn('Elastic fit', names)
        self.assertIn('no valid 0.2% offset yield crossing', inspection_summary(data))

    def test_sparse_empty_and_unresolved_elastic_region(self):
        for n in (0, 3, 19):
            record = bilinear_record()
            record['strain_pct'], record['stress_mpa'] = np.arange(n), np.arange(n)
            data = payload(record)
            self.assertEqual(data['calculation']['properties']['Yield status'], 'unresolved')
            names = {trace.name for trace in inspection_figure(data).data}
            self.assertNotIn('Calculated 0.2% YS', names)
            self.assertNotIn('Elastic fit', names)
            self.assertNotIn('Instron YS (stress only)', names)

    def test_fractions_duplicate_strain_and_nan_preparation_are_shared(self):
        record = bilinear_record()
        record['strain_pct'] = np.r_[record['strain_pct'], .2, np.nan]
        record['stress_mpa'] = np.r_[record['stress_mpa'], 1, 12]
        original_x = record['strain_pct'].copy()
        for fractions in ((.2, .5), (.1, .4), (.3, .6)):
            actual = specimen_calculation(record, fractions)['properties']
            self.assertEqual(actual, specimen_properties(record, fractions))
        calculation = specimen_calculation(record)
        self.assertEqual(calculation['stress_mpa'][calculation['strain_pct'] == .2].item(), 207.)
        np.testing.assert_array_equal(record['strain_pct'], original_x)
        for fractions in ((0, .5), (.5, .5), (.5, 1)):
            with self.assertRaises(ValueError):
                specimen_calculation(record, fractions)

    def test_html_values_are_escaped_and_missing_reference_stays_missing(self):
        data = payload()
        data['sample'] = '<script>bad()</script>'
        data['source_file'] = '<img src=x onerror=bad>'
        data['reference']['notes'] = '<svg onload=bad>'
        html = inspection_summary(data)
        self.assertNotIn('<script>', html)
        self.assertNotIn('<img ', html)
        self.assertNotIn('<svg ', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('—', html)


class InspectorIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        make_fixture(self.root)
        with redirect_stdout(io.StringIO()):
            self.app = TensileWorkbench(self.root)
        self.inspector = self.app.tables.inspector
        self.addCleanup(self.inspector.clear)

    def inspect_event(self, ident='Alloy A/coupon_1.csv', context=None):
        widget = self.app.tables.specimens
        widget._receive(widget, {'type': 'inspect', 'context': context or widget.context, 'id': ident}, [])

    def test_lazy_read_only_inspection_and_navigation(self):
        self.assertIsNone(self.inspector.chart)
        before = self.app.store.path.read_bytes()
        initial = deepcopy(self.app.store.data)
        with patch.object(self.app.session, 'render', side_effect=AssertionError('publication plot generated')):
            self.inspect_event()
            self.assertEqual(self.app.tables.tabs.selected_index, 4)
            self.assertIsNotNone(self.inspector.chart)
            self.assertIn('Read-only', self.inspector.status.value)
            self.inspector.view.value = 'full'
            self.assertGreater(self.inspector.chart.layout.xaxis.range[1], 17)
            self.inspector._step(1)
            self.assertEqual(self.inspector.choice.value, 'Alloy A/coupon_2.csv')
            self.inspector._step(-1)
            self.assertEqual(self.inspector.choice.value, 'Alloy A/coupon_1.csv')
        self.assertEqual(self.app.store.path.read_bytes(), before)
        self.assertEqual(self.app.store.data, initial)
        self.assertFalse((self.root / 'output').exists())

    def test_excluded_specimens_inspect_without_affecting_counts(self):
        self.app._specimen_changed('Alloy A/coupon_2.csv', False, 'Synthetic review')
        before = self.app.store.path.read_bytes()
        self.inspect_event('Alloy A/coupon_2.csv')
        self.assertFalse(self.inspector._payload['included'])
        self.assertIn('Synthetic review', self.inspector.summary.value)
        self.assertIn('Excluded from this graph', self.inspector.summary.value)
        self.assertEqual(self.app.store.path.read_bytes(), before)

    def test_stale_invalid_and_out_of_graph_ids_cannot_load(self):
        old = self.app.tables.specimens.context
        self.app.graph.value = '1'
        self.inspect_event(context=old)
        self.inspect_event('/absolute/coupon.csv')
        self.assertIsNone(self.inspector.chart)
        with self.assertRaises(ValueError):
            self.app.session.specimen_inspection({'groups': []}, {}, 'Alloy A/coupon_1.csv')

    def test_filter_order_and_graph_switch_clear_old_selection(self):
        self.app.tables.sort.value = 'Sample'
        self.app.tables.descending.value = True
        self.inspector._step(1)
        self.assertEqual(self.inspector.choice.value, 'Alloy A/coupon_3.csv')
        self.app.tables.filter.value = 'coupon_2'
        self.assertIsNone(self.inspector.chart)
        self.assertEqual(len(self.inspector.choice.options), 2)
        self.inspect_event('Alloy A/coupon_2.csv')
        self.app.graph.value = '1'
        self.assertIsNone(self.inspector.chart)
        self.assertEqual(self.inspector.choice.value, '')

    def test_saved_fit_settings_match_tables_and_wh_changes_do_not_change_inspection(self):
        spec = self.app._current()['definition']
        spec['landmark_yield_fit_fractions'] = [.1, .4]
        self.app._refresh_properties()
        self.inspect_event()
        p = self.inspector._payload['calculation']['properties']
        row = self.app.tables.frames['tensile_samples'].iloc[0]
        self.assertEqual(p['Yield (MPa)'], row['0.2% Offset Yield Strength (MPa)'])
        self.assertEqual(self.inspector._payload['calculation']['fit_fractions'], (.1, .4))
        state = {**self.app.state(), 'modulus_gpa': 25, 'despike': True, 'median': True, 'smooth': False}
        changed = self.app.session.specimen_inspection(state, spec, 'Alloy A/coupon_1.csv')
        self.assertEqual(changed['calculation']['properties'], p)


if __name__ == '__main__':
    unittest.main()
