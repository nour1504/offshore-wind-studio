"""NetCDF input files: ERA5 from the Copernicus Climate Data Store (current and legacy layouts)
and SST analyses such as OSTIA, converted to WPS intermediate files at the times of a run.

WPS's ungrib reads GRIB only. The conversion writes what ungrib would write from the same ERA5
data read with Vtable.ECMWF: the same field names, units and levels, and the same derived fields
computed at the available times (rrpr.F: HGT = GEOPT / 9.81, SOILHGT = SOILGEO / 9.81, 2 m RH
from the dew point, SNOW from the water equivalent depth, the ECMWF land-sea mask made a 0/1
flag). The run's times between two available times are then interpolated linearly, as ungrib's
datint.F does. Values missing in the files (SST over land) are written as -1e30, as ungrib writes
points outside a GRIB bitmap.
"""

import hashlib
import json
from collections.abc import Callable, Iterator
from contextlib import ExitStack
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import netCDF4
import numpy as np

from owstudio.core import ncio
from owstudio.core.data.intermediate import (
    SEA_LEVEL,
    SURFACE_LEVEL,
    LatLonGrid,
    Slab,
    file_date,
    write,
)
from owstudio.core.i18n import tr
from owstudio.core.series import units as unit_conversion

Kind = Literal["pressure", "surface", "sea level", "soil"]
Role = Literal["atmosphere", "sst"]
# (south, north, west, east) in degrees, east > west
Area = tuple[float, float, float, float]

# Bump when the written files change, so that converted folders are rebuilt
CONVERTER_VERSION = 1
# rrpr.F constants
GRAVITY = 9.81
LATENT_HEAT = 2.5e6
WATER_VAPOUR_GAS_CONSTANT = 461.5
# read_namelist.F: ungrib skips pressure levels above 1 hPa
PMIN_PA = 100.0
# Area margin kept around the outer domain, in degrees (at least five grid steps)
MARGIN_DEG = 1.0
# Slabs kept in memory while converting (daily SST serves several boundary times)
SLAB_CACHE = 256

TIME_DIMS = ("valid_time", "time", "t")
LEVEL_DIMS = ("pressure_level", "level", "isobaricInhPa", "plev", "lev")
LAT_NAMES = ("latitude", "lat")
LON_NAMES = ("longitude", "lon")


@dataclass(frozen=True)
class Source:
    """How a NetCDF variable becomes a WPS field."""

    names: tuple[str, ...]
    standard_names: tuple[str, ...]
    field: str
    kind: Kind
    # Units the variable is converted to before scaling
    units: str
    # Units and description of the field written
    wps_units: str
    description: str
    scale: float = 1.0
    # Read only to derive another field (the dew point gives the 2 m relative humidity)
    output: bool = True
    # On pressure levels (z on pressure levels is HGT, without levels SOILHGT)
    levels: bool = False


def _soil(prefix: str, number: int, name: str, units: str, wps_units: str, what: str) -> Source:
    return Source((f"{prefix}{number}",), (), name, "soil", units, wps_units, what)


SOURCES: tuple[Source, ...] = (
    Source(("z",), ("geopotential",), "HGT", "pressure", "m2 s-2", "m", "Height", 1 / GRAVITY, levels=True),
    Source(("gh",), ("geopotential_height",), "HGT", "pressure", "m", "m", "Height", levels=True),
    Source(("t",), ("air_temperature",), "TT", "pressure", "K", "K", "Temperature", levels=True),
    Source(("u",), ("eastward_wind",), "UU", "pressure", "m s-1", "m s-1", "U", levels=True),
    Source(("v",), ("northward_wind",), "VV", "pressure", "m s-1", "m s-1", "V", levels=True),
    Source(("r",), ("relative_humidity",), "RH", "pressure", "%", "%", "Relative Humidity", levels=True),
    Source(("q",), ("specific_humidity",), "SPECHUMD", "pressure", "kg kg-1", "kg kg-1",
           "Specific Humidity", levels=True),
    Source(("u10",), (), "UU", "surface", "m s-1", "m s-1", "U                    At 10 m"),
    Source(("v10",), (), "VV", "surface", "m s-1", "m s-1", "V                    At 10 m"),
    Source(("t2m",), (), "TT", "surface", "K", "K", "Temperature          At  2 m"),
    Source(("d2m",), (), "DEWPT", "surface", "K", "K", "", output=False),
    Source(("sp",), ("surface_air_pressure",), "PSFC", "surface", "Pa", "Pa", "Surface Pressure"),
    Source(("msl",), ("air_pressure_at_mean_sea_level",), "PMSL", "sea level", "Pa", "Pa",
           "Sea-level Pressure"),
    Source(("skt",), (), "SKINTEMP", "surface", "K", "K", "Sea-Surface Temperature"),
    Source(("sst", "analysed_sst"), ("sea_surface_temperature", "sea_surface_foundation_temperature"),
           "SST", "surface", "K", "K", "Sea-Surface Temperature"),
    Source(("lsm",), ("land_binary_mask",), "LANDSEA", "surface", "1", "0/1 Flag", "Land/Sea flag"),
    Source(("z",), ("surface_geopotential",), "SOILHGT", "surface", "m2 s-2", "m",
           "Terrain field of source analysis", 1 / GRAVITY),
    Source(("siconc", "ci"), ("sea_ice_area_fraction",), "SEAICE", "surface", "1", "0/1 Flag",
           "Sea-Ice-Flag"),
    Source(("sd",), ("lwe_thickness_of_surface_snow_amount",), "SNOW", "surface", "m", "kg m-2",
           "Water Equivalent of Accumulated Snow Depth", 1000.0),
    _soil("stl", 1, "ST000007", "K", "K", "T of 0-7 cm ground layer"),
    _soil("stl", 2, "ST007028", "K", "K", "T of 7-28 cm ground layer"),
    _soil("stl", 3, "ST028100", "K", "K", "T of 28-100 cm ground layer"),
    _soil("stl", 4, "ST100289", "K", "K", "T of 100-289 cm ground layer"),
    _soil("swvl", 1, "SM000007", "m3 m-3", "fraction", "Soil moisture of 0-7 cm ground layer"),
    _soil("swvl", 2, "SM007028", "m3 m-3", "fraction", "Soil moisture of 7-28 cm ground layer"),
    _soil("swvl", 3, "SM028100", "m3 m-3", "fraction", "Soil moisture of 28-100 cm ground layer"),
    _soil("swvl", 4, "SM100289", "m3 m-3", "fraction", "Soil moisture of 100-289 cm ground layer"),
)  # fmt: skip

# Spellings of units in ERA5 and CF files
UNIT_SPELLINGS = {
    "m2 s-2": "m2 s-2", "m s-1": "m s-1", "kg kg-1": "kg kg-1", "m3 m-3": "m3 m-3",
    "(0 - 1)": "1", "0 - 1": "1", "~": "1", "1": "1", "fraction": "1", "proportion": "1",
    "m of water equivalent": "m", "m": "m", "%": "%", "k": "K", "kelvin": "K",
    "degrees_kelvin": "K", "pa": "Pa", "hpa": "hPa", "millibars": "hPa", "mbar": "hPa",
    "degc": "degC", "celsius": "degC", "degrees_celsius": "degC",
}  # fmt: skip


def normalize_unit(text: str) -> str:
    compact = " ".join(text.replace("**", "").replace("^", "").split())
    return UNIT_SPELLINGS.get(compact.lower(), compact)


def unit_converter(found: str, expected: str) -> Callable[[np.ndarray], np.ndarray] | None:
    """Conversion from the file's units to the expected ones; None when not understood."""
    a, b = normalize_unit(found), normalize_unit(expected)
    if a == b:
        return lambda x: x
    try:
        return unit_conversion.converter(a, b)
    except unit_conversion.UnitError:
        return None


class NetcdfError(ValueError):
    """The files cannot be converted; the message says why."""


@dataclass
class Variable:
    """A recognised variable of one file."""

    path: Path
    name: str
    source: Source
    times: list[datetime]
    # Pressure levels in Pa, in the file's order (pressure fields only)
    levels_pa: list[float] | None
    dims: tuple[str, ...]
    time_dim: str
    level_dim: str | None
    units: str


@dataclass
class Content:
    """What one NetCDF file holds, from its metadata and coordinates."""

    path: Path
    variables: list[Variable] = field(default_factory=list)
    latitudes: np.ndarray = field(default_factory=lambda: np.zeros(0))
    longitudes: np.ndarray = field(default_factory=lambda: np.zeros(0))
    lat_name: str = ""
    lon_name: str = ""
    source: str = "NetCDF"
    ignored: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def _attribute(item: Any, name: str) -> str:
    try:
        return str(item.getncattr(name))
    except AttributeError:
        return ""


def _decode_times(variable: Any) -> list[datetime]:
    units = _attribute(variable, "units")
    calendar = _attribute(variable, "calendar") or "standard"
    values = netCDF4.num2date(
        variable[:],
        units,
        calendar,
        only_use_cftime_datetimes=False,
        only_use_python_datetimes=True,
    )
    dates = np.atleast_1d(np.asarray(values, dtype=object)).ravel()
    return [datetime(v.year, v.month, v.day, v.hour, v.minute, v.second) for v in dates]


def _levels_pa(variable: Any) -> list[float]:
    values = np.asarray(variable[:], dtype=float).ravel()
    units = normalize_unit(_attribute(variable, "units"))
    if units == "Pa" or (not units and values.max() > 1100):
        return [float(v) for v in values]
    return [float(v) * 100.0 for v in values]


def _recognise(name: str, variable: Any, has_levels: bool, role: Role) -> Source | None:
    standard = _attribute(variable, "standard_name")
    for source in SOURCES:
        if (role == "sst" and source.field != "SST") or source.levels != has_levels:
            continue
        if name in source.names or (standard and standard in source.standard_names):
            return source
    return None


def _source_name(dataset: Any) -> str:
    text = " ".join(str(dataset.getncattr(a)) for a in dataset.ncattrs()).lower()
    if "ecmwf" in text or "ecmf" in text or "european centre" in text:
        return "ECMWF"
    institution = _attribute(dataset, "institution")
    return institution[:32] if institution else "NetCDF"


def _variable(
    dataset: Any, content: Content, name: str, role: Role, times: dict[str, list[datetime]]
) -> Variable | str | None:
    """The variable if recognised, a problem, or None when it is not a field of interest."""
    variable = dataset.variables[name]
    dims = tuple(variable.dimensions)
    if content.lat_name not in dims or content.lon_name not in dims:
        return None
    time_dim = next((d for d in dims if d in TIME_DIMS), None)
    level_dim = next((d for d in dims if d in LEVEL_DIMS), None)
    source = _recognise(name, variable, level_dim is not None, role)
    if source is None or time_dim is None:
        return None
    file = content.path.name
    grid_dims = (time_dim, level_dim, content.lat_name, content.lon_name, "expver")
    extra = [d for d in dims if d not in grid_dims and len(dataset.dimensions[d]) > 1]
    if extra:
        return tr(
            f"{file}: {name} has the dimension {extra[0]}, which is not supported",
            f"{file} : {name} a la dimension {extra[0]}, non prise en charge",
        )
    if time_dim not in times:
        if time_dim not in dataset.variables:
            return tr(
                f"{file}: no coordinate for the time dimension {time_dim}",
                f"{file} : pas de coordonnée pour la dimension de temps {time_dim}",
            )
        times[time_dim] = _decode_times(dataset.variables[time_dim])
    units = _attribute(variable, "units") or source.units
    if unit_converter(units, source.units) is None:
        return tr(
            f"{file}: units {units!r} of {name} are not understood (expected {source.units})",
            f"{file} : unités {units!r} de {name} non comprises ({source.units} attendu)",
        )
    levels = None
    if level_dim is not None:
        if level_dim not in dataset.variables:
            return tr(
                f"{file}: no coordinate for the level dimension {level_dim}",
                f"{file} : pas de coordonnée pour la dimension des niveaux {level_dim}",
            )
        levels = _levels_pa(dataset.variables[level_dim])
    return Variable(
        content.path, name, source, times[time_dim], levels, dims, time_dim, level_dim, units
    )


@lru_cache(maxsize=1024)
def _scan(path: str, size: int, mtime_ns: int, role: Role) -> Content:
    content = Content(Path(path))
    with ncio.LOCK:
        return _scan_locked(content, path, role)


def _scan_locked(content: Content, path: str, role: Role) -> Content:
    file = content.path.name
    try:
        dataset = netCDF4.Dataset(path)
    except OSError as error:
        content.problems.append(f"{file}: cannot be read as NetCDF ({error})")
        return content
    with dataset:
        content.source = _source_name(dataset)
        names = dataset.variables
        content.lat_name = next((n for n in LAT_NAMES if n in names), "")
        content.lon_name = next((n for n in LON_NAMES if n in names), "")
        if not content.lat_name or not content.lon_name:
            content.problems.append(f"{file}: no latitude and longitude coordinates")
            return content
        lats, lons = names[content.lat_name], names[content.lon_name]
        if lats.ndim != 1 or lons.ndim != 1:
            content.problems.append(
                f"{file}: two-dimensional latitudes and longitudes are not supported "
                "(regular latitude-longitude grids only)"
            )
            return content
        content.latitudes = np.asarray(lats[:], dtype=float)
        content.longitudes = np.asarray(lons[:], dtype=float)
        times: dict[str, list[datetime]] = {}
        for name in names:
            if name in (content.lat_name, content.lon_name):
                continue
            found = _variable(dataset, content, name, role, times)
            if isinstance(found, Variable):
                content.variables.append(found)
            elif isinstance(found, str):
                content.problems.append(found)
            elif names[name].ndim >= 2:
                content.ignored.append(name)
    return content


def scan(path: Path, role: Role = "atmosphere") -> Content:
    """What a file holds (cached until it changes)."""
    stat = path.stat()
    return _scan(str(path.resolve()), stat.st_size, stat.st_mtime_ns, role)


# ------------------------------------------------------------------ the grid


@dataclass(frozen=True)
class Layout:
    """Rows and columns of a file's grid to write, south to north and west to east."""

    rows: np.ndarray
    columns: np.ndarray
    grid: LatLonGrid

    @property
    def shape(self) -> tuple[int, int]:
        return len(self.rows), len(self.columns)


def _regular_step(values: np.ndarray, what: str) -> float:
    if len(values) < 2:
        raise NetcdfError(
            tr(f"The {what} axis has a single value", f"L'axe {what} n'a qu'une valeur")
        )
    steps = np.diff(values)
    step = float(np.median(steps))
    if step <= 0 or np.max(np.abs(steps - step)) > 1e-3 * step + 1e-6:
        raise NetcdfError(
            tr(
                f"The {what} axis is not regularly spaced: only regular latitude-longitude grids "
                "are supported",
                f"L'axe {what} n'est pas régulier : seules les grilles latitude-longitude régulières sont acceptées",
            )
        )
    return step


def layout(latitudes: np.ndarray, longitudes: np.ndarray, area: Area | None = None) -> Layout:
    """The part of a grid to write: rows south to north, columns eastwards with continuous
    longitudes (a grid crossing 0° or 180° stays in one piece), limited to the area and a margin
    when one is given."""
    rows = np.argsort(latitudes, kind="stable")
    lats = latitudes[rows]
    dlat = _regular_step(lats, "latitude")
    if len(longitudes) < 2:
        raise NetcdfError(
            tr("The longitude axis has a single value", "L'axe des longitudes n'a qu'une valeur")
        )
    wrapped = np.mod(longitudes, 360.0)
    order = np.argsort(wrapped, kind="stable")
    ordered = wrapped[order]
    count = len(ordered)
    # Gaps between neighbours around the circle: one large gap outside a regional grid
    gaps = np.diff(np.concatenate([ordered, ordered[:1] + 360.0]))
    dlon = float(np.min(gaps) if count == 2 else np.median(gaps))
    whole = count * dlon >= 360.0 - 0.5 * dlon
    margin = max(MARGIN_DEG, 5 * dlat, 5 * dlon)
    if whole and area is not None:
        # A global grid starts just west of the area
        target = np.mod(area[2] - margin - dlon, 360.0)
        start = int(np.searchsorted(ordered, target, side="right") - 1) % count
    else:
        # A regional grid starts after its largest gap
        start = int((np.argmax(gaps) + 1) % count)
    columns = np.roll(order, -start)
    lons = np.mod(longitudes[columns], 360.0)
    lons = lons + 360.0 * np.concatenate([[0], np.cumsum(np.diff(lons) < 0)])
    _regular_step(lons, "longitude")
    if lons[0] >= 180.0:
        lons = lons - 360.0
    if area is not None:
        south, north, west, east = area
        keep_rows = (lats >= south - margin - dlat) & (lats <= north + margin + dlat)
        if keep_rows.any():
            rows, lats = rows[keep_rows], lats[keep_rows]
        half = (east - west) / 2
        centre = lons[0] + np.mod(west + half - lons[0], 360.0)
        keep = (lons >= centre - half - margin - dlon) & (lons <= centre + half + margin + dlon)
        if keep.any():
            columns, lons = columns[keep], lons[keep]
    return Layout(rows, columns, LatLonGrid(float(lats[0]), float(lons[0]), dlat, dlon))


# ---------------------------------------------------------------- the plan


@dataclass(frozen=True)
class Located:
    variable: Variable
    time_index: int
    level_index: int | None


Key = tuple[str, Kind]


@dataclass
class Plan:
    """Every field the files give: by field, level and time, where to read it."""

    contents: dict[Path, Content]
    fields: dict[Key, dict[float, dict[datetime, Located]]] = field(default_factory=dict)
    problems: list[str] = field(default_factory=list)
    ignored: set[str] = field(default_factory=set)

    def times(self, key: Key) -> set[datetime]:
        return {t for by_time in self.fields.get(key, {}).values() for t in by_time}

    def levels(self, key: Key) -> list[float]:
        return sorted(self.fields.get(key, {}), reverse=True)


def plan(paths: list[Path], role: Role = "atmosphere") -> Plan:
    contents = {p: scan(p, role) for p in paths}
    result = Plan(contents)
    for content in contents.values():
        result.problems += content.problems
        result.ignored |= set(content.ignored)
        for variable in content.variables:
            levels = result.fields.setdefault((variable.source.field, variable.source.kind), {})
            if variable.levels_pa is not None:
                pairs: list[tuple[float, int | None]] = [
                    (p, k) for k, p in enumerate(variable.levels_pa) if p >= PMIN_PA
                ]
            else:
                pseudo = SEA_LEVEL if variable.source.kind == "sea level" else SURFACE_LEVEL
                pairs = [(pseudo, None)]
            for level, level_index in pairs:
                by_time = levels.setdefault(level, {})
                for time_index, time in enumerate(variable.times):
                    by_time.setdefault(time, Located(variable, time_index, level_index))
    # Vtable.ECMWF reads RH, not specific humidity: SPECHUMD only when RH is absent
    if ("RH", "pressure") in result.fields:
        result.fields.pop(("SPECHUMD", "pressure"), None)
    return result


def bracket(times: list[datetime], wanted: datetime) -> tuple[datetime, datetime, float] | None:
    """The available times around ``wanted`` and the weight of the first (datint.F); the same
    time twice with weight 1 when present; None when ``wanted`` is outside the times."""
    if wanted in times:
        return wanted, wanted, 1.0
    before = [t for t in times if t < wanted]
    after = [t for t in times if t > wanted]
    if not before or not after:
        return None
    first, second = before[-1], after[0]
    weight = (second - wanted).total_seconds() / (second - first).total_seconds()
    return first, second, weight


# ---------------------------------------------------------------- reading


class Reader:
    """Open files, and their fields oriented, limited to the area and in the expected units."""

    def __init__(self, stack: ExitStack, the_plan: Plan, area: Area | None) -> None:
        self.stack = stack
        self.plan = the_plan
        self.area = area
        self.datasets: dict[Path, Any] = {}
        self.layouts: dict[Path, Layout] = {}
        self.cache: dict[tuple[Path, str, int, int | None], np.ndarray] = {}

    def _dataset(self, path: Path) -> Any:
        if path not in self.datasets:
            with ncio.LOCK:
                dataset = netCDF4.Dataset(str(path))
            self.stack.callback(_close, dataset)
            self.datasets[path] = dataset
        return self.datasets[path]

    def layout_of(self, path: Path) -> Layout:
        if path not in self.layouts:
            content = self.plan.contents[path]
            self.layouts[path] = layout(content.latitudes, content.longitudes, self.area)
        return self.layouts[path]

    def read(self, located: Located) -> np.ndarray:
        """One horizontal field, NaN where missing, converted and scaled."""
        variable = located.variable
        key = (variable.path, variable.name, located.time_index, located.level_index)
        if key in self.cache:
            return self.cache[key]
        content = self.plan.contents[variable.path]
        index: list[Any] = []
        for dim in variable.dims:
            if dim == variable.time_dim:
                index.append(located.time_index)
            elif dim == variable.level_dim:
                index.append(located.level_index)
            elif dim in (content.lat_name, content.lon_name, "expver"):
                index.append(slice(None))
            else:
                index.append(0)
        dataset = self._dataset(variable.path)
        with ncio.LOCK:
            raw = dataset.variables[variable.name][tuple(index)]
        array = np.ma.filled(np.ma.asarray(raw, dtype=float), np.nan)
        kept = [d for d in variable.dims if d in (content.lat_name, content.lon_name, "expver")]
        if "expver" in kept:
            # Legacy files mixing ERA5 and ERA5T: each point is given by one of them
            stacked = np.moveaxis(array, kept.index("expver"), 0)
            array = stacked[0]
            for other in stacked[1:]:
                array = np.where(np.isnan(array), other, array)
            kept.remove("expver")
        if kept.index(content.lat_name) > kept.index(content.lon_name):
            array = array.T
        grid = self.layout_of(variable.path)
        array = array[np.ix_(grid.rows, grid.columns)]
        convert = unit_converter(variable.units, variable.source.units)
        assert convert is not None
        result = np.asarray(convert(array), dtype=float) * variable.source.scale
        if variable.source.field == "LANDSEA":
            # rrpr.F make_zero_or_one, for ECMWF masks given as fractions
            result = np.where(np.isnan(result), result, (result > 0.5).astype(float))
        if len(self.cache) >= SLAB_CACHE:
            self.cache.clear()
        self.cache[key] = result
        return result


def _close(dataset: Any) -> None:
    with ncio.LOCK:
        dataset.close()


def _surface_rh(temperature: np.ndarray, dew_point: np.ndarray) -> np.ndarray:
    """rrpr.F compute_rh_dewpt."""
    with np.errstate(invalid="ignore", divide="ignore", over="ignore"):
        ratio = LATENT_HEAT / WATER_VAPOUR_GAS_CONSTANT * (1.0 / temperature - 1.0 / dew_point)
        rh: np.ndarray = np.exp(ratio) * 100.0
    return rh


def _interpolated(
    get: Callable[[datetime], np.ndarray], times: list[datetime], wanted: datetime, what: str
) -> np.ndarray:
    around = bracket(times, wanted)
    if around is None:
        raise NetcdfError(
            tr(
                f"No {what} data around {wanted:%Y-%m-%d %H:%M}",
                f"Aucune donnée {what} autour du {wanted:%d/%m/%Y %H:%M}",
            )
        )
    first, second, weight = around
    data = get(first)
    if weight < 1.0:
        data = weight * data + (1.0 - weight) * get(second)
    return data


def slabs_at(
    the_plan: Plan, reader: Reader, wanted: datetime, role: Role = "atmosphere"
) -> Iterator[Slab]:
    """Every field at one time, each interpolated in time when needed."""
    for key in sorted(the_plan.fields):
        name = key[0]
        if role == "sst" and name != "SST":
            continue
        for level, by_time in sorted(the_plan.fields[key].items(), reverse=True):
            first = next(iter(by_time.values()))
            source = first.variable.source
            if not source.output:
                continue

            def read_at(time: datetime, by_time: dict[datetime, Located] = by_time) -> np.ndarray:
                return reader.read(by_time[time])

            data = _interpolated(read_at, sorted(by_time), wanted, name)
            content = the_plan.contents[first.variable.path]
            grid = reader.layout_of(first.variable.path).grid
            yield Slab(
                wanted, name, source.wps_units, source.description, level, grid, data,
                content.source,
            )  # fmt: skip
    temperature = the_plan.fields.get(("TT", "surface"), {}).get(SURFACE_LEVEL, {})
    dew_point = the_plan.fields.get(("DEWPT", "surface"), {}).get(SURFACE_LEVEL, {})
    common = sorted(set(temperature) & set(dew_point))
    if role == "atmosphere" and common:
        # rrpr.F computes the 2 m RH at each available time; datint.F interpolates it
        rh = _interpolated(
            lambda t: _surface_rh(reader.read(temperature[t]), reader.read(dew_point[t])),
            common,
            wanted,
            "2 m humidity",
        )
        path = temperature[common[0]].variable.path
        yield Slab(
            wanted, "RH", "%", "Relative Humidity    At  2 m", SURFACE_LEVEL,
            reader.layout_of(path).grid, rh, the_plan.contents[path].source,
        )  # fmt: skip


# -------------------------------------------------------------- conversion


@dataclass
class Converted:
    folder: Path
    names: list[str]
    fields: int
    interpolated: list[datetime]


def output_names(prefix: str, times: list[datetime], interval_s: int) -> list[str]:
    """Names of the converted files on this computer: ':' is not allowed in Windows file names,
    so FILE_2025-10-01_00 stands for ungrib's FILE:2025-10-01_00 (the engine links them)."""
    return [f"{prefix}_{file_date(t, interval_s).replace(':', '-')}" for t in times]


def conversion_key(paths: list[Path], prefix: str, times: list[datetime], area: Area | None) -> str:
    """Identity of a conversion: files (names, sizes, dates), times, area and converter."""
    parts = [f"v{CONVERTER_VERSION}", prefix, json.dumps(area)]
    for path in sorted(paths):
        stat = path.stat()
        parts.append(f"{path.name}:{stat.st_size}:{stat.st_mtime_ns}")
    parts += [t.isoformat() for t in times]
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()[:20]


def convert(
    paths: list[Path],
    prefix: str,
    times: list[datetime],
    interval_s: int,
    folder: Path,
    area: Area | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> Converted:
    """Writes one intermediate file per time into ``folder``; a folder already complete for the
    same files, times and area is kept as it is."""
    role: Role = "sst" if prefix == "SST" else "atmosphere"
    key = conversion_key(paths, prefix, times, area)
    names = output_names(prefix, times, interval_s)
    marker = folder / ".complete"
    try:
        done = json.loads(marker.read_text(encoding="utf-8"))
        if done.get("key") == key and all((folder / n).exists() for n in names):
            interpolated = [datetime.fromisoformat(t) for t in done.get("interpolated", [])]
            return Converted(folder, names, int(done.get("fields", 0)), interpolated)
    except (OSError, ValueError):
        pass
    the_plan = plan(paths, role)
    if the_plan.problems:
        raise NetcdfError("; ".join(the_plan.problems))
    if not the_plan.fields:
        raise NetcdfError(
            tr(
                "No variable of the files is known to the conversion",
                "Aucune variable des fichiers n'est connue de la conversion",
            )
        )
    folder.mkdir(parents=True, exist_ok=True)
    marker.unlink(missing_ok=True)
    every = [the_plan.times(k) for k in the_plan.fields]
    interpolated = sorted({t for t in times for available in every if t not in available})
    total = 0
    with ExitStack() as stack:
        reader = Reader(stack, the_plan, area)
        for number, (time, name) in enumerate(zip(times, names, strict=True)):
            total += write(folder / name, slabs_at(the_plan, reader, time, role))
            if progress is not None:
                progress(number + 1, len(times))
    marker.write_text(
        json.dumps(
            {
                "key": key,
                "fields": total,
                "names": names,
                "interpolated": [t.isoformat() for t in interpolated],
            }
        ),
        encoding="utf-8",
    )
    return Converted(folder, names, total, interpolated)
