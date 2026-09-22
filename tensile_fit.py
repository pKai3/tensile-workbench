"""Portable specimen-fit policy and validation (no numerical/UI dependencies)."""
import math
import re

DEFAULT_R2_WARNING = .98


def fit_display_places(field):
    """Precision exception for near-unity R² and small fit-strain intervals."""
    name = str(field).casefold().replace('²', '2')
    precise = (re.search(r'\br2\b', name) or any(label in name for label in
               ('fit lower strain', 'fit upper strain', 'yield strain', 'start strain', 'end strain')))
    return 5 if precise else 2


def validate_threshold(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError('R² warning threshold must be a finite number between 0 and 1.')
    return float(value)


def validate_override(override, *, saved=False):
    if not isinstance(override, dict) or override.get('mode') not in ('range', 'line'):
        raise ValueError('Fit override must use Manual range or Manual line.')
    bounds = override.get('strain_bounds')
    def finite(value):
        return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    if not isinstance(bounds, (list, tuple)) or len(bounds) != 2 or not all(map(finite, bounds)) or not bounds[0] < bounds[1]:
        raise ValueError('Fit strain bounds must be finite and increasing.')
    if override['mode'] == 'line':
        endpoints = override.get('endpoints')
        if (not isinstance(endpoints, (list, tuple)) or len(endpoints) != 2 or
                any(not isinstance(p, (list, tuple)) or len(p) != 2 or not all(map(finite, p)) for p in endpoints)):
            raise ValueError('Manual line requires two finite strain/stress endpoints.')
        if [p[0] for p in endpoints] != list(bounds) or endpoints[1][1] <= endpoints[0][1]:
            raise ValueError('Manual line must have increasing strain and positive slope.')
    if saved:
        if not isinstance(override.get('source_sha256'), str) or not re.fullmatch('[0-9a-f]{64}', override['source_sha256']):
            raise ValueError('Saved fit override requires a raw-source fingerprint.')
        if not isinstance(override.get('reason'), str) or not override['reason'].strip() or len(override['reason']) > 2000:
            raise ValueError('Enter a short reason for the fit override (up to 2000 characters).')
        if not isinstance(override.get('saved_at'), str) or not override['saved_at']:
            raise ValueError('Saved fit override requires a timestamp.')
        snapshot = override.get('automatic_snapshot')
        if not isinstance(snapshot, dict) or any(v is not None and not isinstance(v, str) and not finite(v) for v in snapshot.values()):
            raise ValueError('Saved fit override requires an automatic-result snapshot.')
    return override


def fit_policy(project):
    # Both specimen-level policies invalidate downstream calculation/plot caches.
    return {'yield_r2_warning': project.get('yield_r2_warning', DEFAULT_R2_WARNING),
            'specimen_fit_overrides': project.get('specimen_fit_overrides', {}),
            'specimen_failure_overrides': project.get('specimen_failure_overrides', {})}
