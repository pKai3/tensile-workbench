"""Summary display alignment; synthetic values only, no data loading or plots."""
from xml.etree import ElementTree
import unittest

import numpy as np
import pandas as pd

from tensile_tables import METRICS, property_table_sources, summary_html, summary_wide


def summary_fixture():
    rows = []
    for i, group in enumerate(('Alloy A', 'Alloy B', 'Alloy C', 'Single', 'Missing')):
        n = (3, 3, 3, 1, 0)[i]
        for prop, unit, _, _ in METRICS:
            for source, _ in property_table_sources(prop):
                mean = (723.4123, 9.2, 1000.357, -12.5, np.nan)[i]
                sd = (11.153, .04, 105.07, np.nan, np.nan)[i]
                count = n
                if prop == 'Uniform elongation':
                    mean, sd = ((4.85, 4.5, 2.92, 7.05, np.nan)[i],
                                (.64, .98, .52, np.nan, np.nan)[i])
                if source == 'Reconstruct' and i == 1:
                    count, mean, sd = 0, np.nan, np.nan
                if prop == 'Tensile toughness' and source == 'Instron':
                    count, mean, sd = 0, np.nan, np.nan
                rows.append({'Group': group, 'Property': prop, 'Unit': unit, 'Source': source,
                             'Mean': mean, 'SD': sd, 'n': count,
                             'Selected Specimens': 3, 'Available Specimens': 4})
    return pd.DataFrame(rows)


def table_rows(html):
    return ElementTree.fromstring('<root>' + html + '</root>').findall('.//tbody/tr')


class SummaryAlignmentTests(unittest.TestCase):
    def test_same_three_tracks_down_each_property_source_column(self):
        html = summary_html(summary_fixture())
        rows = table_rows(html)
        columns = len(rows[0].findall('td'))
        for col in range(2, columns):
            styles = set()
            for row in rows:
                stat = row.findall('td')[col].find('span')
                if stat is not None:
                    styles.add(stat.get('style'))
                    self.assertEqual([part.get('class') for part in stat],
                                     ['tw-summary-mean', 'tw-summary-pm', 'tw-summary-sd'])
            self.assertEqual(len(styles), 1)
        first = rows[0].findall('td')[2].find('span')
        self.assertEqual([part.text for part in first], ['723.41', '±', '11.15'])
        self.assertIn('--tw-mean-width:7ch;', first.get('style'))
        self.assertIn('--tw-sd-width:6ch;', first.get('style'))
        uniform = rows[0].findall('td')[6].find('span')
        self.assertIn('--tw-mean-width:4ch;', uniform.get('style'))
        self.assertIn('--tw-sd-width:4ch;', uniform.get('style'))
        self.assertIn('font-variant-numeric:tabular-nums lining-nums', html)

    def test_singletons_and_missing_results_keep_alignment_without_fake_sd(self):
        rows = table_rows(summary_html(summary_fixture()))
        single = rows[3].findall('td')[2]
        self.assertEqual([part.text for part in single.find('span')], ['-12.50', None, None])
        self.assertEqual(single.find('small').text, 'n = 1')
        missing = rows[4].findall('td')[2]
        self.assertEqual([part.text for part in missing.find('span')], ['—', None, None])
        self.assertEqual(missing.find('small').text, 'n = 0')
        self.assertEqual(single.find('span').get('style'), missing.find('span').get('style'))
        # Completely unavailable Instron toughness needs no space for ±/SD.
        toughness = rows[0].findall('td')[12].find('span')
        self.assertIn('--tw-pm-width:0px;', toughness.get('style'))
        self.assertIn('--tw-sd-width:0ch;', toughness.get('style'))
        self.assertIn('--tw-stat-gap:0px;', toughness.get('style'))
        # Reconstruction unavailable for Alloy B remains genuinely blank.
        reconstruct = rows[1].findall('td')[10]
        self.assertEqual(list(reconstruct), [])
        self.assertIsNone(reconstruct.text)

    def test_display_does_not_mutate_values_or_excel_schema(self):
        details = summary_fixture()
        before = details.copy(deep=True)
        exported = summary_wide(details)
        summary_html(details)
        pd.testing.assert_frame_equal(details, before)
        pd.testing.assert_frame_equal(summary_wide(details), exported)
        self.assertEqual(details.iloc[0]['Mean'], 723.4123)

    def test_escaped_group_names_and_empty_table(self):
        details = summary_fixture()
        details['Group'] = details['Group'].replace({'Alloy A': '<script>alert("x")</script>&'})
        html = summary_html(details)
        self.assertNotIn('<script>', html)
        self.assertEqual(table_rows(html)[0].find('td').text, '<script>alert("x")</script>&')
        self.assertEqual(summary_html(pd.DataFrame()), '<p>No matching groups.</p>')


if __name__ == '__main__':
    unittest.main()
