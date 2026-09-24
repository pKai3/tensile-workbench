"""Categorical strength/elongation comparison from shared specimen properties."""
import textwrap
import numpy as np

GROUP_FAMILY = 'properties_by_group'
GROUP_LINE_STYLES = {'solid': '-', 'dash': '--', 'dot': ':', 'none': 'None'}
GROUP_DEFAULTS = {
    'properties_by_group_order': [],
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
    style = settings.get('properties_by_group_line_style', 'solid')
    if not isinstance(style, str) or style not in GROUP_LINE_STYLES:
        raise ValueError('Property-plot connecting lines must be solid, dash, dot or none.')
    labels = settings.get('properties_by_group_labels', {})
    if not isinstance(labels, dict) or any(not isinstance(group, str) or not group
                                         or not isinstance(label, str) for group, label in labels.items()):
        raise ValueError('Property-plot labels must map group names to label text.')


def wrap_group_label(label, width):
    """Wrap without truncating labels; preserve user-entered line breaks."""
    return '\n'.join(part for line in str(label).split('\n')
                     for part in (textwrap.wrap(line, max(1, int(width))) or ['']))


def fit_group_tick_labels(figure, axis, labels):
    """Fit full labels inside their actual categorical slots in static exports."""
    for _ in range(2):
        figure.canvas.draw()
        renderer = figure.canvas.get_renderer()
        slot = axis.get_window_extent(renderer).width / max(1, len(labels)) * .86
        wrapped_labels = []
        for label, tick in zip(labels, axis.get_xticklabels()):
            font = tick.get_fontproperties()
            width = 22
            text = wrap_group_label(label, width)
            while width > 1 and any(renderer.get_text_width_height_descent(line, font, ismath=False)[0] > slot
                                    for line in text.split('\n')):
                width -= 1
                text = wrap_group_label(label, width)
            wrapped_labels.append(text)
        axis.set_xticks(axis.get_xticks(), wrapped_labels)
        figure.tight_layout()


def ordered_groups(groups, preferred=()):
    """Keep selected identities in saved order; append newly selected groups."""
    selected = set(groups)
    return list(dict.fromkeys([g for g in preferred if g in selected] + list(groups)))


def render_group_properties(engine, records, state, *, out_path, show_individual=False,
                            ylim=None, name_overrides=None, title=None, preview=False,
                            fit_fractions=None, **_):
    """One mean per metric/group, independently counted; missing values leave gaps."""
    e = engine
    if fit_fractions is None:
        fit_fractions = e.LANDMARK_YIELD_FIT_FRACTIONS
    groups = ordered_groups(state['groups'], state.get('properties_by_group_order', []))
    validate_group_display(state)
    full_labels = [e.get_display_name(group, name_overrides) for group in groups]
    overrides = state.get('properties_by_group_labels', {})
    labels = [overrides.get(group, '').strip() or full for group, full in zip(groups, full_labels)]
    style = GROUP_LINE_STYLES[state.get('properties_by_group_line_style', 'solid')]
    figure, left = e.plt.subplots(figsize=e.PLOT_FIGSIZE)
    right = left.twinx()
    figure._tensile_group_plot = True
    positions = np.arange(len(groups), dtype=float)
    stats = {g: [(r, e.specimen_properties(r, fit_fractions)) for r in records.get(g, [])]
             for g in groups}
    metrics = [('Yield (MPa)', '0.2% YS', 'o', left, 'ys'),
               ('UTS (MPa)', 'UTS', '^', left, 'uts'),
               ('Failure elongation (%)', 'EL', 's', right, 'el')]
    handles, plotted = [], False
    errors = state.get('properties_by_group_error_bars', True)
    for field, label, marker, ax, key in metrics:
        color = state.get(f'properties_by_group_{key}_color', GROUP_DEFAULTS[f'properties_by_group_{key}_color'])
        means, deviations, counts = [], [], []
        for x, group in zip(positions, groups):
            valid = [(r, float(p.get(field, np.nan))) for r, p in stats[group]
                     if np.isfinite(p.get(field, np.nan))]
            values = np.array([v for _, v in valid])
            n = len(values)
            counts.append(n)
            means.append(float(np.mean(values)) if n else np.nan)
            deviations.append(float(np.std(values, ddof=1)) if n > 1 else np.nan)
            if n:
                plotted = True
                # Same automatic limits with and without individual points.
                ax.update_datalim(np.column_stack((np.full(n, x), values)))
                if show_individual:
                    names = e.scatter_specimen_labels([r for r, _ in valid])
                    for (_, value), name in zip(valid, names):
                        point, = ax.plot([x], [value], linestyle='None', marker=marker,
                                         color=color, alpha=.25, markersize=4)
                        point._tensile_hover_label = f'{group} · {name} · {label}'
            print(f'[GROUP PROPERTIES] {group}: {label}; n={n}; mean={means[-1]:.2f}')
        means, deviations = np.asarray(means, float), np.asarray(deviations, float)
        if errors and any(n > 1 for n in counts):
            bars = ax.errorbar(positions, means, yerr=deviations, marker=marker,
                               linestyle=style, color=color, markersize=6,
                               capsize=4, elinewidth=1.1, label='_nolegend_')
            line = bars.lines[0]
            line.set_label(label)
        else:
            line, = ax.plot(positions, means, marker=marker, linestyle=style,
                            color=color, markersize=6, label=label)
        line._tensile_counts = counts
        handles.append(line)
    if not plotted:
        e.plt.close(figure)
        return None
    for ax in (left, right):
        ax._tensile_category_labels = labels
        ax._tensile_category_hover_labels = [f'{group} · {full}' if group != full else group
                                             for group, full in zip(groups, full_labels)]
        ax.margins(y=.12)
    left.set_xticks(positions, [wrap_group_label(label, 22) for label in labels])
    left.set_xlim(-.5, len(groups) - .5)
    left.set(title=title or 'YS, UTS and elongation by sample', xlabel='Sample group', ylabel='Strength (MPa)')
    right.set_ylabel('Elongation at failure (%)')
    if ylim is not None:
        left.set_ylim(ylim)
    if state.get('properties_by_group_el_ylim') is not None:
        right.set_ylim(state['properties_by_group_el_ylim'])
    left.grid(True, linestyle='--', alpha=.4)
    right.grid(False)
    # A single compact legend outside the data, with room for the title.
    left.legend(handles, [line.get_label() for line in handles], loc='lower center',
                bbox_to_anchor=(.5, 1.01), ncol=3)
    left.set_title(left.get_title(), pad=38)
    fit_group_tick_labels(figure, left, labels)
    print('[PLOT INFO] Lines join categorical group means, not fitted trends. '
          'Each metric uses its available included specimens independently. '
          'EL uses Calc or the enabled gauge reconstruction; bars are ±1 sample SD.')
    return e.finish_plot(figure, out_path, preview)
