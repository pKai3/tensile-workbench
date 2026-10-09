"""Presentation-only group labels must never rewrite dataset identities."""
import unittest
from tensile_selection import group_display_name


class GroupDisplayNameTests(unittest.TestCase):
    def test_nested_and_flat_defaults(self):
        self.assertEqual(group_display_name('Other Users/Guofang/Project/Alloy'), 'Alloy')
        self.assertEqual(group_display_name('B09-SR'), 'B09-SR')

    def test_custom_labels_keep_precedence_and_slashes(self):
        group = 'Owner/Project/Alloy'
        saved = {group: '7.5% CO₂ / Ar'}
        overrides = {group: 'My graph label'}
        self.assertEqual(group_display_name(group, saved), '7.5% CO₂ / Ar')
        self.assertEqual(group_display_name(group, saved, overrides), 'My graph label')
        self.assertEqual(saved, {group: '7.5% CO₂ / Ar'})

    def test_legacy_auto_saved_path_is_not_a_publication_label(self):
        group = 'Other Users/Guofang/Alloy'
        self.assertEqual(group_display_name(group, {group: group}), 'Alloy')
        self.assertEqual(group_display_name(group, {}, {group: group}), 'Alloy')

    def test_bundled_label_and_distinct_source_ids_are_preserved(self):
        group = 'Sample data / Demo_Alloy'
        self.assertEqual(group_display_name(group, {group: 'Alloy (sample)'}), 'Alloy (sample)')
        keys = ['Owner A/Alloy', 'Owner B/Alloy']
        self.assertEqual([group_display_name(k) for k in keys], ['Alloy', 'Alloy'])
        self.assertEqual(len(set(keys)), 2)


if __name__ == '__main__':
    unittest.main()
