"""Grouped specimen bars and chart-local group filters; synthetic fixtures only."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import unittest
from unittest.mock import patch

import numpy as np
import test_specimen_variables as fixture
from tensile_locations import SPECIMEN_COUNT
from tensile_moves import migrate_settings, forget_group, references
from tensile_plotly import figure_to_plotly
from tensile_property_variants import SPECIMEN_FAMILY, SPECIMEN_VARIANTS_KEY
from tensile_settings import SPECIMEN_TREND_KEY, SPECIMEN_GROUPS_KEY, validate_group_display
from tensile_workbench import TensileWorkbench


class SpecimenBarTests(unittest.TestCase):
    setUp = fixture.SpecimenVariablesTests.setUp
    state = fixture.SpecimenVariablesTests.state
    bars = staticmethod(fixture.SpecimenVariablesTests.bars)

    def test_default_bars_fit_quadratic_at_actual_locations_not_bar_offsets(self):
        self.app._save_group_variable(SPECIMEN_COUNT, dict(name='Specimen count', unit='', values={'Alloy A': 10}))
        result = self.session.render(self.state())
        bars = self.bars(result)
        self.assertEqual(set(bars), {'0.2% YS', 'UTS', 'EL'})
        self.assertEqual(self.app.specimen_charts.controls[SPECIMEN_TREND_KEY].value, 'quadratic')
        for series in bars.values():
            self.assertEqual(len(series.patches), 3)
            polynomial = np.polynomial.Polynomial.fit(series._tensile_locations, series.datavalues, 2)
            trends = [line for ax in result['figure'].axes for line in ax.lines
                      if getattr(line, '_tensile_series_key', None) == series._tensile_series_key]
            self.assertEqual(len(trends), 2)
            for line in trends:
                np.testing.assert_allclose(line.get_ydata(), polynomial(line.get_xdata()))
            self.assertEqual(max(line.get_xdata()[-1] for line in trends), 10)
        # Exactly one bar per eligible measurement; no invented bars at 8–10.
        chart = figure_to_plotly(result['figure'])
        self.assertEqual(chart.layout.barmode, 'overlay')
        self.assertEqual(len([t for t in chart.data if t.type == 'bar']), 3)
        for trace in chart.data:
            if trace.type == 'bar':
                np.testing.assert_array_equal(trace.y, bars[trace.meta['legend_label']].datavalues)
                self.assertEqual([row[1] for row in trace.customdata], [1, 4, 7])
                self.assertIn('customdata[1]:.0f', trace.hovertemplate)
                self.assertEqual(sum(t.legendgroup == trace.legendgroup for t in chart.data), 3)
        self.assertEqual(next(t for t in chart.data if t.type == 'bar' and t.name == 'EL').yaxis, 'y2')
        self.assertEqual(len(result['export_records']['Alloy A']), 3)

    def test_bars_never_overlap_across_properties_axes_or_duplicate_locations(self):
        self.app._save_specimen_variable('__specimen_location__', dict(name='Location', unit='', values={
            'Alloy A/coupon_1.csv': 4, 'Alloy A/coupon_2.csv': 4, 'Alloy A/coupon_3.csv': 5}))
        result = self.session.render(self.state())
        bars = self.bars(result)
        spans = sorted((p.get_x(), p.get_x() + p.get_width()) for b in bars.values() for p in b.patches)
        self.assertTrue(all(end <= next_start for (_, end), (next_start, _) in zip(spans, spans[1:])))
        for b in bars.values():
            self.assertEqual(b._tensile_locations, [4, 4, 5])
        low, high = result['figure'].axes[0].get_xlim()
        self.assertLess(low, spans[0][0])
        self.assertGreater(high, spans[-1][1])
        self.assertIn('not enough distinct', result['figure']._tensile_variable_warning)

    def test_empty_property_axis_converts_and_does_not_add_zero_bars(self):
        project = deepcopy(self.app.store.data)
        project['specimen_data_modes'] = {f'Alloy A/coupon_{n}.csv': {'mode': 'after_uts', 'reason': 'synthetic'}
                                          for n in range(1, 4)}
        self.session.set_project(project)
        result = self.session.render(self.state())
        chart = figure_to_plotly(result['figure'])
        self.assertEqual({t.name for t in chart.data if t.type == 'bar'}, {'0.2% YS', 'UTS'})
        self.assertEqual(sum(len(t.y) for t in chart.data if t.type == 'bar'), 6)
        self.assertIn('Wall_01 (EL)', result['figure']._tensile_variable_warning)

    def test_group_ticks_all_none_and_subset_only_affect_these_charts(self):
        app, view = self.app, self.app.specimen_charts
        app.controls['groups'].value = ('Alloy A', 'Alloy Z', 'Heat treated')
        app._display_order = ['Heat treated', 'Alloy Z', 'Alloy A']
        app._sync_display_order()
        app.family_boxes[SPECIMEN_FAMILY].value = True
        self.assertEqual(list(view.group_boxes), app._display_order)
        self.assertTrue(view.all_groups.value)
        original_groups = app.state()['groups']
        original_selection = app.session.selection_signature()
        view.group_boxes['Alloy A'].value = False
        self.assertFalse(view.all_groups.value)
        self.assertEqual(set(view.capture()[SPECIMEN_GROUPS_KEY]), {'Heat treated', 'Alloy Z'})
        with patch.object(app.viewer, 'set_items'):
            app.update()
        self.assertEqual([r['state']['groups'] for r in app._results], [['Heat treated'], ['Alloy Z']])
        self.assertEqual(app.state()['groups'], original_groups)
        self.assertEqual(app.session.selection_signature(), original_selection)
        self.assertEqual(set(app.session.property_tables(app.state(), app._current()['definition'])['tensile_summary']['Group']),
                         set(original_groups))
        view.all_groups.value = True
        self.assertIsNone(view.capture()[SPECIMEN_GROUPS_KEY])
        self.assertTrue(all(box.value for box in view.group_boxes.values()))
        view.all_groups.value = False
        self.assertEqual(view.capture()[SPECIMEN_GROUPS_KEY], [])
        self.assertFalse(any(box.value for box in view.group_boxes.values()))
        with patch.object(app.session, 'render', side_effect=AssertionError('No charts selected')):
            app.update()
        self.assertFalse(app._results)
        self.assertTrue(app.export_button.disabled)
        self.assertIn('Choose sample groups', app.status.value)

    def test_subset_and_trend_persist_per_variant_without_loading_unselected_data(self):
        app, view = self.app, self.app.specimen_charts
        app.controls['groups'].value = ('Alloy A', 'Heat treated')
        view.group_boxes['Alloy A'].value = False
        view.controls[SPECIMEN_TREND_KEY].value = 'none'
        first = view.variants.active
        view.variants.add.click()
        view.all_groups.value = True
        view.controls[SPECIMEN_TREND_KEY].value = 'linear'
        view.variants.choice.value = first
        self.assertEqual(view.capture()[SPECIMEN_GROUPS_KEY], ['Heat treated'])
        self.assertEqual(view.controls[SPECIMEN_TREND_KEY].value, 'none')
        with patch.object(app.session, '_load', side_effect=AssertionError('Checkbox list is metadata only')):
            view.refresh_groups(['Heat treated', 'Alloy A'])
        app.controls['groups'].value = ('Alloy A',)
        self.assertEqual(view.capture()[SPECIMEN_GROUPS_KEY], ['Heat treated'])
        app.controls['groups'].value = ('Alloy A', 'Heat treated')
        self.assertTrue(view.group_boxes['Heat treated'].value)
        with redirect_stdout(io.StringIO()):
            reopened = TensileWorkbench(self.root)
        saved = reopened.store.data['graphs'][0]['settings'][SPECIMEN_VARIANTS_KEY]
        self.assertEqual(saved[0]['settings'][SPECIMEN_GROUPS_KEY], ['Heat treated'])
        self.assertEqual(saved[0]['settings'][SPECIMEN_TREND_KEY], 'none')
        self.assertIsNone(saved[1]['settings'][SPECIMEN_GROUPS_KEY])
        self.assertEqual(saved[1]['settings'][SPECIMEN_TREND_KEY], 'linear')

    def test_legacy_no_trend_becomes_quadratic_but_new_none_is_retained(self):
        view = self.app.specimen_charts
        view.apply({'properties_by_group_trend': 'none'})
        self.assertEqual(view.controls[SPECIMEN_TREND_KEY].value, 'quadratic')
        view.apply({'properties_by_group_trend': 'linear'})
        self.assertEqual(view.controls[SPECIMEN_TREND_KEY].value, 'linear')
        view.apply({SPECIMEN_TREND_KEY: 'none'})
        self.assertEqual(view.controls[SPECIMEN_TREND_KEY].value, 'none')

    def test_group_selection_moves_forgets_and_validates(self):
        self.app.save_current()
        project = deepcopy(self.app.store.data)
        settings = project['graphs'][0]['settings'][SPECIMEN_VARIANTS_KEY][0]['settings']
        settings[SPECIMEN_GROUPS_KEY] = ['Unselected group']
        self.assertIn('Unselected group', references(project)[0])
        moved = migrate_settings(project, dict(old='Unselected group', new='Owner/Group', mapping={}), audit=False)
        self.assertEqual(moved['graphs'][0]['settings'][SPECIMEN_VARIANTS_KEY][0]['settings'][SPECIMEN_GROUPS_KEY], ['Owner/Group'])
        forgotten = forget_group(moved, 'Owner/Group')
        self.assertEqual(forgotten['graphs'][0]['settings'][SPECIMEN_VARIANTS_KEY][0]['settings'][SPECIMEN_GROUPS_KEY], [])
        for value in ('all', [1], ['A', 'A'], ['']):
            with self.assertRaises(ValueError):
                validate_group_display({SPECIMEN_GROUPS_KEY: value})


if __name__ == '__main__':
    unittest.main()
