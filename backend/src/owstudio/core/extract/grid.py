"""Where a latitude/longitude falls on a WRF grid, and bilinear weights around it.

Fractional grid indices are found on the model's own coordinates (XLAT, XLONG of the mass
points), whatever the map projection: start from the nearest mass point by great-circle
distance, then Newton iterations on the bilinear interpolation of XLAT/XLONG. This needs no
projection formula and is exact to well below a metre on the smooth WRF grids.
"""

import math
from dataclasses import dataclass

import numpy as np

from owstudio.core.i18n import tr


class OutsideGrid(ValueError):
    """The point is outside the domain (or too close to its edge for interpolation)."""


@dataclass(frozen=True)
class Position:
    """Fractional mass-point indices (0-based, i west-east, j south-north) of a point."""

    i: float
    j: float
    lat: float
    lon: float
    # Mass points of the grid, west-east and south-north
    nx: int
    ny: int

    @property
    def nearest(self) -> tuple[int, int]:
        return round(self.i), round(self.j)

    def window(self) -> tuple[int, int, np.ndarray]:
        """Lower-left corner (i0, j0) of the 2 x 2 cell around the point and the bilinear
        weights w[dj, di] of its four mass points."""
        i0 = min(math.floor(self.i), self.nx - 2)
        j0 = min(math.floor(self.j), self.ny - 2)
        fi, fj = self.i - i0, self.j - j0
        weights = np.array([[(1 - fi) * (1 - fj), fi * (1 - fj)], [(1 - fi) * fj, fi * fj]])
        return i0, j0, weights


def _distance(lat1: np.ndarray, lon1: np.ndarray, lat2: float, lon2: float) -> np.ndarray:
    """Great-circle distance in radians (haversine)."""
    p1, p2 = np.radians(lat1), math.radians(lat2)
    dlat = p2 - p1
    dlon = np.radians(((lon2 - lon1 + 180.0) % 360.0) - 180.0)
    a = np.sin(dlat / 2) ** 2 + np.cos(p1) * math.cos(p2) * np.sin(dlon / 2) ** 2
    result: np.ndarray = 2 * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))
    return result


def _bilinear(field: np.ndarray, i: float, j: float) -> float:
    ny, nx = field.shape
    i0 = min(max(math.floor(i), 0), nx - 2)
    j0 = min(max(math.floor(j), 0), ny - 2)
    fi, fj = i - i0, j - j0
    return float(
        field[j0, i0] * (1 - fi) * (1 - fj)
        + field[j0, i0 + 1] * fi * (1 - fj)
        + field[j0 + 1, i0] * (1 - fi) * fj
        + field[j0 + 1, i0 + 1] * fi * fj
    )


def locate(xlat: np.ndarray, xlong: np.ndarray, lat: float, lon: float) -> Position:
    """Fractional indices of (lat, lon) on the grid of mass points. Raises OutsideGrid."""
    ny, nx = xlat.shape
    distance = _distance(xlat, xlong, lat, lon)
    j, i = np.unravel_index(int(np.argmin(distance)), distance.shape)
    fi, fj = float(i), float(j)
    # Longitudes unwrapped around the point so that grids crossing 180° behave
    lon_grid = lon + ((xlong - lon + 180.0) % 360.0) - 180.0
    for _ in range(8):
        gi = min(max(math.floor(fi), 0), nx - 2)
        gj = min(max(math.floor(fj), 0), ny - 2)
        la = _bilinear(xlat, fi, fj)
        lo = _bilinear(lon_grid, fi, fj)
        # Local derivatives of latitude and longitude with respect to i and j
        dla_di = float(xlat[gj, gi + 1] - xlat[gj, gi])
        dla_dj = float(xlat[gj + 1, gi] - xlat[gj, gi])
        dlo_di = float(lon_grid[gj, gi + 1] - lon_grid[gj, gi])
        dlo_dj = float(lon_grid[gj + 1, gi] - lon_grid[gj, gi])
        det = dla_di * dlo_dj - dla_dj * dlo_di
        if abs(det) < 1e-15:
            break
        r_lat, r_lon = lat - la, lon - lo
        step_i = (r_lat * dlo_dj - r_lon * dla_dj) / det
        step_j = (dla_di * r_lon - dlo_di * r_lat) / det
        fi, fj = fi + step_i, fj + step_j
        if abs(step_i) < 1e-7 and abs(step_j) < 1e-7:
            break
    if not (0.0 <= fi <= nx - 1 and 0.0 <= fj <= ny - 1):
        raise OutsideGrid(
            tr(
                f"The point ({lat:.4f}, {lon:.4f}) is outside the domain",
                f"Le point ({lat:.4f}, {lon:.4f}) est hors du domaine",
            )
        )
    return Position(fi, fj, lat, lon, nx, ny)
