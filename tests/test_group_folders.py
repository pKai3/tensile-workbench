"""Folder discovery and selection only; no research files or plot generation."""
from pathlib import Path
import tempfile
import unittest

import ipywidgets as w

from tensile_group_picker import GroupCheckboxes, group_tree
from tensile_selection import SAMPLE_GROUP_PREFIX, discover_sample_groups


class FolderDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tensile-folders-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def file(self, relative):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        return path

    def test_flat_groups_and_nested_exports_retain_identity(self):
        a = self.file('As built/specimen.csv')
        b = self.file('Heat treated/instrument_exports/specimen.csv')
        c = self.file('ST/test.is_tens_Exports/test_1.csv')
        self.assertEqual(discover_sample_groups(self.root), {
            'As built': [a], 'Heat treated': [b], 'ST': [c]})

    def test_arbitrary_depth_and_duplicate_leaf_names_do_not_pool_groups(self):
        deep = '/'.join(['Guofang', 'Project'] + [f'level{i}' for i in range(20)])
        first = self.file(f'{deep}/Sample X/specimen.csv')
        second = self.file(f'{deep}/Sample Y/specimen.csv')
        other = self.file('Colleague/Sample X/specimen.csv')
        self.assertEqual(discover_sample_groups(self.root), {
            f'{deep}/Sample X': [first], f'{deep}/Sample Y': [second],
            'Colleague/Sample X': [other]})

    def test_instrument_file_or_summary_keeps_nested_runs_in_same_group(self):
        self.file('Owner/Project/Alloy/test.is_tens')
        a = self.file('Owner/Project/Alloy/run1/coupon.csv')
        b = self.file('Owner/Project/Alloy/run2/coupon.csv')
        summary = self.file('Owner/Other/summary.csv')
        c = self.file('Owner/Other/run3/coupon.csv')
        self.assertEqual(discover_sample_groups(self.root), {
            'Owner/Project/Alloy': [a, b], 'Owner/Other': sorted([summary, c])})

    def test_hard_ignore_applies_to_every_folder_level_and_filename(self):
        good = self.file('Owner/Project/Alloy/good.csv')
        self.file('Owner/Project/Alloy/bad!.csv')
        self.file('Owner/Project/Alloy/!run/ignored.csv')
        self.file('Owner/!Project/Alloy/coupon.csv')
        self.file('!Owner/Project/Alloy/coupon.csv')
        self.file('Empty/!only.csv')
        self.assertEqual(discover_sample_groups(self.root), {'Owner/Project/Alloy': [good]})


class FolderPickerTests(unittest.TestCase):
    def setUp(self):
        self.groups = ('Flat', 'Guofang/Project/Batch/Sample X',
                       'Guofang/Project/Batch/Sample Y', 'Guofang/Other/Sample X',
                       'Colleague/Sample X')
        self.selection = w.SelectMultiple(options=self.groups, value=('Flat',))
        self.picker = GroupCheckboxes(w, self.selection)
        self.addCleanup(self.close_widgets)

    def close_widgets(self):
        for widget in self.picker._owned:
            widget.close()
        for widget in self.picker.ui.children:
            widget.close()
        self.picker.ui.close()
        self.selection.close()

    def test_parent_selects_descendants_once_and_preserves_other_groups(self):
        changes = []
        self.selection.observe(lambda change: changes.append(change['new']), names='value')
        self.picker.select_folder(('folder:Guofang',), True)
        self.assertEqual(self.selection.value, self.groups[:4])
        self.assertEqual(len(changes), 1)
        self.assertEqual(self.picker.folder_boxes[('folder:Guofang',)].state, 'all')
        self.assertEqual(self.picker.folder_boxes[('folder:Colleague',)].state, 'none')
        self.picker.select_folder(('folder:Guofang',), False)
        self.assertEqual(self.selection.value, ('Flat',))
        self.assertEqual(len(changes), 2)

    def test_partial_leaf_selection_updates_every_ancestor(self):
        self.picker.boxes[self.groups[1]].value = True
        for path in (('folder:Guofang',), ('folder:Guofang', 'folder:Project'),
                     ('folder:Guofang', 'folder:Project', 'folder:Batch')):
            self.assertEqual(self.picker.folder_boxes[path].state, 'some')
        self.picker.select_folder(('folder:Guofang', 'folder:Project'), True)
        self.assertEqual(self.picker.folder_boxes[('folder:Guofang', 'folder:Project')].state, 'all')
        self.assertEqual(self.picker.folder_boxes[('folder:Guofang',)].state, 'some')
        self.selection.value = (self.groups[-1],)  # Switching graph selections.
        self.assertEqual(self.picker.folder_boxes[('folder:Guofang',)].state, 'none')
        self.assertEqual(self.picker.folder_boxes[('folder:Colleague',)].state, 'all')
        self.picker.clear_button.click()
        self.assertEqual(self.selection.value, ())

    def test_reload_and_unavailable_selection_keep_full_ids(self):
        missing = 'Guofang/Project/Missing'
        options = [(g, g) for g in self.groups] + [(missing + ' (unavailable)', missing)]
        self.selection.options = options
        self.selection.value = (missing,)
        self.assertEqual(self.picker.boxes[missing].description, 'Missing (unavailable)')
        self.assertEqual(self.picker.folder_boxes[('folder:Guofang',)].state, 'some')
        self.assertIn(missing, self.picker.summary.value)
        self.assertEqual(self.picker.boxes[self.groups[1]].description, 'Sample X')

    def test_bundled_examples_and_research_named_sample_data_stay_distinct(self):
        real = 'Sample data/Demo_Alloy'
        bundled = SAMPLE_GROUP_PREFIX + 'Demo_Alloy'
        self.selection.options = [(real, real), ('Alloy (sample)', bundled)]
        self.picker.select_folder(('bundled',), True)
        self.assertEqual(self.selection.value, (bundled,))
        self.assertEqual(self.picker.folder_boxes[('folder:Sample data',)].state, 'none')
        self.picker.select_folder(('folder:Sample data',), True)
        self.assertEqual(set(self.selection.value), {real, bundled})

    def test_tree_has_no_fixed_depth_limit(self):
        path = '/'.join([f'Folder{i}' for i in range(24)] + ['Alloy'])
        self.selection.options = [path]
        self.picker.select_folder(('folder:Folder0',), True)
        self.assertEqual(self.selection.value, (path,))
        self.assertEqual(len(self.picker.folder_boxes), 24)
        node = group_tree([path])
        for i in range(24):
            node = node['folders'][f'folder:Folder{i}']
        self.assertEqual(node['groups'], [('Alloy', path)])


if __name__ == '__main__':
    unittest.main()
