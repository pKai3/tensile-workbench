"""Versioned project definitions with atomic autosave and conflict protection."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import hashlib
import json
import math
import os
import re
import tempfile
import uuid
from tensile_selection import valid_specimen_id
from tensile_fit import validate_threshold, validate_override
from tensile_gauge import validate_group_policy
from tensile_fracture import validate_failure_override
from tensile_group_plot import validate_group_display


class ProjectConflict(RuntimeError):
    pass


def validate_project(project):
    if project.get('schema_version') != 1:
        raise ValueError('Unsupported workbench project schema; the existing file was not changed.')
    validate_threshold(project.get('yield_r2_warning', .98))
    exclusions = project.get('specimen_exclusions', {})
    if not isinstance(exclusions, dict) or any(
            not valid_specimen_id(key) or not isinstance(reason, str)
            for key, reason in exclusions.items()):
        raise ValueError('Global specimen exclusions must map relative specimen paths to reason text.')
    overrides = project.get('specimen_fit_overrides', {})
    if not isinstance(overrides, dict):
        raise ValueError('Specimen fit overrides must be a mapping.')
    for ident, override in overrides.items():
        if not valid_specimen_id(ident):
            raise ValueError('Fit overrides must use relative specimen identities.')
        validate_override(override, saved=True)
    history = project.get('specimen_fit_history', [])
    if not isinstance(history, list):
        raise ValueError('Specimen fit history must be a list.')
    for event in history:
        if not isinstance(event, dict) or not valid_specimen_id(event.get('specimen_id')):
            raise ValueError('Invalid fit history specimen identity.')
        for key in ('before', 'after'):
            if event.get(key) is not None:
                validate_override(event[key], saved=True)
    overrides = project.get('specimen_failure_overrides', {})
    if not isinstance(overrides, dict):
        raise ValueError('Specimen failure EL overrides must be a mapping.')
    for ident, override in overrides.items():
        if not valid_specimen_id(ident):
            raise ValueError('Failure EL overrides must use relative specimen identities.')
        validate_failure_override(override, saved=True)
    history = project.get('specimen_failure_history', [])
    if not isinstance(history, list):
        raise ValueError('Failure EL override history must be a list.')
    for event in history:
        if not isinstance(event, dict) or not valid_specimen_id(event.get('specimen_id')):
            raise ValueError('Invalid failure EL history specimen identity.')
        for key in ('before', 'after'):
            if event.get(key) is not None:
                validate_failure_override(event[key], saved=True)
    graphs = project.get('graphs', [])
    if not graphs:
        raise ValueError('A project needs at least one graph definition.')
    ids, names = set(), set()
    for graph in graphs:
        ident = graph['id']
        name = graph['name'].strip()
        if not ident or ident in ids or not name or name.casefold() in names:
            raise ValueError('Graph names and IDs must be nonempty and unique.')
        ids.add(ident)
        names.add(name.casefold())
        if not isinstance(graph.get('settings'), dict) or not isinstance(graph.get('definition'), dict):
            raise ValueError('Each graph needs calculation settings and a definition.')
        settings = graph['settings']
        validate_group_display(settings)
        order = settings.get('properties_by_group_order', [])
        if (not isinstance(order, list) or any(not isinstance(g, str) or not g for g in order)
                or len(set(order)) != len(order)):
            raise ValueError('Property-plot sample order must be a list of unique group names.')
        for key in ('ys', 'uts', 'el'):
            color = settings.get(f'properties_by_group_{key}_color', '#000000')
            if not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
                raise ValueError('Property-plot colours must be six-digit hex colours.')
        group_gauges = graph['definition'].get('gauge_reconstruction', {})
        if not isinstance(group_gauges, dict):
            raise ValueError('Group gauge settings must be a mapping.')
        for group, policy in group_gauges.items():
            if not isinstance(group, str) or not group:
                raise ValueError('Gauge settings require a sample-group name.')
            validate_group_policy(policy)
        if not isinstance(settings.get('gauge_correction', False), bool):
            raise ValueError('Gauge reconstruction must be a graph-level on/off setting.')
        target = settings.get('target_gauge_mm', 0)
        if (isinstance(target, bool) or not isinstance(target, (int, float)) or
                not math.isfinite(target) or target < 0 or
                (settings.get('gauge_correction') and target <= 0)):
            raise ValueError('Gauge reconstruction requires a positive target gauge length in mm.')
        if not isinstance(graph['settings'].get('groups'), list):
            raise ValueError('Graph sample groups must be a list.')
        if len(set(graph['settings']['groups'])) != len(graph['settings']['groups']):
            raise ValueError('Sample groups cannot be repeated.')
        if not isinstance(graph['settings'].get('families'), list):
            raise ValueError('Visible plot types must be a list.')
        exclusions = graph['definition'].get('specimen_exclusions', {})
        if not isinstance(exclusions, dict) or any(
                not valid_specimen_id(key) or not isinstance(reason, str)
                for key, reason in exclusions.items()):
            raise ValueError('Specimen exclusions must map relative specimen paths to reason text.')
        selections = graph['definition'].get('specimen_inclusion_overrides', {})
        if not isinstance(selections, dict) or any(
                not valid_specimen_id(key) or not isinstance(value, dict)
                or not isinstance(value.get('included'), bool)
                or not isinstance(value.get('reason', ''), str)
                for key, value in selections.items()):
            raise ValueError('Graph specimen overrides require an Include value and optional reason.')
        for group, color in graph['definition'].get('color_overrides', {}).items():
            if not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
                raise ValueError(f'Colour override for {group} must be a six-digit hex colour, e.g. #1f77b4.')
    if project.get('selected_graph') not in ids:
        raise ValueError('The selected graph does not exist.')
    deleted = project.get('deleted_graphs', [])
    if not isinstance(deleted, list):
        raise ValueError('Deleted graphs must be a list.')
    for entry in deleted:
        if (not isinstance(entry, dict) or not isinstance(entry.get('graph'), dict)
                or not isinstance(entry.get('index'), int) or entry['index'] < 0):
            raise ValueError('Invalid deleted-graph recovery entry.')
        graph = entry['graph']
        validate_project({'schema_version': 1, 'graphs': [graph], 'selected_graph': graph.get('id')})


def _atomic_bytes(path, content):
    """Replace one exact project/backup file, never a data file or plot."""
    descriptor, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary = Path(temporary)
        if temporary.exists():
            temporary.unlink()


class ProjectStore:
    def __init__(self, path, defaults_path):
        self.path = Path(path).expanduser().resolve()
        self.defaults_path = Path(defaults_path).resolve()
        self.digest = None
        self.data = None
        if self.path.exists():
            self.reload()
        else:
            seed = json.loads(self.defaults_path.read_text(encoding='utf-8'))
            self.save(seed)

    def reload(self):
        try:
            raw = self.path.read_bytes()
            project = json.loads(raw)
            validate_project(project)
        except Exception as error:
            raise ValueError(f'Cannot load {self.path}. Existing definitions were preserved. '
                             f'The previous save, if available, is in {self.path.with_suffix(".previous.json")}. {error}') from error
        self.data = project
        self.digest = hashlib.sha256(raw).hexdigest()
        return deepcopy(project)

    def save(self, project):
        project = deepcopy(project)
        validate_project(project)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = self.path.with_suffix('.lock')
        try:
            handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as error:
            raise ProjectConflict('The project is being saved by another session. Try again; '
                                  f'if a crashed session left a stale lock, close all notebooks before removing {lock}.') from error
        try:
            with os.fdopen(handle, 'w') as stream:
                stream.write(str(os.getpid()))
            existing = self.path.read_bytes() if self.path.exists() else None
            digest = hashlib.sha256(existing).hexdigest() if existing is not None else None
            if digest != self.digest:
                raise ProjectConflict('Definitions changed in another notebook or outside this session. '
                                      'Reload saved definitions before editing again; no changes were overwritten.')
            project['revision'] = int(self.data.get('revision', 0) if self.data else project.get('revision', 0)) + 1
            project['saved_at'] = datetime.now().astimezone().isoformat()
            encoded = (json.dumps(project, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')
            if existing is not None:
                _atomic_bytes(self.path.with_suffix('.previous.json'), existing)
            _atomic_bytes(self.path, encoded)
            self.digest = hashlib.sha256(encoded).hexdigest()
            self.data = project
        finally:
            lock.unlink()
        return deepcopy(project)

    def add_graph(self, template=None):
        project = deepcopy(self.data)
        base = deepcopy(template or project['new_graph_defaults'])
        if template is None:
            base['definition'].pop('specimen_exclusions', None)
            base['definition'].pop('specimen_inclusion_overrides', None)
            # Older personal projects retain their own new-graph template.
            # Apply the safe default to new graphs without changing saved ones
            # or an explicitly duplicated graph's live-preview preference.
            base['settings']['live_update'] = False
        existing = {g['name'].casefold() for g in project['graphs']}
        stem = base['name'] + ' copy' if template else 'New graph'
        name, number = stem, 2
        while name.casefold() in existing:
            name = f'{stem} {number}'
            number += 1
        base.update(id=uuid.uuid4().hex, name=name)
        base['definition']['name'] = name
        project['graphs'].append(base)
        project['selected_graph'] = base['id']
        return self.save(project)

    def delete_graph(self, ident):
        """Recycle a definition only. No data or output paths are touched."""
        project = deepcopy(self.data)
        index = next(i for i, graph in enumerate(project['graphs']) if graph['id'] == ident)
        entry = {'graph': project['graphs'].pop(index), 'index': index}
        if not project['graphs']:
            draft = deepcopy(project['new_graph_defaults'])
            draft.update(id=uuid.uuid4().hex, name='New graph')
            draft['definition']['name'] = draft['name']
            draft['definition'].pop('specimen_exclusions', None)
            draft['definition'].pop('specimen_inclusion_overrides', None)
            draft['settings'].update(groups=[], live_update=False)
            project['graphs'].append(draft)
            entry['replacement'] = deepcopy(draft)
        if project['selected_graph'] == ident:
            project['selected_graph'] = project['graphs'][min(index, len(project['graphs']) - 1)]['id']
        project.setdefault('deleted_graphs', []).append(entry)
        return self.save(project)

    def undo_delete(self):
        """Restore the latest recycled graph, even after restarting the app."""
        project = deepcopy(self.data)
        if not project.get('deleted_graphs'):
            return deepcopy(self.data)
        entry = project['deleted_graphs'].pop()
        replacement = entry.get('replacement')
        # Remove only the untouched automatic draft. Preserve any user edits.
        if replacement in project['graphs']:
            project['graphs'].remove(replacement)
        graph = entry['graph']
        names = {g['name'].casefold() for g in project['graphs']}
        original, number = graph['name'], 2
        while graph['name'].casefold() in names:
            graph['name'] = f'{original} (restored {number})'
            number += 1
        graph['definition']['name'] = graph['name']
        project['graphs'].insert(min(entry['index'], len(project['graphs'])), graph)
        project['selected_graph'] = graph['id']
        return self.save(project)
