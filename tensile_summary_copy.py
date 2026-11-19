"""Spreadsheet-style selection and copying of the existing numeric Summary."""
import csv
import io

import anywidget
import numpy as np
import pandas as pd
import traitlets


def summary_copy_rows(summary):
    """Keep the Summary export's columns and full-precision numeric values."""
    if summary.empty:
        return [], []
    columns = [str(column) for column in summary.columns]
    rows = []
    for record in summary.itertuples(index=False, name=None):
        row = []
        for value in record:
            if pd.isna(value):
                row.append(None)
            elif isinstance(value, (int, np.integer)):
                row.append(int(value))
            elif isinstance(value, (float, np.floating)):
                row.append(float(value))
            else:
                row.append(str(value))
        rows.append(row)
    return columns, rows


def separated_text(columns, rows, delimiter):
    """Use normal CSV quoting; missing values stay blank, never zero."""
    output = io.StringIO(newline='')
    writer = csv.writer(output, delimiter=delimiter, lineterminator='\n')
    writer.writerow(columns)
    for row in rows:
        writer.writerow('' if value is None else value for value in row)
    return output.getvalue()


class SummaryCopyTable(anywidget.AnyWidget):
    columns = traitlets.List(traitlets.Unicode()).tag(sync=True)
    rows = traitlets.List(traitlets.List()).tag(sync=True)
    csv_text = traitlets.Unicode('').tag(sync=True)
    tsv_text = traitlets.Unicode('').tag(sync=True)

    _css = """
    .tw-summary-copy {width:100%;min-width:0;font:12px/1.45 Arial,sans-serif;color:var(--tw-text,inherit);}
    .tw-summary-copy .toolbar {display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:0 0 8px;}
    .tw-summary-copy .toolbar button {padding:6px 11px;border:1px solid var(--tw-control-border,#b6c1cd);
      border-radius:5px;background:var(--tw-control-bg,#fff);color:var(--tw-control-text,#24354a);cursor:pointer;}
    .tw-summary-copy .toolbar button:focus-visible {outline:2px solid var(--tw-accent,#1767a5);}
    .tw-summary-copy .toolbar small {color:var(--tw-muted,#526170);}
    .tw-summary-copy .grid {max-width:100%;max-height:55vh;overflow:auto;
      border:1px solid var(--tw-border,#cbd5e1);}
    .tw-summary-copy table {border-collapse:separate;border-spacing:0;width:max-content;min-width:100%;}
    .tw-summary-copy th,.tw-summary-copy td {padding:7px 9px;min-width:90px;max-width:190px;
      border-right:1px solid var(--tw-border,#dce3e9);border-bottom:1px solid var(--tw-border,#dce3e9);
      white-space:normal;overflow-wrap:anywhere;user-select:none;-webkit-user-select:none;cursor:cell;}
    .tw-summary-copy th {position:sticky;top:0;z-index:2;text-align:left;cursor:grab;touch-action:none;
      background:var(--tw-table-head-bg,#e8eef4);color:var(--tw-table-head-text,#152c3f);}
    .tw-summary-copy th:active {cursor:grabbing;}
    .tw-summary-copy th.dragging {opacity:.5;}
    .tw-summary-copy th.drop-before {box-shadow:inset 3px 0 var(--tw-accent,#1767a5);}
    .tw-summary-copy th.drop-after {box-shadow:inset -3px 0 var(--tw-accent,#1767a5);}
    .tw-summary-copy td {background:var(--tw-panel-bg,#fff);}
    .tw-summary-copy tbody tr:nth-child(even) td {background:var(--tw-table-stripe-bg,#f6f8fa);}
    .tw-summary-copy th:first-child,.tw-summary-copy td:first-child {position:sticky;left:0;z-index:1;min-width:145px;}
    .tw-summary-copy th:first-child {z-index:3;}
    .tw-summary-copy td.number {text-align:right;font-variant-numeric:tabular-nums;}
    .tw-summary-copy .selected {background:var(--tw-selected-bg,#dcecff)!important;
      box-shadow:inset 0 0 0 1px var(--tw-accent,#1767a5);}
    .tw-summary-copy th:focus-visible,.tw-summary-copy td:focus-visible {outline:2px solid var(--tw-accent,#1767a5);outline-offset:-2px;}
    .tw-summary-copy textarea {box-sizing:border-box;width:100%;min-height:100px;margin-top:8px;
      font:11px/1.4 monospace;}
    """

    _esm = """
    export default {render({model,el}) {
      const root=document.createElement('div'),toolbar=document.createElement('div');
      const grid=document.createElement('div'),notice=document.createElement('small');
      const fallback=document.createElement('textarea');
      root.className='tw-summary-copy';toolbar.className='toolbar';grid.className='grid';
      grid.tabIndex=0;grid.setAttribute('role','region');
      grid.setAttribute('aria-label','Selectable Summary table; drag headers to reorder columns or drag across cells to select a rectangle');
      notice.setAttribute('role','status');fallback.hidden=true;fallback.readOnly=true;
      const buttons={};
      for(const format of ['CSV','TSV']) {
        const button=document.createElement('button');button.type='button';
        button.textContent='Copy '+format;button.setAttribute('aria-label','Copy Summary as '+format);
        buttons[format]=button;toolbar.append(button);
      }
      const clear=document.createElement('button');clear.type='button';clear.textContent='Clear selection';
      clear.hidden=true;toolbar.append(clear,notice);root.append(toolbar,grid,fallback);el.append(root);
      let anchor=null,tip=null,dragging=false,headerDrag=null,columnOrder=[];
      const visibleOrder=()=>columnOrder.filter(label=>model.get('columns').includes(label));
      const matrix=()=>{const columns=model.get('columns'),indices=visibleOrder().map(label=>columns.indexOf(label));
        return [indices.map(index=>columns[index]),...model.get('rows').map(row=>indices.map(index=>row[index]))];};
      const bounds=()=>anchor && tip ? {
        r0:Math.min(anchor.r,tip.r),r1:Math.max(anchor.r,tip.r),
        c0:Math.min(anchor.c,tip.c),c1:Math.max(anchor.c,tip.c)} : null;
      const cellAt=event=>event.target.closest?.('[data-r][data-c]');
      const point=cell=>({r:Number(cell.dataset.r),c:Number(cell.dataset.c)});
      function paint() {
        const area=bounds();
        grid.querySelectorAll('[data-r][data-c]').forEach(cell=>{
          const selected=!!area && Number(cell.dataset.r)>=area.r0 && Number(cell.dataset.r)<=area.r1 &&
            Number(cell.dataset.c)>=area.c0 && Number(cell.dataset.c)<=area.c1;
          cell.classList.toggle('selected',selected);cell.setAttribute('aria-selected',String(selected));
        });
        clear.hidden=!area;
        for(const format of ['CSV','TSV'])
          buttons[format].textContent=area ? 'Copy selection as '+format : 'Copy full '+format;
        notice.textContent=area ? `${area.r1-area.r0+1} × ${area.c1-area.c0+1} cells selected. Ctrl/Cmd+C copies TSV.` :
          `${model.get('rows').length} group rows. Drag headers to reorder columns; drag cells to select.`;
      }
      function selectedText(format) {
        const area=bounds();
        if(!area && visibleOrder().every((label,index)=>label===model.get('columns')[index]))
          return model.get(format==='CSV' ? 'csv_text' : 'tsv_text');
        const delimiter=format==='CSV' ? ',' : '\\t';
        const quote=value=>{const text=value==null ? '' : String(value);
          return text.includes(delimiter) || /["\\r\\n]/.test(text) ? '"'+text.replaceAll('"','""')+'"' : text;};
        const rows=matrix();
        return rows.slice(area ? area.r0 : 0,area ? area.r1+1 : rows.length)
          .map(row=>row.slice(area ? area.c0 : 0,area ? area.c1+1 : row.length)
            .map(quote).join(delimiter)).join('\\n')+'\\n';
      }
      async function copy(format) {
        const value=selectedText(format);
        try {await navigator.clipboard.writeText(value);
          notice.textContent='Copied '+(bounds() ? 'selected cells' : 'full Summary')+' as '+format+'.';fallback.hidden=true;
        } catch {fallback.hidden=false;fallback.value=value;fallback.focus();fallback.select();
          notice.textContent='Clipboard unavailable; press Ctrl/Cmd+C to copy the selected '+format+' text.';}
      }
      for(const format of ['CSV','TSV'])buttons[format].addEventListener('click',()=>copy(format));
      clear.addEventListener('click',()=>{anchor=tip=null;paint();grid.focus();});
      const headerAt=event=>event.target.closest?.('th[data-c]');
      const down=event=>{if(event.button!==0)return;
        const header=headerAt(event);
        if(header && grid.contains(header)){
          headerDrag={from:Number(header.dataset.c),startX:event.clientX,startY:event.clientY,
            pointerId:event.pointerId,extend:event.shiftKey && !!anchor,moving:false,target:null,after:false};
          grid.setPointerCapture(event.pointerId);event.preventDefault();
          header.focus({preventScroll:true});return;
        }
        const cell=cellAt(event);if(!cell || !grid.contains(cell))return;
        if(event.shiftKey && anchor)tip=point(cell);else anchor=tip=point(cell);
        dragging=true;event.preventDefault();cell.focus({preventScroll:true});paint();};
      const over=event=>{if(!dragging)return;const cell=cellAt(event);
        if(cell && grid.contains(cell)){tip=point(cell);paint();}};
      const up=()=>{dragging=false;};
      grid.addEventListener('pointerdown',down);grid.addEventListener('pointerover',over);
      document.addEventListener('pointerup',up);
      const clearDrag=()=>{
        grid.querySelectorAll('.dragging,.drop-before,.drop-after').forEach(cell=>
          cell.classList.remove('dragging','drop-before','drop-after'));};
      grid.addEventListener('pointermove',event=>{const state=headerDrag;
        if(!state || state.pointerId!==event.pointerId)return;
        if(!state.moving && Math.hypot(event.clientX-state.startX,event.clientY-state.startY)<5)return;
        state.moving=true;
        grid.querySelector(`th[data-c="${state.from}"]`)?.classList.add('dragging');
        const gridRect=grid.getBoundingClientRect();
        if(event.clientX<gridRect.left+28)grid.scrollLeft-=15;
        else if(event.clientX>gridRect.right-28)grid.scrollLeft+=15;
        const header=document.elementFromPoint(event.clientX,event.clientY)?.closest?.('th[data-c]');
        grid.querySelectorAll('.drop-before,.drop-after').forEach(cell=>cell.classList.remove('drop-before','drop-after'));
        state.target=header && grid.contains(header) ? Number(header.dataset.c) : null;
        if(state.target===null)return;
        state.after=event.clientX>header.getBoundingClientRect().left+header.getBoundingClientRect().width/2;
        header.classList.add(state.after ? 'drop-after' : 'drop-before');
      });
      grid.addEventListener('pointerup',event=>{const state=headerDrag;
        if(!state || state.pointerId!==event.pointerId)return;
        headerDrag=null;grid.releasePointerCapture(event.pointerId);clearDrag();
        const {from,target,after}=state;
        if(!state.moving){if(state.extend)tip={r:0,c:from};else anchor=tip={r:0,c:from};
          paint();return;}
        if(target===null)return;
        let destination=target+(after ? 1 : 0);
        const visible=visibleOrder(),moved=visible[from],neighbor=visible[target];
        if(from<destination)destination--;
        if(destination===from)return;
        columnOrder.splice(columnOrder.indexOf(moved),1);
        const neighborIndex=columnOrder.indexOf(neighbor);
        columnOrder.splice(neighborIndex+(after ? 1 : 0),0,moved);
        renderTable();
        notice.textContent=`Moved ${moved} to column ${destination+1}. Drag headers to reorder columns.`;
        grid.querySelector(`th[data-c="${destination}"]`)?.focus({preventScroll:true});
      });
      grid.addEventListener('pointercancel',event=>{if(headerDrag?.pointerId!==event.pointerId)return;
        headerDrag=null;clearDrag();});
      grid.addEventListener('copy',event=>{if(!bounds())return;
        event.clipboardData.setData('text/plain',selectedText('TSV'));event.preventDefault();
        notice.textContent='Copied selected cells as TSV.';});
      grid.addEventListener('keydown',event=>{
        if(event.key==='Escape'){anchor=tip=null;paint();return;}
        if((event.ctrlKey || event.metaKey) && event.key.toLowerCase()==='a'){
          event.preventDefault();anchor={r:0,c:0};
          tip={r:model.get('rows').length,c:model.get('columns').length-1};paint();return;}
        const movement={ArrowUp:[-1,0],ArrowDown:[1,0],ArrowLeft:[0,-1],ArrowRight:[0,1]}[event.key];
        if(!movement)return;event.preventDefault();
        const current=tip || {r:0,c:0};
        const next={r:Math.max(0,Math.min(model.get('rows').length,current.r+movement[0])),
          c:Math.max(0,Math.min(model.get('columns').length-1,current.c+movement[1]))};
        if(!event.shiftKey || !anchor)anchor=next;tip=next;paint();
        grid.querySelector(`[data-r="${next.r}"][data-c="${next.c}"]`)?.focus({preventScroll:true});
      });
      function syncOrder() {
        const columns=model.get('columns');
        for(let index=0;index<columns.length;index++){
          const label=columns[index];if(columnOrder.includes(label))continue;
          const parts=label.split(' · '),signature=parts.length>2 ? parts[0]+' · '+parts.at(-1) : null;
          const sibling=signature && columnOrder.find(existing=>{
            const pieces=existing.split(' · ');
            return pieces.length>2 && pieces[0]+' · '+pieces.at(-1)===signature;});
          const prior=columns.slice(0,index).reverse().find(existing=>columnOrder.includes(existing));
          const next=columns.slice(index+1).find(existing=>columnOrder.includes(existing));
          const position=sibling ? columnOrder.indexOf(sibling)+1 :
            prior ? columnOrder.indexOf(prior)+1 : next ? columnOrder.indexOf(next) : columnOrder.length;
          columnOrder.splice(position,0,label);
        }
      }
      function renderTable() {
        syncOrder();
        const left=grid.scrollLeft,top=grid.scrollTop;
        const table=document.createElement('table'),head=table.createTHead().insertRow(),body=table.createTBody();
        const columns=model.get('columns'),order=visibleOrder(),indices=order.map(label=>columns.indexOf(label));
        order.forEach((label,c)=>{const cell=document.createElement('th');
          cell.scope='col';cell.textContent=label;cell.dataset.r=0;cell.dataset.c=c;cell.tabIndex=-1;
          cell.title='Drag to reorder column';head.append(cell);});
        model.get('rows').forEach((row,r)=>{const tr=body.insertRow();
          indices.forEach((index,c)=>{const value=row[index],cell=tr.insertCell(),label=order[c];
            cell.dataset.r=r+1;cell.dataset.c=c;cell.tabIndex=-1;
            if(typeof value==='number') {cell.className='number';
              cell.textContent=label==='Included n' || label==='Available n' || label.endsWith(' · n') ?
                String(value) : value.toFixed(2);cell.title=String(value);
            } else cell.textContent=value ?? '';
          });
        });
        anchor=tip=null;grid.replaceChildren(table);grid.scrollLeft=left;grid.scrollTop=top;
        for(const format of ['CSV','TSV'])buttons[format].disabled=!model.get('rows').length;
        paint();
      }
      model.on('change:columns',renderTable);model.on('change:rows',renderTable);
      renderTable();
      return ()=>{model.off('change:columns',renderTable);model.off('change:rows',renderTable);
        document.removeEventListener('pointerup',up);};
    }};
    """

    def set_data(self, columns, rows):
        with self.hold_sync():
            self.columns = columns
            self.rows = rows
            self.csv_text = separated_text(columns, rows, ',')
            self.tsv_text = separated_text(columns, rows, '\t')
