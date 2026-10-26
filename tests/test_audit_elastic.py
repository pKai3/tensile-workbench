import unittest
import numpy as np
from tensile_properties import specimen_calculation


class ElasticWindowAuditTests(unittest.TestCase):
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
