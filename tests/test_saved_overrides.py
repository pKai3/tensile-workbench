"""Saved override lifecycle on synthetic settings only; no research data."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from tensile_fit import fit_policy
from tensile_moves import forget_group, migrate_settings, references
from tensile_overrides import (DISABLED, change_overrides, clear_disabled, override_entries,
                               override_rows, validate_disabled)
from tensile_selection import selection_state
from workbench_project import validate_project


class SavedOverrideTests(unittest.TestCase):
    def setUp(self):
        self.project = json.loads((Path(__file__).resolve().parents[1] / 'tensile_workbench_defaults.json').read_text())
        self.ident = 'Owner/Alloy/a.csv'
        self.project['specimen_exclusions'] = {self.ident: 'Grip slip'}
        self.project['specimen_data_modes'] = {'Owner/Alloy/b.csv': {'mode':'exclude_shape', 'reason':'Shape'}}
        fit = {'mode':'range', 'strain_bounds':[.123456, .456789], 'source_sha256':'a'*64,
               'reason':'Seating', 'saved_at':'2026-10-09', 'automatic_snapshot':{}}
        endpoint = {'row':123, 'strain_pct':12.5, 'source_sha256':'a'*64,
                    'reason':'Separation', 'saved_at':'2026-10-09', 'automatic_snapshot':{}}
        self.project['specimen_fit_overrides'] = {self.ident:fit}
        self.project['specimen_failure_overrides'] = {self.ident:endpoint}
        self.graph = self.project['graphs'][0]
        self.graph['settings']['groups'] = []  # All overrides remain visible.
        self.graph['definition']['specimen_inclusion_overrides'] = {
            self.ident:{'included':True, 'mode':'all', 'reason':'Graph exception'}}
        self.project['display_names']['Owner/Alloy'] = 'Alloy'

    def entries(self, project=None, kind=None):
        return [row for row in override_entries(self.project if project is None else project)
                if kind is None or row['kind'] == kind]

    def test_disable_reenable_preserves_exact_values_and_active_policies(self):
        original = deepcopy(self.project)
        result = change_overrides(self.project, self.entries(), 'disable')
        validate_project(result)
        self.assertEqual(self.project, original)
        self.assertFalse(fit_policy(result)['specimen_fit_overrides'])
        self.assertFalse(fit_policy(result)['specimen_failure_overrides'])
        record = {'specimen_id':self.ident, 'source_file':'synthetic'}
        self.assertTrue(selection_state(record, result['graphs'][0]['definition'], result)['included'])
        self.assertTrue(all(not row['enabled'] for row in self.entries(result)))
        restored = change_overrides(result, self.entries(result), 'enable')
        validate_project(restored)
        self.assertEqual(restored, original)

    def test_disabled_graph_exception_restores_global_exclusion(self):
        result = change_overrides(self.project, self.entries(kind='specimen_inclusion_overrides'), 'disable')
        policy = selection_state({'specimen_id':self.ident, 'source_file':'synthetic'},
                                 result['graphs'][0]['definition'], result)
        self.assertEqual(policy['scope'], 'global')
        self.assertFalse(policy['included'])

    def test_remove_only_selected_override_and_does_not_add_a_log(self):
        result = change_overrides(self.project, self.entries(kind='specimen_fit_overrides'), 'remove')
        self.assertFalse(result['specimen_fit_overrides'])
        self.assertEqual(result['specimen_exclusions'], self.project['specimen_exclusions'])
        self.assertEqual(set(result), set(self.project))

    def test_stale_selection_aborts_the_entire_batch(self):
        selected = self.entries()
        self.project['specimen_exclusions'][self.ident] = 'New reason'
        original = deepcopy(self.project)
        with self.assertRaisesRegex(ValueError, 'changed since selection'):
            change_overrides(self.project, selected, 'remove')
        self.assertEqual(original, self.project)

    def test_new_policy_cannot_be_shadowed_by_reenable(self):
        result = change_overrides(self.project, self.entries(kind='specimen_exclusions'), 'disable')
        result['specimen_data_modes'][self.ident] = {'mode':'no_strain', 'reason':'AVE'}
        with self.assertRaisesRegex(ValueError, 'Another data-use policy'):
            change_overrides(result, self.entries(result, 'specimen_exclusions'), 'enable')
        self.assertIn(self.ident, result[DISABLED]['specimen_exclusions'])

    def test_new_explicit_edit_clears_parked_previous_override(self):
        result = change_overrides(self.project, self.entries(kind='specimen_fit_overrides'), 'disable')
        clear_disabled(result, ('specimen_fit_overrides',), self.ident)
        self.assertNotIn(DISABLED, result)

    def test_rows_include_unselected_and_unavailable_with_natural_sort(self):
        self.project['specimen_exclusions']['Other/Alloy/a10.csv'] = 'Unavailable'
        self.project['specimen_exclusions']['Other/Alloy/a2.csv'] = 'Unavailable'
        rows = override_rows(self.project, {self.ident:'Owner/Alloy'}, {self.ident:'Wall specimen 2'})
        self.assertTrue(any(row['specimen'] == 'Wall specimen 2' and row['availability'] == 'Available' for row in rows))
        missing = [row for row in rows if row['group'] == 'Other/Alloy']
        self.assertEqual([row['specimen'] for row in missing], ['a2','a10'])
        self.assertTrue(all(row['availability'] == 'Unavailable' for row in missing))
        self.assertIn('0.12346', next(row['setting'] for row in rows if row['type'] == 'Elastic fit'))

    def test_disabled_settings_are_referenced_migrated_and_forgotten(self):
        result = change_overrides(self.project, self.entries(), 'disable')
        self.assertIn(self.ident, references(result)[1])
        new = 'Partner/Alloy'
        mapping = {self.ident:new+'/a.csv', 'Owner/Alloy/b.csv':new+'/b.csv'}
        moved = migrate_settings(result, {'old':'Owner/Alloy', 'new':new, 'mapping':mapping}, audit=False)
        self.assertIn(new+'/a.csv', moved[DISABLED]['specimen_fit_overrides'])
        self.assertIn(new+'/a.csv', moved['graphs'][0]['definition'][DISABLED]['specimen_inclusion_overrides'])
        validate_project(moved)
        forgotten = forget_group(moved, new)
        self.assertFalse(self.entries(forgotten))
        self.assertNotIn(DISABLED, forgotten)

    def test_invalid_or_simultaneously_active_disabled_settings_rejected(self):
        result = deepcopy(self.project)
        result[DISABLED] = {'specimen_exclusions':deepcopy(result['specimen_exclusions'])}
        with self.assertRaisesRegex(ValueError, 'both active and disabled'):
            validate_disabled(result)

    def test_ui_confirmation_filter_selection_and_no_curve_loading(self):
        import ipywidgets as w
        from tensile_override_view import SavedOverridesView
        class Store:
            def __init__(self, project):
                self.data = deepcopy(project)
            def save(self, project):
                validate_project(project)
                self.data = deepcopy(project)
        store = Store(self.project)
        session = SimpleNamespace(files={}, source_roots={}, _records={})
        saved = []
        view = SavedOverridesView(w, store, session, before_apply=lambda:True,
                                  after_apply=lambda:saved.append(True))
        self.addCleanup(view.ui.close)
        self.addCleanup(view.table.close)
        view.refresh()
        view.kind.value = 'specimen_fit_overrides'
        view.table.selected = [view.table.rows[0]['id']]
        view.remove.click()
        self.assertIn(self.ident, store.data['specimen_fit_overrides'])
        view.cancel.click()
        self.assertFalse(saved)
        view.remove.click()
        view.confirm_remove.click()
        self.assertFalse(store.data['specimen_fit_overrides'])
        self.assertEqual(saved, [True])
        view.kind.value = ''
        view.table.selected = [view.table.rows[0]['id']]
        view.state.value = 'disabled'
        self.assertEqual(view.table.selected, [])


if __name__ == '__main__':
    unittest.main()
