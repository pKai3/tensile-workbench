"""Independent property-chart configurations within one saved graph."""
from copy import deepcopy
import uuid
from tensile_settings import GROUP_DEFAULTS, GROUP_FAMILY, validate_group_display, planned_positions
from tensile_locations import LOCATION, SPECIMEN_COUNT

VARIANTS_KEY = 'properties_by_group_variants'
SPECIMEN_FAMILY = 'properties_by_specimen'
SPECIMEN_VARIANTS_KEY = 'properties_by_specimen_variants'
TITLE_KEY = 'properties_by_group_title'
SPECIMEN_DEFAULTS = {**GROUP_DEFAULTS, 'properties_by_group_level': 'specimen',
                     'properties_by_group_x_variable': LOCATION,
                     'properties_by_group_line_style': 'none', 'properties_by_group_error_bars': False}


def split_property_charts(project):
    """Move saved trial specimen variants into their own plot section once."""
    from tensile_moves import graph_blocks
    project = deepcopy(project)
    counts = project.get('group_variables', {}).get(SPECIMEN_COUNT, {}).get('values', {})
    for graph in graph_blocks(project):
        settings = graph.get('settings', {})
        if SPECIMEN_VARIANTS_KEY in settings:
            continue
        original = settings.get(VARIANTS_KEY, [{'id': 'default', 'name': 'Chart 1', 'settings': {
            **{k: deepcopy(settings.get(k, v)) for k, v in GROUP_DEFAULTS.items()},
            TITLE_KEY: graph.get('definition', {}).get('workbench_titles', {}).get(GROUP_FAMILY, '')}}])
        specimens = [deepcopy(v) for v in original if v['settings'].get('properties_by_group_level') == 'specimen']
        if not specimens:
            continue
        groups = [deepcopy(v) for v in original if v['settings'].get('properties_by_group_level', 'group') == 'group']
        settings[SPECIMEN_VARIANTS_KEY] = specimens
        settings[VARIANTS_KEY] = groups or [{'id': 'default', 'name': 'Chart 1', 'settings': deepcopy(GROUP_DEFAULTS)}]
        settings.update({k: deepcopy(settings[VARIANTS_KEY][0]['settings'].get(k, default))
                         for k, default in GROUP_DEFAULTS.items()})
        if GROUP_FAMILY in settings.get('families', []):
            settings['families'] = [f for f in settings['families'] if groups or f != GROUP_FAMILY]
            if SPECIMEN_FAMILY not in settings['families']:
                settings['families'].append(SPECIMEN_FAMILY)
        for chart in specimens:
            values = chart['settings']
            planned = planned_positions(values.get('properties_by_group_planned_positions', ''))
            # The former 1:N reservation becomes the shared count. Preserve any
            # other old numeric domain inside the saved chart for compatibility.
            if planned and planned == list(range(1, int(max(planned)) + 1)) and values.get('properties_by_group_x_variable') == LOCATION:
                for group in settings.get('groups', []):
                    counts[group] = max(counts.get(group, 0), int(max(planned)))
                values['properties_by_group_planned_positions'] = ''
    return project


def validate_variants(variants):
    if not isinstance(variants, list) or not variants:
        raise ValueError('At least one property chart is required.')
    ids = set()
    for variant in variants:
        if not isinstance(variant, dict):
            raise ValueError('Invalid property chart.')
        ident = variant.get('id')
        if not isinstance(ident, str) or not ident or ident in ids:
            raise ValueError('Property chart IDs must be nonempty and unique.')
        ids.add(ident)
        if not isinstance(variant.get('name'), str) or not variant['name'].strip():
            raise ValueError('Each property chart needs a name.')
        settings = variant.get('settings')
        if not isinstance(settings, dict):
            raise ValueError('Each property chart needs settings.')
        validate_group_display(settings)
        if not isinstance(settings.get(TITLE_KEY, ''), str):
            raise ValueError('Chart titles must be text.')


class PropertyVariantsView:
    """One editor, many saved charts. Switching never discards the previous edit."""
    def __init__(self, w, capture, apply, changed):
        self.capture, self.apply, self.changed = capture, apply, changed
        self.variants, self.active, self.paused = [], None, False
        self.choice = w.Dropdown(description='Edit chart:', layout=w.Layout(width='450px', max_width='100%'))
        self.name = w.Text(description='Chart name:', continuous_update=False,
                           style={'description_width': 'initial'}, layout=w.Layout(width='450px', max_width='100%'))
        self.add = w.Button(description='Add chart variant', layout=w.Layout(width='auto'))
        self.remove = w.Button(description='Remove this chart', layout=w.Layout(width='auto'))
        self.ui = w.VBox([w.HTML('All variants below are plotted separately. Each has its own X-axis, properties, title and styling. '
                                'Adding a variant copies the current chart; removal affects only this graph.'),
                          self.choice, w.HBox([self.add, self.remove], layout=w.Layout(flex_flow='row wrap')), self.name])
        self.choice.observe(self._switch, names='value')
        self.name.observe(self._rename, names='value')
        self.add.on_click(self._add)
        self.remove.on_click(self._remove)

    def load(self, saved, base):
        self.variants = deepcopy(saved) if saved is not None else [dict(id='default', name='Chart 1', settings=deepcopy(base))]
        validate_variants(self.variants)
        self.active = self.variants[0]['id']
        self._show()

    def snapshot(self):
        if self.active is not None:
            self._current()['settings'] = deepcopy(self.capture())
        return deepcopy(self.variants)

    def _current(self):
        return next(v for v in self.variants if v['id'] == self.active)

    def _show(self):
        self.paused = True
        try:
            self.choice.options = [(v['name'], v['id']) for v in self.variants]
            self.choice.value = self.active
            self.name.value = self._current()['name']
            self.remove.disabled = len(self.variants) == 1
            self.apply({**deepcopy(GROUP_DEFAULTS), **self._current()['settings']})
        finally:
            self.paused = False

    def _switch(self, change):
        if self.paused or change['new'] is None:
            return
        self.snapshot()
        self.active = change['new']
        self._show()
        self.changed()

    def _rename(self, change):
        if self.paused or self.active is None or not change['new'].strip():
            return
        self.snapshot()
        self._current()['name'] = change['new'].strip()
        self._show()
        self.changed()

    def _add(self, _=None):
        self.snapshot()
        names = {v['name'] for v in self.variants}
        number = 1
        while f'Chart {number}' in names:
            number += 1
        variant = dict(id=uuid.uuid4().hex, name=f'Chart {number}', settings=deepcopy(self._current()['settings']))
        self.variants.append(variant)
        self.active = variant['id']
        self._show()
        self.changed()

    def _remove(self, _=None):
        if len(self.variants) <= 1:
            return
        self.variants = [v for v in self.variants if v['id'] != self.active]
        self.active = self.variants[0]['id']
        self._show()
        self.changed()
