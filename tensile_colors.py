"""Named, discrete chart palettes; no global style changes."""
from html import escape

DEFAULT_PALETTE = 'classic'
PALETTES = {
    'classic': ('Classic · existing colours',
                ('#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                 '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf')),
    # The requested reference is the pink/grey/olive/cyan end of the original cycle.
    'retro_reference': ('Retro Pop · reference colours',
                        ('#E377C2', '#7F7F7F', '#BCBD22', '#17BECF')),
    'retro_pop': ('Retro Pop · vivid',
                  ('#D64CA5', '#A4B514', '#00AFC4', '#4D70BD',
                   '#7555B8', '#E59A18', '#16836F', '#DA6855')),
    'citrus_ink': ('Citrus & Ink',
                   ('#9BAC0D', '#494078', '#EA6C38', '#12A9B8', '#CE4598', '#A66C32')),
    'orchid_teal': ('Orchid & Teal',
                    ('#B94CAE', '#15978D', '#C7A51B', '#5858AE', '#DB7540', '#A64760')),
    'jewel': ('Jewel · rich contrast',
              ('#146C94', '#AE3587', '#16936B', '#C98C12',
               '#6D46AB', '#D05240', '#4CA8BA', '#7C8030')),
    'candy': ('Candy · bright pastels',
              ('#E358AD', '#16AAC5', '#A2B928', '#9769D8',
               '#E69536', '#26A982', '#DC6461', '#5277C8')),
    'mineral': ('Mineral · pigment colours',
                ('#237E92', '#BF5948', '#AF9820', '#7953A0',
                 '#589544', '#D661A1', '#4471B0', '#975E2D')),
    'pastel_coastal': ('Pastel · Coastal',
                      ('#298CC6', '#E66A7B', '#12A58A', '#A36AD1',
                       '#C5A323', '#CE509F', '#719D31', '#B57542')),
    'pastel_orchard': ('Pastel · Orchard',
                      ('#70A13D', '#E18A40', '#9A62C6', '#C4AB22',
                       '#14A7B3', '#D95791', '#A76040', '#527CCE')),
    'pastel_berry': ('Pastel · Berry',
                    ('#CB489C', '#615BC2', '#10A9BE', '#E58B3D',
                     '#A27BCE', '#219870', '#AAB82A', '#BB5351')),
    'muted': ('Muted · stronger contrast',
              ('#377B9C', '#CF7938', '#549447', '#BF426A',
               '#8055A8', '#9B742F', '#36A99A', '#795044')),
    'vivid': ('Vivid · bold contrast',
              ('#1262B5', '#ED7820', '#18954C', '#D52C72',
               '#7443BF', '#ACAF0C', '#00A9BC', '#A64E24')),
    'earth': ('Earth · warm & natural',
              ('#B7542D', '#5A8732', '#B69D19', '#33798D',
               '#9E457D', '#80592C', '#149A80', '#D77B60')),
    'ocean': ('Ocean · blues & greens',
              ('#195788', '#00A4A0', '#6953B3', '#44822C',
               '#26A8D7', '#185C58', '#777DE0', '#71B34B')),
    'greyscale': ('Greyscale',
                  ('#252525', '#989898', '#505050', '#B8B8B8', '#747474', '#3B3B3B')),
}
PALETTE_OPTIONS = [(label, key) for key, (label, _) in PALETTES.items()]


def validate_palette(value):
    if not isinstance(value, str) or value not in PALETTES:
        raise ValueError('Choose one of the available chart colour palettes.')


def palette_colors(value=DEFAULT_PALETTE, classic_colors=None):
    validate_palette(value)
    if value == DEFAULT_PALETTE and classic_colors:
        return tuple(classic_colors)
    return PALETTES[value][1]


def group_color_map(default_colors, palette=DEFAULT_PALETTE, overrides=None):
    """Keep the existing all-groups order; explicit graph overrides always win."""
    from matplotlib.colors import to_hex
    validate_palette(palette)
    if palette == DEFAULT_PALETTE:
        colors = dict(default_colors)
    else:
        swatches = palette_colors(palette)
        colors = {group: swatches[i % len(swatches)] for i, group in enumerate(default_colors)}
    # A configured Matplotlib cycle may contain RGB tuples, not just CSS strings.
    return {group: to_hex(color) for group, color in {**colors, **(overrides or {})}.items()}


def palette_preview(palette, classic_colors=None):
    from matplotlib.colors import to_hex
    colors = tuple(to_hex(color) for color in palette_colors(palette, classic_colors))
    swatches = ''.join(
        '<span title="' + escape(color, quote=True) + '" aria-label="' + escape(color, quote=True)
        + '" style="display:inline-block;width:32px;height:19px;border:1px solid #0002;'
          'border-radius:4px;background:' + escape(color, quote=True) + '"></span>'
        for color in colors)
    return ('<div style="display:flex;flex-wrap:wrap;gap:5px;margin:5px 0">' + swatches + '</div>'
            '<div style="white-space:normal;line-height:1.4">'
            f'{len(colors)} colours, repeating for additional groups. '
            'Saved per graph; individual group overrides take priority. '
            'The YS/UTS/EL-by-sample chart keeps its separate property colours.</div>')
