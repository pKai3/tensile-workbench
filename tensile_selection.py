"""Portable specimen identities and hard-ignore rules shared by all data readers."""
import os
from copy import deepcopy
from pathlib import Path, PurePosixPath

SAMPLE_GROUP_PREFIX = 'Sample data / '
SAMPLE_ID_PREFIX = 'sample-data://'


def csv_files(root):
    """Do not enter marked folders or read CSVs containing ! anywhere in a name."""
    root = Path(root)
    if '!' in root.name:
        return []
    found = []
    for directory, folders, files in os.walk(root, followlinks=False):
        folders[:] = sorted(name for name in folders if '!' not in name)
        found.extend(Path(directory) / name for name in sorted(files)
                     if '!' not in name and name.lower().endswith('.csv'))
    return sorted(found)


def valid_specimen_id(value):
    """Research IDs remain relative paths; bundled IDs have a separate namespace."""
    if isinstance(value, str) and value.startswith(SAMPLE_ID_PREFIX):
        value = value[len(SAMPLE_ID_PREFIX):]
    return (isinstance(value, str) and bool(value) and '\\' not in value
            and not PurePosixPath(value).is_absolute()
            and all(part not in ('', '.', '..') for part in value.split('/')))


def specimen_id(record):
    # Fallback supports callers that construct records outside PreviewSession.
    return record.get('specimen_id', record['source_file'])


def selection_state(record, spec, project=None):
    """A graph override wins; otherwise inherit the persistent global choice."""
    ident = specimen_id(record)
    excluded = (project or {}).get('specimen_exclusions', {})
    override = spec.get('specimen_inclusion_overrides', {}).get(ident)
    # Compatibility for callers still holding a pre-migration definition.
    if override is None and ident in spec.get('specimen_exclusions', {}):
        override = {'included': False, 'reason': spec['specimen_exclusions'][ident]}
    return {'included': override['included'] if override is not None else ident not in excluded,
            'reason': override.get('reason', '') if override is not None else excluded.get(ident, ''),
            'scope': 'graph' if override is not None else 'global',
            'global_included': ident not in excluded,
            'global_reason': excluded.get(ident, '')}


def is_included(record, spec, project=None):
    return selection_state(record, spec, project)['included']


def migrate_specimen_selections(project):
    """Promote existing active-graph exclusions once; never lose saved reasons.

    Deleted graphs do not change the current global population. Their old
    exclusions become explicit local overrides for use if they are restored.
    """
    project = deepcopy(project)
    excluded = project.setdefault('specimen_exclusions', {})
    for graph in project['graphs']:
        for ident, reason in graph['definition'].pop('specimen_exclusions', {}).items():
            previous = excluded.get(ident, '')
            excluded[ident] = '\n'.join(dict.fromkeys(filter(None, [previous, reason])))
    for entry in project.get('deleted_graphs', []):
        for key in ('graph', 'replacement'):
            if key in entry:
                spec = entry[key]['definition']
                for ident, reason in spec.pop('specimen_exclusions', {}).items():
                    spec.setdefault('specimen_inclusion_overrides', {}).setdefault(
                        ident, {'included': False, 'reason': reason})
    default = project.get('new_graph_defaults', {}).get('definition', {})
    default.pop('specimen_exclusions', None)
    default.pop('specimen_inclusion_overrides', None)
    return project
