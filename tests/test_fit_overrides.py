"""Synthetic-only fit policy, preview, persistence and consumer consistency tests."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from selection_fixture import make_fixture
from test_specimen_inspector import bilinear_record
from tensile_fit import validate_threshold, validate_override
from tensile_properties import specimen_calculation, specimen_properties
from tensile_workbench import TensileWorkbench
from workbench_project import validate_project, ProjectConflict

IDENT = 'Alloy A/coupon_1.csv'


class FitCalculationTests(unittest.TestCase):
    def setUp(self):
        self.record = bilinear_record()
        self.record['source_sha256'] = 'a' * 64

    def candidate(self, mode='range'):
        result = {'mode': mode, 'strain_bounds': [.1, .3], 'source_sha256': 'a' * 64}
        if mode == 'line':
            result['endpoints'] = [[.1, 87.], [.3, 247.]]  # 80 GPa, intercept 7 MPa
        return result

    def test_range_and_line_have_analytical_yield_and_unchanged_measurements(self):
        automatic = specimen_calculation(self.record)['properties']
        for mode, modulus in (('range', 100.), ('line', 80.)):
            calc = specimen_calculation(self.record, override=self.candidate(mode))
            p = calc['properties']
            self.assertEqual(p['Yield status'], 'resolved')
            self.assertAlmostEqual(p['Fitted E (GPa)'], modulus)
            expected_x = (392 + modulus * 2) / (modulus * 10 - 20)
            self.assertAlmostEqual(p['Yield strain (%)'], expected_x)
            self.assertAlmostEqual(p['Yield (MPa)'], 399 + expected_x * 20)
            self.assertEqual(p['Automatic Yield (MPa)'], automatic['Yield (MPa)'])
            for field in ('UTS (MPa)', 'Uniform elongation (%)', 'Failure elongation (%)', 'Toughness (MJ/m^3)'):
                self.assertEqual(p[field], automatic[field])
            mask = calc['elastic_mask']
            x, y = calc['strain_pct'][mask], calc['stress_mpa'][mask]
            expected_r2 = 1 - sum((y - (p['Fitted E (GPa)'] * 10 * x + 7)) ** 2) / sum((y-y.mean()) ** 2)
            self.assertAlmostEqual(p['Elastic fit R2'], expected_r2)
        self.assertNotIn('_fit_override', self.record)  # previews do not bind themselves

    def test_override_precedes_graph_fractions_and_cache_tracks_policy(self):
        automatic = specimen_properties(self.record)
        self.record['_fit_override'] = self.candidate('line')
        p = specimen_properties(self.record)
        self.assertNotEqual(automatic['Yield (MPa)'], p['Yield (MPa)'])
        other = specimen_properties(self.record, (.1, .4))
        self.assertEqual(p['Yield (MPa)'], other['Yield (MPa)'])
        self.record['_fit_r2_threshold'] = 0.
        self.assertFalse(specimen_properties(self.record)['Fit review required'])
        self.record['_fit_r2_threshold'] = 1.
        self.assertTrue(specimen_properties(self.record)['Fit review required'])

    def test_stale_fingerprint_falls_back_to_automatic_and_warns(self):
        auto = specimen_properties(self.record)
        self.record['_fit_override'] = self.candidate('line')
        self.record['_fit_override']['source_sha256'] = 'b' * 64
        p = specimen_properties(self.record)
        self.assertEqual(p['Yield (MPa)'], auto['Yield (MPa)'])
        self.assertEqual(p['Fit method'], 'Automatic')
        self.assertIn('Stale', p['Override status'])
        self.assertTrue(p['Fit review required'])

    def test_invalid_and_insufficient_regions_cannot_resolve(self):
        for bounds in ([.1, .101], [7.9, 8.], [-.1, .1], [2., 3.]):
            override = {**self.candidate(), 'strain_bounds': bounds}
            p = specimen_calculation(self.record, override=override)['properties']
            self.assertEqual(p['Yield status'], 'unresolved')
        for bounds in ([.3, .1], [float('nan'), .1]):
            with self.assertRaises(ValueError):
                validate_override({**self.candidate(), 'strain_bounds': bounds})
        with self.assertRaises(ValueError):
            validate_override({**self.candidate('line'), 'endpoints': [[.1, 300], [.3, 100]]})

    def test_manual_line_r2_is_not_clamped_and_threshold_is_finite(self):
        line = self.candidate('line')
        line['endpoints'] = [[.1, 77], [.3, 217]]
        p = specimen_calculation(self.record, override=line)['properties']
        self.assertLess(p['Elastic fit R2'], 0.)
        self.assertTrue(p['Fit review required'])
        for value in (-.01, 1.01, float('nan'), float('inf'), True, '.98'):
            with self.assertRaises(ValueError):
                validate_threshold(value)
        self.assertEqual(validate_threshold(0), 0.)
        self.assertEqual(validate_threshold(1), 1.)


class FitIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        make_fixture(self.root)
        with redirect_stdout(io.StringIO()):
            self.app = TensileWorkbench(self.root)
        self.inspector = self.app.tables.inspector
        self.addCleanup(self.inspector.clear)
        self.inspector.select(IDENT)

    def frame(self):
        return self.app.tables.frames['tensile_samples'].set_index('Specimen ID')

    def draft(self):
        # A deliberately imperfect manual line: measured E is 120 GPa.
        return {'mode': 'line', 'strain_bounds': [.12, .3], 'endpoints': [[.12, 120.], [.3, 300.]]}

    def apply(self, override=None, reason='Synthetic endpoint review'):
        self.app._apply_specimen_fit(IDENT, self.app._inspect_specimen(IDENT)['source_sha256'],
                                    self.draft() if override is None else override, reason)

    def test_preview_numeric_edits_drag_and_cancel_never_save(self):
        before = self.app.store.path.read_bytes()
        self.inspector.mode.value = 'range'
        self.inspector.x0.value = .12
        self.inspector.x1.value = .3
        self.assertIsNotNone(self.inspector._draft)
        shape = next(s for s in self.inspector.chart.layout.shapes if s.name == 'fit-range')
        shape.x0 = .14
        self.assertAlmostEqual(self.inspector.x0.value, .136)  # snapped to measured point
        self.assertTrue(self.inspector.apply_button.disabled)
        self.inspector.reason.value = 'Synthetic range review'
        self.assertFalse(self.inspector.apply_button.disabled)
        self.assertEqual(before, self.app.store.path.read_bytes())
        self.inspector._selected()
        self.assertEqual(self.inspector.mode.value, 'inspect')
        self.assertEqual(self.inspector._payload['calculation']['properties']['Fit method'], 'Automatic')
        self.assertEqual(before, self.app.store.path.read_bytes())
        self.assertFalse((self.root / 'output').exists())

    def test_manual_line_shape_changes_preview_not_saved_policy(self):
        self.inspector.mode.value = 'line'
        shape = next(s for s in self.inspector.chart.layout.shapes if s.name == 'fit-line')
        original = self.inspector._payload['calculation']['properties']['Fitted E (GPa)']
        shape.y1 += 5
        self.assertNotEqual(original, self.inspector._payload['calculation']['properties']['Fitted E (GPa)'])
        self.assertEqual(self.inspector._draft['endpoints'][1][1], self.inspector.y1.value)
        self.assertNotIn('specimen_fit_overrides', self.app.store.data)

    def test_apply_persists_across_graphs_reopen_and_restore_with_audit(self):
        before = self.frame().loc[IDENT, '0.2% Offset Yield Strength (MPa)']
        self.apply()
        saved = self.app.store.data['specimen_fit_overrides'][IDENT]
        validate_override(saved, saved=True)
        self.assertEqual(saved['endpoints'], self.draft()['endpoints'])
        self.assertEqual(saved['automatic_snapshot']['Yield (MPa)'], before)
        after = self.frame().loc[IDENT, '0.2% Offset Yield Strength (MPa)']
        self.assertNotEqual(before, after)
        self.assertEqual(self.frame().loc[IDENT, 'Fit method'], 'Manual line')
        self.assertEqual(self.frame().loc['Alloy A/coupon_2.csv', 'Fit method'], 'Automatic')
        self.app.graph.value = '1'
        self.assertEqual(self.frame().loc[IDENT, '0.2% Offset Yield Strength (MPa)'], after)
        with redirect_stdout(io.StringIO()):
            reopened = TensileWorkbench(self.root)
        self.addCleanup(reopened.tables.inspector.clear)
        self.assertEqual(reopened._inspect_specimen(IDENT)['calculation']['properties']['Yield (MPa)'], after)
        self.app._apply_specimen_fit(IDENT, saved['source_sha256'], None, '')
        self.assertEqual(self.frame().loc[IDENT, '0.2% Offset Yield Strength (MPa)'], before)
        self.assertNotIn(IDENT, self.app.store.data['specimen_fit_overrides'])
        self.assertEqual([e['action'] for e in self.app.store.data['specimen_fit_history']], ['apply', 'restore automatic'])
        validate_project(self.app.store.data)

    def test_threshold_warning_counts_review_and_no_change_to_properties(self):
        self.apply()
        self.app._specimen_changed(IDENT, False, 'Synthetic exclusion')
        p = self.frame().loc[IDENT].copy()
        self.assertIn('1 specimen needs', self.app.fit_warning.value)
        self.assertIn('0 included; 1 excluded', self.app.fit_warning.value)
        self.app._review_fits()
        self.assertEqual(self.inspector.choice.value, IDENT)
        self.assertEqual(len(self.app.tables.specimens.rows), 1)
        self.app.tables.threshold.value = 0.
        self.assertEqual(self.app.store.data['yield_r2_warning'], 0.)
        self.assertIn('no warnings', self.app.fit_warning.value)
        self.assertEqual(len(self.app.tables.specimens.rows), 0)
        q = self.frame().loc[IDENT]
        self.assertEqual(p['0.2% Offset Yield Strength (MPa)'], q['0.2% Offset Yield Strength (MPa)'])
        self.assertFalse(q['Fit review required'])
        self.app.graph.value = '1'
        self.assertEqual(self.app.tables.threshold.value, 0.)

    def test_apply_clears_cached_models_and_shared_landmark_uses_new_yield(self):
        self.app.session._models['old'] = object()
        self.app.session._previews['old'] = object()
        state, spec = self.app.state(), self.app._current()['definition']
        wh_before = deepcopy(self.app.session._wh_settings(state, spec))
        signature = self.app.session.fit_signature()
        self.apply()
        self.assertFalse(self.app.session._models)
        self.assertFalse(self.app.session._previews)
        self.assertEqual(wh_before, self.app.session._wh_settings(state, spec))
        record = self.app.session._load('Alloy A')[0]
        landmark = self.app.session.engine.landmark_specimen(record)
        # All plot consumers use the same record-bound specimen properties.
        self.assertAlmostEqual(landmark[2]['Yield (MPa)'], specimen_properties(record)['Yield (MPa)'])
        with self.assertRaisesRegex(ValueError, 'fit'):
            self.app.session.export([{'fit_signature': signature}])
        self.assertFalse((self.root / 'output').exists())

    def test_failed_saves_invalid_overrides_and_changed_source_leave_policy_untouched(self):
        self.app.save_current()
        before = self.app.store.path.read_bytes()
        for override, reason in ((self.draft(), ''), ({'mode': 'range', 'strain_bounds': [8., 9.]}, 'bad region')):
            with self.assertRaises(ValueError):
                self.apply(override, reason)
        self.assertEqual(before, self.app.store.path.read_bytes())
        with patch.object(self.app.store, 'save', side_effect=ProjectConflict('synthetic conflict')):
            with self.assertRaises(Exception):
                self.apply()
        self.assertEqual(before, self.app.store.path.read_bytes())
        self.assertEqual(self.frame().loc[IDENT, 'Fit method'], 'Automatic')
        source = self.root / 'data' / IDENT
        source.write_text(source.read_text() + '\n')
        with self.assertRaisesRegex(ValueError, 'Source data changed'):
            self.apply()
        self.assertEqual(before, self.app.store.path.read_bytes())

    def test_stale_saved_override_after_source_edit_is_flagged_on_reopen(self):
        self.apply()
        source = self.root / 'data' / IDENT
        source.write_text(source.read_text() + '\n')
        with redirect_stdout(io.StringIO()):
            reopened = TensileWorkbench(self.root)
        self.addCleanup(reopened.tables.inspector.clear)
        p = reopened._inspect_specimen(IDENT)['calculation']['properties']
        self.assertEqual(p['Fit method'], 'Automatic')
        self.assertTrue(p['Fit review required'])
        self.assertIn('Stale', p['Override status'])

    def test_table_exports_include_original_result_and_relevant_audit(self):
        self.apply()
        checks = self.app.tables.frames['specimen_diagnostics'].set_index('Specimen ID').loc[IDENT]
        self.assertIn('Synthetic endpoint review', checks['Override Reason'])
        definition = json.loads(checks['Override Definition'])
        self.assertIn('automatic_snapshot', definition)
        with redirect_stdout(io.StringIO()):
            path = self.app.session.export_properties(self.app.state(), self.app._current()['definition'])
        metadata = json.loads((path / 'settings.json').read_text())['specimen_fit_policy']
        self.assertIn(IDENT, metadata['specimen_fit_overrides'])
        self.assertEqual(len(metadata['specimen_fit_history']), 1)
        self.assertTrue((path / 'tensile_samples.xlsx').exists())

    def test_invalid_preview_cannot_apply_a_previous_valid_draft(self):
        self.inspector.mode.value = 'range'
        self.inspector.reason.value = 'Synthetic range review'
        self.assertFalse(self.inspector.apply_button.disabled)
        self.assertEqual(self.inspector._payload['calculation']['properties']['Override status'], 'Unsaved preview')
        self.inspector.x1.value = .01  # reversed range
        self.assertIsNone(self.inspector._draft)
        self.assertTrue(self.inspector.apply_button.disabled)
        self.inspector._apply()
        self.assertNotIn('specimen_fit_overrides', self.app.store.data)
        self.assertIn('Invalid preview', self.inspector.edit_status.value)

    def test_inspector_apply_restore_and_failed_threshold_save(self):
        self.inspector.mode.value = 'range'
        self.inspector.reason.value = 'Synthetic range review'
        self.inspector._apply()
        self.assertEqual(self.frame().loc[IDENT, 'Fit method'], 'Manual range')
        self.assertIn('Override saved', self.inspector.edit_status.value)
        self.inspector._apply(restore=True)
        self.assertEqual(self.frame().loc[IDENT, 'Fit method'], 'Automatic')
        self.app.save_current()
        before = self.app.store.path.read_bytes()
        with patch.object(self.app.store, 'save', side_effect=ProjectConflict('synthetic conflict')):
            self.app.tables.threshold.value = .9
        self.assertEqual(self.app.tables.threshold.value, .98)
        self.assertIn('Not saved', self.app.tables.threshold_status.value)
        self.assertEqual(before, self.app.store.path.read_bytes())


if __name__ == '__main__':
    unittest.main()
