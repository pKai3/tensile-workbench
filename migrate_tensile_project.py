"""Prepare stable-name graph definitions without overwriting an existing project."""
from copy import deepcopy
from datetime import datetime
import hashlib
import json
from pathlib import Path
from workbench_project import validate_project
from workbench_backups import BackupVault, atomic_bytes, settings_lock


def migrate(root):
    root = Path(root)
    target = root / 'tensile_workbench.project.json'
    if target.exists():
        # The launcher must remain reachable to recover a corrupt personal file.
        return target
    vault = BackupVault(target)
    if target.with_suffix('.previous.json').exists() or vault.has_history():
        # Missing is not first-run when an installation has recovery history.
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
    encoded = (json.dumps(project, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')
    with settings_lock(target):
        if target.exists():
            return target  # Another session completed startup first.
        if source.name != 'tensile_workbench_defaults.json':
            vault.capture(raw, reason='pre-migration', force=True)
        atomic_bytes(target, encoded)
        vault.try_capture(encoded)
    return target


if __name__ == '__main__':
    print('Saved definitions ready:', migrate(Path(__file__).resolve().parent).name)
