"""Reversible colours for interactive views; no analysis or export changes."""
from html import escape
import re

import numpy as np
from matplotlib.colors import to_rgba, to_hex


DARK_BACKGROUND = '#121c28'
DARK_TEXT = '#dce6ef'


def _luminance(rgb):
    linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in rgb]
    return sum(v * weight for v, weight in zip(linear, (.2126, .7152, .0722)))


def dark_color(value):
    """Keep hues, lifting only colours too dark to see on the plotting surface."""
    if isinstance(value, (list, tuple, np.ndarray)):
        return [dark_color(item) for item in value]
    if not isinstance(value, str):
        return value  # Numeric colour scales are not literal colours.
    match = re.fullmatch(r'rgba?\(([^)]+)\)', value)
    try:
        if match:
            parts = [float(part.strip()) for part in match[1].split(',')]
            rgb = [part / 255 for part in parts[:3]]
            alpha = parts[3] if len(parts) == 4 else 1.
        else:
            *rgb, alpha = to_rgba(value)
    except (ValueError, TypeError):
        return value
    background = _luminance(to_rgba(DARK_BACKGROUND)[:3])
    if (_luminance(rgb) + .05) / (background + .05) >= 4.5:
        return value
    # Small, deterministic adjustment of display colours only, preserving alpha.
    for step in range(1, 21):
        lifted = [v + (1 - v) * step / 20 for v in rgb]
        if (_luminance(lifted) + .05) / (background + .05) >= 4.5:
            break
    if alpha < 1:
        return 'rgba(' + ','.join(str(round(v * 255)) for v in lifted) + f',{alpha:g})'
    return to_hex(lifted)


def source_color(obj, field='color'):
    """Read the original colour, including after repeated theme switches."""
    current = getattr(obj, field)
    saved = getattr(obj, '_tw_display_colors', {}).get(field)
    return saved[0] if saved is not None and np.array_equal(current, saved[1]) else current


def _set_color(obj, field, value):
    original = source_color(obj, field)
    if not hasattr(obj, '_tw_display_colors'):
        obj._tw_display_colors = {}
    obj._tw_display_colors[field] = (original, value)
    setattr(obj, field, value)


def _surface(obj, field, value, dark):
    _set_color(obj, field, value if dark else source_color(obj, field))


def _ink(obj, field, dark, *, default=None):
    original = source_color(obj, field)
    value = dark_color(original) if original is not None else default
    _set_color(obj, field, value if dark else original)


def apply_plot_theme(figure, theme):
    """Update only style fields; retain ranges, visibility, data and edit handles."""
    dark = theme == 'dark'
    figure._tw_theme = theme
    with figure.batch_update():
        figure.layout.template = 'plotly_dark' if dark else 'plotly_white'
        layout = figure.layout
        for field in ('paper_bgcolor', 'plot_bgcolor'):
            _surface(layout, field, DARK_BACKGROUND, dark)
        _surface(layout.font, 'color', DARK_TEXT, dark)
        _surface(layout.title.font, 'color', DARK_TEXT, dark)
        _surface(layout.legend.font, 'color', DARK_TEXT, dark)
        _surface(layout.legend, 'bgcolor', DARK_BACKGROUND, dark)
        _surface(layout.legend, 'bordercolor', '#39495c', dark)
        _surface(layout.hoverlabel, 'bgcolor', '#172332', dark)
        _surface(layout.hoverlabel, 'bordercolor', '#94a5b8', dark)
        _surface(layout.hoverlabel.font, 'color', '#edf5fc', dark)
        _surface(layout.modebar, 'bgcolor', 'rgba(0,0,0,0)', dark)
        _surface(layout.modebar, 'color', '#94a5b8', dark)
        _surface(layout.modebar, 'activecolor', '#59d4cb', dark)
        for axis in (*figure.select_xaxes(), *figure.select_yaxes()):
            for field, value in (('color', DARK_TEXT), ('gridcolor', '#2b3746'),
                                 ('linecolor', '#94a5b8'), ('zerolinecolor', '#94a5b8')):
                _surface(axis, field, value, dark)
            _surface(axis.title.font, 'color', DARK_TEXT, dark)
            _surface(axis.tickfont, 'color', DARK_TEXT, dark)
        for trace in figure.data:
            if hasattr(trace, 'line'):
                _ink(trace.line, 'color', dark)
            if hasattr(trace, 'marker'):
                _ink(trace.marker, 'color', dark)
                _ink(trace.marker.line, 'color', dark)
            for name in ('error_x', 'error_y'):
                if hasattr(trace, name):
                    _ink(getattr(trace, name), 'color', dark, default=DARK_TEXT)
            if hasattr(trace, 'textfont'):
                _ink(trace.textfont, 'color', dark, default=DARK_TEXT)
            if hasattr(trace, 'fillcolor'):
                _ink(trace, 'fillcolor', dark)
        for shape in layout.shapes:
            _ink(shape.line, 'color', dark, default=DARK_TEXT)
            _ink(shape, 'fillcolor', dark)
        for annotation in layout.annotations:
            _ink(annotation.font, 'color', dark, default=DARK_TEXT)
            _ink(annotation, 'arrowcolor', dark, default=DARK_TEXT)


def swatch_style(color):
    """CSS variables keep external legend keys in sync without rebuilding widgets."""
    color = str(color or '#334155')
    return ('--tw-swatch-light:' + escape(color, quote=True) +
            ';--tw-swatch-dark:' + escape(str(dark_color(color)), quote=True))
