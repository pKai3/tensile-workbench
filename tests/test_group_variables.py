"""Numeric variables and independent chart variants, using synthetic data only."""
from contextlib import redirect_stdout
from copy import deepcopy
import io
import itertools
import json
import unittest
from unittest.mock import patch

import numpy as np
from openpyxl import load_workbook

import test_group_properties as fixture
from tensile_variables import GroupVariablesView, validate_variables, variable_axis
from tensile_property_variants import VARIANTS_KEY, TITLE_KEY, validate_variants
from tensile_group_plot import GROUP_FAMILY
from tensile_moves import migrate_settings, forget_group, references
from tensile_plotly import figure_to_plotly
from tensile_workbench import TensileWorkbench


class GroupVariablesTests(unittest.TestCase):
    setUp = fixture.GroupPropertiesTests.setUp
    state = fixture.GroupPropertiesTests.state
    means = staticmethod(fixture.GroupPropertiesTests.means)

    def variable(self, values=None):
        variable = dict(name='Shielding CO₂', unit='%', values=values if values is not None else
                        {'Alloy A': 0, 'Alloy Z': 12.5, 'Heat treated': 5})
        self.app._save_group_variable('co2', variable)
        return variable

    def test_validation_zero_missing_equal_and_numeric_order(self):
        v = self.variable({'Alloy A': 0, 'Alloy Z': 0})
        order, x, label, warning = variable_axis(['Alloy Z', 'Heat treated', 'Alloy A'], 'co2', {'co2': v})
        self.assertEqual(order, ['Alloy Z', 'Alloy A'])
        self.assertEqual(x, [0, 0])
        self.assertEqual(label, 'Shielding CO₂ (%)')
        self.assertIn('Heat treated', warning)
        self.assertIn('remain separate', warning)
        for value in (float('nan'), float('inf'), True, '2'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_variables({'x': {**v, 'values': {'A': value}}})
        with self.assertRaises(ValueError):
            validate_variables({'a': v, 'b': {**v, 'name': ' shielding CO₂ '}})
        for ident, groups in [('missing', ['Alloy A']), ('co2', ['Heat treated'])]:
            with self.assertRaises(ValueError):
                variable_axis(groups, ident, {'co2': v})

    def test_variable_rows_follow_shared_order_without_losing_drafts(self):
        self.app.controls['groups'].value = ('Alloy A', 'Heat treated')
        view = self.app.group_variables
        view.name.value, view.unit.value = 'Gas', '%'
        view.fields['Alloy A'].value = '0'
        view.fields['Heat treated'].value = '5.25'
        self.app.display_order_select.value = 'Heat treated'
        self.app._move_display_order(-1)
        self.assertEqual(list(view.fields), ['Heat treated', 'Alloy A'])
        self.assertEqual(view.fields['Alloy A'].value, '0')
        self.assertEqual(view.fields['Heat treated'].value, '5.25')
        self.assertEqual((view.name.value, view.unit.value), ('Gas', '%'))
        view.all_groups.value = True
        self.assertEqual(list(view.fields), ['Heat treated', 'Alloy A', 'Alloy Z'])
        view.fields['Alloy Z'].value = '12.5'
        view.all_groups.value = False
        self.assertEqual(list(view.fields), ['Heat treated', 'Alloy A'])
        view.save.click()
        self.assertEqual(list(view.fields), ['Heat treated', 'Alloy A'])
        self.assertEqual(self.app.store.data['group_variables'][view.choice.value]['values'],
                         {'Alloy A': 0, 'Heat treated': 5.25, 'Alloy Z': 12.5})
        with redirect_stdout(io.StringIO()):
            reopened = TensileWorkbench(self.root)
        self.assertEqual(list(reopened.group_variables.fields), ['Heat treated', 'Alloy A'])
        reopened._apply_graph('1')
        self.assertEqual(list(reopened.group_variables.fields), ['Alloy A'])
        reopened._apply_graph('0')
        self.assertEqual(list(reopened.group_variables.fields), ['Heat treated', 'Alloy A'])

    def test_many_variable_rows_scroll_without_shrinking_or_changing_selection(self):
        import ipywidgets as w
        groups = [f'Owner/Batch/Alloy {i:02d}' for i in range(60)]
        selected = [groups[2], groups[0]]
        view = GroupVariablesView(w, lambda: {}, lambda: groups, lambda *_: None)
        view.refresh(selected, order=selected)
        view.fields[groups[2]].value = '0'
        view.all_groups.value = True
        self.assertEqual(len(view.fields), 60)
        self.assertEqual(list(view.fields)[:2], selected)
        self.assertEqual(view.groups, selected)
        self.assertEqual(view.rows.layout.overflow, 'auto')
        self.assertEqual(view.rows.layout.max_height, '300px')
        self.assertEqual(view.rows.layout.flex, '0 0 auto')
        for row in view.rows.children:
            self.assertEqual(row.layout.flex, '0 0 auto')
            self.assertEqual(row.layout.min_height, '32px')
            self.assertEqual(row.layout.flex_flow, 'row wrap')
        self.assertEqual(view.save.layout.align_self, 'flex-start')
        view.fields[groups[-1]].value = '12.5'
        view.all_groups.value = False
        self.assertEqual(list(view.fields), selected)
        self.assertEqual(view.fields[groups[2]].value, '0')
        view.all_groups.value = True
        self.assertEqual(view.fields[groups[-1]].value, '12.5')

    def test_numeric_spacing_identity_and_unchanged_means(self):
        self.variable()
        result = self.session.render(self.state(properties_by_group_x_variable='co2', show_individuals=True))
        ax = result['figure'].axes[0]
        self.assertEqual(ax.get_xlabel(), 'Shielding CO₂ (%)')
        self.assertIn('vs Shielding CO₂', ax.get_title())
        for line in self.means(result).values():
            np.testing.assert_equal(line.get_xdata(), [0, 5, 12.5])
        chart = figure_to_plotly(result['figure'])
        self.assertIsNone(chart.layout.xaxis.ticktext)
        mean = next(t for t in chart.data if t.showlegend)
        self.assertEqual(mean.customdata[0][0], 'Alloy A')
        self.assertEqual(mean.customdata[0][1], 3)
        self.assertIn('Sample group:', mean.hovertemplate)
        self.assertTrue(mean.error_y.visible)
        without = self.session.render(self.state(properties_by_group_x_variable='co2', show_individuals=False))
        for a, b in zip(result['figure'].axes, without['figure'].axes):
            np.testing.assert_allclose(a.get_ylim(), b.get_ylim())
            np.testing.assert_allclose(a.get_xlim(), b.get_xlim())
        categorical = self.session.render(self.state(group_order=['Alloy A', 'Heat treated', 'Alloy Z']))
        for name, line in self.means(result).items():
            np.testing.assert_allclose(line.get_ydata(), self.means(categorical)[name].get_ydata())

    def test_each_property_combination_and_axis_limits(self):
        self.variable()
        for flags in itertools.product((False, True), repeat=3):
            state = self.state(properties_by_group_x_variable='co2', properties_by_group_xlim=[-1, 15],
                               properties_by_group_ylim=[0, 999], properties_by_group_el_ylim=[0, 44],
                               **dict(zip(('properties_by_group_show_' + k for k in ('ys', 'uts', 'el')), flags)))
            if not any(flags):
                with self.assertRaisesRegex(ValueError, 'at least one property'):
                    self.session.render(state)
                continue
            result = self.session.render(state)
            self.assertEqual(set(self.means(result)), {label for label, on in zip(('0.2% YS', 'UTS', 'EL'), flags) if on})
            chart = figure_to_plotly(result['figure'])
            self.assertEqual(tuple(chart.layout.xaxis.range), (-1, 15))
            self.assertEqual(len(result['figure'].axes), 2 if any(flags[:2]) and flags[2] else 1)
            self.assertEqual(tuple(chart.layout.yaxis.range), (0, 999) if any(flags[:2]) else (0, 44))

    def test_global_editor_persistence_and_cache_invalidation(self):
        view = self.app.group_variables
        view.name.value, view.unit.value = 'Shielding CO₂', '%'
        view.fields['Alloy A'].value = '0'
        view.save.click()
        ident = view.choice.value
        self.assertTrue(ident)
        self.assertEqual(self.app.store.data['group_variables'][ident]['values'], {'Alloy A': 0})
        self.app.controls['properties_by_group_x_variable'].value = ident
        result = self.session.render(self.state(properties_by_group_x_variable=ident))
        self.assertIn('omitted from this plot', result['figure']._tensile_variable_warning)
        view.fields['Alloy A'].value = '2.5'
        view.save.click()
        changed = self.session.render(self.state(properties_by_group_x_variable=ident))
        self.assertIsNot(result['figure'], changed['figure'])
        with self.assertRaisesRegex(ValueError, 'variables changed'):
            self.session.export([result])
        self.assertFalse((self.root / 'output').exists())
        np.testing.assert_equal(self.means(changed)['UTS'].get_xdata(), [2.5])
        self.app._apply_graph('1')
        self.assertIn(ident, dict((value, label) for label, value in self.app.controls['properties_by_group_x_variable'].options))
        with redirect_stdout(io.StringIO()):
            reopened = TensileWorkbench(self.root)
        self.assertEqual(reopened.store.data['group_variables'][ident]['values'], {'Alloy A': 2.5})
        before = deepcopy(reopened.store.data)
        reopened.group_variables.name.value = 'Bad'
        reopened.group_variables.fields['Alloy A'].value = 'nan'
        reopened.group_variables.save.click()
        self.assertIn('Not saved', reopened.group_variables.status.value)
        self.assertEqual(before, reopened.store.data)

    def test_variants_switch_persist_add_remove_and_titles(self):
        self.variable()
        self.app.controls['properties_by_group_x_variable'].value = 'co2'
        self.app.title_inputs[GROUP_FAMILY].value = 'Strength vs gas'
        self.app.controls['properties_by_group_show_el'].value = False
        view = self.app.property_variants
        view.name.value = 'Strength'
        first = view.active
        view.add.click()
        second = view.active
        self.app.controls['properties_by_group_x_variable'].value = ''
        self.app.controls['properties_by_group_show_el'].value = True
        self.app.controls['properties_by_group_show_ys'].value = False
        self.app.controls['properties_by_group_show_uts'].value = False
        self.app.controls['properties_by_group_line_style'].value = 'dot'
        self.app.title_inputs[GROUP_FAMILY].value = 'Elongation by group'
        self.app.group_label_fields['Alloy A'].value = 'Short'
        view.choice.value = first
        self.assertEqual(self.app.title_inputs[GROUP_FAMILY].value, 'Strength vs gas')
        self.assertFalse(self.app.controls['properties_by_group_show_el'].value)
        self.assertEqual(self.app.group_label_fields['Alloy A'].value, '')
        with redirect_stdout(io.StringIO()):
            reopened = TensileWorkbench(self.root)
        self.assertEqual(len(reopened.state()[VARIANTS_KEY]), 2)
        reopened.property_variants.choice.value = second
        self.assertEqual(reopened.title_inputs[GROUP_FAMILY].value, 'Elongation by group')
        self.assertEqual(reopened.group_label_fields['Alloy A'].value, 'Short')
        self.assertEqual(reopened.controls['properties_by_group_line_style'].value, 'dot')
        reopened.property_variants.remove.click()
        self.assertEqual(len(reopened.state()[VARIANTS_KEY]), 1)
        self.assertTrue(reopened.property_variants.remove.disabled)

    def test_gallery_and_export_multiple_charts_both_individual_variants(self):
        self.variable({'Alloy A': 0, 'Alloy Z': 5})
        self.app.controls['groups'].value = ('Alloy A', 'Alloy Z', 'Heat treated')
        self.app.controls['properties_by_group_x_variable'].value = 'co2'
        self.app.controls['show_both_versions'].value = True
        self.app.family_boxes[GROUP_FAMILY].value = True
        self.app.property_variants.add.click()
        self.app.controls['properties_by_group_show_el'].value = False
        with patch.object(self.app.viewer, 'set_items') as display:
            self.app.update()
        self.assertEqual(len(self.app._results), 4, self.app.details.value)
        items = display.call_args.args[0]
        self.assertEqual(len({i['key'] for i in items}), 4)
        self.assertTrue(all('Heat treated' in i['warning'] for i in items))
        self.session.engine.PLOT_DPI = 50
        destination = self.session.export(self.app._results, include_tables=True)
        self.assertEqual(len(list(destination.glob('*.png'))), 4)
        metadata = json.loads((destination / 'settings.json').read_text())
        self.assertEqual(len({v['property_chart_id'] for v in metadata['views']}), 2)
        workbook = load_workbook(next(destination.glob('*_results.xlsx')), read_only=True, data_only=True)
        rows = list(workbook['Group variables'].values)
        self.assertEqual(rows[0][-1], 'Value')
        self.assertEqual(rows[1][-1], 0)
        self.assertEqual(rows[2][-1], 5)
        workbook.close()

    def test_separate_numeric_variables_render_independently(self):
        self.variable()
        self.app._save_group_variable('temperature', dict(name='Temperature', unit='°C',
            values={'Alloy A': 500, 'Alloy Z': 870, 'Heat treated': 600}))
        self.app.controls['groups'].value = ('Alloy A', 'Alloy Z', 'Heat treated')
        self.app.controls['show_both_versions'].value = False
        self.app.controls['properties_by_group_x_variable'].value = 'co2'
        self.app.family_boxes[GROUP_FAMILY].value = True
        self.app.property_variants.add.click()
        self.app.controls['properties_by_group_x_variable'].value = 'temperature'
        with patch.object(self.app.viewer, 'set_items'):
            self.app.update()
        first, second = self.app._results
        np.testing.assert_equal(self.means(first)['UTS'].get_xdata(), [0, 5, 12.5])
        np.testing.assert_equal(self.means(second)['UTS'].get_xdata(), [500, 600, 870])
        self.assertEqual(second['figure'].axes[0].get_xlabel(), 'Temperature (°C)')
        # Changing variables is display metadata, never a specimen-property edit.
        np.testing.assert_allclose(self.means(first)['UTS'].get_ydata(), self.means(second)['UTS'].get_ydata())

    def test_move_and_forget_values_and_variant_labels(self):
        self.variable()
        project = deepcopy(self.app.store.data)
        settings = project['graphs'][0]['settings']
        settings[VARIANTS_KEY][0]['settings']['properties_by_group_labels'] = {'Alloy A': 'Short'}
        proposal = dict(old='Alloy A', new='Owner/Alloy A', mapping={})
        moved = migrate_settings(project, proposal, audit=False)
        self.assertEqual(moved['group_variables']['co2']['values']['Owner/Alloy A'], 0)
        self.assertIn('Owner/Alloy A', moved['graphs'][0]['settings'][VARIANTS_KEY][0]['settings']['properties_by_group_labels'])
        self.assertNotIn('Alloy A', references(moved)[0])
        forgotten = forget_group(moved, 'Owner/Alloy A', live_groups=[])
        self.assertNotIn('Owner/Alloy A', references(forgotten)[0])
        self.assertIn('Alloy A', project['group_variables']['co2']['values'])

    def test_bad_variant_rejected_and_missing_variable_not_replaced(self):
        variant = self.app.state()[VARIANTS_KEY][0]
        for invalid in ([], [variant, variant], [{**variant, 'name': ''}],
                        [{**variant, 'settings': {'properties_by_group_xlim': [3, 1]}}]):
            with self.assertRaises(ValueError):
                validate_variants(invalid)
        self.app._apply_property_chart({**variant['settings'], 'properties_by_group_x_variable': 'gone'})
        self.assertEqual(self.app.controls['properties_by_group_x_variable'].value, 'gone')
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            self.session.render(self.state(properties_by_group_x_variable='gone'))
