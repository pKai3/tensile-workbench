import tempfile
from pathlib import Path
import unittest
import numpy as np
import pandas as pd
from tensile_core import compute_strain_percent, compute_stress_mpa, load_and_prepare_curve
from tensile_units import CurveImportError


class AcquisitionUnitsTests(unittest.TestCase):
    def test_percent_header_does_not_depend_on_ductility(self):
        for end in (.3, 3., 30.):
            result = compute_strain_percent(pd.DataFrame({'Strain (%)': [0., end]}), {})
            self.assertEqual(result.iloc[-1], end)

    def test_fraction_and_microstrain_are_explicit(self):
        self.assertAlmostEqual(compute_strain_percent(pd.DataFrame({'Strain (mm/mm)': [.03]}), {}).iloc[0], 3.)
        self.assertAlmostEqual(compute_strain_percent(pd.DataFrame({'Strain (με)': [30000.]}), {}).iloc[0], 3.)

    def test_equivalent_stress_units(self):
        for unit, factor in [('MPa', 1.), ('Pa', 1e-6), ('kPa', .001), ('GPa', 1000.),
                             ('psi', .006894757293168), ('ksi', 6.894757293168), ('N/mm²', 1.)]:
            frame = pd.DataFrame({f'Stress ({unit})': [475. / factor]})
            self.assertAlmostEqual(compute_stress_mpa(frame, {}).iloc[0], 475.)

    def test_unknown_conflicting_and_true_only_channels_are_rejected(self):
        for frame, units, compute in [
            (pd.DataFrame({'Strain': [.03]}), {}, compute_strain_percent),
            (pd.DataFrame({'Strain (%)': [3.]}), {'Strain (%)': 'mm/mm'}, compute_strain_percent),
            (pd.DataFrame({'Stress (bananas)': [475.]}), {}, compute_stress_mpa),
            (pd.DataFrame({'True Stress (MPa)': [575.]}), {}, compute_stress_mpa),
            (pd.DataFrame({'True Strain (%)': [3.]}), {}, compute_strain_percent)]:
            with self.assertRaises(CurveImportError): compute(frame, units)

    def test_engineering_channel_wins_over_true(self):
        frame = pd.DataFrame({'True Stress (MPa)': [575.], 'Engineering Stress (MPa)': [475.]})
        self.assertEqual(compute_stress_mpa(frame, {}).iloc[0], 475.)

    def test_header_time_and_decimal_comma_load_together(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'specimen.csv'
            path.write_text('Time (s);Strain (%);Stress (MPa)\n' + '\n'.join(
                f'{i},0;{i},1;{i * 10},5' for i in range(8)))
            x, y, metadata, ids = load_and_prepare_curve(path, return_metadata=True, strict=True)
            np.testing.assert_equal(metadata['time'], np.arange(8))
            self.assertEqual(x[-1], 7.1)
            self.assertEqual(y[-1], 70.5)


if __name__ == '__main__': unittest.main()
