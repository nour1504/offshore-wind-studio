"""Export of a run's tslist outputs (Exporter tab), read as the Explorer and the analyses read them
(extract/runs.py).

The points of one grid cell share its series, so a cell is read once. Long layout: one row per time
and cell, with its points and turbines; wide: one row per time, each cell's quantities once (column
names give its turbines) and one power column per turbine. The run without turbines comes beside,
its columns suffixed.
"""

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from owstudio.core import tslist as tslist_locations
from owstudio.core.analysis.profile import MIN_SPEED_FOR_SHEAR
from owstudio.core.case.model import Case
from owstudio.core.extract.points import CELL_POWER, TimeSeriesFiles
from owstudio.core.extract.quantities import Unavailable
from owstudio.core.extract.runs import (
    _UNKNOWN,
    POWER_SOURCES,
    Member,
    _farm_grid,
    _tslist_values,
)
from owstudio.core.i18n import tr
from owstudio.core.method.averaging import coverage
from owstudio.core.postproc.tslist_reader import Location
from owstudio.core.postproc.windowed import time_series_sources
from owstudio.core.series import circular
from owstudio.core.series.sources import SeriesRef
from owstudio.core.storage import stage_folder


@dataclass(frozen=True)
class Quantity:
    key: str
    # Column names, in English and in French
    en: str
    fr: str
    # What extract/points.py reads ("power": one turbine, CELL_POWER: the whole cell)
    variable: str
    unit: str
    # At each height asked for; otherwise at ``height`` (10 m wind, 2 m temperature) or at the
    # surface
    profile: bool = False
    height: float | None = None
    scale: float = 1.0
    offset: float = 0.0
    # Accumulated since the start of the run: the value at the end of each interval
    accumulated: bool = False
    # Between the lowest and the highest heights asked for (shear exponent, veer)
    between: bool = False


# In the order of the file and of the Exporter tab
QUANTITIES: tuple[Quantity, ...] = (
    Quantity("wind_speed", "wind_speed", "vitesse_vent", "wind_speed", "m/s", profile=True),
    Quantity("wind_direction", "wind_direction", "direction_vent", "wind_direction", "deg", profile=True),
    Quantity("turbulence_intensity", "turbulence_intensity", "intensite_turbulence", "turbulence_intensity", "%", profile=True, scale=100.0),
    Quantity("tke", "tke", "tke", "tke", "m2/s2", profile=True),
    Quantity("temperature", "temperature", "temperature", "temperature", "degC", profile=True, offset=-273.15),
    Quantity("potential_temperature", "potential_temperature", "temperature_potentielle", "potential_temperature", "K", profile=True),
    Quantity("mixing_ratio", "mixing_ratio", "rapport_melange", "mixing_ratio", "g/kg", profile=True, scale=1000.0),
    Quantity("pressure", "pressure", "pression", "pressure", "hPa", profile=True, scale=0.01),
    Quantity("vertical_wind", "vertical_wind", "vent_vertical", "vertical_wind", "m/s", profile=True),
    Quantity("shear_exponent", "shear_exponent", "exposant_cisaillement", "wind_speed", "-", between=True),
    Quantity("wind_veer", "wind_veer", "rotation_vent", "wind_direction", "deg", between=True),
    Quantity("power_turbine", "turbine_power", "puissance_eolienne", "power", "MW"),
    Quantity("power_cell", "cell_power", "puissance_maille", CELL_POWER, "MW", scale=1e-6),
    Quantity("wind_speed_10m", "wind_speed_10m", "vitesse_vent_10m", "wind_speed", "m/s", height=10.0),
    Quantity("wind_direction_10m", "wind_direction_10m", "direction_vent_10m", "wind_direction", "deg", height=10.0),
    Quantity("temperature_2m", "temperature_2m", "temperature_2m", "temperature", "degC", height=2.0, offset=-273.15),
    Quantity("mixing_ratio_2m", "mixing_ratio_2m", "rapport_melange_2m", "mixing_ratio", "g/kg", height=2.0, scale=1000.0),
    Quantity("surface_pressure", "surface_pressure", "pression_surface", "surface_pressure", "hPa", scale=0.01),
    Quantity("skin_temperature", "skin_temperature", "temperature_surface", "skin_temperature", "degC", offset=-273.15),
    Quantity("soil_temperature", "soil_temperature", "temperature_sol", "soil_temperature", "degC", offset=-273.15),
    Quantity("sensible_heat_flux", "sensible_heat_flux", "flux_chaleur_sensible", "sensible_heat_flux", "W/m2"),
    Quantity("latent_heat_flux", "latent_heat_flux", "flux_chaleur_latente", "latent_heat_flux", "W/m2"),
    Quantity("longwave_down", "longwave_down", "rayonnement_ir_descendant", "longwave_down", "W/m2"),
    Quantity("shortwave_down", "shortwave_down", "rayonnement_solaire_descendant", "shortwave_down", "W/m2"),
    Quantity("rain_convective", "convective_rain_total", "pluie_convective_cumulee", "rain_convective", "mm", accumulated=True),
    Quantity("rain_grid", "grid_rain_total", "pluie_resolue_cumulee", "rain_grid", "mm", accumulated=True),
    Quantity("cloud_water", "cloud_water_column", "eau_nuageuse_colonne", "cloud_water", "kg/m2"),
    Quantity("inverse_obukhov_length", "inverse_obukhov_length", "inverse_longueur_obukhov", "inverse_obukhov_length", "1/m"),
    Quantity("obukhov_length", "obukhov_length", "longueur_obukhov", "obukhov_length", "m"),
    Quantity("bulk_richardson", "bulk_richardson", "richardson_global", "bulk_richardson", "-"),
    Quantity("friction_velocity", "friction_velocity", "vitesse_frottement", "friction_velocity", "m/s"),
    Quantity("boundary_layer_height", "boundary_layer_height", "hauteur_couche_limite", "boundary_layer_height", "m"),
)  # fmt: skip
BY_KEY = {q.key: q for q in QUANTITIES}


def no_farm() -> str:
    """The suffix of the columns of the run without turbines, in the language of the request."""
    return tr("_no_farm", "_sans_parc")


class ExportError(ValueError):
    """A request the export cannot answer (unknown quantity or point)."""


@dataclass(frozen=True)
class Place:
    """A grid cell of a domain holding tslist points: they all have the same series."""

    domain: int
    i: int
    j: int
    # The file read, and every point of the cell (their tslist names)
    prefix: str
    points: tuple[str, ...]
    prefixes: tuple[str, ...]
    # The turbines of the project whose series is this cell's, and their labels
    turbines: tuple[Member, ...]
    labels: tuple[str, ...]

    @property
    def key(self) -> str:
        return f"{self.domain}:{self.prefix}"

    def title(self) -> str:
        """How the cell is named in the columns of the wide layout."""
        who = " ".join(self.labels) if self.labels else " ".join(self.points)
        return tr(
            f"d{self.domain:02d} cell {self.i},{self.j}: {who}",
            f"d{self.domain:02d} maille {self.i},{self.j} : {who}",
        )


def places(folder: Path, case: Case) -> list[Place]:
    """The cells holding the tslist points of the stage whose outputs are in ``folder``, each
    point in the finest domain that holds it (WRF writes it in every one)."""
    files = TimeSeriesFiles(folder / "tslist")
    members = tslist_locations.turbines_at(case)
    labels = tslist_locations.turbine_labels(case)
    finest: dict[str, int] = {}
    found = files.locations()
    for loc in found:
        finest[loc.prefix] = max(finest.get(loc.prefix, 0), loc.domain)
    cells: dict[tuple[int, int, int], list[Location]] = {}
    for loc in sorted(found, key=lambda loc: loc.prefix):
        if loc.domain != finest[loc.prefix]:
            continue
        cells.setdefault((loc.domain, loc.i, loc.j), []).append(loc)
    result = []
    for (domain, i, j), locs in cells.items():
        turbines = tuple(m for loc in locs for m in members.get(loc.prefix, []))
        result.append(
            Place(
                domain,
                i,
                j,
                locs[0].prefix,
                tuple(loc.name for loc in locs),
                tuple(loc.prefix for loc in locs),
                turbines,
                tuple(labels[m] for m in turbines if m in labels),
            )
        )
    return sorted(result, key=lambda p: (p.domain, p.labels[:1] or p.points[:1], p.prefix))


def column_name(
    quantity: Quantity, height: float | None, suffix: bool = False, top: float | None = None
) -> str:
    stem = tr(quantity.en, quantity.fr)
    if quantity.between and height is not None and top is not None:
        stem = f"{stem}_{height:g}-{top:g}m"
    elif quantity.profile and height is not None:
        stem = f"{stem}_{height:g}m"
    if suffix:
        stem += no_farm()
    return f"{stem} [{quantity.unit}]"


def _on_intervals(values: pd.Series, seconds: int) -> pd.Series:
    """An accumulated quantity at the ends t of ]t - seconds, t] (UTC): the value of a step ending
    at t, else linear between the two steps around t (each value stands for the step ending at
    it, as in method/averaging.py). None across a gap."""
    if not seconds:
        return values
    index = pd.DatetimeIndex(values.index)
    if index.tz is not None:
        index = index.tz_convert(None)
    known = values.to_numpy(dtype=float)
    finite = np.isfinite(known)
    known = known[finite]
    times = index.to_numpy(dtype="datetime64[ns]").astype(np.int64)[finite] / 1e9
    if not len(times):
        return pd.Series([], index=pd.DatetimeIndex([]), dtype=float)
    ends = np.arange(np.ceil(times[0] / seconds), np.floor(times[-1] / seconds) + 1) * seconds
    after = np.searchsorted(times, ends)
    exact = times[after] == ends
    before = np.maximum(after - 1, 0)
    # A value covers the step since the previous one, unless a gap cuts it short
    joined = coverage(times)[after] == times[before]
    with np.errstate(divide="ignore", invalid="ignore"):
        share = (ends - times[before]) / (times[after] - times[before])
    total = np.where(exact, known[after], known[before] + share * (known[after] - known[before]))
    kept = exact | ((after > 0) & joined)
    return pd.Series(total[kept], index=pd.to_datetime(ends[kept], unit="s"))


def _read(
    files: TimeSeriesFiles,
    case: Case,
    place: Place,
    quantity: Quantity,
    height: float | None,
    seconds: int,
    member: Member | None = None,
    how: set[str] | None = None,
    grid: object = _UNKNOWN,
) -> pd.Series:
    """One column: the series of one cell (or, for the power of a turbine, of one turbine), in
    the unit of the column, indexed by UTC times without time zone. ``how`` collects how the
    power of a turbine was obtained (extract/runs.py, POWER_SOURCES); ``grid`` is the grid of
    the wind farm parameterization when the caller has it (extract/runs.py, _farm_grid)."""
    ref = SeriesRef(
        kind="run",
        variable=quantity.variable,
        height_m=height if quantity.profile else quantity.height,
    )
    chosen = [member] if member is not None else None
    if quantity.accumulated:
        _, extracted = _tslist_values(files, case, place.prefix, place.domain, ref, 0, chosen, grid)
        values = _on_intervals(extracted.values, seconds)
    else:
        _, extracted = _tslist_values(
            files, case, place.prefix, place.domain, ref, seconds, chosen, grid
        )
        values = extracted.values
    if how is not None and extracted.how:
        how.add(extracted.how)
    index = pd.DatetimeIndex(values.index)
    if index.tz is not None:
        index = index.tz_convert("UTC").tz_localize(None)
    return pd.Series(values.to_numpy(dtype=float) * quantity.scale + quantity.offset, index=index)


def _between(
    files: TimeSeriesFiles,
    case: Case,
    place: Place,
    quantity: Quantity,
    low: float,
    high: float,
    seconds: int,
) -> pd.Series:
    """Shear exponent or veer from the means at two heights, as the analyses compute them
    (analysis/profile.py): α = ln(U2/U1) / ln(z2/z1), left out under 1 m/s at either height;
    veer = upper minus lower direction, in (-180, 180]."""
    base = BY_KEY["wind_speed" if quantity.key == "shear_exponent" else "wind_direction"]
    lower, upper = _read(files, case, place, base, low, seconds).align(
        _read(files, case, place, base, high, seconds)
    )
    if quantity.key == "shear_exponent":
        below, above = lower.to_numpy(), upper.to_numpy()
        usable = (below >= MIN_SPEED_FOR_SHEAR) & (above >= MIN_SPEED_FOR_SHEAR)
        with np.errstate(divide="ignore", invalid="ignore"):
            alpha = np.log(above / below) / np.log(high / low)
        return pd.Series(np.where(usable, alpha, np.nan), index=lower.index)
    turn = circular.difference(upper.to_numpy(), lower.to_numpy())
    return pd.Series(turn, index=lower.index)


def has_reference(root: Path) -> bool:
    """Whether the run without turbines beside the run in ``root`` has tslist outputs (in one
    folder, or in the folders of its windows)."""
    folder = stage_folder(root, "control") / "tslist"
    return any(source.folder.is_dir() for source in time_series_sources(folder))


@dataclass
class Table:
    frame: pd.DataFrame
    # Quantities asked for that this run's files cannot give, with the reason
    missing: dict[str, str]
    # How the power of the turbines of each power column was obtained (POWER_SOURCES order)
    power: dict[str, list[str]] = field(default_factory=dict)


def table(
    root: Path,
    case: Case,
    keys: list[str],
    quantities: list[str],
    heights: list[float],
    seconds: int,
    layout: str,
    reference: bool,
) -> Table:
    """The export of the run in ``root``: the cells ``keys`` (Place.key), the ``quantities``
    (Quantity.key) at the ``heights`` of the profiles, means over ``seconds`` (0: every model
    time step), in the ``layout`` "long" or "wide", with the run without turbines beside when
    ``reference`` and it exists."""
    unknown = [q for q in quantities if q not in BY_KEY]
    if unknown:
        raise ExportError(
            tr(
                f"Unknown quantities: {', '.join(unknown)}",
                f"Grandeurs inconnues : {', '.join(unknown)}",
            )
        )
    if layout not in ("long", "wide"):
        raise ExportError(tr(f"Unknown layout {layout}", f"Disposition inconnue : {layout}"))
    chosen_quantities = [BY_KEY[q] for q in quantities]
    stages = [("main", False)]
    if reference and has_reference(root):
        stages.append(("control", True))
    main_places = {p.key: p for p in places(stage_folder(root, "main"), case)}
    missing_keys = [k for k in keys if k not in main_places]
    if missing_keys:
        raise ExportError(
            tr(
                f"Unknown points: {', '.join(missing_keys)}",
                f"Points inconnus : {', '.join(missing_keys)}",
            )
        )
    chosen_places = [main_places[k] for k in keys]
    missing: dict[str, str] = {}
    blocks: list[pd.DataFrame] = []
    columns: dict[str, pd.Series] = {}
    levels = sorted(set(heights))
    power: dict[str, set[str]] = {}
    # Where the wind farm parameterization ran: elsewhere the POWER column of the TS file is 0
    scheme = case.farm_scheme
    farm_domains = set(scheme.domains) if scheme is not None and case.active_turbines() else set()
    # The grid of the parameterization, found once per stage and domain: the power of every
    # turbine of every cell reads it
    grids: dict[tuple[str, int], object] = {}

    def put(here: dict[str, pd.Series], place: Place, name: str, series: pd.Series) -> None:
        if layout == "wide":
            columns[f"{name} {place.title()}"] = series
        else:
            here[name] = series

    for place in chosen_places:
        here: dict[str, pd.Series] = {}
        for stage, suffix in stages:
            files = TimeSeriesFiles(stage_folder(root, stage) / "tslist")
            if not files.has(place.prefix, place.domain):
                continue
            for quantity in chosen_quantities:
                if quantity.key == "power_cell" and (suffix or place.domain not in farm_domains):
                    if not suffix:
                        missing.setdefault(
                            column_name(quantity, None),
                            tr(
                                f"no wind farm parameterization in this run on domain {place.domain}: WRF's POWER is 0 there",
                                f"pas de paramétrisation des parcs dans ce calcul sur le domaine {place.domain} : le POWER de WRF y vaut 0",
                            ),
                        )
                    continue
                if quantity.between:
                    if len(levels) < 2:
                        missing.setdefault(
                            column_name(quantity, None, suffix),
                            tr("needs two heights", "demande deux hauteurs"),
                        )
                        continue
                    name = column_name(quantity, levels[0], suffix, levels[-1])
                    try:
                        put(here, place, name, _between(files, case, place, quantity, levels[0], levels[-1], seconds))  # fmt: skip
                    except Unavailable as error:
                        missing.setdefault(name, str(error))
                    continue
                for height in heights if quantity.profile else [None]:
                    name = column_name(quantity, height, suffix)
                    if quantity.key == "power_turbine":
                        how = power.setdefault(name, set())
                        if (stage, place.domain) not in grids:
                            grids[(stage, place.domain)] = _farm_grid(
                                files.folder.parent, case, place.domain
                            )
                        grid = grids[(stage, place.domain)]
                        for member, label in zip(place.turbines, place.labels, strict=True):
                            try:
                                series = _read(
                                    files, case, place, quantity, height, seconds, member, how, grid
                                )
                            except Unavailable as error:
                                missing.setdefault(name, str(error))
                                continue
                            if layout == "wide":
                                columns[f"{name} {label}"] = series
                            else:
                                # One turbine of the cell stands for all: they share POWER equally
                                here.setdefault(name, series)
                        continue
                    try:
                        put(here, place, name, _read(files, case, place, quantity, height, seconds))
                    except Unavailable as error:
                        missing.setdefault(name, str(error))
        if layout == "long" and here:
            block = pd.DataFrame(here)
            block.insert(0, "point", " ".join(place.points))
            block.insert(1, tr("turbines_in_cell", "eoliennes_dans_maille"), len(place.turbines))
            block.insert(2, tr("turbines", "eoliennes"), " ".join(place.labels))
            blocks.append(block)
    if layout == "wide":
        frame = pd.DataFrame(columns)
    else:
        frame = pd.concat(blocks) if blocks else pd.DataFrame()
        if not frame.empty:
            frame = frame.sort_index(kind="stable")
    frame.index.name = (
        tr("time_utc_end", "temps_utc_fin") if seconds else tr("time_utc", "temps_utc")
    )
    # A column is reported missing only if no cell could give it
    written = {str(c).rsplit(" [", 1)[0] for c in frame.columns}
    missing = {name: why for name, why in missing.items() if name.rsplit(" [", 1)[0] not in written}
    sources = {
        name: [how for how in POWER_SOURCES if how in used] for name, used in power.items() if used
    }
    return Table(frame, missing, sources)


def keep_period(
    frame: pd.DataFrame, start: pd.Timestamp | None, end: pd.Timestamp | None
) -> pd.DataFrame:
    """The rows of ]start, end] (UTC)."""
    times = pd.DatetimeIndex(frame.index)
    keep = np.ones(len(times), dtype=bool)
    if start is not None:
        keep &= times > start
    if end is not None:
        keep &= times <= end
    return frame[keep]
