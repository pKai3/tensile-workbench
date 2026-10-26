"""Exact measurement headings shared by curve and summary readers."""

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


def is_measurement_header(row):
    names = {str(value).strip().lower() for value in row}
    return bool(names & {name.lower() for name in STRAIN_COLS}
                and names & {name.lower() for name in STRESS_COLS + FORCE_COLS})
