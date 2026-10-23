"""Shared settings and validation without numerical, plotting or UI imports.

Startup and calculation code use the same validators. Checking a saved project
must not load the calculation stack or read specimen data.
"""
import math
import re

GROUP_FAMILY = 'properties_by_group'
GROUP_LINE_STYLES = {'solid': '-', 'dash': '--', 'dot': ':', 'none': 'None'}
GROUP_DEFAULTS = {
    'properties_by_group_x_variable': '',
    'properties_by_group_xlim': None,
    'properties_by_group_show_ys': True,
    'properties_by_group_show_uts': True,
    'properties_by_group_show_el': True,
    'properties_by_group_line_style': 'solid',
    'properties_by_group_labels': {},
    'properties_by_group_ylim': None,
    'properties_by_group_el_ylim': None,
    'properties_by_group_error_bars': True,
    'properties_by_group_ys_color': '#1f77b4',
    'properties_by_group_uts_color': '#d95f02',
    'properties_by_group_el_color': '#2ca02c',
}


def validate_group_display(settings):
    for key in ('xlim', 'ylim', 'el_ylim'):
        limits = settings.get('properties_by_group_' + key)
        if limits is not None and (not isinstance(limits, (tuple, list)) or len(limits) != 2
                or any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) for v in limits)
                or limits[0] >= limits[1]):
            raise ValueError('Property chart limits must be finite and increase from min to max.')
    for key in ('ys', 'uts', 'el'):
        color = settings.get(f'properties_by_group_{key}_color', GROUP_DEFAULTS[f'properties_by_group_{key}_color'])
        if not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
            raise ValueError('Property-plot colours must be six-digit hex colours.')
    if not isinstance(settings.get('properties_by_group_x_variable', ''), str):
        raise ValueError('The property-plot x-variable must be a saved variable ID.')
    for key in ('ys', 'uts', 'el'):
        if not isinstance(settings.get(f'properties_by_group_show_{key}', True), bool):
            raise ValueError('Property visibility must be on or off.')
    style = settings.get('properties_by_group_line_style', 'solid')
    if not isinstance(style, str) or style not in GROUP_LINE_STYLES:
        raise ValueError('Property-plot connecting lines must be solid, dash, dot or none.')
    if not isinstance(settings.get('properties_by_group_error_bars', True), bool):
        raise ValueError('Property error bars must be on or off.')
    labels = settings.get('properties_by_group_labels', {})
    if not isinstance(labels, dict) or any(not isinstance(group, str) or not group
                                         or not isinstance(label, str) for group, label in labels.items()):
        raise ValueError('Property-plot labels must map group names to label text.')


def validate_group_policy(policy):
    if not isinstance(policy, dict) or not isinstance(policy.get('enabled', False), bool):
        raise ValueError('Each group gauge setting needs an enabled on/off value.')
    target = policy.get('target_gauge_mm', 0)
    if (isinstance(target, bool) or not isinstance(target, (int, float)) or
            not math.isfinite(target) or target < 0 or (policy.get('enabled') and target <= 0)):
        raise ValueError('Enter a positive target gauge length before enabling a group.')
    return {'enabled': policy.get('enabled', False), 'target_gauge_mm': float(target)}


def validate_failure_override(override, *, saved=False):
    """A manual endpoint is an original measurement, never an invented stress."""
    if not isinstance(override, dict):
        raise ValueError('Failure EL override must specify a measurement row.')
    row = override.get('row')
    if isinstance(row, bool) or not isinstance(row, int) or row < 1:
        raise ValueError('Failure EL requires a positive original measurement row number.')
    if saved:
        if not isinstance(override.get('source_sha256'), str) or not re.fullmatch('[0-9a-f]{64}', override['source_sha256']):
            raise ValueError('Saved failure EL override requires a source fingerprint.')
        if not isinstance(override.get('reason'), str) or not override['reason'].strip() or len(override['reason']) > 2000:
            raise ValueError('Enter a short reason for the EL override (up to 2000 characters).')
        if not isinstance(override.get('saved_at'), str) or not override['saved_at']:
            raise ValueError('Saved failure EL override requires a timestamp.')
        if not isinstance(override.get('automatic_snapshot'), dict):
            raise ValueError('Saved failure EL override requires its automatic-result snapshot.')
    return override
