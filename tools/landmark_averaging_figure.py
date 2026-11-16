"""Draw a publication schematic of landmark averaging with synthetic curves.

No CSV files or saved analysis definitions are read. The group-anchoring step
calls the workbench's numerical function so the schematic follows its method.
"""

from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tensile_core import average_landmark_shapes

OUTPUT = ROOT / 'docs' / 'figures'
NAME = 'landmark_averaging_schematic'
COLORS = ('#28619A', '#D17A32', '#258B79')
SPECIMENS = (
    ((0., .65, 5.10, 11.80), (0., 315., 540., 290.)),
    ((0., .90, 6.30, 13.40), (0., 345., 575., 330.)),
    ((0., 1.15, 7.20, 15.10), (0., 370., 600., 360.)),
)


def specimen_stages(index, knots, landmarks, progress):
    """Sample three smooth synthetic stages at uneven measurement positions."""
    raw_x, raw_y, stages = [], [], []
    for stage in range(3):
        measured_progress = np.linspace(0., 1., 29) ** (1 + .12 * ((index + stage) % 3))
        if stage == 0:
            fraction = measured_progress + .025 * np.sin(np.pi * measured_progress)
        elif stage == 1:
            fraction = measured_progress ** (.76 + .05 * index)
        else:
            fraction = measured_progress ** (1.12 + .08 * index)
        x = knots[stage] + measured_progress * (knots[stage + 1] - knots[stage])
        y = landmarks[stage] + fraction * (landmarks[stage + 1] - landmarks[stage])
        raw_x.extend(x if stage == 0 else x[1:])
        raw_y.extend(y if stage == 0 else y[1:])
        grid = knots[stage] + progress * (knots[stage + 1] - knots[stage])
        stages.append(np.interp(grid, x, y))
    return np.asarray(raw_x), np.asarray(raw_y), np.asarray(stages)


def joined_progress(stages, progress):
    return (np.r_[progress, 1 + progress[1:], 2 + progress[1:]],
            np.r_[stages[0], stages[1, 1:], stages[2, 1:]])


def make_figure():
    plt.rcParams.update({
        'font.family': 'DejaVu Sans', 'font.size': 9,
        'svg.fonttype': 'none', 'axes.linewidth': .8,
    })
    progress = np.linspace(0., 1., 400)
    items, raw_curves = [], []
    for index, (strain_knots, stress_knots) in enumerate(SPECIMENS):
        knots = np.asarray(strain_knots)
        stresses = np.asarray(stress_knots)
        raw_x, raw_y, stages = specimen_stages(index, knots, stresses, progress)
        items.append((knots, stages, {}))
        raw_curves.append((raw_x, raw_y))

    shape_x, shape_y, shape_knots = average_landmark_shapes(items)
    mean_stages = np.mean([item[1] for item in items], axis=0)
    shape_stresses = np.array([mean_stages[0, 0], mean_stages[0, -1],
                               mean_stages[1, -1], mean_stages[2, -1]])
    # The deliberately offset YS/UTS/EL targets illustrate that eligible
    # property populations can differ from the full-curve shape population.
    target_knots = shape_knots + np.array([0., .17, .35, .62])
    target_stresses = shape_stresses + np.array([0., 12., 14., 0.])
    anchored_x, anchored_y, _ = average_landmark_shapes(
        items, target_knots, target_stresses)

    figure = plt.figure(figsize=(11.8, 4.0), facecolor='white')
    axes = figure.subplots(1, 3)
    figure.subplots_adjust(left=.067, right=.985, bottom=.205, top=.80, wspace=.23)
    figure.suptitle('Landmark-aligned tensile averaging', y=.965,
                    fontsize=13, fontweight='bold')
    titles = ('A   Specimen landmarks', 'B   Equal-progress averaging',
              'C   Group-anchored mean')
    for axis, title in zip(axes, titles):
        axis.set_title(title, loc='left', pad=13, fontsize=10, fontweight='bold')
        axis.set_ylim(0, 660)
        axis.grid(axis='y', color='#D9DFE5', linewidth=.65)
        axis.set_axisbelow(True)
        axis.spines[['top', 'right']].set_visible(False)
        axis.tick_params(axis='both', labelsize=8, length=3, color='#495562')
    axes[0].set_ylabel('Engineering stress (schematic)')
    for axis in axes[1:]:
        axis.tick_params(labelleft=False)

    first = axes[0]
    for index, ((x, y), (knots, stresses), color) in enumerate(
            zip(raw_curves, SPECIMENS, COLORS), start=1):
        first.plot(x, y, color=color, linewidth=1.75)
        first.plot(knots[1], stresses[1], 'o', color=color, markersize=4.8)
        first.plot(knots[2], stresses[2], '^', color=color, markersize=5.4)
        first.plot(knots[3], stresses[3], 'x', color=color, markersize=5.4,
                   markeredgewidth=1.5)
        first.text(knots[3] + .22, stresses[3], str(index), color=color,
                   fontsize=8, va='center')
    first.set_xlim(0, 16.5)
    first.set_xlabel('Engineering strain (schematic)')

    middle = axes[1]
    for boundary in (1, 2):
        middle.axvline(boundary, color='#B8C1CA', linestyle=':', linewidth=1)
    for item, color in zip(items, COLORS):
        x, y = joined_progress(item[1], progress)
        middle.plot(x, y, color=color, linewidth=1.5, alpha=.85)
    mean_progress, mean_stress = joined_progress(mean_stages, progress)
    middle.plot(mean_progress, mean_stress, color='#202B35', linewidth=2.3,
                linestyle=(0, (4, 2)), label='Equal-weight stage mean')
    middle.legend(loc='upper left', frameon=False, fontsize=8, handlelength=2.7)
    middle.set_xlim(0, 3)
    middle.set_xticks([0, 1, 2, 3], ['Start', 'YS', 'UTS', 'EL'])
    middle.set_xlabel('Normalised progress within each stage')

    last = axes[2]
    last.plot(shape_x, shape_y, color='#8D98A3', linewidth=1.7,
              linestyle=(0, (4, 2)), label='Shape-only mean')
    last.plot(anchored_x, anchored_y, color='#202B35', linewidth=2.6,
              label='Anchored mean')
    for index, (marker, label) in enumerate((('o', 'YS'), ('^', 'UTS'), ('x', 'EL')), start=1):
        last.plot(target_knots[index], target_stresses[index], marker,
                  color='#202B35', markersize=6, markeredgewidth=1.6)
        dx, dy = ((.24, -25) if label == 'YS' else
                  (.18, 15) if label == 'UTS' else (.25, 16))
        last.text(target_knots[index] + dx, target_stresses[index] + dy,
                  label, color='#202B35', fontsize=8, va='center')
    last.legend(loc='upper right', frameon=False, fontsize=8, handlelength=2.7)
    last.set_xlim(0, 16.5)
    last.set_xlabel('Engineering strain (schematic)')

    figure.text(.5, .055,
                'Synthetic schematic · equal-weight shape average; landmark property means may have different eligible populations',
                ha='center', va='center', fontsize=8, color='#687787')
    return figure


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    figure = make_figure()
    svg = OUTPUT / (NAME + '.svg')
    figure.savefig(svg, facecolor='white')
    # Matplotlib leaves spaces before newlines inside SVG path data.
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines()) + '\n')
    figure.savefig(OUTPUT / (NAME + '.png'), dpi=600, facecolor='white')
    plt.close(figure)


if __name__ == '__main__':
    main()
