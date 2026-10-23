"""Independent settings for one specimen-property chart per sample group."""
from copy import deepcopy
from tensile_locations import LOCATION
from tensile_property_variants import PropertyVariantsView, SPECIMEN_DEFAULTS, TITLE_KEY
from tensile_variables import property_chart_title, variable_label
from tensile_settings import SPECIMEN_TREND_KEY, SPECIMEN_GROUPS_KEY, specimen_trend


class SpecimenChartsView:
    def __init__(self, w, get_variables, changed, title):
        self.w, self.get_variables, self.changed = w, get_variables, changed
        self.paused = True
        self.title = title
        self.controls, self.axes = {}, {}
        self._settings = deepcopy(SPECIMEN_DEFAULTS)
        self.groups, self.group_boxes, self._selected_groups = [], {}, None
        self.all_groups = w.Checkbox(description='All sample groups', value=True, indent=False,
                                    layout=w.Layout(width='auto'))
        self.group_rows = w.VBox(layout=w.Layout(width='100%', gap='2px'))
        self.group_note = w.HTML()
        self.group_ui = w.VBox([self.all_groups, self.group_rows, self.group_note])
        self.all_groups.observe(self._all_groups_changed, names='value')
        prefix = 'properties_by_group_'
        self.controls[prefix + 'x_variable'] = w.Dropdown(description='X-axis:',
            options=[('Location', LOCATION)], layout=w.Layout(width='500px', max_width='100%'))
        for key in ('ys', 'uts', 'el'):
            self.controls[prefix + 'show_' + key] = w.Checkbox(value=True, description=key.upper(),
                indent=False, layout=w.Layout(width='auto'))
            self.controls[prefix + key + '_color'] = w.ColorPicker(description=key.upper() + ' colour',
                value=SPECIMEN_DEFAULTS[prefix + key + '_color'])
        self.controls[SPECIMEN_TREND_KEY] = w.Dropdown(description='Trendline:',
            options=[('None', 'none'), ('Linear', 'linear'), ('Quadratic · order 2', 'quadratic')], value='quadratic',
            layout=w.Layout(width='350px', max_width='100%'))
        for suffix, caption, bounds in (('xlim', 'Location / custom variable', (0, 10)),
                                        ('ylim', 'Strength (MPa)', (0, 1000)),
                                        ('el_ylim', 'Elongation (%)', (0, 30))):
            auto = w.Checkbox(description='Automatic', value=True, indent=False)
            low = w.FloatText(description='Min:', value=bounds[0], continuous_update=False)
            high = w.FloatText(description='Max:', value=bounds[1], continuous_update=False)
            box = w.VBox([w.HTML('<b>' + caption + '</b>'), auto,
                          w.HBox([low, high], layout=w.Layout(flex_flow='row wrap'))])
            self.axes[prefix + suffix] = (auto, low, high, box)
            for control in (auto, low, high):
                control.observe(self._changed, names='value')
        axis_panel = w.Accordion(children=[w.VBox([a[3] for a in self.axes.values()])], selected_index=None)
        axis_panel.set_title(0, 'Axes · this plot')
        self.variants = PropertyVariantsView(w, self.capture, self.apply, self._changed)
        self.ui = w.VBox([
            w.HTML('One grouped bar chart per chosen sample group, with individual YS/UTS/EL values. '
                   '<b>Location</b> defaults to the operator specimen number; edit overrides in '
                   '<b>Custom variables → Individual specimens</b>. Set the tested + untested total in '
                   '<b>Custom variables → Sample groups → Specimen count</b>.'),
            self.variants.ui, self.group_ui, self.controls[prefix + 'x_variable'],
            w.HBox([self.controls[prefix + 'show_' + key] for key in ('ys', 'uts', 'el')]),
            title, axis_panel, self.controls[SPECIMEN_TREND_KEY],
            w.HBox([self.controls[prefix + key + '_color'] for key in ('ys', 'uts', 'el')],
                   layout=w.Layout(flex_flow='row wrap')),
            w.HTML('No group averages or SD bars. Excluded properties stay omitted; EL follows gauge reconstruction. '
                   'Specimen count keeps untested locations visible without adding measurements. '
                   'Quadratic (order 2) trendlines are the default and need at least three distinct locations. '
                   'Trendlines use measured eligible values only: dashed within the measured range, dotted beyond it. '
                   'Extrapolation is not a measured result or a validated prediction.')])
        for control in self.controls.values():
            control.observe(self._changed, names='value')
        self.title.observe(self._changed, names='value')
        self.paused = False

    def refresh_groups(self, groups):
        """Workspace identities only; this must not load or analyse specimens."""
        groups = list(dict.fromkeys(groups))
        old, self.paused = self.paused, True
        try:
            if groups != self.groups:
                for box in self.group_boxes.values():
                    box.close()
                self.groups = groups
                self.group_boxes = {}
                for group in groups:
                    box = self.w.Checkbox(description=group, indent=False,
                        layout=self.w.Layout(width='auto', max_width='100%'))
                    box.observe(lambda change, group=group: self._group_changed(group, change['new']), names='value')
                    self.group_boxes[group] = box
                self.group_rows.children = tuple(self.group_boxes.values())
            for group, box in self.group_boxes.items():
                box.value = self._selected_groups is None or group in self._selected_groups
            count = sum(box.value for box in self.group_boxes.values())
            self.all_groups.value = self._selected_groups is None or bool(groups) and count == len(groups)
            self.all_groups.disabled = not groups
            self.group_note.value = (f'{count} of {len(groups)} workspace groups selected for this chart variant. '
                                     'Tables and specimen exclusions are unchanged.' if groups else
                                     'Select sample groups in the workspace above first.')
        finally:
            self.paused = old

    def _all_groups_changed(self, change):
        if self.paused:
            return
        self._selected_groups = None if change['new'] else []
        self.refresh_groups(self.groups)
        self._changed()

    def _group_changed(self, group, included):
        if self.paused:
            return
        selected = list(self.groups if self._selected_groups is None else self._selected_groups)
        if included and group not in selected:
            selected.append(group)
        elif not included:
            selected = [g for g in selected if g != group]
        self._selected_groups = selected
        self.refresh_groups(self.groups)
        self._changed()

    def refresh_variables(self):
        selected = self.controls['properties_by_group_x_variable'].value
        old, self.paused = self.paused, True
        try:
            options = [(variable_label(v), ident) for ident, v in self.get_variables().items()]
            options.append(('Specimen names', ''))
            if selected not in {ident for _, ident in options}:
                options.append(('Unavailable variable · choose another', selected))
            self.controls['properties_by_group_x_variable'].options = options
            self.controls['properties_by_group_x_variable'].value = selected
            self._sync()
        finally:
            self.paused = old

    def _sync(self):
        ident = self.controls['properties_by_group_x_variable'].value
        variable = self.get_variables().get(ident)
        properties = [key for key in ('ys', 'uts', 'el') if self.controls['properties_by_group_show_' + key].value]
        self.title.placeholder = ('Choose an available custom variable' if ident and variable is None else
                                  property_chart_title(variable, properties, scope='specimen'))
        for auto, low, high, _ in self.axes.values():
            low.disabled = high.disabled = auto.value

    def _changed(self, _=None):
        if self.paused:
            return
        self._sync()
        self.changed()

    def capture(self):
        values = {**self._settings, **{key: control.value for key, control in self.controls.items()},
                  TITLE_KEY: self.title.value.strip(), 'properties_by_group_level': 'specimen',
                  SPECIMEN_GROUPS_KEY: deepcopy(self._selected_groups)}
        for key, (auto, low, high, _) in self.axes.items():
            values[key] = None if auto.value else [low.value, high.value]
        return values

    def apply(self, values):
        old, self.paused = self.paused, True
        try:
            self._settings = {**deepcopy(SPECIMEN_DEFAULTS), **deepcopy(values)}
            self._settings[SPECIMEN_TREND_KEY] = specimen_trend(values)
            self._selected_groups = deepcopy(values.get(SPECIMEN_GROUPS_KEY))
            self.refresh_groups(self.groups)
            ident = self._settings['properties_by_group_x_variable']
            self.refresh_variables()
            control = self.controls['properties_by_group_x_variable']
            if ident not in {value for _, value in control.options}:
                control.options = [*control.options, ('Unavailable variable · choose another', ident)]
            for key, widget in self.controls.items():
                widget.value = self._settings[key]
            for key, (auto, low, high, _) in self.axes.items():
                limits = values.get(key)
                auto.value = limits is None
                if limits is not None:
                    low.value, high.value = limits
            self.title.value = values.get(TITLE_KEY, '')
            self._sync()
        finally:
            self.paused = old

    def load(self, variants):
        old, self.paused = self.paused, True
        try:
            self.variants.load(variants, SPECIMEN_DEFAULTS)
        finally:
            self.paused = old

    def snapshot(self):
        return self.variants.snapshot()
