"""Lightweight, schematic plot choices; never load data or render real figures."""
from html import escape
from base64 import b64encode
import anywidget
from tensile_help import help_html
from tensile_popup import SettingsPopup


class CardClicks(anywidget.AnyWidget):
    """Forward card-body clicks to the existing checkbox; keep one selection state."""
    _esm = """
    export default {render({el}) {
      const click = event => {
        const card = event.target.closest('.tw-plot-card');
        if (!card || card.closest('.tw-plot-picker') !== el.closest('.tw-plot-picker')) return;
        if (event.defaultPrevented || event.button !== 0 ||
            event.target.closest('.tw-plot-card-settings,input,label,button,a,select,textarea') ||
            window.getSelection()?.type === 'Range') return;
        const checkbox = card.querySelector('.tw-plot-choice input[type="checkbox"]');
        if (checkbox && !checkbox.disabled) checkbox.click();
      };
      document.addEventListener('click', click);
      return () => document.removeEventListener('click',click);
    }};
    """


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
    if family == 'workspace_order':
        axes = ''
        marks = ('<path class="tw-sketch-blue" d="M28 24h56M28 42h42M28 60h56"/>'
                 '<path class="tw-sketch-orange" d="M105 18v48m-7-40 7-8 7 8m-14 32 7 8 7-8"/>'
                 '<g class="tw-sketch-green" fill="currentColor"><circle cx="16" cy="24" r="3"/>'
                 '<circle cx="16" cy="42" r="3"/><circle cx="16" cy="60" r="3"/></g>')
    elif family == 'workspace_variables':
        axes = ''
        marks = ('<path class="tw-sketch-blue" d="M14 12h100v60H14Zm0 18h100m-100 14h100m-100 14h100M48 12v60m33-60v60"/>'
                 '<path class="tw-sketch-orange" stroke-width="5" d="M23 21h16m18 0h15m18 0h15"/>')
    elif family == 'workspace_gauge':
        axes = ''
        marks = ('<path class="tw-sketch-blue" d="M12 26h22q10 0 15 10h30q5-10 15-10h22v32H94q-10 0-15-10H49q-5 10-15 10H12Z"/>'
                 '<path class="tw-sketch-green" d="M49 16v11m30-11v11M49 20h30m-24-4-6 4 6 4m18-8 6 4-6 4"/>'
                 '<path class="tw-sketch-orange" d="M37 65v12m54-12v12M37 72h54m-48-4-6 4 6 4m42-8 6 4-6 4"/>')
    elif family in ('display_static', 'display_interactive'):
        marks = ('<path class="tw-sketch-blue" d="M18 64Q24 27 36 24Q70 12 105 40"/>'
                 '<path class="tw-sketch-orange" stroke-dasharray="4 3" d="M18 64Q30 33 42 30Q75 21 109 49"/>')
        if family == 'display_static':
            marks += '<path class="tw-sketch-axis" d="M7 3H121V77H7Z"/>'
        else:
            marks += ('<path class="tw-sketch-green" fill="currentColor" d="M62 35l3 25 7-8 10 2Z"/>'
                      '<circle class="tw-sketch-orange" cx="102" cy="20" r="8"/>'
                      '<path class="tw-sketch-orange" d="M108 26l9 9M98 20h8m-4-4v8"/>')
    elif family == 'display_both':
        axes = '<path class="tw-sketch-axis" d="M9 11V68H57M70 11V68H119"/>'
        marks = ('<path class="tw-sketch-blue" d="M12 65Q16 23 25 25Q43 19 53 47"/>'
                 '<g class="tw-sketch-blue" opacity=".35"><path d="M73 65Q76 19 85 21Q102 15 115 44"/>'
                 '<path d="M73 65Q79 32 88 32Q105 25 117 54"/></g>'
                 '<path class="tw-sketch-blue" d="M73 65Q77 25 86 27Q104 21 116 49"/>')
    elif family == 'display_mean':
        marks = '<path class="tw-sketch-blue" d="M18 65Q23 29 33 24Q66 9 92 30L108 55"/>'
    elif family == 'display_individuals':
        marks = ('<g class="tw-sketch-blue" opacity=".5"><path d="M18 65Q20 21 31 19Q65 2 91 25L107 49"/>'
                 '<path d="M18 65Q26 38 39 35Q71 22 96 40L111 63"/></g>'
                 '<path class="tw-sketch-blue" stroke-width="3" d="M18 65Q23 29 33 24Q66 9 92 30L108 55"/>')
    elif family == 'detail_yield':
        marks = ('<path class="tw-sketch-blue" d="M18 65L65 24Q79 15 112 15"/>'
                 '<path class="tw-sketch-green" stroke-dasharray="4 3" d="M18 65L80 10"/>'
                 '<path class="tw-sketch-orange" stroke-dasharray="4 3" d="M43 65L99 15"/>'
                 '<circle class="tw-sketch-orange" cx="94" cy="16" r="3"/>')
    elif family == 'detail_failure':
        marks = ('<path class="tw-sketch-blue" d="M18 20Q62 21 81 30L86 61"/>'
                 '<path class="tw-sketch-orange" d="M77 26l8 8m0-8-8 8"/>')
    elif family == 'detail_full':
        marks = ('<path class="tw-sketch-blue" d="M18 65Q23 29 33 24Q66 9 92 30L98 63"/>'
                 '<circle class="tw-sketch-green" cx="33" cy="24" r="3"/>'
                 '<path class="tw-sketch-orange" d="M88 26l8 8m0-8-8 8"/>')
    elif family == 'review_aligned':
        marks = ('<path class="tw-sketch-blue" d="M17 66Q22 26 32 24Q62 2 86 26L107 43"/>'
                 '<path class="tw-sketch-orange" d="M17 66Q26 30 32 24Q62 10 86 26L107 43"/>'
                 '<path class="tw-sketch-green" d="M17 66Q19 25 32 24Q62 6 86 26L107 43"/>'
                 '<g class="tw-sketch-blue"><circle cx="32" cy="24" r="3"/>'
                 '<path d="M103 39l8 8m0-8-8 8"/></g>')
    elif family.startswith('work_hardening'):
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
        elif family in ('representative', 'review_measured'):
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


def review_selector_css(scope='tw-group-view-switch', families=('review_measured', 'review_aligned')):
    """Illustrate native toggle buttons without replacing their keyboard handling."""
    css = (f'.{scope} .jupyter-button {{min-height:60px;width:auto !important;flex:1 1 auto;margin:0;'
           'padding:8px 12px 8px 74px;background-position:6px center;background-repeat:no-repeat;'
           'background-size:62px 44px;white-space:normal;}'
           f'.{scope}>div {{display:flex;flex-wrap:wrap;gap:6px;}}'
           f'.{scope} {{height:auto;min-height:66px;max-width:100%;width:auto;}}')
    for index, family in enumerate(families, 1):
        svg = thumbnail(family).replace('<g fill=', '<style>.tw-sketch-axis{color:#8394a6;stroke-width:1}'
            '.tw-sketch-blue{color:#4295cf}.tw-sketch-orange{color:#db963e}'
            '.tw-sketch-green{color:#24ad8c}</style><g fill=', 1)
        uri = b64encode(svg.encode()).decode()
        css += f'.{scope} .jupyter-button:nth-child({index}) {{background-image:url("data:image/svg+xml;base64,{uri}");}}'
    return '<style>' + css + '</style>'


class PlotPicker:
    def __init__(self, w, boxes, settings):
        self.boxes, self.settings, self.cards = boxes, settings, {}
        self.status = w.HTML()
        self.clicks = CardClicks(layout=w.Layout(display='none'))
        self.popup = SettingsPopup(w, on_close=self._settings_closed, width='960px')
        self.settings_title, self.settings_close = self.popup.title, self.popup.done
        self.settings_close.tooltip = 'Close settings. Changes save automatically.'
        self.settings_body, self.settings_overlay = self.popup.body, self.popup.overlay
        self.settings_buttons = {}
        self._settings_family = None
        sections = [self.clicks, self.status]
        for heading, families in SECTIONS:
            cards = []
            for family in families:
                short, help_text = DESCRIPTIONS[family]
                checkbox = boxes[family]
                checkbox.tooltip = help_text
                checkbox.add_class('tw-plot-choice')
                sketch = w.HTML('<div title="' + escape(help_text, quote=True) + '">' + thumbnail(family) + '</div>', layout=w.Layout(width='112px', flex='0 0 112px', margin='0'))
                heading_row = w.HBox([sketch, w.VBox([checkbox],
                    layout=w.Layout(min_width='0', flex='1 1 0'))],
                    layout=w.Layout(width='100%', min_width='0', align_items='center', grid_gap='12px'))
                settings[family].add_class('tw-plot-card-settings')
                settings_button = w.Button(description='Settings', icon='cog', tooltip='Open settings for ' + checkbox.description,
                                           layout=w.Layout(width='auto', align_self='flex-end'))
                settings_button.add_class('tw-plot-settings-button')
                settings_button.on_click(lambda _, key=family: self.open_settings(key))
                self.settings_buttons[family] = settings_button
                card = w.VBox([heading_row, settings_button], layout=w.Layout(
                    min_width='0', width='100%', height='100%', justify_content='space-between'))
                card.add_class('tw-plot-card')
                self.cards[family] = card
                checkbox.observe(lambda change, key=family: self._selected(key), names='value')
                cards.append(card)
            # Every section uses the same column widths, including empty slots.
            # Cap at four columns, reducing the count below 350 px per card.
            grid = w.GridBox(cards, layout=w.Layout(width='100%', min_width='0', grid_gap='12px',
                grid_template_columns='repeat(auto-fill, minmax(min(100%, max(350px, calc((100% - 36px) / 4))), 1fr))',
                align_items='stretch'))
            sections.extend([w.HTML('<h4 class="tw-plot-section-title">' + escape(heading) + '</h4>'), grid])
        self.ui = w.VBox([*sections, self.popup.ui], layout=w.Layout(width='100%', min_width='0'))
        self.ui.add_class('tw-plot-picker')
        for family in self.cards:
            self._selected(family)

    def _selected(self, family):
        card = self.cards[family]
        (card.add_class if self.boxes[family].value else card.remove_class)('tw-plot-selected')
        if not self.boxes[family].value:
            self.settings[family].selected_index = None
            if self._settings_family == family:
                self.close_settings()
        self.settings_buttons[family].disabled = not self.boxes[family].value
        count = sum(box.value for box in self.boxes.values())
        self.status.value = (f'<span class="tw-plot-count">{count} plot type' + ('s' if count != 1 else '') +
                             ' selected</span>' + help_html('Selecting plots',
                             'Click a card to select or deselect it. Use its Settings gear to customise that plot. '
                             'Update plots generates the results; related plots share averaging and axis settings.'))

    def open_settings(self, family):
        if not self.boxes[family].value:
            return
        self._settings_family = family
        self.popup.open(self.boxes[family].description, self.settings[family].children)

    def close_settings(self):
        self.popup.close()

    def _settings_closed(self):
        self._settings_family = None
