"""Connection status follows the existing kernel channel, including busy work."""
import shutil
import subprocess
import unittest
from tensile_header import ConnectionStatus


@unittest.skipUnless(shutil.which('node'), 'Node needed for connection-status checks')
class HeaderTests(unittest.TestCase):
    def test_connection_changes_busy_state_and_cleanup(self):
        script = """
        import assert from 'node:assert/strict';
        const signals=()=>({listeners:new Set(),connect(fn){this.listeners.add(fn)},
          disconnect(fn){this.listeners.delete(fn)},emit(){for(const fn of this.listeners)fn()}});
        const kernel={connectionStatus:'connected',status:'idle',isDisposed:false,
          connectionStatusChanged:signals(),statusChanged:signals(),disposed:signals()};
        const nodes=[];
        globalThis.document={createElement:()=>({dataset:{},setAttribute(){}})};
        const el={classList:{add(){}},append(...items){nodes.push(...items)}};
        const model={get:()=> 'v1.0.8',widget_manager:{kernel}};
        """ + ConnectionStatus._esm.replace('export default', 'const widget =') + """
        const dispose=widget.render({el,model});
        const [version,status]=nodes;
        assert.equal(version.textContent,'v1.0.8');
        assert.equal(status.dataset.state,'connected');
        kernel.status='busy';kernel.statusChanged.emit();
        assert.equal(status.dataset.state,'connected');
        assert.match(status.title,/working/);
        kernel.connectionStatus='connecting';kernel.connectionStatusChanged.emit();
        assert.equal(status.textContent,'Reconnecting…');
        kernel.connectionStatus='disconnected';kernel.connectionStatusChanged.emit();
        assert.equal(status.textContent,'Disconnected');
        kernel.connectionStatus='connected';kernel.connectionStatusChanged.emit();
        assert.equal(status.dataset.state,'connected');
        kernel.isDisposed=true;kernel.disposed.emit();
        assert.equal(status.textContent,'Disconnected');
        dispose();
        for(const signal of [kernel.connectionStatusChanged,kernel.statusChanged,kernel.disposed])
          assert.equal(signal.listeners.size,0);
        """
        result = subprocess.run(['node', '--input-type=module'], input=script, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
