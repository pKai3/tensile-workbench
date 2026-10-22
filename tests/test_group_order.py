"""Saved presentation order with synthetic data only; no research exports."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import matplotlib
matplotlib.use('Agg')
import numpy as np
import pandas as pd
import ipywidgets as widgets

from selection_fixture import make_fixture
from test_relative_comparison import frames as comparison_frames
from tensile_comparison import ComparisonView
from tensile_exports import export_results
from tensile_moves import forget_group, references, graph_blocks
from tensile_order import ordered_groups, sort_group_frame
from tensile_plotly import figure_to_plotly
from tensile_workbench import TensileWorkbench
from workbench_project import validate_project


class GroupOrderTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='group-order-synthetic-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        make_fixture(self.root)
        for group in ('Batch/Alloy Z', 'Reference/Control'):
            shutil.copytree(self.root / 'data/Alloy A', self.root / 'data' / group)
        with redirect_stdout(io.StringIO()):
            self.app = TensileWorkbench(self.root)
            self.app.controls['groups'].value = ('Alloy A', 'Batch/Alloy Z', 'Reference/Control')
        self.session = self.app.session
        self.order = ['Reference/Control', 'Alloy A', 'Batch/Alloy Z']
        self.addCleanup(self.session.engine.plt.close, 'all')

    def state(self, **kwargs):
        return {**self.app.state(), 'graph_index': 0, 'family': 'landmark',
                'group_order': self.order, **kwargs}

    def test_order_panel_is_below_selector_and_above_tables_not_in_colours(self):
        app = self.app
        children = list(app.analysis_ui.children)
        panel = app.display_order_panel
        self.assertEqual(children.index(panel), children.index(app.group_picker.ui) + 2)
        self.assertLess(children.index(panel), children.index(app.properties_panel))
        self.assertIsNone(panel.selected_index)
        self.assertEqual(panel.get_title(0), 'Sample group order · tables and plots')
        self.assertIn(app.display_order_select, panel.children[0].children)
        colours = next(child for child in children if isinstance(child, widgets.Accordion)
                       and child.get_title(0).startswith('Labels and colours'))
        def contains(root, target):
            return root is target or any(contains(child, target) for child in getattr(root, 'children', ()))
        self.assertFalse(contains(colours, app.display_order_select))
        self.assertTrue(contains(colours, app.controls['color_palette']))
        self.assertFalse(hasattr(app, 'group_order_select'))
        self.assertFalse(contains(app.plot_settings['properties_by_group'], app.display_order_select))

    def test_obsolete_order_is_ignored_and_removed_on_load_and_save(self):
        for shared in (None, [], self.order[::-1]):
            with self.subTest(shared=shared), redirect_stdout(io.StringIO()):
                project = deepcopy(self.app.store.data)
                for graph in graph_blocks(project):
                    graph['settings']['properties_by_group_order'] = self.order
                settings = project['graphs'][0]['settings']
                settings.pop('group_order', None)
                if shared is not None:
                    settings['group_order'] = shared
                self.app.store.path.write_text(json.dumps(project))
                self.app.store.reload()
                self.assertTrue(all('properties_by_group_order' not in g['settings']
                                    for g in graph_blocks(self.app.store.data)))
                self.session.set_project(self.app.store.data)
                self.app._apply_graph('0')
                expected = shared if shared else sorted(self.order)
                self.assertEqual(self.app.state()['group_order'], expected)
                self.assertNotIn('properties_by_group_order', self.app.state())
                self.assertTrue(self.app.save_current())
                self.app.store.save(self.app.store.data)
                self.assertEqual(self.app._current()['settings']['group_order'], expected)
                saved = json.loads(self.app.store.path.read_text())
                self.assertTrue(all('properties_by_group_order' not in g['settings'] for g in graph_blocks(saved)))
                reopened = TensileWorkbench(self.root)
                self.assertEqual(reopened.state()['group_order'], expected)

    def test_triple_plot_uses_shared_order_and_invalidates_its_cached_figure(self):
        before_state = self.state(family='properties_by_group', group_order=self.order[::-1])
        after_state = self.state(family='properties_by_group', properties_by_group_order=self.order[::-1])
        with redirect_stdout(io.StringIO()):
            before = self.session.render(before_state)
            after = self.session.render(after_state)
            obsolete_only = self.session.render({**after_state, 'group_order': []})
        self.assertIsNot(before['figure'], after['figure'])
        expected = [self.session.engine.get_display_name(g) for g in self.order]
        chart = figure_to_plotly(after['figure'])
        self.assertEqual(list(chart.layout.xaxis.ticktext), expected)
        self.assertEqual([line.get_text() for line in after['figure'].axes[0].get_xticklabels()], expected)
        self.assertEqual([t.name for t in chart.data if t.showlegend], ['0.2% YS', 'UTS', 'EL'])
        self.assertNotIn('properties_by_group_order', after['state'])
        alphabetical = [self.session.engine.get_display_name(g) for g in sorted(self.order)]
        self.assertEqual(list(figure_to_plotly(obsolete_only['figure']).layout.xaxis.ticktext), alphabetical)
        for first_axis, second_axis in zip(before['figure'].axes, after['figure'].axes):
            first = [line for line in first_axis.lines if not line.get_label().startswith('_')]
            second = [line for line in second_axis.lines if not line.get_label().startswith('_')]
            for old, new in zip(first, second):
                np.testing.assert_array_equal(old.get_ydata()[::-1], new.get_ydata())
                self.assertEqual(old.get_color(), new.get_color())

    def test_controls_save_restore_hidden_groups_graph_scope_and_colours(self):
        colors = self.session.color_map(self.app.state(), {})
        self.app.display_order_select.value = 'Reference/Control'
        with redirect_stdout(io.StringIO()):
            self.app.display_order_up.click()
            self.app.display_order_up.click()
        self.assertEqual(self.app.state()['group_order'], self.order)
        self.assertTrue(self.app.display_order_up.disabled)
        self.assertFalse(self.app.display_order_down.disabled)
        self.assertEqual(self.app.controls['groups'].value,
                         ('Alloy A', 'Batch/Alloy Z', 'Reference/Control'))
        self.assertEqual(self.session.color_map(self.app.state(), {}), colors)
        with redirect_stdout(io.StringIO()):
            reopened = TensileWorkbench(self.root)
            reopened.controls['groups'].value = ('Alloy A',)
            reopened.controls['groups'].value = ('Alloy A', 'Batch/Alloy Z', 'Reference/Control')
        self.assertEqual(list(reopened.display_order_select.options), self.order)
        self.assertEqual(reopened.state()['group_order'], self.order)
        reopened._apply_graph('1')
        self.assertEqual(reopened.state()['group_order'], ['Alloy A'])
        reopened._apply_graph('0')
        self.assertEqual(reopened.state()['group_order'], self.order)

    def test_table_and_export_frames_use_order_without_recalculation_or_value_changes(self):
        before = self.session.property_tables(self.state(group_order=[]), {})
        with patch('tensile_workbench.property_tables', side_effect=AssertionError('Recalculated')):
            after = self.session.property_tables(self.state(), {})
        for name, frame in after.items():
            if not frame.empty and 'Group' in frame:
                self.assertEqual(frame['Group'].drop_duplicates().tolist(), self.order)
                pd.testing.assert_frame_equal(frame.sort_index(), before[name].sort_index())
        with patch('tensile_exports.write_workbook') as writer:
            export_results(after, self.root / 'not-written.xlsx', {})
        for sheet in writer.call_args.args[1].values():
            if not sheet.empty and 'Group' in sheet:
                actual = sheet['Group'].drop_duplicates().tolist()
                self.assertEqual(actual, [g for g in self.order if g in actual])
        table = self.app.tables
        table.set_frames(after, group_order=self.order)
        self.assertEqual([row['group'] for row in table.specimens.rows][::3], self.order)
        summary = table.panels[0].value
        self.assertLess(summary.index('Reference/Control'), summary.index('Alloy A'))
        table.descending.value = True
        self.assertEqual(table._filtered(after['tensile_summary_details'])['Group'].unique().tolist(), self.order[::-1])
        table.sort.value = 'UTS (MPa)'
        self.assertTrue(table._filtered(after['tensile_samples'])['UTS (MPa)'].is_monotonic_decreasing)
        table.descending.value = False
        table.sort.value = 'Group'
        table.filter.value = 'Alloy'
        self.assertEqual(table._filtered(after['tensile_summary_details'])['Group'].unique().tolist(), self.order[1:])

    def test_all_group_legend_families_static_plotly_and_variants_keep_numbers_and_colours(self):
        families = ('landmark', 'pointwise', 'comparison', 'representative', 'work_hardening',
                    'work_hardening_landmark', 'work_hardening_comparison', 'ys_vs_el', 'uts_vs_el')
        for family in families:
            for show in (False, True):
                with self.subTest(family=family, show=show), redirect_stdout(io.StringIO()):
                    state = self.state(family=family, show_individuals=show)
                    before = self.session.render({**state, 'group_order': []})['figure']
                    after = self.session.render(state)['figure']
                    expected = [self.session.engine.get_display_name(g) for g in self.order]
                    def group_of(label):
                        return next(g for g in expected if label == g or label.startswith(g + ' '))
                    labels = [text.get_text() for text in after.axes[0].get_legend().get_texts()]
                    actual = [group_of(label) for label in labels]
                    self.assertEqual(actual, [g for g in expected for _ in range(2)]
                                     if family == 'work_hardening_comparison' else expected)
                    traces = [t for t in figure_to_plotly(after).data if t.showlegend]
                    traces.sort(key=lambda trace: trace.legendrank)
                    self.assertEqual([group_of(t.name) for t in traces], actual)
                    def curves(fig):
                        return {line.get_label(): line for line in fig.axes[0].lines
                                if not line.get_label().startswith('_')}
                    old, new = curves(before), curves(after)
                    self.assertEqual(set(old), set(new))
                    for label in old:
                        np.testing.assert_array_equal(old[label].get_xdata(), new[label].get_xdata())
                        np.testing.assert_array_equal(old[label].get_ydata(), new[label].get_ydata())
                        self.assertEqual(old[label].get_color(), new[label].get_color())
        self.assertFalse((self.root / 'output').exists())

    def test_old_definitions_and_invalid_saved_order(self):
        project = deepcopy(self.app.store.data)
        project['graphs'][0]['settings'].pop('group_order', None)
        validate_project(project)
        for invalid in (None, 'Alloy', ['A', 'A'], [''], [1]):
            project['graphs'][0]['settings']['group_order'] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_project(project)
        self.assertEqual(ordered_groups(['A', 'B', 'C'], ['B', 'Missing']), ['B', 'A', 'C'])
        project['graphs'][0]['settings']['group_order'] = ['Missing', 'Alloy A']
        self.assertIn('Missing', references(project)[0])
        forgotten = forget_group(project, 'Missing')
        self.assertEqual(forgotten['graphs'][0]['settings']['group_order'], ['Alloy A'])

    def test_comparison_and_sd_tables_follow_group_order(self):
        view = ComparisonView(widgets)
        self.addCleanup(view.clear)
        view.set_frames(comparison_frames(), ['B', 'A'])
        self.assertEqual(view.summary['Group'].unique().tolist(), ['B', 'A'])
        view.ui.selected_index = 0
        for chart in view.charts.values():
            self.assertEqual(list(chart.layout.xaxis.tickvals), ['B', 'A'])
        view.set_frames(comparison_frames(), ['A', 'B'])
        self.assertEqual(view.summary['Group'].unique().tolist(), ['A', 'B'])


if __name__ == '__main__':
    unittest.main()
