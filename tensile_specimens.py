"""Editable inclusion column; numerical properties stay read-only."""
import anywidget
import traitlets


class SpecimenTable(anywidget.AnyWidget):
    columns = traitlets.List(traitlets.Unicode()).tag(sync=True)
    rows = traitlets.List(traitlets.Dict()).tag(sync=True)
    context = traitlets.Unicode('').tag(sync=True)

    _css = """
    .tw-specimens {overflow:auto; max-height:510px; width:100%; border:1px solid #cbd5e1; box-sizing:border-box;}
    .tw-specimens table {border-collapse:separate; border-spacing:0; width:100%; font:12px/1.4 Arial,sans-serif;}
    .tw-specimens th,.tw-specimens td {padding:7px 9px; border-bottom:1px solid #dce3e9; text-align:right; min-width:100px;}
    .tw-specimens th {position:sticky; top:0; z-index:2; background:#e8eef4; color:#152c3f; text-align:left;}
    .tw-specimens td {background:#fff;}
    .tw-specimens tr:nth-child(even) td {background:#f6f8fa;}
    .tw-specimens tr.excluded td {background:#eef0f3; color:#737b86;}
    .tw-specimens tr.fit-warning td:first-child {border-left:4px solid #d97706;}
    .tw-specimens .fit-override {color:#175ca5;font-weight:bold;}
    .tw-specimens th:first-child,.tw-specimens td:first-child {position:sticky; left:0; min-width:62px; text-align:center; z-index:1;}
    .tw-specimens th:first-child {z-index:3;}
    .tw-specimens td:nth-child(2),.tw-specimens td:nth-child(3) {text-align:left; min-width:130px; max-width:220px; overflow-wrap:anywhere;}
    .tw-specimens input[type=checkbox] {width:17px; height:17px; cursor:pointer; accent-color:#1767a5;}
    .tw-specimens input[type=text] {box-sizing:border-box; width:215px; padding:5px; border:1px solid #b6c1cd; border-radius:3px; font:inherit; color:#24354a; background:#fff;}
    .tw-specimens input:focus-visible {outline:2px solid #1767a5; outline-offset:2px;}
    .tw-specimens input:disabled {cursor:default; opacity:.65;}
    .tw-specimens select {font:inherit;padding:5px;min-width:135px;cursor:pointer;}
    .tw-specimens .selection-scope {text-align:left;white-space:nowrap;}
    .tw-specimens .selection-scope small {display:block;color:#526170;}
    .tw-specimens .checks {white-space:pre-line;text-align:left;min-width:260px;max-width:420px;color:#944900;}
    .tw-specimens .inspect {border:0;background:none;padding:0;color:#1767a5;text-align:left;font:inherit;cursor:pointer;overflow-wrap:anywhere;}
    .tw-specimens .inspect:hover {text-decoration:underline;}
    .tw-specimens .inspect:focus-visible {outline:2px solid #1767a5;outline-offset:3px;}
    """
    _esm = """
    export default {render({model, el}) {
      const container = document.createElement('div');
      container.className = 'tw-specimens';
      container.setAttribute('role','region');
      container.setAttribute('aria-label','Specimen inclusion and properties');
      el.append(container);
      function render() {
        const left = container.scrollLeft, top = container.scrollTop;
        const context = model.get('context');
        const table = document.createElement('table');
        const header = table.createTHead().insertRow();
        ['Include','Group','Specimen','Applies to','Exclusion reason (optional)',...model.get('columns')].forEach(label => {
          const th = document.createElement('th'); th.textContent = label; th.scope='col'; header.append(th);
        });
        const body = table.createTBody();
        let pending = false;
        for (const row of model.get('rows')) {
          const tr = body.insertRow();
          if (!row.included) tr.className='excluded';
          if (row.check_warning || row.fit_warning) tr.classList.add('fit-warning');
          const check = document.createElement('input'); check.type='checkbox'; check.checked=row.included;
          check.setAttribute('aria-label', 'Include ' + row.group + ' / ' + row.sample);
          tr.insertCell().append(check);
          tr.insertCell().textContent=row.group;
          const inspect = document.createElement('button'); inspect.type='button'; inspect.className='inspect';
          inspect.textContent=(row.check_warning || row.fit_warning ? '⚠ ' : '') + row.sample; inspect.title='Inspect this specimen’s property calculations';
          inspect.setAttribute('aria-label','Inspect ' + row.group + ' / ' + row.sample);
          inspect.addEventListener('click', () => model.send({type:'inspect', context, id:row.id}));
          tr.insertCell().append(inspect);
          tr.title=row.id;
          const scope = document.createElement('select');
          [['global','Global default'],['graph','This graph only']].forEach(([value,label]) => {
            const option=document.createElement('option'); option.value=value; option.textContent=label; scope.append(option);
          });
          scope.value=row.scope || 'global';
          scope.setAttribute('aria-label','Inclusion scope for ' + row.group + ' / ' + row.sample);
          const scopeCell=tr.insertCell(); scopeCell.className='selection-scope'; scopeCell.append(scope);
          if (row.scope==='graph') {
            const note=document.createElement('small'); note.textContent='Global: ' + (row.global_included ? 'included' : 'excluded');
            scopeCell.append(note);
          }
          const reason = document.createElement('input'); reason.type='text'; reason.value=row.reason;
          reason.placeholder='Optional reason'; reason.disabled=row.included; reason.maxLength=2000;
          reason.setAttribute('aria-label','Exclusion reason for ' + row.group + ' / ' + row.sample);
          tr.insertCell().append(reason);
          row.values.forEach((value, index) => {
            const cell=tr.insertCell(); cell.textContent=value;
            if (model.get('columns')[index]==='Fit method' && value.startsWith('Manual')) cell.className='fit-override';
            if (model.get('columns')[index]==='Checks') cell.className='checks';
          });
          const submit = (action='selection') => {
            if (pending) return;
            pending = true;
            const message = {type:'selection', context, id:row.id, included:check.checked,
                             reason:reason.value, scope:scope.value, action};
            // Wait for the Python-side save/validation; don't silently change statistics in the browser.
            container.querySelectorAll('input, select').forEach(input => {input.disabled=true;});
            model.send(message);
          };
          check.addEventListener('change', () => submit());
          scope.addEventListener('change', () => submit(scope.value==='global' ? 'inherit' : 'selection'));
          let edited = false;
          reason.addEventListener('input', () => {edited=true;});
          reason.addEventListener('change', () => submit());
          reason.addEventListener('blur', () => {if(edited) submit();});
          reason.addEventListener('keydown', event => {if(event.key==='Enter') {event.preventDefault(); submit();}});
        }
        container.replaceChildren(table);
        if (!model.get('rows').length) {
          const note=document.createElement('p'); note.textContent='No matching specimens.'; container.append(note);
        }
        container.scrollLeft=left; container.scrollTop=top;
      }
      model.on('change:rows change:columns change:context', render); render();
      return () => {model.off('change:rows change:columns change:context', render);};
    }};
    """

    def __init__(self, on_selection=None, on_inspect=None, **kwargs):
        super().__init__(**kwargs)
        self.on_selection = on_selection
        self.on_inspect = on_inspect
        self.on_msg(self._receive)

    def _receive(self, widget, content, buffers):
        if content.get('context') != self.context:
            return
        if content.get('id') not in {row['id'] for row in self.rows}:
            return
        if content.get('type') == 'inspect':
            if self.on_inspect:
                self.on_inspect(content['id'])
            return
        if (content.get('type') != 'selection' or not isinstance(content.get('included'), bool)
                or not isinstance(content.get('reason'), str)
                or content.get('scope', 'global') not in ('global', 'graph')
                or content.get('action', 'selection') not in ('selection', 'inherit')):
            return
        if self.on_selection:
            self.on_selection(content['id'], content['included'], content['reason'][:2000],
                              content.get('scope', 'global'), content.get('action', 'selection'))
