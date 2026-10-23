"""Name-list operations must not invoke tensile analysis or read entire curves."""
from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import ipywidgets as w
from tensile_instron import InstronSummaries, read_catalogue_csv
from tensile_variables import GroupVariablesView
from tensile_workbench import TensileWorkbench
from selection_fixture import make_fixture
from variable_fixture import column, cell, set_cell
from tensile_locations import LOCATION


STRAIN = ['Tensile strain (Strain 1)']
LOAD = ['Tensile stress', 'Force']
HEADER = 'Time,Tensile strain (Strain 1),Tensile stress\n(s),(%),(MPa)\n'
SUMMARY = ('Specimen,Specimen text input 1,Tensile stress at Maximum Force\n,,(MPa)\n'
           '1,Wall_04,500\n2,Wall_07,520\n\n')


class SpecimenCatalogueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='specimen-catalogue-synthetic-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_bounded_reads_and_same_identity_rules_without_hashing(self):
        group = self.root / 'Owner' / 'Wall'
        exports = group / 'Batch.is_tens_Exports'
        exports.mkdir(parents=True)
        summary = group / 'Batch.csv'
        summary.write_text(SUMMARY)
        paths = [exports / f'Batch_{i}.csv' for i in (1, 2)]
        for path in paths:
            path.write_text(HEADER + '0,0,0\n' * 100_000)
        # Embedded metadata takes precedence over the external summary.
        paths[1].write_text(SUMMARY.replace('Wall_07', 'Wall_09') + HEADER + '0,0,0\n' * 100_000)
        service = InstronSummaries(self.root, {'Owner/Wall': group})
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('No whole-file hash')):
            rows = service.catalogue('Owner/Wall', [summary, *paths], STRAIN, LOAD)
        self.assertEqual([r['specimen_label'] for r in rows], ['Wall_04', 'Wall_09'])
        self.assertEqual(len(rows), 2)  # Summary-only CSV is not a specimen.
        with patch('tensile_instron.read_catalogue_csv', side_effect=AssertionError('Catalogue must be cached')):
            self.assertEqual(service.catalogue('Owner/Wall', [], STRAIN, LOAD), rows)
        for record in rows:
            self.assertEqual(service.match('Owner/Wall', record)['label'], record['specimen_label'])
        stream = io.BytesIO((HEADER + '0,0,0\n' * 100_000).encode())
        with patch.object(Path, 'open', return_value=stream), patch.object(stream, 'close'):
            self.assertTrue(read_catalogue_csv(paths[0], STRAIN, LOAD)[0])
            self.assertLessEqual(stream.tell(), 4096)
        unrecognised = io.BytesIO(b'x' * 1_000_000)
        with patch.object(Path, 'open', return_value=unrecognised), patch.object(unrecognised, 'close'):
            self.assertEqual(read_catalogue_csv(paths[0], STRAIN, LOAD, byte_limit=8192), (False, []))
            self.assertEqual(unrecognised.tell(), 8192)

    def test_delimiters_encoding_conflicts_missing_labels_and_multiline(self):
        for delimiter in (',', ';', '\t'):
            path = self.root / 'embedded.csv'
            text = SUMMARY.replace('Wall_04', '"Mur_04\nOpérateur"').replace(',', delimiter)
            path.write_bytes((text + HEADER.replace(',', delimiter)).encode('cp1252'))
            curve, rows = read_catalogue_csv(path, STRAIN, LOAD)
            self.assertTrue(curve)
            self.assertEqual(rows[0]['label'], 'Mur_04\nOpérateur')
        group = self.root / 'Group'
        exports = group / 'Batch.is_tens_Exports'
        exports.mkdir(parents=True)
        (group / 'Batch.csv').write_text(SUMMARY)
        (group / 'Batch_1.csv').write_text(SUMMARY.replace('Wall_04', 'Wall_06'))
        (exports / 'Batch_1.csv').write_text(HEADER)
        (exports / 'Batch_3.csv').write_text(HEADER)
        rows = InstronSummaries(self.root).catalogue('Group', sorted(group.rglob('*.csv')), STRAIN, LOAD)
        self.assertEqual([r['specimen_label'] for r in rows], ['Wall_04 / Wall_06', ''])

    def test_show_all_does_not_analyse_curves_and_reload_invalidates_catalogue(self):
        make_fixture(self.root)
        other = self.root / 'data' / 'Unselected' / 'Batch.is_tens_Exports'
        other.mkdir(parents=True)
        numbered_summary = SUMMARY.replace('Wall_04', '705_AB_#04')
        (other.parent / 'Batch.csv').write_text(numbered_summary)
        (other / 'Batch_1.csv').write_text(HEADER)
        with redirect_stdout(io.StringIO()):
            app = TensileWorkbench(self.root)
        before = set(app.session._records)
        with (patch.object(app.session, '_load', side_effect=AssertionError('No curve load')),
              patch.object(app.session.engine, 'specimen_properties', side_effect=AssertionError('No fits'))):
            app.custom_variables_panel.selected_index = 0
            app.custom_variable_tabs.selected_index = 1
            view = app.specimen_variables
            set_cell(view, LOCATION, 'Alloy A/coupon_1.csv', '12')
            with patch.object(view, '_sync_table', wraps=view._sync_table) as render:
                view.all_groups.value = True
                self.assertEqual(render.call_count, 1)
            self.assertEqual(cell(view, LOCATION, 'Alloy A/coupon_1.csv'), '12')
            self.assertEqual(app._specimen_numbers['Unselected/Batch.is_tens_Exports/Batch_1.csv'], 4)
            view.all_groups.value = False
            self.assertEqual(cell(view, LOCATION, 'Alloy A/coupon_1.csv'), '12')
        self.assertEqual(set(app.session._records), before)
        (other.parent / 'Batch.csv').write_text(numbered_summary.replace('705_AB_#04', '705_AB_#08'))
        app.session.reload_data()
        self.assertEqual(app.session.specimen_variable_catalogue(['Unselected'])[0]['number'], 8)

    def test_large_table_browses_all_specimens_without_losing_hidden_drafts(self):
        ids = [f'Group/specimen_{i:04}.csv' for i in range(1000)]
        view = GroupVariablesView(w, lambda: {}, lambda: ids, lambda *_: None, scope='specimen')
        view.refresh(ids[:3])
        view.add.click()
        ident = view.table.columns[0]['id']
        view.table._message(None, dict(type='paste', row=0, column=0, text='Position\nmm\n12.5'), [])
        view.all_groups.value = True
        self.assertEqual(len(view.table.groups), 1000)
        set_cell(view, ident, ids[100], '77')
        view.all_groups.value = False
        self.assertEqual(view.table.groups, ids[:3])
        self.assertEqual(cell(view, ident, ids[0]), '12.5')
        view.all_groups.value = True
        self.assertEqual(len(view.table.groups), 1000)
        self.assertEqual(column(view, ident)['name'], 'Position')
        self.assertEqual(cell(view, ident, ids[100]), '77')


if __name__ == '__main__':
    unittest.main()
