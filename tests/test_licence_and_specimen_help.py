"""Local notice and presentation tests; no research data or server startup."""
from contextlib import redirect_stdout
from html import escape
import io
from pathlib import Path
import runpy
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import ipywidgets as widgets

from selection_fixture import make_fixture
from tensile_workbench import TensileWorkbench

ROOT = Path(__file__).resolve().parents[1]


class LicenceAndSpecimenHelpTests(unittest.TestCase):
    def test_app_footer_uses_bundled_mit_notice_without_loading_data(self):
        licence = (ROOT / 'LICENSE').read_text(encoding='utf-8')
        self.assertTrue(licence.startswith('MIT License\n'))
        self.assertIn('Copyright (c) 2026 Brogan Csinger, University of Queensland', licence)
        self.assertIn('The above copyright notice and this permission notice', licence)
        self.assertIn('THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND', licence)
        with tempfile.TemporaryDirectory(prefix='licence-ui-test-') as temporary:
            root = Path(temporary).resolve()
            shutil.copy2(ROOT / 'LICENSE', root / 'LICENSE')
            with patch.dict('os.environ', {'TENSILE_WORKBENCH_DIR': str(root)}), \
                    patch('migrate_tensile_project.migrate') as migrate, \
                    patch('tensile_startup.launch', return_value=SimpleNamespace(ui=widgets.HTML('Fixture'))) as launch, \
                    patch('IPython.display.display'):
                scope = runpy.run_path(str(ROOT / 'workbench_app.py'))
            migrate.assert_called_once_with(root)
            launch.assert_called_once_with(root)
            footer = scope['footer']
            self.assertIs(scope['page'].children[-1], footer)
            self.assertIn('© 2026 Brogan Csinger, University of Queensland', footer.value)
            self.assertIn(escape(licence), footer.value)
            self.assertIn('<details><summary>MIT licence</summary>', footer.value)
            self.assertNotIn('<details open', footer.value)
            self.assertFalse((root / 'data').exists())
            scope['page'].close()
            footer.close()

    def test_specimen_prologue_collapsed_but_checks_and_table_stay_outside(self):
        with tempfile.TemporaryDirectory(prefix='specimen-help-test-') as temporary:
            root = Path(temporary)
            make_fixture(root)
            with redirect_stdout(io.StringIO()):
                app = TensileWorkbench(root)
            view = app.tables
            self.assertIsNone(view.specimen_help.selected_index)
            self.assertEqual(view.specimen_help.children, (view.panels[1],))
            self.assertEqual(view.tabs.children[1].children, (view.specimen_help, view.specimens))
            self.assertIn('EL source used for plots by group', view.panels[1].value)
            self.assertIn('Choose <b>This graph only</b>', view.panels[1].value)
            self.assertTrue(view.specimens.rows)
            self.assertEqual(view.specimens.columns[0], 'Checks')
            self.assertTrue(any(row['check_warning'] and row['values'][0] for row in view.specimens.rows))
            before = app.store.path.read_bytes()
            with patch.object(app, '_refresh_properties', side_effect=AssertionError('Recalculated')):
                view.specimen_help.selected_index = 0
                view.specimen_help.selected_index = None
            self.assertEqual(app.store.path.read_bytes(), before)
            self.assertFalse((root / 'output').exists())
            view.inspector.clear()
            view.comparison.clear()


if __name__ == '__main__':
    unittest.main()
