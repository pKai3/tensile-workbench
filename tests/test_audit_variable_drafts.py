from copy import deepcopy
import unittest
import ipywidgets as w
from tensile_variables import GroupVariablesView, merge_variable_drafts


class VariableDraftAuditTests(unittest.TestCase):
    def setUp(self):
        self.saved = {'gas': {'name': 'Gas', 'unit': '%', 'values': {'A': 1., 'B': 2.}}}
        self.view = GroupVariablesView(w, lambda: self.saved, lambda: ['A', 'B'], self.save)
        self.view.refresh(['A'])
        self.addCleanup(self.view.ui.close)

    def save(self, value): self.saved = deepcopy(value)

    def edit(self, group, value):
        columns = deepcopy(self.view.table.columns)
        columns[0]['values'][group] = value
        self.view.table.columns = columns

    def test_save_merges_only_edited_cells_and_keeps_external_column(self):
        self.edit('A', '3')
        self.saved['gas']['values']['B'] = 9.
        self.saved['temp'] = {'name': 'Temperature', 'unit': 'C', 'values': {'A': 750.}}
        self.view.save_all.click()
        self.assertEqual(self.saved['gas']['values'], {'A': 3., 'B': 9.})
        self.assertEqual(self.saved['temp']['values']['A'], 750.)

    def test_same_cell_conflict_is_rejected_without_discarding_draft(self):
        self.edit('A', '3')
        self.saved['gas']['values']['A'] = 4.
        self.view.refresh(['A'], force=True)
        self.view.save_all.click()
        self.assertIn('conflict', self.view.table.notice)
        self.assertEqual(self.saved['gas']['values']['A'], 4.)
        self.assertEqual(self.view.table.columns[0]['values']['A'], '3')

    def test_reload_preserves_clear_and_refreshes_untouched_cells(self):
        self.edit('A', '')
        self.saved['gas']['values']['B'] = 6.
        self.view.refresh(['A', 'B'], force=True)
        self.assertEqual(self.view.table.columns[0]['values'], {'A': '', 'B': '6.0'})
        self.view.save_all.click()
        self.assertEqual(self.saved['gas']['values'], {'B': 6.})

    def test_deleted_edited_variable_cannot_be_resurrected(self):
        self.edit('A', '3')
        del self.saved['gas']
        self.view.save_all.click()
        self.assertIn('deleted elsewhere', self.view.table.notice)
        self.assertEqual(self.saved, {})

    def test_discard_resolves_conflict_without_writing_saved_state(self):
        self.edit('A', '3')
        self.saved['gas']['values']['A'] = 4.
        self.view.save_all.click()
        self.view.discard.click()
        self.assertEqual(self.view.table.columns[0]['values']['A'], '4.0')
        self.assertEqual(self.saved['gas']['values']['A'], 4.)
        self.edit('A', '5')
        self.view.save_all.click()
        self.assertEqual(self.saved['gas']['values']['A'], 5.)


if __name__ == '__main__': unittest.main()
