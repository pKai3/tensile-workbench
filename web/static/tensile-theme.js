/* Shared by the early Voilà head and the notebook's display controls.
   Browser appearance only: no kernel messages or project-file writes. */
(() => {
  if (window.TensileTheme) return;
  const key = 'tensile-workbench-theme';
  const valid = value => value === 'dark' || value === 'light';
  let current = 'light', saved = true;
  try {
    const value = window.localStorage.getItem(key);
    if (valid(value)) current = value;
  } catch { saved = false; }
  const listeners = new Set();
  function apply(value) {
    current = valid(value) ? value : 'light';
    document.documentElement.dataset.twTheme = current;
    listeners.forEach(listener => listener(current, saved));
  }
  window.TensileTheme = {
    set(value) {
      if (!valid(value)) return;
      try { window.localStorage.setItem(key, value); saved = true; }
      catch { saved = false; }
      apply(value);
    },
    subscribe(listener) {
      listeners.add(listener);
      listener(current, saved);
      return () => listeners.delete(listener);
    },
  };
  // Keep other open workbench tabs and duplicate notebook controls in sync.
  window.addEventListener('storage', event => {
    if (event.key === key || event.key === null) {
      apply(valid(event.newValue) ? event.newValue : 'light');
    }
  });
  apply(current);
})();
