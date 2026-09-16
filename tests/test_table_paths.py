from html.parser import HTMLParser
from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tensile_tables import PropertyTablesView


class Elements(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.paths = []
        self.tail_text = []
        self.in_textarea = False
        self.in_bdi = False

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        if tag == 'textarea':
            self.in_textarea = True
            self.paths.append('')
        if tag == 'bdi':
            self.in_bdi = True
            self.tail_text.append('')

    def handle_endtag(self, tag):
        if tag == 'textarea':
            self.in_textarea = False
        if tag == 'bdi':
            self.in_bdi = False

    def handle_data(self, text):
        if self.in_textarea:
            self.paths[-1] += text
        if self.in_bdi:
            self.tail_text[-1] += text


class PathCellTests(unittest.TestCase):
    def test_long_paths_expand_exactly_without_changing_export_data(self):
        path = '/some/very long folder/' * 12 + 'coupon 1.csv'
        summary = 'C:\\Research\\A & B\\' * 10 + 'summary.csv'
        frame = pd.DataFrame({'Source File': [path], 'Instron Summary CSV': [summary], 'Value': [1.23456]})
        before = frame.copy(deep=True)
        html = PropertyTablesView._html(frame)
        parser = Elements()
        parser.feed(html)
        self.assertEqual(parser.paths, [path, summary])
        self.assertEqual(parser.tail_text, [path, summary])
        self.assertEqual(sum(tag == 'details' for tag, attrs in parser.tags), 2)
        for tag, attrs in parser.tags:
            if tag == 'textarea':
                self.assertIn('readonly', attrs)
                self.assertIn('Full ', attrs['aria-label'])
        self.assertIn('text-overflow:ellipsis', html)
        self.assertIn('1.235', html)
        pd.testing.assert_frame_equal(frame, before)

    def test_paths_other_cells_and_headers_are_html_escaped(self):
        path = '/folder/</textarea><script>alert("bad")</script>&file.csv'
        frame = pd.DataFrame({'Source File': [path], '<img src=x onerror=bad>': ['<svg onload=bad>']})
        html = PropertyTablesView._html(frame)
        parser = Elements()
        parser.feed(html)
        self.assertEqual(parser.paths, [path])
        self.assertFalse(any(tag in ('script', 'img', 'svg') for tag, attrs in parser.tags))
        self.assertIn('&lt;svg onload=bad&gt;', html)
        self.assertIn('&lt;img src=x onerror=bad&gt;', html)

    def test_missing_paths_are_not_clickable_and_short_paths_are_not_sliced(self):
        frame = pd.DataFrame({'Source File': ['', None, np.nan, 'tiny.csv'], 'Number': [1, 2, 3, 4]})
        parser = Elements()
        parser.feed(PropertyTablesView._html(frame))
        self.assertEqual(parser.paths, ['tiny.csv'])
        self.assertEqual(sum(tag == 'details' for tag, attrs in parser.tags), 1)

    def test_number_formats_and_ordinary_tables_stay_readable(self):
        html = PropertyTablesView._html(pd.DataFrame({'Group': ['A&B'], 'n': [3], 'Mean': [2.34567], 'SD': [np.nan]}))
        self.assertIn('A&amp;B', html)
        self.assertIn('2.346', html)
        self.assertIn('>3<', html)
        self.assertNotIn('<details', html)


if __name__ == '__main__':
    unittest.main()
