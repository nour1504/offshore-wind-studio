"""What ungrib will find in a folder of GRIB files, checked before a run.

The files are inventoried from their headers (grib.py) and every record is matched against the
chosen Vtable with the rules of WPS 4.7's ungrib (rd_grib1.F, rd_grib2.F): which fields and levels
it extracts, at which times, on which grids. The checks follow what stops the programs: the fields
METGRID.TBL marks mandatory, the inputs module_initialize_real.F cannot do without, and ungrib's
filling of missing times (datint.F interpolates a missing time only between two available ones,
so the first and the last time of the period must be present).

Folders of NetCDF files are examined from their variables (netcdf.py), with the same required
fields, levels and area; their conversion interpolates in time between any two available times.
"""

import itertools
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal

from owstudio.core.case.model import Case, GribInput
from owstudio.core.data import grib, netcdf, userfiles, vtables
from owstudio.core.domains import domain_outlines
from owstudio.core.i18n import tr

Severity = Literal["error", "warning", "info"]
Kind = Literal["pressure", "surface", "sea level", "model level", "soil", "other"]
Role = Literal["atmosphere", "sst"]

# read_namelist.F: by default ungrib skips pressure levels above 1 hPa
PMIN_PA = 100.0
# rd_grib1.F: GRIB1 level types whose second level ungrib takes as blank
GRIB1_SINGLE = {1, 100, 102, 103, 105, 107, 109, 111, 113, 115, 117, 119, 125, 160, 200, 201}
# rd_grib1.F: GRIB1 level types ungrib stores at the surface
GRIB1_SURFACE = {1, 105, 111, 112}
# rd_grib2.F: GRIB2 level types stored at the surface (2 and 10 m heights are handled apart)
GRIB2_SURFACE = {1, 6, 7, 10, 200, *range(206, 235), *range(242, 255)}
# module_initialize_real.F: land surface models that stop without two soil temperature levels
SOIL_SCHEMES = {2: "Noah", 3: "RUC", 4: "Noah-MP", 5: "CLM", 7: "Pleim-Xiu", 8: "SSiB"}
# Fewer pressure levels than this give a coarse vertical interpolation in real.exe
FEW_PRESSURE_LEVELS = 10
# Problems listed one by one; the others are counted
MAX_LISTED_PROBLEMS = 10


@dataclass(frozen=True)
class Finding:
    severity: Severity
    message: str


@dataclass(frozen=True)
class Key:
    """What identifies a field in a record header; records sharing a key differ by time only."""

    edition: int
    discipline: int
    category: int | None
    parameter: int
    level_type: int
    level1: float | None
    level2: float | None
    product: int


def key_of(record: grib.Record) -> Key:
    product = record.product if record.edition == 2 else 0
    return Key(
        record.edition, record.discipline, record.category, record.parameter,
        record.level_type, record.level1, record.level2, product,
    )  # fmt: skip


@dataclass
class Collected:
    """Records of all the files, grouped by key."""

    files: int = 0
    grib_files: int = 0
    messages: int = 0
    # GRIB files left for later (beyond the budget of a quick check), and their size
    deferred: int = 0
    deferred_bytes: int = 0
    times: dict[Key, set[datetime]] = field(default_factory=lambda: defaultdict(set))
    grids: dict[Key, set[grib.Grid]] = field(default_factory=lambda: defaultdict(set))
    editions: Counter[int] = field(default_factory=Counter)
    centres: Counter[str] = field(default_factory=Counter)
    problems: list[str] = field(default_factory=list)


def collect(files: list[userfiles.UserFile], budget_bytes: int | None = None) -> Collected:
    """Inventories of the GRIB files. With a budget, files not inventoried yet are read only when
    their total size fits in it; otherwise they are counted as deferred."""
    found = Collected(files=len(files))
    gribs = [f for f in files if f.format in ("grib1", "grib2")]
    found.grib_files = len(gribs)
    new = [f for f in gribs if grib.cached_inventory(f.path, compute=False) is None]
    compute = budget_bytes is None or sum(f.size for f in new) <= budget_bytes
    for user_file in gribs:
        inventory = grib.cached_inventory(user_file.path, compute=compute)
        if inventory is None:
            found.deferred += 1
            found.deferred_bytes += user_file.size
            continue
        found.problems += [f"{user_file.name}: {p}" for p in inventory.problems]
        for record in inventory.records:
            key = key_of(record)
            found.messages += 1
            found.times[key].add(record.valid)
            found.grids[key].add(record.grid)
            found.editions[record.edition] += 1
            found.centres[grib.CENTRES.get(record.centre, f"centre {record.centre}")] += 1
    return found


# ---------------------------------------------------------------- matching


@dataclass(frozen=True)
class Placement:
    """Where ungrib stores the records of a key: table row, kind of level and level."""

    entry: vtables.Entry
    kind: Kind
    level: float


def _grib1_placement(key: Key, table: list[vtables.Entry]) -> Placement | str | None:
    """rd_grib1.F: the row matching the parameter, the level type and the levels, and the level
    the field is stored at. A string is the reason ungrib stops."""
    ktype = key.level_type
    raw1 = key.level1 if key.level1 is not None else 0.0
    if ktype == 100:
        lvl1 = raw1 * 100.0
    elif ktype in (200, 201):
        lvl1 = 0.0
    else:
        lvl1 = raw1
    if ktype in GRIB1_SINGLE:
        lvl2 = float(vtables.BLANK)
    else:
        lvl2 = key.level2 if key.level2 is not None else 0.0
    for entry in table:
        if entry.grib1_param != key.parameter or entry.grib1_level_type != ktype:
            continue
        if entry.level1 not in (vtables.EVERY_LEVEL, lvl1) or entry.level2 != lvl2:
            continue
        if ktype == 100:
            return None if lvl1 < PMIN_PA else Placement(entry, "pressure", lvl1)
        if ktype == 102:
            return Placement(entry, "sea level", 201300.0)
        if ktype in GRIB1_SURFACE or (ktype == 116 and lvl1 <= 50 and lvl2 == 0):
            return Placement(entry, "soil" if ktype == 112 else "surface", 200100.0)
        if ktype in (107, 109):
            return Placement(entry, "model level", lvl1)
        if ktype in (6, 7, 160, 200, 237, 238):
            return Placement(entry, "other", lvl1)
        return tr(
            f"GRIB1 level type {ktype} of {entry.name} (Vtable line {entry.line}) is not "
            "handled by ungrib, which stops",
            f"le type de niveau GRIB1 {ktype} de {entry.name} (ligne {entry.line} de la Vtable) "
            "n'est pas traité par ungrib, qui s'arrête",
        )
    return None


def _grib2_placement(key: Key, table: list[vtables.Entry]) -> Placement | None:
    """rd_grib2.F: the row matching discipline, category, parameter, level type and product
    template, with its handling of soil layers, heights and pressure levels."""
    codes = (key.discipline, key.category, key.parameter, key.level_type)
    candidates = [e for e in table if e.grib2 == codes and e.grib2_template == key.product]
    if not candidates:
        return None
    ltype = key.level_type
    if ltype == 106:
        # Soil layers: top and bottom depths in cm, matched against the levels of the rows
        top = round(100 * (key.level1 or 0.0))
        bottom = round(100 * (key.level2 or 0.0))
        for entry in table:
            if (
                entry.grib2[3] == 106
                and entry.grib2[1:3] == (key.category, key.parameter)
                and entry.level1 == top
                and (entry.level2 == bottom or entry.level2 <= vtables.EVERY_LEVEL)
            ):
                return Placement(entry, "soil", 200100.0)
        return None
    entry = candidates[0]
    level = key.level1 if key.level1 is not None else 0.0
    if ltype == 100:
        return None if level < PMIN_PA else Placement(entry, "pressure", level)
    if ltype in (104, 105, 118, 150):
        return Placement(entry, "model level", level)
    if ltype == 101:
        return Placement(entry, "sea level", 201300.0)
    if ltype == 103:
        return Placement(entry, "surface", 200100.0) if level in (2.0, 10.0, 1000.0) else None
    if ltype in GRIB2_SURFACE:
        return Placement(entry, "surface", 200100.0)
    return None


def placement(key: Key, table: list[vtables.Entry]) -> Placement | str | None:
    """Where ungrib stores records with this header under this table; None when it skips them,
    a string when it stops on them."""
    return _grib1_placement(key, table) if key.edition == 1 else _grib2_placement(key, table)


@dataclass
class FieldFound:
    name: str
    kind: Kind
    levels: set[float] = field(default_factory=set)
    times: set[datetime] = field(default_factory=set)
    output: bool = True


@dataclass
class Matched:
    fields: dict[tuple[str, Kind], FieldFound] = field(default_factory=dict)
    unused_messages: int = 0
    stops: list[str] = field(default_factory=list)
    grids: set[grib.Grid] = field(default_factory=set)

    def names(self) -> set[str]:
        return {name for name, _ in self.fields}

    def times_of(self, names: set[str], kinds: tuple[Kind, ...] | None = None) -> set[datetime]:
        times: set[datetime] = set()
        for (name, kind), found in self.fields.items():
            if name in names and (kinds is None or kind in kinds):
                times |= found.times
        return times

    def all_times(self) -> set[datetime]:
        return {t for found in self.fields.values() for t in found.times}


def match(collected: Collected, table: list[vtables.Entry]) -> Matched:
    result = Matched()
    for key, times in collected.times.items():
        where = placement(key, table)
        if isinstance(where, str):
            if where not in result.stops:
                result.stops.append(where)
            continue
        if where is None:
            result.unused_messages += len(times)
            continue
        entry = where.entry
        found = result.fields.setdefault(
            (entry.name, where.kind),
            FieldFound(entry.name, where.kind, output=entry.output),
        )
        found.levels.add(where.level)
        found.times |= times
        result.grids |= collected.grids[key]
    return result


# ------------------------------------------------------------ requirements

UPPER: tuple[Kind, ...] = ("pressure", "model level")
# Soil fields are named by prefix and layer (ST000007, SOILT010...)
SOIL_PREFIXES = ("ST", "SM", "SOILT", "SOILM")


@dataclass(frozen=True)
class Requirement:
    """Fields of which one must be present, in any of the listed kinds of level."""

    label: str
    any_of: tuple[str, ...]
    kinds: tuple[Kind, ...]
    severity: Severity
    why: str


def requirements(sf_surface_physics: int | None, smooth_cg_topo: bool) -> list[Requirement]:
    mandatory = tr(
        "metgrid stops without it (mandatory in METGRID.TBL)",
        "metgrid s'arrête sans lui (obligatoire dans METGRID.TBL)",
    )
    found = [
        Requirement(tr("temperature", "température"), ("TT",), UPPER, "error", mandatory),
        Requirement(tr("wind U", "vent U"), ("UU",), UPPER, "error", mandatory),
        Requirement(tr("wind V", "vent V"), ("VV",), UPPER, "error", mandatory),
        Requirement(
            tr("humidity", "humidité"),
            ("RH", "SPECHUMD", "QV", "DEWPT"),
            UPPER,
            "error",
            tr(
                "without it the run would start with dry air",
                "sans elle le calcul partirait d'un air sec",
            ),
        ),
        Requirement(
            tr("surface or sea-level pressure", "pression en surface ou au niveau de la mer"),
            ("PSFC", "PMSL"),
            ("surface", "sea level"),
            "error",
            tr(
                "real.exe stops, not having enough information to compute the surface pressure",
                "real.exe s'arrête, faute d'informations pour calculer la pression en surface",
            ),
        ),
        Requirement(
            tr("geopotential height", "hauteur géopotentielle"),
            ("HGT", "GEOPT"),
            UPPER,
            "warning",
            tr(
                "real.exe uses it to compute the surface pressure and the lowest levels",
                "real.exe s'en sert pour calculer la pression en surface et les niveaux les plus bas",
            ),
        ),
        Requirement(
            tr("skin temperature", "température de surface"),
            ("SKINTEMP",),
            ("surface",),
            "warning",
            tr(
                "WRF's surface temperature (TSK) comes from it",
                "la température de surface de WRF (TSK) en vient",
            ),
        ),
        Requirement(
            tr("land-sea mask", "masque terre-mer"),
            ("LANDSEA",),
            ("surface",),
            "warning",
            tr(
                "metgrid uses it to keep sea values over the sea and land values over land",
                "metgrid s'en sert pour garder les valeurs de mer sur la mer et celles de terre sur la terre",
            ),
        ),
        Requirement(
            tr("2 m temperature", "température à 2 m"),
            ("TT",),
            ("surface",),
            "warning",
            tr(
                "it gives the near-surface temperature",
                "elle donne la température près de la surface",
            ),
        ),
        Requirement(
            tr("10 m wind", "vent à 10 m"),
            ("UU",),
            ("surface",),
            "warning",
            tr("it gives the near-surface wind", "il donne le vent près de la surface"),
        ),
    ]
    if sf_surface_physics in SOIL_SCHEMES:
        scheme = SOIL_SCHEMES[sf_surface_physics]
        found += [
            Requirement(
                tr("soil temperature", "température du sol"),
                ("ST", "SOILT"),
                ("soil", "surface"),
                "error",
                tr(
                    f"real.exe stops without soil temperature on at least 2 levels for the {scheme} land surface model",
                    f"real.exe s'arrête sans température du sol sur au moins 2 niveaux pour le modèle de sol {scheme}",
                ),
            ),
            Requirement(
                tr("soil moisture", "humidité du sol"),
                ("SM", "SOILM"),
                ("soil", "surface"),
                "warning",
                tr(
                    f"the {scheme} land surface model starts from it",
                    f"le modèle de sol {scheme} part d'elle",
                ),
            ),
        ]
    found.append(
        Requirement(
            tr("terrain height of the source", "relief de la source"),
            ("SOILHGT", "SOILGEO"),
            ("surface",),
            "error" if smooth_cg_topo else "warning",
            tr("real.exe needs it with smooth_cg_topo", "real.exe en a besoin avec smooth_cg_topo")
            if smooth_cg_topo
            else tr(
                "real.exe uses it to adjust the soil temperature to the model terrain",
                "real.exe s'en sert pour ajuster la température du sol au relief du modèle",
            ),
        )
    )
    return found


def present(matched: Matched, requirement: Requirement) -> set[str]:
    """Names found for a requirement."""
    found = set()
    for name, kind in matched.fields:
        if kind not in requirement.kinds:
            continue
        for wanted in requirement.any_of:
            layered = wanted in SOIL_PREFIXES and name.startswith(wanted)
            if name == wanted or (layered and name[len(wanted) :][:1].isdigit()):
                found.add(name)
    return found


# ------------------------------------------------------------------- times


def utc_naive(time: datetime) -> datetime:
    return time.astimezone(UTC).replace(tzinfo=None) if time.tzinfo else time


def requested_times(start: datetime, end: datetime, interval_s: int) -> list[datetime]:
    """The times ungrib looks for: from the start every interval_seconds up to the end."""
    step = timedelta(seconds=interval_s)
    count = int((end - start) / step)
    return [start + k * step for k in range(count + 1)]


def _fmt(time: datetime) -> str:
    return time.strftime("%Y-%m-%d %H:%M")


def _list(times: list[datetime], limit: int = 4) -> str:
    shown = ", ".join(_fmt(t) for t in times[:limit])
    return shown + (f" and {len(times) - limit} more" if len(times) > limit else "")


def _hours(seconds: float) -> str:
    return f"{seconds / 3600:g} h"


def time_findings(available: set[datetime], wanted: list[datetime], what: str) -> list[Finding]:
    """datint.F: a time absent from the data is interpolated only between two available times."""
    findings = []
    missing = [t for t in wanted if t not in available]
    ends = [t for t in missing if t in (wanted[0], wanted[-1])]
    inner = [t for t in missing if t not in ends]
    if ends:
        findings.append(
            Finding(
                "error",
                tr(
                    f"{what}: no data at {_list(ends)}. ungrib needs the first and the last time of "
                    "the period (otherwise it stops with 'Data not found').",
                    f"{what} : aucune donnée à {_list(ends)}. ungrib a besoin du premier et du dernier instant de la période (sinon il s'arrête avec 'Data not found').",
                ),
            )
        )
    if inner:
        findings.append(
            Finding(
                "warning",
                tr(
                    f"{what}: {len(inner)} time(s) missing ({_list(inner)}); ungrib interpolates "
                    "them linearly in time between the surrounding times.",
                    f"{what} : {len(inner)} instant(s) manquant(s) ({_list(inner)}) ; ungrib les interpole linéairement dans le temps entre les instants voisins.",
                ),
            )
        )
    first, last = wanted[0], wanted[-1]
    off_step = sorted(
        t
        for t in available
        if first < t < last and (t - first).total_seconds() % (wanted[1] - first).total_seconds()
    ) if len(wanted) > 1 else []  # fmt: skip
    if off_step and inner:
        findings.append(
            Finding(
                "warning",
                tr(
                    f"{what}: the data also have times between the boundary times ({_list(off_step)}); "
                    "next to a missing time, ungrib may try to interpolate from them and fail. "
                    "Remove these times or fill the missing ones.",
                    f"{what} : les données ont aussi des instants entre ceux des frontières ({_list(off_step)}) ; à côté d'un instant manquant, ungrib peut essayer d'interpoler à partir d'eux et échouer. Retirez ces instants ou complétez ceux qui manquent.",
                ),
            )
        )
    return findings


def converted_time_findings(
    available: set[datetime], wanted: list[datetime], what: str, sst: bool = False
) -> list[Finding]:
    """NetCDF files: the conversion interpolates any time between two available ones."""
    ordered = sorted(available)
    missing = [t for t in wanted if t not in available]
    outside = [t for t in missing if netcdf.bracket(ordered, t) is None]
    inner = [t for t in missing if t not in outside]
    findings = []
    if outside:
        findings.append(
            Finding(
                "error",
                tr(
                    f"{what}: no data before or after {_list(outside)}: the files must cover the "
                    f"whole period ({_fmt(wanted[0])} to {_fmt(wanted[-1])}).",
                    f"{what} : aucune donnée avant ou après {_list(outside)} : les fichiers doivent couvrir toute la période ({_fmt(wanted[0])} à {_fmt(wanted[-1])}).",
                ),
            )
        )
    if inner:
        findings.append(
            Finding(
                "info" if sst else "warning",
                tr(
                    f"{what}: {len(inner)} time(s) of the run fall between the times of the files "
                    f"({_list(inner)}); they are interpolated linearly in time, as ungrib would.",
                    f"{what} : {len(inner)} instant(s) du calcul tombent entre ceux des fichiers ({_list(inner)}) ; ils sont interpolés linéairement dans le temps, comme le ferait ungrib.",
                ),
            )
        )
    return findings


def sst_window(
    available: set[datetime], start: datetime, end: datetime, interval_s: int
) -> tuple[datetime, datetime] | None:
    """Period of the SST pass of ungrib: from the last SST time at or before the start to the
    first at or after the end, on the boundary interval, so that every time of the run is either
    present or interpolated between two SST times. None when the data do not reach both ends."""
    aligned = sorted(t for t in available if (t - start).total_seconds() % interval_s == 0)
    before = [t for t in aligned if t <= start]
    after = [t for t in aligned if t >= end]
    if not before or not after:
        return None
    return before[-1], after[0]


# ------------------------------------------------------------------- space


@dataclass(frozen=True)
class Box:
    south: float
    north: float
    west: float
    east: float


def outline_box(outline: list[tuple[float, float]]) -> Box:
    """Bounds of an outline of (lon, lat) points, longitudes kept continuous across 180°."""
    reference = outline[0][0]
    lons = [reference + ((lon - reference + 180.0) % 360.0 - 180.0) for lon, _ in outline]
    lats = [lat for _, lat in outline]
    return Box(min(lats), max(lats), min(lons), max(lons))


def space_findings(grids: set[grib.Grid], domain: Box, what: str) -> list[Finding]:
    findings: list[Finding] = []
    for grid in sorted(grids, key=lambda g: g.describe()):
        bounds = grid.bounds()
        if bounds is None:
            if grid.template >= 0:
                findings.append(
                    Finding(
                        "info",
                        tr(
                            f"{what}: the {grid.kind} grid of the data is not checked against the domains.",
                            f"{what} : la grille {grid.kind} des données n'est pas comparée aux domaines.",
                        ),
                    )
                )
            continue
        south, north, west, east = bounds
        step = max(grid.di or 0.0, grid.dj or 0.0)
        whole_lon = bool(grid.ni and grid.di and grid.ni * grid.di >= 360.0 - 1.5 * grid.di)
        # The domain's longitudes brought into the data's longitude range
        shift = 360.0 * math.floor((domain.west - west) / 360.0)
        dwest, deast = domain.west - shift, domain.east - shift
        problems = []
        if domain.south < south or domain.north > north:
            problems.append(
                tr(
                    f"latitudes {domain.south:.2f}° to {domain.north:.2f}° (data {south:.2f}° to {north:.2f}°)",
                    f"latitudes {domain.south:.2f}° à {domain.north:.2f}° (données {south:.2f}° à {north:.2f}°)",
                )
            )
        if not whole_lon and (dwest < west or deast > east):
            problems.append(
                tr(
                    f"longitudes {domain.west:.2f}° to {domain.east:.2f}° (data {west:.2f}° to {east:.2f}°)",
                    f"longitudes {domain.west:.2f}° à {domain.east:.2f}° (données {west:.2f}° à {east:.2f}°)",
                )
            )
        if problems:
            findings.append(
                Finding(
                    "error",
                    tr(
                        f"{what}: the outer domain extends beyond the data on {grid.describe()} "
                        f"({'; '.join(problems)}). Use data covering a larger area or move the domain.",
                        f"{what} : le domaine extérieur dépasse les données sur {grid.describe()} ({'; '.join(problems)}). Utilisez des données couvrant une zone plus grande ou déplacez le domaine.",
                    ),
                )
            )
            continue
        margins = [domain.south - south, north - domain.north]
        if not whole_lon:
            margins += [dwest - west, east - deast]
        if step and min(margins) < 2 * step:
            findings.append(
                Finding(
                    "warning",
                    tr(
                        f"{what}: the outer domain comes within two grid steps ({step:g}°) of the edge "
                        "of the data, where metgrid falls back to simpler interpolations; a margin of "
                        "a few grid steps is safer.",
                        f"{what} : le domaine extérieur arrive à moins de deux pas de grille ({step:g}°) du bord des données, où metgrid passe à des interpolations plus simples ; une marge de quelques pas est plus sûre.",
                    ),
                )
            )
    return findings


# ------------------------------------------------------------------ report


@dataclass
class FieldSummary:
    name: str
    kind: Kind
    levels: int
    times: int
    output: bool


@dataclass
class Suggestion:
    vtable: str
    fields: int
    required_ok: bool
    used_share: float


@dataclass
class Examination:
    role: Role
    folder: str
    pattern: str
    vtable: str
    # "grib" files read by ungrib, or "netcdf" files converted before the run
    format: str = "grib"
    files: int = 0
    grib_files: int = 0
    messages: int = 0
    editions: list[int] = field(default_factory=list)
    centres: list[str] = field(default_factory=list)
    grids: list[str] = field(default_factory=list)
    first: datetime | None = None
    last: datetime | None = None
    times: int = 0
    step_hours: float | None = None
    fields: list[FieldSummary] = field(default_factory=list)
    unused_messages: int = 0
    pressure_levels_hpa: list[float] = field(default_factory=list)
    soil_fields: list[str] = field(default_factory=list)
    # Period of the SST pass of ungrib, when it must be wider than the run's
    window: tuple[datetime, datetime] | None = None
    suggestions: list[Suggestion] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    @property
    def errors(self) -> list[str]:
        return [f.message for f in self.findings if f.severity == "error"]


@dataclass(frozen=True)
class Context:
    """What the checks need to know about the case."""

    start: datetime
    end: datetime
    interval_s: int
    domain: Box | None = None
    sf_surface_physics: int | None = 2
    smooth_cg_topo: bool = False
    p_top_pa: float = 5000.0


def _step_hours(times: list[datetime]) -> float | None:
    if len(times) < 2:
        return None
    steps = Counter((b - a).total_seconds() / 3600 for a, b in itertools.pairwise(times))
    return steps.most_common(1)[0][0]


def _table_text(settings: GribInput) -> str:
    if settings.vtable == "custom":
        return settings.custom_vtable
    return vtables.read(settings.vtable) if settings.vtable in vtables.names() else ""


def _check_atmosphere(
    matched: Matched, context: Context, what: str, converted: bool = False
) -> list[Finding]:
    """Required fields, levels and times; ``converted`` for NetCDF files, which the conversion
    interpolates in time field by field."""
    findings: list[Finding] = []
    wanted = requested_times(context.start, context.end, context.interval_s)
    available = matched.all_times()
    where = (
        tr("in the NetCDF files", "dans les fichiers NetCDF")
        if converted
        else tr("with this Vtable", "avec cette Vtable")
    )
    for requirement in requirements(context.sf_surface_physics, context.smooth_cg_topo):
        names = present(matched, requirement)
        if not names:
            findings.append(
                Finding(
                    requirement.severity,
                    tr(
                        f"{what}: no {requirement.label} ({' or '.join(requirement.any_of)}) found "
                        f"{where}: {requirement.why}.",
                        f"{what} : aucun champ {requirement.label} ({' ou '.join(requirement.any_of)}) trouvé {where} : {requirement.why}.",
                    ),
                )
            )
            continue
        if requirement.label == "soil temperature" and len(names) < 2:
            findings.append(
                Finding(
                    "error",
                    tr(
                        f"{what}: soil temperature on one level only: {requirement.why}.",
                        f"{what} : température du sol sur un seul niveau : {requirement.why}.",
                    ),
                )
            )
        if requirement.severity == "error":
            times = matched.times_of(names, requirement.kinds)
            if converted:
                ordered = sorted(times)
                partial = [t for t in wanted if netcdf.bracket(ordered, t) is None]
            else:
                partial = [t for t in wanted if t in available and t not in times]
            if partial:
                findings.append(
                    Finding(
                        "error",
                        tr(
                            f"{what}: {requirement.label} missing at {_list(partial)} while other "
                            "fields are there; metgrid or real.exe would stop at these times.",
                            f"{what} : {requirement.label} manque à {_list(partial)} alors que d'autres champs sont là ; metgrid ou real.exe s'arrêteraient à ces instants.",
                        ),
                    )
                )
    levels = {
        level
        for (name, kind), found in matched.fields.items()
        if kind == "pressure" and name == "TT"
        for level in found.levels
    }
    if levels and len(levels) < FEW_PRESSURE_LEVELS:
        findings.append(
            Finding(
                "warning",
                tr(
                    f"{what}: only {len(levels)} pressure levels; the vertical interpolation of "
                    "real.exe will be coarse.",
                    f"{what} : seulement {len(levels)} niveaux de pression ; l'interpolation verticale de real.exe sera grossière.",
                ),
            )
        )
    if levels and min(levels) > context.p_top_pa:
        findings.append(
            Finding(
                "error",
                tr(
                    f"{what}: the highest pressure level is {min(levels) / 100:g} hPa, below the model "
                    f"top of {context.p_top_pa / 100:g} hPa (p_top_requested): real.exe stops. Use data "
                    "with higher levels or lower the model top.",
                    f"{what} : le niveau de pression le plus haut est à {min(levels) / 100:g} hPa, sous le sommet du modèle à {context.p_top_pa / 100:g} hPa (p_top_requested) : real.exe s'arrête. Utilisez des données montant plus haut ou baissez le sommet du modèle.",
                ),
            )
        )
    if converted:
        findings += converted_time_findings(available, wanted, what)
    else:
        findings += time_findings(available, wanted, what)
    return findings


def _check_sst(matched: Matched, context: Context, report: Examination, what: str) -> list[Finding]:
    sst_times = matched.times_of({"SST"})
    if not sst_times:
        names = ", ".join(sorted(matched.names()))
        return [
            Finding(
                "error",
                tr(
                    f"{what}: no SST field found with this Vtable (it reads {names}).",
                    f"{what} : aucun champ SST trouvé avec cette Vtable (elle lit {names}).",
                ),
            )
        ]
    window = sst_window(sst_times, context.start, context.end, context.interval_s)
    if window is None:
        return [
            Finding(
                "error",
                tr(
                    f"{what}: the SST data ({_fmt(min(sst_times))} to {_fmt(max(sst_times))}) must "
                    f"have a time at or before the start ({_fmt(context.start)}) and one at or after "
                    f"the end ({_fmt(context.end)}), on the {_hours(context.interval_s)} steps of the "
                    "boundary data.",
                    f"{what} : les données SST ({_fmt(min(sst_times))} à {_fmt(max(sst_times))}) doivent avoir un instant au début ({_fmt(context.start)}) ou avant, et un à la fin ({_fmt(context.end)}) ou après, sur les pas de {_hours(context.interval_s)} des données aux frontières.",
                ),
            )
        ]
    report.window = window
    wanted = requested_times(window[0], window[1], context.interval_s)
    findings = time_findings(sst_times, wanted, what)
    missing = [t for t in wanted if t not in sst_times]
    if missing and not any(f.severity == "error" for f in findings):
        # Daily SST with 6-hourly boundaries: expected, interpolation is the normal treatment
        findings = [
            Finding(
                "info",
                tr(
                    f"{what}: SST every {_hours((report.step_hours or 0) * 3600)}; ungrib interpolates "
                    f"it linearly to the {_hours(context.interval_s)} boundary times.",
                    f"{what} : SST toutes les {_hours((report.step_hours or 0) * 3600)} ; ungrib l'interpole linéairement aux instants des frontières (toutes les {_hours(context.interval_s)}).",
                ),
            )
        ]
    return findings


def vtable_findings(settings: GribInput, what: str) -> list[Finding]:
    """Whether ungrib can read the chosen table."""
    if settings.vtable == "custom":
        return [
            Finding("error", tr(f"{what}, custom Vtable: {p}", f"{what}, Vtable personnelle : {p}"))
            for p in vtables.validate(settings.custom_vtable)
        ]
    if settings.vtable not in vtables.names():
        return [
            Finding(
                "error",
                tr(
                    f"{what}: unknown Vtable {settings.vtable!r}; choose a WPS table or a custom one.",
                    f"{what} : Vtable inconnue {settings.vtable!r} ; choisissez une table de WPS ou une table personnelle.",
                ),
            )
        ]
    return []


def _netcdf_grid(content: netcdf.Content) -> grib.Grid:
    """The grid of a NetCDF file as a GRIB lat-lon grid, south to north and eastwards."""
    found = netcdf.layout(content.latitudes, content.longitudes)
    ny, nx = found.shape
    g = found.grid
    return grib.Grid(
        0, ni=nx, nj=ny, lat1=g.start_lat, lon1=g.start_lon,
        lat2=g.start_lat + (ny - 1) * g.dlat, lon2=g.start_lon + (nx - 1) * g.dlon,
        di=g.dlon, dj=g.dlat, scanning=0x40,
    )  # fmt: skip


def _examine_netcdf(
    files: list[userfiles.UserFile], role: Role, context: Context, report: Examination, what: str
) -> Examination:
    """NetCDF files: what the conversion will write, with the same checks as for ungrib."""
    report.format = "netcdf"
    the_plan = netcdf.plan([f.path for f in files], role)
    report.findings += [
        Finding("error", f"{what}: {p}") for p in the_plan.problems[:MAX_LISTED_PROBLEMS]
    ]
    report.centres = sorted({c.source for c in the_plan.contents.values() if c.variables})
    matched = Matched()
    for key, levels in the_plan.fields.items():
        first = next(iter(next(iter(levels.values())).values()))
        matched.fields[key] = FieldFound(
            key[0], key[1], set(levels), the_plan.times(key), first.variable.source.output
        )
    report.messages = sum(len(t) for levels in the_plan.fields.values() for t in levels.values())
    for content in the_plan.contents.values():
        if content.variables:
            try:
                matched.grids.add(_netcdf_grid(content))
            except netcdf.NetcdfError as error:
                report.findings.append(Finding("error", f"{what}: {content.path.name}: {error}"))
    report.grids = sorted(g.describe() for g in matched.grids)
    every_time = sorted(matched.all_times())
    if every_time:
        report.first, report.last, report.times = every_time[0], every_time[-1], len(every_time)
        report.step_hours = _step_hours(every_time)
    _summarise(report, matched)
    if not matched.fields:
        ignored = ", ".join(sorted(the_plan.ignored)[:8]) or "none"
        report.findings.append(
            Finding(
                "error",
                tr(
                    f"{what}: no variable of the NetCDF files is known to the conversion "
                    f"(variables found: {ignored}).",
                    f"{what} : aucune variable des fichiers NetCDF n'est connue de la conversion (variables trouvées : {ignored}).",
                ),
            )
        )
        return report
    report.findings.append(
        Finding(
            "info",
            tr(
                f"{what}: NetCDF files, converted on this computer at export into WPS intermediate "
                "files of the package (wps/intermediate/); metgrid reads them, the Vtable is not used.",
                f"{what} : fichiers NetCDF, convertis sur cet ordinateur à l'export en fichiers intermédiaires de WPS du paquet (wps/intermediaires/) ; metgrid les lit, la Vtable n'est pas utilisée.",
            ),
        )
    )
    if role == "sst":
        sst_times = matched.times_of({"SST"})
        wanted = requested_times(context.start, context.end, context.interval_s)
        report.findings += converted_time_findings(sst_times, wanted, what, sst=True)
    else:
        report.findings += _check_atmosphere(matched, context, what, converted=True)
    if context.domain is not None:
        report.findings += space_findings(matched.grids, context.domain, what)
    return report


def _summarise(report: Examination, matched: Matched) -> None:
    report.fields = sorted(
        (
            FieldSummary(f.name, f.kind, len(f.levels), len(f.times), f.output)
            for f in matched.fields.values()
        ),
        key=lambda s: (s.kind, s.name),
    )
    report.pressure_levels_hpa = sorted(
        {
            level / 100
            for (_, kind), found in matched.fields.items()
            if kind == "pressure"
            for level in found.levels
        },
        reverse=True,
    )
    report.soil_fields = sorted(name for (name, kind) in matched.fields if kind == "soil")


def examine(
    settings: GribInput,
    role: Role,
    context: Context,
    with_suggestions: bool = False,
    budget_bytes: int | None = None,
) -> Examination:
    """Everything ungrib will find in the files, and the problems it, metgrid or real.exe would
    meet. With a budget, large folders not examined yet are only listed (quick checks)."""
    what = (
        tr("SST files", "Fichiers SST") if role == "sst" else tr("Input files", "Fichiers d'entrée")
    )
    report = Examination(role, settings.folder, settings.pattern, settings.vtable)
    try:
        files = userfiles.list_files(settings.folder, settings.pattern, sniff_all=True)
    except userfiles.TooManyFiles as error:
        report.findings.append(Finding("error", tr(f"{what}: {error}", f"{what} : {error}")))
        return report
    except FileNotFoundError:
        report.findings.append(
            Finding(
                "error",
                tr(
                    f"{what}: folder not found on this computer: {settings.folder}",
                    f"{what} : dossier introuvable sur cet ordinateur : {settings.folder}",
                ),
            )
        )
        return report
    report.findings += [Finding("error", p) for p in userfiles.problems(files, what)]
    report.findings += [Finding("warning", p) for p in userfiles.repeated_names(files, what)]
    if userfiles.all_netcdf(files):
        report.files = len(files)
        return _examine_netcdf(files, role, context, report, what)
    vtable_problems = vtable_findings(settings, what)
    if vtable_problems:
        report.findings += vtable_problems
        return report
    collected = collect(files, budget_bytes)
    report.files, report.grib_files = collected.files, collected.grib_files
    report.messages = collected.messages
    if collected.deferred:
        report.findings.append(
            Finding(
                "info",
                tr(
                    f"{what}: {collected.deferred} file(s) ({collected.deferred_bytes / 1e9:.1f} GB) "
                    "not examined yet. They are examined when the run is launched, or now from the "
                    "Data page.",
                    f"{what} : {collected.deferred} fichier(s) ({collected.deferred_bytes / 1e9:.1f} Go) pas encore examiné(s). Ils le sont au lancement du calcul, ou dès maintenant depuis la page Données.",
                ),
            )
        )
        return report
    report.editions = sorted(collected.editions)
    report.centres = [name for name, _ in collected.centres.most_common()]
    report.findings += [
        Finding("error", f"{what}: {p}") for p in collected.problems[:MAX_LISTED_PROBLEMS]
    ]
    if len(collected.problems) > MAX_LISTED_PROBLEMS:
        report.findings.append(
            Finding(
                "error",
                tr(
                    f"{what}: {len(collected.problems) - MAX_LISTED_PROBLEMS} more damaged or "
                    "incomplete messages.",
                    f"{what} : {len(collected.problems) - MAX_LISTED_PROBLEMS} autres messages abîmés ou incomplets.",
                ),
            )
        )
    every_time = sorted({t for times in collected.times.values() for t in times})
    if every_time:
        report.first, report.last, report.times = every_time[0], every_time[-1], len(every_time)
        report.step_hours = _step_hours(every_time)
    report.grids = sorted(
        {g.describe() for grids in collected.grids.values() for g in grids if g.template >= 0}
    )
    if not collected.messages:
        return report
    physics = (context.sf_surface_physics, context.smooth_cg_topo)
    table = vtables.entries(_table_text(settings))
    matched = match(collected, table) if table else Matched()
    if with_suggestions or not matched.fields:
        report.suggestions = suggest(collected, role, physics)
    if not table:
        report.findings.append(
            Finding(
                "error",
                tr(
                    f"{what}: the Vtable has no readable row.",
                    f"{what} : la Vtable n'a aucune ligne lisible.",
                ),
            )
        )
        return report
    report.unused_messages = matched.unused_messages
    report.findings += [
        Finding("error", tr(f"{what}: {stop}.", f"{what} : {stop}.")) for stop in matched.stops
    ]
    _summarise(report, matched)
    if not matched.fields:
        better = [s.vtable for s in report.suggestions[:2]]
        hint = (
            tr(
                f" The files look like {' or '.join(better)}.",
                f" Les fichiers ressemblent à {' ou '.join(better)}.",
            )
            if better
            else ""
        )
        report.findings.append(
            Finding(
                "error",
                tr(
                    f"{what}: no record of the files matches the Vtable {settings.vtable}.{hint}",
                    f"{what} : aucun enregistrement des fichiers ne correspond à la Vtable {settings.vtable}.{hint}",
                ),
            )
        )
        return report
    if role == "sst":
        report.findings += _check_sst(matched, context, report, what)
    else:
        report.findings += _check_atmosphere(matched, context, what)
    if context.domain is not None:
        report.findings += space_findings(matched.grids, context.domain, what)
    return report


def suggest(collected: Collected, role: Role, physics: tuple[int | None, bool]) -> list[Suggestion]:
    """Standard tables ranked by how well they read the files: the required fields first, then
    the share of records used and the number of fields."""
    found = []
    for name in vtables.names():
        matched = match(collected, vtables.entries(vtables.read(name)))
        if not matched.fields:
            continue
        if role == "sst":
            required_ok = "SST" in matched.names()
        else:
            required_ok = all(
                present(matched, r) for r in requirements(*physics) if r.severity == "error"
            )
        used = 1.0 - matched.unused_messages / max(collected.messages, 1)
        found.append(Suggestion(name, len(matched.fields), required_ok, round(used, 3)))
    preferred = ["Vtable.SST"] if role == "sst" else ["Vtable.ECMWF", "Vtable.GFS"]
    found.sort(
        key=lambda s: (not s.required_ok, -s.used_share, s.vtable not in preferred, -s.fields)
    )
    return found[:5]


# --------------------------------------------------------------- the case


def _first(value: object) -> str:
    """A namelist value for the outer domain, as text (per-domain lists give their first)."""
    return str(value[0] if isinstance(value, list) and value else value)


def context_of(case: Case) -> Context:
    from owstudio.core.engine.windows import forcing_case

    case = forcing_case(case)
    domains = {**case.namelist_input.get("domains", {})}
    physics = {**case.physics, **case.namelist_input.get("physics", {})}
    try:
        scheme: int | None = int(float(_first(physics.get("sf_surface_physics", 2))))
    except ValueError:
        scheme = None
    try:
        p_top = float(_first(domains.get("p_top_requested", case.grid.p_top_requested)))
    except ValueError:
        p_top = case.grid.p_top_requested
    try:
        box: Box | None = outline_box(domain_outlines(case.grid)[0])
    except NotImplementedError:
        box = None
    return Context(
        start=utc_naive(case.period.start),
        end=utc_naive(case.period.end),
        interval_s=case.period.interval_seconds,
        domain=box,
        sf_surface_physics=scheme,
        smooth_cg_topo=_first(domains.get("smooth_cg_topo", False)).lower()
        in ("true", ".true.", "t", "1"),
        p_top_pa=p_top,
    )


def own_files(case: Case, role: Role) -> GribInput | None:
    """The case's own files for this role; None when the case downloads its data (GFS, ERA5) or
    takes the SST from the atmospheric input."""
    if role == "atmosphere":
        return case.grib if case.input_source == "grib" else None
    return case.sea_surface.grib if case.sea_surface.source == "grib" else None


def examine_case(
    case: Case, role: Role, with_suggestions: bool = False, budget_bytes: int | None = None
) -> Examination | None:
    settings = own_files(case, role)
    if settings is None:
        return None
    return examine(settings, role, context_of(case), with_suggestions, budget_bytes)
