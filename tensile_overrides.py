"""Current specimen settings and reversible disabling; no data processing or I/O."""
from copy import deepcopy
import json
from pathlib import PurePosixPath
import re

from tensile_selection import (DATA_MODES, SAMPLE_GROUP_PREFIX, SAMPLE_ID_PREFIX,
                               valid_specimen_id, validate_data_mode)

DISABLED = 'disabled_specimen_overrides'
KINDS = {
    'specimen_fit_overrides': 'Elastic fit',
    'specimen_failure_overrides': 'Failure elongation',
    'specimen_exclusions': 'Whole-specimen exclusion',
    'specimen_data_modes': 'Data use',
    'specimen_inclusion_overrides': 'Graph data use',
}
GLOBAL_KINDS = tuple(key for key in KINDS if key != 'specimen_inclusion_overrides')
GRAPH_KINDS = ('specimen_inclusion_overrides', 'specimen_exclusions')


def clear_disabled(block, kinds, ident):
    """An explicit edit in an existing editor replaces any disabled old setting."""
    parked = block.get(DISABLED, {})
    for kind in kinds:
        parked.get(kind, {}).pop(ident, None)
    for kind in list(parked):
        if not parked[kind]:
            parked.pop(kind)
    if not parked:
        block.pop(DISABLED, None)


def validate_disabled(block, *, graph=False):
    parked = block.get(DISABLED, {})
    if not isinstance(parked, dict):
        raise ValueError('Disabled specimen overrides must be a mapping.')
    allowed = GRAPH_KINDS if graph else GLOBAL_KINDS
    for kind, values in parked.items():
        if kind not in allowed or not isinstance(values, dict):
            raise ValueError('Invalid disabled specimen override type or scope.')
        for ident, value in values.items():
            if not valid_specimen_id(ident):
                raise ValueError('Disabled overrides require relative specimen identities.')
            if ident in block.get(kind, {}):
                raise ValueError('An override cannot be both active and disabled in the same scope.')
            if kind == 'specimen_fit_overrides':
                from tensile_fit import validate_override
                validate_override(value, saved=True)
            elif kind == 'specimen_failure_overrides':
                from tensile_fracture import validate_failure_override
                validate_failure_override(value, saved=True)
            elif kind == 'specimen_exclusions':
                if not isinstance(value, str):
                    raise ValueError('Disabled exclusion requires reason text.')
            else:
                if not isinstance(value, dict) or not isinstance(value.get('reason', ''), str):
                    raise ValueError('Invalid disabled data-use setting.')
                if kind == 'specimen_inclusion_overrides':
                    if not isinstance(value.get('included'), bool):
                        raise ValueError('Disabled graph selection requires an Include value.')
                    mode = value.get('mode', 'all' if value['included'] else 'exclude')
                    if value['included'] != (mode != 'exclude'):
                        raise ValueError('Disabled data-use mode conflicts with Include value.')
                else:
                    mode = value.get('mode')
                    if mode == 'exclude':
                        raise ValueError('Whole-specimen exclusion belongs in specimen_exclusions.')
                validate_data_mode(mode)


def setting_text(kind, value):
    if kind == 'specimen_exclusions':
        return DATA_MODES['exclude']
    if kind in ('specimen_data_modes', 'specimen_inclusion_overrides'):
        mode = value.get('mode', 'all' if value.get('included', True) else 'exclude')
        return DATA_MODES[mode]
    if kind == 'specimen_fit_overrides':
        lo, hi = value['strain_bounds']
        if value['mode'] == 'range':
            return f'Manual range: {lo:.5f}–{hi:.5f}% strain'
        return 'Manual line: ' + ' → '.join(f'({x:.5f}%, {y:.2f} MPa)' for x, y in value['endpoints'])
    strain = value.get('strain_pct')
    suffix = f' · {strain:.2f}% strain' if isinstance(strain, (float, int)) else ''
    return f'Manual endpoint: original row {value["row"]}' + suffix


def override_entries(project):
    """Current global and saved-graph settings only, never historical snapshots."""
    blocks = [(None, 'Global', project, GLOBAL_KINDS)] + [
        (graph['id'], graph['name'], graph['definition'], GRAPH_KINDS)
        for graph in project.get('graphs', [])]
    for scope, scope_name, block, kinds in blocks:
        for enabled, source in ((True, block), (False, block.get(DISABLED, {}))):
            for kind in kinds:
                for ident, value in source.get(kind, {}).items():
                    yield {'id': json.dumps([scope, kind, ident, enabled]),
                           'scope': scope, 'scope_name': scope_name, 'kind': kind,
                           'specimen_id': ident, 'enabled': enabled, 'value': deepcopy(value)}


def override_rows(project, available=None, labels=None, groups=()):
    """Build table rows from settings and discovery/cached labels, not raw curves."""
    available, labels = available or {}, labels or {}
    known = set(groups) | set(available.values()) | set(project.get('display_names', {}))
    known.update(project.get('data_move_tracking', {}).get('groups', {}))
    for graph in project.get('graphs', []):
        known.update(graph.get('settings', {}).get('groups', []))
    rows = []
    for entry in override_entries(project):
        ident, value = entry['specimen_id'], entry['value']
        group_path = (SAMPLE_ID_PREFIX + g[len(SAMPLE_GROUP_PREFIX):]
                      if g.startswith(SAMPLE_GROUP_PREFIX) else g for g in known)
        owners = [g for g in group_path if ident.startswith(g + '/')]
        owner = max(owners, key=len) if owners else str(PurePosixPath(ident).parent)
        group = (SAMPLE_GROUP_PREFIX + owner[len(SAMPLE_ID_PREFIX):]
                 if owner.startswith(SAMPLE_ID_PREFIX) else owner)
        rows.append({**entry, 'group': group, 'specimen': labels.get(ident) or PurePosixPath(ident).stem,
                     'label_source': 'Specimen label' if labels.get(ident) else 'CSV filename',
                     'type': KINDS[entry['kind']], 'setting': setting_text(entry['kind'], value),
                     'reason': value if isinstance(value, str) else value.get('reason', ''),
                     'availability': 'Available' if ident in available else
                         'Hidden or unavailable sample data' if ident.startswith(SAMPLE_ID_PREFIX) else 'Unavailable'})
    def natural(text):
        return tuple((1, int(part)) if part.isdigit() else (0, part.casefold())
                     for part in re.split(r'(\d+)', text))
    return sorted(rows, key=lambda row: (natural(row['group']), natural(row['specimen']),
                                        row['scope_name'].casefold(), row['type'], not row['enabled']))


def change_overrides(project, selected, action):
    """All-or-nothing edit; reject stale rows and conflicting re-enables."""
    if action not in ('disable', 'enable', 'remove') or not selected:
        raise ValueError('Choose overrides and a valid action first.')
    result = deepcopy(project)
    current = {entry['id']: entry for entry in override_entries(result)}
    seen = set()
    for saved in selected:
        ident = saved['id']
        entry = current.get(ident)
        if ident in seen or entry is None or entry['value'] != saved['value']:
            raise ValueError('Overrides changed since selection. Refresh this page and select them again.')
        seen.add(ident)
    for saved in selected:
        entry = current[saved['id']]
        kind, ident, enabled = entry['kind'], entry['specimen_id'], entry['enabled']
        block = result if entry['scope'] is None else next(
            g['definition'] for g in result['graphs'] if g['id'] == entry['scope'])
        source = block if enabled else block[DISABLED]
        if action == 'disable' and enabled:
            block.setdefault(DISABLED, {}).setdefault(kind, {})[ident] = source[kind].pop(ident)
        elif action == 'enable' and not enabled:
            # A newer explicit policy must not be silently overwritten/shadowed.
            conflicting = ('specimen_exclusions', 'specimen_data_modes') if entry['scope'] is None else GRAPH_KINDS
            if any(ident in block.get(other, {}) for other in conflicting) and kind in conflicting:
                raise ValueError('Another data-use policy is active for ' + ident + '. Disable or remove it first.')
            block.setdefault(kind, {})[ident] = source[kind].pop(ident)
        elif action == 'remove':
            source[kind].pop(ident)
        clear_disabled(block, (), ident)  # Drop empty parked containers only.
    return result
