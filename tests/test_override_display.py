"""Presentation-only checks: compact override cells must preserve export data."""
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tensile_tables import PropertyTablesView


class Markup(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.tags = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


class OverrideDisplayTests(unittest.TestCase):
    def test_range_is_compact_collapsed_and_original_json_unchanged(self):
        saved = {'mode': 'range', 'strain_bounds': [.12, .5],
                 'reason': 'bad fit', 'saved_at': '2026-09-17T13:29:53.990293+10:00',
                 'automatic_snapshot': {'Yield (MPa)': 719.9033338529389, 'Elastic fit R2': .9867891},
                 'automatic_fit_fractions': [.2, .5]}
        raw = json.dumps(saved)
        frame = pd.DataFrame({'Override Definition': [raw], 'Override Saved At': [saved['saved_at']]})
        before = frame.copy(deep=True)
        html = PropertyTablesView._html(frame)
        details = [attrs for tag, attrs in Markup(html).tags if tag == 'details']
        self.assertEqual(len(details), 1)
        self.assertNotIn('open', details[0])
        self.assertIn('Manual range', html)
        self.assertIn('0.1200–0.5000% strain', html)
        self.assertIn('20–50% UTS', html)
        self.assertIn('719.903', html)
        self.assertNotIn('719.9033338529389', html)
        self.assertNotIn('automatic_snapshot', html)
        self.assertIn('2026-09-17 13:29', html)
        self.assertIn('title="' + saved['saved_at'] + '"', html)
        self.assertIn('max-height:220px;overflow:auto', html)
        pd.testing.assert_frame_equal(frame, before)

    def test_line_includes_endpoint_coordinates(self):
        saved = {'mode': 'line', 'strain_bounds': [.1, .3], 'endpoints': [[.1, 107.5], [.3, 307.5]]}
        html = PropertyTablesView._html(pd.DataFrame({'Override Definition': [json.dumps(saved)]}))
        for text in ('Manual line', 'Start stress (MPa)', 'End stress (MPa)', '107.5', '307.5'):
            self.assertIn(text, html)

    def test_missing_overrides_do_not_make_controls(self):
        html = PropertyTablesView._html(pd.DataFrame({'Override Definition': ['', None, np.nan],
                                                     'Override Saved At': ['', None, np.nan]}))
        self.assertNotIn('<details', html)

    def test_unexpected_records_and_timestamps_cannot_inject_html(self):
        payload = '</pre><script>alert(1)</script><img src=x onerror=bad>'
        for value in (payload, json.dumps({'mode': payload}), 'null', '[]'):
            html = PropertyTablesView._html(pd.DataFrame({'Override Definition': [value],
                                                         'Override Saved At': [payload]}))
            self.assertIn('Unrecognised saved record', html)
            self.assertFalse(any(tag in ('script', 'img') for tag, _ in Markup(html).tags))


if __name__ == '__main__':
    unittest.main()
