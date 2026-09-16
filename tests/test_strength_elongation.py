from contextlib import redirect_stdout
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from selection_fixture import make_fixture
from tensile_plotly import figure_to_plotly
from tensile_workbench import TensileWorkbench, PROPERTY_FAMILIES


class StrengthElongationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='strength-el-synthetic-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        make_fixture(self.root)
        with redirect_stdout(io.StringIO()):
            self.app = TensileWorkbench(self.root)
        self.session = self.app.session

    def state(self, family='ys_vs_el', **kwargs):
        return {**self.app.state(), 'graph_index': 0, 'family': family, **kwargs}

    @staticmethod
    def mean_line(result):
        return next(line for line in result['figure'].axes[0].lines
                    if not line.get_label().startswith('_'))

    @staticmethod
    def individual_lines(result):
        return [line for line in result['figure'].axes[0].lines
                if hasattr(line, '_tensile_hover_label')]

    def test_both_views_use_table_properties_without_fitting_average_curves(self):
        frames = self.session.property_tables(self.app.state(), self.app._current()['definition'])
        rows = frames['tensile_samples'].query('Included')
        for family, metric in (('ys_vs_el', '0.2% Offset Yield Strength (MPa)'), ('uts_vs_el', 'UTS (MPa)')):
            with self.subTest(family=family), \
                 patch.object(self.session.engine, 'prepare_average_curves', side_effect=AssertionError('Not a curve plot')):
                without = self.session.render(self.state(family, show_individuals=False))
                with_points = self.session.render(self.state(family, show_individuals=True))
            for result in (without, with_points):
                mean = self.mean_line(result)
                self.assertAlmostEqual(mean.get_xdata()[0], rows['Failure Elongation (%)'].mean())
                self.assertAlmostEqual(mean.get_ydata()[0], rows[metric].mean())
                self.assertIn('(n=3)', mean.get_label())
                bars = result['figure'].axes[0].containers[0]
                x_segment, y_segment = (collection.get_segments()[0] for collection in bars.lines[2])
                self.assertAlmostEqual(np.ptp(x_segment[:, 0]) / 2, rows['Failure Elongation (%)'].std())
                self.assertAlmostEqual(np.ptp(y_segment[:, 1]) / 2, rows[metric].std())
            self.assertEqual(len(self.individual_lines(without)), 0)
            self.assertEqual(len(self.individual_lines(with_points)), 3)
            np.testing.assert_allclose([line.get_xdata()[0] for line in self.individual_lines(with_points)], rows['Failure Elongation (%)'])
            np.testing.assert_allclose([line.get_ydata()[0] for line in self.individual_lines(with_points)], rows[metric])
        self.assertFalse((self.root / 'output').exists())

    def test_exclusion_changes_points_mean_sd_and_count(self):
        self.app._specimen_changed('Alloy A/coupon_2.csv', False, 'synthetic')
        for family in PROPERTY_FAMILIES:
            result = self.session.render(self.state(family, show_individuals=True))
            self.assertEqual(len(self.individual_lines(result)), 2)
            self.assertIn('(n=2)', self.mean_line(result).get_label())
            self.assertNotIn('coupon_2.csv', str([line._tensile_hover_label for line in self.individual_lines(result)]))
        self.app._specimen_changed('Alloy A/coupon_3.csv', False, '')
        result = self.session.render(self.state(show_individuals=True))
        self.assertIn('(n=1)', self.mean_line(result).get_label())
        self.assertFalse(result['figure'].axes[0].containers)

    def test_unresolved_yield_keeps_uts_and_pairs_the_mean_elongation(self):
        original = self.session.engine.specimen_properties
        def partially_unresolved(record, *args):
            properties = original(record, *args)
            if record['sample'] == 'coupon_3':
                properties.update({'Yield (MPa)': np.nan, 'Yield status': 'unresolved', 'Notes': 'synthetic missing fit'})
            return properties
        with patch.object(self.session.engine, 'specimen_properties', side_effect=partially_unresolved):
            ys = self.session.render(self.state(show_individuals=True))
            uts = self.session.render(self.state('uts_vs_el', show_individuals=True))
        self.assertEqual(len(self.individual_lines(ys)), 2)
        self.assertAlmostEqual(self.mean_line(ys).get_xdata()[0], 17.5)  # first two terminal strains, not all three
        self.assertEqual(len(self.individual_lines(uts)), 3)
        self.assertIn('synthetic missing fit', ys['log'])
        self.session._previews.clear()
        def all_unresolved(record, *args):
            return {**original(record, *args), 'Yield (MPa)': np.nan}
        with patch.object(self.session.engine, 'specimen_properties', side_effect=all_unresolved):
            with self.assertRaisesRegex(ValueError, 'No valid paired strength/elongation'):
                self.session.render(self.state())

    def test_plotly_retains_means_errors_and_specimen_hover_identity(self):
        result = self.session.render(self.state(show_individuals=True))
        chart = figure_to_plotly(result['figure'])
        self.assertEqual(len(chart.data), 4)
        self.assertTrue(all(trace.mode == 'markers' for trace in chart.data))
        means = [trace for trace in chart.data if trace.showlegend]
        self.assertEqual(len(means), 1)
        self.assertIn('(n=3)', means[0].meta['legend_label'])
        self.assertEqual(means[0].marker.symbol, 'diamond')
        self.assertGreater(means[0].error_x.array[0], 0)
        self.assertGreater(means[0].error_y.array[0], 0)
        self.assertEqual(len({trace.legendgroup for trace in chart.data}), 1)
        self.assertIn('Alloy A/coupon_1.csv', chart.data[0].hovertemplate)
        without = self.session.render(self.state(show_individuals=False, property_error_bars=False))
        self.assertEqual(len(figure_to_plotly(without['figure']).data), 1)
        self.assertFalse(without['figure'].axes[0].containers)

    def test_independent_axes_titles_labels_and_colours(self):
        project = deepcopy(self.session.project)
        project['graphs'][0]['definition'].update(name_overrides={'Alloy A': 'Custom alloy'},
            color_overrides={'Alloy A': '#aa2244'}, workbench_titles={'ys_vs_el': 'Synthetic yield map'})
        self.session.set_project(project)
        result = self.session.render(self.state(ys_vs_el_xlim=[10, 25], ys_vs_el_ylim=[500, 850],
            tensile_xlim=[0, 1], tensile_ylim=[0, 1], show_individuals=True))
        ax = result['figure'].axes[0]
        np.testing.assert_allclose(ax.get_xlim(), [10, 25])
        np.testing.assert_allclose(ax.get_ylim(), [500, 850])
        self.assertEqual(ax.get_title(), 'Synthetic yield map')
        self.assertEqual(ax.get_ylabel(), '0.2% YS (MPa)')
        self.assertEqual(self.mean_line(result).get_color(), '#aa2244')
        self.assertIn('Custom alloy', self.mean_line(result).get_label())
        uts = self.session.render(self.state('uts_vs_el', tensile_xlim=[0, 1], tensile_ylim=[0, 1]))
        self.assertGreater(uts['figure'].axes[0].get_xlim()[1], 18)
        with self.assertRaisesRegex(ValueError, 'ys_vs_el_xlim'):
            self.session.render(self.state(ys_vs_el_xlim=[10, 5]))

    def test_curve_filter_changes_do_not_recompute_property_plots(self):
        first = self.session.render(self.state())
        second = self.session.render(self.state(modulus_gpa=70, min_plastic_strain=.7,
            landmark_points=800, wh_points=1600, pointwise_points=1200,
            tail_enabled=False, smooth=False, tensile_xlim=[0, 5]))
        self.assertIs(first['figure'], second['figure'])

    def test_controls_save_reopen_and_export_all_four_variants(self):
        self.app.family_boxes['ys_vs_el'].value = True
        self.app.family_boxes['uts_vs_el'].value = True
        self.app.controls['show_both_versions'].value = True
        self.app.controls['property_error_bars'].value = False
        auto, low, high, _ = self.app.axes['ys_vs_el_xlim']
        low.value, high.value, auto.value = 5, 25, False
        self.app.title_inputs['ys_vs_el'].value = 'Yield map'
        self.app.save_current()
        with redirect_stdout(io.StringIO()):
            reopened = TensileWorkbench(self.root)
        self.assertTrue(reopened.family_boxes['ys_vs_el'].value)
        self.assertTrue(reopened.family_boxes['uts_vs_el'].value)
        self.assertFalse(reopened.controls['property_error_bars'].value)
        self.assertEqual(reopened.state()['ys_vs_el_xlim'], [5, 25])
        self.assertIsNone(reopened.state()['uts_vs_el_xlim'])
        self.assertEqual(reopened.title_inputs['ys_vs_el'].value, 'Yield map')
        with redirect_stdout(io.StringIO()):
            reopened.update()
        self.assertEqual(len(reopened._results), 4)
        # Focused synthetic export verifies filenames, not research output generation.
        with patch.object(reopened.session.engine, 'PLOT_DPI', 50):
            folder = reopened.session.export(reopened._results)
        names = sorted(path.name for path in folder.glob('*.png'))
        for expected in ('08_ys_vs_el_with_individuals', '08_ys_vs_el_without_individuals',
                         '09_uts_vs_el_with_individuals', '09_uts_vs_el_without_individuals'):
            self.assertTrue(any(expected in name for name in names))
        metadata = json.loads((folder / 'settings.json').read_text())
        self.assertEqual(len(metadata['views']), 4)


if __name__ == '__main__':
    unittest.main()
