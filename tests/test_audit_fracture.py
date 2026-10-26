"""Independent audit-style synthetic controls; no research files or settings."""
import unittest
import numpy as np
from tensile_fracture import detect_drop_onset


def progressive_curve(count=8000, noise=0., quantum=0., seed=1, power=2):
    strain = np.linspace(0., 30., count)
    stress = np.where(strain <= 18., 600 * (1 - np.exp(-strain / 2)),
                      600 * (1 - ((strain - 18.) / 12.) ** power))
    stress += np.random.default_rng(seed).normal(0., noise, count)
    if quantum:
        stress = np.round(stress / quantum) * quantum
    return strain, np.maximum(stress, 0.)


class AuditFractureTests(unittest.TestCase):
    def test_smooth_failures_use_measured_ten_percent_crossing(self):
        scenarios = [(n, noise, quantum, power)
            for n in (4000, 8000, 16000)
            for noise, quantum in ((0., 0.), (.05, 0.), (.1, 0.), (.2, 0.),
                (.5, 0.), (1., 0.), (.02, .01), (.02, .05), (.02, .1),
                (.02, .5), (.02, 1.)) for power in (2, 4, 8)]
        for count, noise, quantum, power in scenarios:
            for seed in range(20):
                with self.subTest(count=count, noise=noise, quantum=quantum, power=power, seed=seed):
                    x, y = progressive_curve(count, noise, quantum, seed, power)
                    peak = int(np.argmax(y))
                    crossing = peak + 1 + np.flatnonzero(y[peak + 1:] < .1 * y[peak])[0]
                    result = detect_drop_onset(x, y)
                    self.assertEqual(result['row_before'], crossing)
                    self.assertIn('10% of peak', result['criterion'])
                    self.assertFalse(result['iso_confirmation_observed'])

    def test_abrupt_controls_across_noise_and_resolution(self):
        for count in (4000, 8000, 16000):
            for noise in (0., .05, .2, 1.):
                for seed in range(5):
                    x, y = progressive_curve(count, noise, .05, seed)
                    onset = int(.8 * count)
                    y[onset + 1:] = 0.
                    result = detect_drop_onset(x, y)
                    self.assertEqual(result['row_before'], onset + 1)
                    self.assertTrue(result['iso_confirmation_observed'])


if __name__ == '__main__':
    unittest.main()
