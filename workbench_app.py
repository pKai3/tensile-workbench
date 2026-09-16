"""Voilà entry: a ready-to-use web app, not a user-editable notebook."""
from pathlib import Path
import os
import sys

from IPython.display import display
import ipywidgets as w
import matplotlib

matplotlib.use('Agg')
root = Path(os.environ.get('TENSILE_WORKBENCH_DIR', Path.cwd())).expanduser().resolve()
if str(root) not in sys.path:
    sys.path.insert(0, str(root))

from migrate_tensile_project import migrate
from tensile_startup import launch

display(w.HTML('''<style>
body { background: #f5f7fa; }
.jp-VoilaCell { padding: 0 !important; }
.jp-OutputArea-output { width: 100%; }
.tw-webapp { max-width: 1600px; margin: 0 auto; padding: 16px 24px 32px; box-sizing: border-box; }
.tw-webapp .widget-label { color: #26374a; }
.tw-webapp h1 { font-size: 28px; margin-bottom: 4px; color: #203650; }
.tw-webapp h2 { font-size: 21px; }
.tw-webapp p { line-height: 1.45; }
.tw-webapp .jupyter-widgets { font-size: 14px; }
.tw-webapp .widget-hbox { gap: 8px; }
.tw-webapp .widget-accordion { margin: 8px 0; }
.tw-webapp .widget-accordion .p-Accordion-header,
.tw-webapp .widget-accordion .lm-AccordionPanel-title { padding: 8px 12px; }
@media(max-width: 700px) { .tw-webapp { padding: 8px; } }
</style>'''))
migrate(root)
workbench = launch(root)
page = w.VBox([
    w.HTML('<h1>Tensile Workbench</h1><p>Select your folders, choose a graph, and analyse your samples. '
           'No notebook commands are needed. Keep the launcher window open while you work.</p>'),
    workbench.ui,
], layout=w.Layout(width='100%'))
page.add_class('tw-webapp')
display(page)
