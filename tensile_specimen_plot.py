"""Individual-property/location plots; never pool specimens or fill missing tests."""
import re
from collections import Counter
import numpy as np

from tensile_selection import specimen_id
from tensile_order import ordered_groups
from tensile_variables import variable_label, property_chart_title, plot_text, validate_variables
from tensile_group_plot import fit_group_tick_labels, wrap_group_label
from tensile_settings import GROUP_DEFAULTS, validate_group_display, planned_positions, specimen_trend
from tensile_locations import LOCATION, LEGACY_NUMBER, specimen_number, location_values
from tensile_property_variants import SPECIMEN_FAMILY

SPECIMEN_NUMBER = LEGACY_NUMBER  # Read old direct/headless callers; no longer a second UI variable.


def specimen_sort_key(record):
    label = str(record.get('specimen_label') or record['sample'])
    return tuple((1, int(p)) if p.isdecimal() else (0, p.casefold())
                 for p in re.split(r'(\d+)', label))


def render_specimen_properties(engine, records, state, *, out_path, variables=None,
                               color_map=None, name_overrides=None, title=None,
                               preview=False, fit_fractions=None, xlim=None, ylim=None, specimen_counts=None, **_):
    """Grouped specimen bars and trends fitted to actual, unshifted locations."""
    e = engine
    validate_group_display(state)
    fit_fractions = fit_fractions or e.LANDMARK_YIELD_FIT_FRACTIONS
    groups = ordered_groups(sorted(state['groups']), state.get('group_order', []))
    if state.get('family') == SPECIMEN_FAMILY and len(groups) != 1:
        raise ValueError('Specimen charts require one sample group per figure.')
    rows = {g: sorted(records.get(g, []), key=specimen_sort_key) for g in groups}
    labels = {specimen_id(r): f'{e.get_display_name(g, name_overrides)} · {label}' for g, specimens in rows.items()
              for r, label in zip(specimens, e.scatter_specimen_labels(specimens))}
    variable_id = state.get('properties_by_group_x_variable', SPECIMEN_NUMBER)
    variable = None
    warnings = []
    if variable_id in (SPECIMEN_NUMBER, LOCATION):
        variable = dict(name='Location', unit='')
        values = location_values((variables or {}).get(LOCATION, {}),
                                 [r for specimens in rows.values() for r in specimens])
    elif variable_id:
        if variable_id not in (variables or {}):
            raise ValueError('The selected specimen variable is unavailable. Choose one in the plot settings.')
        variable = variables[variable_id]
        validate_variables({variable_id: variable}, scope='specimen')
        values = variable.get('values', {})
    else:
        values = {ident: float(i) for i, ident in enumerate(labels)}
    missing = [label for ident, label in labels.items() if ident not in values]
    if missing:
        warnings.append('Missing ' + variable_label(variable) + '; omitted from this chart: ' + ', '.join(missing) + '.')
    plotted_rows = {g: sorted((r for r in specimens if specimen_id(r) in values),
                             key=lambda r: values[specimen_id(r)]) for g, specimens in rows.items()}
    planned = planned_positions(state.get('properties_by_group_planned_positions', ''))
    if variable_id in (SPECIMEN_NUMBER, LOCATION):
        total = max(((specimen_counts or {}).get(group, 0) for group in groups), default=0)
        # Large specimen counts extend the domain without constructing millions
        # of ticks or pretending the untested positions are observations.
        if total > 0:
            planned = sorted(set(planned + (list(range(1, total + 1)) if total <= 40 else [1, total])))
    if planned and not variable_id:
        raise ValueError('Planned locations require a numeric x-axis, not specimen names.')
    domain = [values[specimen_id(r)] for specimens in plotted_rows.values() for r in specimens] + planned
    if not any(plotted_rows.values()):
        raise ValueError('No specimens have a usable location. Enter values under Custom variables → Individual specimens; '
                         'specimen numbers are taken only from unambiguous operator names, never CSV row numbers.')
    if any(len({values[specimen_id(r)] for r in specimens}) < len(specimens) for specimens in plotted_rows.values()):
        warnings.append('Some specimens share a location. They remain separate, with adjacent bars.')
    show = {k: state.get('properties_by_group_show_' + k, True) for k in ('ys', 'uts', 'el')}
    if not any(show.values()):
        raise ValueError('Turn on at least one property: YS, UTS or EL.')
    strength = show['ys'] or show['uts']
    # Side-by-side slots across both axes. Empty properties retain their slot;
    # duplicate locations get additional slots, never pooled observations.
    gaps = np.diff(sorted(set(domain)))
    spacing = float(min(gaps)) if len(gaps) else 1.0
    if variable_id in (SPECIMEN_NUMBER, LOCATION):
        spacing = min(spacing, 1.0)
    cluster_width = .78 * spacing
    slots = {key: i for i, key in enumerate(k for k, visible in show.items() if visible)}
    trend = specimen_trend(state)
    figure, left = e.plt.subplots(figsize=e.PLOT_FIGSIZE)
    right = left.twinx() if strength and show['el'] else left
    if variable_id in (SPECIMEN_NUMBER, LOCATION):
        for axis in (left, right):
            axis._tensile_x_places = 0
    figure._tensile_group_plot = True
    handles, plotted, missing_properties = [], False, set()
    multiple = sum(bool(v) for v in plotted_rows.values()) > 1
    metrics = [('Yield (MPa)', '0.2% YS', 'o', left, 'ys'),
               ('UTS (MPa)', 'UTS', '^', left, 'uts'),
               ('Failure elongation (%)', 'EL', 's', right, 'el')]
    for group, specimens in plotted_rows.items():
        if not specimens:
            continue
        properties = [e.specimen_properties(r, fit_fractions) for r in specimens]
        x = np.asarray([values[specimen_id(r)] for r in specimens], dtype=float)
        duplicates = Counter(x)
        occurrences = Counter()
        duplicate_slot = []
        for location in x:
            duplicate_slot.append(occurrences[location])
            occurrences[location] += 1
        width = cluster_width / (max(duplicates.values()) * len(slots))
        for field, name, marker, axis, key in metrics:
            if not show[key]:
                continue
            y = np.asarray([p.get(field, np.nan) for p in properties], dtype=float)
            missing_properties.update(labels[specimen_id(r)] + ' (' + name + ')'
                                      for r, value in zip(specimens, y) if not np.isfinite(value))
            valid = np.isfinite(y)
            plotted = plotted or bool(valid.any())
            label = (e.get_display_name(group, name_overrides) + ' · ' if multiple else '') + name
            color = ((color_map or {}).get(group) if multiple else
                     state.get(f'properties_by_group_{key}_color', GROUP_DEFAULTS[f'properties_by_group_{key}_color']))
            series = 'specimen-' + group + '-' + key
            if valid.any():
                centers = x + np.asarray([
                    (duplicate_slot[i] * len(slots) + slots[key] + .5
                     - duplicates[location] * len(slots) / 2) * width
                    for i, location in enumerate(x)])
                bars = axis.bar(centers[valid], y[valid], width=width * .92, color=color,
                                label=label, alpha=.85, zorder=2)
                bars._tensile_point_labels = [labels[specimen_id(r)] for r, keep in zip(specimens, valid) if keep]
                bars._tensile_locations = x[valid].tolist()
                bars._tensile_series_key = series
                bars._tensile_legend_rank = slots[key]
                handles.append(bars)
            if trend != 'none':
                if not variable_id:
                    warnings.append('Trendlines require a numeric x-axis; no fit drawn.')
                    continue
                degree = 1 if trend == 'linear' else 2
                fit_x, fit_y = x[valid], y[valid]
                if len(set(fit_x)) < degree + 1:
                    warnings.append(f'{label}: not enough distinct measured locations for a {trend} trendline.')
                    continue
                polynomial = np.polynomial.Polynomial.fit(fit_x, fit_y, degree)
                lo, hi = min(fit_x), max(fit_x)
                bounds = xlim if xlim is not None else (min(domain), max(domain))
                for start, end, extrapolated in ((max(bounds[0], lo), min(bounds[1], hi), False),
                                                 (bounds[0], min(lo, bounds[1]), True),
                                                 (max(hi, bounds[0]), bounds[1], True)):
                    if end <= start:
                        continue
                    trend_x = np.linspace(start, end, 100)
                    fit_line, = axis.plot(trend_x, polynomial(trend_x), color=color,
                                          linestyle=':' if extrapolated else '--', linewidth=1.8,
                                          label='_nolegend_', zorder=3)
                    fit_line._tensile_hover_label = label + (' extrapolation' if extrapolated else ' trendline')
                    fit_line._tensile_is_extrapolation = extrapolated
                    fit_line._tensile_series_key = series
    if not plotted:
        e.plt.close(figure)
        raise ValueError('No eligible values for the selected properties and specimens.')
    if missing_properties:
        warnings.append('Excluded or unavailable values omitted: ' + '; '.join(sorted(missing_properties)) + '.')
    if trend != 'none':
        warnings.append('Dashed: fitted trend within measured locations. Dotted: extrapolation beyond measurements, '
                        'not measured results or a validated prediction. Untested locations do not enter the fit.')
    figure._tensile_variable_warning = ' '.join(warnings)
    heading = plot_text(title) if title else property_chart_title(variable, [k for k in show if show[k]], scope='specimen')
    if state.get('family') == SPECIMEN_FAMILY:
        heading = plot_text(e.get_display_name(groups[0], name_overrides)) + ' · ' + heading
    left.set(xlabel=variable_label(variable, for_plot=True) if variable else 'Specimen',
             ylabel='Strength (MPa)' if strength else 'Elongation at failure (%)',
             title=heading)
    if show['el']:
        right.set_ylabel('Elongation at failure (%)')
        if state.get('properties_by_group_el_ylim') is not None:
            right.set_ylim(state['properties_by_group_el_ylim'])
    if strength and ylim is not None:
        left.set_ylim(ylim)
    for axis in figure.axes:
        axis.margins(y=.12)
    left.margins(x=.08)
    if variable_id:
        if variable_id in (SPECIMEN_NUMBER, LOCATION):
            from matplotlib.ticker import MaxNLocator, StrMethodFormatter
            left.xaxis.set_major_locator(MaxNLocator(integer=True))
            left.xaxis.set_major_formatter(StrMethodFormatter('{x:.0f}'))
        if planned and len(set(domain)) <= 40:
            left.set_xticks(sorted(set(domain)))
            left._tensile_numeric_ticks = sorted(set(domain))
        if xlim is not None:
            left.set_xlim(xlim)
        elif planned:
            low, high = min(domain), max(domain)
            pad = max((high - low) * .04, cluster_width / 2 + .1 * spacing, .2)
            left.set_xlim(low - pad, high + pad)
    else:
        names = list(labels.values())
        for axis in figure.axes:
            axis._tensile_category_labels = names
        left.set_xticks(list(values.values()), [wrap_group_label(label, 22) for label in names])
        left.set_xlim(-.5, len(names) - .5)
    left.grid(True, linestyle='--', alpha=.4)
    left.set_axisbelow(True)
    if right is not left:
        right.grid(False)
    left.legend(handles, [h.get_label() for h in handles], loc='lower center', bbox_to_anchor=(.5, 1.01), ncol=3)
    left.set_title(left.get_title(), pad=38)
    if variable_id:
        figure.tight_layout()
    else:
        fit_group_tick_labels(figure, left, list(labels.values()))
    print('[SPECIMEN PROPERTIES] Individual eligible values; no averaging, inferred missing tests or SD bars. '
          'Bars show measurements; trendlines fit actual locations, not the visual bar offsets. '
          'EL follows the group reconstruction setting.')
    return e.finish_plot(figure, out_path, preview)
