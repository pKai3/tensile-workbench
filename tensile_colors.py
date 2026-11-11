"""Named, discrete plot palettes; no global style changes."""
from html import escape

DEFAULT_PALETTE = 'classic'
COLOR_SLOTS = 'group_color_slots'
PALETTES = {
    'classic': ('Classic · existing colours',
                ('#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                 '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf')),
    # The requested reference is the pink/grey/olive/cyan end of the original cycle.
    'retro_reference': ('Retro Pop · reference colours',
                        ('#E377C2', '#7F7F7F', '#BCBD22', '#17BECF', '#5575C5',
                         '#EF8536', '#9061BC', '#269970', '#D44E63', '#CBA34B')),
    'retro_pop': ('Retro Pop · vivid',
                  ('#D64CA5', '#A4B514', '#00AFC4', '#4D70BD',
                   '#7555B8', '#E59A18', '#16836F', '#DA6855', '#60A144', '#A55370')),
    'citrus_ink': ('Citrus & Ink',
                   ('#9BAC0D', '#494078', '#EA6C38', '#12A9B8', '#CE4598', '#A66C32',
                    '#277CB3', '#218563', '#D9A323', '#AA4D60')),
    'orchid_teal': ('Orchid & Teal',
                    ('#B94CAE', '#15978D', '#C7A51B', '#5858AE', '#DB7540', '#A64760',
                     '#368FC2', '#789B34', '#805C37', '#DD77A3')),
    'jewel': ('Jewel · rich contrast',
              ('#146C94', '#AE3587', '#16936B', '#C98C12',
               '#6D46AB', '#D05240', '#4CA8BA', '#7C8030', '#354FA3', '#AA6436')),
    'candy': ('Candy · bright pastels',
              ('#E358AD', '#16AAC5', '#A2B928', '#9769D8',
               '#E69536', '#26A982', '#DC6461', '#5277C8', '#C5A047', '#A74F7C')),
    'mineral': ('Mineral · pigment colours',
                ('#237E92', '#BF5948', '#AF9820', '#7953A0',
                 '#589544', '#D661A1', '#4471B0', '#975E2D', '#1C9E85', '#B53E68')),
    'pastel_coastal': ('Pastel · Coastal',
                      ('#298CC6', '#E66A7B', '#12A58A', '#A36AD1',
                       '#C5A323', '#CE509F', '#719D31', '#B57542', '#4D60AD', '#DC873C')),
    'pastel_orchard': ('Pastel · Orchard',
                      ('#70A13D', '#E18A40', '#9A62C6', '#C4AB22',
                       '#14A7B3', '#D95791', '#A76040', '#527CCE', '#258569', '#C94E4B')),
    'pastel_berry': ('Pastel · Berry',
                    ('#CB489C', '#615BC2', '#10A9BE', '#E58B3D',
                     '#A27BCE', '#219870', '#AAB82A', '#BB5351', '#346DAD', '#B39529')),
    'muted': ('Muted · stronger contrast',
              ('#377B9C', '#CF7938', '#549447', '#BF426A',
               '#8055A8', '#9B742F', '#36A99A', '#795044', '#6672BE', '#B0A031')),
    'vivid': ('Vivid · bold contrast',
              ('#1262B5', '#ED7820', '#18954C', '#D52C72',
               '#7443BF', '#ACAF0C', '#00A9BC', '#A64E24', '#E44B3D', '#BA55BB')),
    'earth': ('Earth · warm & natural',
              ('#B7542D', '#5A8732', '#B69D19', '#33798D',
               '#9E457D', '#80592C', '#149A80', '#D77B60', '#6D62A0', '#8F9F59')),
    'ocean': ('Ocean · blues & greens',
              ('#195788', '#00A4A0', '#6953B3', '#44822C',
               '#26A8D7', '#185C58', '#777DE0', '#71B34B', '#458179', '#A5AF2E')),
    'greyscale': ('Greyscale',
                  ('#252525', '#989898', '#505050', '#B8B8B8', '#747474', '#3B3B3B',
                   '#858585', '#626262', '#A8A8A8', '#111111')),
}
PALETTE_OPTIONS = [(label, key) for key, (label, _) in PALETTES.items()]


def validate_palette(value):
    if not isinstance(value, str) or value not in PALETTES:
        raise ValueError('Choose one of the available plot colour palettes.')


def palette_colors(value=DEFAULT_PALETTE, classic_colors=None):
    validate_palette(value)
    if value == DEFAULT_PALETTE and classic_colors:
        from matplotlib.colors import to_hex
        colors = list(dict.fromkeys(to_hex(color) for color in classic_colors))
        for color in PALETTES[DEFAULT_PALETTE][1]:
            if len(colors) >= 10:
                break
            if color not in colors:
                colors.append(color)
        return tuple(colors)
    return PALETTES[value][1]


def validate_color_slots(slots):
    if not isinstance(slots, dict) or any(
            not isinstance(group, str) or not group or isinstance(slot, bool)
            or not isinstance(slot, int) or slot < 0 for group, slot in slots.items()):
        raise ValueError('Automatic group colours must map group names to nonnegative palette positions.')


def reconcile_color_slots(groups, previous=None, size=10):
    """Retain active colours, reclaim removed slots, and repair avoidable repeats."""
    previous = {} if previous is None else previous
    validate_color_slots(previous)
    groups = list(dict.fromkeys(groups))
    slots, used = {}, [0] * size
    for group in groups:
        if group in previous:
            slot = previous[group] % size
            if not used[slot]:
                slots[group] = slot
                used[slot] += 1
    for group in groups:
        if group not in slots:
            slot = min(range(size), key=used.__getitem__)
            slots[group] = slot
            used[slot] += 1
    return {group: slots[group] for group in groups}


def group_color_map(groups, palette=DEFAULT_PALETTE, overrides=None, *, slots=None, classic_colors=None):
    """Assign only active groups; explicit analysis overrides always win."""
    from matplotlib.colors import to_hex
    swatches = palette_colors(palette, classic_colors)
    slots = reconcile_color_slots(groups, slots, len(swatches))
    overrides = overrides or {}
    return {group: to_hex(overrides.get(group, swatches[slot])) for group, slot in slots.items()}


def palette_preview(palette, classic_colors=None):
    from matplotlib.colors import to_hex
    colors = tuple(to_hex(color) for color in palette_colors(palette, classic_colors))
    swatches = ''.join(
        '<span title="' + escape(color, quote=True) + '" aria-label="' + escape(color, quote=True)
        + '" style="display:inline-block;width:32px;height:19px;border:1px solid var(--tw-control-border,#0002);'
          'border-radius:4px;background:' + escape(color, quote=True) + '"></span>'
        for color in colors)
    explanation = (f'{len(colors)} colours. Only selected groups use a colour; removed groups free their colours for reuse. '
                   'Saved per analysis; group overrides take priority. YS/UTS/EL plots use their separate property colours.')
    return ('<div title="' + escape(explanation, quote=True)
            + '" style="display:flex;flex-wrap:wrap;gap:5px;margin:5px 0">' + swatches + '</div>')
