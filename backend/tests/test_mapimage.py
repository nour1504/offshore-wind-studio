"""Fields resampled on the web map's projection: every cell lands inside the domain outline."""

import numpy as np

from owstudio.core.case.model import Case
from owstudio.core.domains import domain_outlines
from owstudio.core.postproc import mapimage


def test_a_lambert_field_fills_its_curved_outline_on_the_map(reference_case: Case) -> None:
    grid = reference_case.grid
    domain = grid.domains[0]
    ny, nx = domain.e_sn - 1, domain.e_we - 1
    # Each cell holds its column number: the image must keep west on the left
    field = np.tile(np.arange(nx, dtype=float), (ny, 1))
    image = mapimage.reproject(field, grid, 1)
    corners = mapimage.corners(grid, 1, (ny, nx))

    west, north = corners[0]
    east, south = corners[2]
    ring = domain_outlines(grid)[0]
    assert west == min(p[0] for p in ring) and east == max(p[0] for p in ring)
    assert south == min(p[1] for p in ring) and north == max(p[1] for p in ring)
    # Inside: every column of the grid appears, increasing from west to east along the middle row
    middle = image[image.shape[0] // 2]
    seen = middle[np.isfinite(middle)]
    assert seen.min() == 0 and seen.max() == nx - 1 and np.all(np.diff(seen) >= 0)
    # Outside the curved edges of a Lambert domain: transparent corners of the image
    assert np.isnan(image[0, 0]) or np.isnan(image[-1, 0])
    assert 0.02 < np.isnan(image).mean() < 0.4
