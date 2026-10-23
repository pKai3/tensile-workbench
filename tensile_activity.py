"""Shared browser busy overlay with exception-safe, nested operation scopes."""
from contextlib import contextmanager, nullcontext
from functools import wraps
from pathlib import Path

import anywidget
import traitlets


def busy(message):
    """UI methods opt in; headless callers need no activity widget."""
    def decorate(function):
        @wraps(function)
        def wrapped(self, *args, **kwargs):
            indicator = getattr(self, 'activity', None)
            scope = indicator.operation(message) if indicator is not None and not getattr(self, '_paused', False) else nullcontext()
            with scope:
                return function(self, *args, **kwargs)
        return wrapped
    return decorate


class BusyOverlay(anywidget.AnyWidget):
    state = traitlets.Dict({'busy': False, 'message': ''}).tag(sync=True)
    # Trusted bundled artwork, also included by the initial Voilà page loader.
    # Inline it so the overlay works in notebook mode without a static endpoint.
    loader_svg = traitlets.Unicode((Path(__file__).resolve().parent / 'web/static/tensile-loading.svg')
                                  .read_text(encoding='utf-8')).tag(sync=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._operations = []

    @contextmanager
    def operation(self, message):
        self._operations.append(message)
        self.state = {'busy': True, 'message': message}
        try:
            yield
        finally:
            self._operations.pop()
            self.state = {'busy': bool(self._operations),
                          'message': self._operations[-1] if self._operations else ''}

    _css = """
    .tw-busy-overlay {position:fixed;inset:0;z-index:2147483000;display:flex;
      align-items:center;justify-content:center;background:rgba(241,245,249,.66);
      cursor:wait;touch-action:none;}
    .tw-busy-overlay[hidden] {display:none;}
    .tw-busy-card {display:flex;align-items:center;gap:16px;max-width:calc(100vw - 48px);box-sizing:border-box;
      background:white;color:#203650;padding:22px 28px;border:1px solid #cbd5e1;
      border-radius:10px;box-shadow:0 8px 30px #20365025;font:15px/1.5 Arial,sans-serif;outline:none;}
    .tw-busy-card small {display:block;color:#637385;font-size:12px;margin-top:4px;}
    .tw-busy-coupon {display:block;width:130px;flex:0 0 130px;line-height:0;}
    .tw-busy-coupon svg {display:block;width:100%;height:auto;}
    @media(max-width:480px) {.tw-busy-card {flex-direction:column;gap:4px;padding:16px;text-align:center;}
      .tw-busy-coupon {flex:0 0 auto;}}
    """
    _esm = """
    export default {render({model,el}) {
      Object.assign(el.style,{height:'0',minHeight:'0',margin:'0',padding:'0',overflow:'hidden',flex:'0 0 0px'});
      const overlay=document.createElement('div');overlay.className='tw-busy-overlay';overlay.hidden=true;
      const card=document.createElement('div');card.className='tw-busy-card';card.tabIndex=-1;
      card.setAttribute('role','status');card.setAttribute('aria-live','polite');card.setAttribute('aria-atomic','true');
      const spinner=document.createElement('span');spinner.className='tw-busy-coupon';spinner.setAttribute('aria-hidden','true');
      spinner.innerHTML=model.get('loader_svg');
      const copy=document.createElement('div'),label=document.createElement('div'),hint=document.createElement('small');
      hint.textContent='Please wait. Controls will be available when this finishes.';
      copy.append(label,hint);card.append(spinner,copy);overlay.append(card);document.body.append(overlay);
      let host,focus,priorInert=false,priorBusy=null,showTimer,active=false,frame;
      const stopScroll=event=>event.preventDefault();
      overlay.addEventListener('wheel',stopScroll,{passive:false});
      overlay.addEventListener('touchmove',stopScroll,{passive:false});
      const trap=event=>{if(active && event.key==='Tab') {event.preventDefault();if(!overlay.hidden) card.focus({preventScroll:true});}};
      document.addEventListener('keydown',trap,true);
      function release() {
        clearTimeout(showTimer);showTimer=undefined;overlay.hidden=true;
        if(host) {
          host.inert=priorInert;
          if(priorBusy===null) host.removeAttribute('aria-busy');else host.setAttribute('aria-busy',priorBusy);
        }
        if(active && focus?.isConnected && !focus.disabled) focus.focus({preventScroll:true});
        host=undefined;focus=undefined;active=false;
      }
      function sync() {
        const state=model.get('state');
        if(!state.busy) {release();return;}
        label.textContent=state.message || 'Working…';
        if(active) return;
        host=el.closest('.tw-webapp') || el.closest('.tw-launcher') || el.closest('.tw-workbench');
        if(!host) return;
        active=true;focus=document.activeElement;
        priorInert=host.inert;priorBusy=host.getAttribute('aria-busy');
        host.inert=true;host.setAttribute('aria-busy','true');
        // Block input immediately but avoid spinner flashes for tiny updates.
        showTimer=setTimeout(()=>{if(active) {overlay.hidden=false;card.focus({preventScroll:true});}},120);
      }
      model.on('change:state',sync);sync();frame=requestAnimationFrame(sync);
      return ()=>{
        cancelAnimationFrame(frame);model.off('change:state',sync);release();
        document.removeEventListener('keydown',trap,true);overlay.remove();
      };
    }};
    """
