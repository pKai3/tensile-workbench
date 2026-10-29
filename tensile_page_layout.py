"""Stable browser-local page sizing; never depends on loaded tables or plots."""
import anywidget
from pathlib import Path


_STATIC = Path(__file__).resolve().parent / 'web' / 'static'


class ContentWidth(anywidget.AnyWidget):
    """Explicit preferred width, capped to the viewport and remembered locally."""
    _css = _STATIC.joinpath('tensile-theme.css').read_text(encoding='utf-8') + """
    .tw-page-width {display:flex;align-items:center;justify-content:flex-end;gap:8px;
      flex-wrap:wrap;color:var(--tw-muted,#536273);font:12px/1.4 Arial,sans-serif;padding:0 0 8px;}
    .tw-page-width label {display:flex;gap:8px;align-items:center;}
    .tw-page-width select {font:inherit;padding:4px 7px;border:1px solid var(--tw-control-border,#bdc8d3);
      border-radius:4px;background:var(--tw-control-bg,white);color:var(--tw-control-text,#26374a);}
    /* Outrank ipywidgets' four-class tab rules regardless of stylesheet load order.
       Scope only the outer navigation: inner specimen tabs retain their style. */
    .tw-page-tabs.jupyter-widgets.jupyter-widget-tab > .p-TabBar .p-TabBar-tab,
    .tw-page-tabs.jupyter-widgets.jupyter-widget-tab > .lm-TabBar .lm-TabBar-tab {flex:0 0 auto;min-width:max-content;
      width:auto;max-width:none;padding-left:16px;padding-right:16px;}
    .tw-page-tabs.jupyter-widgets.jupyter-widget-tab > .p-TabBar .p-TabBar-tabLabel,
    .tw-page-tabs.jupyter-widgets.jupyter-widget-tab > .lm-TabBar .lm-TabBar-tabLabel {
      flex:0 0 auto;white-space:nowrap;overflow:visible;text-overflow:clip;}
    .tw-page-tabs.jupyter-widgets.jupyter-widget-tab > .p-TabBar,
    .tw-page-tabs.jupyter-widgets.jupyter-widget-tab > .lm-TabBar {overflow-x:auto;min-height:34px;}
    """
    _esm = _STATIC.joinpath('tensile-theme.js').read_text(encoding='utf-8') + """
    export default {render({el}) {
      const key='tensile-workbench-page-width';
      const options=[[1100,'Compact · 1100 px'],[1400,'Medium · 1400 px'],
        [1600,'Wide · 1600 px'],[1900,'Extra wide · 1900 px'],[2200,'Large screen · 2200 px']];
      const box=document.createElement('div');box.className='tw-page-width';
      const themeLabel=document.createElement('label');
      const themeText=document.createElement('span');themeText.textContent='Theme';
      const theme=document.createElement('select');theme.setAttribute('aria-label','Colour theme');
      [['light','Light'],['dark','Dark · TEM']].forEach(([value,label])=>{
        const option=document.createElement('option');option.value=value;option.textContent=label;theme.append(option);
      });
      theme.title='Interface only. Plot previews and exports keep their publication colours.';
      themeLabel.append(themeText,theme);
      const storageNote=document.createElement('span');storageNote.setAttribute('role','status');
      const unsubscribe=window.TensileTheme.subscribe((value,saved)=>{
        theme.value=value;storageNote.textContent=saved ? '' : 'Theme saved for this session only';
      });
      theme.addEventListener('change',()=>window.TensileTheme.set(theme.value));
      const widthLabel=document.createElement('label');
      const text=document.createElement('span');text.textContent='Page width';
      const select=document.createElement('select');select.setAttribute('aria-label','Preferred page width');
      select.title='Stays fixed while data loads; automatically fits smaller browser windows.';
      options.forEach(([value,label])=>{
        const option=document.createElement('option');option.value=value;option.textContent=label;select.append(option);
      });
      let width=1600,page;
      try {const stored=Number(localStorage.getItem(key));if(options.some(([v])=>v===stored)) width=stored;} catch {}
      select.value=String(width);widthLabel.append(text,select);
      box.append(themeLabel,widthLabel,storageNote);el.append(box);
      function apply() {
        page=el.closest('.tw-webapp') || el.closest('.tw-workbench') || el.closest('.tw-launcher');
        if(page) page.style.setProperty('--tw-content-width',width+'px');
      }
      select.addEventListener('change',()=>{
        width=Number(select.value);
        try {localStorage.setItem(key,String(width));} catch {}
        apply();
      });
      // Only locate the host on mount/resize. Loaded content never sets width.
      const resize=new ResizeObserver(apply);resize.observe(el);apply();
      return ()=>{resize.disconnect();unsubscribe();};
    }};
    """
