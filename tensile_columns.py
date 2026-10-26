"""Exact measurement headings shared by curve and summary readers."""
import re

FORCE_COLS = [
    "Load", "Force", "Load (N)", "Force (N)", "Force(N)", "Load(N)",
    "Axial Force", "Axial Force (N)"
]
STRESS_COLS = [
    "Stress", "Engineering Stress", "True Stress", "Stress (MPa)",
    "Engineering Stress (MPa)", "True Stress (MPa)",
    "Stress (Pa)", "Engineering Stress (Pa)", "True Stress (Pa)",
    "Tensile stress"
]
STRAIN_COLS = [
    "Strain", "Engineering Strain", "True Strain", "Strain (%)",
    "Engineering Strain (%)", "True Strain (%)",
    "Axial Strain", "Axial Strain (%)",
    "Tensile strain (Strain 1)", "Strain 1"
]


def measurement_kind(name):
    """Recognise whole measurement names, including a trailing unit declaration."""
    text = re.sub(r'\s+', ' ', str(name).strip().casefold())
    for kind, names in (('stress', STRESS_COLS), ('strain', STRAIN_COLS), ('force', FORCE_COLS),
                        ('time', ['Time', 'Test time'])):
        if text in {n.casefold() for n in names}:
            return kind
    base = re.sub(r'\s*[\[(][^\])]+[\])]$', '', text).strip()
    if base != text:
        return measurement_kind(base)
    return None


def is_measurement_header(row):
    kinds = {measurement_kind(value) for value in row}
    return 'strain' in kinds and bool(kinds & {'stress', 'force'})
