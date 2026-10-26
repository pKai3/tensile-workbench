"""CSV-only operation and PDF-summary fallback, using synthetic inputs only."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from tensile_columns import STRAIN_COLS, STRESS_COLS
from tensile_instron import InstronSummaries, read_summary_csv
from tensile_instron_pdf import read_summary_pdf
from tensile_selection import csv_files, discover_sample_groups
from tensile_tables import summary_source_notice
from tensile_inspector import inspection_summary
from tensile_workbench import TensileWorkbench
from selection_fixture import make_fixture
from pdf_fixture import write_pdf

HEADER = 'Time,Tensile strain (Strain 1),Tensile stress\n(s),(%),(MPa)\n'
SUMMARY = ('Specimen,Specimen text input 1,Tensile stress at Maximum Force\n,,(MPa)\n'
           '1,Wall_04,500.00\n2,Wall_07,520.00\n\n')
LABELS = [['', 'Specimen text input 1', "Modulus (Automatic\nYoung's)\n[GPa]", 'Strain 1 gauge length\n[mm]'],
          ['1', 'Wall_04', '110.00', '12.80'], ['2', 'Wall_07', '112.00', '12.90']]
RESULTS = [['', 'Tensile stress at Yield\n(Offset 0.2 %)\n[MPa]', 'Tensile stress at\nMaximum Force\n[MPa]',
            'Tensile strain (Strain 1)\nat Break (Standard)\n[%]'],
           ['1', '420.00', '500.00', '12.34'], ['2', '430.00', '520.00', '14.56'],
           ['Mean', '425.00', '510.00', '13.45']]


class SummaryFallbackTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tensile-summary-synthetic-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.group = self.root / 'Owner' / 'Wall'
        exports = self.group / 'Batch.is_tens_Exports'
        exports.mkdir(parents=True)
        self.source = exports / 'Batch_1.csv'
        self.source.write_text(HEADER + '0,0,0\n1,1,500.003\n')
        self.pdf = self.group / 'Batch.is_tens.pdf'
        self.record = {'source_file': str(self.source), '_acquisition': {
            'stress': np.array([0., 500.003]), 'check_resolution': {'uts': .001}}}

    def service(self):
        return InstronSummaries(self.root)

    def match(self):
        return self.service().match('Owner/Wall', self.record)

    def test_no_summary_is_available_raw_data_not_a_failed_identity_check(self):
        result = self.match()
        self.assertEqual(result['status'], 'CSV only')
        self.assertEqual(result['availability'], 'csv_only')
        self.assertEqual(result['values'], {})
        self.assertEqual(result['label'], '')
        self.assertEqual(result['check_failures'], [])
        self.assertIn('Calc values remain available', result['notes'])
        self.assertEqual(result['csv_filename'], 'Batch_1.csv')
        self.assertEqual(list(discover_sample_groups(self.root)), ['Owner/Wall'])

    def test_multiblock_multipage_report_preserves_rows_units_precision_and_sources(self):
        write_pdf(self.pdf, [[LABELS], [RESULTS, [
            ['', 'Thickness\n[mm]', 'Width\n[mm]'], ['1', '2.00', '3.00'], ['2', '2.01', '3.01']]]])
        result = self.match()
        self.assertEqual(result['label'], 'Wall_04')
        self.assertEqual(result['source_format'], 'PDF')
        self.assertEqual(result['values'], dict(e=110., gauge=12.8, ys=420., uts=500., el=12.34, thickness=2., width=3.))
        self.assertEqual(result['resolution']['uts'], .01)
        self.assertEqual(result['check_failures'], [])
        self.assertIn('PDF fallback', result['status'])
        self.assertIn('1, 2', result['source_pages'])
        self.assertEqual(len(result['sha256']), 64)
        self.assertEqual(len(read_summary_pdf(self.pdf)), 2)

    def test_catalogue_uses_pdf_operator_labels_and_caches_parsing(self):
        write_pdf(self.pdf, [[LABELS, RESULTS]])
        service = self.service()
        with patch('tensile_instron_pdf.read_summary_pdf', wraps=read_summary_pdf) as read:
            rows = service.catalogue('Owner/Wall', csv_files(self.group), STRAIN_COLS, STRESS_COLS)
            self.assertEqual(rows[0]['specimen_label'], 'Wall_04')
            service.match('Owner/Wall', self.record)
            self.assertEqual(read.call_count, 1)

    def test_csv_takes_precedence_without_reading_pdf_or_filling_missing_fields(self):
        self.pdf.write_bytes(b'not a PDF')
        (self.group / 'Batch.csv').write_text(SUMMARY)
        with patch('tensile_instron_pdf.read_summary_pdf', side_effect=AssertionError('CSV has priority')):
            result = self.match()
        self.assertEqual(result['source_format'], 'CSV')
        self.assertNotIn('gauge', result['values'])
        self.assertEqual(result['check_failures'], [])

    def test_missing_csv_row_or_malformed_csv_does_not_silently_fall_back(self):
        write_pdf(self.pdf, [[LABELS, RESULTS]])
        for content in (SUMMARY.replace('1,Wall_04', '9,Wall_04'), SUMMARY.split('1,Wall_04')[0], '', 'invalid report'):
            (self.group / 'Batch.csv').write_text(content)
            with patch('tensile_instron_pdf.read_summary_pdf', side_effect=AssertionError('CSV needs review')):
                result = self.match()
            self.assertEqual(result['availability'], 'unavailable')
            self.assertIn('No matching specimen row', result['check_failures'][0])

    def test_embedded_csv_wins_over_pdf(self):
        self.source.write_text(SUMMARY + HEADER)
        self.pdf.write_bytes(b'broken')
        result = self.match()
        self.assertEqual(result['source_format'], 'CSV')
        self.assertEqual(result['source'], str(self.source))

    def test_pdf_uts_mismatch_is_still_flagged_and_does_not_rematch(self):
        write_pdf(self.pdf, [[LABELS, RESULTS]])
        self.record['_acquisition']['stress'][-1] = 520.
        result = self.match()
        self.assertEqual(result['label'], 'Wall_04')
        self.assertTrue(any('CSV maximum 520.00' in item for item in result['check_failures']))
        self.assertEqual(result['uts_review_candidates'][0]['label'], 'Wall_07')

    def test_pdf_exact_label_fallback_but_no_guess_from_values_or_row_position(self):
        write_pdf(self.pdf, [[LABELS, RESULTS]])
        self.record['source_file'] = str(self.group / 'Wall_04.csv')
        Path(self.record['source_file']).write_text(HEADER)
        self.assertEqual(self.match()['label'], 'Wall_04')
        self.record['source_file'] = str(self.source.with_name('Batch_8.csv'))
        Path(self.record['source_file']).write_text(HEADER)
        result = self.match()
        self.assertEqual(result['availability'], 'unavailable')
        self.assertEqual(result['values'], {})

    def test_unreadable_and_unsupported_pdf_have_actionable_messages(self):
        self.pdf.write_bytes(b'bad PDF')
        self.assertIn('PDF could not be read', self.match()['check_failures'][0])
        write_pdf(self.pdf, [[[['Graph image only', 'No result table']]]])
        self.assertIn('No supported numbered text tables', self.match()['check_failures'][0])

    def test_conflicting_pdf_values_and_labels_are_not_silently_chosen(self):
        conflicting = deepcopy(RESULTS)
        conflicting[1][2] = '499.00'
        labels = deepcopy(LABELS)
        labels[1][1] = 'Wall_05'
        write_pdf(self.pdf, [[LABELS, RESULTS], [labels, conflicting]])
        result = self.match()
        self.assertTrue(np.isnan(result['values']['uts']))
        self.assertIn('Wall_04 / Wall_05', result['label'])
        self.assertTrue(any('conflicting operator' in item for item in result['check_failures']))

    def test_duplicate_pdf_row_and_exclusion_markers_need_review(self):
        results = deepcopy(RESULTS)
        results[1][0] = 'X 1'
        results.append(results[1])
        write_pdf(self.pdf, [[LABELS, results]])
        result = self.match()
        self.assertTrue(result['excluded'])
        self.assertTrue(any('duplicate specimen row' in item for item in result['check_failures']))

    def test_hard_ignored_pdf_and_folder_are_not_loaded(self):
        for path in (self.group / '!Batch.is_tens.pdf', self.group / '!archive' / self.pdf.name):
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(b'bad')
        self.assertEqual(self.match()['availability'], 'csv_only')

    def test_confirmed_group_boundary_keeps_nested_raw_exports_with_report(self):
        self.source.parent.rename(self.group / 'raw measurements')
        write_pdf(self.pdf, [[LABELS, RESULTS]])
        (self.group / '.tensile-group').touch()
        self.assertEqual(list(discover_sample_groups(self.root)), ['Owner/Wall'])

    def test_pdf_unit_conversion_and_missing_unit_remain_explicit(self):
        write_pdf(self.pdf, [[[['', 'Tensile stress at Maximum Force\n[GPa]',
                              "Modulus (Young's)\n[MPa]", 'Strain 1 gauge length\n[m]'],
                             ['1', '0.50000', '110000', '0.01280']]]])
        values = self.match()['values']
        self.assertEqual(values, dict(uts=500., e=110., gauge=12.8))
        write_pdf(self.pdf, [[[['', 'Tensile stress at Maximum Force'], ['1', '500.00']]]])
        result = self.match()
        self.assertTrue(np.isnan(result['values']['uts']))
        self.assertTrue(any('unsupported PDF unit' in item for item in result['check_failures']))

    def test_conflicting_csv_revisions_remain_flagged_instead_of_using_pdf(self):
        (self.group / 'Batch.csv').write_text(SUMMARY)
        (self.group / 'Batch_1.csv').write_text(SUMMARY.replace('500.00', '499.00'))
        write_pdf(self.pdf, [[LABELS, RESULTS]])
        result = self.match()
        self.assertEqual(result['source_format'], 'CSV')
        self.assertTrue(np.isnan(result['values']['uts']))

    def test_unreadable_pdf_revision_does_not_silently_disappear(self):
        write_pdf(self.pdf, [[LABELS, RESULTS]])
        (self.group / 'Batch.is_tens_1.pdf').write_bytes(b'broken revision')
        result = self.match()
        self.assertEqual(result['values']['uts'], 500.)
        self.assertTrue(any('PDF could not be read' in item for item in result['check_failures']))

    def test_raw_header_without_time_stops_summary_reader_before_numeric_body(self):
        stream = io.StringIO('Strain (%),Stress (MPa)\n' + '0,0\n' * 100_000)
        with patch.object(Path, 'open', return_value=stream), patch.object(stream, 'close'):
            self.assertEqual(read_summary_csv(self.source), [])
            self.assertLess(stream.tell(), 100)


class CSVOnlyWorkflowTests(unittest.TestCase):
    def test_calculation_tables_inspector_reload_and_pdf_provenance(self):
        with tempfile.TemporaryDirectory(prefix='tensile-csv-only-synthetic-') as folder:
            root = Path(folder).resolve()
            make_fixture(root)
            with redirect_stdout(io.StringIO()):
                app = TensileWorkbench(root)
                state = {**app.session.defaults(), **app.state()}
                spec = app._current()['definition']
                frames = app.session.property_tables(state, spec)
            samples = frames['tensile_samples']
            self.assertTrue(np.isfinite(samples['UTS (MPa)']).all())
            self.assertTrue(np.isfinite(samples['0.2% Offset Yield Strength (MPa)']).all())
            self.assertTrue(samples['Instron availability'].eq('csv_only').all())
            self.assertFalse(samples['Checks'].str.contains('Name:|UTS:').any())
            self.assertIn('No Instron summary CSV or PDF', summary_source_notice(samples))
            self.assertFalse(frames['instron_comparison']['Paired'].any())
            original_ids = samples['Specimen ID'].tolist()
            payload = app.session.specimen_inspection(state, spec, original_ids[0])
            self.assertIn('No Instron summary CSV or PDF', inspection_summary(payload))
            result = app.session.render({**state, 'family': 'landmark'})
            self.assertIsNotNone(result['figure'])
            app.session.engine.plt.close(result['figure'])
            # Explicitly requested reconstruction cannot invent missing gauge metadata.
            reconstruct = deepcopy(spec)
            reconstruct['gauge_reconstruction'] = {'Alloy A': {'enabled': True, 'target_gauge_mm': 10.}}
            with self.assertRaisesRegex(ValueError, 'gauge|Gauge'):
                app.session.analysis_records(state, reconstruct)
            app._specimen_changed(original_ids[1], False, 'Synthetic exclusion retained on reload')
            # Exact operator labels bind direct CSVs; no guessed filename row.
            uts = float(samples.iloc[0]['UTS (MPa)'])
            pdf = root / 'data' / 'Alloy A' / 'legacy.pdf'
            write_pdf(pdf, [[[['', 'Specimen text input 1', 'Tensile stress at Maximum Force\n[MPa]'],
                             ['1', 'coupon_1', f'{uts:.2f}']]]])
            with redirect_stdout(io.StringIO()):
                app.session.reload_data()
                frames = app.session.property_tables(state, spec)
            self.assertEqual(frames['tensile_samples']['Specimen ID'].tolist(), original_ids)
            self.assertEqual(frames['tensile_samples'].iloc[0]['Instron Summary Format'], 'PDF')
            self.assertIn('PDF summary fallback', summary_source_notice(frames['tensile_samples']))
            audit = frames['specimen_diagnostics']
            self.assertEqual(audit.iloc[0]['Instron Summary File'], str(pdf))
            self.assertIn('1', audit.iloc[0]['Instron PDF Pages'])
            self.assertFalse(frames['tensile_samples'].iloc[1]['Included'])
            payload = app.session.specimen_inspection(state, spec, original_ids[0])
            self.assertIn('PDF pages:', inspection_summary(payload))
            destination = app.session.export_properties(state, spec)
            exported = pd.read_excel(next(destination.glob('*.xlsx')), sheet_name='Audit')
            self.assertEqual(exported.iloc[0]['Instron Summary File'], str(pdf))
            self.assertEqual(exported.iloc[0]['Instron Summary Format'], 'PDF')
            summary = pdf.with_suffix('.csv')
            summary.write_text('Specimen,Specimen text input 1,Tensile stress at Maximum Force\n,,(MPa)\n'
                               f'1,coupon_1,{uts:.2f}\n')
            with redirect_stdout(io.StringIO()):
                app.session.reload_data()
                updated = app.session.property_tables(state, spec)['tensile_samples']
            self.assertEqual(updated.iloc[0]['Instron Summary Format'], 'CSV')
            summary.unlink()
            pdf.unlink()
            with redirect_stdout(io.StringIO()):
                app.session.reload_data()
                updated = app.session.property_tables(state, spec)['tensile_samples']
            self.assertTrue(updated['Instron availability'].eq('csv_only').all())
            self.assertFalse(updated.iloc[1]['Included'])


if __name__ == '__main__':
    unittest.main()
