"""Prepare stable-name graph definitions without overwriting an existing project."""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
from workbench_project import validate_project


def migrate(root):
    root = Path(root)
    target = root / 'tensile_workbench.project.json'
    if target.exists():
        validate_project(json.loads(target.read_text(encoding='utf-8')))
        return target
    candidates = [root / name for name in ('tensile_workbench_v18.project.json',
                                           'tensile_workbench_v17.project.json',
                                           'tensile_workbench_defaults.json')]
    source = next((path for path in candidates if path.is_file()), None)
    if source is None:
        raise FileNotFoundError('The saved graph project and workbench defaults are missing. Restore them from Git or a backup.')
    raw = source.read_bytes()
    project = deepcopy(json.loads(raw))
    validate_project(project)
    if project.get('output_directory') in ('output/interactive_v17', 'output/interactive_v18'):
        project['output_directory'] = './output'
    project['migration'] = {'source': source.name, 'source_revision': project.get('revision'),
                            'source_sha256': hashlib.sha256(raw).hexdigest(),
                            'created': datetime.now().astimezone().isoformat()}
    validate_project(project)
    if source.read_bytes() != raw:
        raise RuntimeError('Source definitions changed during migration. Close the other workbench session and retry.')
    with target.open('x', encoding='utf-8') as stream:
        json.dump(project, stream, indent=2, ensure_ascii=False, allow_nan=False)
    return target


if __name__ == '__main__':
    print('Saved definitions ready:', migrate(Path(__file__).resolve().parent).name)
