"""Synthetic settings only. Every backup is redirected to a temporary vault."""
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import ipywidgets as w

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import workbench_backups as backups
from workbench_project import ProjectStore, ProjectConflict, decode_project
from tensile_backup_ui import BackupPanel
from tensile_startup import (WorkbenchLauncher, DEFAULT_FOLDERS, save_folders,
                             save_sample_data_visibility, local_settings)
from migrate_tensile_project import migrate


class DummyWorkbench:
    def __init__(self, root, **kwargs):
        self.ui = w.HTML('Synthetic workbench')
        self._paused = False

    def save_current(self):
        return True


class BackupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='tensile-backups-test-')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.root = self.base / 'code'
        self.root.mkdir()
        self.history = self.base / 'outside-installation'
        environment = patch.dict(os.environ, {'TENSILE_WORKBENCH_BACKUP_DIR': str(self.history)})
        environment.start()
        self.addCleanup(environment.stop)
        self.defaults = self.root / 'tensile_workbench_defaults.json'
        self.seed = decode_project((ROOT / self.defaults.name).read_bytes())
        for graph in self.seed['graphs']:
            graph['settings'].update(groups=[], families=[], live_update=False)
        self.defaults.write_text(json.dumps(self.seed))
        self.path = self.root / backups.PROJECT_NAME
        self.store = ProjectStore(self.path, self.defaults)
        self.vault = self.store.backups

    def changed(self, name='New settings'):
        project = deepcopy(self.store.data)
        project['graphs'][0]['name'] = name
        project['graphs'][0]['definition']['name'] = name
        return project

    def snapshot(self):
        return self.vault.capture(self.path.read_bytes(), reason='manual', force=True)

    def test_autosaves_are_exact_and_outside_installation(self):
        original = self.path.read_bytes()
        self.store.save(self.changed())
        latest = self.path.read_bytes()
        entries = self.vault.entries()
        self.assertGreaterEqual(len(entries), 2)
        self.assertFalse(self.vault.directory.is_relative_to(self.root))
        self.assertTrue(all(entry['valid'] for entry in entries))
        contents = [self.vault.read(entry['path'])[1] for entry in entries]
        self.assertIn(original, contents)
        self.assertIn(latest, contents)
        self.assertEqual(self.path.with_suffix('.previous.json').read_bytes(), original)
        self.assertEqual(entries[0]['graphs'], len(self.seed['graphs']))

    def test_retention_keeps_recent_daily_and_protected_versions(self):
        vault = backups.BackupVault(self.root / backups.PATHS_NAME)
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        def raw(value):
            return json.dumps({'schema_version': 1, 'data_directory': f'./data-{value}',
                               'output_directory': './output'}).encode()
        protected = vault.capture(raw('manual'), reason='manual', now=start, force=True)
        damaged = vault.directory / 'unrecognised.json'
        damaged.write_text('damaged but do not delete')
        for day in range(60):
            vault.capture(raw(day), now=start + timedelta(days=day, seconds=1))
        latest = []
        for edit in range(25):
            latest.append(vault.capture(raw(f'last-{edit}'), now=start + timedelta(days=59, seconds=edit + 2)))
        entries = [entry for entry in vault.entries() if entry['valid']]
        days = {datetime.fromisoformat(entry['created']).date() for entry in entries if entry['reason'] != 'manual'}
        self.assertEqual(len(days), 30)
        self.assertEqual(len(entries), 50)  # 20 latest + 29 earlier days + protected manual.
        self.assertTrue(all(path.exists() for path in latest[-20:]))
        self.assertTrue(protected.exists())
        self.assertEqual(damaged.read_text(), 'damaged but do not delete')

    def test_hourly_checkpoints_survive_a_burst_of_edits(self):
        vault = backups.BackupVault(self.root / backups.PATHS_NAME)
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        def raw(value):
            return json.dumps({'schema_version': 1, 'data_directory': f'./data-{value}',
                               'output_directory': './output'}).encode()
        checkpoints = [vault.capture(raw(hour), now=start + timedelta(hours=hour)) for hour in range(55)]
        for edit in range(30):
            vault.capture(raw(f'burst-{edit}'), now=start + timedelta(hours=54, seconds=edit + 1))
        self.assertTrue(all(path.exists() for path in checkpoints[7:54]))
        self.assertLessEqual(len(vault.entries()), 20 + 48 + 30)

    def test_external_file_replacement_is_detected_even_with_preserved_timestamp(self):
        original_stat = self.path.stat()
        external = self.changed('Synced from another computer')
        self.path.write_text(json.dumps(external))
        os.utime(self.path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        with self.assertRaises(ProjectConflict):
            self.store.save(self.changed('Stale local edit'))
        self.assertEqual(json.loads(self.path.read_text()), external)

    def test_unchanged_capture_deduplicates_but_next_day_gets_checkpoint(self):
        vault = backups.BackupVault(self.path, self.base / 'isolated')
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        raw = self.path.read_bytes()
        vault.capture(raw, now=start)
        vault.capture(raw, now=start + timedelta(hours=1))
        backups.BackupVault(self.path, self.base / 'isolated').capture(raw, now=start + timedelta(hours=2))
        self.assertEqual(len(vault.entries()), 1)
        vault.capture(raw, now=start + timedelta(days=1))
        self.assertEqual(len(vault.entries()), 2)

    def test_failed_replace_preserves_primary_and_in_memory_revision(self):
        before = self.path.read_bytes()
        revision = self.store.data['revision']
        real_replace = backups.os.replace
        def fail_primary(source, target):
            if Path(target) == self.path:
                raise OSError('Synthetic interrupted replacement')
            return real_replace(source, target)
        with patch.object(backups.os, 'replace', side_effect=fail_primary):
            with self.assertRaisesRegex(OSError, 'interrupted'):
                self.store.save(self.changed())
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(self.path.with_suffix('.previous.json').read_bytes(), before)
        self.assertEqual(self.store.data['revision'], revision)
        self.assertFalse(list(self.root.glob('.*.tmp')))
        self.assertFalse(self.path.with_suffix('.lock').exists())

    def test_failed_fsync_does_not_replace_or_leave_temporary_files(self):
        target = self.root / 'synthetic.json'
        target.write_bytes(b'original')
        with patch.object(backups.os, 'fsync', side_effect=OSError('Synthetic disk failure')):
            with self.assertRaises(OSError):
                backups.atomic_bytes(target, b'changed')
        self.assertEqual(target.read_bytes(), b'original')
        self.assertFalse(list(self.root.glob('.*.tmp')))

    def test_unavailable_vault_reports_warning_without_losing_normal_save(self):
        with patch.object(self.vault, 'capture', side_effect=OSError('Synthetic unavailable backup folder')):
            result = self.store.save(self.changed())
        self.assertEqual(decode_project(self.path.read_bytes()), result)
        self.assertIn('unavailable backup', self.store.backup_warning)
        self.vault.try_capture(self.path.read_bytes())
        self.assertEqual(self.store.backup_warning, '')

    def test_migration_requires_safety_snapshot_and_preserves_original_bytes(self):
        old = deepcopy(self.seed)
        old.pop('group_variables', None)
        old.pop('specimen_variables', None)
        raw = json.dumps(old).encode()
        self.path.write_bytes(raw)
        with patch.object(backups.BackupVault, 'capture', side_effect=OSError('Safety copy failed')):
            with self.assertRaisesRegex(backups.RecoveryRequired, 'Safety copy'):
                ProjectStore(self.path, self.defaults)
        self.assertEqual(self.path.read_bytes(), raw)
        reopened = ProjectStore(self.path, self.defaults)
        protected = [entry for entry in reopened.backups.entries() if entry.get('reason') == 'pre-migration']
        self.assertTrue(any(reopened.backups.read(entry['path'])[1] == raw for entry in protected))
        with patch.object(reopened.backups, 'capture', side_effect=OSError('Safety copy failed')):
            with self.assertRaises(backups.RecoveryRequired):
                reopened.save(reopened.data, reason='pre-migration')
        self.assertEqual(self.path.read_bytes(), raw)

    def test_missing_or_corrupt_project_never_seeds_defaults_over_history(self):
        self.snapshot()
        self.path.unlink()
        with self.assertRaises(backups.RecoveryRequired):
            ProjectStore(self.path, self.defaults)
        self.assertEqual(migrate(self.root), self.path)
        self.assertFalse(self.path.exists())
        self.path.write_text('{broken')
        with self.assertRaises(backups.RecoveryRequired):
            ProjectStore(self.path, self.defaults)
        self.assertEqual(migrate(self.root), self.path)
        self.assertEqual(self.path.read_text(), '{broken')

    def test_previous_save_alone_prevents_default_reset(self):
        self.store.save(self.changed())
        self.path.unlink()
        with self.assertRaises(backups.RecoveryRequired):
            ProjectStore(self.path, self.defaults, backup_root=self.base / 'empty-vault')

    def test_restore_preserves_damaged_original_and_ignores_research_files(self):
        snapshot = self.snapshot()
        valid = self.path.read_bytes()
        damaged = b'{damaged original'
        self.path.write_bytes(damaged)
        data = self.root / 'synthetic-research-placeholder.csv'
        data.write_text('must remain unchanged')
        self.vault.restore(snapshot, expected_current=backups.digest(damaged), expected_snapshot=backups.digest(valid))
        self.assertEqual(self.path.read_bytes(), valid)
        saved_raw = [self.vault.read(path)[1] for path in self.vault.directory.glob('*.json')]
        self.assertIn(damaged, saved_raw)
        self.assertEqual(data.read_text(), 'must remain unchanged')

    def test_restore_aborts_if_safety_copy_fails(self):
        snapshot = self.snapshot()
        raw = self.path.read_bytes()
        self.store.save(self.changed())
        before = self.path.read_bytes()
        with patch.object(self.vault, 'capture', side_effect=OSError('Cannot back up original')):
            with self.assertRaises(OSError):
                self.vault.restore(snapshot, expected_current=backups.digest(before), expected_snapshot=backups.digest(raw))
        self.assertEqual(self.path.read_bytes(), before)

    def test_corrupt_or_changed_snapshot_cannot_be_restored(self):
        snapshot = self.snapshot()
        raw = self.path.read_bytes()
        envelope = json.loads(snapshot.read_bytes())
        envelope['sha256'] = '0' * 64
        snapshot.write_text(json.dumps(envelope))
        with self.assertRaisesRegex(ValueError, 'checksum'):
            self.vault.restore(snapshot, expected_current=backups.digest(raw), expected_snapshot=backups.digest(raw))
        self.assertEqual(self.path.read_bytes(), raw)
        self.assertFalse(next(e for e in self.vault.entries() if e['path'] == snapshot)['valid'])

    def test_damaged_metadata_does_not_hide_other_valid_backups(self):
        snapshot = self.snapshot()
        envelope = json.loads(snapshot.read_bytes())
        del envelope['reason']
        snapshot.write_text(json.dumps(envelope))
        panel = BackupPanel(self.root)
        panel.refresh()
        self.assertNotIn(str(snapshot), panel._entries)
        self.assertGreater(len(panel._entries), 0)
        self.assertIn('1 damaged', panel.message.value)

    def test_unreadable_primary_keeps_recovery_controls_available(self):
        self.path.unlink()
        self.path.mkdir()  # A damaged installation put a directory at this name.
        factory = Mock(side_effect=DummyWorkbench)
        launcher = WorkbenchLauncher(self.root, factory=factory)
        self.assertEqual(launcher.backups.ui.selected_index, 0)
        self.assertIn('Cannot read', launcher.backups.message.value)
        factory.assert_not_called()
        self.assertTrue(self.path.is_dir())

    def test_conflicts_locks_and_restore_do_not_overwrite_another_session(self):
        snapshot = self.snapshot()
        original = self.path.read_bytes()
        other = ProjectStore(self.path, self.defaults)
        self.store.save(self.changed())
        changed = self.path.read_bytes()
        with self.assertRaises(ProjectConflict):
            other.save(other.data)
        with self.assertRaises(ProjectConflict):
            self.vault.restore(snapshot, expected_current=backups.digest(original), expected_snapshot=backups.digest(original))
        with backups.settings_lock(self.path):
            with self.assertRaises(ProjectConflict):
                self.vault.restore(snapshot, expected_current=backups.digest(changed), expected_snapshot=backups.digest(original))
            self.assertTrue(self.path.with_suffix('.lock').exists())
        self.vault.restore(snapshot, expected_current=backups.digest(changed), expected_snapshot=backups.digest(original))
        with self.assertRaises(ProjectConflict):
            self.store.save(self.store.data)
        # Even a session still holding the exact restored bytes must reload.
        with self.assertRaises(ProjectConflict):
            other.save(other.data)

    def test_lock_cleanup_never_removes_someone_elses_lock(self):
        lock = self.path.with_suffix('.lock')
        with backups.settings_lock(self.path):
            lock.write_text('replacement lock')
        self.assertEqual(lock.read_text(), 'replacement lock')

    def test_folder_backups_preserve_other_preferences_and_protect_corrupt_original(self):
        save_folders(self.root, DEFAULT_FOLDERS)
        path = self.root / backups.PATHS_NAME
        before = path.read_bytes()
        save_sample_data_visibility(self.root, False)
        self.assertEqual(local_settings(self.root)['data_directory'], './data')
        save_folders(self.root, {**DEFAULT_FOLDERS, 'data_directory': './elsewhere'})
        self.assertFalse(local_settings(self.root)['show_sample_data'])
        vault = backups.BackupVault(path)
        self.assertIn(before, [vault.read(e['path'])[1] for e in vault.entries()])
        path.write_bytes(b'broken preferences')
        with self.assertRaises(ValueError):
            save_sample_data_visibility(self.root, True)
        save_folders(self.root, DEFAULT_FOLDERS)
        self.assertIn(b'broken preferences', [vault.read(p)[1] for p in vault.directory.glob('*.json')])

    def test_folder_lock_prevents_lost_updates(self):
        save_folders(self.root, DEFAULT_FOLDERS)
        path = self.root / backups.PATHS_NAME
        before = path.read_bytes()
        with backups.settings_lock(path):
            with self.assertRaises(ProjectConflict):
                save_sample_data_visibility(self.root, False)
        self.assertEqual(path.read_bytes(), before)

    def test_ui_requires_confirmation_cancel_and_changed_file_recheck(self):
        snapshot = self.snapshot()
        original = self.path.read_bytes()
        self.store.save(self.changed())
        before = self.path.read_bytes()
        callback = Mock()
        panel = BackupPanel(self.root, after_restore=callback)
        panel.refresh()
        panel.snapshots.value = str(snapshot)
        panel.restore_button.click()
        self.assertIn('analyses', panel.confirm_message.value)
        self.assertEqual(self.path.read_bytes(), before)
        panel.cancel_button.click()
        panel.confirm_button.click()
        self.assertEqual(self.path.read_bytes(), before)
        panel.restore_button.click()
        self.store.save(self.changed('Intervening edit'))
        panel.confirm_button.click()
        self.assertIn('changed after', panel.message.value)
        callback.assert_not_called()
        panel.restore_button.click()
        panel.confirm_button.click()
        self.assertEqual(self.path.read_bytes(), original)
        callback.assert_called_once_with(self.path)

    def test_ui_manual_backup_covers_both_files(self):
        save_folders(self.root, DEFAULT_FOLDERS)
        before = Mock(return_value=True)
        panel = BackupPanel(self.root, before_backup=before)
        panel.backup_now.click()
        before.assert_called_once()
        self.assertIn(backups.PATHS_NAME, panel.message.value)
        self.assertIn(backups.PROJECT_NAME, panel.message.value)
        for name in (backups.PROJECT_NAME, backups.PATHS_NAME):
            entries = backups.BackupVault(self.root / name).entries()
            self.assertTrue(any(entry.get('reason') == 'manual' for entry in entries))

    def test_launcher_can_recover_corrupt_project_without_loading_data_first(self):
        for name in ('data', 'output'):
            (self.root / name).mkdir()
        save_folders(self.root, DEFAULT_FOLDERS)
        snapshot = self.snapshot()
        valid = self.path.read_bytes()
        self.path.write_bytes(b'{corrupted')
        factory = Mock(side_effect=DummyWorkbench)
        with redirect_stdout(io.StringIO()):
            launcher = WorkbenchLauncher(self.root, factory=factory)
            factory.assert_not_called()
            self.assertEqual(launcher.backups.ui.selected_index, 0)
            launcher.backups.snapshots.value = str(snapshot)
            launcher.backups.restore_button.click()
            launcher.backups.confirm_button.click()
        self.assertIsNotNone(launcher.app, launcher.backups.message.value)
        factory.assert_called_once()
        self.assertEqual(self.path.read_bytes(), valid)

    def test_missing_folder_preferences_get_recovery_not_silent_defaults(self):
        save_folders(self.root, DEFAULT_FOLDERS)
        (self.root / backups.PATHS_NAME).unlink()
        factory = Mock(side_effect=DummyWorkbench)
        launcher = WorkbenchLauncher(self.root, factory=factory)
        self.assertEqual(launcher.backups.file.value, backups.PATHS_NAME)
        self.assertIn('missing', launcher.backups.message.value)
        factory.assert_not_called()
        self.assertFalse((self.root / backups.PATHS_NAME).exists())

    def test_restoring_folders_does_not_restore_project_or_create_missing_data_paths(self):
        save_folders(self.root, DEFAULT_FOLDERS)
        path = self.root / backups.PATHS_NAME
        vault = backups.BackupVault(path)
        snapshot = vault.capture(path.read_bytes(), reason='manual', force=True)
        save_folders(self.root, {'data_directory': './new-data', 'output_directory': './new-output'})
        project = self.path.read_bytes()
        factory = Mock(side_effect=DummyWorkbench)
        launcher = WorkbenchLauncher(self.root, factory=factory)
        launcher.backups.file.value = backups.PATHS_NAME
        launcher.backups.snapshots.value = str(snapshot)
        launcher.backups.restore_button.click()
        launcher.backups.confirm_button.click()
        self.assertEqual(self.path.read_bytes(), project)
        self.assertEqual(local_settings(self.root)['data_directory'], './data')
        self.assertIsNone(launcher.app)
        factory.assert_not_called()
        self.assertIn('Confirm folders', launcher.message.value)
        self.assertFalse((self.root / 'data').exists())


if __name__ == '__main__':
    unittest.main()
