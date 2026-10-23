"""User-supplied numeric sample-group variables, shared by saved graphs."""
from copy import deepcopy
from html import escape
import math
import uuid
from tensile_order import ordered_groups


def validate_variables(variables):
    if not isinstance(variables, dict):
        raise ValueError('Sample-group variables must be a mapping.')
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


def variable_label(variable):
    name, unit = variable['name'].strip(), variable.get('unit', '').strip()
    return f'{name} ({unit})' if unit else name


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
        raise ValueError('No selected groups have a value for ' + variable_label(variable) + '. Add values under Sample-group variables.')
    return ordered, [values[group] for group in ordered], variable_label(variable), ' '.join(warnings)


class GroupVariablesView:
    """Compact editor; an explicit save commits names, units and values together."""
    def __init__(self, w, get_variables, get_groups, on_save):
        self.w, self.get_variables, self.get_groups, self.on_save = w, get_variables, get_groups, on_save
        self.groups, self.fields, self._draft = [], {}, {}
        self.order = []
        self._paused = False
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
        self.status = w.HTML()
        self.ui = w.Accordion(children=[w.VBox([
            w.HTML('Numeric values attached to sample groups, shared by all graphs. Create as many variables as needed. '
                   'Rows follow this graph’s sample group order. '
                   'Leave unknown values blank; zero is a valid value. Save before switching variables or graphs.'),
            self.choice, w.HBox([self.name, self.unit], layout=w.Layout(flex_flow='row wrap')),
            self.all_groups, self.rows, self.save, self.status
        ])], selected_index=None, layout=w.Layout(width='100%', min_width='0'))
        self.ui.set_title(0, 'Sample-group variables · shared by all graphs')
        self.choice.observe(self._choose, names='value')
        self.all_groups.observe(lambda _: self._render_rows(), names='value')
        self.save.on_click(self._save)

    def refresh(self, groups, *, order=None, force=False):
        groups = list(groups)
        order = list(order) if order is not None else self.order
        changed = groups != self.groups or order != self.order
        self.groups = groups
        self.order = order
        variables = self.get_variables()
        selected = self.choice.value
        self._paused = True
        try:
            self.choice.options = [('New variable…', '')] + [(variable_label(v), k) for k, v in variables.items()]
            self.choice.value = selected if selected in variables else ''
        finally:
            self._paused = False
        if force:
            self._choose()
        elif changed:
            self._render_rows()

    def _choose(self, _=None):
        if self._paused:
            return
        variable = self.get_variables().get(self.choice.value, {})
        self.name.value, self.unit.value = variable.get('name', ''), variable.get('unit', '')
        self._draft = {group: str(value) for group, value in variable.get('values', {}).items()}
        self.status.value = ''
        self._render_rows()

    def _render_rows(self):
        w = self.w
        groups = sorted(set(self.get_groups()) | set(self._draft)) if self.all_groups.value else self.groups
        groups = ordered_groups(groups, self.order)
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
            ident = self.choice.value or 'var-' + uuid.uuid4().hex
            values = {group: float(text.strip()) for group, text in self._draft.items() if text.strip()}
            variable = dict(name=self.name.value.strip(), unit=self.unit.value.strip(), values=values)
            variables = deepcopy(self.get_variables())
            variables[ident] = variable
            validate_variables(variables)
            self.on_save(ident, variable)
            self.refresh(self.groups)
            self.choice.value = ident
            self.status.value = 'Saved for all graphs. Choose this variable as an X-axis in the YS/UTS/EL plot settings.'
        except Exception as error:
            self.status.value = '<b>Not saved:</b> ' + escape(str(error))
