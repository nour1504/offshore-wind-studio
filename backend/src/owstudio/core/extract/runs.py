"""Series of a run: the resolver of SeriesRef(kind="run") and helpers to find a run's files.

A reference names the case and run ("" for the latest with results), the stage ("main", or "control"
without turbines), the location (turbine, tslist prefix or latitude/longitude), the variable and the
height. Reader "tslist" (every model step at the tslist points) or "wrfout" (history files); tslist
by default when it holds the location and variable.
"""

import hashlib
import threading
from collections import OrderedDict
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import numpy as np
import pandas as pd

from owstudio.core import tslist as tslist_locations
from owstudio.core.case.model import Case
from owstudio.core.extract.grid import OutsideGrid, Position, locate
from owstudio.core.extract.history import HistoryFiles, domains
from owstudio.core.extract.points import CELL_POWER, Extracted, TimeSeriesFiles, point_series
from owstudio.core.extract.quantities import (
    NEUTRAL_INVERSE_L,
    TURBULENCE,
    Computed,
    Unavailable,
    turbulence,
)
from owstudio.core.i18n import counted, pair, tr
from owstudio.core.method.averaging import weighted_means
from owstudio.core.postproc.tslist_reader import Location, read_header, read_profile
from owstudio.core.postproc.windowed import history_paths, time_series_sources
from owstudio.core.series import Series, SeriesMeta, regular_frequency
from owstudio.core.series.sources import Context, SeriesNotFound, SeriesRef, register
from owstudio.core.storage import stage_folder
from owstudio.core.times import naive_index, utc_index


@dataclass(frozen=True)
class RunOutputs:
    case_id: str
    run_id: str
    root: Path

    def folder(self, stage: str) -> Path:
        return stage_folder(self.root, stage)

    def case(self) -> Case:
        for path in (self.folder("main") / "case.yaml", self.root / "case.yaml"):
            if path.exists():
                return Case.from_yaml(path)
        raise SeriesNotFound(
            tr(
                f"Run {self.run_id} has no case snapshot",
                f"Le calcul {self.run_id} n'a pas de copie du projet",
            )
        )


def run_outputs(
    context: Context, case_id: str, run_id: str = "", stage: str = "main"
) -> RunOutputs:
    """The run's folder; without ``run_id`` the latest run whose outputs exist for ``stage``."""
    storage = context.storage
    # Said only for the run without turbines
    without = "" if stage == "main" else tr(" without turbines", " sans éoliennes")
    try:
        ids = [run_id] if run_id else list(reversed(storage.run_ids(case_id)))
    except KeyError as error:
        raise SeriesNotFound(tr(f"Unknown case {case_id}", f"Projet inconnu {case_id}")) from error
    for candidate in ids:
        try:
            root = storage.run(case_id, candidate).root
        except KeyError as error:
            raise SeriesNotFound(
                tr(f"Unknown run {candidate}", f"Calcul inconnu {candidate}")
            ) from error
        folder = stage_folder(root, stage)
        if folder.exists() and (
            history_paths(folder)
            or any(s.folder.is_dir() for s in time_series_sources(folder / "tslist"))
        ):
            return RunOutputs(case_id, candidate, root)
        if run_id:
            raise SeriesNotFound(
                tr(
                    f"Run {run_id} has no outputs{without}",
                    f"Le calcul {run_id} n'a pas de sorties{without}",
                )
            )
    raise SeriesNotFound(
        tr(
            f"Case {case_id} has no run with outputs{without} yet",
            f"Le projet {case_id} n'a pas encore de calcul avec des sorties{without}",
        )
    )


def turbine_position(case: Case, label: str) -> tuple[float, float] | None:
    labels = tslist_locations.turbine_labels(case)
    for farm in case.farms:
        for k, turbine in enumerate(farm.turbines, 1):
            if labels[(farm.id, k)] == label:
                return turbine.lat, turbine.lon
    return None


Member = tuple[str, int]


def _tslist_prefix(case: Case, ref: SeriesRef) -> str | None:
    """The tslist prefix of the reference's location: the prefix itself, or the turbine's (its
    own location, or the cell that holds it)."""
    for point in tslist_locations.locations(case):
        if ref.location in (point.prefix, point.name, point.name.removeprefix("Turbine ")):
            return point.prefix
    turbine = _turbine_of(case, ref.location)
    if turbine is not None:
        for prefix, members in tslist_locations.turbines_at(case).items():
            if turbine in members:
                return prefix
    return None


def _turbine_of(case: Case, label: str) -> Member | None:
    labels = tslist_locations.turbine_labels(case)
    return next((key for key, value in labels.items() if value == label), None)


def _members(case: Case, ref: SeriesRef, prefix: str) -> list[Member]:
    """The turbines whose power the reference asks for at a location: the turbine named, or all
    of them."""
    there = tslist_locations.turbines_at(case).get(prefix, [])
    turbine = _turbine_of(case, ref.location)
    return [turbine] if turbine in there else there


def averaging_of(ref: SeriesRef) -> int:
    """The averaging period asked for (seconds, ``options.averaging_s``); 0 for the values of
    every model time step."""
    try:
        seconds = int(ref.options.get("averaging_s", 0) or 0)
    except (TypeError, ValueError):
        seconds = 0
    if seconds < 0 or seconds > 86_400:
        raise SeriesNotFound(
            tr(
                "The averaging period must be between 0 and 86400 s",
                "La période de moyenne doit être entre 0 et 86400 s",
            )
        )
    return seconds


def _averaged(
    columns: dict[str, pd.Series],
    seconds: int,
    vectors: dict[str, tuple[str, str]] | None = None,
) -> tuple[pd.DataFrame, str]:
    means = weighted_means(pd.DataFrame(columns), seconds, None, vectors)
    return means.frame, means.note


def _profiles(
    files: TimeSeriesFiles, prefix: str, domain: int
) -> tuple[pd.DatetimeIndex, np.ndarray, np.ndarray, np.ndarray]:
    """Times, heights above ground of the mass levels, and earth-relative u and v of a tslist
    location (time, level), every model time step; independent windows are joined, each
    spin-up left out."""
    sources = time_series_sources(files.folder)
    if len(sources) != 1 or sources[0].folder != files.folder:
        parts = [
            (index[keep], z[keep], u[keep], v[keep])
            for source in sources
            if TimeSeriesFiles(source.folder).has(prefix, domain)
            for index, z, u, v in [_profiles(TimeSeriesFiles(source.folder), prefix, domain)]
            for keep in [source.mask(index)]
        ]
        if not parts:
            raise Unavailable(
                tr("no tslist profiles at this point", "pas de profils tslist à ce point")
            )
        index = pd.DatetimeIndex(np.concatenate([part[0] for part in parts]))
        z, u, v = (np.concatenate([part[n] for part in parts]) for n in (1, 2, 3))
        order = np.argsort(index, kind="stable")
        index, z, u, v = index[order], z[order], u[order], v[order]
        unique = ~index.duplicated(keep="first")
        return index[unique], z[unique], u[unique], v[unique]
    if not files.path(prefix, domain, "PH").exists():
        raise Unavailable(
            tr(
                "no vertical profiles in the tslist output (PH file missing)",
                "pas de profils verticaux dans la sortie tslist (fichier PH manquant)",
            )
        )
    location = read_header(
        files.path(prefix, domain, "PH").open(encoding="ascii", errors="replace").readline()
    )
    heights = read_profile(files.path(prefix, domain, "PH"))
    u = read_profile(files.path(prefix, domain, "UU")).to_numpy()
    v = read_profile(files.path(prefix, domain, "VV")).to_numpy()
    rows = min(len(heights), len(u), len(v))
    index = pd.DatetimeIndex(heights.index[:rows])
    return index, heights.to_numpy()[:rows] - location.elevation, u[:rows], v[:rows]


class _FarmGrid:
    """The grid of the wind farm parameterization (run with turbines, its domain): the cell of
    every simulated turbine and the turbines of each cell; its rotation (fixed in time, read at
    the first output time) and spacing, read when first needed."""

    def __init__(
        self, files: HistoryFiles, by_member: dict[Member, tuple[int, int]], fitch: bool
    ) -> None:
        self.files = files
        self.by_member = by_member
        # The Fitch scheme (its formula is known: energy/fitch.py), or MAV
        self.fitch = fitch
        self.members: dict[tuple[int, int], list[Member]] = {}
        for member, cell in by_member.items():
            self.members.setdefault(cell, []).append(member)
        self.cells = {cell: len(members) for cell, members in self.members.items()}

    @cached_property
    def rotation(self) -> tuple[np.ndarray, np.ndarray]:
        return self.files.constant("COSALPHA"), self.files.constant("SINALPHA")

    @property
    def dx(self) -> float:
        return float(self.files.attributes.get("DX", 0.0))


def _farm_grid(folder: Path, case: Case, domain: int) -> _FarmGrid | None:
    """The grid of the wind farm parameterization where it ran on ``domain`` of the run in
    ``folder`` (its history files hold POWER), else None."""
    from owstudio.core.energy.production import EnergyError, RunPower, sites

    scheme = case.farm_scheme
    if scheme is None:
        return None
    try:
        source = RunPower(folder, case)
        if source.domain != domain or not source.files.has("POWER"):
            return None
    except EnergyError:
        return None
    enabled = {farm.id for farm in case.enabled_farms}
    numbers: dict[str, int] = {}
    by_member: dict[Member, tuple[int, int]] = {}
    for site in sites(case):
        numbers[site.farm] = numbers.get(site.farm, 0) + 1
        if site.farm in enabled:
            by_member[(site.farm, numbers[site.farm])] = source.cell(site)
    return _FarmGrid(source.files, by_member, scheme.scheme == "fitch")


_UNKNOWN = object()

# How turbine power comes out of the tslist outputs, the most exact first:
# - "power": WRF's POWER of the cell in the TS file (WRF of the engine kit) divided by the cell's
#   number of turbines (one type per cell);
# - "fitch": the Fitch formula on the cell's tslist profiles (TS files without POWER);
# - "curve": the power curve at the hub wind (run without turbines; MAV without POWER).
POWER_SOURCES = ("power", "fitch", "curve")


def power_source_text(how: str, case: Case) -> str:
    """How the tslist power of a turbine is obtained, in a few words."""
    if how == "power":
        return tr(
            "WRF's POWER of its grid cell divided by the number of turbines in the cell",
            "POWER de WRF de sa maille divisé par le nombre d'éoliennes de la maille",
        )
    if how == "fitch":
        return tr(
            "Fitch formula on the profiles of its grid cell",
            "formule de Fitch sur les profils de sa maille",
        )
    return tr(
        "power curve at the hub-height wind (WRF's conversion)",
        "courbe de puissance au vent à hauteur de moyeu (conversion de WRF)",
    )


def _member_powers(
    files: TimeSeriesFiles,
    case: Case,
    prefix: str,
    domain: int,
    chosen: list[Member] | None = None,
    grid: object = _UNKNOWN,
) -> tuple[Location, dict[Member, pd.Series], str]:
    """Electrical power (MW) of each turbine a location stands for (or of ``chosen``), at every
    model step, and how it was obtained (POWER_SOURCES).

    With a wind farm scheme (run with turbines, its domain): the cell's POWER from the TS file
    divided by its number of turbines (one type per cell: core/case/checks.py), else the Fitch
    formula as WRF computes POWER. Elsewhere (run without turbines), the power curve at the hub
    wind, as for the reference without wakes. ``grid``: the scheme's grid (_farm_grid) when the
    caller has it."""
    # Imported here: the energy modules read run outputs through this package
    from owstudio.core.case.model import TurbineType
    from owstudio.core.energy import fitch
    from owstudio.core.energy.curves import wrf_power_w
    from owstudio.core.windfarm.catalog import turbine_types

    members = tslist_locations.turbines_at(case).get(prefix) if chosen is None else chosen
    if not members:
        raise Unavailable(
            tr(
                "no turbine at this point: the power is given for turbines and their cells",
                "pas d'éolienne à ce point : la puissance est donnée pour les éoliennes et leurs mailles",
            )
        )
    types = turbine_types(case)
    farms = {farm.id: farm for farm in case.farms}
    scheme = case.farm_scheme
    if grid is _UNKNOWN:
        grid = _farm_grid(files.folder.parent, case, domain)
    assert grid is None or isinstance(grid, _FarmGrid)

    def model_of(member: Member) -> TurbineType:
        model = types.get(farms[member[0]].turbines[member[1] - 1].type)
        if model is None:
            raise Unavailable(
                tr(
                    f"turbine {member[0]}-{member[1]} has no power curve",
                    f"l'éolienne {member[0]}-{member[1]} n'a pas de courbe de puissance",
                )
            )
        return model

    location = None
    # WRF's POWER of the location's cell (W), all its turbines together, when the TS file has it
    cell_power: pd.Series | None = None
    if grid is not None:
        try:
            location, written = files.series(prefix, domain, CELL_POWER, None)
            cell_power = written.values
        except Unavailable:
            cell_power = None
    profiles: tuple[pd.DatetimeIndex, np.ndarray, np.ndarray, np.ndarray] | None = None
    formula: dict[tuple[object, ...], np.ndarray] = {}

    def fitch_watts(place: tuple[int, int], model: TurbineType) -> np.ndarray:
        """The Fitch formula for one turbine of this model in the cell, on the tslist profiles."""
        nonlocal profiles
        assert isinstance(grid, _FarmGrid)
        key = (place, id(model))
        if key not in formula:
            if profiles is None:
                profiles = _profiles(files, prefix, domain)
            _, z, u_earth, v_earth = profiles
            rotation = grid.rotation
            cos, sin = float(rotation[0][place]), float(rotation[1][place])
            # Back to the grid's axes, as the scheme reads U and V
            u, v = u_earth * cos + v_earth * sin, v_earth * cos - u_earth * sin
            formula[key] = fitch.turbine_power(
                z, u, v, model, grid.cells[place], grid.dx, scheme is not None and scheme.induction
            )
        return formula[key]

    powers: dict[Member, pd.Series] = {}
    # Turbines of one model in one cell, or at one hub height, have the same power: computed once
    done: dict[tuple[object, ...], pd.Series] = {}
    used = set()
    for member in members:
        model = model_of(member)
        place = grid.by_member.get(member) if grid is not None else None
        simulated = grid is not None and place is not None
        key = (place, id(model)) if simulated else (model.hub_height_m, id(model))
        if key in done:
            powers[member] = done[key]
            continue
        if grid is not None and place is not None and cell_power is not None:
            # One turbine type per cell (core/case/checks.py): the cell's POWER in equal shares
            power = cell_power / grid.cells[place] / 1e6
            used.add("power")
        elif grid is not None and place is not None and grid.fitch:
            watts = fitch_watts(place, model)
            assert profiles is not None
            power = pd.Series(watts / 1e6, index=profiles[0].tz_localize("UTC"))
            used.add("fitch")
        else:
            location, wind = files.series(prefix, domain, "wind_speed", model.hub_height_m, "agl")
            power = pd.Series(
                wrf_power_w(wind.values.to_numpy(), model, scheme.scheme if scheme else "fitch")
                / 1e6,
                index=wind.values.index,
            )
            used.add("curve")
        powers[member] = done[key] = power
    if location is None:
        location = files.series(prefix, domain, "wind_speed", 10)[0]
    return location, powers, next(how for how in POWER_SOURCES if how in used)


def _power(
    files: TimeSeriesFiles,
    case: Case,
    prefix: str,
    domain: int,
    chosen: list[Member] | None = None,
    grid: object = _UNKNOWN,
) -> tuple[Location, Extracted]:
    """Electrical power (MW) of the turbines a location stands for (or of ``chosen`` among them),
    at every model time step: their sum. ``grid``: as for _member_powers."""
    location, powers, how = _member_powers(files, case, prefix, domain, chosen, grid)
    members = list(powers)
    total = sum(powers.values(), start=pd.Series(0.0, index=powers[members[0]].index))
    return location, Extracted(
        total,
        "MW",
        tr(
            f"power of {len(members)} {counted(len(members), 'turbine', 'turbines')} at every model time step, from the tslist outputs: {power_source_text(how, case)}",
            f"puissance de {len(members)} {counted(len(members), 'éolienne', 'éoliennes')} à chaque pas de temps du modèle, tirée des sorties tslist : {power_source_text(how, case)}",
        ),
        [],
        None,
        how,
    )


def location_power(folder: Path, case: Case, prefix: str, domain: int) -> pd.Series | None:
    """Power (MW) of the turbines a tslist location stands for, at every model time step (times
    in UTC without time zone, as the tslist tables); None when the location holds no turbine."""
    if not tslist_locations.turbines_at(case).get(prefix):
        return None
    _, extracted = _power(TimeSeriesFiles(folder), case, prefix, domain)
    values = extracted.values
    return pd.Series(values.to_numpy(), index=naive_index(values.index))


# The 10-minute power of the turbines of the last runs read (a run and its reference), with how
# it was obtained: every energy page asks for it again. Large for long runs, so only a few are kept.
_MEANS: OrderedDict[tuple[object, ...], tuple[dict[str, pd.Series], str]] = OrderedDict()
_MEANS_SIZE = 4
_MEANS_LOCK = threading.Lock()


def _stamp(folder: Path) -> tuple[object, ...]:
    """The outputs in ``folder`` as they are now: imported again, they are another key."""
    found = []
    for path in (folder / "case.yaml", folder / "tslist", folder / "windows.json"):
        try:
            found.append(path.stat().st_mtime_ns)
        except OSError:
            found.append(0)
    return (str(folder), *found)


def tslist_turbines(folder: Path, case: Case) -> set[str]:
    """The turbines (their labels) with a tslist output in the farm domain, in the stage whose
    outputs are in ``folder``."""
    domain = tslist_locations.farm_domain(case)
    files = TimeSeriesFiles(folder / "tslist")
    labels = tslist_locations.turbine_labels(case)
    return {
        labels[member]
        for prefix, members in tslist_locations.turbines_at(case).items()
        if files.has(prefix, domain)
        for member in members
        if member in labels
    }


def turbine_means(
    folder: Path, case: Case, labels: list[str], seconds: int = 600
) -> tuple[dict[str, pd.Series], str]:
    """Mean power (W) of each named turbine over ]t - seconds, t] (UTC, stamped at t) from the farm
    domain's tslist outputs, and how it was obtained (POWER_SOURCES): the cell's POWER divided by
    its number of turbines, or the Fitch formula without POWER; the power curve at the free wind
    without turbines. Raises Unavailable for a turbine with no tslist output."""
    project = hashlib.sha1(case.model_dump_json().encode()).hexdigest()
    key = (*_stamp(folder), project, tuple(labels), seconds)
    with _MEANS_LOCK:
        if key in _MEANS:
            _MEANS.move_to_end(key)
            return dict(_MEANS[key][0]), _MEANS[key][1]
    result = _turbine_means(folder, case, labels, seconds)
    with _MEANS_LOCK:
        _MEANS[key] = result
        while len(_MEANS) > _MEANS_SIZE:
            _MEANS.popitem(last=False)
    return dict(result[0]), result[1]


def _turbine_means(
    folder: Path, case: Case, labels: list[str], seconds: int
) -> tuple[dict[str, pd.Series], str]:
    domain = tslist_locations.farm_domain(case)
    files = TimeSeriesFiles(folder / "tslist")
    wanted = {
        member: label
        for member, label in tslist_locations.turbine_labels(case).items()
        if label in labels
    }
    result: dict[str, pd.Series] = {}
    grid: object = _UNKNOWN
    used = set()
    for prefix, members in tslist_locations.turbines_at(case).items():
        here = [m for m in members if m in wanted]
        if not here or not files.has(prefix, domain):
            continue
        if grid is _UNKNOWN:
            grid = _farm_grid(folder, case, domain)
        _, powers, how = _member_powers(files, case, prefix, domain, here, grid)
        used.add(how)
        frame, _ = _averaged({str(k): series for k, series in enumerate(powers.values())}, seconds)
        for k, member in enumerate(powers):
            values = frame[str(k)].dropna() * 1e6
            values.index = utc_index(values.index)
            result[wanted[member]] = values
    missing = [label for label in labels if label not in result]
    if missing:
        who = "les éoliennes" if len(missing) > 1 else "l'éolienne"
        raise Unavailable(
            tr(
                f"no tslist output for {counted(len(missing), 'turbine', 'turbines')} {', '.join(missing[:5])} in domain {domain}: the energy is computed from the tslist outputs at the turbines (Outputs page)",
                f"pas de sortie tslist pour {who} {', '.join(missing[:5])} dans le domaine {domain} : l'énergie se calcule avec les sorties tslist aux éoliennes (page Sorties)",
            )
        )
    return result, next((how for how in POWER_SOURCES if how in used), "curve")


def _tslist_values(
    files: TimeSeriesFiles,
    case: Case,
    prefix: str,
    domain: int,
    ref: SeriesRef,
    seconds: int,
    chosen: list[Member] | None = None,
    grid: object = _UNKNOWN,
) -> tuple[Location, Extracted]:
    """The reference's series at a tslist location, every model step or means over ``seconds``.
    Derived quantities come from the means of their parts: direction from the mean components, σu
    and TI from the mean TKE and speed, L from the mean of 1/L. ``grid``: for the power, as in
    _member_powers."""
    if ref.variable == "power":
        location, extracted = _power(files, case, prefix, domain, chosen, grid)
    else:
        location, extracted = files.series(
            prefix, domain, ref.variable, ref.height_m, ref.height_ref
        )
    if not seconds:
        return location, extracted
    method, unit, flags = extracted.method, extracted.unit, extracted.flags
    if ref.variable == "wind_direction":
        _, u = files.series(prefix, domain, "u", ref.height_m, ref.height_ref)
        _, v = files.series(prefix, domain, "v", ref.height_m, ref.height_ref)
        frame, note = _averaged(
            {"u": u.values, "v": v.values}, seconds, vectors={"value": ("u", "v")}
        )
        values = frame["value"]
    elif ref.variable in TURBULENCE:
        _, tke = files.series(prefix, domain, "tke", ref.height_m, ref.height_ref)
        _, speed = files.series(prefix, domain, "wind_speed", ref.height_m, ref.height_ref)
        frame, note = _averaged({"tke": tke.values, "speed": speed.values}, seconds)
        computed = turbulence(
            ref.variable,
            Computed(frame["tke"].to_numpy(), tke.unit, tke.method, tke.flags),
            Computed(frame["speed"].to_numpy(), speed.unit, speed.method),
        )
        values = pd.Series(computed.values, index=frame.index)
        method, unit, flags = computed.method, computed.unit, computed.flags
        note = tr(
            f"from the means of the TKE and of U: {note}",
            f"à partir des moyennes de la TKE et de U : {note}",
        )
    elif ref.variable == "obukhov_length":
        _, inverse = files.series(prefix, domain, "inverse_obukhov_length", None)
        frame, note = _averaged({"value": inverse.values}, seconds)
        mean = frame["value"].to_numpy()
        with np.errstate(divide="ignore", invalid="ignore"):
            length = np.where(np.abs(mean) < NEUTRAL_INVERSE_L, np.nan, 1.0 / mean)
        values = pd.Series(length, index=frame.index)
        note = tr(f"from the mean of 1/L: {note}", f"à partir de la moyenne de 1/L : {note}")
    else:
        frame, note = _averaged({"value": extracted.values}, seconds)
        values = frame["value"]
    return location, Extracted(
        values,
        unit,
        tr(f"{method}; {note}", f"{method} ; {note}"),
        flags,
        float(seconds),
        extracted.how,
    )


def turbine_wind(
    folder: Path, case: Case, label: str, height_m: float, seconds: int = 600
) -> tuple[pd.Series, pd.Series]:
    """Wind speed (m/s) and direction (degrees) at a turbine, from the tslist outputs of the farm
    domain, as the wind analyses read them: means over ]t - seconds, t]."""
    domain = tslist_locations.farm_domain(case)
    prefix = _tslist_prefix(case, SeriesRef(kind="run", variable="wind_speed", location=label))
    files = TimeSeriesFiles(folder / "tslist")
    if prefix is None or not files.has(prefix, domain):
        raise Unavailable(
            tr(
                f"no tslist output for turbine {label}",
                f"pas de sortie tslist pour l'éolienne {label}",
            )
        )
    winds = []
    for variable in ("wind_speed", "wind_direction"):
        ref = SeriesRef(kind="run", variable=variable, location=label, height_m=height_m)
        _, extracted = _tslist_values(files, case, prefix, domain, ref, seconds)
        winds.append(extracted.values)
    return winds[0], winds[1]


def _from_tslist(
    outputs: RunOutputs, ref: SeriesRef, prefix: str
) -> tuple[Extracted, dict[str, object]] | None:
    files = TimeSeriesFiles(outputs.folder(ref.stage) / "tslist")
    candidates = (
        [ref.domain]
        if ref.domain
        else sorted({loc.domain for loc in files.locations() if loc.prefix == prefix}, reverse=True)
    )
    for domain in candidates:
        if domain is not None and files.has(prefix, domain):
            case = outputs.case()
            location, extracted = _tslist_values(
                files, case, prefix, domain, ref, averaging_of(ref), _members(case, ref, prefix)
            )
            return extracted, {
                "reader": "tslist",
                "domain": domain,
                "lat": location.lat,
                "lon": location.lon,
                "name": location.name,
                # How the power was obtained (POWER_SOURCES); nothing for the other variables
                **({"power": extracted.how} if extracted.how else {}),
            }
    return None


def tslist_point_at(context: Context, ref: SeriesRef, lat: float, lon: float) -> SeriesRef:
    """``ref`` read at the tslist point whose grid cell holds (lat, lon), on the innermost
    domain holding it (or the domain asked for): WRF writes there the column of that cell at
    every time step. ``ref`` itself when no tslist point is in that cell."""
    outputs = run_outputs(context, ref.case_id, ref.run_id, ref.stage)
    folder = outputs.folder(ref.stage)
    available = domains(folder)
    for domain in [ref.domain] if ref.domain else sorted(available, reverse=True):
        if domain not in available:
            break
        try:
            position = locate(*HistoryFiles(folder, domain).coordinates, lat, lon)
        except OutsideGrid:
            continue
        # WRF numbers the mass points from 1 in the header of each tslist file
        i, j = position.nearest
        found = sorted(
            loc.prefix
            for loc in TimeSeriesFiles(folder / "tslist").locations()
            if loc.domain == domain and (loc.i, loc.j) == (i + 1, j + 1)
        )
        if found:
            return ref.model_copy(update={"location": found[0], "domain": domain})
        break
    return ref


def _from_history(
    outputs: RunOutputs, ref: SeriesRef, lat: float, lon: float
) -> tuple[Extracted, dict[str, object]]:
    folder = outputs.folder(ref.stage)
    available = domains(folder)
    if not available:
        raise SeriesNotFound(
            tr(
                f"Run {outputs.run_id} has no history files ({ref.stage})",
                f"Le calcul {outputs.run_id} n'a pas de fichiers d'historique ({ref.stage})",
            )
        )
    # The innermost domain holding the point, unless one is asked for
    for domain in [ref.domain] if ref.domain else sorted(available, reverse=True):
        if domain not in available:
            raise SeriesNotFound(
                tr(
                    f"No history files of domain {domain}",
                    f"Aucun fichier d'historique du domaine {domain}",
                )
            )
        files = HistoryFiles(folder, domain)
        xlat, xlong = files.coordinates
        try:
            position: Position = locate(xlat, xlong, lat, lon)
        except OutsideGrid:
            if ref.domain:
                raise
            continue
        interpolation = str(ref.options.get("interpolation", "bilinear"))
        extracted = point_series(
            files,
            position,
            ref.variable,
            ref.height_m,
            ref.height_ref,
            "nearest" if interpolation == "nearest" else "bilinear",
        )
        return extracted, {"reader": "wrfout", "domain": domain, "i": position.i, "j": position.j}
    raise SeriesNotFound(
        tr(
            f"The point ({lat:.4f}, {lon:.4f}) is outside every domain",
            f"Le point ({pair(lat, lon, '.4f')}) est hors de tous les domaines",
        )
    )


def resolve_run(context: Context, ref: SeriesRef) -> Series:
    outputs = run_outputs(context, ref.case_id, ref.run_id, ref.stage)
    case = outputs.case()
    lat, lon = ref.lat, ref.lon
    name = ref.location
    if lat is None or lon is None:
        position = turbine_position(case, ref.location)
        if position is None:
            point = next(
                (p for p in tslist_locations.locations(case) if ref.location in (p.prefix, p.name)),
                None,
            )
            if point is None:
                raise SeriesNotFound(
                    tr(
                        f"Unknown point {ref.location!r} in project {ref.case_id} (turbine label or tslist prefix)",
                        f"Point inconnu {ref.location!r} dans le projet {ref.case_id} (nom d'éolienne ou préfixe tslist)",
                    )
                )
            position = (point.lat, point.lon)
        lat, lon = position
    else:
        name = name or f"{lat:.4f},{lon:.4f}"
    try:
        found = None
        prefix = _tslist_prefix(case, ref) if ref.reader in ("", "tslist") else None
        if prefix is not None:
            try:
                found = _from_tslist(outputs, ref, prefix)
            except Unavailable:
                if ref.reader == "tslist":
                    raise
        if found is None:
            if ref.reader == "tslist":
                raise SeriesNotFound(
                    tr(
                        f"No tslist output for {ref.location!r}",
                        f"Aucune sortie tslist pour {ref.location!r}",
                    )
                )
            found = _from_history(outputs, ref, lat, lon)
    except Unavailable as error:
        raise SeriesNotFound(tr(f"{ref.variable}: {error}", f"{ref.variable} : {error}")) from error
    except OutsideGrid as error:
        raise SeriesNotFound(str(error)) from error
    return _series(outputs, ref, found, lat, lon, name)


def _series(
    outputs: RunOutputs,
    ref: SeriesRef,
    found: tuple[Extracted, dict[str, object]],
    lat: float | None,
    lon: float | None,
    name: str,
) -> Series:
    extracted, details = found
    reader = str(details["reader"])
    averaged = reader == "tslist" and averaging_of(ref) > 0
    meta = SeriesMeta(
        variable=ref.variable,
        unit=extracted.unit,
        source="tslist" if reader == "tslist" else "wrfout",
        dataset=f"{outputs.case_id}/{outputs.run_id}/{ref.stage}",
        location=ref.location or name,
        location_name=str(details.get("name", name)),
        lat=lat,
        lon=lon,
        height_m=ref.height_m,
        height_ref=ref.height_ref if ref.height_m is not None else "surface",
        method=extracted.method,
        frequency_s=extracted.frequency_s
        or regular_frequency(pd.DatetimeIndex(extracted.values.index)),
        averaging_s=float(averaging_of(ref)) if averaged else 0.0,
        time_label="end" if averaged else "instant",
        description=tr(
            f"WRF run {outputs.run_id} ({ref.stage}), domain {details.get('domain')}",
            f"Calcul WRF {outputs.run_id} ({ref.stage}), domaine {details.get('domain')}",
        ),
        flags=extracted.flags,
        extra={k: v for k, v in details.items() if k not in ("name", "reader")},
    )
    return Series(meta, extracted.values)


register("run", resolve_run)
