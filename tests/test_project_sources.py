"""Independent projects, content-verified moves and idle refresh on synthetic data."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from selection_fixture import make_fixture
from tensile_sources import (FolderChanges, browse, default_source, folder_snapshot,
                             resolve_sources, validate_sources)
from tensile_workbench import PreviewSession, TensileWorkbench
from tensile_moves import scan_moves, migrate_settings
from tensile_startup import WorkbenchLauncher, local_settings
from workbench_backups import validate_paths


class ProjectSourcesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tensile-sources-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.project = make_fixture(self.root)
        self.other = self.root / 'partner'
        shutil.copytree(self.root / 'data', self.other)
        self.sources = [default_source(self.root / 'data'),
            dict(id='partner', name='Partner', path=str(self.other), output=str(self.root / 'partner-results'))]

    def session(self, sources=None):
        return PreviewSession(self.root, self.project, sources=sources or self.sources)

    def scan(self, session, project):
        return scan_moves(project, session.data_dir, session.files,
                          source_id=session.source_id, source_path=session.source_path)

    def test_same_group_names_are_separate_and_original_ids_survive(self):
        session = self.session()
        self.assertEqual(set(session.files), {'Alloy A', 'Partner/Alloy A'})
        original = session._load('Alloy A')
        partner = session._load('Partner/Alloy A')
        self.assertEqual(original[0]['specimen_id'], 'Alloy A/coupon_1.csv')
        self.assertEqual(partner[0]['specimen_id'], 'Partner/Alloy A/coupon_1.csv')
        self.assertEqual(session.source_path(partner[0]['specimen_id']), Path(partner[0]['source_file']))
        catalogue = session.specimen_variable_catalogue(['Partner/Alloy A'])
        self.assertTrue(all(row['id'].startswith('Partner/') for row in catalogue))
        self.assertEqual(session.output_root(['Partner/Alloy A']), self.root / 'partner-results')
        self.assertEqual(session.output_root(['Alloy A', 'Partner/Alloy A']), self.root / 'output')

    def test_relink_same_project_retains_ids_and_missing_source_retains_settings(self):
        session = self.session()
        ids = session._group_specimen_ids(['Partner/Alloy A'])
        moved = self.root / 'relocated'
        self.other.rename(moved)
        sources = deepcopy(self.sources)
        sources[1]['path'] = str(moved)
        self.assertEqual(self.session(sources)._group_specimen_ids(['Partner/Alloy A']), ids)
        absent = self.session()
        self.assertEqual(set(absent.files), {'Alloy A'})
        self.assertIn('source folder unavailable', ' '.join(absent.discovery_issues))
        self.assertEqual(absent.project['graphs'][0]['settings']['groups'], ['Alloy A'])

    def test_cross_project_move_is_proposed_not_applied_and_survives_rescan(self):
        shutil.rmtree(self.other / 'Alloy A')
        session = self.session()
        project = deepcopy(self.project)
        project['specimen_exclusions'] = {'Alloy A/coupon_1.csv': 'reviewed'}
        tracking, proposals, _ = self.scan(session, project)
        self.assertFalse(proposals)
        project['data_move_tracking'] = tracking
        (self.root / 'data/Alloy A').rename(self.other / 'Alloy A')
        session.reload_data()
        tracking, proposals, warnings = self.scan(session, project)
        self.assertEqual(len(proposals), 1, warnings)
        self.assertEqual(project['graphs'][0]['settings']['groups'], ['Alloy A'])
        self.assertEqual(proposals[0]['new'], 'Partner/Alloy A')
        project['data_move_tracking'] = tracking
        self.assertEqual(self.scan(session, project)[1], proposals)
        applied = migrate_settings(project, proposals[0])
        self.assertEqual(applied['graphs'][0]['settings']['groups'], ['Partner/Alloy A'])
        self.assertEqual(applied['specimen_exclusions'], {'Partner/Alloy A/coupon_1.csv': 'reviewed'})

    def test_duplicate_content_is_ambiguous_across_destinations(self):
        session = self.session()
        project = deepcopy(self.project)
        project['data_move_tracking'] = self.scan(session, project)[0]
        shutil.copytree(self.other / 'Alloy A', self.other / 'Copy')
        shutil.rmtree(self.root / 'data/Alloy A')
        session.reload_data()
        _, proposals, warnings = self.scan(session, project)
        self.assertFalse(proposals)
        self.assertIn('ambiguous move', ' '.join(warnings))

    def test_project_rename_is_reviewed_and_rejected_if_destination_changes(self):
        # Distinct projects; exact duplicate data is intentionally ambiguous.
        original = self.root / 'data/Alloy A/coupon_1.csv'
        original.write_text(original.read_text() + '\n')
        project = deepcopy(self.project)
        project['graphs'][0]['settings']['groups'] = ['Partner/Alloy A']
        session = self.session()
        project['data_move_tracking'] = self.scan(session, project)[0]
        sources = deepcopy(self.sources)
        sources[1]['name'] = 'Renamed'
        renamed = self.session(sources)
        _, proposals, warnings = self.scan(renamed, project)
        self.assertEqual(len(proposals), 1, warnings)
        self.assertEqual(proposals[0]['new'], 'Renamed/Alloy A')
        self.assertTrue(all(a.startswith('Partner/') and b.startswith('Renamed/')
                            for a, b in proposals[0]['mapping'].items()))
        path = self.other / 'Alloy A/coupon_1.csv'
        path.write_text(path.read_text() + '\n')
        self.assertFalse(self.scan(renamed, project)[1])

    def test_failed_discovery_retains_previous_catalogue_and_records(self):
        session = self.session()
        original = session._load('Alloy A')
        files = session.files
        with patch('tensile_workbench.InstronSummaries', side_effect=OSError('Offline')):
            with self.assertRaises(OSError):
                session.reload_data()
        self.assertIs(session.files, files)
        self.assertIs(session._load('Alloy A'), original)

    def test_watch_requires_two_stable_snapshots_and_reads_no_contents(self):
        initial = folder_snapshot(self.sources)
        changes = FolderChanges(initial)
        self.assertFalse(changes.observe(initial))
        path = self.other / 'Alloy A/summary.csv'
        path.write_text('first')
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('No content reads')):
            copying = folder_snapshot(self.sources)
        self.assertFalse(changes.observe(copying))
        path.write_text('finished writing')
        ready = folder_snapshot(self.sources)
        self.assertFalse(changes.observe(ready))
        self.assertTrue(changes.observe(ready))
        changes.accept(ready)
        self.assertFalse(changes.observe(ready))

    def test_source_validation_and_backup_validation_reject_bad_config(self):
        sources = deepcopy(self.sources)
        sources[1]['path'] = str(self.root / 'data/subfolder')
        with self.assertRaisesRegex(ValueError, 'overlap'):
            resolve_sources(sources, self.root)
        sources = deepcopy(self.sources)
        sources[1]['output'] = str(self.root / 'data/results')
        with self.assertRaisesRegex(ValueError, 'separate'):
            resolve_sources(sources, self.root)
        sources[1]['name'] = 'My data'
        with self.assertRaisesRegex(ValueError, 'unique'):
            validate_sources(sources)
        settings = dict(schema_version=1, data_directory='./data', output_directory='./output', sources=sources)
        with self.assertRaises(ValueError):
            validate_paths(json.dumps(settings))

    def test_folder_browser_and_launch_persist_projects(self):
        path, rows = browse(self.other, self.root)
        self.assertEqual(path, self.other)
        self.assertEqual(rows[0][0], 'Alloy A')
        with redirect_stdout(io.StringIO()):
            launcher = WorkbenchLauncher(self.root)
            launcher.sources.load(self.sources)
            launcher.save_button.click()
        self.assertIsNotNone(launcher.app, launcher.message.value)
        self.addCleanup(launcher.app.close)
        self.assertEqual(set(launcher.app.session.files), {'Alloy A', 'Partner/Alloy A'})
        self.assertEqual(local_settings(self.root)['sources'], self.sources)

    def test_invalid_saved_sources_offer_recovery_instead_of_crashing(self):
        (self.root / '.tensile-paths.json').write_text(json.dumps(dict(schema_version=1,
            data_directory='./data', output_directory='./output', sources=[{'name': 'Missing fields'}])))
        launcher = WorkbenchLauncher(self.root)
        self.assertIsNone(launcher.app)
        self.assertIn('Could not read', launcher.message.value)

    def test_live_refresh_preserves_filters_selection_and_other_group_cache(self):
        with redirect_stdout(io.StringIO()):
            app = TensileWorkbench(self.root, sources=self.sources)
        self.addCleanup(app.close)
        first = app.session._load('Alloy A')
        app.project_filter.value = 'partner'
        self.assertEqual(set(app.group_picker.boxes), {'Partner/Alloy A'})
        app.group_picker.boxes['Partner/Alloy A'].value = True
        self.assertEqual(set(app.controls['groups'].value), {'Alloy A', 'Partner/Alloy A'})
        app.group_picker.boxes['Partner/Alloy A'].value = False
        selected = app.controls['groups'].value
        path = self.other / 'Alloy A/coupon_1.csv'
        path.write_text(path.read_text() + '\n')
        with redirect_stdout(io.StringIO()):
            app._poll_sources()
            app._poll_sources()
        self.assertEqual(app.controls['groups'].value, selected)
        self.assertIs(app.session._load('Alloy A'), first)
        self.assertEqual(app.project_filter.value, 'partner')
        self.assertEqual(app.folder_status.value, '')
        self.assertEqual(app.folder_status.layout.display, 'none')
        app.close()
        self.assertFalse(app._folder_watch.enabled)
