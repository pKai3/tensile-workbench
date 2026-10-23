"""User-supplied group/specimen variables, shared by saved graphs."""
from copy import deepcopy
from html import escape
import math
import re
import uuid
from tensile_order import ordered_groups
from tensile_selection import valid_specimen_id
from tensile_locations import REQUIRED_VARIABLES, SPECIMEN_COUNT, whole_number


def validate_variables(variables, *, scope='group'):
    if not isinstance(variables, dict):
        raise ValueError('Custom variables must be a mapping.')
    names = set()
    for ident, variable in variables.items():
        if not isinstance(ident, str) or not ident or not isinstance(variable, dict):
            raise ValueError('Invalid custom variable.')
        name, unit = variable.get('name'), variable.get('unit', '')
        if not isinstance(name, str) or not name.strip() or name.strip().casefold() in names:
            raise ValueError('Variable names must be nonempty and unique.')
        names.add(name.strip().casefold())
        if not isinstance(unit, str):
            raise ValueError('Variable units must be text.')
        required = REQUIRED_VARIABLES.get(scope, {}).get(ident)
        if required and (name != required['name'] or unit != required['unit']):
            raise ValueError(required['name'] + ' is a permanent variable; its name and unit cannot be changed.')
        values = variable.get('values', {})
        if not isinstance(values, dict):
            raise ValueError('Variable values must map identities to numbers.')
        for group, value in values.items():
            if (not isinstance(group, str) or not group or isinstance(value, bool)
                    or not isinstance(value, (float, int)) or not math.isfinite(value)):
                raise ValueError('Variable values must be finite numbers. Leave missing values blank.')
            if scope == 'specimen' and not valid_specimen_id(group):
                raise ValueError('Specimen variable values need relative specimen IDs, not display names or absolute paths.')
            if required and (not whole_number(value) or (ident == SPECIMEN_COUNT and value < 0)):
                raise ValueError(required['name'] + ' must use whole numbers' +
                                 (' greater than or equal to zero.' if ident == SPECIMEN_COUNT else '.'))


def plot_text(text):
    """Portable numeric scripts for Matplotlib, Plotly and exported figures."""
    def script(match):
        alphabet = '₀₁₂₃₄₅₆₇₈₉₊₋' if match[1] == '_' else '⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻'
        return (match[2] or match[3]).translate(str.maketrans('0123456789+-', alphabet))
    return re.sub(r'([_^])(?:\{([+-]?\d+)\}|([+-]?\d+))', script, text)


def variable_label(variable, *, for_plot=False):
    name, unit = variable['name'].strip(), variable.get('unit', '').strip()
    label = f'{name} ({unit})' if unit else name
    return plot_text(label) if for_plot else label


def property_chart_title(variable=None, properties=('ys', 'uts', 'el'), *, scope='group'):
    shown = '/'.join(key.upper() for key in properties)
    if variable is None:
        return shown + (' by specimen' if scope == 'specimen' else ' by sample')
    return shown + ' vs. ' + variable_label(variable, for_plot=True)


def variable_usage(project, ident, *, scope='group'):
    """Describe affected saved charts without rewriting their axis selections."""
    graphs = [(graph, '') for graph in project.get('graphs', [])]
    graphs += [(item['graph'], 'Deleted graph: ') for item in project.get('deleted_graphs', []) if 'graph' in item]
    used = []
    for graph, prefix in graphs:
        settings = graph.get('settings', {})
        charts = [*(settings.get('properties_by_group_variants') or [dict(name='Chart 1', settings=settings)]),
                  *settings.get('properties_by_specimen_variants', [])]
        for chart in charts:
            config = chart.get('settings', {})
            if (config.get('properties_by_group_level', 'group') == scope
                    and config.get('properties_by_group_x_variable') == ident):
                used.append(prefix + graph.get('name', 'Unnamed graph') + ' — ' + chart.get('name', 'Chart'))
    return used


def variable_axis(groups, ident, variables):
    """Return actual numeric positions; never pool groups with equal x values."""
    if ident not in variables:
        raise ValueError('The selected x-variable is unavailable. Choose one in the plot settings.')
    validate_variables({ident: variables[ident]})
    variable = variables[ident]
    values = variable.get('values', {})
    missing = [group for group in groups if group not in values]
    ordered = sorted((group for group in groups if group in values), key=values.__getitem__)
    warnings = []
    if missing:
        warnings.append('Missing ' + variable_label(variable) + '; omitted from this plot: ' + ', '.join(missing) + '.')
    if len({values[group] for group in ordered}) != len(ordered):
        warnings.append('Some groups share an x-value. They remain separate, not pooled; markers may overlap.')
    if not ordered:
        raise ValueError('No selected groups have a value for ' + variable_label(variable) + '. Add values under Custom variables.')
    return ordered, [values[group] for group in ordered], variable_label(variable, for_plot=True), ' '.join(warnings)


class GroupVariablesView:
    """Table-only editor; an explicit save commits names, units and values together."""
    def __init__(self, w, get_variables, get_groups, on_save_all=None, get_usage=None,
                 *, scope='group', row_label=None, on_scope_change=None, required=None,
                 get_defaults=None):
        from tensile_variable_table import VariableTable
        self.get_variables, self.get_groups = get_variables, get_groups
        self.on_save_all = on_save_all
        self.scope = scope
        self.on_scope_change = on_scope_change
        self.required = required or {}
        self.get_defaults = get_defaults or (lambda: {})
        self.row_label = row_label or str
        entity = 'individual specimens' if scope == 'specimen' else 'sample groups'
        self.get_usage = get_usage or (lambda _: [])
        self._pending_delete = None
        self.groups = []
        self.order = []
        self._paused = False
        self._drafts = self._editable(get_variables())
        self.all_groups = w.Checkbox(description='Show all ' + entity, indent=False,
                                     tooltip='Include unselected groups without changing the graph selection. Values include excluded specimens.',
                                     layout=w.Layout(width='auto'))
        self.table = VariableTable(on_delete=self._request_delete, required=self.required,
                                   layout=w.Layout(width='100%', min_width='0'))
        self.delete_message = w.HTML()
        self.delete_confirm = w.Button(description='Confirm delete', button_style='danger', layout=w.Layout(width='auto'))
        self.delete_cancel = w.Button(description='Cancel', layout=w.Layout(width='auto'))
        self.delete_panel = w.VBox([self.delete_message, w.HBox([self.delete_confirm, self.delete_cancel])],
                                   layout=w.Layout(display='none', border='1px solid #d97706', padding='8px'))
        self.add = w.Button(description='Add variable (column)', layout=w.Layout(width='auto'))
        self.save_all = w.Button(description='Save all variables', button_style='primary',
                                 layout=w.Layout(width='auto'))
        self.table_ui = w.VBox([
            w.HTML('Row 1: name · Row 2: unit · Rows 3 onward: ' + entity + '. '
                   'Paste CSV/TSV or an Excel block into a cell; extra columns are added automatically. '
                   'Paste variable cells only, without the row labels. Blank cells clear values. '
                   'Edits are applied with Save all variables; deletion requires separate confirmation.'),
            w.HBox([self.add, self.save_all], layout=w.Layout(flex_flow='row wrap')),
            self.table], layout=w.Layout(width='100%', min_width='0'))
        self.status = w.HTML()
        self.ui = w.Accordion(children=[w.VBox([
            w.HTML('Numeric values attached to ' + entity + ', shared by all graphs. Create as many variables as needed. '
                   'Rows follow this graph’s sample group order. '
                   'Leave unknown values blank; zero is a valid value. Save before switching graphs.'
                   + (' Specimen rows use operator labels when available; hover a row label for its stable CSV identity. '
                      'Location defaults to the operator specimen number. Enter a whole number to override it; clear the cell to restore the default. '
                      'CSV row numbers are never used as locations. '
                      'Within each group, rows are sorted by specimen name.' if scope == 'specimen' else '')),
            self.all_groups, self.delete_panel, self.table_ui, self.status
        ])], selected_index=None, layout=w.Layout(width='100%', min_width='0'))
        self.ui.set_title(0, 'Custom variables · shared by all graphs')
        self.all_groups.observe(self._scope_changed, names='value')
        self.table.observe(self._table_changed, names='columns')
        self.add.on_click(self._add_column)
        self.save_all.on_click(self._save_table)
        self.delete_cancel.on_click(self._cancel_delete)
        self.delete_confirm.on_click(self._confirm_delete)

    @staticmethod
    def _editable(variables):
        return {ident: dict(name=v['name'], unit=v.get('unit', ''),
                           values={g: str(int(value)) if any(ident in r for r in REQUIRED_VARIABLES.values()) and whole_number(value)
                                   else str(value) for g, value in v.get('values', {}).items()})
                for ident, v in variables.items()}

    @staticmethod
    def _numeric(variable):
        values = {}
        for group, text in variable['values'].items():
            if text.strip():
                try:
                    value = float(text)
                    if not math.isfinite(value):
                        raise ValueError()
                except ValueError as error:
                    raise ValueError(f'{variable["name"] or "Unnamed variable"} / {group}: '
                                     'use a finite number or leave blank.') from error
                values[group] = value
        return dict(name=variable['name'].strip(), unit=variable['unit'].strip(), values=values)

    def refresh(self, groups, *, order=None, force=False, redraw=False):
        groups = list(groups)
        order = list(order) if order is not None else self.order
        changed = groups != self.groups or order != self.order
        self.groups = groups
        self.order = order
        variables = self._editable(self.get_variables())
        changed = changed or bool(variables.keys() - self._drafts.keys())
        if force:
            self._cancel_delete()
            self._drafts = variables
            self.status.value = ''
            self.table.notice = ''
        else:
            for ident, variable in variables.items():
                self._drafts.setdefault(ident, variable)
        if force or changed or redraw or self._editable_defaults() != self.table.defaults:
            self._sync_table()

    def _scope_changed(self, _=None):
        if self.on_scope_change is not None:
            self.on_scope_change()
        else:
            self._sync_table()

    def _visible_groups(self):
        if not self.all_groups.value:
            return ordered_groups(self.groups, self.order)
        groups = set(self.get_groups())
        for variable in self._drafts.values():
            groups.update(variable['values'])
        return ordered_groups(sorted(groups), self.order)

    def _sync_table(self):
        old, self._paused = self._paused, True
        try:
            with self.table.hold_sync():
                self.table.groups = self._visible_groups()
                self.table.labels = {ident: self.row_label(ident) for ident in self.table.groups}
                self.table.columns = [dict(id=k, **deepcopy(v)) for k, v in self._drafts.items() if k]
                self.table.defaults = self._editable_defaults()
        finally:
            self._paused = old

    def _table_changed(self, change):
        if self._paused:
            return
        for column in change['new']:
            self._drafts[column['id']] = deepcopy({k: column[k] for k in ('name', 'unit', 'values')})

    def _add_column(self, _=None):
        self._cancel_delete()
        ident = 'var-' + uuid.uuid4().hex
        self._drafts[ident] = dict(name='', unit='', values={})
        self._sync_table()
        self.table.notice = 'New column added. Enter its name, optional unit and values, then Save all variables.'

    def _request_delete(self, ident):
        if ident in self.required:
            self.table.notice = self.required[ident]['name'] + ' is required and cannot be deleted.'
            return
        if not ident or ident not in self._drafts:
            return
        saved = self.get_variables()
        self._pending_delete = dict(id=ident, saved=deepcopy(saved.get(ident)), persisted=ident in saved)
        name = self._drafts[ident]['name'].strip() or 'Unnamed variable'
        if ident in saved:
            message = f'<b>Delete {escape(name)}?</b> This removes the variable and all its values from every graph. '
            usage = self.get_usage(ident)
            if usage:
                message += '<br><b>Charts needing a new X-axis selection:</b><ul>'
                message += ''.join('<li>' + escape(label) + '</li>' for label in usage) + '</ul>'
                message += 'These charts will remain unavailable until you choose another variable. No automatic axis substitution. '
            else:
                message += 'No saved charts currently use it. '
        else:
            message = f'<b>Remove unsaved column {escape(name)}?</b> Its draft values will be discarded. '
        self.delete_message.value = message + 'Other variable edits will not be saved or removed.'
        self.delete_panel.layout.display = ''

    def _cancel_delete(self, _=None):
        self._pending_delete = None
        self.delete_message.value = ''
        self.delete_panel.layout.display = 'none'

    def _confirm_delete(self, _=None):
        pending = self._pending_delete
        if pending is None:
            return
        ident = pending['id']
        if ident in self.required:
            self._cancel_delete()
            return
        try:
            variables = deepcopy(self.get_variables())
            if variables.get(ident) != pending['saved'] or (ident in variables) != pending['persisted']:
                raise ValueError('The saved variable changed. Cancel and review deletion again.')
            if pending['persisted']:
                if self.on_save_all is None:
                    raise ValueError('Deleting saved variables is unavailable in this preview.')
                del variables[ident]
                self.on_save_all(variables)
            name = self._drafts[ident]['name'].strip() or 'Unnamed variable'
            del self._drafts[ident]
            self._sync_table()
            self._cancel_delete()
            self.status.value = ''
            self.table.notice = f'Deleted {name}. Other draft edits are unchanged.'
        except Exception as error:
            self.delete_message.value += '<br><b>Not deleted:</b> ' + escape(str(error))

    def _editable_defaults(self):
        return {ident: {group: str(int(value)) if ident in self.required and whole_number(value) else str(value)
                        for group, value in values.items() if value is not None}
                for ident, values in self.get_defaults().items()}

    def _save_table(self, _=None):
        self._cancel_delete()
        try:
            variables = deepcopy(self.get_variables())
            variables.update({k: self._numeric(v) for k, v in self._drafts.items() if k})
            validate_variables(variables, scope=self.scope)
            if self.on_save_all is None:
                raise ValueError('Saving the table is unavailable in this preview.')
            self.on_save_all(variables)
            self._drafts = self._editable(self.get_variables())
            self._sync_table()
            self.status.value = ''
            self.table.notice = 'All variables saved for all graphs.'
        except Exception as error:
            self.table.notice = 'Not saved: ' + str(error)
