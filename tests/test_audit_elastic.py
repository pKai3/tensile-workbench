import unittest
import numpy as np
from tensile_properties import specimen_calculation


def noisy_loading_record(seed=0, *, seating=False, noise=.006, quantum=.0005):
    """Known 110 GPa elasticity followed by plastic flow, with AVE-like error."""
    rng = np.random.default_rng(seed)
    stress = np.linspace(0., 800., 5000)
    strain = 100 * (stress / 110000. + np.maximum(stress - 650., 0.) / 1200.)
    if seating:
        progress = np.minimum(stress / 300., 1.)
        strain += .1 * (2 * progress - progress ** 2)
    strain += rng.normal(0., noise, len(strain))
    if quantum:
        strain = np.round(strain / quantum) * quantum
    return {'sample': 'synthetic noisy AVE', 'source_file': 'synthetic.csv',
            'strain_pct': np.r_[strain, strain[-1] + [.1, .11]],
            'stress_mpa': np.r_[stress, 400., 0.]}


class ElasticWindowAuditTests(unittest.TestCase):
    def test_measurement_noise_preserves_known_properties(self):
        for seed in range(20):
            with self.subTest(seed=seed):
                p = specimen_calculation(noisy_loading_record(seed))['properties']
                self.assertEqual(p['Yield status'], 'resolved')
                self.assertAlmostEqual(p['Fitted E (GPa)'], 110., delta=4.)
                self.assertAlmostEqual(p['Yield (MPa)'], 652.4, delta=3.)
                self.assertGreaterEqual(p['Elastic fit R2'], .98)
                self.assertFalse(p['Fit review required'])

    def test_correlated_tracking_does_not_promote_a_locally_steeper_patch(self):
        # The true elastic slope is constant. Smooth AVE-like drift creates
        # convincing short tangents whose slopes can be much higher than E.
        for period in (200., 300., 400.):
            for phase in (0., np.pi / 2, np.pi, 3 * np.pi / 2):
                with self.subTest(period=period, phase=phase):
                    stress = np.linspace(0., 900., 10000)
                    strain = 100 * (stress / 110000. + np.maximum(stress - 750., 0.) / 2000.)
                    strain += .01 * np.sin(2 * np.pi * stress / period + phase)
                    record = {'sample': 'correlated tracking', 'source_file': 'synthetic.csv',
                              'strain_pct': np.r_[strain, strain[-1] + [.1, .11]],
                              'stress_mpa': np.r_[stress, 450., 0.]}
                    before_x, before_y = record['strain_pct'].copy(), record['stress_mpa'].copy()
                    calc = specimen_calculation(record)
                    p = calc['properties']
                    self.assertAlmostEqual(p['Fitted E (GPa)'], 110., delta=3.)
                    self.assertAlmostEqual(p['Yield (MPa)'], 754., delta=1.)
                    self.assertGreater(p['Fit upper stress (MPa)'] - p['Fit lower stress (MPa)'], 400.)
                    self.assertLess(p['Fit upper stress (MPa)'], 750.)
                    self.assertEqual(p['Fit point count'], calc['elastic_mask'].sum())
                    np.testing.assert_array_equal(record['strain_pct'], before_x)
                    np.testing.assert_array_equal(record['stress_mpa'], before_y)

    def test_short_noisy_elastic_region_still_uses_measurement_tolerance(self):
        for seed in range(10):
            with self.subTest(seed=seed):
                stress = np.linspace(0., 900., 10000)
                strain = 100 * (np.minimum(stress, 280.) / 70000.
                                + np.maximum(stress - 280., 0.) / 110000.
                                + np.maximum(stress - 500., 0.) / 2000.)
                strain += np.random.default_rng(seed).normal(0., .006, len(strain))
                record = {'sample': 'short noisy elastic', 'source_file': 'synthetic.csv',
                          'strain_pct': np.r_[strain, strain[-1] + [.1, .11]],
                          'stress_mpa': np.r_[stress, 450., 0.]}
                p = specimen_calculation(record)['properties']
                self.assertAlmostEqual(p['Fitted E (GPa)'], 110., delta=3.)
                self.assertAlmostEqual(p['Yield (MPa)'], 504., delta=.5)
                self.assertGreaterEqual(p['Elastic fit R2'], .98)
                self.assertLess(p['Elastic fit R2'], .995)
                self.assertEqual(p['Automatic fit support'], 'Measurement-noise tolerance')
                self.assertFalse(p['Fit review required'])

    def test_search_moves_above_seating_region_without_smoothing_measurements(self):
        for seed in range(20):
            with self.subTest(seed=seed):
                record = noisy_loading_record(seed, seating=True, noise=.001)
                before_x, before_y = record['strain_pct'].copy(), record['stress_mpa'].copy()
                calc = specimen_calculation(record)
                p = calc['properties']
                self.assertEqual(p['Yield status'], 'resolved')
                self.assertAlmostEqual(p['Fitted E (GPa)'], 110., delta=2.)
                self.assertAlmostEqual(p['Yield (MPa)'], 652.4, delta=1.)
                self.assertGreater(p['Fit lower stress (MPa)'], .3 * p['UTS (MPa)'])
                self.assertEqual(p['Fit point count'], calc['elastic_mask'].sum())
                np.testing.assert_array_equal(record['strain_pct'], before_x)
                np.testing.assert_array_equal(record['stress_mpa'], before_y)

    def test_linear_plastic_hardening_does_not_hide_an_earlier_elastic_window(self):
        stress = np.linspace(0., 900., 10000)
        strain = 100 * (stress / 200000. + np.maximum(stress - 50., 0.) / 2000.)
        record = {'sample': 'low yield ratio', 'source_file': 'synthetic.csv',
                  'strain_pct': np.r_[strain, strain[-1] + [.1, .11]],
                  'stress_mpa': np.r_[stress, 450., 0.]}
        p = specimen_calculation(record)['properties']
        self.assertAlmostEqual(p['Fitted E (GPa)'], 200., delta=.1)
        self.assertAlmostEqual(p['Yield (MPa)'], 54., delta=.1)
        self.assertLess(p['Fit upper stress (MPa)'], 50.)

    def test_short_elastic_region_is_preferred_over_linear_seating(self):
        stress = np.linspace(0., 900., 5000)
        strain = 100 * (np.minimum(stress, 280.) / 70000.
                        + np.maximum(stress - 280., 0.) / 110000.
                        + np.maximum(stress - 500., 0.) / 2000.)
        record = {'sample': 'seating then elastic then plastic', 'source_file': 'synthetic.csv',
                  'strain_pct': np.r_[strain, strain[-1] + [.1, .11]],
                  'stress_mpa': np.r_[stress, 450., 0.]}
        p = specimen_calculation(record)['properties']
        self.assertAlmostEqual(p['Fitted E (GPa)'], 110., delta=.1)
        self.assertAlmostEqual(p['Yield (MPa)'], 504., delta=.1)
        self.assertGreater(p['Fit lower stress (MPa)'], 280.)
        self.assertLess(p['Fit upper stress (MPa)'], 500.)

    def test_noisy_elastic_window_takes_precedence_over_smoother_plastic_fit(self):
        stress = np.linspace(0., 900., 30000)
        for noise in (.00035, .0005):
            for seed in range(10):
                with self.subTest(noise=noise, seed=seed):
                    strain = 100 * (stress / 200000. + np.maximum(stress - 50., 0.) / 2000.)
                    strain += np.random.default_rng(seed).normal(0., noise, len(stress))
                    record = {'sample': 'noisy low yield ratio', 'source_file': 'synthetic.csv',
                              'strain_pct': np.r_[strain, strain[-1] + [.1, .11]],
                              'stress_mpa': np.r_[stress, 450., 0.]}
                    p = specimen_calculation(record)['properties']
                    self.assertAlmostEqual(p['Fitted E (GPa)'], 200., delta=5.)
                    self.assertAlmostEqual(p['Yield (MPa)'], 54., delta=.25)
                    self.assertLess(p['Fit upper stress (MPa)'], 50.)

    def test_r_squared_warning_threshold_still_applies_to_noise_tolerant_fit(self):
        record = noisy_loading_record()
        p = specimen_calculation(record, r2_warning=.9999)['properties']
        self.assertTrue(np.isfinite(p['Fitted E (GPa)']))
        self.assertTrue(np.isfinite(p['Yield (MPa)']))
        self.assertTrue(p['Fit review required'])
        self.assertIn('low R2', p['Notes'])

    def test_known_modulus_and_offset_yield_across_strength_ratios(self):
        for uts in (280., 315., 400., 500., 650., 830.):
            stress = np.linspace(0., uts, 5000)
            strain = 100 * (stress / 200000. + .002 * (stress / 250.) ** 10)
            # A separate smooth post-peak segment establishes the UTS boundary.
            x = np.r_[strain, strain[-1] + np.linspace(.01, 5., 101)]
            y = np.r_[stress, np.linspace(uts - 1., 0., 101)]
            record = {'sample': 'synthetic', 'source_file': 'synthetic.csv', 'strain_pct': x, 'stress_mpa': y}
            p = specimen_calculation(record)['properties']
            with self.subTest(uts=uts):
                self.assertAlmostEqual(p['Fitted E (GPa)'], 200., delta=2.)
                self.assertAlmostEqual(p['Yield (MPa)'], 250., delta=1.)
                self.assertFalse(p['Fit review required'])

    def test_short_or_curved_ranges_require_review_not_maximum_slope(self):
        x = np.linspace(0., 3., 100)
        y = 500 * (1 - np.exp(-x))
        record = {'sample': 'curved', 'source_file': 'synthetic.csv', 'strain_pct': x, 'stress_mpa': y}
        p = specimen_calculation(record)['properties']
        self.assertTrue(p['Fit review required'])
        self.assertTrue(p['Automatic fit warning'])
        self.assertTrue(np.isnan(p['Fitted E (GPa)']))
        self.assertTrue(np.isnan(p['Yield (MPa)']))

    def test_strain_sampled_ramberg_osgood_curves_across_hardening_exponents(self):
        for n in (.05, .1, .15, .2, .25, .3, .35, .4):
            stress = np.linspace(0., 2000., 300000)
            strain = 100 * (stress / 200000. + .002 * (stress / 250.) ** (1 / n))
            x = np.linspace(0., 25., 15000)
            y = np.interp(x, strain, stress)
            record = {'sample': 'RO', 'source_file': 'synthetic.csv',
                      'strain_pct': np.r_[x, 25.01, 25.02], 'stress_mpa': np.r_[y, y[-1] * .5, 0.]}
            p = specimen_calculation(record)['properties']
            with self.subTest(n=n):
                if p['Fit review required']:
                    self.assertTrue(p['Automatic fit warning'] or p['Notes'])
                    self.assertTrue(np.isnan(p['Fitted E (GPa)']))
                else:
                    self.assertAlmostEqual(p['Fitted E (GPa)'], 200., delta=5.)
                    self.assertAlmostEqual(p['Yield (MPa)'], 250., delta=5.)


if __name__ == '__main__': unittest.main()
