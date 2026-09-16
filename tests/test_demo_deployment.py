"""Deployment examples are synthetic and never touch installation data/output."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import ipywidgets as w
import numpy as np

from migrate_tensile_project import migrate
from tensile_startup import (DEFAULT_FOLDERS, DEFAULT_SAMPLE_DATA, SETTINGS_NAME, WorkbenchLauncher,
                             save_folders, save_sample_data_visibility, sample_data_settings)
from tensile_selection import SAMPLE_GROUP_PREFIX, SAMPLE_ID_PREFIX, valid_specimen_id
from tensile_workbench import FAMILIES, PreviewSession, TensileWorkbench, upgrade_legacy_demo_graph
from workbench_project import validate_project

ROOT = Path(__file__).resolve().parents[1]


class DummyWorkbench:
    def __init__(self, root, data_dir, output_dir):
        self.data_dir, self.output_dir = data_dir, output_dir
        self.ui = w.HTML('Synthetic launch test')

    def save_current(self):
        return True


class DemoDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tensile-demo-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        for filename in ('tensile_core.py', 'tensile_workbench_defaults.json'):
            shutil.copy2(ROOT / filename, self.root / filename)
        shutil.copytree(ROOT / 'examples', self.root / 'examples')
        (self.root / 'data').mkdir()

    def test_defaults_are_generic_and_migration_preserves_personal_file(self):
        defaults = json.loads((self.root / 'tensile_workbench_defaults.json').read_text())
        validate_project(defaults)
        self.assertEqual(len(defaults['graphs']), 1)
        groups = defaults['graphs'][0]['settings']['groups']
        self.assertEqual(len(groups), 3)
        self.assertEqual(set(groups), set(defaults['display_names']))
        self.assertTrue(all(group.startswith(SAMPLE_GROUP_PREFIX) for group in groups))
        self.assertEqual(defaults['new_graph_defaults']['settings']['groups'], [])
        self.assertEqual({key: defaults[key] for key in DEFAULT_FOLDERS}, DEFAULT_FOLDERS)
        target = migrate(self.root)
        personal = deepcopy(json.loads(target.read_text()))
        personal['graphs'][0]['name'] = 'My private graph'
        personal['graphs'][0]['settings']['groups'] = ['Arbitrary user sample']
        target.write_text(json.dumps(personal))
        before = target.read_bytes()
        migrate(self.root)
        self.assertEqual(target.read_bytes(), before)

    def test_folder_setup_keeps_primary_path_and_saves_hidden_sample_source(self):
        target = migrate(self.root)
        before = target.read_bytes()
        app = WorkbenchLauncher(self.root, factory=DummyWorkbench)
        self.assertEqual(app._values(), DEFAULT_FOLDERS)
        self.assertIsNone(app.app)
        self.assertFalse(hasattr(app, 'demo_button'))
        self.assertEqual(set(app.fields), set(DEFAULT_FOLDERS))
        custom_output = self.root / 'custom results'
        app.fields['output_directory'].value = str(custom_output)
        app.save_button.click()
        self.assertEqual(app.app.data_dir, self.root / 'data')
        self.assertEqual(app.app.output_dir, custom_output)
        self.assertEqual(target.read_bytes(), before)
        self.assertFalse(list((self.root / 'data').iterdir()))
        self.assertFalse(list(custom_output.iterdir()))
        paths = json.loads((self.root / SETTINGS_NAME).read_text())
        self.assertEqual(paths['data_directory'], './data')
        self.assertEqual(paths['output_directory'], str(custom_output))
        self.assertEqual(paths['sample_data_directory'], './examples/data')
        self.assertTrue(paths['show_sample_data'])

    def test_missing_samples_do_not_block_research_or_create_empty_sample_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            from selection_fixture import make_fixture
            make_fixture(folder)
            with redirect_stdout(io.StringIO()):
                app = TensileWorkbench(folder)
                app.sample_data_toggle.value = False
                app.sample_data_toggle.value = True
            self.assertEqual(set(app.session.files), {'Alloy A'})
            self.assertFalse((Path(folder) / 'examples').exists())
            self.assertIn('unavailable', app.sample_data_note.value)

    def test_fresh_launch_uses_samples_alongside_empty_primary_folder(self):
        with redirect_stdout(io.StringIO()):
            launcher = WorkbenchLauncher(self.root)
            self.assertIsNone(launcher.app)
            launcher.save_button.click()
        self.assertIsNotNone(launcher.app, launcher.message.value)
        self.assertEqual(launcher.app.session.data_dir, self.root / 'data')
        self.assertTrue(launcher.app.sample_data_toggle.value)
        self.assertEqual(len(launcher.app.group_picker.boxes), 3)
        self.assertEqual(len(launcher.app._results), 1)
        self.assertTrue(all(group.startswith(SAMPLE_GROUP_PREFIX) for group in launcher.app.state()['groups']))
        self.assertFalse(list((self.root / 'data').iterdir()))
        self.assertFalse(list((self.root / 'output').iterdir()))
        paths = json.loads((self.root / SETTINGS_NAME).read_text())
        self.assertEqual({key: paths[key] for key in DEFAULT_SAMPLE_DATA}, DEFAULT_SAMPLE_DATA)

    def test_toggle_is_persistent_and_preserves_hidden_selections_and_exclusions(self):
        from selection_fixture import make_fixture
        make_fixture(self.root)
        project_path = self.root / 'tensile_workbench.project.json'
        project = json.loads(project_path.read_text())
        group = SAMPLE_GROUP_PREFIX + 'Demo_Ductile'
        identity = SAMPLE_ID_PREFIX + 'Demo_Ductile/specimen_1.csv'
        project['graphs'][0]['settings']['groups'].append(group)
        project['graphs'][0]['definition']['specimen_exclusions'] = {identity: 'synthetic test'}
        project_path.write_text(json.dumps(project))
        save_folders(self.root, DEFAULT_FOLDERS)
        with redirect_stdout(io.StringIO()):
            app = TensileWorkbench(self.root)
            app.save_current()
        saved = project_path.read_bytes()
        color = app.session.colors['Alloy A']
        self.assertIn(group, app.state()['groups'])
        self.assertIn(app.sample_data_toggle, app.group_picker.ui.children[1].children)
        self.assertTrue(valid_specimen_id(identity))
        self.assertFalse(valid_specimen_id(SAMPLE_ID_PREFIX + '../escape'))
        with redirect_stdout(io.StringIO()):
            app.sample_data_toggle.value = False
        self.assertEqual(project_path.read_bytes(), saved)
        self.assertEqual(app.state()['groups'], ['Alloy A'])
        self.assertNotIn(group, app.group_picker.boxes)
        self.assertEqual(app.session.colors['Alloy A'], color)
        self.assertEqual(set(app.tables.frames['tensile_samples']['Group']), {'Alloy A'})
        self.assertEqual(sample_data_settings(self.root)['show_sample_data'], False)
        paths = json.loads((self.root / SETTINGS_NAME).read_text())
        self.assertEqual(paths['data_directory'], './data')
        self.assertEqual(paths['output_directory'], './output')
        with redirect_stdout(io.StringIO()):
            reopened = TensileWorkbench(self.root)
            reopened.name.value = 'Renamed with samples hidden'
            reopened.save_current()
            reopened.sample_data_toggle.value = True
        self.assertIn(group, reopened.state()['groups'])
        self.assertIn(identity, reopened._current()['definition']['specimen_exclusions'])
        sample_rows = reopened.tables.frames['tensile_samples'].query('Group == @group')
        self.assertEqual(len(sample_rows), 3)
        self.assertEqual(sample_rows['Included'].tolist(), [False, True, True])
        self.assertEqual(reopened.session.data_dir, self.root / 'data')
        self.assertTrue(sample_data_settings(self.root)['show_sample_data'])

    def test_hidden_samples_are_not_read_and_names_cannot_merge_with_research(self):
        sample = self.root / 'examples' / 'data' / 'Demo_Ductile' / 'specimen_1.csv'
        research = self.root / 'data' / 'Demo_Ductile'
        research.mkdir()
        shutil.copy2(sample, research / sample.name)
        session = PreviewSession(self.root)
        sample_key = SAMPLE_GROUP_PREFIX + 'Demo_Ductile'
        self.assertEqual(len(session.files['Demo_Ductile']), 1)
        self.assertEqual(len(session.files[sample_key]), 3)
        own, bundled = session._load('Demo_Ductile')[0], session._load(sample_key)[0]
        self.assertNotEqual(own['specimen_id'], bundled['specimen_id'])
        self.assertTrue(bundled['specimen_id'].startswith(SAMPLE_ID_PREFIX))
        self.assertEqual(own['specimen_id'], 'Demo_Ductile/specimen_1.csv')
        self.assertEqual(session.instron.group_directories[sample_key], sample.parent)
        session.show_sample_data = False
        original = session.engine.find_sample_groups
        def research_only(root):
            self.assertEqual(root, self.root / 'data')
            return original(root)
        with patch.object(session.engine, 'find_sample_groups', side_effect=research_only):
            session.reload_data()
            frames = session.property_tables({'groups': ['Demo_Ductile', sample_key]}, {})
        self.assertEqual(set(frames['tensile_samples']['Group']), {'Demo_Ductile'})

    def test_visibility_save_failure_reverts_without_changing_primary_paths(self):
        from selection_fixture import make_fixture
        make_fixture(self.root)
        save_folders(self.root, DEFAULT_FOLDERS)
        before = (self.root / SETTINGS_NAME).read_bytes()
        with redirect_stdout(io.StringIO()):
            app = TensileWorkbench(self.root)
            with patch('tensile_workbench.save_sample_data_visibility', side_effect=OSError('test denied')):
                app.sample_data_toggle.value = False
        self.assertTrue(app.sample_data_toggle.value)
        self.assertTrue(app.session.show_sample_data)
        self.assertIn('test denied', app.status.value)
        self.assertEqual((self.root / SETTINGS_NAME).read_bytes(), before)

    def test_folder_changes_preserve_sample_preference_and_relative_source_is_portable(self):
        save_folders(self.root, DEFAULT_FOLDERS)
        save_sample_data_visibility(self.root, False)
        new_data, new_output = self.root / 'my inputs', self.root / 'my outputs'
        save_folders(self.root, {'data_directory': str(new_data), 'output_directory': str(new_output)})
        settings = json.loads((self.root / SETTINGS_NAME).read_text())
        self.assertFalse(settings['show_sample_data'])
        self.assertEqual(settings['sample_data_directory'], './examples/data')
        self.assertEqual(settings['data_directory'], str(new_data))
        # Returning to a relative primary directory also works after moving code.
        save_folders(self.root, DEFAULT_FOLDERS)
        moved = self.root / 'moved installation'
        moved.mkdir()
        for filename in ('tensile_core.py', 'tensile_workbench_defaults.json', SETTINGS_NAME):
            shutil.copy2(self.root / filename, moved / filename)
        shutil.copytree(self.root / 'examples', moved / 'examples')
        (moved / 'data').mkdir()
        session = PreviewSession(moved)
        self.assertFalse(session.show_sample_data)
        self.assertEqual(session.sample_data_dir, moved / 'examples' / 'data')

    def test_only_original_demo_graph_gets_namespace_upgrade(self):
        project = json.loads((self.root / 'tensile_workbench_defaults.json').read_text())
        graph = project['graphs'][0]
        graph['settings']['groups'] = ['Demo_Ductile']
        graph['definition']['specimen_exclusions'] = {'Demo_Ductile/specimen_1.csv': 'test'}
        upgraded = upgrade_legacy_demo_graph(project, self.root / 'data', self.root / 'examples' / 'data')
        self.assertEqual(upgraded['graphs'][0]['settings']['groups'], [SAMPLE_GROUP_PREFIX + 'Demo_Ductile'])
        self.assertIn(SAMPLE_ID_PREFIX + 'Demo_Ductile/specimen_1.csv', upgraded['graphs'][0]['definition']['specimen_exclusions'])
        graph['id'] = 'personal'
        self.assertEqual(upgrade_legacy_demo_graph(project, self.root / 'data', self.root / 'examples' / 'data'), project)

    def test_small_datasets_load_and_all_views_accept_them(self):
        files = list((self.root / 'examples' / 'data').rglob('*.csv'))
        self.assertEqual(len(files), 9)
        self.assertLess(sum(path.stat().st_size for path in files), 100_000)
        with redirect_stdout(io.StringIO()):
            session = PreviewSession(self.root)
            self.assertEqual(len(session.files), 3)
            for group in session.files:
                records = session._load(group)
                self.assertEqual(len(records), 3)
                for record in records:
                    self.assertEqual(len(record['strain_pct']), 301)
                    self.assertTrue(np.all(np.diff(record['strain_pct']) > 0))
                    properties = session.engine.specimen_properties(record)
                    self.assertTrue(np.isfinite(properties['Yield (MPa)']))
                    self.assertLess(properties['Yield (MPa)'], properties['UTS (MPa)'])
                    self.assertGreater(properties['Failure elongation (%)'], 10)
            for _, family in FAMILIES:
                result = session.render({**session.defaults(), 'family': family})
                self.assertIsNotNone(result['figure'], family)
                session.engine.plt.close(result['figure'])
        self.assertFalse((self.root / 'output').exists())

    def test_ignore_rules_exempt_only_known_demo_filenames(self):
        shutil.copy2(ROOT / '.gitignore', self.root / '.gitignore')
        subprocess.run(['git', 'init', '-q', str(self.root)], check=True, capture_output=True)
        candidates = ['tensile_workbench.project.json', 'tensile_workbench_v18.project.json',
                      '.tensile-paths.json', 'data/user.csv', 'other/user.csv',
                      'examples/data/Demo_Ductile/research.csv', 'output/result.xlsx',
                      'tensile_workbench_defaults.json', 'examples/data/Demo_Ductile/specimen_1.csv']
        result = subprocess.run(['git', '-C', str(self.root), 'check-ignore', '--stdin'],
                                input='\n'.join(candidates), capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(set(result.stdout.splitlines()), set(candidates[:-2]))


if __name__ == '__main__':
    unittest.main()
