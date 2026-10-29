"""Fields drawn for the web map: resampled from the model grid to the map's own projection.

The map (MapLibre) stretches an image between four corners in Web Mercator. A WRF grid is
regular in its own projection (Lambert, polar, Mercator), not in Web Mercator: its edges curve
on the map. Each pixel of a regular Web Mercator image over the domain therefore takes the value
of the grid cell under it (nearest cell), and pixels outside the domain stay transparent.
"""

import math
from functools import lru_cache

import numpy as np

from owstudio.core.case.model import Grid
from owstudio.core.domains import domain_extents, domain_outlines, projection_for

# Pixels per grid cell across the image, within these bounds
SUPERSAMPLING = 3
MIN_WIDTH, MAX_WIDTH = 256, 1024


def _mercator_y(lat: float) -> float:
    return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


Bounds = tuple[float, float, float, float]


@lru_cache(maxsize=32)
def _lookup(grid_json: str, domain: int, ny: int, nx: int) -> tuple[np.ndarray, np.ndarray, Bounds]:
    """Grid indices (j, i) under every pixel (-1 outside the domain) and the image bounds
    (west, south, east, north) in degrees."""
    grid = Grid.model_validate_json(grid_json)
    extent = domain_extents(grid)[domain - 1]
    outline = domain_outlines(grid)[domain - 1]
    lons = [p[0] for p in outline]
    lats = [p[1] for p in outline]
    west, east, south, north = min(lons), max(lons), min(lats), max(lats)
    width = int(min(MAX_WIDTH, max(MIN_WIDTH, SUPERSAMPLING * nx)))
    top, bottom = _mercator_y(north), _mercator_y(south)
    height = max(1, round(width * (top - bottom) / math.radians(east - west)))
    columns = west + (np.arange(width) + 0.5) / width * (east - west)
    rows = top - (np.arange(height) + 0.5) / height * (top - bottom)
    lat = np.degrees(np.arctan(np.sinh(rows)))
    lon_grid, lat_grid = np.meshgrid(columns, lat)
    forward = np.vectorize(projection_for(grid.projection).forward, otypes=[float, float])
    x, y = forward(lat_grid, lon_grid)
    i = np.floor((x - extent.west) / extent.dx).astype(int)
    j = np.floor((y - extent.south) / extent.dx).astype(int)
    outside = (i < 0) | (i >= nx) | (j < 0) | (j >= ny)
    i[outside] = -1
    j[outside] = -1
    return j, i, (west, south, east, north)


def reproject(values: np.ndarray, grid: Grid, domain: int) -> np.ndarray:
    """The field on the Web Mercator image, north at the top; NaN outside the domain."""
    ny, nx = values.shape
    j, i, _ = _lookup(grid.model_dump_json(), domain, ny, nx)
    image: np.ndarray = np.asarray(values, dtype=float)[np.clip(j, 0, None), np.clip(i, 0, None)]
    image[j < 0] = np.nan
    return image


def corners(grid: Grid, domain: int, shape: tuple[int, int]) -> list[list[float]]:
    """Corners of the image, clockwise from the top left, as [lon, lat] for the map."""
    _, _, (west, south, east, north) = _lookup(grid.model_dump_json(), domain, *shape)
    return [[west, north], [east, north], [east, south], [west, south]]
