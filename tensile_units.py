"""Explicit acquisition units. No magnitude-based guessing or true/engineering mixing."""
import re
import unicodedata
from tensile_columns import measurement_kind


class CurveImportError(ValueError):
    """A visible import failure, never an invented numerical result."""


def unit_key(unit):
    text = unicodedata.normalize('NFKC', str(unit or '')).casefold()
    return re.sub(r'[\s()^·]', '', text).replace('μ', 'u').replace('µ', 'u')


UNITS = {
    'stress': {'pa': 1e-6, 'kpa': .001, 'mpa': 1., 'gpa': 1000.,
               'n/mm2': 1., 'n/m2': 1e-6, 'psi': .006894757293168, 'ksi': 6.894757293168},
    'strain': {'%': 1., 'percent': 1., 'percent%': 1., 'mm/mm': 100., 'm/m': 100.,
               'in/in': 100., '1': 100., 'dimensionless': 100.,
               'ue': .0001, 'uε': .0001, 'microstrain': .0001},
    'time': {'s': 1., 'sec': 1., 'second': 1., 'seconds': 1., 'ms': .001,
             'min': 60., 'minutes': 60., 'h': 3600.},
}


def header_unit(column):
    match = re.search(r'[\[(]([^\])]+)[\])]\s*$', column)
    if not match or match[1].casefold().strip() == 'strain 1':
        return ''
    return match[1]


def conversion(column, units, kind):
    if re.search(r'\btrue\b', column, re.I):
        raise CurveImportError(f'{column}: true stress/strain cannot be analysed as engineering data.')
    declarations = [unit for unit in (units.get(column), header_unit(column)) if unit]
    if not declarations:
        raise CurveImportError(f'{column}: {kind} units are missing; add units to the header or units row.')
    scales = []
    for unit in declarations:
        scale = UNITS[kind].get(unit_key(unit))
        if scale is None:
            raise CurveImportError(f'{column}: unsupported {kind} unit "{unit}".')
        scales.append(scale)
    if any(scale != scales[0] for scale in scales):
        raise CurveImportError(f'{column}: header and units row disagree.')
    return scales[0]


def measurement_column(frame, kind):
    candidates = [c for c in frame.columns if measurement_kind(c) == kind]
    # An explicitly engineering channel wins over a simultaneous true channel.
    return next((c for c in candidates if not re.search(r'\btrue\b', c, re.I)),
                candidates[0] if candidates else None)
