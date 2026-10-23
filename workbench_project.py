"""Versioned project definitions with atomic autosave and conflict protection."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
import json
import math
import re
import uuid
from tensile_selection import valid_specimen_id, validate_data_mode
from tensile_fit import validate_threshold, validate_override
from tensile_settings import validate_group_policy, validate_failure_override, validate_group_display
from tensile_property_variants import VARIANTS_KEY, SPECIMEN_VARIANTS_KEY, validate_variants, split_property_charts
from tensile_locations import ensure_required_variables
from tensile_order import validate_group_order
from tensile_variables import validate_variables
from tensile_colors import DEFAULT_PALETTE, validate_palette
from tensile_moves import validate_tracking, graph_blocks
from tensile_overrides import DISABLED, validate_disabled
from workbench_backups import (BackupVault, ProjectConflict, RecoveryRequired,
                               atomic_bytes as _atomic_bytes, backup_warning,
                               digest, read_optional, settings_lock)


def validate_project(project):
    if project.get('schema_version') != 1:
        raise ValueError('Unsupported workbench project schema; the existing file was not changed.')
    validate_tracking(project)
    validate_disabled(project)
    validate_threshold(project.get('yield_r2_warning', .98))
    validate_variables(project.get('group_variables', {}))
    validate_variables(project.get('specimen_variables', {}), scope='specimen')
    modes = project.get('specimen_data_modes', {})
    if not isinstance(modes, dict):
        raise ValueError('Specimen data-use modes must be a mapping.')
    for ident, policy in modes.items():
        if not valid_specimen_id(ident) or not isinstance(policy, dict) or not isinstance(policy.get('reason', ''), str):
            raise ValueError('Invalid specimen data-use policy.')
        validate_data_mode(policy.get('mode'))
        if policy['mode'] == 'exclude':
            raise ValueError('Whole-specimen exclusions belong in specimen_exclusions.')
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
        validate_disabled(graph['definition'], graph=True)
        validate_palette(settings.get('color_palette', DEFAULT_PALETTE))
        validate_group_display(settings)
        for key in (VARIANTS_KEY, SPECIMEN_VARIANTS_KEY):
            if key in settings:
                validate_variants(settings[key])
        validate_group_order(settings.get('group_order', []))
        for family in ('ys_vs_el', 'uts_vs_el'):
            if settings.get(family + '_mean_population', 'independent') not in ('paired', 'independent'):
                raise ValueError(f'{family}: mean population must be paired or independent.')
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
        for policy in selections.values():
            validate_data_mode(policy.get('mode', 'all' if policy['included'] else 'exclude'))
            if 'mode' in policy and policy['included'] != (policy['mode'] != 'exclude'):
                raise ValueError('Data-use mode conflicts with specimen inclusion.')
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


def _discard_obsolete_settings(project):
    """Retire the redundant plot-specific order without adopting it elsewhere."""
    for graph in graph_blocks(project):
        graph.get('settings', {}).pop('properties_by_group_order', None)


def decode_project(raw):
    """Validate/normalise a snapshot without reading data or writing settings."""
    project = split_property_charts(ensure_required_variables(json.loads(raw)))
    validate_project(project)
    _discard_obsolete_settings(project)
    return project


class ProjectStore:
    def __init__(self, path, defaults_path, *, backup_root=None):
        self.path = Path(path).expanduser().resolve()
        self.defaults_path = Path(defaults_path).resolve()
        self.digest = None
        self.file_stamp = None
        self.data = None
        self.backups = BackupVault(self.path, backup_root)
        if self.path.exists():
            self.reload()
        elif self.path.with_suffix('.previous.json').exists() or self.backups.has_history():
            raise RecoveryRequired('Saved definitions are missing, but backup history exists. '
                                   'Use Backups & restore. Starter definitions were not written.')
        else:
            seed = json.loads(self.defaults_path.read_text(encoding='utf-8'))
            self.save(seed)

    @property
    def backup_warning(self):
        return backup_warning(self.path)

    def _stamp(self):
        try:
            info = self.path.stat()
            return (info.st_dev, info.st_ino, info.st_mtime_ns, info.st_size)
        except FileNotFoundError:
            return None

    def _protect_migration(self, raw):
        try:
            self.backups.capture(raw, reason='pre-migration', force=True)
        except Exception as error:
            raise RecoveryRequired('Settings upgrade paused: the safety backup could not be made. '
                                   f'The original file was not changed. {error}') from error

    def reload(self):
        try:
            raw = self.path.read_bytes()
            project = decode_project(raw)
        except Exception as error:
            raise RecoveryRequired(f'Cannot load {self.path.name}. Existing definitions were preserved. '
                                   f'Use Backups & restore. {error}') from error
        if project != json.loads(raw):
            # Preserve the exact older schema before any upgrade can be saved.
            self._protect_migration(raw)
        else:
            self.backups.try_capture(raw, reason='opened')
        self.data = project
        self.digest = digest(raw)
        self.file_stamp = self._stamp()
        return deepcopy(project)

    def save(self, project, *, reason='autosave'):
        project = split_property_charts(ensure_required_variables(project))
        validate_project(project)
        _discard_obsolete_settings(project)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with settings_lock(self.path):
            existing = read_optional(self.path)
            # The stamp also catches restoring byte-identical older contents:
            # an already-open stale session must still reload after a restore.
            if digest(existing) != self.digest or self._stamp() != self.file_stamp:
                raise ProjectConflict('Definitions changed in another notebook or outside this session. '
                                      'Reload saved definitions before editing again; no changes were overwritten.')
            project['revision'] = int(self.data.get('revision', 0) if self.data else project.get('revision', 0)) + 1
            project['saved_at'] = datetime.now().astimezone().isoformat()
            encoded = (json.dumps(project, indent=2, ensure_ascii=False, allow_nan=False) + '\n').encode('utf-8')
            if existing is not None:
                if reason == 'pre-migration':
                    self._protect_migration(existing)
                else:
                    self.backups.try_capture(existing)
                _atomic_bytes(self.path.with_suffix('.previous.json'), existing)
            _atomic_bytes(self.path, encoded)
            self.digest = digest(encoded)
            self.file_stamp = self._stamp()
            self.data = project
            self.backups.try_capture(encoded)
        return deepcopy(project)

    def add_graph(self, template=None):
        project = deepcopy(self.data)
        base = deepcopy(template or project['new_graph_defaults'])
        if template is None:
            base['definition'].pop(DISABLED, None)
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
            draft['definition'].pop(DISABLED, None)
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
