"""Selectable Summary reuses export numbers and copies separate mean/SD cells."""
import csv
import io
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest

import ipywidgets as w
import pandas as pd

from selection_fixture import make_fixture
from tensile_summary_copy import SummaryCopyTable, summary_copy_rows
from tensile_tables import PropertyTablesView, summary_copy_frame, summary_wide
from tensile_workbench import PreviewSession
from test_summary_alignment import summary_fixture


class SummaryCopyTests(unittest.TestCase):
    def test_compact_columns_and_reconstruct_elongation_are_independent(self):
        wide = summary_wide(summary_fixture())
        compact = summary_copy_frame(wide)
        self.assertEqual(list(compact.columns), [
            'Group', '0.2% YS (MPa) · Calc · Mean', 'UTS (MPa) · Calc · Mean',
            'Elongation (%) · Calc · Mean'])
        expanded = summary_copy_frame(wide, source='both', statistics='sd',
                                      reconstruct=True)
        self.assertEqual(list(expanded.columns), [
            'Group',
            '0.2% YS (MPa) · Calc · Mean', '0.2% YS (MPa) · Calc · SD',
            '0.2% YS (MPa) · Instron · Mean', '0.2% YS (MPa) · Instron · SD',
            'UTS (MPa) · Calc · Mean', 'UTS (MPa) · Calc · SD',
            'UTS (MPa) · Instron · Mean', 'UTS (MPa) · Instron · SD',
            'Elongation (%) · Calc · Mean', 'Elongation (%) · Calc · SD',
            'Elongation (%) · Instron · Mean', 'Elongation (%) · Instron · SD',
            'Elongation (%) · Reconstruct · Mean', 'Elongation (%) · Reconstruct · SD'])
        full = summary_copy_frame(wide, source='instron', statistics='all',
                                  properties='all', reconstruct=True, group_counts=True)
        self.assertEqual(list(full.columns[:3]), ['Group', 'Included n', 'Available n'])
        self.assertIn('Elongation (%) · Reconstruct · n', full.columns)
        self.assertNotIn('0.2% YS (MPa) · Calc · Mean', full.columns)
        self.assertIn('Uniform elongation (%) · Instron · Mean', full.columns)

    def test_flat_summary_keeps_mean_sd_and_n_in_distinct_cells(self):
        wide = summary_wide(summary_fixture())
        columns, rows = summary_copy_rows(wide)
        self.assertEqual(columns, list(wide.columns))
        mean = columns.index('0.2% YS (MPa) · Calc · Mean')
        sd = columns.index('0.2% YS (MPa) · Calc · SD')
        count = columns.index('0.2% YS (MPa) · Calc · n')
        self.assertEqual((rows[0][mean], rows[0][sd], rows[0][count]), (723.4123, 11.153, 3))
        self.assertEqual((rows[3][sd], rows[3][count]), (None, 1))
        self.assertEqual((rows[4][mean], rows[4][sd], rows[4][count]), (None, None, 0))

    def test_csv_and_tsv_copy_keep_header_quoting_and_numeric_precision(self):
        details = summary_fixture()
        details['Group'] = details['Group'].replace({'Alloy A': 'Alloy, "A"'})
        columns, rows = summary_copy_rows(summary_wide(details))
        table = SummaryCopyTable()
        table.set_data(columns, rows)
        for delimiter, text in ((',', table.csv_text), ('\t', table.tsv_text)):
            parsed = list(csv.reader(io.StringIO(text), delimiter=delimiter))
            self.assertEqual(parsed[0], columns)
            self.assertEqual(parsed[1][0], 'Alloy, "A"')
            self.assertEqual(parsed[1][columns.index('0.2% YS (MPa) · Calc · Mean')], '723.4123')
            self.assertEqual(parsed[4][columns.index('0.2% YS (MPa) · Calc · SD')], '')
            self.assertEqual(len(parsed), len(rows) + 1)
        table.close()

    def test_button_in_summary_opens_matching_filtered_table(self):
        view = PropertyTablesView(w)
        self.addCleanup(view.clear)
        self.assertIs(view.tabs.children[0].children[0].children[0], view.summary_data_button)
        self.assertTrue(view.summary_data_button.disabled)
        details = summary_fixture()
        view.filter.value = 'Alloy B'
        view.frames = {'tensile_summary_details': details}
        view.summary_data_button.disabled = False
        view.summary_data_button.click()
        self.assertEqual(view.summary_data_popup.overlay.layout.display, 'flex')
        self.assertEqual(len(view.summary_copy.rows), 1)
        self.assertEqual(view.summary_copy.rows[0][0], 'Alloy B')
        self.assertEqual(len(view.summary_copy.columns), 4)
        view.summary_source.value = 'both'
        view.summary_statistics.value = 'sd'
        view.summary_reconstruct.value = True
        self.assertIn('Elongation (%) · Reconstruct · SD', view.summary_copy.columns)
        self.assertEqual(list(csv.reader(io.StringIO(view.summary_copy.tsv_text), delimiter='\t'))[0],
                         view.summary_copy.columns)
        view.clear()
        self.assertTrue(view.summary_data_button.disabled)
        self.assertEqual(view.summary_data_popup.overlay.layout.display, 'none')

    def test_current_analysis_summary_matches_export_numbers(self):
        with tempfile.TemporaryDirectory(prefix='summary-copy-synthetic-') as temp:
            root = Path(temp)
            project = make_fixture(root)
            session = PreviewSession(root, project)
            with redirect_stdout(io.StringIO()):
                current = session.property_tables(session.defaults(), session.graphs[0])
            view = PropertyTablesView(w)
            self.addCleanup(view.clear)
            view.set_frames(current)
            view.summary_data_button.click()
            expected = summary_copy_frame(summary_wide(view._filtered(current['tensile_summary_details'])))
            self.assertEqual(view.summary_copy.columns, list(expected.columns))
            for copied, (_, original) in zip(view.summary_copy.rows, expected.iterrows()):
                for value, source in zip(copied, original):
                    if pd.isna(source):
                        self.assertIsNone(value)
                    elif isinstance(source, (int, float)):
                        self.assertAlmostEqual(value, source)
                    else:
                        self.assertEqual(value, source)
            view.summary_source.value = 'both'
            view.summary_statistics.value = 'all'
            view.summary_properties.value = 'all'
            view.summary_reconstruct.value = True
            view.summary_group_counts.value = True
            self.assertEqual(set(view.summary_copy.columns),
                             set(summary_wide(current['tensile_summary_details']).columns))
            self.assertFalse((root / 'output').exists())


if __name__ == '__main__':
    unittest.main()
