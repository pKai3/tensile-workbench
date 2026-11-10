"""Acknowledgements clear notifications, never calculations or diagnostic history."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
from pathlib import Path
import tempfile
import unittest

from selection_fixture import make_fixture
from tensile_tables import review_fields, specimen_review_mask
from tensile_workbench import TensileWorkbench
from workbench_project import ProjectStore


class ReviewAcknowledgementTests(unittest.TestCase):
    def test_review_reopen_persistence_and_source_change(self):
        with tempfile.TemporaryDirectory(prefix='review-ack-synthetic-') as folder:
            root = Path(folder)
            make_fixture(root)
            with redirect_stdout(io.StringIO()):
                app = TensileWorkbench(root)
                ident = 'Alloy A/coupon_1.csv'
                from tensile_locations import LOCATION
                project = deepcopy(app.store.data)
                project['specimen_variables'][LOCATION]['values'][ident] = 10
                app.store.save(project)
                app.session.set_project(app.store.data)
                app._refresh_properties()
                app.tables.inspector.select(ident)
                payload = app.tables.inspector._payload
                review = payload['review']
                self.assertTrue(review['Needs review'])
                before = deepcopy(payload['calculation']['properties'])
                app.tables.review_only.value = True
                app.tables.inspector.mark_reviewed.click()
                current = app.tables.inspector._payload
                self.assertFalse(current['review']['Needs review'])
                self.assertEqual(current['review']['Reviewed checks'], review['Checks'])
                self.assertIn('✓ Reviewed checks', app.tables.inspector.checks.value)
                self.assertFalse(app.tables.review_only.value)
                for field in ('Yield (MPa)', 'Fitted E (GPa)', 'UTS (MPa)', 'Failure elongation (%)'):
                    self.assertEqual(current['calculation']['properties'][field], before[field])
                samples = app.session.property_tables(app.state(), app._current()['definition'])['tensile_samples']
                self.assertFalse(specimen_review_mask(samples).loc[samples['Specimen ID'] == ident].any())
                audit = app.tables.frames['specimen_diagnostics'].set_index('Specimen ID').loc[ident]
                self.assertEqual(audit['Checks'], review['Checks'])
                self.assertEqual(audit['Review status'], 'Reviewed')
                saved = ProjectStore(root/'tensile_workbench.project.json',
                    root/'tensile_workbench_defaults.json').data['specimen_review_acknowledgements'][ident]
                self.assertEqual(saved['fingerprint'], review['Review fingerprint'])
                app.tables.inspector.reopen_checks.click()
                self.assertTrue(app.tables.inspector._payload['review']['Needs review'])
                self.assertNotIn(ident, app.store.data['specimen_review_acknowledgements'])
                source = Path(payload['source_file'])
                source.write_text(source.read_text() + '\n')
                with self.assertRaisesRegex(ValueError, 'source file changed'):
                    app._review_specimen_checks(ident, review['Review fingerprint'], True)
                app.tables.inspector.clear()

    def test_changed_check_result_or_source_requires_review_again(self):
        record = {'specimen_id': 'A/test.csv', 'source_file': 'test.csv', 'source_sha256': 'source'}
        from tensile_selection import specimen_id
        ident = specimen_id(record)
        properties, reference = {'E': 110.0}, {'sha256': 'summary'}
        check = 'Elastic fit sensitive to selected range.'
        fields = review_fields(check, record, properties, reference, {})
        project = {'specimen_review_acknowledgements': {ident: {'fingerprint': fields['Review fingerprint']}}}
        self.assertFalse(review_fields(check, record, properties, reference, project)['Needs review'])
        for message, rec, props, ref in (
            (check + '\nNew check.', record, properties, reference),
            (check, dict(record, source_sha256='changed'), properties, reference),
            (check, record, {'E': 111.0}, reference),
            (check, record, properties, {'sha256': 'changed'}),
        ):
            self.assertTrue(review_fields(message, rec, props, ref, project)['Needs review'])


if __name__ == '__main__':
    unittest.main()
