from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import ipywidgets as w
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tensile_startup import (DEFAULT_FOLDERS, SETTINGS_NAME, WorkbenchLauncher,
                                resolve_folder, save_folders, validate_folders)
from tensile_workbench import PreviewSession, TensileWorkbench
import launch_workbench
from migrate_tensile_project import migrate
import launch_workbench_windows as windows


class DummyWorkbench:
    def __init__(self, root, data_dir, output_dir):
        self.root, self.data_dir, self.output_dir = root, data_dir, output_dir
        self.ui = w.HTML('Test workbench')

    def save_current(self):
        return True


class FolderTests(unittest.TestCase):
    def test_stable_project_migration_preserves_saved_graphs(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            project = json.loads((ROOT / 'tensile_workbench_defaults.json').read_text())
            legacy = root / 'tensile_workbench_v18.project.json'
            legacy.write_text(json.dumps(project))
            before = legacy.read_bytes()
            target = migrate(root)
            self.assertEqual(target.name, 'tensile_workbench.project.json')
            self.assertEqual(json.loads(target.read_text())['graphs'], project['graphs'])
            self.assertEqual(legacy.read_bytes(), before)
            current = target.read_bytes()
            migrate(root)
            self.assertEqual(target.read_bytes(), current)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            shutil.copy2(ROOT / 'tensile_workbench_defaults.json', root / 'tensile_workbench_defaults.json')
            self.assertTrue(migrate(root).is_file())

    def test_windows_launcher_uses_existing_environment_and_stable_entry_point(self):
        with patch.object(windows.sys, 'platform', 'win32'), \
             patch.object(windows, 'manage_environment', return_value=0) as launch:
            self.assertEqual(windows.main(), 0)
        launch.assert_called_once_with(['launch'])

    def test_first_run_waits_for_confirmation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            factory = Mock(side_effect=DummyWorkbench)
            ui = WorkbenchLauncher(root, factory=factory)
            self.assertEqual(ui._values(), DEFAULT_FOLDERS)
            factory.assert_not_called()
            self.assertIsNone(ui.app)
            self.assertFalse((root / 'data').exists())
            self.assertFalse((root / SETTINGS_NAME).exists())
            ui.save_button.click()
            self.assertIsNotNone(ui.app, ui.message.value)
            self.assertTrue((root / 'data').is_dir())
            self.assertTrue((root / 'output').is_dir())
            self.assertEqual(factory.call_args.kwargs['data_dir'], root / 'data')
            self.assertEqual(factory.call_args.kwargs['output_dir'], root / 'output')
            self.assertEqual(json.loads((root / SETTINGS_NAME).read_text())['output_directory'], './output')
            restored = WorkbenchLauncher(root, factory=factory)
            self.assertEqual(restored.app.output_dir, root / 'output')
            self.assertIsNone(restored.folders.selected_index)

    def test_external_folders_change_and_persist(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve() / 'code'
            root.mkdir()
            first = Path(folder).resolve() / 'different data'
            second = Path(folder).resolve() / 'other input'
            output = Path(folder).resolve() / 'results elsewhere'
            ui = WorkbenchLauncher(root, factory=DummyWorkbench)
            ui.fields['data_directory'].value = str(first)
            ui.fields['output_directory'].value = str(output)
            ui.save_button.click()
            self.assertEqual(ui.app.data_dir, first)
            sentinel = first / 'keep.txt'
            sentinel.write_text('untouched research placeholder')
            ui.fields['data_directory'].value = str(second)
            ui.save_button.click()
            self.assertEqual(ui.app.data_dir, second)
            self.assertEqual(sentinel.read_text(), 'untouched research placeholder')
            restored = WorkbenchLauncher(root, factory=DummyWorkbench)
            self.assertEqual(restored.app.data_dir, second)
            self.assertEqual(restored.app.output_dir, output)
            self.assertFalse((root / 'data').exists())
            self.assertFalse((root / 'output').exists())

    def test_missing_or_invalid_saved_paths_reopen_setup(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            save_folders(root, DEFAULT_FOLDERS)
            factory = Mock(side_effect=DummyWorkbench)
            ui = WorkbenchLauncher(root, factory=factory)
            factory.assert_not_called()
            self.assertEqual(ui.folders.selected_index, 0)
            self.assertIn('unavailable', ui.message.value)
            (root / SETTINGS_NAME).write_text('{broken')
            broken = WorkbenchLauncher(root, factory=factory)
            self.assertIsNone(broken.app)
            self.assertIn('Could not read', broken.message.value)

    def test_file_path_same_folder_and_failed_save_do_not_replace_active_config(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve()
            ui = WorkbenchLauncher(root, factory=DummyWorkbench)
            ui.save_button.click()
            before = (root / SETTINGS_NAME).read_bytes()
            previous = ui.app
            not_folder = root / 'a-file'
            not_folder.write_text('keep')
            ui.fields['data_directory'].value = str(not_folder)
            ui.save_button.click()
            self.assertIs(ui.app, previous)
            self.assertEqual((root / SETTINGS_NAME).read_bytes(), before)
            self.assertIn('not a folder', ui.message.value)
            ui.fields['data_directory'].value = './output'
            ui.save_button.click()
            self.assertIn('separate', ui.message.value)
            self.assertEqual((root / SETTINGS_NAME).read_bytes(), before)

    def test_relative_paths_follow_moved_code_not_cwd(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder).resolve() / 'code'
            root.mkdir()
            ui = WorkbenchLauncher(root, factory=DummyWorkbench)
            ui.save_button.click()
            moved = Path(folder).resolve() / 'moved code'
            root.rename(moved)
            previous = Path.cwd()
            try:
                os.chdir(Path(folder))
                restored = WorkbenchLauncher(moved, factory=DummyWorkbench)
                self.assertEqual(restored.app.data_dir, moved / 'data')
                self.assertEqual(resolve_folder('./output', moved), moved / 'output')
            finally:
                os.chdir(previous)

    def test_portable_entry_point_sets_root_without_starting_server(self):
        with tempfile.TemporaryDirectory() as folder:
            previous = Path.cwd()
            try:
                os.chdir(folder)
                with patch.object(launch_workbench.subprocess, 'call', return_value=0) as call, \
                     patch.object(launch_workbench.sys, 'argv', ['launch_workbench.py', '--no-browser']), \
                     redirect_stdout(io.StringIO()):
                    self.assertEqual(launch_workbench.main(), 0)
                self.assertEqual(call.call_args.kwargs['cwd'], ROOT)
                self.assertEqual(call.call_args.kwargs['env']['TENSILE_WORKBENCH_DIR'], str(ROOT))
                self.assertIn(str(ROOT / 'workbench_app.py'), call.call_args.args[0])
                self.assertIn(str(ROOT / 'workbench_server.py'), call.call_args.args[0])
                self.assertIn('--no-browser', call.call_args.args[0])
                self.assertIn('--token', call.call_args.args[0])
                self.assertIn('--Voila.ip=127.0.0.1', call.call_args.args[0])
            finally:
                os.chdir(previous)

    def test_real_workbench_tables_route_to_external_output_without_plots(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder).resolve()
            root, data, output = base / 'code', base / 'input elsewhere', base / 'results elsewhere'
            root.mkdir()
            group = data / 'Arbitrary alloy name'
            group.mkdir(parents=True)
            shutil.copy2(ROOT / 'tensile_core.py', root / 'tensile_core.py')
            project = json.loads((ROOT / 'tensile_workbench_defaults.json').read_text())
            project['graphs'] = project['graphs'][:1]
            graph = project['graphs'][0]
            graph['settings'].update(groups=[group.name], families=[], live_update=False)
            project['selected_graph'] = graph['id']
            (root / 'tensile_workbench_defaults.json').write_text(json.dumps(project))
            x = np.linspace(0, 18, 181)
            y = np.where(x <= .6, 1000*x, np.where(x <= 6, 600+40*(x-.6), 816-20*(x-6)))
            raw = group / 'coupon.csv'
            raw.write_text('Time,Tensile strain (Strain 1),Tensile stress\n(s),(%),(MPa)\n' +
                           '\n'.join(f'{i},{strain},{stress}' for i, (strain, stress) in enumerate(zip(x,y))))
            raw_before = raw.read_bytes()
            with patch.object(PreviewSession, 'render', side_effect=AssertionError('No plots')), redirect_stdout(io.StringIO()):
                app = TensileWorkbench(root, data_dir=data, output_dir=output)
                destination = app.session.export_properties(app.state(), app._current()['definition'])
                app.session.set_project(deepcopy(app.store.data))
                self.assertEqual(app.session.output_root(), output)
                self.assertEqual(app.session.data_dir, data)
            self.assertTrue(destination.is_relative_to(output))
            self.assertTrue((destination / 'tensile_samples.xlsx').is_file())
            self.assertFalse(list(base.rglob('*.png')))
            self.assertEqual(raw.read_bytes(), raw_before)
            self.assertFalse((root / 'output').exists())


if __name__ == '__main__':
    unittest.main()
