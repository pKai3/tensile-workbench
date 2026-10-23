"""User-supplied numeric sample-group variables, shared by saved graphs."""
from copy import deepcopy
from html import escape
import math
import re
import uuid
from tensile_order import ordered_groups


def validate_variables(variables):
    if not isinstance(variables, dict):
        raise ValueError('Custom variables must be a mapping.')
    names = set()
    for ident, variable in variables.items():
        if not isinstance(ident, str) or not ident or not isinstance(variable, dict):
            raise ValueError('Invalid sample-group variable.')
        name, unit = variable.get('name'), variable.get('unit', '')
        if not isinstance(name, str) or not name.strip() or name.strip().casefold() in names:
            raise ValueError('Variable names must be nonempty and unique.')
        names.add(name.strip().casefold())
        if not isinstance(unit, str):
            raise ValueError('Variable units must be text.')
        values = variable.get('values', {})
        if not isinstance(values, dict):
            raise ValueError('Variable values must map sample groups to numbers.')
        for group, value in values.items():
            if (not isinstance(group, str) or not group or isinstance(value, bool)
                    or not isinstance(value, (float, int)) or not math.isfinite(value)):
                raise ValueError('Group variable values must be finite numbers. Leave missing values blank.')


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


def property_chart_title(variable=None, properties=('ys', 'uts', 'el')):
    shown = '/'.join(key.upper() for key in properties)
    if variable is None:
        return shown + ' by sample'
    return shown + ' vs. ' + variable_label(variable, for_plot=True)


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
    """Compact editor; an explicit save commits names, units and values together."""
    def __init__(self, w, get_variables, get_groups, on_save, on_save_all=None):
        from tensile_variable_table import VariableTable
        self.w, self.get_variables, self.get_groups, self.on_save = w, get_variables, get_groups, on_save
        self.on_save_all = on_save_all
        self.groups, self.fields, self._draft = [], {}, {}
        self.order = []
        self._paused = False
        self._active = ''
        self._drafts = self._editable(get_variables())
        self.view = w.ToggleButtons(description='View:', options=[('One variable', 'single'), ('Table', 'table')],
                                     style={'button_width': 'auto'})
        self.choice = w.Dropdown(description='Variable:', options=[('New variable…', '')],
                                 layout=w.Layout(width='450px', max_width='100%'))
        self.name = w.Text(description='Name:', placeholder='e.g. Shielding gas CO₂', continuous_update=False)
        self.unit = w.Text(description='Units:', placeholder='e.g. %, °C, mm', continuous_update=False)
        self.all_groups = w.Checkbox(description='Show all sample groups', indent=False,
                                     tooltip='Include groups not selected in this graph, without changing the graph selection.',
                                     layout=w.Layout(width='auto'))
        self.rows = w.VBox(layout=w.Layout(width='100%', max_height='300px', overflow='auto', flex='0 0 auto'))
        self.save = w.Button(description='Save variable and values', button_style='primary',
                             layout=w.Layout(width='auto', align_self='flex-start', flex='0 0 auto'))
        self.table = VariableTable(layout=w.Layout(width='100%', min_width='0'))
        self.add = w.Button(description='Add variable (column)', layout=w.Layout(width='auto'))
        self.save_all = w.Button(description='Save all variables', button_style='primary',
                                 layout=w.Layout(width='auto'))
        self.single_ui = w.VBox([self.choice, w.HBox([self.name, self.unit], layout=w.Layout(flex_flow='row wrap')),
                                self.rows, self.save], layout=w.Layout(width='100%', min_width='0'))
        self.table_ui = w.VBox([
            w.HTML('Row 1: name · Row 2: unit · Rows 3 onward: sample-group values. '
                   'Paste CSV/TSV or an Excel block into a cell; extra columns are added automatically. '
                   'Paste variable cells only, without the sample-group labels. Blank cells clear values. '
                   'Nothing is applied until Save all variables.'),
            w.HBox([self.add, self.save_all], layout=w.Layout(flex_flow='row wrap')),
            self.table], layout=w.Layout(width='100%', min_width='0', display='none'))
        self.status = w.HTML()
        self.ui = w.Accordion(children=[w.VBox([
            w.HTML('Numeric values attached to sample groups, shared by all graphs. Create as many variables as needed. '
                   'Rows follow this graph’s sample group order. '
                   'Leave unknown values blank; zero is a valid value. Save before switching graphs.'),
            self.view, self.all_groups, self.single_ui, self.table_ui, self.status
        ])], selected_index=None, layout=w.Layout(width='100%', min_width='0'))
        self.ui.set_title(0, 'Custom variables · shared by all graphs')
        self.choice.observe(self._choose, names='value')
        self.all_groups.observe(lambda _: self._render(), names='value')
        self.view.observe(self._switch_view, names='value')
        self.table.observe(self._table_changed, names='columns')
        self.save.on_click(self._save)
        self.add.on_click(self._add_column)
        self.save_all.on_click(self._save_table)

    @staticmethod
    def _editable(variables):
        return {ident: dict(name=v['name'], unit=v.get('unit', ''),
                           values={g: str(value) for g, value in v.get('values', {}).items()})
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

    def _capture_single(self):
        self._drafts[self._active] = dict(name=self.name.value, unit=self.unit.value, values=dict(self._draft))

    def _promote_new(self):
        new = self._drafts.get('')
        if new and (new['name'].strip() or new['unit'].strip() or any(v.strip() for v in new['values'].values())):
            ident = 'var-' + uuid.uuid4().hex
            self._drafts[ident] = self._drafts.pop('')
            if not self._active:
                self._active = ident

    def _sync_choices(self):
        old, self._paused = self._paused, True
        try:
            self.choice.options = [('New variable…', '')] + [
                (variable_label(v) if v['name'].strip() else 'Unnamed variable', k)
                for k, v in self._drafts.items() if k]
            self.choice.value = self._active if self._active in self._drafts else ''
        finally:
            self._paused = old

    def _load_single(self):
        variable = self._drafts.get(self._active, dict(name='', unit='', values={}))
        self.name.value, self.unit.value = variable['name'], variable['unit']
        self._draft = dict(variable['values'])
        self._render_rows()

    def refresh(self, groups, *, order=None, force=False):
        groups = list(groups)
        order = list(order) if order is not None else self.order
        changed = groups != self.groups or order != self.order
        self.groups = groups
        self.order = order
        variables = self._editable(self.get_variables())
        if force:
            self._drafts = variables
            if self._active not in variables:
                self._active = ''
            self._load_single()
            self.status.value = ''
            self.table.notice = ''
        else:
            for ident, variable in variables.items():
                self._drafts.setdefault(ident, variable)
        self._sync_choices()
        if force or changed:
            self._render()

    def _choose(self, _=None):
        if self._paused:
            return
        self._capture_single()
        self._active = self.choice.value
        self.status.value = ''
        self._load_single()

    def _switch_view(self, change):
        if change['new'] == 'table':
            self._capture_single()
            self._promote_new()
            self._sync_table()
        else:
            self._sync_choices()
            self._load_single()
        self.single_ui.layout.display = '' if change['new'] == 'single' else 'none'
        self.table_ui.layout.display = '' if change['new'] == 'table' else 'none'
        self.status.value = ''

    def _visible_groups(self):
        if not self.all_groups.value:
            return ordered_groups(self.groups, self.order)
        groups = set(self.get_groups()) | set(self._draft)
        for variable in self._drafts.values():
            groups.update(variable['values'])
        return ordered_groups(sorted(groups), self.order)

    def _render(self):
        if self.view.value == 'table':
            self._sync_table()
        else:
            self._render_rows()

    def _sync_table(self):
        old, self._paused = self._paused, True
        try:
            with self.table.hold_sync():
                self.table.groups = self._visible_groups()
                self.table.columns = [dict(id=k, **deepcopy(v)) for k, v in self._drafts.items() if k]
        finally:
            self._paused = old

    def _table_changed(self, change):
        if self._paused:
            return
        for column in change['new']:
            self._drafts[column['id']] = deepcopy({k: column[k] for k in ('name', 'unit', 'values')})

    def _add_column(self, _=None):
        self._active = 'var-' + uuid.uuid4().hex
        self._drafts[self._active] = dict(name='', unit='', values={})
        self._sync_table()
        self.table.notice = 'New column added. Enter its name, optional unit and values, then Save all variables.'

    def _render_rows(self):
        w = self.w
        groups = self._visible_groups()
        old = self.rows.children
        self.fields = {}
        rows = []
        for group in groups:
            field = w.Text(value=self._draft.get(group, ''), placeholder='Not set', continuous_update=False,
                           layout=w.Layout(width='160px', flex='0 0 160px'))
            field.observe(lambda change, g=group: self._draft.__setitem__(g, change['new']), names='value')
            self.fields[group] = field
            # Flex children otherwise shrink into the capped viewport instead
            # of overflowing it, clipping every input when many groups appear.
            rows.append(w.HBox([w.HTML(escape(group), layout=w.Layout(width='450px', max_width='100%')), field],
                                layout=w.Layout(flex_flow='row wrap', gap='8px', flex='0 0 auto', min_height='32px')))
        self.rows.children = tuple(rows) or (w.HTML('Select sample groups above, or enable Show all sample groups.'),)
        for row in old:
            for child in getattr(row, 'children', ()):
                child.close()
            row.close()

    def _save(self, _=None):
        try:
            self._capture_single()
            ident = self._active or 'var-' + uuid.uuid4().hex
            variable = self._numeric(self._drafts[self._active])
            variables = deepcopy(self.get_variables())
            variables[ident] = variable
            validate_variables(variables)
            self.on_save(ident, variable)
            if not self._active:
                self._drafts.pop('', None)
            self._active = ident
            self._drafts.update(self._editable({ident: variable}))
            self._sync_choices()
            self._load_single()
            self.status.value = 'Saved for all graphs. Choose this variable as an X-axis in the YS/UTS/EL plot settings.'
        except Exception as error:
            self.status.value = '<b>Not saved:</b> ' + escape(str(error))

    def _save_table(self, _=None):
        try:
            variables = deepcopy(self.get_variables())
            variables.update({k: self._numeric(v) for k, v in self._drafts.items() if k})
            validate_variables(variables)
            if self.on_save_all is None:
                raise ValueError('Saving the table is unavailable in this preview.')
            self.on_save_all(variables)
            self._drafts = self._editable(variables)
            self._sync_choices()
            self._load_single()
            self._sync_table()
            self.table.notice = 'All variables saved for all graphs.'
        except Exception as error:
            self.table.notice = 'Not saved: ' + str(error)
