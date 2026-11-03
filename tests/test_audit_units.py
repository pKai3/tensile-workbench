import tempfile
from pathlib import Path
import unittest
import numpy as np
import pandas as pd
from tensile_core import compute_strain_percent, compute_stress_mpa, load_and_prepare_curve, coerce_numeric
from tensile_units import CurveImportError


class AcquisitionUnitsTests(unittest.TestCase):
    def test_numeric_tokens_keep_locale_whitespace_and_missing_readings(self):
        tokens = ['0', ' 2.50 ', '\u00a03.5\u00a0', '-1,25', ' +2,5e2 ', '1.25e-3',
                  '', None, '-----', '1,2,3', '2 MPa', 'NaN', '-inf', 'Infinity']
        actual = coerce_numeric(pd.DataFrame({'reading': tokens}))['reading'].to_numpy(float)
        expected = [0., 2.5, 3.5, -1.25, 250., .00125, np.nan, np.nan, np.nan,
                    np.nan, np.nan, np.nan, -np.inf, np.inf]
        np.testing.assert_equal(actual, expected)

    def test_import_preserves_all_channels_rows_and_printed_precision(self):
        import csv
        import io
        header = ['Time', 'True Stress (MPa)', 'Engineering Stress (GPa)',
                  'Strain (mm/mm)', 'Force (N)', 'Unused auxiliary']
        units = ['(ms)', '(MPa)', '(GPa)', '(mm/mm)', '(N)', '(mm)']
        stress = ['0.000', '0.100', '0.200', '0.50000', '-----', '0.450', '0.300', '0.050']
        strain = ['0.000', '0.001', '\u00a00.002\u00a0', '0.003', '0.004', '0.005', '0.006', '0.00700']
        with tempfile.TemporaryDirectory() as directory:
            for separator, decimal_comma in [(',', False), (';', True), ('\t', False)]:
                with self.subTest(separator=separator):
                    text = io.StringIO(newline='')
                    writer = csv.writer(text, delimiter=separator)
                    writer.writerow(['Operator comment', 'Preamble with a\nquoted newline'])
                    writer.writerow(header)
                    writer.writerow(units)
                    for i, (s, e) in enumerate(zip(stress, strain)):
                        if decimal_comma:
                            s, e = s.replace('.', ','), e.replace('.', ',')
                        writer.writerow([i * 20, 999, s, e, i * 30, 'unused text'])
                    path = Path(directory) / 'sample.csv'
                    original = text.getvalue().encode('utf-8')
                    path.write_bytes(original)
                    x, y, metadata, ids = load_and_prepare_curve(path, return_metadata=True, strict=True)
                    np.testing.assert_allclose(metadata['time'], np.arange(8) * .02)
                    np.testing.assert_equal(metadata['force'], np.arange(8) * 30)
                    np.testing.assert_allclose(metadata['strain'], np.arange(8) * .1)
                    np.testing.assert_allclose(metadata['stress'], [0, 100, 200, 500, np.nan, 450, 300, 50])
                    np.testing.assert_equal(ids, [0, 1, 2, 3, 5, 6, 7])
                    np.testing.assert_allclose(x, metadata['strain'][ids])
                    np.testing.assert_allclose(y, metadata['stress'][ids])
                    self.assertAlmostEqual(metadata['check_resolution']['uts'], .01)
                    self.assertAlmostEqual(metadata['check_resolution']['el'], .001)
                    self.assertEqual(path.read_bytes(), original)

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
