"""Required location/count metadata. No curve analysis or inferred measurements."""
from copy import deepcopy
import math
import re

LOCATION = '__specimen_location__'
SPECIMEN_COUNT = '__specimen_count__'
LEGACY_NUMBER = '__specimen_number__'
REQUIRED_VARIABLES = {
    'group': {SPECIMEN_COUNT: {'name': 'Specimen count', 'unit': ''}},
    'specimen': {LOCATION: {'name': 'Location', 'unit': ''}},
}


def specimen_number(record):
    """Only an unambiguous operator number, never a CSV acquisition-row suffix."""
    label = str(record.get('specimen_label') or '').strip()
    match = re.fullmatch(r'(?:.*?[_\s-])?(\d+)', label)
    return int(match[1]) if match and '/' not in label else None


def whole_number(value):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and math.isfinite(value) and value == int(value))


def ensure_required_variables(project):
    """Upgrade the trial's Location column and references without duplicating it.

    Fractional legacy locations remain a separately named custom variable, so
    migration never rounds away a user's measurements or breaks their chart.
    """
    from tensile_moves import graph_blocks
    project = deepcopy(project)
    remaps = {'group': {}, 'specimen': {LEGACY_NUMBER: LOCATION}}
    for scope, required in REQUIRED_VARIABLES.items():
        variables = project.setdefault(scope + '_variables', {})
        for ident, definition in required.items():
            minimums = dict(variables.get(ident, {}).get('minimums', {})) if ident == SPECIMEN_COUNT else None
            values = dict(variables.get(ident, {}).get('values', {}))
            for old, variable in list(variables.items()):
                if old == ident or variable.get('name', '').strip().casefold() != definition['name'].casefold():
                    continue
                if any(not whole_number(v) for v in variable.get('values', {}).values()) or variable.get('unit', '').strip():
                    names = {v['name'] for v in variables.values()}
                    name, suffix = definition['name'] + ' (legacy)', 2
                    while name in names:
                        name = f'{definition["name"]} (legacy {suffix})'
                        suffix += 1
                    variable['name'] = name
                    continue
                values = {**variable.get('values', {}), **values}
                remaps[scope][old] = ident
                del variables[old]
            variables[ident] = {**definition, 'values': {
                key: int(value) if whole_number(value) else value for key, value in values.items()}}
            if minimums is not None:
                variables[ident]['minimums'] = minimums
            # Required columns always appear first, not after every custom column.
            project[scope + '_variables'] = variables = {ident: variables[ident], **variables}
    for graph in graph_blocks(project):
        settings = graph.get('settings', {})
        charts = [settings]
        for key in ('properties_by_group_variants', 'properties_by_specimen_variants'):
            charts.extend(v['settings'] for v in settings.get(key, []))
        for chart in charts:
            scope = chart.get('properties_by_group_level', 'group')
            key = 'properties_by_group_x_variable'
            if chart.get(key) in remaps.get(scope, {}):
                chart[key] = remaps[scope][chart[key]]
    return project


def reconcile_specimen_counts(project, imported_counts):
    """Raise missing/too-small counts; never lower a planned total on reload."""
    project = ensure_required_variables(project)
    values = project['group_variables'][SPECIMEN_COUNT]['values']
    minimums = project['group_variables'][SPECIMEN_COUNT]['minimums']
    for group, count in imported_counts.items():
        saved = values.get(group, 0)
        if not whole_number(saved) or saved < 0:
            raise ValueError('Specimen count must be a nonnegative whole number.')
        values[group] = max(int(saved), int(count))
        minimums[group] = int(count)
    return project


def location_values(variable, records):
    """Effective locations: automatic operator numbers plus explicit overrides."""
    from tensile_selection import specimen_id
    values = {specimen_id(r): number for r in records if (number := specimen_number(r)) is not None}
    values.update(variable.get('values', {}))
    return values
