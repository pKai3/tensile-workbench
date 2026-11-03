"""Palette persistence and rendering with small synthetic data only."""
from contextlib import redirect_stdout
from copy import deepcopy
from colorsys import rgb_to_hsv
import io
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from matplotlib.colors import to_hex, to_rgb, is_color_like
import ipywidgets as widgets

from selection_fixture import make_fixture
from test_relative_comparison import frames
from tensile_colors import (PALETTES, COLOR_SLOTS, group_color_map, palette_colors,
                            palette_preview, reconcile_color_slots)
from tensile_comparison import ComparisonView
from tensile_plotly import figure_to_plotly
from tensile_workbench import TensileWorkbench
from workbench_project import validate_project


class PaletteTests(unittest.TestCase):
    def test_reference_colours_and_stronger_custom_themes(self):
        self.assertEqual(len(PALETTES), 16)
        self.assertEqual(palette_colors('retro_reference')[:4],
                         ('#E377C2', '#7F7F7F', '#BCBD22', '#17BECF'))
        self.assertEqual(palette_colors('classic')[-4:],
                         tuple(color.lower() for color in palette_colors('retro_reference')[:4]))
        for name in ('pastel_coastal', 'pastel_orchard', 'pastel_berry',
                     'muted', 'vivid', 'earth', 'ocean'):
            with self.subTest(palette=name):
                saturation = [rgb_to_hsv(*to_rgb(color))[1] for color in palette_colors(name)]
                self.assertGreater(sum(saturation) / len(saturation), .55)

    def test_palettes_preview_cycle_legacy_and_override_priority(self):
        groups = [f'Group {i:02}' for i in range(12)]
        for key, (_, colors) in PALETTES.items():
            with self.subTest(palette=key):
                self.assertTrue(all(is_color_like(color) for color in colors))
                self.assertGreaterEqual(len(colors), 10)
                self.assertEqual(len(colors), len(set(colors)))
                self.assertEqual(palette_preview(key).count('aria-label='), len(colors))
                result = group_color_map(groups, key, {'Group 01': '#112233', 'Removed': '#445566'})
                self.assertEqual(result['Group 01'], '#112233')
                self.assertNotIn('Removed', result)
                self.assertEqual(result['Group 00'], colors[0].lower())
                self.assertEqual(result[f'Group {len(colors):02}'], colors[0].lower())
                self.assertEqual(len(set(group_color_map(groups[:10], key).values())), 10)
        custom = palette_colors('classic', ['#010203', '#040506'])
        self.assertEqual(custom[:2], ('#010203', '#040506'))
        self.assertEqual(len(custom), 10)
        self.assertEqual(group_color_map(['A'], classic_colors=[(1., 0., 0.)]), {'A': '#ff0000'})
        self.assertIn('#ff0000', palette_preview('classic', [(1., 0., 0.)]))

    def test_removed_groups_release_slots_without_recolouring_survivors(self):
        slots = reconcile_color_slots(['A', 'B', 'C'])
        slots = reconcile_color_slots(['B', 'C'], slots)
        self.assertEqual(slots, {'B': 1, 'C': 2})
        for index in range(30):
            group = f'New {index}'
            added = reconcile_color_slots(['B', 'C', group], slots)
            self.assertEqual(added, {'B': 1, 'C': 2, group: 0})
            slots = reconcile_color_slots(['B', 'C'], added)
        self.assertEqual(reconcile_color_slots([], slots), {})

    def test_shrinking_overflow_repairs_duplicates_and_reordering_keeps_colours(self):
        groups = [f'Group {i:02}' for i in range(12)]
        slots = reconcile_color_slots(groups)
        selected = groups[:8] + groups[10:]
        slots = reconcile_color_slots(selected, slots)
        self.assertEqual(set(slots.values()), set(range(10)))
        self.assertEqual([slots[group] for group in groups[:8]], list(range(8)))
        self.assertEqual(reconcile_color_slots(selected[::-1], slots), slots)

    def test_bad_palette_rejected(self):
        for value in ('unknown', '', None, [], {}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                group_color_map({}, value)

    def test_comparison_recolours_existing_frames_and_keeps_numbers(self):
        view = ComparisonView(widgets)
        self.addCleanup(view.clear)
        view.set_frames(frames(), ['A', 'B'], color_map={'A': '#112233', 'B': '#445566'})
        view.ui.selected_index = 0
        before = view.summary.copy()
        first = view.charts['0.2% yield strength']
        self.assertEqual(first.data[0].marker.color, ('#112233', '#445566'))
        view.set_frames(frames(), ['A', 'B'], color_map={'A': '#778899', 'B': '#445566'})
        self.assertTrue(view.summary.equals(before))
        self.assertIsNot(view.charts['0.2% yield strength'], first)
        self.assertEqual(view.charts['0.2% yield strength'].data[0].marker.color, ('#778899', '#445566'))


class PaletteWorkbenchTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='palette-synthetic-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        make_fixture(self.root)
        shutil.copytree(self.root / 'data' / 'Alloy A', self.root / 'data' / 'Alloy M')
        shutil.copytree(self.root / 'data' / 'Alloy A', self.root / 'data' / 'Alloy Z')
        with redirect_stdout(io.StringIO()):
            self.app = TensileWorkbench(self.root)
        self.addCleanup(self.app.tables.inspector.clear)
        self.addCleanup(self.app.tables.comparison.clear)

    def test_save_reopen_graph_switch_and_override_without_recalculation(self):
        app = self.app
        app.override_group.value = 'Alloy A'
        self.assertEqual(app.controls['color_palette'].value, 'classic')
        with (patch.object(app.session.engine, 'specimen_properties', side_effect=AssertionError('Recalculated')),
              patch.object(app.session, 'render', side_effect=AssertionError('Rendered'))):
            app.controls['color_palette'].value = 'pastel_coastal'
        expected = palette_colors('pastel_coastal')[0].lower()
        self.assertEqual(app.override_color.value, expected)
        self.assertIn(expected, app.palette_swatches.value)
        self.assertEqual(app.tables.comparison.color_map['Alloy A'], expected)
        app.override_color_enabled.value = True
        app.override_color.value = '#112233'
        app._apply_overrides()
        app.controls['color_palette'].value = 'pastel_berry'
        self.assertEqual(app.override_color.value, '#112233')
        self.assertEqual(app.session.color_map(app.state(), app._current()['definition'])['Alloy A'], '#112233')
        with redirect_stdout(io.StringIO()):
            reopened = TensileWorkbench(self.root)
        self.addCleanup(reopened.tables.inspector.clear)
        self.addCleanup(reopened.tables.comparison.clear)
        reopened.override_group.value = 'Alloy A'
        self.assertEqual(reopened.controls['color_palette'].value, 'pastel_berry')
        self.assertEqual(reopened.override_color.value, '#112233')
        reopened._apply_graph('1')
        self.assertEqual(reopened.controls['color_palette'].value, 'classic')
        reopened._apply_graph('0')
        self.assertEqual(reopened.controls['color_palette'].value, 'pastel_berry')
        bad = deepcopy(reopened.store.data)
        bad['graphs'][0]['settings']['color_palette'] = 'missing'
        with self.assertRaises(ValueError):
            validate_project(bad)
        self.assertFalse((self.root / 'output').exists())

    def test_family_consistency_static_plotly_and_faint_individuals(self):
        session = self.app.session
        expected = palette_colors('pastel_orchard')[0].lower()
        for family in ('representative', 'landmark', 'pointwise', 'comparison', 'work_hardening',
                       'work_hardening_landmark', 'work_hardening_comparison', 'ys_vs_el', 'uts_vs_el'):
            with self.subTest(family=family):
                state = {**self.app.state(), 'family': family, 'graph_index': 0,
                         'color_palette': 'pastel_orchard', 'show_individuals': True}
                result = session.render(state)
                lines = result['figure'].axes[0].lines
                self.assertTrue(lines)
                self.assertTrue(all(to_hex(line.get_color()) == expected for line in lines))
                plotly = figure_to_plotly(result['figure'])
                self.assertTrue(all(trace.line.color == expected for trace in plotly.data))
                self.assertTrue(any(trace.opacity < 1 for trace in plotly.data))
        self.assertFalse((self.root / 'output').exists())

    def test_unselected_groups_do_not_reserve_colours_and_property_colours_unchanged(self):
        app = self.app
        app.controls['color_palette'].value = 'pastel_berry'
        app.controls['groups'].value = ('Alloy Z',)
        app.override_group.value = 'Alloy Z'
        self.assertEqual(app.override_color.value, palette_colors('pastel_berry')[0].lower())
        base = {**app.state(), 'graph_index': 0, 'family': 'properties_by_group'}
        for palette in ('classic', 'pastel_berry'):
            result = app.session.render({**base, 'color_palette': palette})
            means = {line.get_label(): to_hex(line.get_color())
                     for ax in result['figure'].axes for line in ax.lines if not line.get_label().startswith('_')}
            self.assertEqual(means, {'0.2% YS': '#1f77b4', 'UTS': '#d95f02', 'EL': '#2ca02c'})

    def test_reclaimed_colours_survive_reopen_analysis_switch_and_saved_overrides(self):
        app = self.app
        with redirect_stdout(io.StringIO()):
            app.controls['color_palette'].value = 'retro_reference'
            app.controls['groups'].value = ('Alloy A', 'Alloy Z')
            before = app.session.color_map(app.state(), {})
            app.controls['groups'].value = ('Alloy Z',)
            app.controls['groups'].value = ('Alloy M', 'Alloy Z')
        after = app.session.color_map(app.state(), {})
        self.assertEqual(after, {'Alloy M': before['Alloy A'], 'Alloy Z': before['Alloy Z']})
        app.override_group.value = 'Alloy Z'
        app.override_color_enabled.value = True
        app.override_color.value = '#112233'
        with redirect_stdout(io.StringIO()):
            app._apply_overrides()
            app.controls['groups'].value = ('Alloy M',)
            app.controls['groups'].value = ('Alloy A', 'Alloy M')
        saved = app._current()
        self.assertEqual(saved['settings'][COLOR_SLOTS], {'Alloy A': 1, 'Alloy M': 0})
        self.assertEqual(saved['definition']['color_overrides'], {'Alloy Z': '#112233'})
        expected = app.session.color_map(app.state(), saved['definition'])
        self.assertEqual(set(expected), {'Alloy A', 'Alloy M'})
        with redirect_stdout(io.StringIO()):
            reopened = TensileWorkbench(self.root)
        self.addCleanup(reopened.tables.inspector.clear)
        self.addCleanup(reopened.tables.comparison.clear)
        self.assertEqual(reopened.session.color_map(reopened.state(), reopened._current()['definition']), expected)
        reopened._apply_graph('1')
        self.assertEqual(reopened.state()[COLOR_SLOTS], {'Alloy A': 0})
        reopened._apply_graph('0')
        self.assertEqual(reopened.state()[COLOR_SLOTS], {'Alloy A': 1, 'Alloy M': 0})
        with redirect_stdout(io.StringIO()):
            reopened.controls['groups'].value = ('Alloy A', 'Alloy M', 'Alloy Z')
        self.assertEqual(reopened.session.color_map(reopened.state(), reopened._current()['definition'])['Alloy Z'], '#112233')

    def test_invalid_saved_automatic_assignments_are_rejected(self):
        for invalid in ([], None, {'A': -1}, {'A': True}, {'A': '1'}, {'': 0}):
            project = deepcopy(self.app.store.data)
            project['graphs'][0]['settings'][COLOR_SLOTS] = invalid
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_project(project)


if __name__ == '__main__':
    unittest.main()
