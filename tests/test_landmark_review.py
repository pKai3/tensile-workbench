"""Synthetic-only checks for aligned contributions and property-only specimens."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import ipywidgets as w
import numpy as np

from selection_fixture import make_fixture
from tensile_comparison import relative_comparison
from tensile_group_review import GroupCurveReview
from tensile_selection import DATA_MODES, curve_allowed, property_allowed
from tensile_tables import specimen_table_data, specimen_export_frame
from tensile_workbench import PreviewSession, TensileWorkbench
from workbench_project import validate_project


class LandmarkReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='landmark-review-synthetic-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = make_fixture(self.root)
        self.session = PreviewSession(self.root, self.project)
        self.state = self.session.defaults()
        self.state['landmark_points'] = 47

    @property
    def spec(self):
        return self.session.graphs[0]

    def mode(self, mode, number=2):
        self.project.setdefault('specimen_data_modes', {})[f'Alloy A/coupon_{number}.csv'] = {
            'mode': mode, 'reason': 'Synthetic shape review'}
        self.session.set_project(self.project)

    def payload(self):
        return self.session.group_review_landmark('Alloy A', self.state, self.spec)

    def frames(self):
        with redirect_stdout(io.StringIO()):
            return self.session.property_tables(self.state, self.spec)

    def review(self):
        frames = self.frames()
        _, _, rows = specimen_table_data(frames['tensile_samples'], frames['instron_comparison'])
        loader = Mock(side_effect=lambda group: self.session.group_review_landmark(group, self.state, self.spec))
        view = GroupCurveReview(w,
            loader=lambda group: self.session.group_review_records(group, self.spec), aligned_loader=loader)
        self.addCleanup(view.clear)
        view.set_rows(rows)
        return view, loader

    def assert_mean_matches(self, model):
        components = model['contributions']
        x = components[0]['x']
        finite = np.isfinite(x)
        y = np.mean([c['y'] for c in components], axis=0)
        np.testing.assert_allclose(y[finite], np.interp(x[finite], model['x'], model['y']), atol=1e-10)
        self.assertEqual(np.count_nonzero(~finite), 2)
        self.assertEqual(len(x), 3 * self.state['landmark_points'] + 2)
        self.assertEqual([c['specimen_id'] for c in components], model['shape_specimens'])

    def test_contributions_reproduce_unchanged_publication_mean_for_every_mode(self):
        for mode in DATA_MODES:
            with self.subTest(mode=mode):
                self.mode(mode)
                model = self.payload()['model']
                with redirect_stdout(io.StringIO()):
                    records = self.session.analysis_records(self.state, self.spec)
                    regular = self.session.engine.prepare_average_curves(self.spec, records,
                        landmark_points_per_stage=self.state['landmark_points'])[0]['Alloy A']['landmark']
                np.testing.assert_array_equal(model['x'], regular['x'])
                np.testing.assert_array_equal(model['y'], regular['y'])
                self.assertNotIn('contributions', regular)
                self.assertEqual(model['shape_n'], 3 if mode == 'all' else 2)
                self.assertEqual(model['property_counts']['UTS (MPa)'], 2 if mode == 'exclude' else 3)
                self.assertEqual(model['property_counts']['Failure elongation (%)'],
                                 3 if mode in ('all', 'exclude_shape') else 2)
                self.assert_mean_matches(model)
        self.assertFalse((self.root / 'output').exists())

    def test_shared_transform_does_not_force_every_specimen_through_mean_stresses(self):
        model = self.payload()['model']
        yield_index = self.state['landmark_points'] - 1
        values = [c['y'][yield_index] for c in model['contributions']]
        self.assertGreater(np.ptp(values), 1.)
        self.assertAlmostEqual(np.mean(values), model['mean_yield'])

    def test_lazy_selected_group_only_no_pointwise_work_and_cached(self):
        self.state['groups'].append('Unrelated group')
        with patch.object(self.session, '_load', wraps=self.session._load) as load, \
             patch.object(self.session.engine, 'build_tensile_mean_tail', side_effect=AssertionError('pointwise work')), \
             patch.object(self.session.engine, 'average_group_curves', side_effect=AssertionError('pointwise work')):
            first = self.payload()
            second = self.payload()
        self.assertIs(first['model'], second['model'])
        self.assertTrue(load.called)
        self.assertTrue(all(call.args == ('Alloy A',) for call in load.call_args_list))
        with self.assertRaisesRegex(ValueError, 'not selected'):
            self.session.group_review_landmark('Missing', self.state, self.spec)

    def test_review_switch_markers_zoom_and_properties_only_entry(self):
        self.mode('exclude_shape')
        view, loader = self.review()
        self.assertIsNone(view.figure)
        view.set_active(True)
        loader.assert_not_called()
        view.axis.value = 'time'
        view.markers['YS'].value = True
        project = deepcopy(self.session.project)
        view.view.value = 'aligned'
        loader.assert_called_once()
        self.assertTrue(view.axis.disabled)
        self.assertEqual(sum(t.meta['kind'] == 'curve' for t in view.figure.data), 2)
        self.assertEqual(sum(t.meta['kind'] == 'mean_marker' for t in view.figure.data), 3)
        mean = next(t for t in view.figure.data if t.meta['kind'] == 'mean')
        np.testing.assert_array_equal(mean.y, self.payload()['model']['y'])
        button = view._legend_buttons['Alloy A/coupon_2.csv']
        self.assertIn('Shape excluded', button.description)
        self.assertIn('Properties only', button.description)
        button.click()
        self.assertEqual(view.selected, 'Alloy A/coupon_2.csv')
        self.assertEqual(mean.line.width, 4)
        view.figure.update_layout(xaxis_range=[1., 12.])
        view.markers['EL'].value = False
        self.assertEqual(tuple(view.figure.layout.xaxis.range), (1., 12.))
        self.assertTrue(any(t is mean for t in view.figure.data))
        loader.assert_called_once()
        view.view.value = 'measured'
        self.assertFalse(view.axis.disabled)
        self.assertEqual(view.axis.value, 'time')
        self.assertTrue(view.markers['YS'].value)
        self.assertFalse(view.markers['EL'].value)
        self.assertEqual(sum(t.meta['kind'] == 'curve' for t in view.figure.data), 3)
        self.assertEqual(self.session.project, project)

    def test_unresolved_shape_reported_without_silently_dropping_specimens(self):
        view, _ = self.review()
        view.set_active(True)
        with patch.object(self.session.engine, 'landmark_specimen', side_effect=ValueError('Synthetic unresolved fit')):
            view.view.value = 'aligned'
        self.assertIsNone(view.figure)
        self.assertIn('unresolved specimens', view.notice.value)
        self.assertEqual(len(view._legend_buttons), 3)
        view.view.value = 'measured'
        self.assertEqual(len(view.figure.data), 3)

    def test_shape_exclusion_retains_properties_pairs_comparisons_and_exports(self):
        baseline = self.frames()
        self.mode('exclude_shape')
        validate_project(self.project)
        frames = self.frames()
        for field in ('ys', 'uts', 'uniform', 'el', 'Toughness (MJ/m^3)', 'e'):
            self.assertTrue(property_allowed('exclude_shape', field))
        for prepeak in (False, True):
            self.assertFalse(curve_allowed({'_data_mode': 'exclude_shape'}, prepeak=prepeak))
        for field in ('0.2% Offset Yield Strength (MPa)', 'UTS (MPa)', 'Uniform Elongation (%)',
                      'Failure Elongation (%)', 'Toughness (MJ/m^3)'):
            np.testing.assert_allclose(frames['tensile_samples'][field], baseline['tensile_samples'][field])
        self.assertTrue((frames['tensile_summary_details'].query("Source in ['Calculated', 'Calc']")['n'] == 3).all())
        self.assertEqual(self.session.scatter_omission_warning(self.state, self.spec), '')
        exported = specimen_export_frame(frames['tensile_samples'], frames['instron_comparison'])
        self.assertEqual(exported.iloc[1]['Data use'], 'Exclude from shape')
        self.assertEqual(exported.iloc[1]['Excluded properties'], '')
        comparison_frames = deepcopy(frames)
        comparison_frames['tensile_samples']['Instron summary EL (%)'] = [17., 18., 19.]
        comparison = relative_comparison(comparison_frames).set_index('Property')
        self.assertEqual(comparison.loc['Failure elongation', 'Paired n'], 3)
        with redirect_stdout(io.StringIO()):
            records = self.session.analysis_records(self.state, self.spec, measured=True)
            wh = self.session.engine.prepare_average_curves(self.spec, records, prepeak_only=True)[0]['Alloy A']['landmark']
        self.assertEqual(wh['shape_n'], 2)
        self.assertEqual(wh['property_counts']['Uniform elongation (%)'], 3)
        self.assertEqual(wh['property_counts']['Yield (MPa)'], 3)

    def test_reconstruction_still_applies_to_shape_excluded_specimens(self):
        self.mode('exclude_shape')
        raw = self.payload()['model']
        self.project['graphs'][0]['definition']['gauge_reconstruction'] = {
            'Alloy A': {'enabled': True, 'target_gauge_mm': 20.}}
        self.session.set_project(self.project)
        match = self.session.instron.match
        def dimensions(group, record):
            ref = match(group, record)
            return {**ref, 'values': {**ref['values'], 'gauge': 25.}}
        with patch.object(self.session.instron, 'match', side_effect=dimensions):
            model = self.payload()['model']
            frames = self.frames()
        self.assert_mean_matches(model)
        np.testing.assert_array_equal(model['knots'][:3], raw['knots'][:3])
        self.assertGreater(model['knots'][-1], raw['knots'][-1])
        self.assertEqual(frames['tensile_samples'].iloc[1]['Gauge correction status'], 'Applied')
        self.assertTrue(np.isfinite(frames['tensile_samples'].iloc[1]['Reconstructed EL (%)']))
        details = frames['tensile_summary_details']
        self.assertEqual(details.query("Property == 'Failure elongation' and Source == 'Reconstruct'")['n'].iloc[0], 3)
        self.assertEqual(frames['tensile_summary'].iloc[0]['Estimated toughness (MJ/m^3) · n'], 3)

    def test_all_shapes_excluded_keeps_means_without_inventing_a_curve(self):
        for number in (1, 2, 3):
            self.mode('exclude_shape', number)
        self.assertIsNone(self.payload()['model'])
        self.assertIn('No eligible curve shapes', self.payload()['diagnostic'])
        self.assertTrue((self.frames()['tensile_summary_details'].query("Source in ['Calculated', 'Calc']")['n'] == 3).all())

    def test_manual_failure_override_refreshes_aligned_contributions(self):
        before = self.payload()['model']
        record = self.session._load('Alloy A')[0]
        self.project['specimen_failure_overrides'] = {record['specimen_id']: {
            'row': 1601, 'source_sha256': record['source_sha256']}}
        self.session.set_project(self.project)
        after = self.payload()['model']
        self.assertIsNot(before, after)
        self.assertLess(after['knots'][-1], before['knots'][-1])
        np.testing.assert_allclose(after['knots'][:3], before['knots'][:3])
        self.assert_mean_matches(after)

    def test_property_only_long_elongation_does_not_clip_landmark_plot(self):
        self.mode('exclude_shape', 3)
        record = self.session._load('Alloy A')[2]
        for key in ('strain_pct', 'raw_strain_pct'):
            record[key] = record[key] * 4
        record['_acquisition']['strain'] = record['_acquisition']['strain'] * 4
        record['source_sha256'] = 'synthetic-long-elongation'
        record.pop('_fracture_detection', None)
        record.pop('_property_cache', None)
        with redirect_stdout(io.StringIO()):
            result = self.session.render({**self.state, 'family': 'landmark',
                                          'tensile_xlim': None, 'tensile_ylim': None})
        model = result['export_models']['Alloy A']['landmark']
        self.assertGreater(model['knots'][-1], 19.)
        self.assertGreater(result['figure'].axes[0].get_xlim()[1], model['knots'][-1])
        self.assertEqual(model['shape_n'], 2)
        self.assertEqual(model['property_counts']['Failure elongation (%)'], 3)

    def test_app_refresh_and_global_graph_override_roundtrip(self):
        with redirect_stdout(io.StringIO()):
            app = TensileWorkbench(self.root)
            self.addCleanup(app.tables.clear)
            view = app.tables.group_review
            view.view.value = 'aligned'
            self.assertIsNone(view.figure)
            app.tables.tabs.selected_index = 3
            self.assertEqual(view._aligned_model['shape_n'], 3)
            app._specimen_changed('Alloy A/coupon_2.csv', True, 'Synthetic bend', mode='exclude_shape')
            self.assertEqual(view._aligned_model['shape_n'], 2)
            self.assertEqual(view._aligned_model['property_counts']['Failure elongation (%)'], 3)
            app.controls['landmark_points'].value = 150
            self.assertEqual(len(view._aligned_model['contributions'][0]['x']), 452)
            app.graph.value = '1'
            self.assertEqual(view._aligned_model['shape_n'], 2)
            app._specimen_changed('Alloy A/coupon_2.csv', True, '', scope='graph', mode='all')
            self.assertEqual(view._aligned_model['shape_n'], 3)
            app.graph.value = '0'
            self.assertEqual(view._aligned_model['shape_n'], 2)
        self.assertEqual(app.store.data['specimen_data_modes']['Alloy A/coupon_2.csv']['mode'], 'exclude_shape')
        self.assertFalse((self.root / 'output').exists())

    def test_flat_stage_is_shifted_consistently_or_rejected(self):
        stages = np.array([[0., 5., 10.], [10., 10., 10.], [10., 8., 6.]])
        items = [(np.arange(4), stages + delta, {}) for delta in (-1., 1.)]
        x, y, _, components = self.session.engine.average_landmark_shapes(items, [0, 2, 4, 6],
            [0, 12, 12, 7], return_contributions=True)
        finite = np.isfinite(components['x'])
        np.testing.assert_allclose(np.mean(components['y'], axis=0)[finite], np.interp(components['x'][finite], x, y))
        with self.assertRaisesRegex(ValueError, 'flat stage'):
            self.session.engine.average_landmark_shapes(items, [0, 2, 4, 6], [0, 12, 13, 7], return_contributions=True)


if __name__ == '__main__':
    unittest.main()
