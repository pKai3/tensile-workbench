"""Exercise the browser probes with synthetic DOM/clock events, without a server."""
import shutil
import subprocess
import unittest
from tensile_plotly import visibility_probe, width_probe


@unittest.skipUnless(shutil.which('node'), 'Node needed for browser-probe checks')
class PlotLoadingTests(unittest.TestCase):
    def run_js(self, probe, setup, checks):
        self.addCleanup(probe.close)
        script = "import assert from 'node:assert/strict';\n" + setup + '\n' + probe._esm.replace('export default', 'const widget =') + '\n' + checks
        result = subprocess.run(['node', '--input-type=module'], input=script, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_theme_timeout_reveals_plot_and_resets_on_next_theme_change(self):
        self.run_js(width_probe(lambda _: None), """
          const timers=new Map(), mutations=[]; let seq=0;
          globalThis.setTimeout=(fn, delay)=>{assert.equal(delay,5000); timers.set(++seq,fn); return seq;};
          globalThis.clearTimeout=id=>timers.delete(id);
          globalThis.requestAnimationFrame=()=>1; globalThis.cancelAnimationFrame=()=>{};
          globalThis.ResizeObserver=class {observe(){} disconnect(){}};
          globalThis.MutationObserver=class {constructor(fn){mutations.push(fn);} observe(){} disconnect(){}};
          globalThis.document={documentElement:{dataset:{twTheme:'dark'}}};
          const classes=new Set(['tw-themed-plot']); let background='rgb(255, 255, 255)';
          globalThis.getComputedStyle=()=>({backgroundColor:background});
          const plot={matches:()=>false,querySelector:()=>({}),classList:{add:c=>classes.add(c), remove:(...cs)=>cs.forEach(c=>classes.delete(c)), contains:c=>classes.has(c)}};
          const el={style:{},isConnected:true,closest:()=>({querySelectorAll:()=>[plot]})};
          const values={theme:'light'};
          const model={get:k=>values[k],set:(k,v)=>values[k]=v,save_changes:()=>{}};
        """, """
          const dispose=widget.render({model,el});
          assert.equal(values.theme,'dark');
          assert.equal(classes.has('tw-theme-fallback'),false);
          [...timers.values()][0](); // Theme response never arrives.
          assert.equal(classes.has('tw-theme-fallback'),true);
          background='rgb(18, 28, 40)'; // A late response remains usable.
          document.documentElement.dataset.twTheme='light'; mutations[0]();
          assert.equal(classes.has('tw-theme-fallback'),false);
          assert.equal(values.theme,'light');
          background='rgb(255, 255, 255)'; [...timers.values()][0]();
          assert.equal(classes.has('tw-theme-light'),true);
          assert.equal(classes.has('tw-theme-fallback'),false);
          dispose(); assert.equal(timers.size,0);
        """)

    def test_visibility_observes_whole_card_after_attachment_and_prefetches(self):
        self.run_js(visibility_probe(lambda: None), """
          let pending, observed, options, callback, saves=0, disconnected=false;
          globalThis.requestAnimationFrame=fn=>{pending=fn;return 1;};
          globalThis.cancelAnimationFrame=()=>{pending=null;};
          globalThis.IntersectionObserver=class {
            constructor(fn,opts){callback=fn;options=opts;}
            observe(target){observed=target;} disconnect(){disconnected=true;}
          };
          const listeners={}; let top=3000;
          globalThis.window={innerHeight:800,addEventListener:(name,fn)=>listeners[name]=fn,
                             removeEventListener:name=>delete listeners[name]};
          const card={getBoundingClientRect:()=>({top,bottom:top+600,width:800,height:600})};
          const el={style:{},isConnected:false,closest:()=>el.isConnected?card:null};
          const values={visible:false};
          const model={get:k=>values[k],set:(k,v)=>values[k]=v,save_changes:()=>saves++};
        """, """
          const dispose=widget.render({model,el});
          assert.equal(observed,undefined);
          el.isConnected=true; pending();
          assert.equal(observed,card);
          assert.equal(options.rootMargin,'1000px 0px');
          callback([{isIntersecting:false}]); assert.equal(saves,0);
          // Nested clipping can suppress intersection until too late; the
          // viewport prefetch still fires before the card is visible.
          top=900; listeners.scroll(); pending();
          callback([{isIntersecting:true}]);
          assert.equal(values.visible,true); assert.equal(saves,1); assert.equal(disconnected,true);
          assert.equal(listeners.scroll,undefined);
          dispose(); assert.equal(pending,null);
        """)
