"""Categorical strength/elongation comparison from shared specimen properties."""
import textwrap
import numpy as np

GROUP_FAMILY = 'properties_by_group'
GROUP_DEFAULTS = {
    'properties_by_group_order': [],
    'properties_by_group_ylim': None,
    'properties_by_group_el_ylim': None,
    'properties_by_group_error_bars': True,
    'properties_by_group_ys_color': '#1f77b4',
    'properties_by_group_uts_color': '#d95f02',
    'properties_by_group_el_color': '#2ca02c',
}


def ordered_groups(groups, preferred=()):
    """Keep selected identities in saved order; append newly selected groups."""
    selected = set(groups)
    return list(dict.fromkeys([g for g in preferred if g in selected] + list(groups)))


def render_group_properties(engine, records, state, *, out_path, show_individual=False,
                            ylim=None, name_overrides=None, title=None, preview=False,
                            fit_fractions=None, **_):
    """One mean per metric/group, independently counted; missing values leave gaps."""
    e = engine
    groups = ordered_groups(state['groups'], state.get('properties_by_group_order', []))
    labels = [e.get_display_name(group, name_overrides) for group in groups]
    figure, left = e.plt.subplots(figsize=e.PLOT_FIGSIZE)
    right = left.twinx()
    figure._tensile_group_plot = True
    positions = np.arange(len(groups), dtype=float)
    stats = {g: [(r, e.specimen_properties(r, fit_fractions)) for r in records.get(g, [])]
             for g in groups}
    metrics = [('Yield (MPa)', '0.2% YS', 'o', '-', left, 'ys'),
               ('UTS (MPa)', 'UTS', '^', '--', left, 'uts'),
               ('Failure elongation (%)', 'EL', 's', '-.', right, 'el')]
    handles, plotted = [], False
    errors = state.get('properties_by_group_error_bars', True)
    for field, label, marker, style, ax, key in metrics:
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
        ax.margins(y=.12)
    left.set_xticks(positions, ['\n'.join(textwrap.wrap(label, 22) or ['']) for label in labels])
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
    figure.tight_layout()
    print('[PLOT INFO] Lines join categorical group means, not fitted trends. '
          'Each metric uses its available included specimens independently. '
          'EL uses Calc or the enabled gauge reconstruction; bars are ±1 sample SD.')
    return e.finish_plot(figure, out_path, preview)
