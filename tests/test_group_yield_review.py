"""Synthetic-only parity and lifecycle checks for the group fit overview."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

import ipywidgets as w
import numpy as np

from selection_fixture import make_fixture
from test_specimen_inspector import bilinear_record
from tensile_inspector import inspection_figure
from tensile_properties import specimen_calculation
from tensile_workbench import TensileWorkbench
from tensile_yield_review import FIT_LAYERS, GroupYieldReview, yield_fit_figure


class YieldFigureTests(unittest.TestCase):
    def test_current_fit_traces_and_r_squared_match_inspector_including_manual_fit(self):
        for manual in (False, True):
            with self.subTest(manual=manual):
                record = bilinear_record()
                record['_review_reference'] = {'values': {'ys': 418.5}}
                record['source_sha256'] = 'a' * 64
                if manual:
                    record['_fit_override'] = {'mode': 'line', 'strain_bounds': [.1, .3],
                        'endpoints': [[.1, 109.], [.3, 313.]], 'source_sha256': 'a' * 64}
                calc = specimen_calculation(record)
                before = deepcopy(calc['properties'])
                reference = inspection_figure({'record': record, 'calculation': calc,
                                               'reference': record['_review_reference']})
                grid = yield_fit_figure(record, calc)
                full_traces = {t.meta['inspector_layer']: t for t in reference.data}
                self.assertEqual({t.meta['inspector_layer'] for t in grid.data}, FIT_LAYERS)
                for trace in grid.data:
                    if trace.meta['inspector_layer'] != 'measured':
                        np.testing.assert_array_equal(trace.x, full_traces[trace.meta['inspector_layer']].x)
                        np.testing.assert_array_equal(trace.y, full_traces[trace.meta['inspector_layer']].y)
                self.assertIn(f"R² = {before['Elastic fit R2']:.5f}", grid.layout.annotations[-1].text)
                self.assertEqual(calc['properties']['Fitted E (GPa)'], before['Fitted E (GPa)'])
                self.assertEqual(calc['properties']['Fit method'], 'Manual line' if manual else 'Automatic')
                self.assertEqual([s.name for s in grid.layout.shapes], ['inspector:fit_points'])
                instron = next(t for t in grid.data if t.meta['inspector_layer'] == 'yield_instron')
                self.assertEqual(instron.marker.symbol, 'diamond-open')
                self.assertEqual(tuple(instron.y), (418.5,))

    def test_instron_marker_outside_calc_detail_range_remains_visible_and_missing_is_not_invented(self):
        record = bilinear_record()
        record['_review_reference'] = {'values': {'ys': 500.}}
        calc = specimen_calculation(record)
        grid = yield_fit_figure(record, calc)
        instron = next(t for t in grid.data if t.meta['inspector_layer'] == 'yield_instron')
        self.assertGreater(grid.layout.xaxis.range[1], instron.x[0])
        self.assertNotIn('instron_ys_level', {t.meta['inspector_layer'] for t in grid.data})
        record['_review_reference'] = {'values': {}, 'candidate_values': {'ys': 500.}}
        grid = yield_fit_figure(record, calc)
        self.assertNotIn('yield_instron', {t.meta['inspector_layer'] for t in grid.data})

    def test_measured_crop_preserves_acquisition_reversals_and_missing_readings(self):
        record = bilinear_record()
        calc = specimen_calculation(record)
        record['_acquisition'] = {
            'strain': np.array([0., .1, .2, 8., 9., 10., .2, .15, np.nan, .3, .4, 11.]),
            'stress': np.arange(12, dtype=float) * 10.,
        }
        before = record['_acquisition']['strain'].copy()
        figure = yield_fit_figure(record, calc, crop_range=[0., .5])
        trace = next(t for t in figure.data if t.meta['inspector_layer'] == 'measured')
        np.testing.assert_array_equal(trace.x, [0., .1, .2, 8., np.nan, 10., .2, .15, np.nan, .3, .4, 11.])
        self.assertFalse(trace.connectgaps)
        np.testing.assert_array_equal(record['_acquisition']['strain'], before)

    def test_missing_fit_is_not_labelled_with_zero_r_squared(self):
        x = np.linspace(0, 3, 100)
        record = {'sample': 'curved', 'source_file': 'synthetic.csv',
                  'strain_pct': x, 'stress_mpa': 500 * (1 - np.exp(-x))}
        calc = specimen_calculation(record)
        figure = yield_fit_figure(record, calc)
        self.assertIn('R² unavailable', figure.layout.annotations[-1].text)
        self.assertIn('Review fit', figure.layout.annotations[-1].text)
        self.assertNotIn('elastic_fit', {t.meta['inspector_layer'] for t in figure.data})


class YieldReviewTests(unittest.TestCase):
    def test_lazy_natural_order_exclusions_axes_and_disposal(self):
        records, rows = [], []
        for index in (10, 2, 1):
            record = bilinear_record()
            record.update(specimen_id=f'Group/coupon_{index}.csv', sample=f'Operator_{index}',
                          _review_fit_fractions=(.15, .4))
            record['stress_mpa'] *= 1 + index / 100
            records.append(record)
            rows.append({'id': record['specimen_id'], 'group': 'Group', 'sample': record['sample'],
                         'included': index != 2, 'mode': 'exclude' if index == 2 else 'all'})
        loader, inspect = Mock(return_value=records), Mock()
        review = GroupYieldReview(w, loader, inspect)
        self.addCleanup(review.clear)
        review.set_rows(rows)
        loader.assert_not_called()
        self.assertFalse(review.entries)
        review.set_active(True)
        self.assertEqual(loader.call_count, 1)
        self.assertEqual([e['id'] for e in review.entries], ['Group/coupon_1.csv', 'Group/coupon_2.csv', 'Group/coupon_10.csv'])
        self.assertIn('Exclude specimen entirely', review.grid.children[1].children[0].value)
        self.assertTrue(all(e['calculation']['fit_fractions'] == (.15, .4) for e in review.entries))
        charts = [e['figure'] for e in review.entries]
        self.assertEqual(charts[0].layout.yaxis.range, charts[1].layout.yaxis.range)
        review.shared_axes.value = False
        self.assertNotEqual(charts[0].layout.yaxis.range, charts[1].layout.yaxis.range)
        review._resize(650)
        self.assertEqual(review.grid.layout.grid_template_columns, 'repeat(1, minmax(0, 1fr))')
        self.assertLessEqual(charts[0].layout.width, 650)
        self.assertEqual(loader.call_count, 1)  # display changes never refit/reload
        stale_button = review.grid.children[0].children[-1]
        stale_button.click()
        inspect.assert_called_once_with('Group/coupon_1.csv')
        review.show_excluded.value = False
        self.assertEqual(len(review.entries), 2)
        self.assertNotIn('Group/coupon_2.csv', [e['id'] for e in review.entries])
        stale_button.click()
        self.assertEqual(inspect.call_count, 1)
        review.clear()
        self.assertFalse(review.entries)
        self.assertFalse(review.grid.children)

    def test_workbench_tab_opens_matching_inspector_without_writing_state(self):
        with tempfile.TemporaryDirectory(prefix='yield-grid-synthetic-') as directory:
            root = Path(directory)
            make_fixture(root)
            with redirect_stdout(io.StringIO()):
                app = TensileWorkbench(root)
                before = (root / 'tensile_workbench.project.json').read_bytes()
                self.addCleanup(app.tables.clear)
                view = app.tables.yield_review
                self.assertFalse(view.entries)
                self.assertEqual(app.tables.tabs.get_title(3), 'Group yield fits')
                self.assertEqual(app.tables.tabs.get_title(4), 'Calculation inspector')
                app.tables.tabs.selected_index = 3
                self.assertEqual(len(view.entries), 3)
                entry = view.entries[1]
                expected = app._inspect_specimen(entry['id'])['calculation']['properties']
                self.assertEqual(entry['calculation']['properties']['Elastic fit R2'], expected['Elastic fit R2'])
                self.assertEqual(entry['calculation']['properties']['Fitted E (GPa)'], expected['Fitted E (GPa)'])
                view.grid.children[1].children[-1].click()
                self.assertEqual(app.tables.tabs.selected_index, 4)
                self.assertEqual(app.tables.inspector.choice.value, entry['id'])
                self.assertFalse(view.active)
                self.assertEqual(before, (root / 'tensile_workbench.project.json').read_bytes())


if __name__ == '__main__':
    unittest.main()
