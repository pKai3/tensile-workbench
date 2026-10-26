"""Portable specimen identities and hard-ignore rules shared by all data readers."""
import os
import re
from copy import deepcopy
from pathlib import Path, PurePosixPath

SAMPLE_GROUP_PREFIX = 'Sample data / '
SAMPLE_ID_PREFIX = 'sample-data://'


def group_display_name(group, display_names=None, overrides=None):
    """Folder paths are identities, not publication labels. Keep explicit labels."""
    leaf = group.rsplit('/', 1)[-1]
    for labels in (overrides or {}, display_names or {}):
        if group in labels:
            # Older colour/label editors sometimes saved the automatic full ID.
            return leaf if labels[group] == group else labels[group]
    return leaf


DATA_MODES = {
    'all': 'Use all data',
    'exclude_shape': 'Exclude from shape',
    'after_uts': 'AVE failed after UTS / Broke outside dots',
    'after_yield': 'AVE failed after yield, before UTS',
    'no_strain': 'AVE unreliable throughout',
    'exclude': 'Exclude specimen entirely',
}
DATA_MODE_OPTIONS = [(label, key) for key, label in DATA_MODES.items()]


def validate_data_mode(mode):
    if not isinstance(mode, str) or mode not in DATA_MODES:
        raise ValueError('Unknown specimen data-use mode.')


def record_mode(record):
    return record.get('_data_mode', 'all')


def property_allowed(mode, field):
    validate_data_mode(mode)
    if mode == 'exclude':
        return False
    if mode == 'exclude_shape':
        return True  # Properties stay valid; only curve contributions are excluded.
    if field in ('UTS (MPa)', 'uts', 'UTS'):
        return True
    if field in ('Yield (MPa)', 'Yield strain (%)', 'Fitted E (GPa)', 'ys', 'e',
                 '0.2% yield strength', 'Fitted elastic modulus'):
        return mode != 'no_strain'
    if field in ('Uniform elongation (%)', 'uniform', 'Uniform elongation'):
        return mode in ('all', 'after_uts')
    return mode == 'all'


def curve_allowed(record, prepeak=False):
    return record_mode(record) in (('all', 'after_uts') if prepeak else ('all',))


def analysis_properties(record, properties):
    result = dict(properties)
    for field in ('Yield (MPa)', 'Yield strain (%)', 'UTS (MPa)', 'Uniform elongation (%)',
                  'Failure elongation (%)', 'Toughness (MJ/m^3)', 'Fitted E (GPa)',
                  'Measured failure elongation (%)', 'Measured toughness (MJ/m^3)',
                  'Estimated failure elongation (%)', 'Estimated toughness (MJ/m^3)'):
        if field in result and not property_allowed(record_mode(record), field):
            result[field] = float('nan')
    return result


def data_files(root, suffix):
    """Do not enter marked folders or read files containing ! in a name."""
    root = Path(root)
    if '!' in root.name:
        return []
    found = []
    for directory, folders, files in os.walk(root, followlinks=False):
        folders[:] = sorted(name for name in folders if '!' not in name)
        found.extend(Path(directory) / name for name in sorted(files)
                     if '!' not in name and name.lower().endswith(suffix))
    return sorted(found)


def csv_files(root):
    return data_files(root, '.csv')


class DiscoveredGroups(dict):
    """Ordinary group mapping with visible boundary-review notices."""
    def __init__(self):
        super().__init__()
        self.warnings = []


def discover_sample_groups(root):
    """Discover groups under any number of organisational folders.

    A group owns direct CSVs or instrument files/export folders. Its nested
    exports stay together, as in the original flat layout. Directories holding
    only other group directories are containers, never combined datasets.
    Keys are full POSIX paths relative to the selected data root, so identical
    leaf names under different owners cannot merge.
    """
    root = Path(root)
    groups = DiscoveredGroups()

    def visit(directory):
        entries = sorted(p for p in directory.iterdir() if '!' not in p.name)
        files = [p for p in entries if p.is_file()]
        folders = [p for p in entries if p.is_dir() and not p.is_symlink()]
        key = directory.relative_to(root).as_posix()
        if (directory / '.tensile-group').is_file():
            sources = csv_files(directory)
            if sources:
                groups[key] = sources
            return
        exports = [p for p in folders if re.search(r'(?:^|[._ -])exports?$', p.name, re.I)
                   and any(f.is_file() and f.suffix.lower() == '.csv' and '!' not in f.name for f in p.iterdir())]
        own = [p for p in files if p.suffix.lower() == '.csv']
        for folder in exports:
            own.extend(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == '.csv' and '!' not in p.name)
        before = len(groups)
        for folder in folders:
            if folder not in exports:
                visit(folder)
            else:
                # An export-like folder name is not permission to combine
                # additional materials nested beneath it.
                for child in sorted(folder.iterdir()):
                    if child.is_dir() and not child.is_symlink() and '!' not in child.name:
                        visit(child)
        descendants = len(groups) > before
        if descendants:
            # A parent report or stray CSV does not establish that its child
            # groups are repeat runs of the same material. Keep boundaries.
            if own or any(p.suffix.lower() in ('.is_tens', '.id_tens', '.pdf') for p in files):
                groups.warnings.append(f'{key}: nested sample groups kept separate; parent files were not '
                    'pooled. For deliberately combined runs, confirm the boundary by adding an empty '
                    '.tensile-group file in their common sample-group folder.')
            if own:
                from tensile_columns import is_measurement_header
                import csv
                def has_measurements(path):
                    try:
                        with path.open('rb') as stream:
                            text = stream.read(262144).decode('utf-8-sig', errors='replace')
                        return any(is_measurement_header(row) for sep in (',', ';', '\t')
                                   for row in csv.reader(text.splitlines(), delimiter=sep))
                    except (OSError, csv.Error):
                        return False
                if any(has_measurements(p) for p in own):
                    groups[key] = sorted(own)
        elif own:
            groups[key] = sorted(own)

    for directory in sorted(p for p in root.iterdir() if p.is_dir() and not p.is_symlink() and '!' not in p.name):
        visit(directory)
    return groups


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
    """An analysis override wins; otherwise inherit the persistent global choice."""
    ident = specimen_id(record)
    excluded = (project or {}).get('specimen_exclusions', {})
    override = spec.get('specimen_inclusion_overrides', {}).get(ident)
    # Compatibility for callers still holding a pre-migration definition.
    if override is None and ident in spec.get('specimen_exclusions', {}):
        override = {'included': False, 'reason': spec['specimen_exclusions'][ident]}
    partial = (project or {}).get('specimen_data_modes', {}).get(ident, {})
    global_mode = 'exclude' if ident in excluded else partial.get('mode', 'all')
    mode = (override.get('mode', 'all') if override['included'] else 'exclude') if override is not None else global_mode
    validate_data_mode(mode)
    result = {'included': mode != 'exclude', 'mode': mode, 'global_mode': global_mode,
            'reason': override.get('reason', '') if override is not None else excluded.get(ident, partial.get('reason', '')),
            'scope': 'graph' if override is not None else 'global',
            'global_included': ident not in excluded,
            'global_reason': excluded.get(ident, partial.get('reason', ''))}
    active = [other for other in record.get('_duplicate_ids', [])
              if selection_state({'specimen_id': other, 'source_file': other}, spec, project)['included']]
    result['duplicate_review'] = ''
    if len(active) > 1:
        result['included'] = False
        result['duplicate_review'] = ('Duplicate export or shared Instron row: ' +
            ', '.join(Path(other).name for other in active) +
            '. Results withheld pending review. Use Data use to exclude the unwanted copies, leaving one candidate.')
    return result


def is_included(record, spec, project=None):
    return selection_state(record, spec, project)['included']


def migrate_specimen_selections(project):
    """Promote existing active-analysis exclusions once; never lose saved reasons.

    Deleted analyses do not change the current global population. Their old
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
