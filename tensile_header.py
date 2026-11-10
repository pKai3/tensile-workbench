"""Running version and live connection state for the browser header."""
from pathlib import Path
import anywidget
import traitlets


class ConnectionStatus(anywidget.AnyWidget):
    version = traitlets.Unicode('Development').tag(sync=True)
    _esm = """
    export default {render({el,model}) {
      el.classList.add('tw-header-status');
      const version=document.createElement('span'),connection=document.createElement('span');
      version.className='tw-version';version.textContent=model.get('version');
      version.title='Running analysis engine version. Restart Workbench after updating.';
      connection.className='tw-connection';connection.setAttribute('role','status');
      connection.setAttribute('aria-live','polite');el.append(version,connection);
      const kernel=model.widget_manager?.kernel;
      const refresh=()=>{
        let state='unknown',text='Status unavailable';
        if(kernel){
          if(kernel.isDisposed || kernel.status==='dead'){state='disconnected';text='Disconnected';}
          else if(kernel.connectionStatus==='connected'){
            state='connected';text='Local Python · connected';
          }else if(kernel.connectionStatus==='connecting'){state='connecting';text='Reconnecting…';}
          else {state='disconnected';text='Disconnected';}
        }
        connection.dataset.state=state;connection.textContent=text;
        connection.title=state==='connected'
          ? (kernel.status==='busy' ? 'Connected; the analysis engine is working.' : 'Connected to the local analysis engine.')
          : 'Keep the launcher running. If the connection does not recover, restart Workbench and reload this page.';
      };
      const signals=[kernel?.connectionStatusChanged,kernel?.statusChanged,kernel?.disposed].filter(Boolean);
      for(const signal of signals)signal.connect(refresh);
      refresh();
      return ()=>{for(const signal of signals)signal.disconnect(refresh);};
    }};
    """


def app_header(w, root):
    version_path = Path(root) / 'VERSION'
    version = 'v' + version_path.read_text(encoding='utf-8').strip() if version_path.is_file() else 'Development'
    status = ConnectionStatus(version=version, layout=w.Layout(width='auto', flex='0 0 auto'))
    title = w.HTML('<span class="tw-eyebrow">LOCAL ANALYSIS</span><h1>Tensile Workbench</h1>')
    header = w.HBox([title, status], layout=w.Layout(width='100%', justify_content='space-between',
        align_items='center', flex_flow='row wrap', grid_gap='12px', margin='0 0 16px'))
    header.add_class('tw-app-header')
    return header
