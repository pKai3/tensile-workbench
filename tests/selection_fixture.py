"""Small synthetic curves only; never reads the installation's data directory."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import numpy as np

ROOT = Path(__file__).resolve().parents[1]


def make_fixture(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    if (ROOT / 'tensile_core.py').resolve() != (root / 'tensile_core.py').resolve():
        shutil.copy2(ROOT / 'tensile_core.py', root / 'tensile_core.py')
    project = json.loads((ROOT / 'tensile_workbench_defaults.json').read_text())
    template = deepcopy(project['graphs'][0])
    template['definition'] = {'name': 'Selection test'}
    project['graphs'] = []
    project['display_names'] = {}
    for index, name in enumerate(('Selection test', 'Comparison')):
        graph = deepcopy(template)
        graph.update(id=str(index), name=name)
        graph['definition']['name'] = name
        graph['settings'].update(groups=['Alloy A'], families=[], live_update=False,
                                 tensile_xlim=None, tensile_ylim=None, wh_xlim=None, wh_ylim=None)
        project['graphs'].append(graph)
    project['selected_graph'] = '0'
    for name in ('tensile_workbench_defaults.json', 'tensile_workbench.project.json'):
        (root / name).write_text(json.dumps(project))
    for specimen, scale in ((1, 1), (2, 1.1), (3, .9)):
        group = root / 'data' / 'Alloy A'
        group.mkdir(parents=True, exist_ok=True)
        x = np.linspace(0, 16 + specimen, 2001)
        y = np.where(x <= .5, 1200 * x, 600 + 180 * (1 - np.exp(-(x - .5) / 2)))
        y = (y - np.maximum(x - 7, 0) ** 1.5 * 7) * scale
        y[-1] = 200
        (group / f'coupon_{specimen}.csv').write_text(
            'Time,Tensile strain (Strain 1),Tensile stress\n(s),(%),(MPa)\n' +
            '\n'.join(f'{i},{strain},{stress}' for i, (strain, stress) in enumerate(zip(x, y))))
    return project
