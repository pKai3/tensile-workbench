"""Work-count and data-integrity checks; no machine-dependent timing limits."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import ipywidgets as w
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from selection_fixture import make_fixture
from tensile_display import PREVIEW_POINTS, preview_indices
from tensile_plotly import PlotlyView, figure_to_plotly
from tensile_properties import specimen_calculation
from tensile_workbench import PreviewSession, TensileWorkbench


class DisplaySubsetTests(unittest.TestCase):
    def test_dense_line_keeps_original_readings_endpoints_and_gaps(self):
        x = np.arange(200_000, dtype=float)
        y = np.sin(x / 1000)
        y[12_345:12_351] = np.nan
        x[55_555] = np.nan
        before_x, before_y = x.copy(), y.copy()
        ids = preview_indices(x, y)
        self.assertLessEqual(len(ids), PREVIEW_POINTS + 10)
        self.assertEqual((ids[0], ids[-1]), (0, len(x) - 1))
        self.assertTrue(np.all(np.diff(ids) > 0))
        self.assertTrue({12_344, 12_345, 12_350, 12_351, 55_554, 55_555, 55_556} <= set(ids))
        np.testing.assert_array_equal(x, before_x)
        np.testing.assert_array_equal(y, before_y)

    def test_interactive_subset_does_not_change_export_artists_or_property_markers(self):
        fig, ax = plt.subplots()
        self.addCleanup(plt.close, fig)
        x = np.linspace(0, 20, 200_000)
        y = np.sin(x) * 100 + 500
        line, = ax.plot(x, y, label='Dense specimen')
        bars = ax.errorbar([x[10_003]], [y[10_003]], yerr=[5], fmt='o')
        bars.lines[0].set_label('Property')
        chart = figure_to_plotly(fig)
        dense = next(t for t in chart.data if t.name == 'Dense specimen')
        prop = next(t for t in chart.data if t.name == 'Property')
        ids = preview_indices(x, y)
        np.testing.assert_array_equal(dense.x, x[ids])
        np.testing.assert_array_equal(dense.y, y[ids])
        np.testing.assert_array_equal(prop.x, [x[10_003]])
        np.testing.assert_array_equal(prop.error_y.array, [5])
        np.testing.assert_array_equal(line.get_xdata(), x)
        np.testing.assert_array_equal(line.get_ydata(), y)
        self.assertLess(len(chart.to_json()), 300_000)

    def test_gallery_creates_only_visible_or_explicitly_opened_charts(self):
        fig, ax = plt.subplots()
        self.addCleanup(plt.close, fig)
        ax.plot([0, 1], [0, 1], label='Synthetic')
        view = PlotlyView(w, w.Dropdown(options=[1, 2], value=1), w.IntSlider(value=640, max=1200))
        self.addCleanup(view.clear)
        items = [{'key': str(i), 'label': f'Synthetic {i}', 'result': {'figure': fig}} for i in range(3)]
        with patch('tensile_plotly.figure_to_plotly', wraps=figure_to_plotly) as convert:
            view.set_items(items)
            convert.assert_not_called()
            old_frame = view._frames['0']
            old_frame.children[0].visible = True
            self.assertEqual(list(view._charts), ['0'])
            view.open_focus('2')
            self.assertEqual(set(view._charts), {'0', '2'})
            view.close_focus()
            view.open_focus('2')
            self.assertEqual(convert.call_count, 2)
            view.set_items(items)
            self.assertFalse(view._ensure_chart('0', old_frame))
            self.assertEqual(convert.call_count, 2)


class IncrementalCalculationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='tensile-incremental-synthetic-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.project = make_fixture(self.root)
        shutil.copytree(self.root / 'data' / 'Alloy A', self.root / 'data' / 'Alloy B')
        self.session = PreviewSession(self.root, self.project)
        self.state = self.session.defaults()
        self.spec = self.session.graphs[0]
        self.other = {**self.state, 'groups': ['Alloy B']}
        self.frames_a = self.session.property_tables(self.state, self.spec)
        self.frames_b = self.session.property_tables(self.other, self.spec)

    def fit_project(self):
        project = deepcopy(self.session.project)
        record = self.session._load('Alloy A')[0]
        project.setdefault('specimen_fit_overrides', {})[record['specimen_id']] = {
            'mode': 'line', 'strain_bounds': [.15, .35], 'endpoints': [[.15, 150.], [.35, 350.]],
            'source_sha256': record['source_sha256'], 'reason': 'Synthetic fit',
            'saved_at': '2026-11-04T00:00:00+00:00', 'automatic_snapshot': {}}
        return project, record

    def test_one_fit_edit_recalculates_only_that_specimen_and_keeps_other_group_plots(self):
        result_b = self.session.render({**self.other, 'family': 'landmark', 'show_individuals': False})
        project, record = self.fit_project()
        with patch('tensile_properties.specimen_calculation', wraps=specimen_calculation) as calculate:
            self.session.set_project(project)
            after = self.session.property_tables(self.state, self.spec)
            other = self.session.property_tables(self.other, self.spec)
            self.assertGreater(calculate.call_count, 0)
            self.assertEqual({call.args[0]['specimen_id'] for call in calculate.call_args_list}, {record['specimen_id']})
        pd.testing.assert_frame_equal(other['tensile_samples'], self.frames_b['tensile_samples'])
        rows = after['tensile_samples'].set_index('Specimen ID')
        self.assertAlmostEqual(rows.loc[record['specimen_id'], 'Fitted E (GPa)'], 100.)
        with patch.object(self.session.engine, 'prepare_average_curves', side_effect=AssertionError('Unrelated model rebuilt')):
            again = self.session.render({**self.other, 'family': 'landmark', 'show_individuals': False})
        self.assertIs(again['figure'], result_b['figure'])

    def test_one_failure_edit_refreshes_elongation_without_refitting_other_specimens(self):
        project = deepcopy(self.session.project)
        record = self.session._load('Alloy A')[0]
        project.setdefault('specimen_failure_overrides', {})[record['specimen_id']] = {
            'row': 1800, 'source_sha256': record['source_sha256'], 'reason': 'Synthetic endpoint',
            'saved_at': '2026-11-04T00:00:00+00:00', 'automatic_snapshot': {}}
        with patch('tensile_properties.specimen_calculation', wraps=specimen_calculation) as calculate:
            self.session.set_project(project)
            after = self.session.property_tables(self.state, self.spec)
            self.assertEqual({call.args[0]['specimen_id'] for call in calculate.call_args_list}, {record['specimen_id']})
        row = after['tensile_samples'].set_index('Specimen ID').loc[record['specimen_id']]
        self.assertAlmostEqual(row['Failure Elongation (%)'], record['_acquisition']['strain'][1799])

    def test_title_changes_reuse_numeric_models(self):
        self.session.render({**self.state, 'family': 'landmark'})
        project = deepcopy(self.session.project)
        project['graphs'][0]['definition'].setdefault('workbench_titles', {})['landmark'] = 'New title'
        self.session.set_project(project)
        with patch.object(self.session.engine, 'prepare_average_curves', side_effect=AssertionError('Title recalculated model')):
            after = self.session.render({**self.state, 'family': 'landmark'})
        self.assertEqual(after['figure'].axes[0].get_title(), 'New title')

    def test_presentation_edits_leave_tables_and_active_inspector_alone(self):
        with redirect_stdout(io.StringIO()):
            app = TensileWorkbench(self.root, data_dir=self.root / 'data', output_dir=self.root / 'output')
        self.addCleanup(app.tables.inspector.clear)
        context = app.tables.specimens.context
        with patch.object(app.tables, 'set_frames', side_effect=AssertionError('Presentation rebuilt table')):
            app.title_inputs['landmark'].value = 'Preview title'
            app.axes['tensile_xlim'][0].value = False
            app.axes['tensile_xlim'][2].value = 35
            app.family_boxes['landmark'].value = True
        self.assertEqual(app.tables.specimens.context, context)
        # Numerical changes still refresh the displayed values.
        with patch.object(app.tables, 'set_frames', wraps=app.tables.set_frames) as render:
            app._specimen_changed('Alloy A/coupon_1.csv', False, 'Synthetic exclusion')
            self.assertGreater(render.call_count, 0)
        self.assertFalse(app.tables.frames['tensile_samples'].set_index('Specimen ID').loc[
            'Alloy A/coupon_1.csv', 'Included'])


if __name__ == '__main__':
    unittest.main()
