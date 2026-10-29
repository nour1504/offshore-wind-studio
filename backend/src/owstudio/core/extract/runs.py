"""Series of a run: the resolver of SeriesRef(kind="run") and the helpers to find a run's files.

A reference names the case and run ("" for the latest run with results), the stage ("main", or
"control" for the run without turbines), the location (turbine label, tslist prefix, or
latitude/longitude), the variable and the height. The reader is "tslist" (every model time
step at the tslist locations) or "wrfout" (the history files, at their output interval); by
default the tslist files are used when they hold the location and the variable.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from owstudio.core import tslist as tslist_locations
from owstudio.core.case.model import Case
from owstudio.core.extract.grid import OutsideGrid, Position, locate
from owstudio.core.extract.history import HistoryFiles, domains
from owstudio.core.extract.points import Extracted, TimeSeriesFiles, point_series
from owstudio.core.extract.quantities import Unavailable
from owstudio.core.i18n import tr
from owstudio.core.method.averaging import weighted_means
from owstudio.core.postproc.tslist_reader import Location, read_header, read_profile
from owstudio.core.postproc.windowed import history_paths, time_series_sources
from owstudio.core.series import Series, SeriesMeta, regular_frequency
from owstudio.core.series.sources import Context, SeriesNotFound, SeriesRef, register
from owstudio.core.storage import stage_folder


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
                    f"Run {run_id} has no {stage} outputs",
                    f"Le calcul {run_id} n'a pas de sorties {stage}",
                )
            )
    raise SeriesNotFound(
        tr(
            f"Case {case_id} has no run with {stage} outputs yet",
            f"Le projet {case_id} n'a pas encore de calcul avec des sorties {stage}",
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
                tr("no tslist profiles at this location", "pas de profils tslist à ce point")
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


def _power(
    files: TimeSeriesFiles, case: Case, prefix: str, domain: int, chosen: list[Member] | None = None
) -> tuple[Location, Extracted]:
    """Electrical power (MW) of the turbines a location stands for (or of ``chosen`` among them),
    at every model time step. Where the Fitch scheme ran (run with turbines, its domain), the
    scheme's own formula on the tslist profiles of the cell (energy/fitch.py: wind interpolated
    to the hub between the mass levels, induction correction for the n turbines of the cell),
    as WRF computes its POWER. Elsewhere (run without turbines), the power curve with WRF's
    conversion at the hub-height wind, as the reference without wakes."""
    # Imported here: the energy modules read run outputs through this package
    from owstudio.core.energy import fitch
    from owstudio.core.energy.curves import turbine_types, wrf_power_w
    from owstudio.core.energy.production import EnergyError, RunPower, sites

    members = tslist_locations.turbines_at(case).get(prefix) if chosen is None else chosen
    if not members:
        raise Unavailable(
            tr(
                "no turbine at this location: the power is given for turbines and their cells",
                "pas d'éolienne à ce point : la puissance est donnée pour les éoliennes et leurs mailles",
            )
        )
    types = turbine_types(case)
    farms = {farm.id: farm for farm in case.farms}
    scheme = case.farm_scheme
    # The scheme's grid: the cell of every simulated turbine, its rotation and spacing
    grid = None
    if scheme is not None and scheme.scheme == "fitch":
        try:
            source = RunPower(files.folder.parent, case)
            if source.domain == domain and source.files.has("POWER"):
                grid = source
        except EnergyError:
            grid = None
    cells: dict[tuple[int, int], int] = {}
    by_member = {}
    if grid is not None:
        enabled = {farm.id for farm in case.enabled_farms}
        numbers: dict[str, int] = {}
        for site in sites(case):
            numbers[site.farm] = numbers.get(site.farm, 0) + 1
            if site.farm in enabled:
                cell = grid.cell(site)
                cells[cell] = cells.get(cell, 0) + 1
                by_member[(site.farm, numbers[site.farm])] = cell
    total: pd.Series | None = None
    location = None
    profiles = None
    # The grid's rotation is fixed in time: read at the first output time only
    rotation: tuple[np.ndarray, np.ndarray] | None = None
    # Turbines of one model in one cell, or at one hub height, have the same power: computed once
    done: dict[tuple[object, ...], pd.Series] = {}
    for farm_id, number in members:
        model = types.get(farms[farm_id].turbines[number - 1].type)
        if model is None:
            raise Unavailable(
                tr(
                    f"turbine {farm_id}-{number} has no power curve",
                    f"l'éolienne {farm_id}-{number} n'a pas de courbe de puissance",
                )
            )
        place = by_member.get((farm_id, number))
        key = (
            (place, id(model))
            if grid is not None and place is not None
            else (model.hub_height_m, id(model))
        )
        if key in done:
            power = done[key]
        elif grid is not None and place is not None:
            if profiles is None:
                profiles = _profiles(files, prefix, domain)
                location = files.series(prefix, domain, "wind_speed", 10)[0]
            index, z, u_earth, v_earth = profiles
            if rotation is None:
                rotation = grid.files.at_time("COSALPHA", 0), grid.files.at_time("SINALPHA", 0)
            cos, sin = float(rotation[0][place]), float(rotation[1][place])
            # Back to the grid's axes, as the scheme reads U and V
            u, v = u_earth * cos + v_earth * sin, v_earth * cos - u_earth * sin
            dx = float(grid.files.attributes.get("DX", 0.0))
            watts = fitch.turbine_power(
                z, u, v, model, cells[place], dx, scheme is not None and scheme.induction
            )
            power = done[key] = pd.Series(watts / 1e6, index=index.tz_localize("UTC"))
        else:
            location, wind = files.series(prefix, domain, "wind_speed", model.hub_height_m, "agl")
            power = done[key] = pd.Series(
                wrf_power_w(wind.values.to_numpy(), model, scheme.scheme if scheme else "fitch")
                / 1e6,
                index=wind.values.index,
            )
        total = power if total is None else total + power
    assert total is not None and location is not None
    return location, Extracted(
        total,
        "MW",
        tr(
            f"power of {len(members)} turbine(s), Fitch scheme formula on the tslist profiles at every model time step"
            if grid is not None
            else f"power of {len(members)} turbine(s) from their power curve (WRF's conversion) at the hub-height wind of the tslist location, at every model time step",
            f"puissance de {len(members)} éolienne(s), formule du schéma de Fitch sur les profils tslist, à chaque pas de temps du modèle"
            if grid is not None
            else f"puissance de {len(members)} éolienne(s) par leur courbe de puissance (conversion de WRF) au vent à hauteur de moyeu du point tslist, à chaque pas de temps du modèle",
        ),
        [],
        None,
    )


def location_power(folder: Path, case: Case, prefix: str, domain: int) -> pd.Series | None:
    """Power (MW) of the turbines a tslist location stands for, at every model time step (times
    in UTC without time zone, as the tslist tables); None when the location holds no turbine."""
    if not tslist_locations.turbines_at(case).get(prefix):
        return None
    _, extracted = _power(TimeSeriesFiles(folder), case, prefix, domain)
    values = extracted.values
    index = pd.DatetimeIndex(values.index)
    return pd.Series(values.to_numpy(), index=index.tz_localize(None) if index.tz else index)


def _tslist_values(
    files: TimeSeriesFiles,
    case: Case,
    prefix: str,
    domain: int,
    ref: SeriesRef,
    seconds: int,
    chosen: list[Member] | None = None,
) -> tuple[Location, Extracted]:
    """The series of the reference at a tslist location: the values of every model time step,
    or their means over ``seconds`` (direction from the mean components; turbulence intensity
    from the spread of the speed inside each interval)."""
    if ref.variable == "power":
        location, extracted = _power(files, case, prefix, domain, chosen)
    else:
        location, extracted = files.series(
            prefix, domain, ref.variable, ref.height_m, ref.height_ref
        )
    if not seconds:
        return location, extracted
    if ref.variable == "wind_direction":
        _, u = files.series(prefix, domain, "u", ref.height_m, ref.height_ref)
        _, v = files.series(prefix, domain, "v", ref.height_m, ref.height_ref)
        frame, note = _averaged(
            {"u": u.values, "v": v.values}, seconds, vectors={"value": ("u", "v")}
        )
    else:
        frame, note = _averaged({"value": extracted.values}, seconds)
    return location, Extracted(
        frame["value"],
        extracted.unit,
        f"{extracted.method}; {note}",
        extracted.flags,
        float(seconds),
    )


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
            }
    return None


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
            f"Le point ({lat:.4f}, {lon:.4f}) est hors de tous les domaines",
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
                        f"Unknown location {ref.location!r} in case {ref.case_id} (turbine label or tslist prefix)",
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
        raise SeriesNotFound(f"{ref.variable}: {error}") from error
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
