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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tensile_workbench import TensileWorkbench, graph_menu_options, NEW_GRAPH_ACTION
import launch_workbench


class WebAppTests(unittest.TestCase):
    def make_app(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        shutil.copy2(ROOT / 'tensile_core.py', root / 'tensile_core.py')
        project = json.loads((ROOT / 'tensile_workbench_defaults.json').read_text())
        base = project['graphs'][0]
        project['graphs'] = []
        for index, name in enumerate(('Baseline', 'New graph', 'Annealed')):
            graph = deepcopy(base)
            graph.update(id=str(index), name=name)
            graph['definition']['name'] = name
            graph['settings'].update(groups=[], families=[], live_update=False)
            project['graphs'].append(graph)
        project['selected_graph'] = '0'
        for name in ('tensile_workbench_defaults.json', 'tensile_workbench.project.json'):
            (root / name).write_text(json.dumps(project))
        (root / 'data').mkdir()
        with redirect_stdout(io.StringIO()):
            return TensileWorkbench(root, data_dir=root / 'data', output_dir=root / 'output')

    def test_drafts_follow_named_graphs_and_create_action_is_always_last(self):
        app = self.make_app()
        before = deepcopy(app.store.data['graphs'])
        self.assertEqual(app.graph.options, (('Baseline', '0'), ('Annealed', '2'),
                                           ('Untitled graph (draft)', '1'), ('＋ Create new graph…', NEW_GRAPH_ACTION)))
        self.assertEqual(app.store.data['graphs'], before)
        self.assertEqual(app.graph.value, '0')

    def test_create_action_creates_once_and_is_never_saved_as_a_graph_id(self):
        app = self.make_app()
        app.graph.value = NEW_GRAPH_ACTION
        self.assertEqual(len(app.store.data['graphs']), 4)
        self.assertNotEqual(app.graph.value, NEW_GRAPH_ACTION)
        self.assertEqual(app.graph.options[-1][1], NEW_GRAPH_ACTION)
        self.assertEqual(app.store.data['selected_graph'], app.graph.value)
        self.assertNotIn(NEW_GRAPH_ACTION, [g['id'] for g in app.store.data['graphs']])
        app.name.value = 'Tempered'
        self.assertEqual(app.graph.options[-1][1], NEW_GRAPH_ACTION)
        self.assertIn(('Tempered', app.graph.value), app.graph.options)
        saved = json.loads(app.store.path.read_text())
        self.assertEqual(saved['graphs'][-1]['name'], 'Tempered')

    def test_failed_creation_restores_real_selection_and_preserves_graphs(self):
        app = self.make_app()
        app.save_current()
        before = app.store.path.read_bytes()
        with patch.object(app.store, 'add_graph', side_effect=RuntimeError('synthetic conflict')):
            app.graph.value = NEW_GRAPH_ACTION
        self.assertEqual(app.graph.value, '0')
        self.assertEqual(app.store.path.read_bytes(), before)
        self.assertIn('Could not create graph', app.save_status.value)

    def test_switching_named_graph_and_refresh_do_not_select_create_action(self):
        app = self.make_app()
        app.graph.value = '2'
        self.assertEqual(app.store.data['selected_graph'], '2')
        before = app.store.path.read_bytes()
        app._refresh_graph_options()
        self.assertEqual(app.graph.value, '2')
        self.assertEqual(app.store.path.read_bytes(), before)

    def test_properties_fold_contains_tables_and_buttons_without_recalculation(self):
        app = self.make_app()
        self.assertFalse(hasattr(app, 'range_button'))
        self.assertFalse(hasattr(app, 'range_from'))
        self.assertEqual(app.controls['renderer'].options[0], ('Static plots', 'static'))
        self.assertIsNone(app.properties_panel.selected_index)
        content = app.properties_panel.children[0]
        self.assertIn(app.tables.ui, content.children)
        self.assertIn(app.table_export_button, content.children[1].children)
        with patch.object(app, '_refresh_properties') as calculate:
            app.properties_panel.selected_index = 0
            app.properties_panel.selected_index = None
        calculate.assert_not_called()

    def test_advanced_notebook_mode_is_still_available(self):
        with patch.object(launch_workbench.subprocess, 'call', return_value=0) as call, redirect_stdout(io.StringIO()):
            self.assertEqual(launch_workbench.main(['--notebook', '--no-browser']), 0)
        command = call.call_args.args[0]
        self.assertIn('jupyterlab', command)
        self.assertIn(str(ROOT / 'tensile_workbench.ipynb'), command)
        self.assertIn('--no-browser', command)
        self.assertNotIn('--notebook', command)


if __name__ == '__main__':
    unittest.main()
