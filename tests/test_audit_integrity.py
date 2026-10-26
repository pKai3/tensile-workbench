"""Full-session audit regressions, entirely synthetic temporary data."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
from pathlib import Path
import tempfile
import unittest
import numpy as np
import pandas as pd

from selection_fixture import make_fixture
from tensile_workbench import PreviewSession, TensileWorkbench
from tensile_selection import DATA_MODES, discover_sample_groups
from tensile_tables import specimen_export_frame, property_column, property_table_sources, import_status_notice
from tensile_locations import LOCATION, SPECIMEN_COUNT, location_details
from tensile_property_variants import SPECIMEN_FAMILY
from tensile_fracture import prepared_points, fracture_curve


class AuditIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='audit-integrity-synthetic-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = make_fixture(self.root)
        self.group = self.root / 'data' / 'Alloy A'

    def session(self):
        session = PreviewSession(self.root, self.project)
        return session, session.defaults(), session.graphs[0]

    def summaries(self, mismatch=False):
        exports = self.group / 'Batch.is_tens_Exports'
        exports.mkdir()
        rows = []
        for i in (1, 2, 3):
            source = self.group / f'coupon_{i}.csv'
            data = pd.read_csv(source, skiprows=[1])
            uts = data['Tensile stress'].max() + (100 if mismatch and i == 1 else 0)
            source.rename(exports / f'Batch_{i}.csv')
            rows.append(f'{i},Wall_{i:02},{uts:.5f},25.00,500.00,15.00')
        (self.group / 'Batch.csv').write_text(
            'Specimen,Specimen text input 1,Tensile stress at Maximum Force,Strain 1 gauge length,'
            'Tensile stress at Yield (Offset 0.2 %),Tensile strain (Strain 1) at Break (Standard)\n'
            ',,(MPa),(mm),(MPa),(%)\n' + '\n'.join(rows) + '\n\n')
        return exports

    def test_duplicate_exports_quarantined_until_one_retained(self):
        folder = self.summaries()
        copy = folder / 'Batch_1_1.csv'
        copy.write_bytes((folder / 'Batch_1.csv').read_bytes())
        session, state, spec = self.session()
        self.assertEqual(session.imported_counts['Alloy A'], 3)
        frames = session.property_tables(state, spec)
        self.assertEqual(len(frames['tensile_samples']), 4)
        self.assertEqual(frames['tensile_samples'].Included.sum(), 2)
        self.assertEqual(frames['tensile_samples'].Checks.str.contains('Duplicate export').sum(), 2)
        self.assertEqual(frames['import_summary'].iloc[0]['Duplicate candidates'], 2)
        from tensile_inspector import inspection_checks
        payload = session.specimen_inspection(state, spec, copy.relative_to(self.root / 'data').as_posix())
        self.assertIn('Duplicate export', inspection_checks(payload))
        self.assertTrue(payload['withheld'])
        ident = copy.relative_to(self.root / 'data').as_posix()
        project = deepcopy(session.project)
        project['specimen_exclusions'][ident] = 'Keep original export'
        session.set_project(project)
        fixed = session.property_tables(state, spec)
        self.assertEqual(fixed['tensile_samples'].Included.sum(), 3)
        self.assertFalse(fixed['tensile_samples'].Checks.str.contains('Duplicate export').any())
        self.assertEqual(len(session.included_records(state['groups'], spec)['Alloy A']), 3)

    def test_failed_identity_withholds_reference_gauge_and_location_but_keeps_calc(self):
        self.summaries(mismatch=True)
        session, state, spec = self.session()
        spec['gauge_reconstruction'] = {'Alloy A': {'enabled': True, 'target_gauge_mm': 18.75}}
        frames = session.property_tables(state, spec)
        raw = session._load('Alloy A')[0]
        reference = session.instron.match('Alloy A', raw)
        self.assertFalse(reference['identity_verified'])
        self.assertEqual(reference['candidate_values']['gauge'], 25)
        self.assertTrue(all(np.isnan(value) for value in reference['values'].values()))
        row = frames['tensile_samples'].iloc[0]
        self.assertTrue(np.isfinite(row['UTS (MPa)']))
        self.assertTrue(np.isnan(row['Reconstructed EL (%)']))
        self.assertIn('assignment unverified', row.Checks)
        defaults = session.variables_for({**state, 'family': SPECIMEN_FAMILY})[LOCATION]['values']
        self.assertNotIn(raw['specimen_id'], defaults)
        self.assertEqual(len(defaults), 2)
        ys = frames['tensile_summary_details'].query("Property == '0.2% yield strength' and Source == 'Instron'")
        self.assertEqual(ys.iloc[0]['n'], 2)

    def test_import_failure_remains_visible_even_when_every_curve_fails(self):
        for path in self.group.glob('*.csv'):
            path.write_text(path.read_text().replace('(MPa)', '(unrecognised)'))
        session, state, spec = self.session()
        frames = session.property_tables(state, spec)
        self.assertTrue(frames['tensile_samples'].empty)
        self.assertEqual(frames['import_summary'].iloc[0]['Tests found'], 3)
        self.assertEqual(frames['import_summary'].iloc[0]['Curves loaded'], 0)
        self.assertEqual(len(frames['import_diagnostics']), 3)
        self.assertIn('unrecognised', import_status_notice(frames))
        with redirect_stdout(io.StringIO()):
            directory = session.export_properties(state, spec)
        issues = pd.read_excel(next(directory.glob('*results.xlsx')), sheet_name='Import issues')
        self.assertEqual(len(issues), 3)
        with redirect_stdout(io.StringIO()):
            app = TensileWorkbench(self.root)
        self.addCleanup(app.tables.clear)
        self.assertIn('3 import review items', app.fit_warning.value)
        self.assertFalse(app.table_export_button.disabled)
        self.assertIn('unrecognised', app.tables.source_status.value)

    def test_export_columns_reproduce_summary_mean_sd_and_n_for_every_mode(self):
        self.summaries()
        session, state, spec = self.session()
        ident = session._load('Alloy A')[1]['specimen_id']
        for mode in DATA_MODES:
            project = deepcopy(session.project)
            project.setdefault('specimen_data_modes', {})[ident] = {'mode': mode, 'reason': 'synthetic audit'}
            session.set_project(project)
            frames = session.property_tables(state, spec)
            exported = specimen_export_frame(frames['tensile_samples'], frames['instron_comparison'])
            for _, expected in frames['tensile_summary_details'].iterrows():
                with self.subTest(mode=mode, metric=expected.Property, source=expected.Source):
                    short = dict(property_table_sources(expected.Property))[expected.Source]
                    values = exported[property_column(expected.Property, expected.Unit, short)].dropna()
                    self.assertEqual(len(values), expected['n'])
                    if len(values): self.assertAlmostEqual(values.mean(), expected.Mean)
                    if len(values) > 1: self.assertAlmostEqual(values.std(ddof=1), expected.SD)

    def test_reversal_row_is_available_to_strength_and_fracture_preparation(self):
        session, state, spec = self.session()
        record = session._load('Alloy A')[0]
        path = Path(record['source_file'])
        data = pd.read_csv(path, skiprows=[1])
        # A visible tracking reversal at the strength maximum must not delete UTS.
        peak = int(data['Tensile stress'].idxmax())
        data.loc[peak, 'Tensile strain (Strain 1)'] = data.loc[peak - 1, 'Tensile strain (Strain 1)'] - .15
        path.write_text('Time (s),Strain (%),Stress (MPa)\n' + data.to_csv(index=False, header=False))
        session.reload_data()
        record = session._load('Alloy A')[0]
        _, ys, ids = prepared_points(record)
        _, fy, fids = fracture_curve(record)
        self.assertIn(peak, ids)
        self.assertIn(peak, fids)
        self.assertEqual(ys.max(), fy.max())
        self.assertIn('Strain reverses', ' '.join(record['_acquisition']['import_warnings']))

    def test_location_provenance_soft_notice_and_explicit_override(self):
        record = {'specimen_id': 'group/test.csv', 'source_file': 'test.csv', 'specimen_label': 'Wall repeat 250'}
        project = {'group_variables': {SPECIMEN_COUNT: {'values': {'group': 10}}}}
        detail = location_details(record, project, 'group')
        self.assertEqual(detail['Location automatic token'], '250')
        self.assertEqual(detail['Location used'], 250)
        self.assertIn('retained', detail['Location review'])
        project['specimen_variables'] = {LOCATION: {'values': {'group/test.csv': 4}}}
        self.assertEqual(location_details(record, project, 'group')['Location review'], '')

    def test_ambiguous_representative_override_requires_exact_identity(self):
        from tensile_core import choose_representative_curve
        records = [{'source_file': f'Group/{folder}/same.csv', 'sample': 'same',
                    'specimen_id': f'Group/{folder}/same.csv', 'failure_elongation_pct': 10.}
                   for folder in ('one', 'two')]
        with self.assertRaisesRegex(ValueError, 'multiple specimens'):
            choose_representative_curve('Group', records, 'same')
        self.assertIs(choose_representative_curve('Group', records, 'Group/two/same.csv'), records[1])

    def test_equal_peak_strain_span_is_reported_without_smoothing(self):
        from tensile_properties import specimen_calculation
        session, _, _ = self.session()
        record = session._load('Alloy A')[0]
        acquisition = record['_acquisition']
        peak = np.argmax(acquisition['stress'])
        acquisition['stress'][peak:peak + 30] = acquisition['stress'][peak]
        result = specimen_calculation(record)['properties']
        self.assertEqual(result['Uniform elongation (%)'], acquisition['strain'][peak])
        self.assertGreater(result['Uniform elongation peak span (%)'], .1)
        self.assertIn('plateau', result['Uniform elongation warning'])


if __name__ == '__main__': unittest.main()
