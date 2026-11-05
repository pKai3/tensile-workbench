"""Synthetic recoil histories: phase boundaries precede strain sorting."""
from copy import deepcopy
from contextlib import redirect_stdout
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tensile_core import landmark_specimen, prepare_average_curves
from tensile_fracture import fracture_endpoint, loading_curve
from tensile_gauge import prepared_indices
from tensile_inspector import inspection_figure, inspection_ranges, instron_ys_strain
from tensile_properties import specimen_calculation
from selection_fixture import make_fixture
from tensile_workbench import PreviewSession


def recoil_record(direction='backward', *, acquisition=True):
    x = np.linspace(0., 3.8, 7601)
    y = np.where(x <= 1.1, 1100 * x, 1210 + 140 * (1 - np.exp(-(x - 1.1) / .2)))
    # A resolved, very short post-UTS section, less than the normal shape margin.
    y[-50:] = np.linspace(y[-51] - .01, y[-51] - .5, 50)
    end = len(x)
    tail_x = {'backward': np.linspace(3.8, .1, 101),
              'forward': np.linspace(3.801, 4.3, 101),
              'fixed': np.full(101, 3.8)}[direction]
    x, y = np.r_[x, tail_x], np.r_[y, np.linspace(1200., 0., 101)]
    metadata = {'strain': x, 'stress': y, 'time': np.arange(len(x)) * .02,
                'force': y.copy(), 'force_channel': 'Force', 'peak': int(np.argmax(y))}
    ids = prepared_indices(metadata)
    record = {'sample': 'Synthetic recoil', 'source_file': 'synthetic.csv', 'source_sha256': 'a' * 64,
              'strain_pct': x[ids] if acquisition else x,
              'stress_mpa': y[ids] if acquisition else y}
    if acquisition:
        record.update(_acquisition=metadata, _measurement_indices=ids)
    return record, end


class LoadingPhaseTests(unittest.TestCase):
    def test_tail_direction_cannot_change_fit_yield_or_landmark_shape(self):
        baseline = specimen_calculation(recoil_record('forward')[0])['properties']
        baseline_shape = landmark_specimen(recoil_record('forward')[0])
        for acquisition in (True, False):
            for direction in ('forward', 'backward', 'fixed'):
                with self.subTest(acquisition=acquisition, direction=direction):
                    record, end = recoil_record(direction, acquisition=acquisition)
                    before_x, before_y = record['strain_pct'].copy(), record['stress_mpa'].copy()
                    calc = specimen_calculation(record)
                    for key in ('Fitted E (GPa)', 'Yield (MPa)', 'Yield strain (%)', 'Elastic fit R2'):
                        self.assertAlmostEqual(calc['properties'][key], baseline[key], places=10)
                    self.assertAlmostEqual(calc['properties']['Fitted E (GPa)'], 110., places=7)
                    self.assertEqual(calc['properties']['Yield status'], 'resolved')
                    if acquisition:
                        self.assertTrue(np.all(calc['measurement_indices'][calc['elastic_mask']]
                                               < record['_acquisition']['peak']))
                    self.assertAlmostEqual(fracture_endpoint(record)['strain_pct'], 3.8)
                    shape = landmark_specimen(record)
                    for i in (0, 1):
                        np.testing.assert_allclose(shape[i], baseline_shape[i])
                    self.assertGreater(shape[0][-1], shape[0][-2])
                    self.assertLess(shape[0][-1] - shape[0][-2], .05)
                    np.testing.assert_array_equal(record['strain_pct'], before_x)
                    np.testing.assert_array_equal(record['stress_mpa'], before_y)

    def test_loading_prefix_is_selected_before_duplicate_strains_are_combined(self):
        record, _ = recoil_record()
        meta = record['_acquisition']
        peak = meta['peak']
        # Later, higher-stress readings at exactly the same early strains must
        # not replace the original elastic measurements during deduplication.
        meta['strain'][-3:] = [.2, .4, .6]
        meta['stress'][-3:] = [800., 700., 600.]
        x, y, ids = loading_curve(record)
        for value in (.2, .4, .6):
            self.assertAlmostEqual(y[np.argmin(abs(x - value))], 1100 * value)
        self.assertTrue(np.all(ids <= peak))

    def test_manual_range_and_line_also_exclude_unloading(self):
        for mode in ('range', 'line'):
            values = []
            for direction in ('forward', 'backward', 'fixed'):
                record, _ = recoil_record(direction)
                override = {'mode': mode, 'strain_bounds': [.2, .8], 'source_sha256': 'a' * 64}
                if mode == 'line':
                    override['endpoints'] = [[.2, 220.], [.8, 880.]]
                calc = specimen_calculation(record, override=override)
                values.append([calc['properties'][key] for key in
                               ('Fitted E (GPa)', 'Yield (MPa)', 'Elastic fit R2')])
                self.assertTrue(np.all(calc['measurement_indices'][calc['elastic_mask']]
                                       < record['_acquisition']['peak']))
            np.testing.assert_allclose(values, [values[0]] * 3, atol=1e-10)

    def test_full_inspector_keeps_unloading_and_endpoint_markers(self):
        record, _ = recoil_record('forward')
        calc = specimen_calculation(record)
        payload = {'record': record, 'calculation': calc, 'reference': {'values': {'ys': 1320., 'el': 3.8}}}
        figure = inspection_figure(payload, mode='full')
        traces = {trace.name: trace for trace in figure.data}
        np.testing.assert_array_equal(traces['Measured CSV'].x, record['_acquisition']['strain'])
        np.testing.assert_array_equal(traces['Fit points'].x, calc['strain_pct'][calc['elastic_mask']])
        self.assertEqual(traces['Max retained strain'].x[0], 4.3)
        self.assertAlmostEqual(traces['Instron EL'].x[0], 3.8)
        self.assertGreater(inspection_ranges(calc, 'full')[0][1], 4.3)
        self.assertLess(inspection_ranges(calc, 'yield')[0][1], 2.5)
        self.assertTrue(np.isfinite(instron_ys_strain(calc, 1320.)))

    def test_unresolved_fracture_does_not_block_loading_fit_or_prepeak_landmarks(self):
        record, end = recoil_record()
        meta = record['_acquisition']
        for name in ('strain', 'stress', 'force', 'time'):
            meta[name] = meta[name][:end]
        ids = prepared_indices(meta)
        record.update(strain_pct=meta['strain'][ids], stress_mpa=meta['stress'][ids], _measurement_indices=ids)
        self.assertEqual(fracture_endpoint(record)['status'], 'Not detected')
        self.assertEqual(specimen_calculation(record)['properties']['Yield status'], 'resolved')
        with redirect_stdout(io.StringIO()):
            models, _, _ = prepare_average_curves({}, {'Synthetic': [record]}, prepeak_only=True)
        self.assertIsNotNone(models['Synthetic']['landmark'])

    def test_recoil_group_builds_both_landmark_models_without_a_pointwise_tail(self):
        records = [recoil_record(direction)[0] for direction in ('forward', 'backward', 'fixed')]
        for prepeak in (True, False):
            with redirect_stdout(io.StringIO()):
                models, _, _ = prepare_average_curves({}, {'Synthetic': deepcopy(records)}, prepeak_only=prepeak)
            model = models['Synthetic']
            self.assertIsNotNone(model['landmark'])
            self.assertEqual(model['landmark']['shape_n'], 3)
            self.assertEqual(model['landmark_diagnostic'], '')
            if not prepeak:
                self.assertEqual(model['pointwise_diagnostic'], 'insufficient post-peak data for tail fit')


class LoadingPreviewTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='loading-phase-synthetic-')
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        project = make_fixture(root)
        for number, direction in enumerate(('forward', 'backward', 'fixed'), 1):
            record, _ = recoil_record(direction)
            meta = record['_acquisition']
            path = root / 'data' / 'Alloy A' / f'coupon_{number}.csv'
            np.savetxt(path, np.column_stack([meta['time'], meta['strain'], meta['stress']]),
                       delimiter=',', header='Time,Strain,Stress\n(s),(%),(MPa)', comments='')
        self.session = PreviewSession(root, project)
        self.state = self.session.defaults()
        self.state.update(show_individuals=True, wh_xlim=None, wh_ylim=None)

    def test_original_wh_preview_and_export_arrays_ignore_recoil(self):
        self.state['family'] = 'work_hardening'
        result = self.session.render(self.state)
        self.addCleanup(self.session.engine.plt.close, result['figure'])
        individuals = [(x, y) for sheet, _, index, x, y in result['figure']._export_wh
                       if sheet == 'WH individuals']
        self.assertEqual(len(individuals), 3)
        for x, y in individuals[1:]:
            np.testing.assert_allclose(x, individuals[0][0])
            np.testing.assert_allclose(y, individuals[0][1])

    def test_landmark_error_identifies_fit_without_unrelated_tail_log(self):
        self.state['family'] = 'landmark'
        with patch.object(self.session.engine, 'landmark_specimen', side_effect=ValueError('Synthetic fit unavailable')):
            with self.assertRaises(ValueError) as raised:
                self.session.render(self.state)
        message = str(raised.exception)
        self.assertIn('coupon_1: Synthetic fit unavailable', message)
        self.assertNotIn('[TAIL]', message)
        self.assertNotIn('post-peak', message)


if __name__ == '__main__':
    unittest.main()
