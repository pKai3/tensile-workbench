"""Display-only population checks with synthetic in-memory curves."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

import tensile_core as core
from tensile_plotly import figure_to_plotly
from tensile_group_review import GroupCurveReview


def synthetic_landmark(shape=2, ys=3, uts=3, el=2, uniform=2):
    counts = {'Yield (MPa)': ys, 'Yield strain (%)': ys, 'UTS (MPa)': uts,
              'Uniform elongation (%)': uniform, 'Failure elongation (%)': el,
              'Pre-break stress (MPa)': shape}
    points = []
    for name, x, y, xkey, ykey, marker in (
        ('yield', .7, 600., 'Yield strain (%)', 'Yield (MPa)', 'o'),
        ('UTS', 6., 800., 'Uniform elongation (%)', 'UTS (MPa)', '^'),
        ('failure', 18., 450., 'Failure elongation (%)', 'Pre-break stress (MPa)', 'x'),
    ):
        points.append(dict(name=name, x=x, y=y, x_n=counts[xkey], y_n=counts[ykey],
                           x_sd=.1 if counts[xkey] > 1 else np.nan,
                           y_sd=10. if counts[ykey] > 1 else np.nan,
                           marker=marker, marker_size=5))
    return {'n': shape, 'shape_n': shape, 'property_counts': counts,
            'point_statistics': points, 'x': np.array([0., .7, 6., 18.]),
            'y': np.array([0., 600., 800., 450.]), 'knots': np.array([0., .7, 6., 18.])}


class LandmarkCountTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='landmark-counts-synthetic-')
        self.addCleanup(temp.cleanup)
        self.output = Path(temp.name) / 'not-written.png'
        self.addCleanup(plt.close, 'all')

    def render(self, landmark, family='landmark', show=False, bars=True):
        pointwise = dict(measured_x=landmark['x'].copy(), measured_y=landmark['y'].copy(),
                         predicted_x=np.array([]), predicted_y=np.array([]),
                         x=landmark['x'].copy(), y=landmark['y'].copy())
        models = {'Alloy': {'pointwise': pointwise, 'landmark': landmark}}
        records = {'Alloy': [dict(strain_pct=landmark['x'].copy(), stress_mpa=landmark['y'].copy(),
                                  sample=f'coupon_{i}', source_file=f'/synthetic/coupon_{i}.csv')
                             for i in range(landmark['shape_n'])]}
        with redirect_stdout(io.StringIO()):
            figure = core.render_average_plot(models, records, self.output, family, show,
                {'Alloy': '#336699'}, None, None, 'Synthetic counts',
                name_overrides={'Alloy': 'Custom name'}, landmark_error_bars=bars, preview=True)
        self.assertFalse(self.output.exists())
        return figure

    def test_common_count_is_compact_in_static_and_plotly(self):
        landmark = synthetic_landmark(shape=8, ys=8, uts=8, el=8, uniform=8)
        self.assertEqual(core.landmark_population_suffix(landmark), '(n=8)')
        for show in (False, True):
            figure = self.render(landmark, show=show)
            self.assertEqual(figure.axes[0].get_legend_handles_labels()[1], ['Custom name (n=8)'])
            chart = figure_to_plotly(figure)
            legend = [trace for trace in chart.data if trace.showlegend]
            self.assertEqual([trace.meta['legend_label'] for trace in legend], ['Custom name (n=8)'])

    def test_split_counts_for_both_variants_and_comparison_without_geometry_changes(self):
        landmark = synthetic_landmark(shape=6, ys=8, uts=8, el=7, uniform=8)
        before = deepcopy(landmark)
        suffix = '(shape n=6; YS/UTS/EL n=8/8/7)'
        for family in ('landmark', 'comparison'):
            for show in (False, True):
                figure = self.render(landmark, family=family, show=show)
                self.assertEqual(figure.axes[0].get_legend_handles_labels()[1], ['Custom name ' + suffix])
                chart = figure_to_plotly(figure)
                self.assertEqual([trace.meta['legend_label'] for trace in chart.data if trace.showlegend],
                                 ['Custom name ' + suffix])
                count = sum(hasattr(line, '_tensile_hover_label') for line in figure.axes[0].lines)
                self.assertEqual(count, 6 if show else 0)
        np.testing.assert_array_equal(landmark['x'], before['x'])
        np.testing.assert_array_equal(landmark['y'], before['y'])
        self.assertEqual(landmark['point_statistics'], before['point_statistics'])
        self.assertEqual(landmark['property_counts'], before['property_counts'])

    def test_pointwise_only_retains_its_shape_count(self):
        figure = self.render(synthetic_landmark(), family='pointwise')
        self.assertEqual(figure.axes[0].get_legend_handles_labels()[1], ['Custom name (n=2)'])

    def test_coordinate_hover_with_and_without_sd_bars_including_singletons(self):
        for landmark in (synthetic_landmark(shape=2, ys=3, uts=3, el=3),
                         synthetic_landmark(shape=1, ys=2, uts=2, el=1, uniform=1)):
            for bars in (False, True):
                figure = self.render(landmark, bars=bars)
                chart = figure_to_plotly(figure)
                markers = [trace for trace in chart.data if trace.customdata is not None]
                self.assertEqual(len(markers), 3)
                for point, trace in zip(landmark['point_statistics'], markers):
                    self.assertEqual(list(trace.customdata[0]), [point['x_n'], point['y_n']])
                    self.assertIn('Strain n=%{customdata[0]}', trace.hovertemplate)
                    self.assertIn('Stress n=%{customdata[1]}', trace.hovertemplate)
                    self.assertEqual(list(trace.x), [point['x']])
                    self.assertEqual(list(trace.y), [point['y']])
                    if bars and np.isfinite(point['x_sd']):
                        self.assertAlmostEqual(trace.error_x.array[0], point['x_sd'])
                    if bars and np.isfinite(point['y_sd']):
                        self.assertAlmostEqual(trace.error_y.array[0], point['y_sd'])

    def test_coordinate_only_difference_does_not_get_an_unqualified_count(self):
        landmark = synthetic_landmark(shape=8, ys=8, uts=8, el=8, uniform=6)
        self.assertEqual(core.landmark_population_suffix(landmark),
                         '(shape n=8; YS/UTS/EL n=8/8/8)')
        chart = figure_to_plotly(self.render(landmark))
        uts = next(trace for trace in chart.data if trace.customdata is not None and trace.marker.symbol == 'triangle-up')
        self.assertEqual(list(uts.customdata[0]), [6, 8])

    def test_group_review_marker_hover_uses_same_coordinate_counts(self):
        landmark = synthetic_landmark(el=3)
        review = SimpleNamespace(view=SimpleNamespace(value='aligned'), _aligned_model=landmark,
                                 markers={name: SimpleNamespace(value=True) for name in ('YS', 'UTS', 'EL')})
        traces = list(GroupCurveReview._marker_traces(review))
        for point, trace in zip(landmark['point_statistics'], traces):
            self.assertEqual(list(trace.customdata[0]), [point['x_n'], point['y_n']])
            self.assertIn('Stress n=%{customdata[1]}', trace.hovertemplate)

    def test_landmark_wh_legends_only_shape_count_with_inputs_in_log(self):
        result = (np.linspace(.2, 2., 10), np.linspace(2000., 800., 10), None)
        unequal = synthetic_landmark(shape=2, ys=3, uts=4, el=99, uniform=3)
        equal = synthetic_landmark(shape=2, ys=2, uts=2, el=99, uniform=2)
        legacy = deepcopy(equal)
        legacy.pop('shape_n')
        legacy.pop('property_counts')
        for landmark in (unequal, equal, legacy):
            for show in (False, True):
                log = io.StringIO()
                with patch.object(core, 'compute_landmark_work_hardening_curve', return_value=result), \
                     patch.object(core, 'compute_work_hardening_curve', return_value=result), \
                     redirect_stdout(log):
                    figure = core.render_landmark_work_hardening_plot(
                        {'Alloy': {'landmark': landmark}}, {'Alloy': [(result[0], result[1])]}, self.output,
                        {'Alloy': '#336699'}, show_individual=show, preview=True)
                expected = 'Alloy (shape n=2)'
                self.assertEqual(figure.axes[0].get_legend_handles_labels()[1], [expected])
                chart = figure_to_plotly(figure)
                self.assertEqual([trace.meta['legend_label'] for trace in chart.data if trace.showlegend],
                                 [expected])
                if landmark is unequal:
                    self.assertIn('input populations=(shape n=2; YS/UTS/UE n=3/4/3)', log.getvalue())
                self.assertNotIn('99', log.getvalue())
                np.testing.assert_array_equal(figure._export_wh[-1][3], result[0])
                np.testing.assert_array_equal(figure._export_wh[-1][4], result[1])
                self.assertFalse(self.output.exists())

    def test_wh_comparison_inherits_shape_only_legend(self):
        from tensile_workbench import PreviewSession
        result = (np.linspace(.2, 2., 10), np.linspace(2000., 800., 10), None)
        landmark = synthetic_landmark(shape=2, ys=3, uts=4, uniform=3)
        for show in (False, True):
            first, ax = plt.subplots()
            ax.plot(result[0], result[1], label='Alloy (n=2)')
            common = dict(out_path=self.output, color_map={'Alloy': '#336699'},
                          xlim=None, ylim=None, show_individual=show, preview=True)
            with patch.object(core, 'render_work_hardening_plot', return_value=first), \
                 patch.object(core, 'compute_landmark_work_hardening_curve', return_value=result), \
                 redirect_stdout(io.StringIO()):
                figure = PreviewSession._compare_wh(SimpleNamespace(engine=core),
                    {'Alloy': {'landmark': landmark}}, {'Alloy': []}, common, {})
            expected = ['Alloy (n=2) · original', 'Alloy (shape n=2) · landmark']
            self.assertEqual(figure.axes[0].get_legend_handles_labels()[1], expected)
            chart = figure_to_plotly(figure)
            self.assertEqual([trace.meta['legend_label'] for trace in chart.data if trace.showlegend], expected)
            self.assertFalse(self.output.exists())

    def test_legacy_count_without_metadata(self):
        self.assertEqual(core.landmark_population_suffix({'n': 4}), '(n=4)')


if __name__ == '__main__':
    unittest.main()
