"""WRF time series output (tslist): locations, the tslist file and its namelist settings.

WRF reads tslist with three header lines, then one location per line in the Fortran format
(A25,1X,A5,1X,F7.3,1X,F8.3): name, prefix, latitude, longitude. For each location inside a
domain it writes, at every time step, prefix.dNN.TS (surface variables) and vertical profiles
prefix.dNN.UU, VV, WW, TH, PH, QV and PR.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass

from owstudio.core.case.model import Case, TimeSeriesPoint
from owstudio.core.domains import cell_of
from owstudio.core.i18n import tr

HEADER = (
    "#-----------------------------------------------#\n"
    "# 24 characters for name | pfx |  LAT  |   LON  |\n"
    "#-----------------------------------------------#\n"
)
NAME_WIDTH, LAT_WIDTH, LON_WIDTH = 25, 7, 8


def turbine_labels(case: Case) -> dict[tuple[str, int], str]:
    """Stable result identifiers, preserving globally unique existing display labels.

    Farms commonly both use A01. Qualify only colliding labels, including collisions with
    automatically generated names. Reserve every unique original label before adding qualified
    ones so a user's label such as ``farm/A01`` cannot itself be overwritten.
    """
    entries = [
        (farm.id, index, turbine.id or f"{farm.id}-{index}")
        for farm in case.farms
        for index, turbine in enumerate(farm.turbines, 1)
    ]
    counts = Counter(label for _, _, label in entries)
    used = {label for _, _, label in entries if counts[label] == 1}
    result = {}
    for farm, index, label in entries:
        if counts[label] == 1:
            result[(farm, index)] = label
            continue
        base = f"{farm}/{label}"
        candidate, suffix = base, 2
        while candidate in used:
            candidate = f"{base}#{suffix}"
            suffix += 1
        used.add(candidate)
        result[(farm, index)] = candidate
    return result


def _fixed(value: float, width: int) -> str:
    """The most precise rendering of ``value`` that fits the Fortran field width.

    Fortran honours an explicit decimal point on input, so 55.50635 reads correctly from an
    F7.3 field as long as it fits in seven characters.
    """
    for decimals in (5, 4, 3, 2):
        text = f"{value:.{decimals}f}"
        if len(text) <= width:
            return text.rjust(width)
    raise ValueError(
        tr(
            f"{value} does not fit a {width}-character field",
            f"{value} ne tient pas dans un champ de {width} caractères",
        )
    )


def _turbine_points(case: Case) -> list[tuple[TimeSeriesPoint, list[tuple[str, int]]]]:
    """The turbine locations (one per turbine or per cell), each with its turbines (farm id,
    number in the farm from 1)."""
    config = case.time_series
    if config is None:
        return []
    # Every farm, enabled or not: runs of the project with other farms switched on then write
    # series at the same locations, so each turbine can be compared from one run to another
    turbines = [(farm, k, t) for farm in case.farms for k, t in enumerate(farm.turbines, 1)]
    if turbines and config.turbines == "each":
        labels = turbine_labels(case)
        return [
            (
                TimeSeriesPoint(
                    name=f"Turbine {labels[(farm.id, k)]}"[:NAME_WIDTH],
                    prefix=f"T{n:04d}",
                    lat=t.lat,
                    lon=t.lon,
                ),
                [(farm.id, k)],
            )
            for n, (farm, k, t) in enumerate(turbines, 1)
        ]
    points = []
    if turbines and config.turbines == "cells":
        # One location per cell of the innermost wind farm domain, at its turbines' centroid
        domain = max(case.farm_scheme.domains) if case.farm_scheme else case.max_dom
        cells: dict[tuple[int, int], list[tuple[str, int, float, float]]] = defaultdict(list)
        for farm, k, t in turbines:
            cell = cell_of(case.grid, domain, t.lat, t.lon)
            if cell is not None:
                cells[cell].append((farm.id, k, t.lat, t.lon))
        for n, ((i, j), members) in enumerate(sorted(cells.items()), 1):
            lat = sum(m[2] for m in members) / len(members)
            lon = sum(m[3] for m in members) / len(members)
            name = f"Cell {i},{j} ({len(members)} turb.)"
            point = TimeSeriesPoint(name=name[:NAME_WIDTH], prefix=f"C{n:04d}", lat=lat, lon=lon)
            points.append((point, [(m[0], m[1]) for m in members]))
    return points


def locations(case: Case) -> list[TimeSeriesPoint]:
    """Locations of the case: the turbines or their cells, then the user's points."""
    if case.time_series is None:
        return []
    return [point for point, _ in _turbine_points(case)] + list(case.time_series.points)


def turbines_at(case: Case) -> dict[str, list[tuple[str, int]]]:
    """The turbines each turbine location stands for (farm id, number in the farm from 1), by
    prefix: one for a turbine, every turbine of the cell for a cell."""
    return {point.prefix: members for point, members in _turbine_points(case)}


def duplicate_prefixes(points: list[TimeSeriesPoint]) -> list[str]:
    seen: set[str] = set()
    duplicates = []
    for point in points:
        key = point.prefix.lower()  # file names are compared case-insensitively on Windows
        if key in seen:
            duplicates.append(point.prefix)
        seen.add(key)
    return duplicates


def tslist_text(points: list[TimeSeriesPoint]) -> str:
    lines = [
        f"{p.name:<{NAME_WIDTH}.{NAME_WIDTH}} {p.prefix:<5} "
        f"{_fixed(p.lat, LAT_WIDTH)} {_fixed(p.lon, LON_WIDTH)}"
        for p in points
    ]
    return HEADER + "".join(f"{line}\n" for line in lines)


def namelist_settings(case: Case) -> dict[str, object]:
    """&domains options enabling the time series for the case's locations."""
    points = locations(case)
    if not points or case.time_series is None:
        return {}
    return {
        "max_ts_locs": len(points),
        "max_ts_level": min(case.time_series.max_levels, case.grid.e_vert - 1),
        # Winds at the cell centres, where heights and the other variables are given
        "tslist_unstagger_winds": True,
    }


@dataclass(frozen=True)
class CellTurbine:
    farm: str
    label: str
    # Prefix of the turbine's own time series in "each" mode
    prefix: str | None
    simulated: bool


@dataclass(frozen=True)
class Cell:
    """A grid cell of the farm domain holding turbines (i, j: WRF mass-point indices from 1)."""

    domain: int
    i: int
    j: int
    turbines: tuple[CellTurbine, ...]
    # Prefix of the cell's time series in "cells" mode
    prefix: str | None

    @property
    def farms(self) -> list[str]:
        return sorted({t.farm for t in self.turbines})


def farm_domain(case: Case) -> int:
    """Domain of the wind farm cells: the innermost domain of the scheme."""
    return max(case.farm_scheme.domains) if case.farm_scheme else case.max_dom


def cells(case: Case) -> list[Cell]:
    """Every cell holding turbines, with its turbines, in the numbering of the tslist: the same
    farms and order as locations() (every farm, enabled or not)."""
    if not case.max_dom:
        return []
    domain = farm_domain(case)
    labels = turbine_labels(case)
    mode = case.time_series.turbines if case.time_series else "none"
    simulated = {farm.id for farm in case.enabled_farms} if case.farm_scheme else set()
    members: dict[tuple[int, int], list[CellTurbine]] = defaultdict(list)
    number = 0
    for farm in case.farms:
        for k, turbine in enumerate(farm.turbines, 1):
            number += 1
            cell = cell_of(case.grid, domain, turbine.lat, turbine.lon)
            if cell is None:
                continue
            members[cell].append(
                CellTurbine(
                    farm.id,
                    labels[(farm.id, k)],
                    f"T{number:04d}" if mode == "each" else None,
                    farm.id in simulated,
                )
            )
    return [
        Cell(domain, i, j, tuple(group), f"C{n:04d}" if mode == "cells" else None)
        for n, ((i, j), group) in enumerate(sorted(members.items()), 1)
    ]
