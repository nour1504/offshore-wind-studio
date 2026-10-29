"""Variable explorer: variables of a run's outputs, their fiches, the diagnostics available, and
the extraction of series and maps in the common format."""

import io
import json
import re
from functools import cache
from importlib import resources
from typing import Any, Literal

import numpy as np
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field

from owstudio.api.routes_cases import state
from owstudio.core import extract  # noqa: F401  (registers the "run" series resolver)
from owstudio.core import series as series_format
from owstudio.core.case.model import Case, Grid
from owstudio.core.extract.catalogue import DIAGNOSTICS, availability
from owstudio.core.extract.history import HistoryFiles, domains
from owstudio.core.extract.points import TimeSeriesFiles, field_at
from owstudio.core.extract.quantities import Unavailable
from owstudio.core.extract.runs import run_outputs
from owstudio.core.i18n import tr
from owstudio.core.postproc import mapimage
from owstudio.core.postproc.results import field_png, legend_colors
from owstudio.core.postproc.windowed import time_series_sources
from owstudio.core.series import VARIABLES
from owstudio.core.series.sources import SeriesNotFound, SeriesRef, resolve

router = APIRouter()
Stage = Literal["main", "control"]


@cache
def catalogue() -> dict[str, dict[str, Any]]:
    text = (resources.files("owstudio.data") / "variables_4.8.0.json").read_bytes().decode("utf-8")
    variables: dict[str, dict[str, Any]] = json.loads(text)["variables"]
    return variables


def _outputs(request: Request, case_id: str, run_id: str, stage: str) -> Any:
    state(request).workspace.load(case_id)
    try:
        return run_outputs(state(request), case_id, "" if run_id == "latest" else run_id, stage)
    except SeriesNotFound as error:
        raise HTTPException(404, str(error)) from error


def _files(request: Request, case_id: str, run_id: str, stage: str, domain: int) -> HistoryFiles:
    outputs = _outputs(request, case_id, run_id, stage)
    try:
        return HistoryFiles(outputs.folder(stage), domain)
    except FileNotFoundError as error:
        raise HTTPException(404, str(error)) from error


@router.get("/api/cases/{case_id}/runs/{run_id}/variables")
def run_variables(
    request: Request, case_id: str, run_id: str, stage: Stage = "main"
) -> dict[str, Any]:
    """Variables of the history files, per domain, with their catalogue entry."""
    outputs = _outputs(request, case_id, run_id, stage)
    known = catalogue()
    result = {}
    for domain in domains(outputs.folder(stage)):
        files = HistoryFiles(outputs.folder(stage), domain)
        result[str(domain)] = [
            {
                "name": v.name,
                "dims": list(v.dims),
                "units": v.units,
                "description": v.description,
                "stagger": v.stagger,
                "vertical": v.vertical,
                "in_catalogue": v.name in known,
            }
            for v in files.variables.values()
            if v.horizontal and v.name not in ("Times",)
        ]
    times = {}
    for domain in domains(outputs.folder(stage)):
        files = HistoryFiles(outputs.folder(stage), domain)
        times[str(domain)] = [t.isoformat() for t in files.times]
    tslist = TimeSeriesFiles(outputs.folder(stage) / "tslist")
    return {
        "run_id": outputs.run_id,
        "domains": result,
        "times": times,
        "tslist": [
            {
                "prefix": loc.prefix,
                "name": loc.name,
                "domain": loc.domain,
                "lat": loc.lat,
                "lon": loc.lon,
                "elevation": loc.elevation,
            }
            for loc in tslist.locations()
        ],
    }


@router.get("/api/cases/{case_id}/runs/{run_id}/diagnostics")
def run_diagnostics(
    request: Request, case_id: str, run_id: str, domain: int | None = None, stage: Stage = "main"
) -> dict[str, Any]:
    """Each diagnostic: direct, derivable or impossible with this run's files, and how."""
    outputs = _outputs(request, case_id, run_id, stage)
    available = domains(outputs.folder(stage))
    chosen = domain or (max(available) if available else None)
    files = HistoryFiles(outputs.folder(stage), chosen) if chosen in available else None
    tslist = any(s.folder.is_dir() for s in time_series_sources(outputs.folder(stage) / "tslist"))
    return {"run_id": outputs.run_id, "domain": chosen, "diagnostics": availability(files, tslist)}


# Registry files of atmospheric chemistry: thousands of entries, rarely what a wind study needs
_CHEMISTRY = {"registry.chem", "registry.var_chem", "registry.wrfvarchem"}
_REGISTRY_NAME = re.compile(r"^[A-Za-z0-9_]{1,40}$")


@router.get("/api/variables")
def search_variables(q: str = "", limit: int = 50, names: str = "") -> list[dict[str, Any]]:
    """WRF Registry variables matching the text (name or description), or, with `names`
    (comma separated), exactly these variables in this order. Names a history file cannot list
    (blanks, dashes) are left out; chemistry comes after the meteorological variables."""
    known = catalogue()
    if names:
        wanted = [name.strip().upper() for name in names.split(",") if name.strip()]
        return [known[name] for name in wanted if name in known][:500]
    text = q.strip().lower()
    hits = [
        v for v in known.values()
        if _REGISTRY_NAME.match(v["name"])
        and (not text or text in v["name"].lower() or text in str(v["description"]).lower())
    ]  # fmt: skip
    hits.sort(
        key=lambda v: (
            v["name"].lower() != text,
            not v["name"].lower().startswith(text),
            v["file"] in _CHEMISTRY,
            not v["history"],
            v["name"],
        )
    )
    return hits[: max(1, min(limit, 500))]


@router.get("/api/variables/{name}")
def variable_fiche(
    request: Request,
    name: str,
    case_id: str | None = None,
    run_id: str | None = None,
    domain: int | None = None,
) -> dict[str, Any]:
    """Fiche of a WRF variable or of a diagnostic: meaning, unit, dimensions and stagger, I/O
    streams, schemes that allocate it, how to add it to the history files, and, with a run,
    the attributes written in its files."""
    diagnostic = next((d for d in DIAGNOSTICS if d.key == name), None)
    entry = catalogue().get(name.upper())
    if diagnostic is None and entry is None:
        raise HTTPException(
            404,
            tr(
                f"Unknown variable or diagnostic {name!r}",
                f"Variable ou diagnostic inconnu : {name!r}",
            ),
        )
    fiche: dict[str, Any] = {"name": name}
    if entry is not None:
        fiche["registry"] = entry
        fiche["in_history_by_default"] = bool(entry["history"])
        fiche["how_to_add"] = (
            "Already written to the history files."
            if entry["history"]
            else f"Add {entry['name']} to the history outputs (Outputs page): iofields line +:h:0:{entry['name']}."
        )
    if diagnostic is not None:
        fiche["diagnostic"] = next(d for d in availability(None, False) if d["key"] == name)
        fiche["canonical"] = (
            {"unit": VARIABLES[name].unit, "description": VARIABLES[name].description}
            if name in VARIABLES
            else None
        )
    if case_id and run_id and entry is not None:
        files = _files(request, case_id, run_id, "main", domain or 1)
        info = files.variables.get(entry["name"])
        if info:
            fiche["file"] = {
                "dims": list(info.dims),
                "units": info.units,
                "description": info.description,
                "stagger": info.stagger,
            }
    return fiche


class SeriesRequest(BaseModel):
    refs: list[SeriesRef] = Field(min_length=1, max_length=50)


@router.post("/api/explore/series", response_model=None)
def extract_series(
    request: Request, body: SeriesRequest, format: Literal["json", "csv"] = "json"
) -> Response | dict[str, Any]:
    """Series in the common format: JSON (metadata, times, values) or the long CSV table."""
    found = []
    for ref in body.refs:
        try:
            found.append(resolve(state(request), ref))
        except SeriesNotFound as error:
            raise HTTPException(404, str(error)) from error
    if format == "csv":
        frame = series_format.to_frame(found)
        buffer = io.StringIO()
        frame.to_csv(buffer, index=False, float_format="%.6g")
        metadata = "".join(f"# {json.dumps(s.meta.model_dump(mode='json'))}\n" for s in found)
        return PlainTextResponse(
            metadata + buffer.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="series.csv"'},
        )
    return {
        "series": [
            {
                "meta": s.meta.model_dump(mode="json"),
                "times": [t.isoformat() for t in s.times],
                "values": [None if not np.isfinite(v) else float(v) for v in s.values.to_numpy()],
            }
            for s in found
        ]
    }


def _field(
    request: Request,
    case_id: str,
    run_id: str,
    stage: str,
    domain: int,
    variable: str,
    time: int,
    height: float | None,
    height_ref: str,
) -> tuple[np.ndarray, str, str, HistoryFiles]:
    files = _files(request, case_id, run_id, stage, domain)
    if not 0 <= time < len(files.times):
        raise HTTPException(404, tr("No output at this time", "Aucune sortie à cet instant"))
    try:
        values, unit, method = field_at(files, time, variable, height, height_ref)
    except (Unavailable, KeyError) as error:
        raise HTTPException(422, f"{variable}: {error}") from error
    return values, unit, method, files


def _grid(files: HistoryFiles) -> Grid | None:
    """The grid of the case that produced the outputs (its snapshot is kept beside them)."""
    snapshot = files.folder / "case.yaml"
    return Case.from_yaml(snapshot).grid if snapshot.is_file() else None


def _corners(files: HistoryFiles) -> list[list[float]]:
    """Corners of the grid of mass points, clockwise from the top left, as [lon, lat]: the image
    pixels are the cells, so the corners are extended by half a cell."""
    lat, lon = files.coordinates

    def corner(j: int, i: int, dj: int, di: int) -> list[float]:
        return [
            float(lon[j, i] + 0.5 * (lon[j, i] - lon[j - dj, i - di])),
            float(lat[j, i] + 0.5 * (lat[j, i] - lat[j - dj, i - di])),
        ]

    return [corner(-1, 0, 1, -1), corner(-1, -1, 1, 1), corner(0, -1, -1, 1), corner(0, 0, -1, -1)]


COLORMAPS = {
    "wind_direction": "twilight",
    "turbulence_intensity": "magma",
    "tke": "magma",
    "power": "magma",
}


@router.get("/api/cases/{case_id}/runs/{run_id}/map")
def map_meta(
    request: Request, case_id: str, run_id: str, variable: str, domain: int, time: int = 0,
    height: float | None = None, height_ref: Literal["agl", "asl"] = "agl", stage: Stage = "main",
) -> dict[str, Any]:  # fmt: skip
    values, unit, method, files = _field(
        request, case_id, run_id, stage, domain, variable, time, height, height_ref
    )
    finite = values[np.isfinite(values)]
    vmin, vmax = (
        (float(np.percentile(finite, 1)), float(np.percentile(finite, 99)))
        if finite.size
        else (0.0, 1.0)
    )
    colormap = COLORMAPS.get(variable, "viridis")
    return {
        "variable": variable,
        "unit": unit,
        "method": method,
        "time": files.times[time].isoformat(),
        "vmin": vmin,
        "vmax": vmax if vmax > vmin else vmin + 1.0,
        "colormap": colormap,
        "colors": legend_colors(colormap),
        # On the map's projection when the grid is known (see mapimage.py), else the grid corners
        "coordinates": mapimage.corners(grid, domain, values.shape)
        if (grid := _grid(files))
        else _corners(files),
    }


@router.get("/api/cases/{case_id}/runs/{run_id}/map.png")
def map_png(
    request: Request, case_id: str, run_id: str, variable: str, domain: int, time: int = 0,
    height: float | None = None, height_ref: Literal["agl", "asl"] = "agl", stage: Stage = "main",
    vmin: float | None = None, vmax: float | None = None,
) -> Response:  # fmt: skip
    values, _, _, files = _field(
        request, case_id, run_id, stage, domain, variable, time, height, height_ref
    )
    finite = values[np.isfinite(values)]
    low = vmin if vmin is not None else (float(np.percentile(finite, 1)) if finite.size else 0.0)
    high = vmax if vmax is not None else (float(np.percentile(finite, 99)) if finite.size else 1.0)
    grid = _grid(files)
    png = field_png(
        mapimage.reproject(values, grid, domain) if grid else values,
        low,
        high if high > low else low + 1.0,
        COLORMAPS.get(variable, "viridis"),
        north_up=grid is not None,
    )
    return Response(png, media_type="image/png", headers={"Cache-Control": "max-age=3600"})
