"""Editable variable grid. Clipboard imports remain drafts until explicitly saved."""
from copy import deepcopy
import csv
import io
import math
import uuid

import anywidget
import traitlets


def paste_cells(columns, groups, row, column, text):
    """Apply a rectangular CSV/TSV block atomically, never inventing sample groups."""
    if (type(row) is not int or type(column) is not int
            or not 0 <= row < len(groups) + 2 or not 0 <= column < len(columns)):
        raise ValueError('Select a variable cell to paste into.')
    if not isinstance(text, str) or len(text) > 1_000_000:
        raise ValueError('Paste a smaller block (at most 1 MB).')
    text = text.removeprefix('\ufeff')
    # Excel uses tabs; ignore tabs inside quoted CSV fields when detecting them.
    quoted, delimiter = False, ','
    for char in text:
        if char == '"':
            quoted = not quoted
        elif char == '\t' and not quoted:
            delimiter = '\t'
            break
    try:
        block = list(csv.reader(io.StringIO(text, newline=''), delimiter=delimiter, strict=True))
    except csv.Error as error:
        raise ValueError('Could not read the quoted CSV/TSV block.') from error
    if not block:
        block = [['']]
    width = max((len(line) for line in block), default=1) or 1
    block = [line or [''] * width for line in block]
    if not width or any(len(line) != width for line in block):
        raise ValueError('Paste a rectangular block: each row must have the same number of cells.')
    if row + len(block) > len(groups) + 2:
        raise ValueError('The block extends beyond the visible rows. Show all rows or paste fewer rows.')
    if width + column > 200 or len(block) * width > 100_000:
        raise ValueError('Paste a smaller block (at most 200 variable columns / 100,000 cells).')
    result = deepcopy(columns)
    while len(result) < column + width:
        result.append(dict(id='var-' + uuid.uuid4().hex, name='', unit='', values={}))
    for dr, line in enumerate(block):
        r = row + dr
        for dc, value in enumerate(line):
            target = result[column + dc]
            if r < 2:
                target['name' if r == 0 else 'unit'] = value
            else:
                if value.strip():
                    try:
                        valid = math.isfinite(float(value))
                    except ValueError:
                        valid = False
                    if not valid:
                        raise ValueError(f'{groups[r - 2]}, variable {column + dc + 1}: '
                                         'use a finite number or a blank cell (no formulas). Nothing pasted.')
                target['values'][groups[r - 2]] = value
    return result


class VariableTable(anywidget.AnyWidget):
    columns = traitlets.List(traitlets.Dict()).tag(sync=True)
    groups = traitlets.List(traitlets.Unicode()).tag(sync=True)
    labels = traitlets.Dict().tag(sync=True)
    notice = traitlets.Unicode('').tag(sync=True)

    _css = """
    .tw-variable-grid {max-width:100%;min-width:0;overflow:auto;max-height:440px;
      border:1px solid #cbd5e1;box-sizing:border-box;font:13px/1.4 Arial,sans-serif;}
    .tw-variable-grid table {border-collapse:separate;border-spacing:0;width:max-content;min-width:100%;}
    .tw-variable-grid td,.tw-variable-grid th {padding:4px 6px;border-right:1px solid #dce3e9;
      border-bottom:1px solid #dce3e9;box-sizing:border-box;height:40px;text-align:left;}
    .tw-variable-grid td {background:#fff;}
    .tw-variable-grid tbody tr:nth-child(even) td {background:#f6f8fa;}
    .tw-variable-grid th {background:#e8eef4;color:#152c3f;}
    .tw-variable-grid thead th {position:sticky;top:0;z-index:2;}
    .tw-variable-grid thead tr:nth-child(2) th {top:40px;}
    .tw-variable-grid .group {position:sticky;left:0;z-index:1;min-width:220px;max-width:320px;
      overflow-wrap:anywhere;font-weight:normal;}
    .tw-variable-grid thead .group {z-index:3;font-weight:bold;}
    .tw-variable-grid input {box-sizing:border-box;width:190px;height:30px;padding:4px 6px;
      border:1px solid #b6c1cd;border-radius:3px;background:white;color:#24354a;font:inherit;}
    .tw-variable-grid tbody input {text-align:right;font-variant-numeric:tabular-nums;}
    .tw-variable-grid input:focus {outline:2px solid #1767a5;outline-offset:0;}
    .tw-variable-heading {display:flex;align-items:center;gap:6px;}
    .tw-variable-delete {width:25px;height:28px;flex:0 0 25px;border:1px solid #cbd5e1;
      border-radius:3px;background:#fff;color:#a42b2b;cursor:pointer;font-size:18px;}
    .tw-variable-grid-note {margin:6px 0;color:#526170;white-space:pre-wrap;}
    .tw-variable-copy {margin:0 0 8px;padding:5px 10px;cursor:pointer;}
    """
    _esm = r"""
    export default {render({model,el}) {
      const copy=document.createElement('button');copy.type='button';copy.className='tw-variable-copy';
      copy.textContent='Copy variable cells (TSV)';
      const box=document.createElement('div');box.className='tw-variable-grid';box.tabIndex=0;
      box.setAttribute('role','region');box.setAttribute('aria-label','Editable custom variables');
      const note=document.createElement('div');note.className='tw-variable-grid-note';note.setAttribute('role','status');
      el.append(copy,box,note);
      let local=false;
      let renderFrame;
      const scheduleRender=()=>{
        if(local || renderFrame!==undefined) return;
        renderFrame=requestAnimationFrame(()=>{renderFrame=undefined;render();});
      };
      function status() {note.textContent=model.get('notice');}
      function render() {
        if(local) return;
        const left=box.scrollLeft,top=box.scrollTop,active=document.activeElement;
        const focus=box.contains(active) && active.matches('input') ?
          {r:active.dataset.row,c:active.dataset.col,start:active.selectionStart,end:active.selectionEnd} : null;
        const columns=model.get('columns'),groups=model.get('groups'),labels=model.get('labels');
        const table=document.createElement('table'),head=table.createTHead(),body=table.createTBody();
        ['Name','Unit',...groups].forEach((label,r)=>{
          const tr=(r<2 ? head : body).insertRow(),group=document.createElement('th');
          const caption=r<2 ? label : (labels[label] || label);
          group.textContent=caption;group.title=label;group.className='group';group.scope='row';tr.append(group);
          columns.forEach((column,c)=>{
            const cell=document.createElement(r<2 ? 'th' : 'td'),input=document.createElement('input');
            input.type='text';input.dataset.row=r;input.dataset.col=c;
            input.setAttribute('aria-label',r===0 ? 'Variable name '+(c+1) :
              r===1 ? 'Variable unit '+(c+1) : caption+' · variable '+(c+1));
            input.value=r===0 ? column.name : r===1 ? column.unit : (column.values[label] ?? '');
            input.placeholder=r===0 ? 'Variable name' : r===1 ? 'Optional unit' : 'Not set';
            input.addEventListener('input',()=>{
              const updated=structuredClone(model.get('columns'));
              if(r<2) updated[c][r===0 ? 'name' : 'unit']=input.value;
              else updated[c].values[label]=input.value;
              local=true;model.set('columns',updated);model.save_changes();local=false;
              model.set('notice','Unsaved changes. Click Save all variables to apply.');model.save_changes();
            });
            input.addEventListener('paste',event=>{
              const text=event.clipboardData?.getData('text/plain');
              if(text===undefined) return;
              // Native paste handles a single cell, including selected text.
              if(!/["\t\r\n,]/.test(text)) return;
              event.preventDefault();model.send({type:'paste',row:r,column:c,text});
            });
            input.addEventListener('keydown',event=>{
              if(event.key==='Enter') {
                const next=box.querySelector(`input[data-row="${r+(event.shiftKey ? -1 : 1)}"][data-col="${c}"]`);
                if(next) {event.preventDefault();next.focus();next.select();}
              }
            });
            if(r===0) {
              const heading=document.createElement('div'),remove=document.createElement('button');
              heading.className='tw-variable-heading';remove.type='button';remove.className='tw-variable-delete';
              remove.textContent='×';remove.title='Delete this variable';
              remove.setAttribute('aria-label','Delete variable '+(column.name || 'column '+(c+1)));
              remove.addEventListener('click',()=>model.send({type:'delete',id:column.id}));
              heading.append(input,remove);cell.append(heading);
            } else {cell.append(input);}
            tr.append(cell);
          });
        });
        box.replaceChildren(table);
        if(!columns.length) {const empty=document.createElement('p');empty.textContent='Add a variable to create the first column.';box.append(empty);}
        if(focus) {
          const input=box.querySelector(`input[data-row="${focus.r}"][data-col="${focus.c}"]`);
          if(input) {input.focus({preventScroll:true});input.setSelectionRange(focus.start,focus.end);}
        }
        box.scrollLeft=left;box.scrollTop=top;
        copy.disabled=!columns.length;
      }
      copy.addEventListener('click',async()=>{
        const columns=model.get('columns'),groups=model.get('groups');
        const quote=value=>/["\t\r\n]/.test(value) ? '"'+value.replaceAll('"','""')+'"' : value;
        const rows=[columns.map(c=>c.name),columns.map(c=>c.unit),...groups.map(g=>columns.map(c=>c.values[g] ?? ''))];
        try {
          await navigator.clipboard.writeText(rows.map(row=>row.map(quote).join('\t')).join('\n'));
          note.textContent='Copied names, units and visible values. Group labels are not included.';
        } catch {note.textContent='Clipboard access was unavailable. You can still paste from Excel into a cell.';}
      });
      model.on('change:columns',scheduleRender);model.on('change:groups',scheduleRender);model.on('change:labels',scheduleRender);model.on('change:notice',status);
      render();status();
      return ()=>{cancelAnimationFrame(renderFrame);model.off('change:columns',scheduleRender);model.off('change:groups',scheduleRender);model.off('change:labels',scheduleRender);model.off('change:notice',status);};
    }};
    """

    def __init__(self, on_delete=None, **kwargs):
        self._on_delete = on_delete
        super().__init__(**kwargs)
        self.on_msg(self._message)

    def _message(self, _, message, buffers):
        if message.get('type') == 'delete':
            if self._on_delete:
                self._on_delete(message.get('id'))
            return
        if message.get('type') != 'paste':
            return
        try:
            self.columns = paste_cells(self.columns, self.groups, message.get('row'),
                                       message.get('column'), message.get('text'))
            self.notice = 'Pasted into the draft. Click Save all variables to apply.'
        except ValueError as error:
            self.notice = str(error)
