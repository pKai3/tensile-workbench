"""Edit all selected groups together, with one atomic apply per analysis."""
from copy import deepcopy
from html import escape

from tensile_colors import group_badge
from tensile_help import control_row, notice_widget


class GroupAppearanceEditor:
    def __init__(self, w, on_apply):
        self.w, self.on_apply = w, on_apply
        self.analysis = None
        self.rows, self._drafts, self._saved = {}, {}, {}
        self._defaults, self._automatic = {}, {}
        self._syncing = False
        self.grid = w.GridBox(layout=w.Layout(width='100%', min_width='720px',
            grid_template_columns='minmax(150px, 1fr) minmax(260px, 2fr) 230px',
            grid_auto_rows='max-content', align_items='stretch', grid_gap='0 16px'))
        self.grid.add_class('tw-appearance-grid')
        self.headings = [w.HTML('<b>' + title + '</b>') for title in ('Sample group', 'Label', 'Colour')]
        for heading in self.headings:
            heading.add_class('tw-appearance-heading')
        self.scroller = w.Box([self.grid], layout=w.Layout(width='100%', min_width='0',
            display='block', max_height='min(420px, 48vh)', overflow='auto',
            border='1px solid var(--tw-border,#cbd5e1)', padding='0 14px'))
        self.empty = w.HTML('Select sample groups to edit their labels and colours.')
        self.apply = w.Button(description='Apply changes', icon='check', button_style='primary',
            disabled=True, layout=w.Layout(width='auto'))
        self.discard = w.Button(description='Discard edits', icon='undo', disabled=True,
            tooltip='Restore saved labels and colours for this analysis.', layout=w.Layout(width='auto'))
        self.status = notice_widget(w)
        style = w.HTML('''<style>
          .tw-appearance-grid .tw-appearance-heading {position:sticky;top:0;z-index:2;
            background:var(--tw-panel-bg,#fff);margin:0;padding:10px 0;border-bottom:1px solid var(--tw-border,#cbd5e1);}
          .tw-appearance-grid .tw-appearance-cell {min-width:0;margin:0;padding:6px 0;
            border-bottom:1px solid var(--tw-border,#dce3e9);}
          .tw-appearance-grid .tw-appearance-label .widget-label {position:absolute;width:1px !important;
            height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap;}
          .tw-appearance-grid .widget-colorpicker {margin:0;}
        </style>''', layout=w.Layout(height='0', margin='0'))
        footer = control_row(w, [self.apply, self.discard, self.status])
        footer.layout.margin = '10px 0 0'
        self.ui = w.VBox([style, self.empty, self.scroller, footer],
            layout=w.Layout(width='100%', min_width='0'))
        self.apply.on_click(self._apply)
        self.discard.on_click(self._discard)

    def _new_row(self, group):
        w = self.w
        name = w.HTML()
        label = w.Text(description='Label for ' + group, continuous_update=False,
            tooltip='Leave blank to restore the default label.', layout=w.Layout(width='100%', min_width='0'))
        label.add_class('tw-appearance-label')
        color = w.ColorPicker(description='Colour for ' + group, concise=False,
            layout=w.Layout(width='166px', min_width='0'))
        color.add_class('tw-appearance-label')
        color.tooltip = 'Colour for ' + group + '. Editing this sets a custom colour.'
        reset = w.Button(icon='undo', tooltip='Use the palette colour for ' + group,
            layout=w.Layout(width='32px', min_width='32px', padding='0', margin='0'))
        mode = w.HTML(layout=w.Layout(margin='0', padding='0', height='16px'))
        color_controls = w.HBox([color, reset], layout=w.Layout(align_items='center', grid_gap='4px', height='36px'))
        colour_cell = w.VBox([color_controls, mode], layout=w.Layout(min_width='0'))
        label_cell = w.Box([label], layout=w.Layout(min_width='0', align_items='center'))
        name_cell = w.Box([name], layout=w.Layout(min_width='0', align_items='center'))
        cells = (name_cell, label_cell, colour_cell)
        for cell in cells:
            cell.add_class('tw-appearance-cell')
        analysis = self.analysis
        label.observe(lambda change: self._edit(analysis, group, 'label', change['new']), names='value')
        color.observe(lambda change: self._edit(analysis, group, 'color', change['new']), names='value')
        reset.on_click(lambda _: self._edit(analysis, group, 'color', None))
        return dict(name=name, label=label, color=color, reset=reset, mode=mode, cells=cells,
                    owned=[name, label, color, reset, mode, color_controls, colour_cell, label_cell, name_cell])

    def refresh(self, analysis, groups, definition, defaults, automatic):
        self._syncing = True
        try:
            if analysis != self.analysis:
                self._close_rows()
            self.analysis = analysis
            for group in set(self.rows) - set(groups):
                for widget in reversed(self.rows.pop(group)['owned']):
                    widget.close()
            self._defaults, self._automatic = dict(defaults), dict(automatic)
            self._saved = {group: {'label': definition.get('name_overrides', {}).get(group),
                                   'color': definition.get('color_overrides', {}).get(group)} for group in groups}
            for group in groups:
                if group not in self.rows:
                    self.rows[group] = self._new_row(group)
                self._paint(group)
            children = (*self.headings, *(cell for group in groups for cell in self.rows[group]['cells']))
            if self.grid.children != children:
                self.grid.children = children
            self.empty.layout.display = 'none' if groups else ''
            self.scroller.layout.display = '' if groups else 'none'
            self._status()
        finally:
            self._syncing = False

    def _paint(self, group):
        row = self.rows[group]
        values = dict(self._saved[group])
        values.update({field: edit['after'] for field, edit in self._drafts.get(self.analysis, {}).get(group, {}).items()})
        color = values['color'] or self._automatic[group]
        row['name'].value = group_badge(group, color)
        row['label'].value = values['label'] or self._defaults[group]
        row['color'].value = color
        row['reset'].disabled = values['color'] is None
        row['mode'].value = '<small style="color:var(--tw-muted,#526170)">' + ('Custom colour' if values['color'] else 'Palette colour') + '</small>'

    def _edit(self, analysis, group, field, value):
        if self._syncing or analysis != self.analysis or group not in self.rows:
            return
        if field == 'label':
            value = value.strip() or None
            if value == self._defaults[group]:
                value = None
        edits = self._drafts.setdefault(analysis, {}).setdefault(group, {})
        before = edits.get(field, {}).get('before', self._saved[group][field])
        if value == before:
            edits.pop(field, None)
        else:
            edits[field] = {'before': before, 'after': value}
        if not edits:
            self._drafts[analysis].pop(group, None)
        self._syncing = True
        try:
            self._paint(group)
        finally:
            self._syncing = False
        self._status()

    def _status(self):
        count = len(self._drafts.get(self.analysis, {}))
        self.apply.disabled = self.discard.disabled = not count
        self.status.value = (f'{count} edited group' + ('s' if count != 1 else '') + ' · not applied yet'
                             if count else f'{len(self.rows)} groups · changes apply together')

    def _apply(self, _):
        edits = deepcopy(self._drafts.get(self.analysis, {}))
        if not edits:
            return
        try:
            self.on_apply(self.analysis, edits)
        except Exception as error:
            self.status.value = '<b>Not applied:</b> ' + escape(str(error))
            return
        self._drafts.pop(self.analysis, None)
        self._status()
        self.status.value = '✓ Labels and colours saved'

    def _discard(self, _):
        self._drafts.pop(self.analysis, None)
        self._syncing = True
        try:
            for group in self.rows:
                self._paint(group)
        finally:
            self._syncing = False
        self._status()

    def _close_rows(self):
        self.grid.children = ()
        for row in self.rows.values():
            for widget in reversed(row['owned']):
                widget.close()
        self.rows.clear()

    def close(self):
        self._close_rows()
        self.ui.close()
