"""Lightweight, schematic plot choices; never load data or render real figures."""
from html import escape


SECTIONS = (
    ('Tensile response', ('landmark', 'pointwise', 'comparison', 'representative')),
    ('Work hardening', ('work_hardening_landmark', 'work_hardening', 'work_hardening_comparison')),
    ('Properties & trends', ('ys_vs_el', 'uts_vs_el', 'properties_by_group', 'properties_by_specimen')),
)

DESCRIPTIONS = {
    'landmark': ('Align curve stages to group landmarks.',
                 'Average specimen shapes after aligning yield, UTS and failure landmarks. The curve passes through the eligible group means.'),
    'pointwise': ('Average stress at each strain value.',
                  'Average the available specimen stresses on a common strain grid. Specimens contribute only where their curves have data.'),
    'comparison': ('Overlay landmark and pointwise averages.',
                   'Compare the two tensile averaging methods on the same axes. Averaging and axis settings stay linked to their individual plots.'),
    'representative': ('Show one chosen curve per group.',
                       'Compare representative specimens instead of averaging their shapes. Choose each specimen in Settings.'),
    'work_hardening_landmark': ('Differentiate the landmark average.',
                               'Calculate work hardening from the landmark-aligned mean curve, ending at mean uniform elongation.'),
    'work_hardening': ('Average specimen work-hardening curves.',
                       'Calculate each specimen’s work-hardening rate, then average on a common true plastic-strain grid.'),
    'work_hardening_comparison': ('Compare both work-hardening methods.',
                                 'Overlay mean specimen work hardening and the derivative of the landmark mean. Modulus and filter settings stay linked.'),
    'ys_vs_el': ('Compare yield strength and failure EL.',
                 'Plot group mean 0.2% yield strength against failure elongation, with optional specimen points and sample SD bars. Choose the mean population in Settings.'),
    'uts_vs_el': ('Compare ultimate strength and failure EL.',
                  'Plot group mean UTS against failure elongation, with optional specimen points and sample SD bars. Choose the mean population in Settings.'),
    'properties_by_group': ('Track group means against names or a variable.',
                            'Plot YS, UTS and EL against sample group names or a numeric custom variable. Add separate plot variants and choose the properties shown in Settings.'),
    'properties_by_specimen': ('Inspect specimen locations, one group per plot.',
                               'Show individual properties as grouped bars with optional trendlines. Choose sample groups and variants in Settings; untested locations remain visible.'),
}


def thumbnail(family):
    """Small inline vectors: a stable visual vocabulary, independent of data."""
    axes = '<path class="tw-sketch-axis" d="M14 8V68H116"/>'
    if family.startswith('work_hardening'):
        smooth = '<path class="tw-sketch-blue" d="M20 11C23 42 37 49 56 54S92 60 111 62"/>'
        original = '<path class="tw-sketch-orange" d="M20 11L24 30 28 37 32 34 36 46 41 43 47 51 53 49 60 56 67 54 75 59 83 57 93 62 104 60 112 63"/>'
        marks = smooth if family.endswith('landmark') else original
        if family.endswith('comparison'):
            marks = smooth + '<g stroke-dasharray="4 3">' + original + '</g>'
    elif family in ('ys_vs_el', 'uts_vs_el'):
        marks = '<text x="20" y="18" class="tw-sketch-label">' + ('YS' if family == 'ys_vs_el' else 'UTS') + '</text>'
        for x, y, color in ((37, 34, 'blue'), (64, 44, 'orange'), (96, 29, 'green')):
            marks += (f'<g class="tw-sketch-{color}"><path opacity=".55" d="M{x-12} {y}h24M{x} {y-10}v20"/>'
                      f'<path fill="currentColor" d="M{x} {y-4}l4 4-4 4-4-4Z"/></g>')
        marks += '<text x="102" y="81" class="tw-sketch-label">EL</text>'
    elif family == 'properties_by_group':
        axes += '<path class="tw-sketch-axis" d="M116 8V68"/>'
        marks = ''
        for color, points in (('blue', ((24, 55), (51, 46), (79, 42), (106, 24))),
                              ('orange', ((24, 40), (51, 34), (79, 24), (106, 15))),
                              ('green', ((24, 18), (51, 29), (79, 40), (106, 51)))):
            marks += f'<g class="tw-sketch-{color}"><polyline points="' + ' '.join(f'{x},{y}' for x, y in points) + '"/>'
            marks += ''.join(f'<circle cx="{x}" cy="{y}" r="2.4" fill="currentColor"/>' for x, y in points) + '</g>'
    elif family == 'properties_by_specimen':
        marks = ''
        for x, heights in ((26, (32, 42, 24)), (54, (38, 48, 31)), (82, (30, 40, 22))):
            for offset, color, height in zip((0, 7, 14), ('blue', 'orange', 'green'), heights):
                marks += f'<rect class="tw-sketch-{color}" x="{x+offset}" y="{68-height}" width="5" height="{height}" fill="currentColor" stroke="none"/>'
        marks += '<path class="tw-sketch-orange" stroke-dasharray="3 3" d="M22 30Q65 4 114 39"/>'
    else:
        mean = '<path class="tw-sketch-blue" d="M17 66C20 36 23 27 32 24C50 14 73 16 88 28L107 43"/>'
        alternate = '<path class="tw-sketch-orange" d="M17 66C21 36 24 30 34 27C55 17 76 20 92 35L112 48"/>'
        if family == 'comparison':
            marks = mean + '<g stroke-dasharray="4 3">' + alternate + '</g>'
        elif family == 'representative':
            marks = mean + alternate + '<path class="tw-sketch-green" d="M17 66C21 40 26 32 38 31C62 25 89 34 104 55"/>'
        else:
            marks = ('<g opacity=".2">' + alternate +
                     '<path class="tw-sketch-blue" d="M17 66C20 30 22 23 31 20C48 10 76 13 90 24L111 40"/></g>' + mean)
            if family == 'landmark':
                marks += ('<g class="tw-sketch-blue"><circle cx="32" cy="24" r="3" fill="var(--tw-panel-bg,white)"/>'
                          '<path d="M62 13l4 7h-8Z" fill="var(--tw-panel-bg,white)"/>'
                          '<path d="M103 39l8 8m0-8-8 8"/></g>')
    return ('<svg class="tw-plot-sketch" viewBox="0 0 128 84" aria-hidden="true" focusable="false" '
            'xmlns="http://www.w3.org/2000/svg"><g fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round">' + axes + marks + '</g></svg>')


class PlotPicker:
    def __init__(self, w, boxes, settings):
        self.boxes, self.settings, self.cards = boxes, settings, {}
        self.status = w.HTML()
        sections = [self.status]
        for heading, families in SECTIONS:
            cards = []
            for family in families:
                short, help_text = DESCRIPTIONS[family]
                checkbox = boxes[family]
                checkbox.tooltip = help_text
                checkbox.add_class('tw-plot-choice')
                sketch = w.HTML(thumbnail(family), layout=w.Layout(width='112px', flex='0 0 112px', margin='0'))
                summary = w.HTML('<div class="tw-plot-description">' + escape(short) + '</div>')
                heading_row = w.HBox([sketch, w.VBox([checkbox, summary],
                    layout=w.Layout(min_width='0', flex='1 1 0'))],
                    layout=w.Layout(width='100%', min_width='0', align_items='center', grid_gap='12px'))
                settings[family].set_title(0, '⚙ Settings')
                settings[family].add_class('tw-plot-card-settings')
                card = w.VBox([heading_row, settings[family]], layout=w.Layout(min_width='0', width='100%'))
                card.add_class('tw-plot-card')
                self.cards[family] = card
                checkbox.observe(lambda change, key=family: self._selected(key), names='value')
                settings[family].observe(lambda change, key=family: self._expanded(key), names='selected_index')
                cards.append(card)
            grid = w.GridBox(cards, layout=w.Layout(width='100%', min_width='0', grid_gap='12px',
                grid_template_columns='repeat(auto-fit, minmax(min(100%, 350px), 1fr))', align_items='flex-start'))
            sections.extend([w.HTML('<h4 class="tw-plot-section-title">' + escape(heading) + '</h4>'), grid])
        self.ui = w.VBox(sections, layout=w.Layout(width='100%', min_width='0'))
        self.ui.add_class('tw-plot-picker')
        for family in self.cards:
            self._selected(family)

    def _selected(self, family):
        card = self.cards[family]
        (card.add_class if self.boxes[family].value else card.remove_class)('tw-plot-selected')
        if not self.boxes[family].value:
            self.settings[family].selected_index = None
        count = sum(box.value for box in self.boxes.values())
        self.status.value = (f'<span class="tw-plot-count">{count} plot type' + ('s' if count != 1 else '') +
                             ' selected</span> · Tick a plot to include it. Open ⚙ Settings to customise it.')

    def _expanded(self, family):
        opened = self.settings[family].selected_index is not None
        card = self.cards[family]
        (card.add_class if opened else card.remove_class)('tw-plot-expanded')
        if opened:
            # Give the editor the full row and keep other settings compact.
            for other, settings in self.settings.items():
                if other != family:
                    settings.selected_index = None
