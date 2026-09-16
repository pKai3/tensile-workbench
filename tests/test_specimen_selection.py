from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from selection_fixture import make_fixture
from tensile_workbench import TensileWorkbench, FAMILIES
from tensile_selection import csv_files
from tensile_tables import METRICS, summary_html
from tensile_instron import InstronSummaries
from workbench_project import ProjectStore, ProjectConflict, validate_project


class FixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        make_fixture(self.root)
        with redirect_stdout(io.StringIO()):
            self.app = TensileWorkbench(self.root)

    def frames(self):
        return self.app.session.property_tables(self.app.state(), self.app._current()['definition'])

    def exclude(self, sample='coupon_2.csv', reason='Synthetic grip slip'):
        self.app._specimen_changed('Alloy A/' + sample, False, reason)


class SelectionTests(FixtureTests):
    def test_included_column_recomputes_statistics_but_keeps_excluded_rows(self):
        before = self.frames()
        mean_before = before['tensile_summary']['UTS (MPa) · Calc Mean'].iloc[0]
        self.exclude()
        frame = self.frames()
        self.assertEqual(len(frame['tensile_samples']), 3)
        self.assertEqual(frame['tensile_samples']['Included'].tolist(), [True, False, True])
        selected = frame['tensile_samples'].query('Included')
        summary = frame['tensile_summary'].iloc[0]
        self.assertEqual(summary['Included n'], 2)
        self.assertEqual(summary['Available n'], 3)
        self.assertAlmostEqual(summary['UTS (MPa) · Calc Mean'], selected['UTS (MPa)'].mean())
        self.assertNotEqual(summary['UTS (MPa) · Calc Mean'], mean_before)
        self.assertEqual(frame['uniform_elongation_summary']['n'].iloc[0], 2)
        self.assertTrue(self.app.export_button.disabled)

    def test_inclusion_persists_per_graph_and_survives_reopen_and_copy(self):
        self.exclude()
        self.app.graph.value = '1'
        self.assertEqual(self.frames()['tensile_summary']['Included n'].iloc[0], 3)
        self.app.graph.value = '0'
        self.assertEqual(self.frames()['tensile_summary']['Included n'].iloc[0], 2)
        with redirect_stdout(io.StringIO()):
            reopened = TensileWorkbench(self.root)
        self.assertIn('Alloy A/coupon_2.csv', reopened._current()['definition']['specimen_exclusions'])
        reopened.new_graph(duplicate=True)
        self.assertIn('Alloy A/coupon_2.csv', reopened._current()['definition']['specimen_exclusions'])

    def test_undo_checkbox_restores_cached_population_and_reason_edits_persist(self):
        self.exclude(reason='first')
        self.exclude(reason='updated')
        self.assertEqual(self.frames()['tensile_samples']['Exclusion Reason'].tolist(), ['', 'updated', ''])
        self.app._specimen_changed('Alloy A/coupon_2.csv', True, '')
        self.assertEqual(self.frames()['tensile_summary']['Included n'].iloc[0], 3)

    def test_all_excluded_has_zero_counts_not_old_averages_and_remains_editable(self):
        for i in (1, 2, 3):
            self.exclude(f'coupon_{i}.csv')
        frames = self.frames()
        self.assertEqual(frames['tensile_summary']['Included n'].iloc[0], 0)
        self.assertTrue(np.isnan(frames['tensile_summary']['UTS (MPa) · Calc Mean'].iloc[0]))
        self.assertEqual(len(self.app.tables.specimens.rows), 3)
        state = {**self.app.state(), 'graph_index': 0, 'family': 'landmark'}
        with self.assertRaisesRegex(ValueError, 'No included usable specimens'):
            self.app.session.render(state)

    def test_selection_failure_does_not_change_saved_or_displayed_population(self):
        self.app.save_current()
        before = self.app.store.path.read_bytes()
        with patch.object(self.app.store, 'save', side_effect=ProjectConflict('test conflict')):
            self.exclude()
        self.assertEqual(self.app.store.path.read_bytes(), before)
        self.assertEqual(self.frames()['tensile_summary']['Included n'].iloc[0], 3)
        self.assertIn('not saved', self.app.save_status.value.lower())

    def test_stale_widget_messages_and_unknown_ids_cannot_change_selection(self):
        widget = self.app.tables.specimens
        old_context = widget.context
        self.app.graph.value = '1'
        before = self.app.store.path.read_bytes()
        widget._receive(widget, {'type': 'selection', 'context': old_context, 'id': 'Alloy A/coupon_2.csv',
                                'included': False, 'reason': ''}, [])
        widget._receive(widget, {'type': 'selection', 'context': widget.context, 'id': 'not a specimen',
                                'included': False, 'reason': ''}, [])
        self.assertEqual(self.app.store.path.read_bytes(), before)

    def test_widget_event_filter_and_sort_keep_identity(self):
        self.app.tables.filter.value = 'coupon_2'
        widget = self.app.tables.specimens
        self.assertEqual(len(widget.rows), 1)
        widget._receive(widget, {'type': 'selection', 'context': widget.context, 'id': widget.rows[0]['id'],
                                'included': False, 'reason': 'test'}, [])
        self.assertEqual(self.frames()['tensile_summary']['Included n'].iloc[0], 2)
        self.app.tables.filter.value = ''
        self.assertEqual(len(widget.rows), 3)
        self.assertFalse(next(row for row in widget.rows if row['sample'] == 'coupon_2')['included'])

    def test_summary_layout_numeric_export_order_and_counts(self):
        frames = self.frames()
        summary = frames['tensile_summary']
        self.assertEqual(len(summary), 1)
        self.assertNotIn('Property', summary.columns)
        columns = list(summary.columns)
        self.assertLess(columns.index('0.2% yield strength (MPa) · Instron Mean'), columns.index('UTS (MPa) · Calc Mean'))
        html = summary_html(frames['tensile_summary_details'])
        self.assertEqual(html.count('scope="col">Calc'), len(METRICS))
        self.assertIn('n = 0', html)
        self.assertIn('±', html)
        self.assertTrue(np.isnan(summary['Tensile toughness (MJ/m³) · Instron Mean'].iloc[0]))
        self.assertIn('0.2% YS (MPa)', self.app.tables.specimens.columns)
        self.assertIn('0.2% Offset Yield Strength (MPa)', frames['tensile_samples'].columns)

    def test_instron_statistics_and_paired_differences_use_only_included(self):
        original = self.app.session.instron.match
        def match(group, row):
            reference = original(group, row)
            number = int(row['sample'].split('_')[-1])
            reference['values'] = {'uts': 100 * number} if number != 3 else {}
            return reference
        with patch.object(self.app.session.instron, 'match', side_effect=match):
            self.app.session._property_frames.clear()
            self.exclude()
        frames = self.frames()
        row = frames['tensile_summary'].iloc[0]
        self.assertEqual(row['UTS (MPa) · Instron Mean'], 100)
        self.assertEqual(row['UTS (MPa) · Instron n'], 1)
        paired = frames['instron_comparison_summary'].query("Property == 'UTS'").iloc[0]
        self.assertEqual(paired['n paired'], 1)
        self.assertEqual(len(frames['instron_comparison'].query("Property == 'UTS'")), 3)

    def test_all_plot_families_receive_only_included_records_and_refresh_caches(self):
        # Render synthetic curves in memory specifically to check selection propagation.
        session = self.app.session
        state = {**self.app.state(), 'graph_index': 0, 'family': 'landmark', 'show_individuals': True}
        original = session.render(state)
        self.assertEqual(original['n_samples'], 3)
        self.exclude()
        for _, family in FAMILIES:
            with self.subTest(family=family):
                result = session.render({**state, 'family': family})
                self.assertEqual(result['n_samples'], 2)
                self.assertEqual({r['sample'] for r in result['sources']}, {'coupon_1', 'coupon_3'})
                self.assertNotIn('n=3', result['log'])
        self.assertFalse(list(self.root.rglob('*.png')))

    def test_export_audit_keeps_excluded_but_average_exports_do_not(self):
        self.exclude()
        destination = self.root / 'test-export'
        destination.mkdir()
        state = {**self.app.state(), 'graph_index': 0, 'family': 'landmark'}
        spec = self.app._current()['definition']
        with redirect_stdout(io.StringIO()):
            self.app.session._export_tables(destination, {'state': state, 'graph_spec': spec})
        samples = pd.read_excel(destination / 'tensile_samples.xlsx')
        audit = pd.read_excel(destination / 'landmark_samples.xlsx')
        summary = pd.read_excel(destination / 'tensile_summary.xlsx')
        self.assertEqual(samples.Included.tolist(), [True, False, True])
        self.assertEqual(samples.loc[1, 'Exclusion Reason'], 'Synthetic grip slip')
        self.assertEqual(set(audit.Sample), {'coupon_1', 'coupon_3'})
        self.assertEqual(summary['Included n'].iloc[0], 2)

    def test_ids_are_relative_portable_and_distinguish_duplicate_stems(self):
        source = self.root / 'data/Alloy A/coupon_1.csv'
        duplicate = source.parent / 'nested/coupon_1.csv'
        duplicate.parent.mkdir()
        shutil.copy2(source, duplicate)
        self.app.session.reload_data()
        self.exclude('nested/coupon_1.csv')
        rows = self.frames()['tensile_samples']
        self.assertEqual(len(rows), 4)
        self.assertEqual(int(rows.Included.sum()), 3)
        self.assertTrue(rows.loc[rows['Specimen ID'] == 'Alloy A/coupon_1.csv', 'Included'].iloc[0])
        for key in ('../bad.csv', '/absolute/file.csv', 'group\\file.csv'):
            project = deepcopy(self.app.store.data)
            project['graphs'][0]['definition']['specimen_exclusions'] = {key: ''}
            with self.assertRaises(ValueError):
                validate_project(project)

    def test_hard_ignore_anywhere_in_file_and_nested_folder_names_for_both_readers(self):
        root = self.root / 'data'
        for relative in ('Alloy A/!before.csv', 'Alloy A/after!.csv', 'Alloy A/x!y/bad.csv',
                         'Alloy A/nested/!bad/bad.csv', 'group!/otherwise-normal.csv'):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('do not read')
        found = csv_files(root)
        self.assertEqual(len(found), 3)
        self.assertEqual(list(self.app.session.engine.find_sample_groups(root)), ['Alloy A'])
        reader = InstronSummaries(root)
        read_paths = []
        with patch.object(reader, 'read', side_effect=lambda path: read_paths.append(path) or []):
            reader.match('Alloy A', self.app.session._load('Alloy A')[0])
        self.assertFalse(any('!' in str(path.relative_to(root)) for path in read_paths))


class DeleteTests(FixtureTests):
    def test_delete_confirmation_cancel_undo_preserves_files_and_selection(self):
        self.exclude()
        files = {p: p.read_bytes() for p in (self.root / 'data').rglob('*.csv')}
        original = deepcopy(self.app._current())
        self.app._ask_delete_graph()
        self.assertIn('Selection test', self.app.delete_message.value)
        self.assertEqual(len(self.app.store.data['graphs']), 2)
        self.app._cancel_delete_graph()
        self.app._confirm_delete_graph()
        self.assertEqual(len(self.app.store.data['graphs']), 2)
        self.app._ask_delete_graph()
        self.app._confirm_delete_graph()
        self.assertEqual(len(self.app.store.data['graphs']), 1)
        self.assertEqual(self.app.graph.value, '1')
        self.app._undo_delete_graph()
        self.assertEqual(self.app._current(), original)
        for path, content in files.items():
            self.assertEqual(path.read_bytes(), content)

    def test_delete_last_creates_empty_draft_undo_survives_restart(self):
        store = self.app.store
        store.delete_graph('1')
        original = deepcopy(store.data['graphs'][0])
        store.delete_graph('0')
        self.assertEqual(store.data['graphs'][0]['settings']['groups'], [])
        reopened = ProjectStore(store.path, store.defaults_path)
        reopened.undo_delete()
        self.assertEqual(reopened.data['graphs'], [original])

    def test_undo_preserves_new_edits_and_handles_name_collision(self):
        store = self.app.store
        store.delete_graph('1')
        store.delete_graph('0')
        project = deepcopy(store.data)
        project['graphs'][0]['name'] = 'Selection test'
        project['graphs'][0]['definition']['name'] = 'Selection test'
        store.save(project)
        store.undo_delete()
        self.assertEqual(len(store.data['graphs']), 2)
        self.assertEqual(store.data['graphs'][0]['name'], 'Selection test (restored 2)')

    def test_delete_conflict_preserves_definition(self):
        self.app._ask_delete_graph()
        before = deepcopy(self.app.store.data)
        with patch.object(self.app.store, 'save', side_effect=ProjectConflict('test conflict')):
            self.app._confirm_delete_graph()
        self.assertEqual(self.app.store.data, before)

    def test_ui_undo_after_last_deletion_does_not_leave_untouched_draft(self):
        for _ in range(2):
            self.app._ask_delete_graph()
            self.app._confirm_delete_graph()
        self.assertEqual(len(self.app.store.data['graphs']), 1)
        self.app._undo_delete_graph()
        self.assertEqual(len(self.app.store.data['graphs']), 1)
        self.assertEqual(self.app._current()['name'], 'Comparison')


if __name__ == '__main__':
    unittest.main()
