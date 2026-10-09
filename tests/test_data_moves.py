"""Synthetic file-identity checks; no tensile calculations or research files."""
from copy import deepcopy
import hashlib
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from tensile_moves import scan_moves, migrate_settings, validate_tracking
from tensile_selection import discover_sample_groups


class DataMoveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tensile-moves-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'Alloy').mkdir()
        for name in ('a', 'b'):
            (self.root / 'Alloy' / (name + '.csv')).write_text('Synthetic identity ' + name)
        self.project = {
            'display_names': {'Alloy': 'My alloy'},
            'specimen_exclusions': {'Alloy/a.csv': 'grip slip'},
            'specimen_data_modes': {'Alloy/b.csv': {'mode': 'exclude_shape', 'reason': 'shape'}},
            'graphs': [{'id': 'graph', 'settings': {'groups': ['Alloy'],
                'properties_by_group_order': ['Alloy'], 'properties_by_group_labels': {'Alloy': 'Short'}},
                'definition': {'name_overrides': {'Alloy': 'Label'},
                    'color_overrides': {'Alloy': '#123456'},
                    'youngs_modulus_overrides': {'Alloy': 110000},
                    'gauge_reconstruction': {'Alloy': {'enabled': True, 'target_gauge_mm': 25}},
                    'representative_overrides': {'Alloy': 'b'},
                    'specimen_inclusion_overrides': {'Alloy/a.csv': {'included': True, 'reason': 'graph'}}}}]}

    def scan(self, **kwargs):
        return scan_moves(self.project, self.root, discover_sample_groups(self.root), **kwargs)

    def remember(self):
        tracking, proposals, warnings = self.scan()
        self.assertFalse(proposals)
        self.assertFalse(warnings)
        self.project['data_move_tracking'] = tracking

    def move(self, destination='Owner/Project/Batch/Alloy'):
        target = self.root / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        (self.root / 'Alloy').rename(target)
        return destination

    def test_scan_only_proposes_and_explicit_apply_remaps_every_scope(self):
        sha = hashlib.sha256((self.root / 'Alloy/b.csv').read_bytes()).hexdigest()
        self.project['specimen_fit_overrides'] = {'Alloy/b.csv': {'source_sha256': sha, 'mode': 'range'}}
        self.project['specimen_failure_overrides'] = {'Alloy/b.csv': {'source_sha256': sha, 'row': 5}}
        self.project['specimen_fit_history'] = [{'specimen_id': 'Alloy/b.csv', 'before': None, 'after': {}}]
        self.project['specimen_failure_history'] = [{'specimen_id': 'Alloy/b.csv', 'before': None, 'after': {}}]
        self.project['deleted_graphs'] = [{'graph': deepcopy(self.project['graphs'][0]), 'index': 0}]
        self.remember()
        new = self.move()
        before = deepcopy(self.project)
        tracking, proposals, warnings = self.scan()
        self.assertEqual(self.project, before)
        self.assertEqual(len(proposals), 1)
        self.assertFalse(warnings)
        self.assertFalse(proposals[0]['blocked'])
        self.project['data_move_tracking'] = tracking
        result = migrate_settings(self.project, proposals[0])
        validate_tracking(result)
        self.assertEqual(result['display_names'], {new: 'My alloy'})
        self.assertEqual(result['specimen_exclusions'], {new + '/a.csv': 'grip slip'})
        self.assertIn(new + '/b.csv', result['specimen_data_modes'])
        for key in ('specimen_fit_overrides', 'specimen_failure_overrides'):
            self.assertEqual(result[key][new + '/b.csv']['source_sha256'], sha)
        for key in ('specimen_fit_history', 'specimen_failure_history'):
            self.assertEqual(result[key][0]['specimen_id'], new + '/b.csv')
            self.assertEqual(result[key][0]['original_specimen_id'], 'Alloy/b.csv')
        for graph in [result['graphs'][0], result['deleted_graphs'][0]['graph']]:
            self.assertEqual(graph['settings']['groups'], [new])
            self.assertEqual(graph['settings']['properties_by_group_order'], [new])
            self.assertEqual(graph['settings']['properties_by_group_labels'], {new: 'Short'})
            for key in ('name_overrides', 'color_overrides', 'gauge_reconstruction', 'youngs_modulus_overrides'):
                self.assertIn(new, graph['definition'][key])
            self.assertIn(new + '/a.csv', graph['definition']['specimen_inclusion_overrides'])
        self.assertEqual(result['data_move_history'][0]['old_group'], 'Alloy')

    def test_copy_is_not_a_move_and_other_groups_are_not_hashed_on_normal_start(self):
        shutil.copytree(self.root / 'Alloy', self.root / 'Copy')
        self.remember()
        self.assertNotIn('Copy', self.project['data_move_tracking']['groups'])
        self.assertFalse(self.scan()[1])

    def test_unchanged_cache_does_not_reopen_files(self):
        self.remember()
        with patch.object(Path, 'open', side_effect=AssertionError('Unchanged CSV reopened')):
            self.scan()

    def test_reload_preserves_pending_move_until_approved(self):
        self.remember()
        new = self.move()
        tracking, first, _ = self.scan()
        self.project['data_move_tracking'] = tracking
        _, again, _ = self.scan()
        self.assertEqual(first, again)
        self.assertEqual(again[0]['new'], new)
        self.assertEqual(self.project['graphs'][0]['settings']['groups'], ['Alloy'])

    def test_duplicate_destinations_are_ambiguous(self):
        self.remember()
        new = self.move()
        shutil.copytree(self.root / new, self.root / 'Copy')
        _, proposals, warnings = self.scan()
        self.assertFalse(proposals)
        self.assertTrue(any('ambiguous' in w for w in warnings))

    def test_source_changed_during_move_does_not_transfer_override(self):
        self.remember()
        new = self.move()
        (self.root / new / 'b.csv').write_text('Different data')
        _, proposals, warnings = self.scan()
        self.assertFalse(proposals)
        self.assertTrue(warnings)

    def test_filename_rename_needs_review_and_updates_representative(self):
        self.remember()
        (self.root / 'Alloy/b.csv').rename(self.root / 'Alloy/renamed.csv')
        _, proposals, _ = self.scan()
        self.assertEqual(proposals[0]['mapping'], {'Alloy/b.csv': 'Alloy/renamed.csv'})
        result = migrate_settings(self.project, proposals[0])
        self.assertIn('Alloy/renamed.csv', result['specimen_data_modes'])
        self.assertEqual(result['graphs'][0]['definition']['representative_overrides'], {'Alloy': 'renamed'})

    def test_conflicts_block_whole_migration_without_overwriting(self):
        self.remember()
        new = self.move()
        self.project['specimen_exclusions'][new + '/a.csv'] = 'Different reason'
        _, proposals, _ = self.scan()
        self.assertIn('Conflicting', proposals[0]['blocked'])
        before = deepcopy(self.project)
        with self.assertRaises(ValueError):
            migrate_settings(self.project, proposals[0])
        self.assertEqual(self.project, before)

    def test_partial_legacy_evidence_lists_unverified_settings(self):
        sha = hashlib.sha256((self.root / 'Alloy/a.csv').read_bytes()).hexdigest()
        self.project['specimen_fit_overrides'] = {'Alloy/a.csv': {'source_sha256': sha}}
        new = self.move()
        _, proposals, _ = self.scan()
        proposal = proposals[0]
        self.assertTrue(proposal['partial_evidence'])
        self.assertIn('Alloy/b.csv', proposal['unresolved'])
        result = migrate_settings(self.project, proposal)
        self.assertIn(new + '/a.csv', result['specimen_fit_overrides'])
        self.assertIn('Alloy/b.csv', result['specimen_data_modes'])

    def test_multiple_vanished_groups_cannot_merge_into_single_destination(self):
        shutil.copytree(self.root / 'Alloy', self.root / 'Twin')
        self.project['graphs'][0]['settings']['groups'].append('Twin')
        self.remember()
        self.move('Destination')
        # Remove only this synthetic duplicate to model two missing originals.
        shutil.rmtree(self.root / 'Twin')
        _, proposals, _ = self.scan()
        self.assertEqual(len(proposals), 2)
        self.assertTrue(all('Multiple missing groups' in p['blocked'] for p in proposals))

    def review_panel(self):
        import ipywidgets as w
        from tensile_move_review import MoveReview
        root = self.root
        class Store:
            def __init__(self, project):
                self.data = deepcopy(project)
            def save(self, project):
                self.data = deepcopy(project)
        class Session:
            data_dir = root
            def reload_data(self):
                self.files = discover_sample_groups(root)
            def set_project(self, project):
                self.project = deepcopy(project)
        store, session = Store(self.project), Session()
        session.reload_data()
        applied = []
        panel = MoveReview(w, store, session, before_apply=lambda: True,
                           after_apply=lambda: applied.append(True), reload_data=session.reload_data)
        self.addCleanup(lambda: [widget.close() for widget in panel._owned])
        self.addCleanup(panel.ui.close)
        panel.refresh()
        button = next(widget for widget in panel._owned if isinstance(widget, w.Button))
        return store, panel, button, applied

    def test_ui_requires_ok_before_any_reference_is_migrated(self):
        self.remember()
        new = self.move()
        store, panel, button, applied = self.review_panel()
        self.assertEqual(store.data['graphs'][0]['settings']['groups'], ['Alloy'])
        self.assertFalse(applied)
        button.click()
        self.assertEqual(store.data['graphs'][0]['settings']['groups'], [new])
        self.assertEqual(applied, [True])
        self.assertIn('Approved:', panel.message.value)

    def test_ui_rechecks_changed_destination_when_ok_is_clicked(self):
        self.remember()
        new = self.move()
        store, panel, button, applied = self.review_panel()
        (self.root / new / 'b.csv').write_text('Changed after proposal was displayed')
        button.click()
        self.assertEqual(store.data['graphs'][0]['settings']['groups'], ['Alloy'])
        self.assertFalse(applied)
        self.assertIn('Move not applied', panel.message.value)

    def test_forget_requires_confirmation_and_removes_missing_group_reference(self):
        self.project['display_names']['B12'] = 'Removed group'
        store, panel, button, _ = self.review_panel()
        button.click()
        self.assertEqual(store.data['display_names']['B12'], 'Removed group')
        self.assertEqual(button.layout.align_self, 'flex-start')
        panel.cancel_forget.click()
        self.assertIn('B12', store.data['display_names'])
        button.click()
        panel.confirm_forget.click()
        self.assertNotIn('B12', store.data['display_names'])
        self.assertNotIn('data_move_dismissed_groups', store.data)
        panel.refresh()
        self.assertNotIn('review needed', panel.summary.value)

    def test_forget_refuses_group_that_returns_before_confirmation(self):
        self.project['display_names']['B12'] = 'Removed group'
        store, panel, button, _ = self.review_panel()
        button.click()
        (self.root / 'B12').mkdir()
        (self.root / 'B12' / 'one.csv').write_text('Synthetic returning specimen')
        panel.confirm_forget.click()
        self.assertIn('B12', store.data['display_names'])
        self.assertIn('Group not forgotten', panel.message.value)


if __name__ == '__main__':
    unittest.main()
