"""Copy saved v17 graph definitions once; never overwrite an existing v18 project."""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
from workbench_project_v18 import validate_project


def migrate(root):
    root = Path(root)
    target = root / 'tensile_workbench_v18.project.json'
    if target.exists():
        validate_project(json.loads(target.read_text(encoding='utf-8')))
        return target
    source = root / 'tensile_workbench_v17.project.json'
    if not source.is_file():
        raise FileNotFoundError('Place the v18 patch in your existing v17 workbench folder. '
                                'The saved tensile_workbench_v17.project.json is required for first launch.')
    raw = source.read_bytes()
    project = deepcopy(json.loads(raw))
    validate_project(project)
    if project.get('output_directory') == 'output/interactive_v17':
        project['output_directory'] = 'output/interactive_v18'
    project['migration'] = {'source': source.name, 'source_revision': project.get('revision'),
                            'source_sha256': hashlib.sha256(raw).hexdigest(),
                            'created': datetime.now().astimezone().isoformat()}
    validate_project(project)
    if source.read_bytes() != raw:
        raise RuntimeError('v17 definitions changed during migration. Close v17 and retry.')
    with target.open('x', encoding='utf-8') as stream:
        json.dump(project, stream, indent=2, ensure_ascii=False, allow_nan=False)
    return target


if __name__ == '__main__':
    print('Saved definitions ready:', migrate(Path(__file__).resolve().parent).name)
