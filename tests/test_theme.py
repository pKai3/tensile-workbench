"""Browser appearance state, using the bundled script without a browser or kernel."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

from tensile_page_layout import ContentWidth


ROOT = Path(__file__).resolve().parents[1]
THEME_SCRIPT = (ROOT / 'web/static/tensile-theme.js').read_text(encoding='utf-8')
THEME_CSS = (ROOT / 'web/static/tensile-theme.css').read_text(encoding='utf-8')
NODE = shutil.which('node')

# Only the DOM/storage interfaces used by a page-head bootstrap are available.
# This executes the actual bundled script; no third-party browser dependencies.
HARNESS = r"""
const assert = require('node:assert/strict');
const vm = require('node:vm');
const key = 'tensile-workbench-theme';
function boot(options = {}) {
  const state = {
    readBlocked: options.readBlocked || false,
    writeBlocked: options.writeBlocked || false,
    writes: [], reads: 0,
  };
  const storage = new Map();
  if (options.saved !== undefined) storage.set(key, options.saved);
  const events = new Map();
  const document = {documentElement: {dataset: {}}};
  const window = {
    localStorage: {
      getItem(name) {
        state.reads++;
        if (state.readBlocked) throw new Error('Storage unavailable');
        return storage.has(name) ? storage.get(name) : null;
      },
      setItem(name, value) {
        if (state.writeBlocked) throw new Error('Storage unavailable');
        state.writes.push([name, value]);
        storage.set(name, value);
      },
    },
    addEventListener(name, listener) {
      if (!events.has(name)) events.set(name, []);
      events.get(name).push(listener);
    },
  };
  const context = vm.createContext({window, document});
  const run = () => vm.runInContext(source, context);
  run();
  return {
    window, document, state, storage, run, events,
    value: () => document.documentElement.dataset.twTheme,
    storageEvent: event => (events.get('storage') || []).forEach(fn => fn(event)),
  };
}
"""


class ThemeAssetsTests(unittest.TestCase):
    def test_notebook_controls_share_the_page_head_assets(self):
        self.assertIn(THEME_SCRIPT, ContentWidth._esm)
        self.assertIn(THEME_CSS, ContentWidth._css)
        self.assertIn("'Colour theme'", ContentWidth._esm)
        self.assertIn("'Dark · TEM'", ContentWidth._esm)
        # Appearance must remain browser-local rather than writing analyses or
        # triggering expensive kernel calculations on each theme change.
        self.assertNotIn('model.', THEME_SCRIPT)
        self.assertNotIn('fetch(', THEME_SCRIPT)


@unittest.skipUnless(NODE, 'Node.js is required for browser-script regression checks')
class ThemeBehaviourTests(unittest.TestCase):
    def javascript(self, checks):
        script = 'const source = ' + json.dumps(THEME_SCRIPT) + ';\n' + HARNESS + '\n' + checks
        result = subprocess.run([NODE, '-e', script], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_default_is_light_without_creating_a_preference(self):
        self.javascript(r"""
          const app = boot();
          assert.equal(app.value(), 'light');
          assert.equal(app.state.reads, 1);
          assert.deepEqual(app.state.writes, []);
          const notices = [];
          app.window.TensileTheme.subscribe((value, saved) => notices.push([value, saved]));
          assert.deepEqual(notices, [['light', true]]);
        """)

    def test_saved_light_and_dark_are_restored_without_rewriting_storage(self):
        self.javascript(r"""
          for (const saved of ['light', 'dark']) {
            const app = boot({saved});
            assert.equal(app.value(), saved);
            assert.deepEqual(app.state.writes, []);
            const notices = [];
            app.window.TensileTheme.subscribe((value, persisted) => notices.push([value, persisted]));
            assert.deepEqual(notices, [[saved, true]]);
          }
        """)

    def test_invalid_saved_values_fall_back_to_light(self):
        self.javascript(r"""
          for (const saved of ['', 'Dark', 'system', '<script>', 'undefined']) {
            const app = boot({saved});
            assert.equal(app.value(), 'light');
            assert.equal(app.storage.get(key), saved);
            assert.deepEqual(app.state.writes, []);
          }
        """)

    def test_blocked_storage_still_allows_session_only_theme_changes(self):
        self.javascript(r"""
          const app = boot({readBlocked: true, writeBlocked: true});
          const notices = [];
          app.window.TensileTheme.subscribe((value, saved) => notices.push([value, saved]));
          assert.equal(app.value(), 'light');
          app.window.TensileTheme.set('dark');
          assert.equal(app.value(), 'dark');
          assert.deepEqual(notices, [['light', false], ['dark', false]]);
          assert.deepEqual(app.state.writes, []);
        """)

    def test_setter_persists_notifies_controls_and_unsubscribes(self):
        self.javascript(r"""
          const app = boot();
          const first = [], second = [];
          const unsubscribe = app.window.TensileTheme.subscribe((...value) => first.push(value));
          app.window.TensileTheme.subscribe((...value) => second.push(value));
          app.window.TensileTheme.set('dark');
          assert.equal(app.value(), 'dark');
          assert.equal(app.storage.get(key), 'dark');
          unsubscribe();
          app.window.TensileTheme.set('light');
          app.window.TensileTheme.set('invalid');
          assert.equal(app.value(), 'light');
          assert.deepEqual(first, [['light', true], ['dark', true]]);
          assert.deepEqual(second, [['light', true], ['dark', true], ['light', true]]);
          assert.deepEqual(app.state.writes, [[key, 'dark'], [key, 'light']]);
        """)

    def test_failed_write_is_reported_and_later_success_clears_session_only_status(self):
        self.javascript(r"""
          const app = boot({saved: 'dark', writeBlocked: true});
          const notices = [];
          app.window.TensileTheme.subscribe((...value) => notices.push(value));
          app.window.TensileTheme.set('light');
          assert.equal(app.value(), 'light');
          assert.equal(app.storage.get(key), 'dark');
          app.state.writeBlocked = false;
          app.window.TensileTheme.set('light');
          assert.equal(app.storage.get(key), 'light');
          assert.deepEqual(notices, [['dark', true], ['light', false], ['light', true]]);
        """)

    def test_cross_tab_changes_removal_and_clear_update_controls_without_writing_back(self):
        self.javascript(r"""
          const app = boot({saved: 'dark'});
          const notices = [];
          app.window.TensileTheme.subscribe((value, saved) => notices.push([value, saved]));
          app.storageEvent({key: 'another-setting', newValue: 'light'});
          assert.equal(app.value(), 'dark');
          assert.equal(notices.length, 1);
          app.storageEvent({key, newValue: 'light'});
          assert.equal(app.value(), 'light');
          app.storageEvent({key, newValue: 'dark'});
          app.storageEvent({key, newValue: null});
          assert.equal(app.value(), 'light');
          app.storageEvent({key, newValue: 'dark'});
          app.storageEvent({key: null, newValue: null});
          assert.equal(app.value(), 'light');
          app.storageEvent({key, newValue: 'dark'});
          app.storageEvent({key, newValue: 'invalid'});
          assert.equal(app.value(), 'light');
          assert.deepEqual(notices.map(item => item[0]),
            ['dark', 'light', 'dark', 'light', 'dark', 'light', 'dark', 'light']);
          assert.deepEqual(app.state.writes, []);
        """)

    def test_repeated_bootstrap_preserves_state_and_does_not_duplicate_listeners(self):
        self.javascript(r"""
          const app = boot();
          const api = app.window.TensileTheme;
          const notices = [];
          api.subscribe((value, saved) => notices.push([value, saved]));
          api.set('dark');
          app.run();
          assert.equal(app.window.TensileTheme, api);
          assert.equal(app.value(), 'dark');
          assert.equal(app.state.reads, 1);
          assert.equal(app.events.get('storage').length, 1);
          app.storageEvent({key, newValue: 'light'});
          assert.deepEqual(notices, [['light', true], ['dark', true], ['light', true]]);
        """)


if __name__ == '__main__':
    unittest.main()
