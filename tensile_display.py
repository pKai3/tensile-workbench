"""Simple display-only row selection; never used by calculations or exports."""
import numpy as np

PREVIEW_POINTS = 4000


def preview_indices(x, y, limit=PREVIEW_POINTS):
    """Keep every Nth reading, the endpoints, and missing-reading boundaries.

    No fitting, averaging, extrema search or interpolation. Gaps can add points
    beyond the normal budget so the preview never joins across missing data.
    """
    n = len(x)
    if n <= limit:
        return np.arange(n)
    step = (n + limit - 1) // limit
    valid = np.isfinite(x) & np.isfinite(y)
    boundaries = np.flatnonzero(valid[1:] != valid[:-1])
    return np.unique(np.r_[np.arange(0, n, step), n - 1, boundaries, boundaries + 1])
