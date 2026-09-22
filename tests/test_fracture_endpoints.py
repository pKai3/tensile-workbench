"""Synthetic endpoint regressions; no research data, exports or plot generation."""
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tensile_fracture import (
    FRACTURE_METHOD, automatic_fracture_endpoint, detect_drop_onset,
    endpoint_available, fracture_audit, fracture_curve, fracture_endpoint,
)
from tensile_gauge import gauge_record
from tensile_properties import specimen_properties


def record_for(load):
    load = np.asarray(load, float)
    x = np.arange(1, len(load) + 1, dtype=float) / 10
    time = np.arange(len(x), dtype=float)
    return {'sample': 'synthetic', 'source_file': 'synthetic/coupon.csv', 'source_sha256': 'a' * 64,
            'strain_pct': x.copy(), 'stress_mpa': load.copy(),
            '_measurement_indices': np.arange(len(x)),
            '_acquisition': {'strain': x, 'stress': load.copy(), 'force': load,
                             'time': time, 'force_channel': 'Force', 'time_channel': 'Time',
                             'strain_channel': 'Strain 1',
                             'peak': int(np.nanargmax(load)), 'peak_basis': 'Maximum force'}}


def sudden_tail(final=30.):
    return [0., 20., 40., 60., 80., 100., 99., 98., final]


def gradual_tail(final=30.):
    return np.r_[np.linspace(0., 100., 21), np.linspace(99., final, 100)]


def distributed_drop(density=1):
    before = np.r_[np.linspace(0., 100., 100 * density), np.linspace(99.8, 80., 100 * density)]
    fall = np.linspace(80., 30., 20 * density + 1)[1:]
    return np.r_[before, fall], len(before)


def accelerating_collapse():
    """Synthetic filtered fall with an acquisition-rate change, not a data fixture."""
    before = np.r_[np.linspace(0., 100., 100), np.linspace(99.8, 80., 100)]
    losses = np.r_[2., 2., 3., np.full(11, 4.)]
    load = np.r_[before, 80. - np.cumsum(losses)]
    time = np.r_[np.arange(len(before)) * .02,
                 (len(before) - 1) * .02 + np.cumsum(np.r_[.02, np.full(len(losses) - 1, .002)])]
    return load, time, len(before)


def accelerating_ductile_record():
    """Fast force loss in time, but smooth continued extension in strain space."""
    load, time, _ = accelerating_collapse()
    record = record_for(load)
    peak = int(np.argmax(load))
    strain = np.r_[load[:peak + 1] / 100., 1. + (100. - load[peak + 1:]) / 100.]
    record['strain_pct'] = strain.copy()
    record['_acquisition'].update(strain=strain, time=time)
    return record


class EndpointRegressionTests(unittest.TestCase):
    def test_accelerated_ductile_extension_is_not_a_sudden_fracture(self):
        record = accelerating_ductile_record()
        end = automatic_fracture_endpoint(record)
        self.assertEqual(end['row_before'], len(record['strain_pct']))
        self.assertEqual(end['strain_pct'], record['strain_pct'][-1])
        self.assertEqual(end['status'], 'Estimated')
        self.assertIn('terminal', end['criterion'])
        self.assertTrue(end['review_required'])

    def test_ductile_shape_check_is_independent_of_strain_scale(self):
        for scale in (.01, 1., 100.):
            record = accelerating_ductile_record()
            record['strain_pct'] *= scale
            record['_acquisition']['strain'] *= scale
            end = automatic_fracture_endpoint(record)
            self.assertEqual(end['row_before'], len(record['strain_pct']))
            self.assertIn('terminal', end['criterion'])

    def test_real_sudden_break_after_ductile_extension_is_still_selected(self):
        record = accelerating_ductile_record()
        a = record['_acquisition']
        a['time'] = np.r_[a['time'], a['time'][-1] + .002]
        a['strain'] = np.r_[a['strain'], a['strain'][-1]]
        a['stress'] = np.r_[a['stress'], 0.]
        a['force'] = np.r_[a['force'], 0.]
        end = automatic_fracture_endpoint(record)
        self.assertEqual(end['row_before'], len(a['strain']) - 1)
        self.assertEqual(end['status'], 'Detected')
        self.assertTrue(end['iso_confirmation_observed'])

    def test_unavailable_pre_event_strain_baseline_requires_review(self):
        load, onset_row = distributed_drop(5)
        record = record_for(load)
        record['_acquisition']['strain'][:] = 5.
        end = automatic_fracture_endpoint(record)
        self.assertEqual(end['row_before'], onset_row)
        self.assertEqual(end['status'], 'Detected')
        self.assertTrue(end['review_required'])
        self.assertIn('strain baseline', end['review_reason'])

    def test_gradual_accelerating_lead_in_does_not_replace_sharp_collapse(self):
        before = np.r_[np.linspace(0., 100., 100), np.linspace(99.99, 80., 2000)]
        lead_in = before[-1] - np.cumsum([.07, .11, .17, .25])
        losses = np.r_[2., 2., 3., np.full(11, 4.)]
        load = np.r_[before, lead_in, lead_in[-1] - np.cumsum(losses)]
        onset_row = len(before) + len(lead_in)
        time = np.r_[np.arange(onset_row) * .02,
                     (onset_row - 1) * .02 + np.cumsum(np.r_[.02, np.full(len(losses) - 1, .002)])]
        record = record_for(load)
        record['_acquisition']['time'] = time
        end = automatic_fracture_endpoint(record)
        self.assertEqual(end['row_before'], onset_row)
        self.assertAlmostEqual(end['stress_mpa'], lead_in[-1])
        self.assertFalse(end['review_required'])

    def test_accelerating_collapse_keeps_slow_leading_edge(self):
        load, time, onset_row = accelerating_collapse()
        rates = -np.diff(load) / np.diff(time)
        # The old 20%-of-fastest gate wrongly discarded this valid leading edge.
        self.assertLess(rates[onset_row - 1], .2 * np.max(rates))
        self.assertLess(np.max(-np.diff(load)), 5.)
        record = record_for(load)
        record['_acquisition']['time'] = time
        end = automatic_fracture_endpoint(record)
        self.assertEqual(end['row_before'], onset_row)
        self.assertEqual(end['stress_mpa'], 80.)
        self.assertEqual(end['status'], 'Detected')
        self.assertIn('multi-reading', end['criterion'])
        self.assertFalse(end['review_required'])
        self.assertFalse(end['iso_confirmation_observed'])
        self.assertTrue(np.isnan(end['confirmation_row']))

    def test_accelerating_collapse_followed_by_recovery_is_rejected(self):
        load, time, _ = accelerating_collapse()
        recovery = np.r_[np.linspace(31., 85., 100), np.full(20, 85.)]
        record = record_for(np.r_[load, recovery])
        record['_acquisition']['time'] = np.r_[time, time[-1] + .02 * np.arange(1, len(recovery) + 1)]
        self.assertEqual(automatic_fracture_endpoint(record)['status'], 'Not detected')

    def test_checks_distinguish_detection_from_missing_iso_confirmation(self):
        from tensile_tables import specimen_check_failures
        for load, expected_review in ((distributed_drop(5)[0], False), (gradual_tail(), True)):
            audit = fracture_audit(record_for(load))
            self.assertFalse(audit['Fracture ISO-style confirmation observed'])
            checks = specimen_check_failures(audit, {})
            self.assertEqual(bool(checks), expected_review)
            if expected_review:
                self.assertIn('terminal', checks)

    def test_inspector_marks_detected_collapse_without_false_review_warning(self):
        from tensile_inspector import inspection_figure, inspection_summary
        from tensile_properties import specimen_calculation
        record = record_for(distributed_drop(5)[0])
        payload = {'group': 'Synthetic', 'sample': 'coupon', 'source_file': record['source_file'],
                   'included': True, 'exclusion_reason': '', 'record': record,
                   'calculation': specimen_calculation(record), 'reference': {'values': {}, 'status': 'Unavailable'}}
        names = [trace.name for trace in inspection_figure(payload).data]
        self.assertIn('Calc EL', names)
        self.assertNotIn('Calc EL (needs review)', names)
        summary = inspection_summary(payload)
        self.assertIn('Rapid multi-reading load loss (heuristic)', summary)
        self.assertIn('not ISO confirmation', summary)

    def test_distributed_collapse_selects_leading_edge_not_terminal(self):
        for density in (1, 5, 20):
            with self.subTest(density=density):
                load, onset_row = distributed_drop(density)
                self.assertLess(np.max(-np.diff(load)), 5.)
                record = record_for(load)
                # Same underlying shape sampled more densely.
                record['_acquisition']['time'] /= density
                end = automatic_fracture_endpoint(record)
                self.assertEqual(end['status'], 'Detected')
                self.assertEqual(end['row_before'], onset_row)
                self.assertLess(end['row_before'], len(load))
                self.assertIn('multi-reading', end['criterion'])
                self.assertGreaterEqual(end['event_loss_fraction'], .05)
                self.assertFalse(end['review_required'])
                self.assertFalse(end['iso_confirmation_observed'])

    def test_distributed_drop_with_recovery_is_not_fracture(self):
        load, _ = distributed_drop(5)
        load = np.r_[load, np.linspace(31., 80., 100), np.linspace(80., 75., 100)]
        end = automatic_fracture_endpoint(record_for(load))
        self.assertEqual(end['status'], 'Not detected')

    def test_slow_continuous_necking_does_not_select_the_peak(self):
        load = np.r_[np.linspace(0., 100., 2000), np.linspace(99.99, 30., 7000)]
        end = automatic_fracture_endpoint(record_for(load))
        self.assertEqual(end['row_before'], len(load))
        self.assertIn('terminal', end['criterion'])

    def test_sampling_rate_change_without_load_rate_change_is_not_a_collapse(self):
        times = np.r_[np.arange(0., 100., .1), np.arange(100., 150., .1), np.arange(150., 171., .02)]
        load = np.where(times < 100., times, 200. - times)
        record = record_for(load)
        record['_acquisition']['time'] = times
        end = automatic_fracture_endpoint(record)
        self.assertEqual(end['row_before'], len(load))
        self.assertIn('terminal', end['criterion'])

    def test_distributed_collapse_preserves_repeated_strain_rows(self):
        load, onset_row = distributed_drop(5)
        record = record_for(load)
        record['_acquisition']['strain'][onset_row:] = record['_acquisition']['strain'][onset_row - 1]
        end = automatic_fracture_endpoint(record)
        self.assertEqual(end['row_before'], onset_row)
        self.assertEqual(end['stress_mpa'], 80.)

    def test_distributed_collapse_does_not_bridge_missing_force(self):
        load, onset_row = distributed_drop(5)
        record = record_for(load)
        record['_acquisition']['force'][onset_row - 1] = np.nan
        end = automatic_fracture_endpoint(record)
        self.assertEqual(end['status'], 'Not detected')

    def test_truncated_sudden_drop_keeps_pre_drop_reading(self):
        record = record_for(sudden_tail())
        end = automatic_fracture_endpoint(record)
        self.assertTrue(endpoint_available(end))
        self.assertEqual(end['status'], 'Detected')
        self.assertEqual(end['row_before'], 8)
        self.assertEqual(end['stress_mpa'], 98.)
        self.assertFalse(end['review_required'])
        self.assertFalse(end['iso_confirmation_observed'])
        self.assertIn('confirmation not recorded', end['criterion'])
        self.assertTrue(np.isnan(end['confirmation_row']))
        self.assertTrue(np.isnan(end['ten_percent_row']))

    def test_confirmed_sudden_drop_still_uses_iso_criterion(self):
        end = automatic_fracture_endpoint(record_for(sudden_tail(60.) + [1., 0.]))
        self.assertEqual(end['status'], 'Detected')
        self.assertEqual(end['row_before'], 8)
        self.assertEqual(end['confirmation_row'], 10)
        self.assertFalse(end['review_required'])
        self.assertTrue(end['iso_confirmation_observed'])
        self.assertIn('ISO-style', end['criterion'])

    def test_gradual_export_ending_at_thirty_percent_is_reviewable(self):
        record = record_for(gradual_tail())
        end = automatic_fracture_endpoint(record)
        self.assertEqual(end['status'], 'Estimated')
        self.assertEqual(end['row_before'], len(record['strain_pct']))
        self.assertEqual(end['strain_pct'], record['strain_pct'][-1])
        self.assertTrue(np.isnan(end['row_after']))
        self.assertTrue(end['review_required'])
        self.assertIn('Progressive terminal', end['criterion'])

    def test_gradual_below_ten_percent_uses_previous_measurement(self):
        load = gradual_tail(1.)
        expected = np.flatnonzero(load[21:] < 10)[0] + 21
        end = automatic_fracture_endpoint(record_for(load))
        self.assertEqual(end['status'], 'Detected')
        self.assertEqual(end['row_before'], expected)  # previous zero-based row + 1
        self.assertEqual(end['row_after'], expected + 1)
        self.assertIn('10% of peak', end['criterion'])

    def test_ten_percent_without_two_does_not_move_sudden_endpoint(self):
        end = automatic_fracture_endpoint(record_for(sudden_tail(5.)))
        self.assertEqual(end['row_before'], 8)
        self.assertEqual(end['status'], 'Detected')
        self.assertFalse(end['review_required'])
        self.assertEqual(end['ten_percent_row'], 9)

    def test_plateau_and_rising_record_do_not_use_last_point(self):
        for load in (np.r_[np.linspace(0, 100, 21), np.full(20, 99.)],
                     np.linspace(0., 100., 40), gradual_tail(90.)):
            with self.subTest(load=load[-1]):
                self.assertFalse(endpoint_available(automatic_fracture_endpoint(record_for(load))))

    def test_low_load_flat_tail_is_not_an_ongoing_terminal_decline(self):
        end = automatic_fracture_endpoint(record_for(np.r_[gradual_tail(), np.full(20, 30.)]))
        self.assertEqual(end['status'], 'Not detected')

    def test_recovered_ping_does_not_supply_sudden_endpoint(self):
        end = automatic_fracture_endpoint(record_for([0, 20, 40, 60, 80, 100, 99, 20, 99, 98, 97]))
        self.assertEqual(end['status'], 'Not detected')

    def test_missing_force_cannot_be_bridged(self):
        record = record_for(gradual_tail())
        record['_acquisition']['force'][30] = np.nan
        end = automatic_fracture_endpoint(record)
        self.assertEqual(end['status'], 'Not detected')
        self.assertIn('gap', end['reason'])

    def test_time_gap_cannot_be_bridged(self):
        record = record_for(sudden_tail())
        record['_acquisition']['time'][-1] += 100
        end = automatic_fracture_endpoint(record)
        self.assertEqual(end['status'], 'Not detected')
        self.assertIn('gap', end['reason'])

    def test_missing_selected_strain_is_not_replaced(self):
        record = record_for(sudden_tail())
        record['_acquisition']['strain'][7] = np.nan
        end = automatic_fracture_endpoint(record)
        self.assertEqual(end['status'], 'Not detected')
        self.assertIn('missing', end['reason'])

    def test_force_units_and_stress_proxy_preserve_selection(self):
        record = record_for(sudden_tail())
        x, stress = record['strain_pct'], record['stress_mpa']
        for force in (None, stress * 25, stress / 1000):
            end = detect_drop_onset(x, stress, force=force)
            self.assertEqual(end['row_before'], 8)
            self.assertEqual(end['status'], 'Detected')

    def test_small_ratio_spike_does_not_replace_gradual_terminal(self):
        load = gradual_tail()
        load[25] = load[24]  # zero previous increment, then a small decrement
        end = automatic_fracture_endpoint(record_for(load))
        self.assertEqual(end['row_before'], len(load))
        self.assertIn('Progressive terminal', end['criterion'])

    def test_saved_manual_endpoint_still_takes_precedence(self):
        record = record_for(sudden_tail())
        record['_failure_override'] = {'row': 7, 'source_sha256': record['source_sha256']}
        end = fracture_endpoint(record)
        self.assertEqual(end['status'], 'Manual')
        self.assertEqual(end['row_before'], 7)
        self.assertEqual(automatic_fracture_endpoint(record)['row_before'], 8)

    def test_stale_endpoint_is_recomputed(self):
        record = record_for(sudden_tail())
        record['_fracture_detection'] = {'method': 'Acquisition-order endpoint selection (v7)',
                                         'status': 'Not detected'}
        end = automatic_fracture_endpoint(record)
        self.assertEqual(end['method'], FRACTURE_METHOD)
        self.assertTrue(endpoint_available(end))

    def test_estimates_flow_through_properties_and_reconstruction(self):
        for load in (sudden_tail(), gradual_tail(), distributed_drop(5)[0]):
            with self.subTest(kind=len(load)):
                record = record_for(load)
                original = record['_acquisition']['strain'].copy()
                end = automatic_fracture_endpoint(record)
                p = specimen_properties(record)
                self.assertEqual(p['Failure elongation (%)'], end['strain_pct'])
                self.assertTrue(np.isfinite(p['Toughness (MJ/m^3)']))
                self.assertEqual(p['Fracture review required'], 'terminal' in end['criterion'])
                x, _, _ = fracture_curve(record)
                self.assertEqual(x[-1], end['strain_pct'])
                rebuilt = gauge_record(record, {'values': {'gauge': 50.}}, True, 25.)
                self.assertEqual(rebuilt['_gauge']['Gauge correction status'], 'Applied')
                peak_x = record['_acquisition']['strain'][record['_acquisition']['peak']]
                expected = peak_x + 2 * (end['strain_pct'] - peak_x)
                self.assertAlmostEqual(rebuilt['_gauge']['Estimated failure elongation (%)'], expected)
                self.assertTrue(np.isfinite(specimen_properties(rebuilt)['Toughness (MJ/m^3)']))
                self.assertEqual(fracture_audit(record)['Fracture criterion'], end['criterion'])
                np.testing.assert_array_equal(record['_acquisition']['strain'], original)


if __name__ == '__main__':
    unittest.main()
