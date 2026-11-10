"""Compact help shown on hover/focus without changing the page layout."""
from html import escape
import anywidget


def help_html(label, body):
    """Body is trusted application markup; escape user values before passing it."""
    return ('<div class="tw-help" tabindex="0" role="button" aria-label="Help: '
            + escape(label, quote=True) + '">ⓘ ' + escape(label)
            + '<div class="tw-help-content" hidden>' + body + '</div></div>')


class HelpTooltips(anywidget.AnyWidget):
    """One delegated help bubble, including dynamically created controls."""
    _esm = """
    export default {render({el}) {
      const popup=document.createElement('div');
      popup.className='tw-help-popup';popup.id='tw-help-'+crypto.randomUUID();
      popup.setAttribute('role','tooltip');popup.hidden=true;document.body.append(popup);
      let active=null, closing;
      const hide=()=>{clearTimeout(closing);active?.removeAttribute('aria-describedby');active=null;popup.hidden=true;};
      const position=()=>{
        if(!active?.isConnected){hide();return;}
        const rect=active.getBoundingClientRect(), margin=12;
        popup.style.left=Math.max(margin,Math.min(rect.left,innerWidth-popup.offsetWidth-margin))+'px';
        const below=rect.bottom+6;
        popup.style.top=Math.max(margin,below+popup.offsetHeight<=innerHeight-margin
          ? below : rect.top-popup.offsetHeight-6)+'px';
      };
      const show=target=>{
        if(!target || !el.closest('.tw-workbench')?.contains(target))return;
        clearTimeout(closing);
        if(active!==target){active?.removeAttribute('aria-describedby');active=target;
          popup.innerHTML=target.querySelector('.tw-help-content')?.innerHTML || '';
          target.setAttribute('aria-describedby',popup.id);}
        popup.hidden=false;position();
      };
      const enter=event=>{
        if(popup.contains(event.target)){clearTimeout(closing);return;}
        show(event.target.closest?.('.tw-help'));
      };
      const leave=event=>{
        if(!active)return;
        if(active.contains(event.relatedTarget) || popup.contains(event.relatedTarget))return;
        if(active.contains(event.target) || popup.contains(event.target))closing=setTimeout(hide,120);
      };
      const focus=event=>show(event.target.closest?.('.tw-help'));
      const blur=event=>{if(active?.contains(event.target) && !popup.contains(event.relatedTarget))hide();};
      const click=event=>{const target=event.target.closest?.('.tw-help');if(target)show(target);else if(!popup.contains(event.target))hide();};
      const key=event=>{
        if(event.key==='Escape' && active){hide();event.stopPropagation();}
        else if((event.key==='Enter' || event.key===' ') && event.target.closest?.('.tw-help')){
          event.preventDefault();show(event.target.closest('.tw-help'));}
      };
      const scroll=event=>{if(active && !popup.contains(event.target))hide();};
      const events={mouseover:enter,mouseout:leave,focusin:focus,focusout:blur,click,keydown:key};
      for(const [name,handler] of Object.entries(events))document.addEventListener(name,handler);
      document.addEventListener('scroll',scroll,true);window.addEventListener('resize',hide);
      return ()=>{hide();popup.remove();for(const [name,handler] of Object.entries(events))document.removeEventListener(name,handler);
        document.removeEventListener('scroll',scroll,true);window.removeEventListener('resize',hide);};
    }};
    """
