"""Categorical dual-axis view; synthetic temporary data only."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from selection_fixture import make_fixture
from tensile_group_plot import GROUP_FAMILY, ordered_groups
from tensile_plotly import figure_to_plotly, resize_chart
from tensile_workbench import TensileWorkbench


class GroupPropertiesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='group-properties-synthetic-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        make_fixture(self.root)
        for group in ('Heat treated', 'Alloy Z'):
            shutil.copytree(self.root / 'data' / 'Alloy A', self.root / 'data' / group)
        with redirect_stdout(io.StringIO()):
            self.app = TensileWorkbench(self.root)
        self.session = self.app.session

    def state(self, **kwargs):
        return {**self.app.state(), 'graph_index': 0, 'family': GROUP_FAMILY,
                'groups': ['Alloy A', 'Alloy Z', 'Heat treated'],
                'properties_by_group_order': ['Heat treated', 'Alloy Z', 'Alloy A'], **kwargs}

    @staticmethod
    def means(result):
        return {line.get_label(): line for ax in result['figure'].axes for line in ax.lines
                if not line.get_label().startswith('_')}

    def test_means_axes_and_individuals_use_shared_properties_without_curve_fit(self):
        with patch.object(self.session.engine, 'prepare_average_curves', side_effect=AssertionError('Not needed')):
            without = self.session.render(self.state(show_individuals=False))
            individuals = self.session.render(self.state(show_individuals=True))
        means = self.means(without)
        self.assertEqual(set(means), {'0.2% YS', 'UTS', 'EL'})
        left, right = without['figure'].axes
        self.assertEqual(left.get_ylabel(), 'Strength (MPa)')
        self.assertEqual(right.get_ylabel(), 'Elongation at failure (%)')
        self.assertEqual([t.get_text() for t in left.get_xticklabels()], ['Heat treated', 'Alloy Z', 'Alloy A'])
        properties = [self.session.engine.specimen_properties(r)
                      for r in without['export_records']['Alloy A']]
        for label, field in (('0.2% YS', 'Yield (MPa)'), ('UTS', 'UTS (MPa)'), ('EL', 'Failure elongation (%)')):
            np.testing.assert_allclose(means[label].get_ydata(), np.mean([p[field] for p in properties]))
            self.assertEqual(means[label]._tensile_counts, [3, 3, 3])
        for first, second in zip(without['figure'].axes, individuals['figure'].axes):
            np.testing.assert_allclose(first.get_xlim(), second.get_xlim())
            np.testing.assert_allclose(first.get_ylim(), second.get_ylim())
            self.assertFalse(any(hasattr(line, '_tensile_hover_label') for line in first.lines))
        self.assertEqual(sum(hasattr(line, '_tensile_hover_label') for ax in individuals['figure'].axes for line in ax.lines), 27)
        self.assertFalse((self.root / 'output').exists())

    def test_missing_metric_leaves_gap_and_exclusions_apply_to_all_properties(self):
        original = self.session.engine.specimen_properties
        def missing_yield(record, *args):
            p = original(record, *args)
            if record['specimen_id'].startswith('Alloy Z/'):
                p['Yield (MPa)'] = np.nan
            return p
        self.app._specimen_changed('Alloy A/coupon_2.csv', False, 'synthetic exclusion')
        with patch.object(self.session.engine, 'specimen_properties', side_effect=missing_yield):
            result = self.session.render(self.state(show_individuals=True))
        means = self.means(result)
        self.assertTrue(np.isnan(means['0.2% YS'].get_ydata()[1]))
        self.assertEqual(means['0.2% YS']._tensile_counts, [3, 0, 2])
        self.assertEqual(means['UTS']._tensile_counts, [3, 3, 2])
        self.assertEqual(means['EL']._tensile_counts, [3, 3, 2])
        self.assertTrue(all(np.isfinite(means['EL'].get_ydata())))

    def test_plotly_categorical_labels_secondary_axis_errors_and_identity(self):
        result = self.session.render(self.state(show_individuals=True,
            properties_by_group_ylim=[0, 950], properties_by_group_el_ylim=[0, 30],
            properties_by_group_el_color='#aa2244'))
        chart = figure_to_plotly(result['figure'])
        means = {trace.meta['legend_label']: trace for trace in chart.data if trace.showlegend}
        self.assertEqual(len(chart.data), 30)
        self.assertEqual(chart.layout.yaxis.range, (0, 950))
        self.assertEqual(chart.layout.yaxis2.range, (0, 30))
        self.assertEqual(chart.layout.yaxis2.overlaying, 'y')
        self.assertEqual(chart.layout.yaxis2.side, 'right')
        self.assertEqual(chart.layout.xaxis.ticktext, ('Heat treated', 'Alloy Z', 'Alloy A'))
        self.assertEqual(means['EL'].yaxis, 'y2')
        self.assertEqual(means['EL'].marker.color, '#aa2244')
        self.assertEqual(means['EL'].customdata[0][1], 3)
        self.assertTrue(all(trace.mode == 'lines+markers' for trace in means.values()))
        self.assertTrue(all(trace.line.dash == 'solid' for trace in means.values()))
        self.assertTrue(all(trace.error_y.array[0] > 0 for trace in means.values()))
        self.assertEqual(len({trace.legendgroup for trace in chart.data}), 3)
        self.assertTrue(any('coupon_1' in trace.hovertemplate for trace in chart.data))
        resize_chart(chart, 450)
        self.assertGreaterEqual(chart.layout.margin.r, 85)
        self.assertFalse(means['EL'].connectgaps)

    def test_order_controls_save_reopen_and_do_not_reorder_other_plots(self):
        self.app.controls['groups'].value = ('Alloy A', 'Alloy Z', 'Heat treated')
        self.app.family_boxes[GROUP_FAMILY].value = True
        self.app.group_order_select.value = 'Heat treated'
        self.app._move_group_order(-1)
        self.app._move_group_order(-1)
        self.app.controls['properties_by_group_error_bars'].value = False
        self.app.title_inputs[GROUP_FAMILY].value = 'Comparison'
        auto, lo, hi, _ = self.app.axes['properties_by_group_el_ylim']
        lo.value, hi.value, auto.value = 0, 40, False
        self.assertEqual(self.app.state()['properties_by_group_order'], ['Heat treated', 'Alloy A', 'Alloy Z'])
        self.assertEqual(self.app.state()['groups'], ['Alloy A', 'Alloy Z', 'Heat treated'])
        with redirect_stdout(io.StringIO()):
            reopened = TensileWorkbench(self.root)
        self.assertEqual(list(reopened.group_order_select.options), ['Heat treated', 'Alloy A', 'Alloy Z'])
        self.assertFalse(reopened.state()['properties_by_group_error_bars'])
        self.assertEqual(reopened.state()['properties_by_group_el_ylim'], [0, 40])
        self.assertEqual(reopened.title_inputs[GROUP_FAMILY].value, 'Comparison')
        reopened.controls['groups'].value = ('Alloy A', 'Alloy Z')
        reopened.controls['groups'].value = ('Alloy A', 'Alloy Z', 'Heat treated')
        self.assertEqual(list(reopened.group_order_select.options), ['Heat treated', 'Alloy A', 'Alloy Z'])
        reopened._apply_graph('1')
        self.assertEqual(reopened.state()['properties_by_group_order'], ['Alloy A'])
        reopened._apply_graph('0')
        self.assertEqual(reopened.state()['properties_by_group_order'], ['Heat treated', 'Alloy A', 'Alloy Z'])

    def test_new_groups_append_without_losing_saved_order_and_empty_groups_leave_gaps(self):
        self.assertEqual(ordered_groups(['A', 'C', 'B'], ['B', 'hidden', 'A']), ['B', 'A', 'C'])
        self.app.controls['groups'].value = ('Alloy A', 'Alloy Z')
        for specimen in (1, 2, 3):
            self.app._specimen_changed(f'Alloy Z/coupon_{specimen}.csv', False, 'synthetic exclusion')
        result = self.session.render(self.state(groups=['Alloy A', 'Alloy Z'], properties_by_group_order=['Alloy Z', 'Alloy A']))
        for line in self.means(result).values():
            self.assertTrue(np.isnan(line.get_ydata()[0]))
            self.assertEqual(line._tensile_counts, [0, 3])

    def test_export_variants_and_no_unselected_curves(self):
        results = [self.session.render(self.state(show_individuals=show)) for show in (False, True)]
        with patch.object(self.session.engine, 'PLOT_DPI', 40):
            folder = self.session.export(results, include_tables=True)
        names = [path.name for path in folder.iterdir()]
        self.assertTrue(any('10_properties_by_group_with_individuals.png' in name for name in names))
        self.assertTrue(any('10_properties_by_group_without_individuals.png' in name for name in names))
        self.assertTrue(any(name.endswith('_results.xlsx') for name in names))
        self.assertFalse(any(name.endswith('_curves.xlsx') for name in names))

    def test_group_gauge_policies_change_only_the_elongation_series(self):
        raw = self.session.render(self.state())
        project = deepcopy(self.session.project)
        project['graphs'][0]['definition']['gauge_reconstruction'] = {
            'Alloy A': {'enabled': True, 'target_gauge_mm': 25},
            'Heat treated': {'enabled': True, 'target_gauge_mm': 40}}
        self.session.set_project(project)
        original = self.session.instron.match
        def reference_with_gauge(group, record):
            reference = original(group, record)
            return {**reference, 'values': {**reference.get('values', {}), 'gauge': 50}}
        with patch.object(self.session.instron, 'match', side_effect=reference_with_gauge):
            reconstructed = self.session.render(self.state())
        before, after = self.means(raw), self.means(reconstructed)
        for metric in ('0.2% YS', 'UTS'):
            np.testing.assert_allclose(before[metric].get_ydata(), after[metric].get_ydata())
        for index, group, ratio in ((0, 'Heat treated', 1.25), (1, 'Alloy Z', 1), (2, 'Alloy A', 2)):
            expected = []
            for record in raw['export_records'][group]:
                original_record = record['_measured_record']
                meta = original_record['_acquisition']
                eu = meta['strain'][meta['peak']]
                ef = self.session.engine.specimen_properties(record)['Failure elongation (%)']
                expected.append(eu + ratio * (ef - eu))
            self.assertAlmostEqual(after['EL'].get_ydata()[index], np.mean(expected))

    def test_unrelated_filters_do_not_recompute_and_existing_single_axis_plotly_works(self):
        first = self.session.render(self.state())
        second = self.session.render(self.state(modulus_gpa=70, smooth=False, landmark_points=800))
        self.assertIs(first['figure'], second['figure'])
        scatter = self.session.render(self.state(family='uts_vs_el'))
        chart = figure_to_plotly(scatter['figure'])
        self.assertNotIn('yaxis2', chart.layout)


if __name__ == '__main__':
    unittest.main()
