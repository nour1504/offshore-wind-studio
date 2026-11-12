"""The Exporter tab: the tslist outputs of a run in one CSV (core/extract/tslist_export.py), and
one variable of the history files (wrfout) at one point. Each file starts with lines saying its
source, its time step and its averaging; the units are in the column names.
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse, Response

from owstudio.api.routes_cases import state
from owstudio.api.routes_results import records, run_root
from owstudio.core import extract  # noqa: F401  (registers the "run" series resolver)
from owstudio.core.case.model import Case
from owstudio.core.extract import tslist_export
from owstudio.core.extract.runs import power_source_text
from owstudio.core.i18n import tr
from owstudio.core.series import units
from owstudio.core.series.sources import SeriesNotFound, SeriesRef, resolve
from owstudio.core.storage import stage_folder
from owstudio.core.times import naive_stamp

router = APIRouter()


def _attachment(text: str, name: str) -> Response:
    return Response(
        text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


def _period_line(start: datetime | None, end: datetime | None) -> list[str]:
    if start is None and end is None:
        return []
    first = naive_stamp(start).isoformat(sep=" ") if start else "…"
    last = naive_stamp(end).isoformat(sep=" ") if end else "…"
    return [tr(f"# period ]{first}, {last}] UTC", f"# période ]{first}, {last}] UTC")]


def _duration(seconds: float) -> str:
    """600 as "10 min", 3600 as "60 min", 15 as "15 s"."""
    if seconds >= 60 and seconds % 60 == 0:
        return f"{seconds / 60:g} min"
    return f"{seconds:g} s"


def plain_unit(unit: str) -> str:
    """WRF's "m s-1" as "m/s", "W m-2" as "W/m2": the units of the column names."""
    tokens = unit.split()
    if len(tokens) < 2:
        return unit or "-"
    up: list[str] = []
    down: list[str] = []
    for token in tokens:
        match = re.fullmatch(r"([A-Za-z%]+)(-?\d*)", token)
        if match is None:
            return unit
        name, power = match.groups()
        if power.startswith("-"):
            down.append(name + ("" if power == "-1" else power[1:]))
        else:
            up.append(token)
    if not down:
        return unit
    bottom = down[0] if len(down) == 1 else f"({' '.join(down)})"
    return f"{' '.join(up) or '1'}/{bottom}"


def _case(root: Path) -> Case:
    return Case.from_yaml(stage_folder(root, "main") / "case.yaml")


@router.get("/api/cases/{case_id}/export/tslist")
def export_index(request: Request, case_id: str, run: str | None = None) -> dict[str, Any]:
    """What the tslist export of the run offers: its cells (each with its points and turbines),
    the quantities in their order, the hub height, and whether a run without turbines is there."""
    from owstudio.core.windfarm.catalog import turbine_types

    root = run_root(request, case_id, run, "tslist")
    case = _case(root)
    types = turbine_types(case)
    places = tslist_export.places(stage_folder(root, "main"), case)
    # The hub heights of the run's turbines, with or without the wind farm parameterization
    hubs = sorted(
        {
            types[t.type].hub_height_m
            for farm in case.enabled_farms
            for t in farm.turbines
            if t.type in types
        }
    )
    return {
        "run_id": root.name,
        "reference": tslist_export.has_reference(root),
        "hub_heights_m": hubs,
        "places": [
            {
                "key": p.key,
                "domain": p.domain,
                "i": p.i,
                "j": p.j,
                "points": list(p.points),
                "prefixes": list(p.prefixes),
                "turbines": list(p.labels),
            }
            for p in places
        ],
        "quantities": [
            {
                "key": q.key,
                "unit": q.unit,
                "profile": q.profile,
                "between": q.between,
                "height_m": q.height,
            }
            for q in tslist_export.QUANTITIES
        ],
    }


def _table(
    request: Request,
    case_id: str,
    run: str | None,
    points: list[str],
    quantities: list[str],
    heights: list[float],
    average_s: int,
    layout: str,
    reference: bool,
    start: datetime | None,
    end: datetime | None,
) -> tuple[Path, tslist_export.Table, pd.DatetimeIndex]:
    """The table of the choice, kept to ]start, end], and all the times the files give."""
    root = run_root(request, case_id, run, "tslist")
    if not points or not quantities:
        raise HTTPException(422, tr("Choose points and quantities", "Choisir points et grandeurs"))
    if average_s < 0 or any(h <= 0 for h in heights):
        raise HTTPException(422, tr("Invalid averaging or height", "Moyenne ou hauteur invalide"))
    try:
        result = tslist_export.table(
            root, _case(root), points, quantities, heights, average_s, layout, reference
        )
    except tslist_export.ExportError as error:
        raise HTTPException(422, str(error)) from error
    times = pd.DatetimeIndex(result.frame.index).unique().sort_values()
    result.frame = tslist_export.keep_period(
        result.frame,
        naive_stamp(start) if start else None,
        naive_stamp(end) if end else None,
    )
    return root, result, times


Points = Annotated[list[str], Query()]
Quantities = Annotated[list[str], Query()]
Heights = Annotated[list[float] | None, Query()]


@router.get("/api/cases/{case_id}/export/tslist/preview")
def export_preview(
    request: Request,
    case_id: str,
    points: Points,
    quantities: Quantities,
    heights: Heights = None,
    average_s: int = 600,
    layout: str = "long",
    reference: bool = True,
    run: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict[str, Any]:
    """The file as it will be, read at the first point only so as to answer at once: its columns
    (in the wide layout, those of the first cell, repeated for each), its first rows, how many
    times in the period, the first and last times of the files, what is missing."""
    _, result, times = _table(
        request, case_id, run, points[:1], quantities, heights or [], average_s, layout,
        reference, start, end,
    )  # fmt: skip
    frame = result.frame
    return {
        "columns": [str(frame.index.name), *[str(c) for c in frame.columns]],
        "rows": records(frame.head(3), 4),
        "times": int(pd.DatetimeIndex(frame.index).nunique()),
        "first": times[0].isoformat() if len(times) else None,
        "last": times[-1].isoformat() if len(times) else None,
        "missing": result.missing,
    }


@router.get("/api/cases/{case_id}/export/tslist.csv", response_class=PlainTextResponse)
def export_csv(
    request: Request,
    case_id: str,
    points: Points,
    quantities: Quantities,
    heights: Heights = None,
    average_s: int = 600,
    layout: str = "long",
    reference: bool = True,
    run: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> Response:
    root, result, _ = _table(
        request, case_id, run, points, quantities, heights or [], average_s, layout, reference,
        start, end,
    )  # fmt: skip
    frame = result.frame
    averaging = (
        tr(
            f"{_duration(average_s)} means of every model time step over ]t - {average_s} s, t], stamped at the end t",
            f"moyennes {_duration(average_s)} de chaque pas de temps du modèle sur ]t - {average_s} s, t], datées de leur fin t",
        )
        if average_s
        else tr(
            "every model time step, no averaging", "chaque pas de temps du modèle, sans moyenne"
        )
    )
    header = [
        tr(
            f"# Source: tslist (WRF time series), project {case_id}, run {root.name}, times UTC",
            f"# Source : tslist (séries temporelles de WRF), projet {case_id}, calcul {root.name}, heures UTC",
        ),
        f"# {averaging}",
        tr("# Heights above ground", "# Hauteurs au-dessus du sol"),
    ]
    cell = tslist_export.column_name(tslist_export.BY_KEY["power_cell"], None)
    if any(str(c) == cell or str(c).startswith(f"{cell} ") for c in frame.columns):
        header.append(
            tr(
                f"# {cell}: WRF's POWER of the whole grid cell (all its turbines)",
                f"# {cell} : POWER de WRF de toute la maille (toutes ses éoliennes)",
            )
        )
    case = _case(root)
    for name, sources in result.power.items():
        how = "; ".join(power_source_text(source, case) for source in sources)
        header.append(tr(f"# {name}: {how}", f"# {name} : {how}"))
    suffix = tslist_export.no_farm()
    if any(f"{suffix} [" in str(c) for c in frame.columns):
        header.append(
            tr(
                "# _no_farm: the same quantity in the run without turbines",
                "# _sans_parc : la même grandeur dans le calcul sans éoliennes",
            )
        )
    header += _period_line(start, end)
    for name, why in result.missing.items():
        header.append(tr(f"# not available: {name}: {why}", f"# non disponible : {name} : {why}"))
    text = "".join(line + "\n" for line in header) + frame.to_csv(float_format="%.5g")
    return _attachment(text, f"{case_id}-tslist-{layout}-{average_s}s.csv")


@router.get("/api/cases/{case_id}/export/wrfout.csv", response_class=PlainTextResponse)
def export_wrfout_csv(
    request: Request,
    case_id: str,
    variable: str,
    domain: int | None = None,
    height: float | None = None,
    stage: Literal["main", "control"] = "main",
    location: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    run: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> Response:
    """One variable of the history files at one point (a turbine, a tslist point or a position),
    at each output time, interpolated between the four nearest cells; the quantities the tslist
    export also gives are written in its names and units."""
    root = run_root(request, case_id, run)
    if not location and (lat is None or lon is None):
        raise HTTPException(422, tr("Choose a point", "Choisir un point"))
    ref = SeriesRef(
        kind="run",
        case_id=case_id,
        run_id=root.name,
        variable=variable,
        domain=domain,
        stage=stage,
        reader="wrfout",
        height_m=height,
        location=location or None,
        lat=None if location else lat,
        lon=None if location else lon,
    )
    try:
        series = resolve(state(request), ref)
    except SeriesNotFound as error:
        raise HTTPException(404, str(error)) from error
    meta = series.meta
    values = series.values.to_numpy(dtype=float)
    unit = plain_unit(meta.unit)
    stem = variable
    same = next((q for q in tslist_export.QUANTITIES if q.profile and q.variable == variable), None)
    if same is not None:
        try:
            values = units.convert(values, meta.unit, same.unit)
            stem, unit = tr(same.en, same.fr), same.unit
        except units.UnitError:
            pass
    if height is not None and meta.height_ref != "surface":
        stem = f"{stem}_{height:g}m"
    if stage == "control":
        stem += tslist_export.no_farm()
    index = pd.DatetimeIndex(series.values.index)
    if index.tz is not None:
        index = index.tz_convert("UTC").tz_localize(None)
    frame = pd.DataFrame({f"{stem} [{unit}]": values}, index=index)
    frame.index.name = tr("time_utc", "temps_utc")
    frame = tslist_export.keep_period(
        frame, naive_stamp(start) if start else None, naive_stamp(end) if end else None
    )
    where = meta.location_name or meta.location
    position = (
        f" ({meta.lat:.4f}, {meta.lon:.4f})"
        if meta.lat is not None and meta.lon is not None
        else ""
    )
    domain_used = meta.extra.get("domain")
    step = _duration(meta.frequency_s) if meta.frequency_s else "?"
    header = [
        tr(
            f"# Source: wrfout (WRF history files), project {case_id}, run {root.name}, times UTC",
            f"# Source : wrfout (fichiers d'historique de WRF), projet {case_id}, calcul {root.name}, heures UTC",
        ),
        tr(
            f"# every {step} (the output interval), the value at each output time, no averaging",
            f"# toutes les {step} (l'intervalle de sortie), la valeur à chaque sortie, sans moyenne",
        ),
        tr(
            f"# point {where}{position}, domain d{domain_used:02d}" if isinstance(domain_used, int) else f"# point {where}{position}",
            f"# point {where}{position}, domaine d{domain_used:02d}" if isinstance(domain_used, int) else f"# point {where}{position}",
        ),
    ]  # fmt: skip
    if meta.method:
        header.append(f"# {meta.method}")
    if height is not None and meta.height_ref == "asl":
        header.append(tr("# heights above sea level", "# hauteurs au-dessus de la mer"))
    elif height is not None and meta.height_ref != "surface":
        header.append(tr("# heights above ground", "# hauteurs au-dessus du sol"))
    header += _period_line(start, end)
    text = "".join(line + "\n" for line in header) + frame.to_csv(float_format="%.5g")
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", f"{variable}-{where}")
    return _attachment(text, f"{case_id}-wrfout-{safe}.csv")
