"""Results of a run: summary, power, maps, point series and WRF time series.

Every route takes an optional ``run``; without it the latest run with results is used.
"""

from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response

from owstudio.api.routes_cases import state
from owstudio.api.runs import RunStatus
from owstudio.core import tslist as tslist_locations
from owstudio.core.case.model import Case
from owstudio.core.extract.quantities import Unavailable
from owstudio.core.extract.runs import location_power
from owstudio.core.i18n import tr
from owstudio.core.postproc.results import (
    VARIABLES,
    Results,
    Variable,
    field_png,
    legend_colors,
    warm_in_background,
)
from owstudio.core.postproc.tslist_reader import TimeSeriesSet, average
from owstudio.core.postproc.windowed import time_series_sources
from owstudio.core.storage import outputs_stamp, stage_folder
from owstudio.core.windfarm.catalog import turbine_types

router = APIRouter()


def has_outputs(root: Path, need: str) -> bool:
    if need == "tslist":
        return (
            any(
                s.folder.is_dir() for s in time_series_sources(root / "outputs" / "main" / "tslist")
            )
            and (root / "outputs" / "main" / "case.yaml").exists()
        )
    return Results.exist(root)


def run_root(request: Request, case_id: str, run: str | None, need: str = "wrfout") -> Path:
    """The run folder to read: the one asked for, or the latest with the needed outputs."""
    app = state(request)
    app.workspace.load(case_id)
    if run:
        try:
            root = app.storage.run(case_id, run).root
        except KeyError as error:
            raise HTTPException(404, tr("Unknown run", "Calcul inconnu")) from error
        if not has_outputs(root, need):
            raise HTTPException(
                404, tr("This run has no results", "Ce calcul n'a pas de résultats")
            )
        return root
    # The latest with turbines: a run without turbines imported after it is only its reference
    from owstudio.api.routes_reference import without_turbines

    latest = None
    for run_id in reversed(app.storage.run_ids(case_id)):
        root = app.storage.run(case_id, run_id).root
        if not has_outputs(root, need):
            continue
        if need != "wrfout" or not without_turbines(root / "outputs" / "main"):
            return root
        latest = latest or root
    if latest is not None:
        return latest
    raise HTTPException(
        404,
        tr(
            "No results yet: import outputs first",
            "Pas encore de résultats : importer d'abord des sorties",
        ),
    )


def results_for(request: Request, case_id: str, run: str | None) -> Results:
    return Results(run_root(request, case_id, run))


def check_domain(results: Results, domain: int) -> None:
    if domain not in results.files("main"):
        raise HTTPException(
            404, tr(f"No output for domain {domain}", f"Aucune sortie pour le domaine {domain}")
        )


def records(frame: pd.DataFrame, digits: int = 3) -> list[dict[str, Any]]:
    """JSON rows with the time index first and missing values as null."""
    rows = frame.round(digits).astype(object).where(frame.notna(), None).to_dict("records")
    return [
        {"time": pd.Timestamp(t).isoformat(), **{str(k): v for k, v in row.items()}}
        for t, row in zip(frame.index, rows, strict=True)
    ]


@router.get("/api/cases/{case_id}/runs")
def runs(request: Request, case_id: str) -> list[RunStatus]:
    """The runs of the project (imported outputs), the latest first."""
    app = state(request)
    app.workspace.load(case_id)
    return app.runs.runs(case_id)


@router.get("/api/cases/{case_id}/results")
def results_summary(request: Request, case_id: str, run: str | None = None) -> dict[str, Any]:
    results = results_for(request, case_id, run)
    files = [*results.files("main").values(), *results.files("control").values()]
    stamp = outputs_stamp(results.root)
    # The key figures first (they hold the energy of the page); then the map is computed ahead
    summary = results.summary()
    warm_in_background(("map", *stamp), results.warm)
    error, source = energy_state(results)
    return {
        **summary,
        "run_id": results.root.name,
        "windowed": results.windowed,
        # Changes with every new run, so that the interface does not reuse cached images
        "version": int(max(stamp[1:] + tuple(path.stat().st_mtime for path in files))),
        "times": {str(d): [t.isoformat() for t in results.times(d)] for d in results.files("main")},
        "variables": {k: asdict(v) for k, v in VARIABLES.items()},
        "fields": results.available_fields(),
        # What the page may ask for: the series of the tslist points, and the energy tables (or
        # why they cannot be computed), so that it asks for nothing in vain
        "tslist": has_outputs(results.root, "tslist"),
        "energy_error": error,
        # Where the power and the energy come from: the tslist outputs at the turbines, the
        # history files without them (the key figures alone when the tables cannot be computed)
        "energy_source": source or ("wrfout" if summary["mean_power_mw"] is not None else None),
    }


def energy_state(results: Results) -> tuple[str | None, str | None]:
    """Why the energy tables of the run cannot be computed (None when they can: then computed
    and kept for the energy routes, as the key figures of a run in windows already do), and
    where their power comes from: "tslist" or "wrfout"."""
    # Imported here: the energy routes read this module
    from owstudio.api.routes_energy import energy_of
    from owstudio.core.energy.production import EnergyError

    try:
        energy = energy_of(results.root, results.case, "auto")
    except EnergyError as error:
        return str(error), None
    return None, "tslist" if energy["method"] == "tslist" else "wrfout"


def field_args(results: Results, variable: str, domain: int) -> Variable:
    check_domain(results, domain)
    if variable not in VARIABLES:
        raise HTTPException(
            422, tr(f"Unknown variable {variable}", f"Variable inconnue : {variable}")
        )
    return variable  # type: ignore[return-value]


@router.get("/api/cases/{case_id}/results/field")
def results_field(
    request: Request, case_id: str, variable: str, domain: int, run: str | None = None
) -> dict[str, Any]:
    results = results_for(request, case_id, run)
    name = field_args(results, variable, domain)
    try:
        vmin, vmax = results.color_range(name, domain)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    info = VARIABLES[name]
    return {
        **asdict(info),
        "vmin": vmin,
        "vmax": vmax,
        "colors": legend_colors(info.colormap),
        "coordinates": results.map_corners(domain),
    }


@router.get("/api/cases/{case_id}/results/field.png")
def results_field_png(
    request: Request,
    case_id: str,
    variable: str,
    domain: int,
    time: int | None = None,
    run: str | None = None,
) -> Response:
    results = results_for(request, case_id, run)
    name = field_args(results, variable, domain)
    try:
        vmin, vmax = results.color_range(name, domain)
        image = results.map_image(name, domain, time)
    except LookupError as error:
        raise HTTPException(404, str(error)) from error
    except IndexError as error:
        raise HTTPException(
            404, tr("No output at this time", "Aucune sortie à cet instant")
        ) from error
    png = field_png(image, vmin, vmax, VARIABLES[name].colormap, north_up=True)
    return Response(png, media_type="image/png", headers={"Cache-Control": "max-age=3600"})


@router.get("/api/cases/{case_id}/results/point")
def results_point(
    request: Request, case_id: str, domain: int, lat: float, lon: float, run: str | None = None
) -> list[dict[str, Any]]:
    results = results_for(request, case_id, run)
    check_domain(results, domain)
    frame = results.point(domain, lat, lon)
    if frame is None:
        raise HTTPException(
            404, tr("The point is outside the domain", "Le point est hors du domaine")
        )
    return records(frame)


def tslist_sets(root: Path) -> tuple[TimeSeriesSet, TimeSeriesSet]:
    return TimeSeriesSet(root / "outputs" / "main" / "tslist"), TimeSeriesSet(
        stage_folder(root, "control") / "tslist"
    )


@router.get("/api/cases/{case_id}/results/tslist")
def tslist_index(request: Request, case_id: str, run: str | None = None) -> dict[str, Any]:
    root = run_root(request, case_id, run, "tslist")
    main, control = tslist_sets(root)
    results = Results(root)
    turbines = tslist_locations.turbines_at(results.case)
    # The turbines of one grid cell have the same series (WRF uses the cell's grid point):
    # one series per cell, with the names of every location it stands for and the number of
    # turbines each one holds (its power can then be computed)
    types = turbine_types(results.case)
    farms = {farm.id: farm for farm in results.case.farms}

    def hub(prefix: str) -> float:
        """Hub height of the turbines a location stands for (their mean when models differ)."""
        heights = [
            types[farms[farm].turbines[number - 1].type].hub_height_m
            for farm, number in turbines.get(prefix, [])
            if farm in farms and farms[farm].turbines[number - 1].type in types
        ]
        return float(np.mean(heights)) if heights else results.hub_height_m

    cells: dict[tuple[int, int, int], dict[str, Any]] = {}
    for loc in main.locations():
        key = (loc.domain, loc.i, loc.j)
        member = {
            "prefix": loc.prefix,
            "name": loc.name,
            "turbines": len(turbines.get(loc.prefix, [])),
        }
        if key in cells:
            cells[key]["members"].append(member)
            continue
        cells[key] = {
            **asdict(loc),
            "hub_height_m": hub(loc.prefix),
            "has_control": control.has(loc.prefix, loc.domain),
            "members": [member],
        }
    return {"hub_height_m": results.hub_height_m, "locations": list(cells.values())}


def tslist_frame(
    request: Request,
    case_id: str,
    prefix: str,
    domain: int,
    height: float,
    seconds: int,
    run: str | None,
) -> pd.DataFrame:
    if not prefix.replace("_", "").isalnum() or len(prefix) > 5:
        raise HTTPException(422, tr("Invalid prefix", "Préfixe invalide"))
    root = run_root(request, case_id, run, "tslist")
    return point_frame(root, Results(root).case, prefix, domain, height, seconds)


def _with_power(
    frame: pd.DataFrame, folder: Path, case: Case, prefix: str, domain: int
) -> pd.DataFrame:
    """The table of a location with the power of its turbines (MW), when it holds some."""
    try:
        power = location_power(folder, case, prefix, domain)
    except Unavailable:
        power = None
    if power is not None and not frame.empty:
        frame = frame.copy()
        frame["power_mw"] = power.reindex(pd.DatetimeIndex(frame.index)).to_numpy()
    return frame


def point_frame(
    root: Path, case: Case, prefix: str, domain: int, height: float, seconds: int
) -> pd.DataFrame:
    """The tslist table of one location: surface variables, wind at ``height``, power of its
    turbines, averaged over ``seconds``, with the run without farms beside it."""
    main, control = tslist_sets(root)
    if not main.has(prefix, domain):
        raise HTTPException(
            404,
            tr(
                f"No time series {prefix} on domain {domain}",
                f"Aucune série temporelle {prefix} sur le domaine {domain}",
            ),
        )
    frame = average(
        _with_power(main.series(prefix, domain, height), main.directory, case, prefix, domain),
        seconds,
    )
    if control.has(prefix, domain):
        other = average(
            _with_power(
                control.series(prefix, domain, height), control.directory, case, prefix, domain
            ),
            seconds,
        )
        columns = [
            c
            for c in ("wind_speed_hub", "wind_direction_hub", "wind_speed_10m", "power_mw")
            if c in other
        ]
        frame = frame.join(other[columns].add_suffix("_no_farm"), how="left")
    attrs = dict(frame.attrs)
    frame = frame.drop(columns=[c for c in ("u_hub", "v_hub", "u_10m", "v_10m") if c in frame])
    frame.attrs = attrs
    return frame


@router.get("/api/cases/{case_id}/results/tslist/{prefix}")
def tslist_series(
    request: Request,
    case_id: str,
    prefix: str,
    domain: int,
    height: float = 100.0,
    average_s: int = 600,
    run: str | None = None,
) -> list[dict[str, Any]]:
    return records(tslist_frame(request, case_id, prefix, domain, height, average_s, run), 4)
