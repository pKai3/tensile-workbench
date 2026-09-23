"""On-demand specimen inspection and explicitly applied fit-override previews."""
from copy import deepcopy
from html import escape
from pathlib import Path

import numpy as np
from tensile_properties import specimen_calculation, elongation_report
from tensile_fit import fit_display_places
from tensile_fracture import (endpoint_available, automatic_fracture_endpoint, failure_measurements,
                              failure_row_for_strain, manual_failure_endpoint, fracture_curve,
                              ISO_DROP_RATIO, ISO_CONFIRM_FRACTION, ASTM_END_FRACTION,
                              RAPID_RATE_CONTRAST)
from tensile_gauge import gauge_record

# Stable display-layer IDs: visibility never changes measurements/calculations.
INSPECTOR_LAYERS = {
    'measured': ('Curves', True),
    'reconstructed': ('Curves', True),
    'yield_calc': ('Yield & fit', True),
    'yield_instron': ('Yield & fit', True),
    'fit_points': ('Yield & fit', 'yield'),
    'elastic_fit': ('Yield & fit', 'yield'),
    'offset': ('Yield & fit', 'yield'),
    'automatic_fit': ('Yield & fit', False),
    'manual_fit': ('Yield & fit', True),
    'uts': ('Peak', True),
    'fracture_calc': ('Fracture', True),
    'fracture_automatic': ('Fracture', True),
    'fracture_instron': ('Fracture', True),
    'fracture_reconstructed': ('Fracture', True),
    'peak_raw': ('Diagnostics', True),
    'csv_end': ('Diagnostics', False),
    'instron_ys_level': ('Diagnostics', False),
    'fracture_guide': ('Diagnostics', False),
}


def shape_layer(shape):
    name = shape.name or ''
    if name in ('fit-line', 'fit-range'):
        return 'manual_fit'
    return name.removeprefix('inspector:') if name.startswith('inspector:') else None


def layer_swatch(color, symbol=None, dash=None):
    """Small text/CSS key outside the Plotly canvas; no image assets needed."""
    color = escape(str(color or '#334155'), quote=True)
    if symbol:
        glyph = {'diamond-open': '◇', 'diamond': '◆', 'triangle-up-open': '△',
                 'circle-open': '○', 'circle': '●', 'x': '×'}.get(str(symbol), '●')
        return f'<span aria-hidden="true" style="color:{color};font:22px/24px Arial">{glyph}</span>'
    style = 'dotted' if dash == 'dot' else 'dashed' if dash and dash != 'solid' else 'solid'
    return f'<span aria-hidden="true" style="display:inline-block;width:25px;border-top:2px {style} {color}"></span>'


def inspection_ranges(calculation, mode='yield'):
    """Explicit reset ranges, independent of the publication plot settings."""
    x, y = calculation['strain_pct'], calculation['stress_mpa']
    if not len(x):
        return [0, 1], [0, 1]
    p = calculation['properties']
    left, right = min(0., float(x[0])), float(x[-1])
    if mode == 'yield':
        candidates = x[calculation['elastic_mask']].tolist()
        if np.isfinite(p['Yield strain (%)']):
            candidates.append(p['Yield strain (%)'])
        # With an unresolved yield, show the fit plus some material beyond it.
        right = min(right, max(candidates) * 1.3 + .2 if candidates else max(1., right * .15))
    span = max(right - left, .1)
    upper = max(1., float(np.max(y)))
    lower = min(0., float(np.min(y)))
    return [left - .02 * span, right + .04 * span], [lower - .03 * upper, upper * 1.12]


def overlay_ranges(payload, mode='yield', show_gauge=False):
    if mode == 'failure':
        return failure_detail_ranges(payload, show_gauge)
    xrange, yrange = inspection_ranges(payload['calculation'], mode)
    reported_el = payload['reference'].get('values', {}).get('el', np.nan)
    if mode == 'full' and np.isfinite(reported_el):
        padding = .04 * max(xrange[1] - xrange[0], .1)
        xrange = [min(xrange[0], reported_el - padding), max(xrange[1], reported_el + padding)]
    preview = payload.get('gauge_preview')
    if show_gauge and mode == 'full' and preview and preview['_gauge']['Gauge correction status'] == 'Applied':
        x = np.asarray(preview['strain_pct'])
        finite = x[np.isfinite(x)]
        if len(finite):
            left, right = min(xrange[0], float(finite.min())), max(xrange[1], float(finite.max()))
            padding = .04 * max(right - left, .1)
            xrange = [left, right + padding]
    return xrange, yrange


def failure_detail_ranges(payload, show_gauge=False):
    """Zoom around endpoint candidates and the recorded tail, without selecting EL."""
    calc = payload['calculation']
    acquisition = payload['record'].get('_acquisition', {})
    x = np.asarray(acquisition.get('strain', calc['strain_pct']), dtype=float)
    y = np.asarray(acquisition.get('stress', calc['stress_mpa']), dtype=float)
    valid = np.isfinite(x) & np.isfinite(y) & (x >= 0)
    if not valid.any():
        return inspection_ranges(calc, 'full')
    xs, ys = x[valid], y[valid]
    anchors = [float(xs[-1])]
    marker_stresses = []
    ends = [calc['fracture']]
    if payload['record'].get('_failure_override'):
        ends.append(automatic_fracture_endpoint(payload['record']))
    for endpoint in ends:
        if endpoint_available(endpoint):
            anchors.append(float(endpoint['strain_pct']))
            marker_stresses.append(float(endpoint['stress_mpa']))
    reported = payload['reference'].get('values', {}).get('el', np.nan)
    if np.isfinite(reported):
        anchors.append(float(reported))
    preview = payload.get('gauge_preview')
    if show_gauge and preview and preview['_gauge']['Gauge correction status'] == 'Applied':
        gx, gy = np.asarray(preview['strain_pct'], float), np.asarray(preview['stress_mpa'], float)
        usable = np.isfinite(gx) & np.isfinite(gy)
        xs, ys = np.concatenate([xs, gx[usable]]), np.concatenate([ys, gy[usable]])
        anchors.append(float(preview['_gauge']['Estimated failure elongation (%)']))
    # A little necking context, rather than a microscopic view of one point.
    padding = max(.05, .06 * float(np.ptp(x[valid])), .12 * (max(anchors) - min(anchors)))
    left, right = min(anchors) - padding, max(anchors) + padding
    local_y = ys[(xs >= left) & (xs <= right)]
    local_y = np.concatenate([local_y, np.asarray(marker_stresses, float)])
    local_y = local_y[np.isfinite(local_y)]
    if not len(local_y):
        return [left, right], inspection_ranges(calc, 'full')[1]
    low, high = float(local_y.min()), float(local_y.max())
    ypad = max(1., .08 * (high - low), .02 * abs(high))
    return [left, right], [low - ypad, high + ypad]


def instron_el_marker(payload):
    """Keep the reported value; tolerate printed-digit rounding at CSV bounds only."""
    reference = payload['reference']
    reported = reference.get('values', {}).get('el', np.nan)
    x = np.asarray(payload['calculation']['strain_pct'], float)
    result = {'reported': reported, 'strain': np.nan, 'snapped': False, 'tolerance': 0.}
    if not np.isfinite(reported) or not len(x):
        return result
    bound = float(np.clip(reported, x[0], x[-1]))
    precision = reference.get('resolution', {}).get('el', np.nan)
    tolerance = precision / 2 if np.isfinite(precision) and precision > 0 else 0.
    measured = payload['record'].get('_measured_record', payload['record'])
    acquisition = measured.get('_acquisition', {})
    raw_x = np.asarray(acquisition.get('strain', []), float)
    # check_resolution.el describes the original maximum strain, not a lower
    # bound or a truncated analysis endpoint. Never apply it to another bound.
    raw_precision = acquisition.get('check_resolution', {}).get('el', np.nan)
    if (reported > x[-1] and np.isfinite(raw_x).any() and bound == np.nanmax(raw_x)
            and np.isfinite(raw_precision) and raw_precision > 0):
        tolerance += raw_precision / 2
    tolerance += 64 * np.finfo(float).eps * max(1., abs(reported), abs(bound))
    result['tolerance'] = tolerance
    if abs(reported - bound) <= tolerance:
        result.update(strain=bound, snapped=bool(reported != bound))
    return result


def inspection_figure(payload, mode='yield', edit=None, show_gauge=False):
    """Plot original measurements and prepared fit points, never an averaged curve."""
    import plotly.graph_objects as go

    calculation = payload['calculation']
    x, y = calculation['strain_pct'], calculation['stress_mpa']
    p = calculation['properties']
    fig = go.Figure()

    def line(name, xs, ys, color, *, layer, **kwargs):
        places = 5 if mode in ('yield', 'failure') or INSPECTOR_LAYERS[layer][0] == 'Yield & fit' else 2
        fig.add_trace(go.Scatter(x=np.asarray(xs).tolist(), y=np.asarray(ys).tolist(),
            name=name, mode='lines', line=dict(color=color, **kwargs), meta={'inspector_layer': layer},
            hovertemplate=escape(name) + '<br>Strain: %{x:.' + str(places) + 'f}%<br>Stress: %{y:.2f} MPa<extra></extra>'))

    def points(name, xs, ys, color, symbol='circle', size=9, *, layer):
        places = 5 if mode in ('yield', 'failure') or INSPECTOR_LAYERS[layer][0] == 'Yield & fit' else 2
        fig.add_trace(go.Scatter(x=np.asarray(xs).tolist(), y=np.asarray(ys).tolist(),
            name=name, mode='markers', marker=dict(color=color, symbol=symbol, size=size), meta={'inspector_layer': layer},
            hovertemplate=escape(name) + '<br>Strain: %{x:.' + str(places) + 'f}%<br>Stress: %{y:.2f} MPa<extra></extra>'))

    acquisition = payload['record'].get('_acquisition', {})
    measured_x = np.asarray(acquisition.get('strain', x), float)
    measured_y = np.asarray(acquisition.get('stress', y), float)
    valid = np.isfinite(measured_x) & np.isfinite(measured_y)
    # Keep acquisition order, including repeated/reversing strain at collapse.
    # Fit points remain the prepared points used by the yield calculation.
    line('Measured CSV', np.where(valid, measured_x, np.nan), np.where(valid, measured_y, np.nan),
         '#334155', layer='measured', width=2)
    if show_gauge:
        preview = payload.get('gauge_preview')
        if preview and preview['_gauge']['Gauge correction status'] == 'Applied':
            target = preview['_gauge']['Target gauge length (mm)']
            line(f'Reconstruct ({target:.2f} mm)', preview['strain_pct'], preview['stress_mpa'], '#e76f00',
                 layer='reconstructed', dash='dash', width=2)
            points('Reconstruct EL', [preview['_gauge']['Estimated failure elongation (%)']],
                   [preview['_gauge']['Failure endpoint stress (MPa)']], '#e76f00', 'x', 12, layer='fracture_reconstructed')
    mask = calculation['elastic_mask']
    if mask.any():
        points('Fit points', x[mask], y[mask], '#16a085', size=6, layer='fit_points')
        fig.add_shape(type='rect', name='inspector:fit_points', x0=float(x[mask].min()), x1=float(x[mask].max()),
            y0=p['Fit lower stress (MPa)'], y1=p['Fit upper stress (MPa)'],
            fillcolor='rgba(22,160,133,0.10)', line_width=0, layer='below', editable=False)
    modulus = p['Fitted E (GPa)'] * 1000
    if np.isfinite(modulus) and modulus > 0:
        # Define the lines over the visible stress range, not to full fracture strain.
        stresses = np.array([0., max(1., p['UTS (MPa)']) * 1.10])
        strains = (stresses - p['Elastic intercept (MPa)']) / modulus * 100
        line('Elastic fit', strains, stresses, '#16a085', layer='elastic_fit', dash='dash', width=1.8)
        line('0.2% offset', strains + .2, stresses, '#d97706', layer='offset', dash='dash', width=1.8)
    automatic = calculation.get('automatic_calculation')
    if automatic and np.isfinite(automatic['properties']['Fitted E (GPa)']):
        ap = automatic['properties']
        stresses = np.array([0., max(1., p['UTS (MPa)'])])
        strains = (stresses - ap['Elastic intercept (MPa)']) / (ap['Fitted E (GPa)'] * 1000) * 100
        line('Automatic fit', strains, stresses, '#94a3b8', layer='automatic_fit', dash='dot', width=1.3)
    if p['Yield status'] == 'resolved':
        points('Calc YS', [p['Yield strain (%)']], [p['Yield (MPa)']], '#d97706', 'diamond', 12, layer='yield_calc')
    raw_peak = acquisition.get('peak')
    raw_peak_valid = (raw_peak is not None and np.isfinite(acquisition['strain'][raw_peak])
                      and np.isfinite(acquisition['stress'][raw_peak]))
    same_peak = False
    if calculation['uts_index'] is not None:
        peak = calculation['uts_index']
        same_peak = bool(raw_peak_valid and
            np.isclose(x[peak], acquisition['strain'][raw_peak], rtol=1e-9, atol=1e-9) and
            np.isclose(y[peak], acquisition['stress'][raw_peak], rtol=1e-9, atol=1e-9))
        peak_name = 'UTS / max force' if same_peak and acquisition.get('force_channel') else 'UTS / uniform EL'
        points(peak_name, [x[peak]], [y[peak]], '#2563eb', 'circle', 11, layer='uts')
        points('Max retained strain', [x[-1]], [y[-1]], '#94a3b8', 'circle-open', 8, layer='csv_end')
    if raw_peak_valid and not same_peak:
        name = 'Max force (original CSV)' if acquisition.get('force_channel') else 'Max stress (original CSV)'
        points(name, [acquisition['strain'][raw_peak]], [acquisition['stress'][raw_peak]],
               '#dc2626', 'triangle-up-open', 13, layer='peak_raw')
    fracture = calculation['fracture']
    if payload['record'].get('_failure_override'):
        automatic = automatic_fracture_endpoint(payload['record'])
        if endpoint_available(automatic):
            points('Automatic EL', [automatic['strain_pct']], [automatic['stress_mpa']],
                   '#64748b', 'circle-open', 12, layer='fracture_automatic')
    if endpoint_available(fracture):
        label = {'Estimated': 'Calc EL (needs review)', 'Manual': 'Calc EL (manual override)'}.get(fracture['status'], 'Calc EL')
        points(label, [fracture['strain_pct']],
               [fracture['stress_mpa']], '#9333ea', 'x', 12, layer='fracture_calc')
        fig.add_vline(x=fracture['strain_pct'], name='inspector:fracture_guide',
                      line_dash='dot', line_color='#9333ea', line_width=1)
    elif mode in ('full', 'failure'):
        fig.add_annotation(x=.02, y=.98, xref='paper', yref='paper', showarrow=False,
                           text='No supported EL endpoint — review the full curve',
                           xanchor='left', font=dict(color='#b45309'))
    reported = payload['reference'].get('values', {}).get('ys', np.nan)
    if np.isfinite(reported) and len(x):
        line('Instron YS level', [min(0., x[0]), x[-1]], [reported, reported],
             '#be185d', layer='instron_ys_level', dash='dot', width=1.8)
        # Instron supplies the yield stress here, not a yield strain. Locate
        # the first ascending crossing on the measured pre-UTS loading curve.
        peak = calculation['uts_index']
        crossings = np.flatnonzero((y[:-1] <= reported) & (y[1:] >= reported) & (np.diff(y) > 0))
        crossings = crossings[crossings < peak] if peak is not None else np.array([], dtype=int)
        if len(crossings):
            i = int(crossings[0])
            fraction = (reported - y[i]) / (y[i + 1] - y[i])
            strain_at_reported_ys = float(x[i] + fraction * (x[i + 1] - x[i]))
            fig.add_trace(go.Scatter(x=[strain_at_reported_ys], y=[float(reported)],
                name='Instron YS', mode='markers', meta={'inspector_layer': 'yield_instron'},
                marker=dict(color='#be185d', symbol='diamond-open', size=13, line=dict(width=2)),
                hovertemplate='Instron YS: %{y:.2f} MPa<br>CSV-interpolated strain: %{x:.5f}%'
                              '<br>First ascending pre-UTS crossing; strain is not an Instron yield result<extra></extra>'))
    el_marker = instron_el_marker(payload)
    reported_el = el_marker['reported']
    if np.isfinite(reported_el) and len(x):
        # Only x is supplied by Instron. Place it on the measured CSV curve;
        # do not call the interpolated y value an Instron fracture stress.
        if np.isfinite(el_marker['strain']):
            rounding_note = ('<br>Marker snapped to CSV boundary within printed-digit rounding tolerance'
                             '<br>Marker strain: %{x:.5f}%; imported EL is unchanged'
                             if el_marker['snapped'] else '')
            fig.add_trace(go.Scatter(x=[el_marker['strain']],
                y=[float(np.interp(el_marker['strain'], x, y))], customdata=[[float(reported_el)]],
                name='Instron EL', mode='markers', meta={'inspector_layer': 'fracture_instron'},
                marker=dict(color='#be185d', symbol='diamond-open', size=14, line=dict(width=2)),
                hovertemplate='Instron fracture EL: %{customdata[0]:.5f}%<br>CSV-interpolated stress: %{y:.2f} MPa'
                              + rounding_note + '<br>Stress is not an Instron break result<extra></extra>'))
        elif mode in ('full', 'failure'):
            fig.add_annotation(x=.02, y=.89, xref='paper', yref='paper', showarrow=False,
                text='Instron fracture EL outside CSV range beyond rounding tolerance — no marker extrapolated',
                xanchor='left', font=dict(color='#be185d'))
    if edit:
        if edit['mode'] == 'range':
            fig.add_shape(type='rect', name='fit-range', editable=True, x0=edit['strain_bounds'][0],
                x1=edit['strain_bounds'][1], y0=0, y1=1, yref='paper',
                line=dict(color='#7c3aed', width=3), fillcolor='rgba(124,58,237,.04)')
        else:
            (x0, y0), (x1, y1) = edit['endpoints']
            fig.add_shape(type='line', name='fit-line', editable=True, x0=x0, x1=x1, y0=y0, y1=y1,
                          line=dict(color='#7c3aed', width=4))
            points('Fit edit handles', [x0, x1], [y0, y1], '#7c3aed', 'circle-open', 12, layer='manual_fit')
    xrange, yrange = overlay_ranges(payload, mode, show_gauge)
    fig.update_layout(template='plotly_white', autosize=True, height=530, showlegend=False,
        margin=dict(l=82, r=25, t=22, b=88), font=dict(family='Arial, sans-serif', size=12),
        xaxis=dict(title=dict(text='Engineering strain (%)', standoff=18), range=xrange, automargin=True),
        yaxis=dict(title=dict(text='Engineering stress (MPa)', standoff=16), range=yrange, automargin=True),
        hovermode='closest', dragmode='zoom',
        activeshape=dict(fillcolor='rgba(124,58,237,.12)', opacity=.9))
    return fig


def fracture_detection_help():
    """Always accessible in the inspector, outside publication plots."""
    return f'''<details style="font:13px/1.5 Arial,sans-serif;margin:8px 0;white-space:normal">
      <summary style="cursor:pointer"><b>How failure elongation is selected</b></summary>
      <p><b>Calc EL</b> comes from the original recorded load sequence, independently of Instron’s
      reported EL. Force is preferred; engineering stress is a proxy when force is absent.
      No smoothing, strain sorting or work-hardening filters are used for detection.</p>
      <ol>
        <li><b>Sudden drop:</b> look after peak load for a drop between consecutive readings greater
          than {ISO_DROP_RATIO:g}× the preceding change in magnitude, confirmed by load subsequently
          falling below {100 * ISO_CONFIRM_FRACTION:g}% of peak. Select the strain immediately before
          the drop. This is based on ISO 6892-1:2019, informative Annex A.3.6.
          If the export ends before confirmation, a substantial supported drop can still supply a
          detected pre-drop endpoint. Missing 2% confirmation is recorded in the details, not treated
          as an endpoint error by itself; it is not called ISO-confirmed.</li>
        <li><b>Collapse spread over several readings:</b> a separate check looks for sustained rapid
          load loss across a short window and a local unloading-rate increase of more than
          {RAPID_RATE_CONTRAST:g}× its recent background. It selects the leading edge of the rapid fall,
          not the final reading. The 5% event-loss check applies to the combined fall, not to each
          individual step. An onset may initially be much slower than the fastest part of the fall.
          If a gradual accelerating lead-in precedes a distinct sharp collapse, select the start of
          that sharp transition. Also check that load loss per additional strain increases sharply:
          faster continued stretching alone must not turn progressive unloading into sudden fracture.
          This is an algorithmic detection, separate from ISO confirmation.</li>
        <li><b>No supported sudden drop:</b> select the reading immediately before load first falls
          below {100 * ASTM_END_FRACTION:g}% of peak, following the approach in ASTM E8/E8M-25 §7.11.3.4.
          This means {100 * ASTM_END_FRACTION:g}% <i>remaining</i>, not a {100 * ASTM_END_FRACTION:g}% reduction.
          A sudden-drop candidate without the {100 * ISO_CONFIRM_FRACTION:g}% confirmation is flagged for review.</li>
        <li><b>Progressive unloading in a truncated export:</b> when neither threshold is captured,
          substantial continuing load loss can support the final recorded measurement as a
          <b>terminal estimate</b>. It remains usable for EL, toughness and reconstruction, but needs
          review because actual separation is not established.</li>
        <li><b>Insufficient evidence:</b> an ordinary rising curve/plateau, missing required measurements
          or an acquisition gap does not justify using the final point. Review or override the endpoint.</li>
        <li><b>Manual override:</b> a saved, valid specimen-wide override takes precedence. Calc EL,
          toughness, tensile curves and gauge reconstruction all use that selected endpoint.</li>
      </ol>
      <p><b>Implementation safeguards:</b> reject noise-sized drops and substantial recovery before
      confirmation. The adjacent-reading rule ranks consecutive losses; the multi-reading check ranks
      sustained events and groups consecutive rapid increments into one leading edge.
      It also checks for a sharper consecutive-rate transition within an accelerating lead-in.
      When strain is available, the event's load loss per additional strain must exceed its local
      pre-event value by more than {RAPID_RATE_CONTRAST:g}×. A force fall with no additional strain
      supports a sharp collapse. An unusable pre-event strain baseline requires review.
      Stop searching for sudden drops at the first 10% crossing, excluding the unloaded tail.
      Post-crossing recovery requires review. See <i>Fracture detection details</i> below the chart for
      this specimen’s criterion, selected row and evidence.</p>
      <p><b>Review warnings</b> identify unresolved terminal estimates, unusable measurements or
      conflicting evidence. A clearly detected load collapse is not flagged simply because the export
      stopped before the standards confirmation threshold.</p>
      <p>This combines standards-derived criteria with application safeguards; it is <b>not a claim
      of full ASTM or ISO compliance</b>. Sampling, tracking errors and machine unloading can affect
      selection. Use <b>Failure detail</b> to review questionable results and adjust EL if needed.</p>
      <p>References: <a href="https://store.astm.org/e0008_e0008m-25.html" target="_blank" rel="noopener noreferrer">ASTM E8/E8M-25</a>,
      <a href="https://www.iso.org/standard/78322.html" target="_blank" rel="noopener noreferrer">ISO 6892-1:2019</a>.</p>
      <p>The <b>Instron EL</b> diamond is comparison-only. A value just outside the CSV range because
      of printed-digit rounding is displayed at the boundary; hover retains the imported value.
      Larger discrepancies are flagged, not extrapolated.</p>
    </details>'''


def gauge_model_help(expanded=False):
    """Settings/inspector help; plain HTML needs no MathJax or network."""
    return ('<details open>' if expanded else '<details>') + '''<summary>Gauge reconstruction: formula and assumptions</summary>
      <p>Define <b>r = L<sub>dots</sub> / L<sub>target</sub></b>.</p>
      <div class="tw-gauge-equations">
        <div>At or before maximum force: <b>ε<sub>est</sub> = ε<sub>measured</sub></b></div>
        <div>After maximum force: <b>ε<sub>est</sub> = ε<sub>u</sub> +
          r (ε<sub>measured</sub> − ε<sub>u</sub>)</b></div>
        <div>At the selected failure endpoint: <b>ε<sub>f,est</sub> = ε<sub>u</sub> +
          r (ε<sub>f,measured</sub> − ε<sub>u</sub>)</b></div>
        <div>Post-peak extension (mm): <b>ΔL<sub>post</sub> = L<sub>dots</sub>
          (ε<sub>f,measured</sub> − ε<sub>u</sub>) / 100</b>, with strain expressed in %.</div>
      </div>
      <p><b>L<sub>dots</sub></b> is this specimen’s initial AVE dot spacing, imported from
      <i>Strain 1 gauge length</i>; <b>L<sub>target</sub></b> is the saved target for its group.
      Both lengths are in mm. <b>ε<sub>u</sub></b> is total engineering strain at the original
      maximum-force reading. All strains use the same engineering-strain definition and are
      expressed in percent, including the elastic component. The breakpoint is applied by
      acquisition order, not by testing whether a strain value exceeds ε<sub>u</sub>.
      Maximum engineering stress is used as a recorded proxy only if no force channel exists.</p>
      <p><b>Example:</b> 10% strain at peak force, 18% measured failure strain, 50 mm dots
      and a 25 mm target give 10 + (50 / 25) × (18 − 10) = <b>26%</b>.</p>
      <p><b>Assumptions and limits</b></p>
      <ul>
        <li>Deformation before maximum force is assumed approximately uniform, so the
          uniform-strain component is not rescaled.</li>
        <li>Both gauges are assumed to contain the same neck/fracture region. The model
          assigns all measured post-peak extension to the neck-centred target gauge.</li>
        <li>Continued deformation and elastic unloading outside the target gauge cannot
          be separated from this single gauge history. For targets longer than the AVE
          spacing, additional post-peak extension outside the measured interval is not recovered.</li>
        <li>The endpoint is selected in acquisition order: before a supported sudden load collapse,
          otherwise immediately before load falls below 10% of peak. Clear collapses can be detected
          without recorded ISO confirmation; truncated progressive unloading can use a review-flagged
          terminal estimate. A valid manual selection takes
          precedence. This is not Instron’s break result or a post-fracture gauge measurement.
          With no supported endpoint, EL and reconstruction are unavailable. See the inspector’s
          <i>How failure elongation is selected</i> explanation for criteria and limits.</li>
        <li>Stress values stay unchanged throughout. Reconstructed toughness is the area
          under the estimated engineering curve, not a newly measured material property.</li>
      </ul>
      <p>This is a derived estimate, not a standards-compliant measurement. If the original
      video or spatial-strain data are available, reprocessing with the correct virtual gauge
      is preferable.</p>
    </details>'''


def inspection_checks(payload, *, preview=False):
    """The same failure-only checks as the specimen table, visible above the plot."""
    from tensile_tables import specimen_check_failures
    gauge = (payload.get('gauge_preview') or {}).get('_gauge') if payload.get('gauge_policy', {}).get('enabled') else None
    failures = specimen_check_failures(payload['calculation']['properties'], payload['reference'], gauge)
    if not failures:
        return ''
    title = 'Specimen checks' + (' · unsaved preview' if preview else '')
    return ('<div role="status" style="font:13px/1.5 Arial,sans-serif;white-space:normal;'
            'overflow-wrap:anywhere;padding:8px 12px;background:#fff4dc;border-left:3px solid #d97706">'
            '<b>' + title + '</b><div style="white-space:pre-line">' + escape(failures) + '</div></div>')


def inspection_summary(payload):
    """Display fit provenance and available Instron values without inventing matches."""
    calculation, reference = payload['calculation'], payload['reference']
    p, values = calculation['properties'], reference.get('values', {})

    def number(value, places=2):
        return f'{value:.{places}f}' if np.isfinite(value) else '—'

    def row_number(value):
        return str(int(value)) if np.isfinite(value) else '—'

    metrics = [('0.2% YS (MPa)', 'Yield (MPa)', 'ys'),
               ('UTS (MPa)', 'UTS (MPa)', 'uts'),
               ('Uniform elongation (%)', 'Uniform elongation (%)', 'uniform'),
               ('Fitted E (GPa)', 'Fitted E (GPa)', 'e')]
    result = ['<style>.tw-inspect-summary{font:13px/1.5 Arial,sans-serif;white-space:normal;overflow-wrap:anywhere}'
              '.tw-inspect-summary table{border-collapse:collapse;width:100%;max-width:850px}'
              '.tw-inspect-summary th,.tw-inspect-summary td{padding:6px 12px;border-bottom:1px solid #dce3e9;text-align:right}'
              '.tw-inspect-summary th:first-child,.tw-inspect-summary td:first-child{text-align:left}'
              '.tw-inspect-summary th{background:#e8eef4}.tw-inspect-summary details{margin:8px 0;padding:0 8px;border:1px solid #dce3e9;border-radius:3px}'
              '.tw-inspect-summary summary{cursor:pointer;padding:8px 0;font-weight:600}'
              '.tw-gauge-equations{padding:10px 12px;background:#f2f6fa;border-radius:5px;line-height:1.8}'
              '.tw-inspect-summary li{margin:5px 0}'
              '.tw-inspect-warning{padding:8px;background:#fff4dc;border-left:3px solid #d97706}</style>',
              '<div class="tw-inspect-summary">',
              '<details><summary>Specimen identity and inclusion</summary>',
              '<p><b>' + escape(payload['group'] + ' · ' + (reference.get('label') or payload['sample'])) + '</b> · ' +
              ('Included in this graph' if payload['included'] else 'Excluded from this graph') + '</p>']
    result.append('<p>Inclusion: ' + ('explicit override for this graph' if payload.get('selection_scope') == 'graph'
                                    else 'inherited from the global default') + '.</p>')
    if reference.get('label'):
        result.append('<p>Operator specimen/location label: <b>' + escape(reference['label']) + '</b></p>')
    result.append('<p><b>CSV:</b> ' + escape(Path(payload['source_file']).name) +
                  ' · <b>Assigned Instron row:</b> ' + escape(str(reference.get('index') if reference.get('source') else 'Unavailable')) +
                  '<br><b>Summary:</b> ' + escape('; '.join(Path(path).name for path in
                    reference.get('source', '').split('; ') if path) or 'Unavailable') + '</p>')
    if payload.get('exclusion_reason'):
        result.append('<p>Exclusion reason: ' + escape(payload['exclusion_reason']) + '</p>')
    result.append('</details><details><summary>Calculated and Instron properties</summary>')
    show_automatic = bool(calculation.get('automatic_calculation'))
    result.append('<p><b>Fit method: ' + escape(p.get('Fit method', 'Automatic')) + '</b> · ' +
                  escape(p.get('Override status', 'None')) + '</p>')
    result.append('<table><thead><tr><th>Property</th><th>Calculated</th>' +
                  ('<th>Automatic</th>' if show_automatic else '') + '<th>Instron</th>'
                  '<th>Δ (Calc − Instron)</th></tr></thead><tbody>')
    for label, field, key in metrics:
        calculated, reported = p[field], values.get(key, np.nan)
        auto = calculation['automatic_calculation']['properties'][field] if show_automatic else np.nan
        result.append('<tr><td>' + escape(label) + '</td><td>' + number(calculated) + '</td>' +
                      ('<td>' + number(auto) + '</td>' if show_automatic else '') + '<td>' +
                      number(reported) + '</td><td>' + number(calculated - reported) + '</td></tr>')
    result.append('</tbody></table><p>Δ uses the displayed units; elongation differences are percentage points. '
                  'Instron YS has a hollow diamond at the first ascending pre-UTS '
                  'CSV crossing of that stress. The marker strain is interpolated from CSV, not supplied by Instron. '
                  'Its horizontal stress reference is available under Diagnostics and shown by default '
                  'if no crossing exists.</p></details>')
    active_record = (payload.get('gauge_preview') if payload.get('gauge_policy', {}).get('enabled') else None)
    el = elongation_report(active_record or payload['record'], reference, p)
    result.append('<details><summary>Elongation sources and endpoint selection</summary><table><tr><th>Quantity</th><th>Strain (%)</th><th>Source</th></tr>')
    for label, key, description in (
            ('Instron summary EL', 'Instron summary EL (%)', 'Imported Instron Strain 1 at break result.'),
            ('Last valid CSV strain', 'Last valid CSV strain (%)', 'Last finite strain in original acquisition order, not necessarily fracture.'),
            ('Max retained CSV strain', 'CSV endpoint EL (%)', 'Maximum strain after preparation; audit only, not used as fracture EL.'),
            ('Calc EL', 'CSV-derived fracture EL (%)', el['Fracture endpoint kind'] or 'No supported endpoint.'),
            ('Reconstructed EL', 'Reconstructed EL (%)', 'Gauge reconstruction of the selected Calc endpoint; blank unless enabled and available.')):
        result.append('<tr><td>' + escape(label) + '</td><td>' + number(el[key]) + '</td><td>' + escape(description) + '</td></tr>')
    result.append('</table><p>These endpoint definitions are distinct. EL is not used to verify specimen identity, '
                  'and differences from the Instron break result do not trigger a matching failure. '
                  'The magenta hollow diamond shows Instron fracture EL on the measured CSV curve. Its strain is '
                  'imported from Instron; its stress is interpolated from CSV, not an Instron fracture-stress result. '
                  'Only a boundary discrepancy within printed-digit rounding tolerance is snapped to the CSV boundary; '
                  'the imported value is retained in the table and hover. Larger discrepancies are not extrapolated.</p>')
    el_marker = instron_el_marker(payload)
    if el_marker['snapped']:
        result.append('<p>Instron EL marker snapped to ' + number(el_marker['strain'], 5) +
                      '% for display (imported ' + number(el_marker['reported'], 5) + '%; rounding tolerance ±' +
                      number(el_marker['tolerance'], 5) + ' percentage points). No measurement was changed.</p>')
    result.append('<p><b>Endpoint selection: ' + escape(el['Fracture detection status']) + '</b>' +
                  (': ' + escape(el['Fracture detection reason']) if el['Fracture detection reason'] else '') +
                  '. The purple cross marks the selected measurement. No strain-grid interpolation or landmark shape setback '
                  'is subtracted from reported EL.</p>')
    result.append('<details><summary>Fracture detection details</summary><p>' + escape(el['Fracture EL method']) +
                  '.</p><p><b>Criterion:</b> ' + escape(el['Fracture criterion'] or 'None met') +
                  '<br>Signal: ' + escape(el['Fracture load signal']) + '; comparison: ' +
                  escape(el['Fracture rate basis']) + '. Selected consecutive load loss: ' +
                  number(el['Fracture detected load loss (%)']) + '% of peak.</p>')
    if el['Fracture detection status'] in ('Detected', 'Estimated', 'Manual'):
        result.append('<p>Selected measurement row: ' +
                      row_number(el['Fracture bracket first row (1-based)']) + '; following row (if recorded): ' +
                      row_number(el['Fracture bracket second row (1-based)']) +
                      '; time: ' + number(el['Fracture endpoint time (s)']) + ' s.</p>')
    if el['Fracture detection status'] != 'Manual':
        result.append('<p>Below-10% reading: ' + row_number(el['Fracture below-10% row (1-based)']) +
                      '; below-2% confirmation reading: ' + row_number(el['Fracture confirmation row (1-based)']) +
                      '. Consecutive-drop ratio: ' + number(el['Fracture observed consecutive-drop ratio']) +
                      '; noise floor: ' + number(el['Fracture noise floor (% of peak)'], 5) + '% of peak.</p>')
    if np.isfinite(el['Fracture multi-reading event loss (% of peak)']):
        result.append('<p><b>Multi-reading event:</b> sustained loss ' +
                      number(el['Fracture multi-reading event loss (% of peak)']) + '% of peak; supporting window ' +
                      row_number(el['Fracture multi-reading event window (rows)']) + ' readings. Rate basis: ' +
                      escape(el['Fracture event rate basis']) + '. Leading edge selected from the original readings.</p>')
        strain_contrast = el['Fracture load/strain rate contrast']
        result.append('<p>Strain-shape check: ' + escape(el['Fracture strain-shape check']) + '. ' +
                      ('No additional strain across the force-loss window.' if np.isinf(strain_contrast) else
                       'Load loss per additional strain / local background: ' + number(strain_contrast) + '×.') + '</p>')
    if el['Fracture detection notes']:
        result.append('<p>' + escape(el['Fracture detection notes']) + '</p>')
    result.append('<p>EL selection: <b>' + escape(el['EL selection']) + '</b>. Automatic EL: ' +
                  number(el['Automatic EL (%)']) + '% (' + escape(el['Automatic EL status']) + '). ' +
                  escape(el['Automatic EL criterion']) + '.</p>')
    if el['EL override reason']:
        result.append('<p>Override reason: ' + escape(el['EL override reason']) +
                      '<br>Saved: ' + escape(el['EL override saved at']) + '</p>')
    result.append('</details></details>')
    if reference.get('check_values'):
        result.append('<details><summary>Original CSV ↔ Instron verification values</summary><table>')
        for label, value in reference['check_values'].items():
            result.append('<tr><td>' + escape(label) + '</td><td>' + number(value) + '</td></tr>')
        result.append('</table><p>Name verification uses dataset/export row or an exact label, not numerical similarity. '
                      'UTS uses maximum engineering stress from the original CSV. EL is not checked for matching '
                      'because Instron break EL and CSV endpoints have different definitions. '
                      'UTS tolerance is half the last printed unit from each CSV plus a floating-point allowance. '
                      'No smoothing, yield fit or gauge reconstruction is used.</p></details>')
    acquisition_note = ''
    preview = payload.get('gauge_preview')
    if preview:
        audit = preview['_gauge']
        enabled = payload.get('gauge_policy', {}).get('enabled', False)
        result.append('<details><summary>Gauge reconstruction</summary>')
        result.append('<p><b>Gauge reconstruction for this group: ' + ('on' if enabled else 'off — preview only') + '</b>. '
                      'The calculations and Instron comparison above remain measured. Overlaying a curve does not apply it.</p>')
        result.append('<table><tr><th>AVE dot spacing (mm)</th><th>Group target (mm)</th><th>Ratio</th></tr>'
                      '<tr><td>' + number(audit['AVE dot spacing (mm)']) + '</td><td>' +
                      number(audit['Target gauge length (mm)']) + '</td><td>' + number(audit['Gauge ratio']) + '</td></tr></table>')
        result.append('<table><tr><th>Property</th><th>Measured</th><th>Reconstructed' +
                      ('' if enabled else ' (preview only)') + '</th></tr>')
        for label, raw_key, estimated_key in (
                ('CSV-derived fracture EL (%)', 'Failure elongation (%)', 'Estimated failure elongation (%)'),
                ('Tensile toughness (MJ/m³)', 'Toughness (MJ/m^3)', 'Estimated toughness (MJ/m^3)')):
            result.append('<tr><td>' + label + '</td><td>' + number(p[raw_key]) + '</td><td>' + number(audit[estimated_key]) + '</td></tr>')
        result.append('</table><p>Derived localisation model, not a standards-compliant measurement. '
                      'Pre-peak strain is unchanged; stress values are unchanged throughout.</p>')
        result.append(gauge_model_help())
        if audit['Gauge correction status'] != 'Applied':
            result.append('<p class="tw-inspect-warning"><b>Overlay unavailable:</b> ' + escape(audit['Gauge correction status']) +
                          '. Set and save a target under Gauge reconstruction · per sample group.</p>')
        for key in ('Gauge model warning', 'Gauge reconstruction notes'):
            if audit.get(key):
                result.append('<p class="tw-inspect-warning">' + escape(audit[key]) + '</p>')
        result.append('</details>')
        acquisition = payload['record'].get('_acquisition', {})
        peak = acquisition.get('peak')
        if peak is not None:
            acquisition_note = ('<p>' + escape(acquisition['peak_basis']) + f': original measurement row {peak + 1}, '
                          + 'time ' + number(acquisition['time'][peak]) + ' s, strain ' + number(acquisition['strain'][peak]) + '%. '
                          'Peak comes from the original acquisition, independently of plotting cleanup.</p>')
    result.append('<details><summary>Elastic fit and calculation details</summary>')
    if p['Yield status'] != 'resolved' or p['Notes']:
        result.append('<p class="tw-inspect-warning"><b>Yield ' + escape(p['Yield status']) + ':</b> ' +
                      escape(p['Notes']) + '</p>')
    low, high = calculation['fit_fractions']
    description = (f'Automatic elastic fit: {100 * low:.2f}–{100 * high:.2f}% of this specimen’s UTS'
                   if p.get('Fit method', 'Automatic') == 'Automatic' else
                   f'{p["Fit method"]}: {number(p["Fit lower strain (%)"], 5)}–{number(p["Fit upper strain (%)"], 5)}% strain')
    result.append(f'<p>{description}, before the first UTS point '
                  f'({number(p["Fit lower stress (MPa)"])}–{number(p["Fit upper stress (MPa)"])} MPa); '
                  f'<b>{int(calculation["elastic_mask"].sum())} selected points</b>. '
                  f'R² = {number(p["Elastic fit R2"], 5)}; intercept = {number(p["Elastic intercept (MPa)"])} MPa. '
                  'This fitted E is independent of the WH modulus.</p>')
    result.append(f'<p>Review threshold: R² &lt; {calculation.get("r2_threshold", .98):.5f}. '
                  'Checks use full precision, before display rounding. '
                  'A high R² alone does not establish that a region is elastic.</p>')
    if p.get('Fit method') == 'Manual line':
        result.append('<p>Manual line is not a least-squares fit. R² measures residual agreement with the selected '
                      'data points between the endpoint strains and can be negative.</p>')
    saved = calculation.get('saved_override') or {}
    if saved.get('saved_at'):
        result.append('<p>Override saved: ' + escape(saved['saved_at']) + ' · ' + escape(saved.get('reason', '')) + '</p>')
        original = saved.get('automatic_snapshot', {})
        result.append('<details><summary>Automatic result when this override was applied</summary><p>' +
                      '<br>'.join(escape(str(k)) + ': ' + escape(number(v, fit_display_places(k)) if isinstance(v, (int, float))
                                  else str(v) if v is not None else 'Unavailable')
                                  for k, v in original.items()) + '</p></details>')
    bracket = calculation['yield_bracket']
    if bracket is not None:
        xs = calculation['strain_pct'][list(bracket)]
        result.append(f'<p>0.2% YS is interpolated between {xs[0]:.5f}% and {xs[1]:.5f}% strain, '
                      'at the first eligible crossing after the elastic-fit region and before UTS.</p>')
    result.append('<p>Uniform elongation uses the first maximum engineering stress. Tensile plots, fracture EL and '
                  'toughness use the selected CSV endpoint, or its reconstruction when enabled. Missing detection '
                  'is not replaced unconditionally by a final reading or an Instron result. Supported estimates '
                  'remain review-flagged; pre-peak calculations remain available.</p></details>')
    result.append('<details><summary>Source and preparation details</summary>' + acquisition_note + '<p>Source: ' +
                  escape(payload['source_file']) + '</p><p>SHA256: ' + escape(payload.get('source_sha256', '')) +
                  '</p><p>The measured line preserves original acquisition order. Elastic-fit points use the '
                  'existing property preparation: finite pairs sorted by strain, with the maximum stress retained '
                  'for repeated strain values. Fracture detection uses the original load sequence. '
                  'No WH filters, averaging, extrapolation or landmark alignment are applied.</p><p>Instron match: ' +
                  escape(reference.get('status', 'Unavailable')) + '. ' + escape(reference.get('notes', '')) +
                  '</p><p>Instron source: ' + escape(reference.get('source', '') or 'Unavailable') +
                  '</p></details></div>')
    return ''.join(result)


class SpecimenInspector:
    """Create one disposable interactive figure only when a specimen is selected."""
    def __init__(self, widgets, loader=None, on_apply=None, on_failure_apply=None):
        self.w, self.loader = widgets, loader
        self.on_apply = on_apply
        self.on_failure_apply = on_failure_apply
        self._failure_sync, self._failure_draft = False, None
        self._painting, self._editing, self._draft = False, False, None
        self._updating, self._payload, self.chart, self._probe = False, None, None, None
        self._layer_choices, self._layer_widgets = {}, []
        w = widgets
        self.choice = w.Dropdown(description='Specimen:', options=[('Choose a specimen…', '')],
                                 layout=w.Layout(width='min(100%, 720px)'))
        self.previous = w.Button(description='Previous', layout=w.Layout(width='95px'), disabled=True)
        self.next = w.Button(description='Next', layout=w.Layout(width='75px'), disabled=True)
        self.view = w.ToggleButtons(options=[('Yield detail', 'yield'), ('Failure detail', 'failure'),
                                            ('Full curve', 'full')], value='yield')
        self.reset = w.Button(description='Reset zoom', layout=w.Layout(width='110px'))
        self.gauge_overlay = w.Checkbox(description='Overlay measured / reconstructed', value=False, indent=False,
                                       layout=w.Layout(width='auto'))
        self.gauge_status = w.HTML()
        self.checks = w.HTML(layout=w.Layout(width='100%', min_width='0', display='none'))
        self.status = w.HTML('Click a specimen name in the Specimens table, or choose one above.')
        self.summary = w.HTML(layout=w.Layout(width='100%', min_width='0'))
        self.chart_box = w.VBox(layout=w.Layout(width='100%', min_width='0'))
        self.layer_groups = w.HBox(layout=w.Layout(width='100%', min_width='0',
                                                  flex_flow='row wrap', grid_gap='10px', align_items='flex-start'))
        self.reset_layers = w.Button(description='Reset shown items', layout=w.Layout(width='auto'),
                                     tooltip='Restore the display defaults for this view; calculations are unchanged.')
        layer_heading = w.HTML('<style>.tw-inspector-layer.widget-checkbox {height:auto;min-height:28px}'
                               '.tw-inspector-layer.widget-checkbox label {white-space:normal;line-height:1.3;'
                               'height:auto;min-width:0}</style>'
                               '<b>Show on plot</b> · display only; tick items to show or hide them.')
        self.layers_panel = w.VBox([
            w.HBox([layer_heading, self.reset_layers], layout=w.Layout(flex_flow='row wrap', grid_gap='12px', align_items='center')),
            self.layer_groups,
        ], layout=w.Layout(width='100%', min_width='0', display='none', padding='8px 0 16px 0'))
        self.mode = w.Dropdown(description='Fit:', options=[('Inspect saved fit', 'inspect'),
            ('Manual range', 'range'), ('Manual line', 'line')], value='inspect', layout=w.Layout(width='300px'))
        self.x0 = w.FloatText(description='Start strain (%)', continuous_update=False, style={'description_width': 'initial'})
        self.x1 = w.FloatText(description='End strain (%)', continuous_update=False, style={'description_width': 'initial'})
        self.y0 = w.FloatText(description='Start stress (MPa)', continuous_update=False, style={'description_width': 'initial'})
        self.y1 = w.FloatText(description='End stress (MPa)', continuous_update=False, style={'description_width': 'initial'})
        self.fit_pick = w.ToggleButtons(options=[('Not picking', ''), ('Set start', 'start'), ('Set end', 'end')],
                                        value='', description='Click curve:', style={'description_width': 'initial'})
        self.fit_pick_hint = w.HTML('Choose Set start or Set end, then click a measured point. '
            'Manual range takes strain only; Manual line takes strain and stress. '
            'Start advances to End; after End, picking stops. Nothing is saved until Apply.')
        self.line_fields = w.HBox([self.y0, self.y1], layout=w.Layout(flex_flow='row wrap', display='none'))
        self.reason = w.Text(description='Reason:', placeholder='Why is the fit being adjusted?', continuous_update=True,
                             layout=w.Layout(width='min(100%, 800px)'))
        self.apply_button = w.Button(description='Apply override · all graphs', button_style='primary',
                                     layout=w.Layout(width='auto'), disabled=True)
        self.cancel_button = w.Button(description='Cancel preview', disabled=True)
        self.restore_button = w.Button(description='Restore automatic fit', layout=w.Layout(width='auto'), disabled=True)
        self.edit_status = w.HTML('Select a specimen to review or adjust its elastic fit.')
        self.editor = w.Accordion(children=[w.VBox([self.mode, self.fit_pick, self.fit_pick_hint,
            w.HBox([self.x0, self.x1], layout=w.Layout(flex_flow='row wrap')), self.line_fields, self.reason,
            w.HBox([self.apply_button, self.cancel_button, self.restore_button], layout=w.Layout(flex_flow='row wrap')),
            self.edit_status])], selected_index=None)
        self.editor.set_title(0, 'Adjust elastic fit · preview before applying')
        self.failure_enabled = w.Checkbox(description='Edit failure EL', value=False, indent=False)
        self.failure_el = w.FloatText(description='Failure EL (%)', continuous_update=False,
                                     style={'description_width': 'initial'})
        self.failure_row = w.BoundedIntText(value=1, min=1, max=1, description='Measurement row',
                                            continuous_update=False, style={'description_width': 'initial'})
        self.failure_reason = w.Text(description='Reason:', placeholder='Why is the endpoint being adjusted?',
                                     layout=w.Layout(width='min(100%, 800px)'))
        self.failure_apply = w.Button(description='Apply EL override · all graphs', button_style='primary',
                                      layout=w.Layout(width='auto'), disabled=True)
        self.failure_cancel = w.Button(description='Cancel EL preview', layout=w.Layout(width='auto'), disabled=True)
        self.failure_restore = w.Button(description='Restore automatic EL', layout=w.Layout(width='auto'), disabled=True)
        self.failure_status = w.HTML('Select a specimen to adjust failure elongation.')
        self.failure_editor = w.Accordion(children=[w.VBox([
            w.HTML('Enter measured EL (%) or click the measured curve while editing. EL snaps to a recorded '
                   'post-peak point; the row selector distinguishes repeated strain readings. '
                   'Choose the endpoint before any unwanted fracture/unloading tail. '
                   'Reconstruction is applied afterwards; do not enter reconstructed EL here.'),
            self.failure_enabled, w.HBox([self.failure_el, self.failure_row], layout=w.Layout(flex_flow='row wrap')),
            self.failure_reason, w.HBox([self.failure_apply, self.failure_cancel, self.failure_restore],
                                       layout=w.Layout(flex_flow='row wrap')), self.failure_status])], selected_index=None)
        self.failure_editor.set_title(0, 'Adjust failure elongation · preview before applying')
        self.layers_dropdown = w.Accordion(children=[self.layers_panel], selected_index=None)
        self.layers_dropdown.set_title(0, 'Show on plot · display items')
        self.details_panel = w.Accordion(children=[w.VBox([
            self.layers_dropdown, self.editor, self.failure_editor,
            self.summary, w.HTML(fracture_detection_help()),
        ], layout=w.Layout(width='100%', min_width='0'))], selected_index=None,
            layout=w.Layout(width='100%', min_width='0'))
        self.details_panel.set_title(0, 'Inspector controls and calculation details')
        self.ui = w.VBox([w.HBox([self.choice, self.previous, self.next],
                                layout=w.Layout(flex_flow='row wrap', grid_gap='6px')),
                          self.status,
                          w.HBox([self.view, self.reset, self.gauge_overlay], layout=w.Layout(flex_flow='row wrap')),
                          self.gauge_status, self.checks, self.chart_box, self.details_panel], layout=w.Layout(width='100%', min_width='0'))
        self.choice.observe(self._selected, names='value')
        self.view.observe(self._view_changed, names='value')
        self.reset.on_click(lambda _: self._reset_zoom())
        self.reset_layers.on_click(self._reset_layers)
        self.gauge_overlay.observe(self._overlay_changed, names='value')
        self.previous.on_click(lambda _: self._step(-1))
        self.next.on_click(lambda _: self._step(1))
        self.mode.observe(self._mode_changed, names='value')
        for control in (self.x0, self.x1, self.y0, self.y1):
            control.observe(lambda _: self._preview(), names='value')
        self.reason.observe(lambda _: self._buttons(), names='value')
        self.apply_button.on_click(lambda _: self._apply())
        self.cancel_button.on_click(lambda _: self._selected())
        self.restore_button.on_click(lambda _: self._apply(restore=True))
        self.failure_enabled.observe(self._failure_mode_changed, names='value')
        self.failure_el.observe(lambda _: self._failure_preview(from_strain=True), names='value')
        self.failure_row.observe(lambda _: self._failure_preview(), names='value')
        self.failure_reason.observe(lambda _: self._buttons(), names='value')
        self.failure_apply.on_click(lambda _: self._apply_failure())
        self.failure_cancel.on_click(lambda _: self._selected())
        self.failure_restore.on_click(lambda _: self._apply_failure(restore=True))
        self._navigation()

    def _dispose(self):
        self.chart_box.children = ()
        self._clear_layers()
        if self.chart is not None:
            self.chart.close()
        if self._probe is not None:
            self._probe.close()
        self._probe = None
        self.chart, self._payload = None, None
        self._draft = None
        self._failure_draft = None
        self.summary.value = ''
        self.gauge_status.value = ''
        self.checks.value = ''
        self.checks.layout.display = 'none'

    def _clear_layers(self):
        self.layer_groups.children = ()
        for widget in reversed(self._layer_widgets):
            widget.close()
        self._layer_widgets = []
        self.layers_panel.layout.display = 'none'

    def _set_layer_visible(self, key, visible):
        if self.chart is None:
            return
        # Changing shape visibility must not trigger an elastic-fit edit.
        painting = self._painting
        self._painting = True
        try:
            with self.chart.batch_update():
                for trace in self.chart.data:
                    if (trace.meta or {}).get('inspector_layer') == key:
                        trace.visible = bool(visible)
                for shape in self.chart.layout.shapes:
                    if shape_layer(shape) == key:
                        shape.visible = bool(visible)
        finally:
            self._painting = painting

    def _layer_changed(self, key, change):
        if self._painting or self.chart is None or key == 'manual_fit':
            return
        self._layer_choices[(self.view.value, key)] = bool(change['new'])
        self._set_layer_visible(key, change['new'])

    def _sync_layers(self):
        """Separate normal-flow legend, so labels can never collide with axes."""
        self._clear_layers()
        if self.chart is None:
            return
        entries = {}
        for trace in self.chart.data:
            key = (trace.meta or {}).get('inspector_layer')
            if key not in INSPECTOR_LAYERS or key in entries:
                continue
            marker = 'markers' in (trace.mode or '')
            swatch = layer_swatch(trace.marker.color if marker else trace.line.color,
                                  trace.marker.symbol if marker else None,
                                  trace.line.dash if not marker else None)
            entries[key] = (trace.name, swatch)
        for shape in self.chart.layout.shapes:
            key = shape_layer(shape)
            if key in INSPECTOR_LAYERS and key not in entries:
                name = 'Fit edit handles' if key == 'manual_fit' else 'Calc EL vertical guide'
                entries[key] = (name, layer_swatch(shape.line.color, dash=shape.line.dash))

        groups = {}
        w = self.w
        for key, (group, default) in INSPECTOR_LAYERS.items():
            if key not in entries:
                continue
            name, swatch = entries[key]
            if key == 'instron_ys_level' and 'yield_instron' not in entries:
                default = True
            visible = self._layer_choices.get((self.view.value, key), default is True or default == self.view.value)
            if key == 'manual_fit':
                visible = True  # Never hide handles while editing a fit.
            self._set_layer_visible(key, visible)
            check = w.Checkbox(description=name, value=bool(visible), indent=False,
                disabled=key == 'manual_fit', layout=w.Layout(width='auto', flex='1 1 auto', min_width='0'),
                tooltip='Fit handles stay visible while editing.' if key == 'manual_fit' else
                        'Show or hide this item without changing calculations.')
            check.add_class('tw-inspector-layer')
            check.observe(lambda change, layer=key: self._layer_changed(layer, change), names='value')
            icon = w.HTML(swatch, layout=w.Layout(width='30px', flex='0 0 30px', margin='0'))
            row = w.HBox([icon, check], layout=w.Layout(width='100%', min_width='0', align_items='center'))
            groups.setdefault(group, []).append(row)
            self._layer_widgets.extend([icon, check, row])
        cards = []
        for group, rows in groups.items():
            title = w.HTML('<b>' + escape(group) + '</b>', layout=w.Layout(margin='0 0 3px 0'))
            card = w.VBox([title, *rows], layout=w.Layout(flex='1 1 240px', min_width='0', max_width='100%',
                padding='8px 10px', border='1px solid #dce3e9'))
            cards.append(card)
            self._layer_widgets.extend([title, card])
        self.layer_groups.children = tuple(cards)
        self.layers_panel.layout.display = '' if cards else 'none'

    def _reset_layers(self, _=None):
        self._layer_choices = {key: value for key, value in self._layer_choices.items() if key[0] != self.view.value}
        self._sync_layers()

    def _view_changed(self, _=None):
        if self._painting or self._updating or self._payload is None:
            return
        self._paint(self._payload, edit=self._draft if self.mode.value != 'inspect' else None)

    def clear(self):
        self._updating = True
        try:
            self.choice.options = [('Choose a specimen…', '')]
            self.choice.value = ''
        finally:
            self._updating = False
        self._dispose()
        self._navigation()
        self.status.value = 'Click a specimen name in the Specimens table, or choose one above.'

    def set_rows(self, rows):
        selected = self.choice.value
        options = [('Choose a specimen…', '')]
        names = [row['group'] + ' · ' + row['sample'] for row in rows]
        for row, name in zip(rows, names):
            # Match the specimen table, not the export-row filename. Keep the
            # stable relative ID as the value and only show it for duplicate names.
            label = name + (' · ' + row['id'] if names.count(name) > 1 else '')
            label += '' if row['included'] else ' (excluded)'
            options.append((label, row['id']))
        self._updating = True
        try:
            self.choice.options = options
            self.choice.value = selected if selected in {value for _, value in options} else ''
        finally:
            self._updating = False
        self._selected()

    def select(self, ident):
        if ident not in {value for _, value in self.choice.options}:
            return
        if self.choice.value == ident:
            self._selected()
        else:
            self.choice.value = ident

    def _navigation(self):
        ids = [value for _, value in self.choice.options if value]
        index = ids.index(self.choice.value) if self.choice.value in ids else -1
        self.previous.disabled = index <= 0
        self.next.disabled = not ids or index >= len(ids) - 1
        self.view.disabled = self.chart is None
        self.reset.disabled = self.chart is None
        self.gauge_overlay.disabled = self.chart is None
        self.mode.disabled = self.chart is None or self.on_apply is None
        self._buttons()

    def _step(self, direction):
        ids = [value for _, value in self.choice.options if value]
        index = ids.index(self.choice.value) if self.choice.value in ids else -1
        if 0 <= index + direction < len(ids):
            self.choice.value = ids[index + direction]

    def _selected(self, _=None):
        if self._updating:
            return
        self._dispose()
        if not self.choice.value or self.loader is None:
            self.status.value = 'Click a specimen name in the Specimens table, or choose one above.'
            self._navigation()
            return
        self.status.value = 'Loading specimen calculation…'
        try:
            payload = self.loader(self.choice.value)
            self._editing = True
            self.mode.value = 'inspect'
            self._editing = False
            self._saved_payload = payload
            self._seed_editor(payload)
            self._seed_failure_editor(payload)
            self._paint(payload)
            self.status.value = ('Read-only until Apply override · drag to zoom; use Reset zoom to return. '
                                 'Fit and EL overrides apply to this specimen in every graph.')
            self.edit_status.value = 'Choose Manual range or Manual line to start an unsaved preview.'
        except Exception as error:
            self._dispose()
            self.status.value = '<b>Inspection unavailable:</b> ' + escape(str(error))
        self._navigation()

    def _seed_failure_editor(self, payload):
        self._failure_sync = True
        self._failure_draft = None
        try:
            self.failure_enabled.value = False
            self.failure_reason.value = (payload['record'].get('_failure_override') or {}).get('reason', '')
            ids, x, _ = failure_measurements(payload['record'])
            self.failure_row.max = len(x)
            end = payload['calculation']['fracture']
            row = end.get('row_before', np.nan)
            row = int(row) if np.isfinite(row) and int(row) - 1 in ids else int(ids[-1]) + 1
            self.failure_row.value = row
            self.failure_el.value = float(x[row - 1])
            self.failure_status.value = ('Current selection: <b>' + escape(end['status']) + '</b>. '
                                         'Enable editing to preview a different endpoint; nothing changes until Apply.')
        except ValueError as error:
            self.failure_status.value = escape(str(error))
        finally:
            self._failure_sync = False

    def _failure_mode_changed(self, _=None):
        if self._failure_sync or self._payload is None:
            return
        if not self.failure_enabled.value:
            self._selected()
            return
        # Preview one kind of override at a time; do not save/discard the other
        # saved policy. EL preview uses the specimen's saved elastic fit.
        self._editing = True
        try:
            self.mode.value = 'inspect'
            self._draft = None
        finally:
            self._editing = False
        self._painting = True
        try:
            self.view.value = 'failure'
        finally:
            self._painting = False
        self._failure_preview(keep_zoom=False)

    def _failure_preview(self, *, from_strain=False, keep_zoom=True):
        if self._failure_sync or self._payload is None or not self.failure_enabled.value:
            return
        self._failure_draft = None
        try:
            saved = self._saved_payload
            record = saved['record']
            row = failure_row_for_strain(record, self.failure_el.value) if from_strain else self.failure_row.value
            candidate = {'row': int(row), 'source_sha256': saved['source_sha256']}
            endpoint = manual_failure_endpoint(record, candidate)
            preview_record = {**record, '_failure_override': candidate}
            fracture_curve(preview_record)  # Validate that downstream trimming is usable.
            calc = specimen_calculation(preview_record, saved['calculation']['fit_fractions'])
            target = saved.get('gauge_policy', {}).get('target_gauge_mm', 0)
            preview = {**saved, 'record': preview_record, 'calculation': calc,
                       'gauge_preview': gauge_record(preview_record, saved['reference'], True, target)}
            self._failure_sync = True
            try:
                self.failure_row.value = row
                self.failure_el.value = endpoint['strain_pct']
            finally:
                self._failure_sync = False
            self._failure_draft = candidate
            self._paint(preview, keep_zoom=keep_zoom)
            self.failure_status.value = (f'<b>Unsaved EL preview:</b> {endpoint["strain_pct"]:.5f}% at '
                f'{endpoint["stress_mpa"]:.2f} MPa · original measurement row {row}. '
                'Purple × = selected point; grey circle = automatic point (when available). '
                'Enter a reason, then Apply. Recorded values and Instron results are unchanged.')
        except Exception as error:
            self.failure_status.value = ('<b>Invalid EL preview:</b> ' + escape(str(error)) +
                                         ' Nothing saved; chart retains the last valid view.')
        finally:
            self._buttons()

    def _pick_failure_point(self, trace, points, _selector):
        if self._painting or not self.failure_enabled.value or not points.point_inds:
            return
        # Measured trace keeps every acquisition row (invalid pairs are NaN),
        # so Plotly point indices map exactly to original measurement indices.
        self._failure_sync = True
        try:
            self.failure_row.value = int(points.point_inds[0]) + 1
        finally:
            self._failure_sync = False
        self._failure_preview()

    def _pick_curve_point(self, trace, points, selector):
        if self._painting or not points.point_inds:
            return
        if self.failure_enabled.value:
            if (trace.meta or {}).get('inspector_layer') == 'measured':
                self._pick_failure_point(trace, points, selector)
            return
        endpoint = self.fit_pick.value
        if self.mode.value == 'inspect' or not endpoint:
            return
        index = int(points.point_inds[0])
        x, y = float(trace.x[index]), float(trace.y[index])
        if not np.isfinite(x) or not np.isfinite(y):
            return
        self._editing = True
        try:
            (self.x0 if endpoint == 'start' else self.x1).value = x
            if self.mode.value == 'line':
                (self.y0 if endpoint == 'start' else self.y1).value = y
            self.fit_pick.value = 'end' if endpoint == 'start' else ''
        finally:
            self._editing = False
        self._preview()

    def _apply_failure(self, restore=False):
        if (not self.on_failure_apply or self._payload is None or
                (not restore and self.failure_apply.disabled)):
            return
        try:
            self.on_failure_apply(self.choice.value, self._saved_payload['source_sha256'],
                                  None if restore else deepcopy(self._failure_draft), self.failure_reason.value)
            self._selected()
            self.failure_status.value = ('Automatic EL restored in all graphs.' if restore else
                                         'Manual EL saved for this specimen in all graphs. Update plots when ready.')
        except Exception as error:
            self.failure_status.value = '<b>EL override not saved:</b> ' + escape(str(error))

    def _seed_editor(self, payload):
        calc = payload['calculation']
        saved = calc.get('override')
        mask, x, y = calc['elastic_mask'], calc['strain_pct'], calc['stress_mpa']
        if saved:
            low, high = saved['strain_bounds']
        elif mask.any():
            low, high = float(x[mask][0]), float(x[mask][-1])
        elif len(x) > 5:
            end = max(4, min(len(x)-1, (calc['uts_index'] or len(x)) // 3))
            low, high = float(x[0]), float(x[end])
        else:
            low, high = 0., .2
        p = calc['properties']
        self._editing = True
        try:
            self.x0.value, self.x1.value = low, high
            if saved and saved['mode'] == 'line':
                self.y0.value, self.y1.value = saved['endpoints'][0][1], saved['endpoints'][1][1]
            elif np.isfinite(p['Fitted E (GPa)']):
                self.y0.value, self.y1.value = [p['Fitted E (GPa)'] * 10 * v + p['Elastic intercept (MPa)'] for v in (low, high)]
            elif len(x):
                self.y0.value, self.y1.value = np.interp([low, high], x, y)
            self.reason.value = (calc.get('saved_override') or {}).get('reason', '')
        finally:
            self._editing = False

    def _buttons(self):
        editing = self._payload is not None and self.mode.value != 'inspect'
        self.fit_pick.disabled = not editing
        self.fit_pick.layout.display = self.fit_pick_hint.layout.display = '' if editing else 'none'
        self.x0.disabled = self.x1.disabled = self.reason.disabled = not editing
        self.y0.disabled = self.y1.disabled = not editing or self.mode.value != 'line'
        self.line_fields.layout.display = '' if self.mode.value == 'line' else 'none'
        self.cancel_button.disabled = not editing
        self.apply_button.disabled = not (editing and self._draft and self.reason.value.strip() and
            self._payload['calculation']['properties']['Yield status'] == 'resolved' and self.on_apply)
        self.restore_button.disabled = not (self._payload and self.on_apply and
            self._saved_payload['calculation'].get('saved_override'))
        failure_editing = self._payload is not None and self.failure_enabled.value
        self.failure_enabled.disabled = self._payload is None or self.on_failure_apply is None
        self.failure_el.disabled = self.failure_row.disabled = self.failure_reason.disabled = not failure_editing
        self.failure_apply.disabled = not (failure_editing and self._failure_draft and
                                          self.failure_reason.value.strip() and self.on_failure_apply)
        self.failure_cancel.disabled = not failure_editing
        self.failure_restore.disabled = not (self._payload and self.on_failure_apply and
                                            self._saved_payload['record'].get('_failure_override'))
        self.mode.disabled = self.chart is None or self.on_apply is None or failure_editing
        if failure_editing:
            self.restore_button.disabled = True

    def _mode_changed(self, _=None):
        if self._editing or self._payload is None:
            return
        if self.mode.value == 'inspect':
            self.fit_pick.value = ''
            self._selected()
        else:
            self.fit_pick.value = 'start'
            self._painting = True
            try:
                self.view.value = 'yield'
            finally:
                self._painting = False
            self._preview(keep_zoom=False)

    def _preview(self, *, keep_zoom=True):
        if self._editing or self._payload is None or self.mode.value == 'inspect':
            return
        self._draft = None
        try:
            record = self._saved_payload['record']
            bounds = [self.x0.value, self.x1.value]
            if self.mode.value == 'range':
                # Snap range handles/numerical bounds to actual prepared measurement points.
                x = self._saved_payload['calculation']['strain_pct']
                if len(x):
                    bounds = [float(x[np.argmin(abs(x-v))]) for v in bounds]
            candidate = {'mode': self.mode.value, 'strain_bounds': bounds,
                         'source_sha256': self._saved_payload['source_sha256']}
            if self.mode.value == 'line':
                candidate['endpoints'] = [[bounds[0], self.y0.value], [bounds[1], self.y1.value]]
            calc = specimen_calculation(record, self._saved_payload['calculation']['fit_fractions'], override=candidate)
            calc['properties']['Override status'] = 'Unsaved preview'
            self._editing = True
            self.x0.value, self.x1.value = bounds
            self._editing = False
            self._draft = candidate
            self._paint({**self._saved_payload, 'calculation': calc}, edit=candidate, keep_zoom=keep_zoom)
            instruction = ('Use Set start / Set end and click the measured curve, or drag the purple range borders; '
                           'all selected points are refitted.' if self.mode.value == 'range' else
                           'Use Set start / Set end and click the measured curve, or drag either purple line endpoint; '
                           'this directly changes slope/intercept.')
            self.edit_status.value = '<b>Unsaved preview.</b> ' + instruction + ' Enter a reason, then Apply override to use it in every graph.'
            if calc['properties']['Yield status'] != 'resolved':
                self.edit_status.value += '<br><b>Cannot apply:</b> ' + escape(calc['properties']['Notes'])
        except Exception as error:
            self.edit_status.value = '<b>Invalid preview:</b> ' + escape(str(error)) + ' The chart retains the last valid view; nothing has been saved.'
        finally:
            self._editing = False
            self._buttons()

    def _overlay_changed(self, _=None):
        if self._painting or self._updating or self._payload is None:
            return
        if self.gauge_overlay.value and self.view.value != 'failure':
            self._painting = True
            try:
                self.view.value = 'full'
            finally:
                self._painting = False
        self._paint(self._payload, edit=self._draft if self.mode.value != 'inspect' else None)

    def _paint(self, payload, edit=None, keep_zoom=False):
        import plotly.graph_objects as go
        from tensile_plotly import width_probe
        fig = inspection_figure(payload, self.view.value, edit=edit, show_gauge=self.gauge_overlay.value)
        self._painting = True
        try:
            if self.chart is None:
                self.chart = go.FigureWidget(fig)
                self.chart.layout.on_change(self._dragged, 'shapes')
                self._probe = width_probe(self._resize)
                self.chart_box.children = (self._probe, self.chart)
            else:
                if keep_zoom:
                    fig.update_xaxes(range=self.chart.layout.xaxis.range)
                    fig.update_yaxes(range=self.chart.layout.yaxis.range)
                with self.chart.batch_update():
                    self.chart.data = []
                    self.chart.add_traces(fig.data)
                    self.chart.layout.shapes = fig.layout.shapes
                    self.chart.layout.annotations = fig.layout.annotations
                    self.chart.update_xaxes(range=fig.layout.xaxis.range, autorange=False)
                    self.chart.update_yaxes(range=fig.layout.yaxis.range, autorange=False)
            self._payload = payload
            for trace in self.chart.data:
                if (trace.meta or {}).get('inspector_layer') in ('measured', 'fit_points'):
                    trace.on_click(self._pick_curve_point)
            self._sync_layers()
            self.summary.value = inspection_summary(payload)
            self.checks.value = inspection_checks(payload, preview=bool(edit or self._failure_draft))
            self.checks.layout.display = '' if self.checks.value else 'none'
            preview = payload.get('gauge_preview')
            audit = preview['_gauge'] if preview else {}
            self.gauge_status.value = ''
            if self.gauge_overlay.value:
                if audit.get('Gauge correction status') != 'Applied':
                    self.gauge_status.value = '<b>Measured curve only — reconstruction unavailable:</b> ' + escape(
                        audit.get('Gauge correction status', 'No gauge preview available'))
                else:
                    self.gauge_status.value = 'Display-only overlay: solid measured; dashed reconstructed. No settings or measurements changed.'
                    if audit.get('Gauge model warning'):
                        self.gauge_status.value += '<br><b>Model warning:</b> ' + escape(audit['Gauge model warning'])
            if self._probe and self._probe.pixels:
                self._resize(self._probe.pixels)
        finally:
            self._painting = False

    def _dragged(self, layout, shapes):
        if self._painting or self.chart is None or layout is not self.chart.layout or self.mode.value == 'inspect':
            return
        shape = next((shape for shape in shapes if shape.name in ('fit-line', 'fit-range')), None)
        if shape is None:
            return
        self._editing = True
        try:
            self.x0.value, self.x1.value = shape.x0, shape.x1
            if shape.name == 'fit-line':
                self.y0.value, self.y1.value = shape.y0, shape.y1
        finally:
            self._editing = False
        self._preview()

    def _apply(self, restore=False):
        if not self.on_apply or not self._payload or (not restore and self.apply_button.disabled):
            return
        try:
            self.on_apply(self.choice.value, self._saved_payload['source_sha256'],
                          None if restore else deepcopy(self._draft), self.reason.value)
            self._selected()
            self.edit_status.value = 'Automatic fit restored in all graphs.' if restore else 'Override saved for this specimen in all graphs.'
        except Exception as error:
            self.edit_status.value = '<b>Not applied:</b> ' + escape(str(error))

    def _resize(self, width):
        if self.chart is None:
            return
        width = max(240, int(width))
        plot_height = 420
        bottom = 88
        with self.chart.batch_update():
            self.chart.update_layout(width=width, height=plot_height + 22 + bottom,
                margin=dict(l=82, r=25, t=22, b=bottom), showlegend=False)

    def _reset_zoom(self):
        if self.chart is None or self._payload is None:
            return
        xrange, yrange = overlay_ranges(self._payload, self.view.value, self.gauge_overlay.value)
        with self.chart.batch_update():
            self.chart.update_xaxes(range=xrange, autorange=False)
            self.chart.update_yaxes(range=yrange, autorange=False)
