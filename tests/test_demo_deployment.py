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

import ipywidgets as w
import numpy as np

from migrate_tensile_project import migrate
from tensile_startup import DEFAULT_FOLDERS, SETTINGS_NAME, WorkbenchLauncher
from tensile_workbench import FAMILIES, PreviewSession
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

    def test_defaults_are_generic_and_migration_preserves_personal_file(self):
        defaults = json.loads((self.root / 'tensile_workbench_defaults.json').read_text())
        validate_project(defaults)
        self.assertEqual(len(defaults['graphs']), 1)
        groups = defaults['graphs'][0]['settings']['groups']
        self.assertEqual(len(groups), 3)
        self.assertEqual(set(groups), set(defaults['display_names']))
        self.assertTrue(all(group.startswith('Demo_') for group in groups))
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

    def test_demo_button_does_not_copy_data_or_replace_graphs(self):
        target = migrate(self.root)
        before = target.read_bytes()
        app = WorkbenchLauncher(self.root, factory=DummyWorkbench)
        self.assertEqual(app._values(), DEFAULT_FOLDERS)
        self.assertIsNone(app.app)
        self.assertFalse(app.demo_button.disabled)
        custom_output = self.root / 'custom results'
        app.fields['output_directory'].value = str(custom_output)
        app.demo_button.click()
        self.assertEqual(app.app.data_dir, self.root / 'examples' / 'data')
        self.assertEqual(app.app.output_dir, custom_output)
        self.assertEqual(target.read_bytes(), before)
        self.assertFalse((self.root / 'data').exists())
        self.assertFalse(list(custom_output.iterdir()))
        paths = json.loads((self.root / SETTINGS_NAME).read_text())
        self.assertEqual(paths['data_directory'], './examples/data')
        self.assertEqual(paths['output_directory'], str(custom_output))

    def test_missing_demo_does_not_silently_create_empty_example_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            app = WorkbenchLauncher(folder, factory=DummyWorkbench)
            self.assertTrue(app.demo_button.disabled)
            app._demo()
            self.assertIsNone(app.app)
            self.assertFalse((Path(folder) / 'examples').exists())
            self.assertIn('unavailable', app.message.value)

    def test_small_datasets_load_and_all_views_accept_them(self):
        files = list((self.root / 'examples' / 'data').rglob('*.csv'))
        self.assertEqual(len(files), 9)
        self.assertLess(sum(path.stat().st_size for path in files), 100_000)
        with redirect_stdout(io.StringIO()):
            session = PreviewSession(self.root, data_dir=self.root / 'examples' / 'data')
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
