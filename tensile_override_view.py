"""Project-wide saved specimen settings browser; never computes tensile curves."""
from copy import deepcopy
from html import escape

import anywidget
import traitlets

from tensile_overrides import KINDS, change_overrides, override_rows
from tensile_selection import SAMPLE_GROUP_PREFIX, SAMPLE_ID_PREFIX
from tensile_activity import busy


class OverrideTable(anywidget.AnyWidget):
    rows = traitlets.List(traitlets.Dict()).tag(sync=True)
    selected = traitlets.List(traitlets.Unicode()).tag(sync=True)

    _css = """
    .tw-overrides {width:100%;max-width:100%;min-width:0;overflow:auto;max-height:65vh;
      border:1px solid #cbd5e1;box-sizing:border-box;font:13px/1.45 Arial,sans-serif;}
    .tw-overrides table {width:100%;border-collapse:separate;border-spacing:0;}
    .tw-overrides th {position:sticky;top:0;background:#e8eef4;color:#152c3f;z-index:1;white-space:nowrap;}
    .tw-overrides th,.tw-overrides td {padding:9px 12px;text-align:left;border-bottom:1px solid #dce3e9;vertical-align:top;}
    .tw-overrides tr:nth-child(even) td {background:#f6f8fa;}
    .tw-overrides tr.selected td {background:#edf5ff;}
    .tw-overrides .setting,.tw-overrides .reason {min-width:160px;max-width:300px;white-space:pre-line;overflow-wrap:anywhere;}
    .tw-overrides .identity {min-width:120px;max-width:240px;overflow-wrap:anywhere;}
    .tw-overrides small {display:block;color:#637385;margin-top:3px;}
    .tw-overrides details {margin-top:4px;}
    .tw-overrides summary {cursor:pointer;color:#1767a5;font-size:12px;}
    .tw-overrides .path {max-width:260px;overflow-wrap:anywhere;user-select:all;}
    .tw-overrides .badge {display:inline-block;padding:2px 7px;border-radius:12px;white-space:nowrap;
      background:#e6f2eb;color:#246046;font-size:12px;}
    .tw-overrides .off {background:#eceef2;color:#536172;}
    .tw-overrides .unavailable {color:#94530c;}
    .tw-overrides input[type=checkbox] {width:17px;height:17px;accent-color:#1767a5;cursor:pointer;}
    .tw-overrides input:focus-visible {outline:2px solid #1767a5;outline-offset:2px;}
    .tw-overrides .empty {padding:20px;color:#637385;}
    """
    _esm = """
    export default {render({model,el}) {
      const box=document.createElement('div'); box.className='tw-overrides'; box.tabIndex=0;
      box.setAttribute('role','region'); box.setAttribute('aria-label','Saved specimen overrides across all graphs');
      el.append(box);
      let header, inputs=[];
      function select(ids) {model.set('selected',ids);model.save_changes();}
      function sync() {
        const selected=new Set(model.get('selected'));
        inputs.forEach(({input,tr,id}) => {input.checked=selected.has(id);tr.classList.toggle('selected',input.checked);});
        if(header) {
          const n=inputs.filter(item => selected.has(item.id)).length;
          header.checked=inputs.length>0 && n===inputs.length;
          header.indeterminate=n>0 && n<inputs.length;
          header.disabled=inputs.length===0;
        }
      }
      function render() {
        const left=box.scrollLeft,top=box.scrollTop;
        inputs=[];
        const table=document.createElement('table'), head=table.createTHead().insertRow();
        const checkCell=document.createElement('th'); checkCell.scope='col';
        header=document.createElement('input'); header.type='checkbox';
        header.setAttribute('aria-label','Select all visible overrides');checkCell.append(header);head.append(checkCell);
        header.addEventListener('change',()=>select(header.checked ? model.get('rows').map(row=>row.id) : []));
        ['Group','Specimen','Override','Applies to','Setting','Reason','Status','Data'].forEach(label=>{
          const th=document.createElement('th');th.scope='col';th.textContent=label;head.append(th);
        });
        const body=table.createTBody();
        for(const row of model.get('rows')) {
          const tr=body.insertRow();
          const input=document.createElement('input');input.type='checkbox';
          input.setAttribute('aria-label','Select '+row.specimen+' · '+row.type+' · '+row.scope_name);
          tr.insertCell().append(input);inputs.push({input,tr,id:row.id});
          input.addEventListener('change',()=>{
            const selected=new Set(model.get('selected'));
            if(input.checked) selected.add(row.id);else selected.delete(row.id);
            select([...selected]);
          });
          const group=tr.insertCell();group.className='identity';group.textContent=row.group.split('/').pop();group.title=row.group;
          const specimen=tr.insertCell();specimen.className='identity';specimen.textContent=row.specimen;
          if(row.label_source==='CSV filename') {const note=document.createElement('small');note.textContent='CSV filename';specimen.append(note);}
          const details=document.createElement('details'),summary=document.createElement('summary'),path=document.createElement('div');
          summary.textContent='Source identity';path.className='path';path.textContent=row.specimen_id;
          details.append(summary,path);specimen.append(details);
          tr.insertCell().textContent=row.type;
          const scope=tr.insertCell();scope.className='identity';scope.textContent=row.scope===null ? 'Global' : 'Graph: '+row.scope_name;
          const setting=tr.insertCell();setting.className='setting';setting.textContent=row.setting;
          const reason=tr.insertCell();reason.className='reason';reason.textContent=row.reason || '—';
          const badge=document.createElement('span');badge.className='badge'+(row.enabled ? '' : ' off');
          badge.textContent=row.enabled ? 'Enabled' : 'Disabled';tr.insertCell().append(badge);
          const available=tr.insertCell();available.className=row.availability==='Available' ? '' : 'unavailable';
          available.textContent=row.availability;
        }
        box.replaceChildren(table);
        if(!model.get('rows').length) {const p=document.createElement('p');p.className='empty';p.textContent='No saved overrides match these filters.';box.append(p);}
        sync();box.scrollLeft=left;box.scrollTop=top;
      }
      model.on('change:rows',render);model.on('change:selected',sync);render();
      return ()=>{model.off('change:rows',render);model.off('change:selected',sync);};
    }};
    """


class SavedOverridesView:
    def __init__(self, widgets, store, session, *, before_apply, after_apply):
        self.w, self.store, self.session = widgets, store, session
        self.before_apply, self.after_apply = before_apply, after_apply
        self._rows, self._pending, self._refreshing = [], [], False
        w = widgets
        compact = lambda: w.Layout(width='auto', flex='0 0 auto')
        self.search = w.Text(placeholder='Group, specimen, setting or reason', continuous_update=False,
                             layout=w.Layout(width='300px'))
        self.kind = w.Dropdown(options=[('All override types', '')] + [(v,k) for k,v in KINDS.items()],
                              layout=w.Layout(width='235px'))
        self.scope = w.Dropdown(options=[('All scopes', '*'), ('Global only', '')], layout=w.Layout(width='240px'))
        self.state = w.Dropdown(options=[('Enabled and disabled', ''), ('Enabled only', 'enabled'),
                                        ('Disabled only', 'disabled')], layout=w.Layout(width='205px'))
        self.refresh_button = w.Button(description='Refresh list', layout=compact())
        self.disable = w.Button(description='Disable selected', disabled=True, layout=compact())
        self.enable = w.Button(description='Enable selected', disabled=True, layout=compact())
        self.remove = w.Button(description='Remove selected…', disabled=True, button_style='danger', layout=compact())
        self.clear = w.Button(description='Clear selection', disabled=True, layout=compact())
        self.table = OverrideTable(layout=w.Layout(width='100%', min_width='0'))
        self.count, self.message, self.confirm_message = w.HTML(), w.HTML(), w.HTML()
        self.confirm_remove = w.Button(description='Confirm remove', button_style='danger', layout=compact())
        self.cancel = w.Button(description='Cancel', layout=compact())
        row = lambda items: w.HBox(items, layout=w.Layout(flex_flow='row wrap', gap='8px', align_items='center'))
        self.confirmation = w.VBox([self.confirm_message, row([self.confirm_remove, self.cancel])],
                                   layout=w.Layout(display='none'))
        self.ui = w.VBox([
            w.HTML('<h3>Saved specimen overrides</h3><p>Current settings across <b>all specimens and saved graphs</b>, '
                   'not just the current graph. Tick rows to manage them; the header checkbox selects all visible rows. '
                   'Changing filters clears the selection.</p><p><b>Disable</b> retains the setting without applying it; '
                   '<b>Enable</b> restores it. <b>Remove</b> deletes the setting after confirmation. '
                   'Without a graph override, the global setting applies; without a global override, automatic/default '
                   'behaviour applies. Enabled/disabled refers to the <b>override</b>, not specimen inclusion. '
                   'Source files and exports are never changed.</p>'),
            row([self.search, self.kind, self.scope, self.state, self.refresh_button]),
            row([self.disable, self.enable, self.remove, self.clear]), self.count,
            self.message, self.confirmation, self.table,
            w.HTML('<small>Unavailable specimens retain their saved settings. Hidden bundled samples are not loaded here. '
                   'Specimen labels are used when already loaded; otherwise the CSV filename identifies the specimen. '
                   'Source identity expands to its full relative path. Group-wide settings and deleted-graph recovery '
                   'snapshots are not listed. This is not a history log.</small>')
        ], layout=w.Layout(width='100%', min_width='0', padding='10px'))
        for control in (self.search, self.kind, self.scope, self.state):
            control.observe(lambda _: self._filter() if not self._refreshing else None, names='value')
        self.table.observe(lambda _: self._selection_changed(), names='selected')
        self.refresh_button.on_click(lambda _: self.refresh())
        self.clear.on_click(lambda _: setattr(self.table, 'selected', []))
        self.disable.on_click(lambda _: self._apply('disable'))
        self.enable.on_click(lambda _: self._apply('enable'))
        self.remove.on_click(lambda _: self._ask_remove())
        self.cancel.on_click(lambda _: self._cancel())
        self.confirm_remove.on_click(lambda _: self._apply('remove', self._pending))

    def refresh(self):
        """Read settings/discovery only; opening the page must not process CSVs."""
        available, labels = {}, {}
        for group, paths in self.session.files.items():
            root = self.session.source_roots[group]
            for path in paths:
                ident = path.relative_to(root).as_posix()
                if group.startswith(SAMPLE_GROUP_PREFIX):
                    ident = SAMPLE_ID_PREFIX + ident
                available[ident] = group
        for records in self.session._records.values():
            for record in records:
                if record.get('specimen_label'):
                    labels[record['specimen_id']] = record['specimen_label']
        self._rows = override_rows(self.store.data, available, labels, self.session.files)
        self._refreshing = True
        try:
            previous = self.scope.value
            self.scope.options = [('All scopes', '*'), ('Global only', '')] + [
                ('Graph: ' + graph['name'], graph['id']) for graph in self.store.data['graphs']]
            self.scope.value = previous if previous in {value for _,value in self.scope.options} else '*'
        finally:
            self._refreshing = False
        self.message.value = ''
        self._filter()

    def _filter(self):
        self._cancel()
        self.table.selected = []
        text = self.search.value.strip().casefold()
        visible = [row for row in self._rows
            if (not self.kind.value or row['kind'] == self.kind.value)
            and (self.scope.value == '*' or row['scope'] == (self.scope.value or None))
            and (not self.state.value or row['enabled'] == (self.state.value == 'enabled'))
            and (not text or text in ' '.join(str(row[key]) for key in
                 ('group', 'specimen', 'specimen_id', 'scope_name', 'type', 'setting', 'reason')).casefold())]
        # Never send source fingerprints or automatic-result snapshots to a table cell.
        self.table.rows = [{key:value for key,value in row.items() if key != 'value'} for row in visible]
        self._selection_changed()

    def _selected(self):
        ids = set(self.table.selected) & {row['id'] for row in self.table.rows}
        return [row for row in self._rows if row['id'] in ids]

    def _selection_changed(self):
        self._cancel()
        selected = self._selected()
        self.disable.disabled = not any(row['enabled'] for row in selected)
        self.enable.disabled = not any(not row['enabled'] for row in selected)
        self.remove.disabled = self.clear.disabled = not selected
        self.count.value = f'{len(self.table.rows)} of {len(self._rows)} overrides shown · {len(selected)} selected'

    def _cancel(self):
        self._pending = []
        self.confirmation.layout.display = 'none'

    def _ask_remove(self):
        self._pending = deepcopy(self._selected())
        if not self._pending:
            return
        names = ''.join('<li>' + escape(f"{row['group']} / {row['specimen']} · {row['type']} · "
                    + ('Global' if row['scope'] is None else 'Graph: ' + row['scope_name'])) + '</li>'
                    for row in self._pending)
        self.confirm_message.value = (f'<b>Remove {len(self._pending)} saved override(s)?</b> '
            'Removed settings cannot be re-enabled. Automatic/default or inherited settings will apply. '
            'Source files are untouched.<details><summary>Review selected overrides</summary><ul>' + names + '</ul></details>')
        self.confirmation.layout.display = ''

    @busy('Updating saved specimen overrides…')
    def _apply(self, action, selected=None):
        selected = deepcopy(self._selected() if selected is None else selected)
        if not selected:
            return
        controls = (self.disable, self.enable, self.remove, self.confirm_remove)
        for control in controls:
            control.disabled = True
        try:
            if not self.before_apply():
                raise ValueError('Resolve the graph-save warning before changing overrides.')
            project = change_overrides(self.store.data, selected, action)
            if project != self.store.data:
                self.store.save(project)
        except Exception as error:
            self.message.value = '<b>Overrides not changed:</b> ' + escape(str(error))
            self._cancel()
        else:
            count = sum(action == 'remove' or row['enabled'] == (action == 'disable') for row in selected)
            verb = {'disable':'Disabled', 'enable':'Enabled', 'remove':'Removed'}[action]
            try:
                self.after_apply()
                self.refresh()
                self.message.value = f'{verb} {count} override(s). Update tables or plots on the Analysis page when ready.'
            except Exception as error:
                self.message.value = '<b>Settings saved.</b> Reload the app to refresh the view: ' + escape(str(error))
        finally:
            self.confirm_remove.disabled = False
            self._selection_changed()
