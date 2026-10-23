"""Specimen-location trial: synthetic curves, no research data or outputs."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import itertools
import unittest
from unittest.mock import patch

import numpy as np
from openpyxl import load_workbook
import test_group_properties as fixture
from tensile_workbench import TensileWorkbench
from tensile_specimen_plot import specimen_number, SPECIMEN_NUMBER
from tensile_settings import planned_positions, validate_group_display, SPECIMEN_TREND_KEY
from tensile_variables import validate_variables, variable_usage
from tensile_property_variants import VARIANTS_KEY, SPECIMEN_VARIANTS_KEY, SPECIMEN_FAMILY
from tensile_locations import LOCATION, SPECIMEN_COUNT
from tensile_group_plot import GROUP_FAMILY
from tensile_plotly import figure_to_plotly
from tensile_moves import migrate_settings, forget_group, references


class SpecimenVariablesTests(unittest.TestCase):
    @staticmethod
    def bars(result):
        return {bars.get_label(): bars for ax in result['figure'].axes for bars in ax.containers}

    def setUp(self):
        fixture.GroupPropertiesTests.setUp(self)
        for group in self.session.files:
            for record, number in zip(self.session._load(group), (1, 4, 7)):
                record['specimen_label'] = f'Wall_{number:02d}'

    def state(self, **kwargs):
        return fixture.GroupPropertiesTests.state(self, groups=['Alloy A'], family=SPECIMEN_FAMILY,
            properties_by_group_level='specimen', properties_by_group_x_variable=LOCATION,
            properties_by_group_line_style='none', **kwargs)

    def location(self):
        variable = dict(name='Height', unit='mm', values={
            'Alloy A/coupon_1.csv': 0, 'Alloy A/coupon_2.csv': 5, 'Alloy A/coupon_3.csv': 20})
        self.app._save_specimen_variable('height', variable)
        return variable

    def editor(self):
        self.app.custom_variables_panel.selected_index = 0
        self.app.custom_variable_tabs.selected_index = 1
        return self.app.specimen_variables

    def test_number_from_operator_not_export_row_and_ambiguous_names(self):
        for label, expected in [('B14_007', 7), ('7', 7), ('Wall-02', 2), ('Wall 4', 4),
                                ('B14_1 / B14_2', None), ('B14', None), ('B14_1 unsure', None), ('', None)]:
            self.assertEqual(specimen_number(dict(specimen_label=label, sample='B14_99')), expected)
        self.assertIsNone(specimen_number(dict(sample='B14_99')))
        self.assertEqual(planned_positions('1:10'), list(range(1, 11)))
        self.assertEqual(planned_positions('0,5,20'), [0, 5, 20])
        for invalid in ('1:9999', '10:1', 'nan', 'abc', '1:', '1,,2'):
            with self.assertRaises(ValueError):
                planned_positions(invalid)

    def test_planned_untested_locations_and_trend_do_not_create_observations(self):
        self.app._save_group_variable(SPECIMEN_COUNT, dict(name='Specimen count', unit='', values={'Alloy A': 10}))
        state = self.state(properties_by_group_trend='linear')
        result = self.session.render(state)
        for bars in self.bars(result).values():
            np.testing.assert_array_equal(bars._tensile_locations, [1, 4, 7])
            self.assertFalse(hasattr(bars, '_tensile_counts'))
        axis = result['figure'].axes[0]
        np.testing.assert_array_equal(axis.get_xticks(), range(1, 11))
        self.assertLess(axis.get_xlim()[0], 1)
        self.assertGreater(axis.get_xlim()[1], 10)
        extrapolated = [line for a in result['figure'].axes for line in a.lines
                        if getattr(line, '_tensile_is_extrapolation', False)]
        self.assertEqual(len(extrapolated), 3)
        ys = self.bars(result)['0.2% YS']
        prediction = np.polynomial.Polynomial.fit(ys._tensile_locations, ys.datavalues, 1)(10)
        self.assertAlmostEqual(extrapolated[0].get_ydata()[-1], prediction)
        self.assertEqual(extrapolated[0].get_xdata()[-1], 10)
        self.assertEqual(extrapolated[0].get_linestyle(), ':')
        self.assertEqual(len(result['export_records']['Alloy A']), 3)
        plotly = figure_to_plotly(result['figure'])
        self.assertEqual(list(plotly.layout.xaxis.tickvals), list(range(1, 11)))
        trace = next(t for t in plotly.data if t.name == '0.2% YS')
        self.assertIn('Specimen:', trace.hovertemplate)
        self.assertEqual(trace.customdata[0][0], 'Alloy A · Wall_01')
        self.assertEqual(trace.type, 'bar')
        self.assertEqual(trace.customdata[0][1], 1)

    def test_location_editor_defaults_override_reset_and_clipboard(self):
        view = self.editor()
        self.assertEqual(view.name.value, 'Location')
        self.assertEqual([v.value for v in view.fields.values()], ['1', '4', '7'])
        first = 'Alloy A/coupon_1.csv'
        view.fields[first].value = '2'
        view.save.click()
        ident = view.choice.value
        self.assertEqual(ident, LOCATION)
        self.assertEqual(self.app.store.data['specimen_variables'][ident]['values'][first], 2)
        view.fields[first].value = ''
        view.save.click()
        self.app._refresh_specimen_variables(force=True)
        self.assertEqual(view.fields[first].value, '1')
        self.assertNotIn(first, self.app.store.data['specimen_variables'][LOCATION]['values'])
        view.view.value = 'table'
        view.table._message(None, dict(type='paste', row=0, column=0, text='Location\tTemperature\n\t°C\n0\t500\n5\t600\n20\t700'), [])
        view.save_all.click()
        saved = self.app.store.data['specimen_variables']
        self.assertEqual(len(saved), 2)
        self.assertEqual(saved[ident]['values'][first], 0)
        self.assertEqual(view.table.labels[first], 'Alloy A · Wall_01')
        self.assertEqual(set(self.app.store.data['group_variables']), {SPECIMEN_COUNT})
        with redirect_stdout(io.StringIO()):
            reopened = TensileWorkbench(self.root)
        self.assertEqual(reopened.store.data['specimen_variables'], saved)

    def test_independent_sections_variants_and_one_chart_per_group(self):
        view = self.app.specimen_charts
        self.assertNotIn('properties_by_group_level', self.app.controls)
        self.assertEqual(view.controls['properties_by_group_x_variable'].value, LOCATION)
        self.assertNotIn('properties_by_group_line_style', view.controls)
        self.assertEqual(view.controls[SPECIMEN_TREND_KEY].value, 'quadratic')
        self.app.controls['groups'].value = ('Alloy A', 'Heat treated')
        self.app.controls['show_both_versions'].value = True
        self.app.family_boxes[SPECIMEN_FAMILY].value = True
        with patch.object(self.app.viewer, 'set_items') as display:
            self.app.update()
        self.assertEqual(len(self.app._results), 2, self.app.details.value)
        self.assertIn('individual specimens', display.call_args.args[0][0]['label'])
        self.assertEqual(len({i['key'] for i in display.call_args.args[0]}), 2)
        for result in self.app._results:
            self.assertEqual(len(result['state']['groups']), 1)
            self.assertEqual(set(self.bars(result)), {'0.2% YS', 'UTS', 'EL'})
        first = view.variants.active
        view.variants.add.click()
        view.controls[SPECIMEN_TREND_KEY].value = 'linear'
        view.variants.choice.value = first
        self.assertEqual(view.controls[SPECIMEN_TREND_KEY].value, 'quadratic')
        self.assertEqual(self.app.property_variants.snapshot()[0]['settings']['properties_by_group_level'], 'group')

    def test_custom_locations_duplicates_and_missing_are_not_pooled(self):
        self.location()
        self.app._save_specimen_variable('height', dict(name='Height', unit='mm', values={
            'Alloy A/coupon_1.csv': 5, 'Alloy A/coupon_3.csv': 5}))
        result = self.session.render({**self.state(), 'properties_by_group_x_variable': 'height'})
        for bars in self.bars(result).values():
            np.testing.assert_array_equal(bars._tensile_locations, [5, 5])
        self.assertIn('Wall_04', result['figure']._tensile_variable_warning)
        self.assertIn('remain separate', result['figure']._tensile_variable_warning)
        self.assertEqual(result['figure'].axes[0].get_xlabel(), 'Height (mm)')

    def test_groups_stay_separate_and_insufficient_trend_remains_undrawn(self):
        state = {**self.state(), 'groups': ['Alloy A', 'Heat treated'],
                 'properties_by_group_planned_positions': '1:10', 'properties_by_group_trend': 'quadratic'}
        with self.assertRaisesRegex(ValueError, 'one sample group'):
            self.session.render(state)
        self.location()
        self.app._save_specimen_variable('height', dict(name='Height', values={'Alloy A/coupon_1.csv': 1}))
        result = self.session.render({**self.state(), 'properties_by_group_x_variable': 'height',
                                      'properties_by_group_trend': 'linear'})
        self.assertIn('not enough distinct measured locations', result['figure']._tensile_variable_warning)
        self.assertFalse(any(hasattr(line, '_tensile_is_extrapolation') for ax in result['figure'].axes for line in ax.lines))

    def test_shape_exclusion_keeps_properties_and_full_exclusion_keeps_editor_row(self):
        self.location()
        project = deepcopy(self.app.store.data)
        project['specimen_data_modes'] = {'Alloy A/coupon_1.csv': {'mode': 'exclude_shape', 'reason': 'odd curve'}}
        project['specimen_exclusions'] = {'Alloy A/coupon_3.csv': 'reserved for review'}
        self.session.set_project(project)
        result = self.session.render({**self.state(), 'properties_by_group_x_variable': 'height'})
        self.assertTrue(all(np.isfinite(bars.datavalues).all() for bars in self.bars(result).values()))
        self.assertTrue(all(len(bars.datavalues) == 2 for bars in self.bars(result).values()))
        self.assertEqual(len(self.session.specimen_variable_catalogue(['Alloy A'])), 3)

    def test_property_toggles_and_partial_exclusions(self):
        self.location()
        project = deepcopy(self.app.store.data)
        project['specimen_data_modes'] = {'Alloy A/coupon_2.csv': {'mode': 'after_uts', 'reason': 'synthetic AVE failure'}}
        project['specimen_exclusions'] = {'Alloy A/coupon_3.csv': 'synthetic exclusion'}
        self.session.set_project(project)
        state = {**self.state(), 'properties_by_group_x_variable': 'height'}
        result = self.session.render(state)
        values = self.bars(result)
        self.assertEqual(len(values['UTS'].datavalues), 2)
        self.assertTrue(np.isfinite(values['0.2% YS'].datavalues).all())
        self.assertEqual(values['EL']._tensile_point_labels, ['Alloy A · Wall_01'])
        self.assertIn('Wall_04 (EL)', result['figure']._tensile_variable_warning)
        for combination in itertools.product([False, True], repeat=3):
            if not any(combination):
                continue
            variant = {**state, **{f'properties_by_group_show_{k}': v for k, v in zip(('ys', 'uts', 'el'), combination)}}
            chart = self.session.render(variant)
            self.assertEqual(len(chart['figure'].axes), 2 if combination[2] and any(combination[:2]) else 1)

    def test_save_delete_invalidate_and_export(self):
        self.location()
        state = {**self.state(), 'properties_by_group_x_variable': 'height'}
        result = self.session.render(state)
        destination = self.session.export_properties(state, self.app._current()['definition'])
        workbook = load_workbook(next(destination.glob('*_results.xlsx')), read_only=True, data_only=True)
        rows = list(workbook['Specimen variables'].values)
        workbook.close()
        self.assertEqual(rows[0], ('Specimen ID', 'Variable ID', 'Variable', 'Unit', 'Value'))
        self.assertIn(('Alloy A/coupon_1.csv', 'height', 'Height', 'mm', 0), rows)
        self.assertIn(('Alloy A/coupon_1.csv', LOCATION, 'Location', None, 1), rows)
        self.app.specimen_charts.controls['properties_by_group_x_variable'].value = 'height'
        self.assertTrue(variable_usage(self.app.store.data, 'height', scope='specimen'))
        self.assertFalse(variable_usage(self.app.store.data, 'height'))
        view = self.editor()
        view.choice.value = 'height'
        view.remove.click()
        view.delete_confirm.click()
        self.assertNotIn('height', self.app.store.data['specimen_variables'])
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            self.session.render(state)
        with self.assertRaisesRegex(ValueError, 'variables changed'):
            self.session.export([result])

    def test_moves_forgetting_validation_and_scope_collision(self):
        variable = self.location()
        project = deepcopy(self.app.store.data)
        project['group_variables'] = {'height': dict(name='Group height', unit='mm', values={'Alloy A': 99})}
        mapping = {old: old.replace('Alloy A/', 'Owner/Alloy A/') for old in variable['values']}
        moved = migrate_settings(project, {'old': 'Alloy A', 'new': 'Owner/Alloy A', 'mapping': mapping}, audit=False)
        self.assertEqual(set(moved['specimen_variables']['height']['values']), set(mapping.values()))
        self.assertEqual(moved['group_variables']['height']['values'], {'Owner/Alloy A': 99})
        self.assertTrue(set(variable['values']) <= references(project)[1])
        forgotten = forget_group(project, 'Alloy A')
        self.assertEqual(forgotten['specimen_variables']['height']['values'], {})
        for bad_id in ('/absolute.csv', '../elsewhere.csv'):
            with self.assertRaises(ValueError):
                validate_variables({'x': dict(name='Location', values={bad_id: 1})}, scope='specimen')
        with self.assertRaises(ValueError):
            validate_group_display({'properties_by_group_level': 'wrong'})


if __name__ == '__main__':
    unittest.main()
