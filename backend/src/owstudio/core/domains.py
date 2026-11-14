"""Map projections and domain outlines, following the conventions of WPS geogrid.

Coordinates are on a sphere of radius 6370 km like WRF. Each domain is
described in projection-plane metres by the edges of its staggered grid; the
outermost domain is centred on (ref_lat, ref_lon).
"""

import math
from dataclasses import dataclass
from typing import Protocol

from owstudio.core.case.model import Grid, Projection
from owstudio.core.i18n import tr

EARTH_RADIUS_M = 6_370_000.0


class PlaneProjection(Protocol):
    def forward(self, lat: float, lon: float) -> tuple[float, float]: ...

    def inverse(self, x: float, y: float) -> tuple[float, float]: ...


def _wrap(angle: float) -> float:
    """Wrap an angle in radians to [-pi, pi)."""
    return (angle + math.pi) % (2 * math.pi) - math.pi


class LambertConformal:
    """Lambert conformal conic, secant at truelat1 and truelat2 (or tangent if equal)."""

    def __init__(self, truelat1: float, truelat2: float, stand_lon: float) -> None:
        # Southern hemisphere cones are the mirror image of northern ones
        self.hemi = 1.0 if truelat1 >= 0 else -1.0
        phi1 = math.radians(self.hemi * truelat1)
        phi2 = math.radians(self.hemi * truelat2)
        if abs(phi1 - phi2) < 1e-6:
            self.n = math.sin(phi1)
        else:
            self.n = math.log(math.cos(phi1) / math.cos(phi2)) / math.log(
                math.tan(math.pi / 4 + phi2 / 2) / math.tan(math.pi / 4 + phi1 / 2)
            )
        self.f = math.cos(phi1) * math.tan(math.pi / 4 + phi1 / 2) ** self.n / self.n
        self.lon0 = math.radians(stand_lon)

    def forward(self, lat: float, lon: float) -> tuple[float, float]:
        phi = math.radians(self.hemi * lat)
        rho = EARTH_RADIUS_M * self.f / math.tan(math.pi / 4 + phi / 2) ** self.n
        theta = self.n * _wrap(math.radians(lon) - self.lon0)
        return rho * math.sin(theta), -self.hemi * rho * math.cos(theta)

    def inverse(self, x: float, y: float) -> tuple[float, float]:
        y = self.hemi * y
        rho = math.hypot(x, y)
        theta = math.atan2(x, -y)
        phi = 2 * math.atan((EARTH_RADIUS_M * self.f / rho) ** (1 / self.n)) - math.pi / 2
        lon = math.degrees(_wrap(self.lon0 + theta / self.n))
        return self.hemi * math.degrees(phi), lon


class Mercator:
    """Mercator true at truelat1, longitudes measured from the reference longitude."""

    def __init__(self, truelat1: float, ref_lon: float) -> None:
        self.scale = EARTH_RADIUS_M * math.cos(math.radians(truelat1))
        self.lon0 = math.radians(ref_lon)

    def forward(self, lat: float, lon: float) -> tuple[float, float]:
        x = self.scale * _wrap(math.radians(lon) - self.lon0)
        y = self.scale * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
        return x, y

    def inverse(self, x: float, y: float) -> tuple[float, float]:
        lat = math.degrees(2 * math.atan(math.exp(y / self.scale)) - math.pi / 2)
        return lat, math.degrees(_wrap(self.lon0 + x / self.scale))


def projection_for(projection: Projection) -> PlaneProjection:
    if projection.map_proj == "lambert":
        truelat1 = projection.truelat1 if projection.truelat1 is not None else projection.ref_lat
        truelat2 = projection.truelat2 if projection.truelat2 is not None else truelat1
        stand_lon = projection.stand_lon if projection.stand_lon is not None else projection.ref_lon
        return LambertConformal(truelat1, truelat2, stand_lon)
    if projection.map_proj == "mercator":
        truelat1 = projection.truelat1 if projection.truelat1 is not None else 0.0
        return Mercator(truelat1, projection.ref_lon)
    raise NotImplementedError(
        tr(
            f"{projection.map_proj} projection is not supported yet",
            f"La projection {projection.map_proj} n'est pas encore prise en charge",
        )
    )


@dataclass(frozen=True)
class Extent:
    """Edges of a domain's staggered grid in the projection plane, metres."""

    west: float
    east: float
    south: float
    north: float
    dx: float


def domain_extents(grid: Grid) -> list[Extent]:
    proj = projection_for(grid.projection)
    xc, yc = proj.forward(grid.projection.ref_lat, grid.projection.ref_lon)
    extents: list[Extent] = []
    for number, (domain, dx) in enumerate(zip(grid.domains, grid.domain_dx(), strict=True), 1):
        width, height = (domain.e_we - 1) * dx, (domain.e_sn - 1) * dx
        if number == 1:
            west, south = xc - width / 2, yc - height / 2
        else:
            parent = extents[domain.parent_id - 1]
            west = parent.west + (domain.i_parent_start - 1) * parent.dx
            south = parent.south + (domain.j_parent_start - 1) * parent.dx
        extents.append(Extent(west, west + width, south, south + height, dx))
    return extents


def domain_outlines(grid: Grid, points_per_edge: int = 24) -> list[list[tuple[float, float]]]:
    """Closed (lon, lat) outline of every domain, sampled along edges that curve on the map."""
    proj = projection_for(grid.projection)
    outlines = []
    for e in domain_extents(grid):
        corners = [(e.west, e.south), (e.east, e.south), (e.east, e.north), (e.west, e.north)]
        ring: list[tuple[float, float]] = []
        for (x0, y0), (x1, y1) in zip(corners, corners[1:] + corners[:1], strict=True):
            for k in range(points_per_edge):
                t = k / points_per_edge
                lat, lon = proj.inverse(x0 + t * (x1 - x0), y0 + t * (y1 - y0))
                ring.append((lon, lat))
        ring.append(ring[0])
        outlines.append(ring)
    return outlines


def cell_of(grid: Grid, domain_number: int, lat: float, lon: float) -> tuple[int, int] | None:
    """1-based (i, j) of the mass cell containing a point, or None outside the domain."""
    proj = projection_for(grid.projection)
    e = domain_extents(grid)[domain_number - 1]
    x, y = proj.forward(lat, lon)
    if not (e.west <= x < e.east and e.south <= y < e.north):
        return None
    return int((x - e.west) // e.dx) + 1, int((y - e.south) // e.dx) + 1
