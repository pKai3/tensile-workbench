"""Content-verified relocation proposals. Applying one requires explicit approval.

Only the personal project is changed; source CSVs are never edited or moved.
The index lives in that ignored project, not in shared deployment defaults.
"""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from pathlib import Path, PurePosixPath
import re

from tensile_selection import SAMPLE_GROUP_PREFIX, SAMPLE_ID_PREFIX, valid_specimen_id
from tensile_overrides import DISABLED

GROUP_MAPS = ('name_overrides', 'color_overrides', 'youngs_modulus_overrides',
              'representative_overrides', 'gauge_reconstruction')
SPECIMEN_MAPS = ('specimen_exclusions', 'specimen_data_modes',
                 'specimen_fit_overrides', 'specimen_failure_overrides',
                 'specimen_inclusion_overrides')
HISTORIES = ('specimen_fit_history', 'specimen_failure_history')


def graph_blocks(project):
    yield from project.get('graphs', [])
    for entry in project.get('deleted_graphs', []):
        for key in ('graph', 'replacement'):
            if key in entry:
                yield entry[key]
    if 'new_graph_defaults' in project:
        yield project['new_graph_defaults']


def references(project):
    groups = set(project.get('display_names', {}))
    specimens = set()
    for block in [project, *(g.get('definition', {}) for g in graph_blocks(project))]:
        for key in SPECIMEN_MAPS:
            specimens.update(block.get(key, {}))
            specimens.update(block.get(DISABLED, {}).get(key, {}))
    for key in HISTORIES:
        specimens.update(e['specimen_id'] for e in project.get(key, []))
    for graph in graph_blocks(project):
        settings, definition = graph.get('settings', {}), graph.get('definition', {})
        for key in ('groups', 'properties_by_group_order'):
            groups.update(settings.get(key, []))
        groups.update(settings.get('properties_by_group_labels', {}))
        for key in GROUP_MAPS:
            groups.update(definition.get(key, {}))
    return ({g for g in groups if not g.startswith(SAMPLE_GROUP_PREFIX)},
            {s for s in specimens if not s.startswith(SAMPLE_ID_PREFIX)})


def under(ident, group):
    return ident.startswith(group + '/')


def valid_hash(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def validate_tracking(project):
    tracking = project.get('data_move_tracking')
    if tracking is None:
        return
    if not isinstance(tracking, dict) or tracking.get('version') != 1:
        raise ValueError('Unsupported data-move index; existing settings were preserved.')
    if not isinstance(tracking.get('groups'), dict) or not isinstance(tracking.get('cache'), dict):
        raise ValueError('Invalid data-move index; existing settings were preserved.')
    for group, entry in tracking['groups'].items():
        if not valid_specimen_id(group) or group.startswith((SAMPLE_GROUP_PREFIX, SAMPLE_ID_PREFIX)):
            raise ValueError('Invalid research group in data-move index.')
        if (not isinstance(entry, dict) or not isinstance(entry.get('complete'), bool)
                or not isinstance(entry.get('files'), dict)):
            raise ValueError('Invalid data-move group inventory.')
        for ident, digest in entry['files'].items():
            if not valid_specimen_id(ident) or not under(ident, group) or not valid_hash(digest):
                raise ValueError('Invalid data-move file fingerprint.')
    for ident, entry in tracking.get('cache', {}).items():
        if (not valid_specimen_id(ident) or ident.startswith(SAMPLE_ID_PREFIX)
                or not isinstance(entry, dict) or not valid_hash(entry.get('sha256'))):
            raise ValueError('Invalid data-move fingerprint cache.')
        if any(not isinstance(entry.get(key), int) for key in ('size', 'mtime_ns', 'ctime_ns')):
            raise ValueError('Invalid data-move file metadata.')


def fingerprint(path, cached=None):
    before = path.stat()
    metadata = dict(size=before.st_size, mtime_ns=before.st_mtime_ns, ctime_ns=before.st_ctime_ns)
    if cached and all(cached.get(k) == v for k, v in metadata.items()):
        return cached
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise ValueError(f'File changed during move check: {path.name}. Reload data and retry.')
    return {**metadata, 'sha256': digest.hexdigest()}


def seed_legacy(project, history):
    """Older installations may already have hashes on manual overrides.

    These are partial evidence, not a fabricated full-group inventory. Settings
    for any other unverified specimens are explicitly left at their old IDs.
    """
    groups, _ = references(project)
    for key in ('specimen_fit_overrides', 'specimen_failure_overrides'):
        overrides = {**project.get(DISABLED, {}).get(key, {}), **project.get(key, {})}
        for ident, override in overrides.items():
            if ident.startswith(SAMPLE_ID_PREFIX) or not valid_hash(override.get('source_sha256')):
                continue
            owners = [g for g in groups if under(ident, g)]
            if owners:
                group = max(owners, key=len)
                if group not in history:
                    history[group] = {'complete': False, 'files': {}}
                # Never replace previously recorded content with an older override.
                history[group]['files'].setdefault(ident, override['source_sha256'])


def match_files(old, new, sources, targets):
    """Stable relative filenames disambiguate identical files within a group.

    Renamed files need a unique hash match. Never use names alone as evidence.
    """
    available, mapping = dict(targets), {}
    for ident, digest in sources.items():
        same = new + '/' + ident[len(old) + 1:]
        if available.get(same) == digest:
            mapping[ident] = same
            available.pop(same)
    for ident, digest in sources.items():
        if ident in mapping:
            continue
        matches = [p for p, sha in available.items() if sha == digest]
        if len(matches) != 1:
            return None
        mapping[ident] = matches[0]
        available.pop(matches[0])
    return mapping


def scan_moves(project, root, files, *, force_groups=()):
    """Return a new index and review proposals; never apply a relocation.

    Fingerprint work is cached by path, size, mtime and ctime. Confirmation
    forces a fresh read of the destination before any settings are migrated.
    """
    validate_tracking(project)
    root = Path(root)
    tracking = deepcopy(project.get('data_move_tracking', {'version': 1, 'groups': {}, 'cache': {}}))
    history = tracking['groups']
    seed_legacy(project, history)
    group_refs, specimen_refs = references(project)
    def relevant(group):
        return group in group_refs or any(under(s, group) for s in specimen_refs)
    # Normal starts index only groups with saved settings/selections. Expand the
    # search to other groups only when a tracked source actually goes missing.
    searching = any(relevant(g) and any(not (root / p).exists() for p in entry['files'])
                    for g, entry in history.items())
    current, cache, warnings = {}, deepcopy(tracking['cache']), []
    for group in sorted(group_refs - files.keys() - history.keys()):
        warnings.append(f'{group}: no earlier file fingerprints are available to verify a move. '
                        'Restore the original location and reload once to establish move protection, '
                        'or reselect the group and review its settings manually.')
    for group, paths in files.items():
        if group.startswith(SAMPLE_GROUP_PREFIX) or (not searching and not relevant(group)):
            continue
        manifest = {}
        try:
            for path in paths:
                path = Path(path)
                ident = path.relative_to(root).as_posix()
                cached = None if group in force_groups else tracking['cache'].get(ident)
                info = fingerprint(path, cached)
                cache[ident] = info
                manifest[ident] = info['sha256']
            if manifest:
                current[group] = {'complete': True, 'files': manifest}
        except (OSError, ValueError) as error:
            warnings.append(f'{group}: move check incomplete — {error}')
    proposals = []
    for old, baseline in history.items():
        if old not in group_refs and not any(under(s, old) for s in specimen_refs):
            continue
        old_files = baseline['files']
        if not old_files:
            continue
        same_group = old in files
        missing = {p: sha for p, sha in old_files.items() if not (root / p).exists()}
        if not missing:
            continue  # A copy is not a move, even if its contents are identical.
        if not same_group and len(missing) != len(old_files):
            warnings.append(f'{old}: only part of the group is missing; no whole-group migration proposed.')
            continue
        sources = missing if same_group else old_files
        candidates = []
        for new, entry in current.items():
            if same_group and new != old:
                continue
            targets = entry['files']
            if same_group:
                targets = {p: sha for p, sha in targets.items() if p not in old_files}
            source_counts, target_counts = Counter(sources.values()), Counter(targets.values())
            if not same_group and baseline['complete'] and source_counts != target_counts:
                continue
            if source_counts - target_counts:
                continue
            mapping = match_files(old, new, sources, targets)
            candidates.append((new, mapping))
        if not candidates:
            warnings.append(f'{old}: saved files are missing, but no unchanged-content move was found. '
                            'Settings remain at their original paths.')
            continue
        if len(candidates) != 1 or candidates[0][1] is None:
            warnings.append(f'{old}: ambiguous move (duplicate file contents or multiple matching groups: '
                            + ', '.join(g for g, _ in candidates) + '). No settings migrated.')
            continue
        new, mapping = candidates[0]
        mapping = {a: b for a, b in mapping.items() if a != b}
        unresolved = sorted(s for s in specimen_refs if under(s, old)
                            and s not in mapping and not (root / s).exists())
        proposals.append({'old': old, 'new': new, 'mapping': mapping,
                          'target': current[new], 'unresolved': unresolved,
                          'partial_evidence': not baseline['complete'], 'blocked': ''})
    # Two vanished, identical groups must not both donate settings to one target.
    claims = Counter(p['new'] for p in proposals)
    for proposal in proposals:
        if claims[proposal['new']] > 1:
            proposal['blocked'] = 'Multiple missing groups match this destination. Resolve the ambiguity first.'
        else:
            try:
                migrate_settings(project, proposal, audit=False)
            except ValueError as error:
                proposal['blocked'] = str(error)
    # Retain the old inventory while a file is missing, even without a candidate.
    # Otherwise a second reload would forget an unapproved rename.
    for group, entry in current.items():
        previous = history.get(group)
        if previous is None or all((root / p).exists() for p in previous['files']):
            history[group] = entry
    tracking['cache'] = cache
    return tracking, proposals, warnings


def remap_keys(block, key, mapping):
    if key not in block:
        return
    values = block[key]
    for old, new in mapping.items():
        if old == new or old not in values:
            continue
        if new in values and values[new] != values[old]:
            raise ValueError(f'Conflicting {key} settings at {new}; nothing will be overwritten.')
        values[new] = values.pop(old)


def migrate_settings(project, proposal, *, audit=True):
    """Pure, atomic proposal application; callers must verify files and ask first."""
    result = deepcopy(project)
    old, new, specimens = proposal['old'], proposal['new'], proposal['mapping']
    groups = {old: new} if old != new else {}
    remap_keys(result, 'display_names', groups)
    for key in SPECIMEN_MAPS:
        remap_keys(result, key, specimens)
        remap_keys(result.get(DISABLED, {}), key, specimens)
    for key in HISTORIES:
        for event in result.get(key, []):
            if event['specimen_id'] in specimens:
                event.setdefault('original_specimen_id', event['specimen_id'])
                event['specimen_id'] = specimens[event['specimen_id']]
    for graph in graph_blocks(result):
        settings, definition = graph.get('settings', {}), graph.get('definition', {})
        for key in ('groups', 'properties_by_group_order'):
            if key in settings:
                settings[key] = list(dict.fromkeys(groups.get(g, g) for g in settings[key]))
        remap_keys(settings, 'properties_by_group_labels', groups)
        representatives = definition.get('representative_overrides', {})
        if old in representatives:
            matches = {PurePosixPath(b).stem for a, b in specimens.items()
                       if PurePosixPath(a).stem == representatives[old]}
            if len(matches) > 1:
                raise ValueError(f'Ambiguous representative specimen in {old}.')
            if matches:
                representatives[old] = matches.pop()
        for key in GROUP_MAPS:
            remap_keys(definition, key, groups)
        for key in SPECIMEN_MAPS:
            remap_keys(definition, key, specimens)
            remap_keys(definition.get(DISABLED, {}), key, specimens)
    for block in [result, *(g.get('definition', {}) for g in graph_blocks(result))]:
        for key in SPECIMEN_MAPS:
            if set(block.get(key, {})) & set(block.get(DISABLED, {}).get(key, {})):
                raise ValueError(f'Conflicting active and disabled {key} settings after move.')
    if audit:
        result.setdefault('data_move_history', []).append({
            'approved_at': datetime.now(timezone.utc).isoformat(),
            'old_group': old, 'new_group': new, 'specimen_paths': dict(specimens),
            'unresolved_paths': proposal['unresolved'], 'basis': 'SHA-256 verified; user approved'})
        tracking = result.setdefault('data_move_tracking', {'version': 1, 'groups': {}, 'cache': {}})
        tracking['groups'].pop(old, None)
        tracking['groups'][new] = deepcopy(proposal['target'])
    return result


def forget_group(project, group, *, live_groups=()):
    """Forget a removed group's preferences and tracking, not its source files.

    No deletion log or tombstone is created. Other live groups retain their
    specimen settings, including when an old group folder became a container.
    """
    if not valid_specimen_id(group) or group.startswith((SAMPLE_GROUP_PREFIX, SAMPLE_ID_PREFIX)):
        raise ValueError('Only a specific research group can be forgotten.')
    if group in live_groups:
        raise ValueError('This group is available again. Reload and review it before forgetting settings.')
    result = deepcopy(project)
    def owned(ident):
        return under(ident, group) and not any(under(ident, live) for live in live_groups)
    result.get('display_names', {}).pop(group, None)
    for block in [result, *(g.get('definition', {}) for g in graph_blocks(result))]:
        for key in SPECIMEN_MAPS:
            if key in block:
                block[key] = {ident: value for ident, value in block[key].items() if not owned(ident)}
            parked = block.get(DISABLED, {})
            if key in parked:
                parked[key] = {ident: value for ident, value in parked[key].items() if not owned(ident)}
                if not parked[key]:
                    parked.pop(key)
            if not parked:
                block.pop(DISABLED, None)
    for graph in graph_blocks(result):
        settings, definition = graph.get('settings', {}), graph.get('definition', {})
        for key in ('groups', 'properties_by_group_order'):
            if key in settings:
                settings[key] = [g for g in settings[key] if g != group]
        settings.get('properties_by_group_labels', {}).pop(group, None)
        for key in GROUP_MAPS:
            definition.get(key, {}).pop(group, None)
    for key in HISTORIES:
        if key in result:
            result[key] = [e for e in result[key] if not owned(e['specimen_id'])]
    tracking = result.get('data_move_tracking', {})
    tracking.get('groups', {}).pop(group, None)
    if 'cache' in tracking:
        tracking['cache'] = {ident: item for ident, item in tracking['cache'].items() if not owned(ident)}
    if 'data_move_history' in result:
        result['data_move_history'] = [e for e in result['data_move_history']
                                      if group not in (e.get('old_group'), e.get('new_group'))]
    # Clean up a dismissal saved by the earlier UI, without maintaining a log.
    if 'data_move_dismissed_groups' in result:
        result['data_move_dismissed_groups'] = [g for g in result['data_move_dismissed_groups'] if g != group]
        if not result['data_move_dismissed_groups']:
            result.pop('data_move_dismissed_groups')
    return result
