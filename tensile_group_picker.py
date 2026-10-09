"""Hierarchical group selection; folders select leaves, never merge datasets."""
from html import escape
import uuid

import anywidget
import traitlets

from tensile_selection import SAMPLE_GROUP_PREFIX


class FolderCheckbox(anywidget.AnyWidget):
    """Native checked/mixed/unchecked checkbox, including keyboard support."""
    label = traitlets.Unicode().tag(sync=True)
    state = traitlets.Unicode('none').tag(sync=True)
    count = traitlets.Unicode().tag(sync=True)
    _css = """
      .tw-folder-check {display:flex;align-items:center;gap:6px;cursor:pointer;
        font:inherit;line-height:1.2;margin:0;padding:2px 0;}
      .tw-folder-check input {accent-color:#1767a5;cursor:pointer;margin:0;flex:0 0 auto;}
      .tw-folder-check strong {overflow-wrap:anywhere;}
      .tw-folder-check small {color:#526170;white-space:nowrap;font-weight:normal;}
    """
    _esm = """
    export default {render({model,el}) {
      const label=document.createElement('label'); label.className='tw-folder-check';
      const input=document.createElement('input'); input.type='checkbox';
      const text=document.createElement('strong'), count=document.createElement('small');
      label.append(input,text,count); el.append(label);
      const draw=() => {
        const state=model.get('state');
        input.checked=state==='all'; input.indeterminate=state==='some';
        input.setAttribute('aria-checked',state==='some'?'mixed':String(input.checked));
        text.textContent=model.get('label'); count.textContent=model.get('count');
        label.title='Select or clear every sample group below this folder';
      };
      const change=() => model.send({action:'toggle',checked:input.checked});
      input.addEventListener('change',change);
      model.on('change:state change:label change:count',draw); draw();
      return () => {input.removeEventListener('change',change);
        model.off('change:state change:label change:count',draw);};
    }};
    """


def group_tree(options):
    """Keep folder identity separate from labels and the bundled-data namespace."""
    root = {'folders': {}, 'groups': []}
    for option in options:
        label, group = option if isinstance(option, (tuple, list)) else (option, option)
        bundled = group.startswith(SAMPLE_GROUP_PREFIX)
        relative = group[len(SAMPLE_GROUP_PREFIX):] if bundled else group
        parts = relative.split('/')
        folders = ([('bundled', 'Sample data')] if bundled else [])
        folders += [('folder:' + part, part) for part in parts[:-1]]
        node = root
        for key, name in folders:
            node = node['folders'].setdefault(key, {'label': name, 'folders': {}, 'groups': []})
        # Existing display labels (including unavailable/sample suffixes) remain
        # intact; only the redundant organisational path is shortened in-tree.
        prefix = '/'.join(parts[:-1]) + '/' if len(parts) > 1 else ''
        short_label = label.removeprefix(SAMPLE_GROUP_PREFIX).removeprefix(prefix) if bundled else label.removeprefix(prefix)
        node['groups'].append((short_label, group))
    return root


class GroupCheckboxes:
    """Drive the existing exact-group model with arbitrarily nested folder checks."""
    def __init__(self, widgets, selection, display_names=None):
        self.w, self.selection = widgets, selection
        self.display_names = display_names or {}
        self.boxes, self.folder_boxes, self.folder_members = {}, {}, {}
        self._owned, self._expanded = [], set()
        self._syncing = False
        self._scope = 'tensile-groups-' + uuid.uuid4().hex
        self.summary = widgets.HTML(layout=widgets.Layout(width='100%', min_width='0'))
        self.clear_button = widgets.Button(description='Clear selection', layout=widgets.Layout(width='auto'))
        self.grid = widgets.VBox(layout=widgets.Layout(width='100%', min_width='0', max_width='980px'))
        compact = widgets.HTML('<style>.' + self._scope + '{column-width:180px;column-gap:16px;column-fill:balance;}'
            '.' + self._scope + '>.widget-checkbox{break-inside:avoid;page-break-inside:avoid;'
            'width:100%;height:auto;min-height:0;margin:0;padding:2px 0;line-height:1.1;}'
            '.' + self._scope + '>.widget-checkbox label,.' + self._scope + '>.widget-checkbox span{line-height:1.1;}'
            '</style>', layout=widgets.Layout(height='0px', min_height='0px', margin='0', overflow='hidden'))
        self.ui = widgets.VBox([
            widgets.HTML('<b>Sample groups</b>'), compact, self.grid,
            widgets.HBox([self.summary, self.clear_button], layout=widgets.Layout(
                width='100%', flex_flow='row wrap', gap='12px', align_items='center')),
        ], layout=widgets.Layout(width='100%', min_width='0'))
        selection.observe(self._options_changed, names='options')
        selection.observe(self._value_changed, names='value')
        self.clear_button.on_click(lambda _: setattr(selection, 'value', ()))
        self._options_changed()

    def _options_changed(self, _=None):
        self.grid.children = ()
        for widget in reversed(self._owned):
            widget.close()
        self._owned = []
        self.boxes, self.folder_boxes, self.folder_members = {}, {}, {}
        children, _ = self._branch(group_tree(self.selection.options), ())
        self.grid.children = tuple(children)
        self._value_changed()

    def _branch(self, node, path):
        w = self.w
        children, members = [], []
        leaves = []
        for label, group in node['groups']:
            box = w.Checkbox(value=group in self.selection.value, description=label, indent=False,
                tooltip=group + '\n' + self.display_names.get(group, label), layout=w.Layout(width='auto'))
            box.observe(self._checked, names='value')
            self.boxes[group] = box
            self._owned.append(box)
            leaves.append(box)
            members.append(group)
        if leaves:
            grid = w.Box(leaves, layout=w.Layout(display='block', width='100%', min_width='0'))
            grid.add_class(self._scope)
            self._owned.append(grid)
            children.append(grid)
        for key, folder in node['folders'].items():
            branch_path = (*path, key)
            nested, descendants = self._branch(folder, branch_path)
            body = w.VBox(nested, layout=w.Layout(width='auto', min_width='0', margin='0 0 0 22px',
                display='flex' if branch_path in self._expanded else 'none'))
            checkbox = FolderCheckbox(label=folder['label'], layout=w.Layout(width='auto', min_width='0'))
            checkbox.on_msg(lambda _, content, buffers, p=branch_path: self._folder_message(p, content))
            toggle = w.Button(icon='caret-down' if branch_path in self._expanded else 'caret-right',
                tooltip='Expand/collapse folder', layout=w.Layout(width='22px', min_width='22px',
                                                                  height='24px', margin='0', padding='0'))
            toggle.on_click(lambda button, p=branch_path, b=body: self._toggle_folder(p, b, button))
            header = w.HBox([toggle, checkbox], layout=w.Layout(align_items='center', min_width='0', gap='4px'))
            branch = w.VBox([header, body], layout=w.Layout(width='100%', min_width='0', margin='3px 0'))
            self.folder_boxes[branch_path] = checkbox
            self.folder_members[branch_path] = tuple(descendants)
            self._owned.extend([body, checkbox, toggle, header, branch])
            children.append(branch)
            members.extend(descendants)
        return children, members

    def _folder_message(self, path, content):
        if (path in self.folder_members and content.get('action') == 'toggle'
                and isinstance(content.get('checked'), bool)):
            self.select_folder(path, content['checked'])

    def select_folder(self, path, checked):
        descendants = set(self.folder_members[path])
        selected = set(self.selection.value)
        selected = selected | descendants if checked else selected - descendants
        # One change notification/autosave for the whole folder, not one per leaf.
        self.selection.value = tuple(group for group in self._option_groups() if group in selected)

    def _option_groups(self):
        return [item[1] if isinstance(item, (tuple, list)) else item for item in self.selection.options]

    def _toggle_folder(self, path, body, button):
        if path in self._expanded:
            self._expanded.remove(path)
        else:
            self._expanded.add(path)
        body.layout.display = 'flex' if path in self._expanded else 'none'
        button.icon = 'caret-down' if path in self._expanded else 'caret-right'

    def _value_changed(self, _=None):
        self._syncing = True
        try:
            selected = set(self.selection.value)
            for group, box in self.boxes.items():
                box.value = group in selected
            for path, box in self.folder_boxes.items():
                members = self.folder_members[path]
                count = len(selected.intersection(members))
                with box.hold_sync():
                    box.state = 'all' if count == len(members) else 'some' if count else 'none'
                    box.count = f'({count}/{len(members)} groups)'
        finally:
            self._syncing = False
        self.summary.value = ('<span style="white-space:normal"><b>Selected (' + str(len(selected)) + '):</b> ' +
                              escape(' · '.join(self.selection.value) if selected else 'None') + '</span>')
        self.clear_button.disabled = not selected

    def _checked(self, _):
        if not self._syncing:
            self.selection.value = tuple(group for group in self._option_groups() if self.boxes[group].value)
