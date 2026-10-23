"""Spreadsheet-style clipboard edits and portable plot labels; synthetic only."""
from copy import deepcopy
import unittest
from tensile_variable_table import paste_cells
from tensile_variables import plot_text, property_chart_title


class VariableClipboardTests(unittest.TestCase):
    def setUp(self):
        self.columns = [dict(id='gas', name='Gas', unit='%', values={'A': '1', 'B': '2', 'Hidden': '9'})]
        self.groups = ['A', 'B']

    def test_rectangular_tsv_with_names_units_extra_columns_and_crlf(self):
        text = 'Gas CO_2\tTemperature\r\n%\t°C\r\n0\t500\r\n12.5\t870\r\n'
        pasted = paste_cells(self.columns, self.groups, 0, 0, text)
        self.assertEqual(pasted[0]['id'], 'gas')
        self.assertEqual(pasted[0]['values'], {'A': '0', 'B': '12.5', 'Hidden': '9'})
        self.assertTrue(pasted[1]['id'].startswith('var-'))
        self.assertEqual(pasted[1]['values'], {'A': '500', 'B': '870'})
        self.assertEqual(self.columns[0]['values']['A'], '1')

    def test_quoted_csv_bom_empty_unit_and_empty_values(self):
        pasted = paste_cells(self.columns, self.groups, 0, 0, '\ufeff"Gas, CO_2"\n\n1e-3\n\n')
        self.assertEqual(pasted[0]['name'], 'Gas, CO_2')
        self.assertEqual(pasted[0]['unit'], '')
        self.assertEqual(pasted[0]['values']['A'], '1e-3')
        self.assertEqual(pasted[0]['values']['B'], '')
        pasted = paste_cells(self.columns, self.groups, 0, 0, '"A ""quoted"" name",B\n%,mm^2\n1,2\n3,4')
        self.assertEqual(pasted[0]['name'], 'A "quoted" name')

    def test_bad_blocks_rejected_without_partial_mutation(self):
        before = deepcopy(self.columns)
        for text in ('1\n2\n3', '1,2\n3', '1\nnan', '1\ninf', '1\n=SUM(A1:A2)', '"unterminated'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                paste_cells(self.columns, self.groups, 2, 0, text)
            self.assertEqual(self.columns, before)
        for row, col in ((-1, 0), (4, 0), (2, -1), (2, 1), (True, 0)):
            with self.subTest(row=row, col=col), self.assertRaises(ValueError):
                paste_cells(self.columns, self.groups, row, col, '1')

    def test_offset_paste_clear_zero_and_quoted_cell(self):
        columns = self.columns + [dict(id='temp', name='Temp', unit='°C', values={'A': '500', 'B': '870'})]
        pasted = paste_cells(columns, self.groups, 2, 1, '\n0')
        self.assertEqual(pasted[0], columns[0])
        self.assertEqual(pasted[1]['values'], {'A': '', 'B': '0'})
        self.assertEqual(paste_cells(columns, self.groups, 3, 1, '"12.5"')[1]['values']['B'], '12.5')

    def test_portable_numeric_scripts(self):
        self.assertEqual(plot_text('CO_2; H_{12}; mm^2; m^{-3}; Na^{+1}'), 'CO₂; H₁₂; mm²; m⁻³; Na⁺¹')
        self.assertEqual(plot_text('my_variable, CO₂, mm²'), 'my_variable, CO₂, mm²')
        self.assertEqual(property_chart_title(dict(name='CO_2', unit='')), 'YS/UTS/EL vs. CO₂')
        self.assertEqual(property_chart_title(dict(name='Heat Treat Time', unit='h')),
                         'YS/UTS/EL vs. Heat Treat Time (h)')
        self.assertEqual(property_chart_title(dict(name='Area', unit=' mm^2 '), ['uts']),
                         'UTS vs. Area (mm²)')
