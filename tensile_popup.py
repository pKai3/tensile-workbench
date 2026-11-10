"""Small shared popup shell for workspace settings."""
import anywidget
from html import escape


class PopupEvents(anywidget.AnyWidget):
    _esm = """
    export default {render({el,model}) {
      const root=()=>el.closest('.tw-popup-host');
      const overlay=()=>root()?.querySelector('.tw-settings-overlay');
      let wasOpen=false,previousFocus,shell,home,backdropPress=false,locked=[];
      const isOpen=()=>overlay() && getComputedStyle(overlay()).display!=='none';
      const close=()=>model.send({action:'close'});
      // A tab can change height between pointer-down and click. Only an
      // intentional click that started on the backdrop dismisses the dialog.
      const down=event=>{backdropPress=event.target===overlay();};
      const click=event=>{if(backdropPress && event.target===overlay())close();backdropPress=false;};
      const unlock=()=>{for(const [node,value,priority] of locked){
        if(value)node.style.setProperty('overflow',value,priority);else node.style.removeProperty('overflow');
      }locked=[];};
      const dismiss=event=>{event.preventDefault();close();};
      const key=event=>{
        if(!isOpen())return;
        if(event.key==='Escape'){event.preventDefault();event.stopPropagation();close();return;}
        if(event.key!=='Tab')return;
        const items=[...overlay().querySelectorAll('button,input,select,textarea,[tabindex="0"],summary')]
          .filter(node=>!node.disabled && node.getClientRects().length);
        const first=items[0],last=items.at(-1),outside=!overlay().contains(document.activeElement);
        if(event.shiftKey && (document.activeElement===first || outside)){event.preventDefault();last?.focus();}
        else if(!event.shiftKey && (document.activeElement===last || outside)){event.preventDefault();first?.focus();}
      };
      const sync=()=>{
        const open=isOpen();
        if(open){const panel=overlay().querySelector('.tw-settings-dialog');
          if(!panel)return;
          // The browser's top layer is viewport-relative even inside notebook
          // containers with transforms or CSS containment. Keep the original
          // ancestry so widget themes and delegated help still work.
          if(!shell){
            shell=document.createElement('dialog');shell.className='tw-modal-shell';
            home=overlay().parentElement;home.append(shell);shell.append(overlay());
            shell.addEventListener('cancel',dismiss);
          }
          shell.setAttribute('aria-modal','true');
          shell.setAttribute('aria-label',panel.querySelector('h3')?.textContent || 'Settings');
          if(!wasOpen){
            previousFocus=document.activeElement;
            // Voilà can scroll an inner container rather than body.
            for(let node=root();node;node=node.parentElement){
              locked.push([node,node.style.getPropertyValue('overflow'),node.style.getPropertyPriority('overflow')]);
              node.style.setProperty('overflow','hidden','important');
            }
            shell.showModal();panel.querySelector('button')?.focus({preventScroll:true});
          }}
        else if(wasOpen){shell.close();unlock();previousFocus?.focus({preventScroll:true});}
        wasOpen=open;
      };
      const observer=new MutationObserver(sync);
      observer.observe(document.body,{subtree:true,childList:true,attributes:true,attributeFilter:['style']});
      document.addEventListener('pointerdown',down,true);document.addEventListener('click',click);document.addEventListener('keydown',key);
      sync();
      return ()=>{observer.disconnect();unlock();
        if(shell){shell.close();shell.removeEventListener('cancel',dismiss);if(home?.isConnected)home.append(...shell.children);shell.remove();}
        document.removeEventListener('pointerdown',down,true);document.removeEventListener('click',click);document.removeEventListener('keydown',key);};
    }};
    """


class SettingsPopup:
    def __init__(self, w, on_close=None, width='1100px'):
        self.on_close = on_close
        self.title = w.HTML()
        self.done = w.Button(description='Done', icon='check', tooltip='Close this window.',
                             layout=w.Layout(width='auto'))
        self.done.on_click(lambda _: self.close())
        self.body = w.VBox(layout=w.Layout(width='100%', min_width='0'))
        dialog = w.VBox([w.HBox([self.title, self.done], layout=w.Layout(
            justify_content='space-between', align_items='center', flex_flow='row wrap')), self.body],
            layout=w.Layout(width=f'min({width}, 94vw)', max_height='88vh', overflow='auto', padding='20px'))
        dialog.add_class('tw-settings-dialog')
        self.overlay = w.Box([dialog], layout=w.Layout(display='none'))
        self.overlay.add_class('tw-settings-overlay')
        self.events = PopupEvents(layout=w.Layout(display='none'))
        self.events.on_msg(lambda _, content, buffers: self.close() if content.get('action') == 'close' else None)
        self.ui = w.VBox([self.events, self.overlay])
        self.ui.add_class('tw-popup-host')

    def open(self, title, children):
        self.title.value = '<h3 style="margin:0">' + escape(title) + '</h3>'
        self.body.children = tuple(children)
        self.overlay.layout.display = 'flex'

    def close(self):
        self.overlay.layout.display = 'none'
        self.body.children = ()
        if self.on_close:
            self.on_close()
