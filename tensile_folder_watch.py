"""Idle, visible-session folder watching. No threads or orphan server timers."""
import anywidget
import traitlets


class FolderPulse(anywidget.AnyWidget):
    enabled = traitlets.Bool(True).tag(sync=True)
    acknowledgement = traitlets.Int(0).tag(sync=True)
    _esm = """
    export default {render({model}) {
      let waiting=false;
      const ack=()=>{waiting=false;};
      model.on('change:acknowledgement',ack);
      const timer=setInterval(()=>{
        const active=document.activeElement;
        if(waiting || !model.get('enabled') || document.hidden || document.querySelector('dialog[open]')
          || active?.matches('input:not([type=checkbox]),textarea,[contenteditable=true]'))return;
        waiting=true;model.send({action:'poll'});
      },15000);
      return ()=>{clearInterval(timer);model.off('change:acknowledgement',ack);};
    }};
    """

    def __init__(self, callback, **kwargs):
        super().__init__(**kwargs)
        self.callback = callback
        self.on_msg(self._message)

    def _message(self, _, content, buffers):
        if content.get('action') != 'poll' or not self.enabled:
            return
        try:
            self.callback()
        finally:
            self.acknowledgement += 1
