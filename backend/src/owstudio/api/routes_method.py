"""The files of the method (core/method): preview, ZIP download and extraction to a folder."""

import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ValidationError

from owstudio.api.routes_cases import state
from owstudio.core.case.checks import _check_method
from owstudio.core.case.model import Case
from owstudio.core.engine.profiles import seen_here
from owstudio.core.i18n import tr
from owstudio.core.method import plan as method
from owstudio.core.method.export import ExportOptions, export_files, export_zip, write_folder

router = APIRouter()


class PreviewBody(BaseModel):
    case: Case
    options: ExportOptions = ExportOptions()


class FolderBody(BaseModel):
    options: ExportOptions = ExportOptions()
    folder: str
    # An earlier extraction is replaced, its downloaded data kept
    replace: bool = False


def _issues(case: Case) -> list[dict[str, str]]:
    return [{"severity": i.severity, "message": i.message} for i in _check_method(case)]


@router.post("/api/method/plan")
def window_plan(case: Case) -> dict[str, Any]:
    """The windows of the project, chronological, with their order of computation."""
    try:
        found = method.plan(case)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return {
        "start": found.start,
        "end": found.end,
        "spin_up_hours": found.spin_up_hours,
        "useful_hours": found.useful_hours,
        "grouping": found.grouping,
        "single": found.single,
        "restart": found.restart,
        "simulated_hours": found.simulated_seconds / 3600,
        "blocks": [{"id": b.id, "start": b.start, "end": b.end} for b in found.blocks],
        "windows": [
            {
                "id": w.id,
                "order": w.order,
                "block": w.block,
                "simulation_start": w.simulation_start,
                "simulation_end": w.simulation_end,
                "useful_start": w.useful_start,
                "useful_end": w.useful_end,
                "restart": w.restart,
            }
            for w in found.windows
        ],
        "wps_passes": [{"year": p.year, "start": p.start, "end": p.end} for p in found.wps_passes],
    }


@router.post("/api/method/files")
def preview(body: PreviewBody) -> dict[str, Any]:
    """Every exported file with its text, and the checks of the method."""
    try:
        files = export_files(body.case, body.options)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return {
        "files": [
            {"path": path, "text": text, "executable": executable}
            for path, (text, executable) in sorted(files.items())
        ],
        "issues": _issues(body.case),
    }


@router.get("/api/cases/{case_id}/method/files.zip")
def download(request: Request, case_id: str, options: str = "{}") -> Response:
    """The ZIP of the saved project, for the browser's or the window's download."""
    case = state(request).workspace.load(case_id)
    try:
        chosen = ExportOptions.model_validate(json.loads(options))
        name, data = export_zip(case, chosen)
    except (ValueError, ValidationError) as error:
        raise HTTPException(422, str(error)) from error
    return Response(
        data,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=\"{name}\"; filename*=UTF-8''{quote(name)}"
        },
    )


def _extracted(request: Request, case_id: str, folder: str) -> Path:
    """The folder ``folder``/<project>-WRF where the files of the project are extracted."""
    from owstudio.core.method.export import safe_name

    case = state(request).workspace.load(case_id)
    parent = Path(folder).expanduser()
    if not folder.strip() or not parent.is_dir():
        raise HTTPException(404, tr("Folder not found", "Dossier introuvable"))
    return parent / f"{safe_name(case.name)}-WRF"


def _ours(target: Path) -> bool:
    """Written by an extraction (its manifest is there): the only folders replaced or deleted."""
    return (target / "manifest.json").is_file() and (target / "wps").is_dir()


@router.get("/api/cases/{case_id}/method/folder")
def folder_state(request: Request, case_id: str, folder: str) -> dict[str, Any]:
    """Whether the files of the project were already extracted in ``folder``."""
    target = _extracted(request, case_id, folder)
    exists = target.exists() and any(target.iterdir())
    return {"folder": str(target), "exists": exists, "ours": exists and _ours(target)}


@router.post("/api/cases/{case_id}/method/folder")
def to_folder(request: Request, case_id: str, body: FolderBody) -> dict[str, Any]:
    """Writes the files of the saved project into a new folder inside ``folder``; with
    ``replace``, an earlier extraction is emptied first, except its downloaded data."""
    import shutil

    from owstudio.core.method.scripts import FILE_NAMES

    case = state(request).workspace.load(case_id)
    target = _extracted(request, case_id, body.folder)
    if target.exists() and any(target.iterdir()):
        if not (body.replace and _ours(target)):
            raise HTTPException(
                409,
                tr(
                    f"{target} already exists and is not empty",
                    f"{target} existe déjà et n'est pas vide",
                ),
            )
        kept = {names["data"] for names in FILE_NAMES.values()}
        for item in target.iterdir():
            if item.name in kept and item.is_dir():
                continue
            if item.is_dir() and not item.is_symlink():
                shutil.rmtree(item)
            else:
                item.unlink()
    try:
        names = write_folder(case, body.options, target)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return {"folder": str(target), "files": names}


@router.get("/api/cases/{case_id}/method/progress")
def run_progress(request: Request, case_id: str, folder: str) -> dict[str, Any]:
    """Where the calculation of the files extracted in ``folder`` stands (core/method/progress.py)."""
    from owstudio.core.method.progress import progress

    target = _extracted(request, case_id, folder)
    if not _ours(target):
        return {"state": "none"}
    return progress(target)


@router.post("/api/method/estimate")
def computing_estimate(request: Request, case: Case) -> dict[str, Any]:
    """Order of magnitude of WRF's computing time and memory (core/method/estimate.py), with the
    physical cores and the memory of the engine machine (half of this computer's for WSL, its
    default limit)."""
    import psutil

    from owstudio.core.method.estimate import estimate
    from owstudio.core.settings import physical_cores

    try:
        found = estimate(case)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    memory = psutil.virtual_memory().total
    try:
        if state(request).settings.profile(None).kind == "wsl":
            memory //= 2
    except KeyError:
        pass
    return {**found, "physical_cores": physical_cores(), "memory_total": memory}


@router.delete("/api/cases/{case_id}/method/folder")
def delete_folder(request: Request, case_id: str, folder: str) -> dict[str, Any]:
    """Deletes an extraction of the project, data and results included."""
    import shutil

    target = _extracted(request, case_id, folder)
    if not target.exists():
        return {"folder": str(target), "deleted": False}
    if not _ours(target):
        raise HTTPException(
            409,
            tr(
                f"{target} was not written by an extraction",
                f"{target} n'a pas été écrit par une extraction",
            ),
        )
    shutil.rmtree(target)
    return {"folder": str(target), "deleted": True}


@router.post("/api/method/vertical")
def vertical_levels(case: Case) -> dict[str, Any]:
    """The full levels of real.exe over the sea (heights of the base state), the mass levels,
    the rotor of each turbine model in use, the levels of the time series profiles, and the
    checks of these settings (core/method/vertical_advice.py)."""
    from owstudio.core.energy.curves import turbine_types
    from owstudio.core.method import vertical, vertical_advice

    if not case.max_dom:
        return {"error": None, "levels": [], "mass_heights_m": [], "turbines": [], "checks": []}
    checks = vertical_advice.as_json(vertical_advice.checks(case))
    try:
        found = vertical.profile(case)
    except vertical.VerticalError as error:
        return {
            "error": str(error),
            "levels": [],
            "mass_heights_m": [],
            "turbines": [],
            "checks": checks,
        }
    used: dict[int, int] = {}
    for farm in case.farms:
        for turbine in farm.turbines:
            used[turbine.type] = used.get(turbine.type, 0) + 1
    types = turbine_types(case)
    turbines = []
    for number, count in sorted(used.items()):
        model = types.get(number)
        if model is None:
            continue
        low = model.hub_height_m - model.rotor_diameter_m / 2
        high = model.hub_height_m + model.rotor_diameter_m / 2
        turbines.append(
            {
                "type": number,
                "name": model.name or f"Type {number}",
                "count": count,
                "hub_height_m": model.hub_height_m,
                "rotor_diameter_m": model.rotor_diameter_m,
                "levels_in_rotor": sum(low <= z <= high for z in found.mass_heights_m),
            }
        )
    series = case.time_series
    top_level = min(series.max_levels, case.grid.e_vert - 1) if series else None
    return {
        "error": None,
        "levels": [
            {"number": lv.number, "eta": lv.eta, "height_m": lv.height_m, "dz_m": lv.dz_m}
            for lv in found.full
        ],
        "mass_heights_m": found.mass_heights_m,
        "top_m": found.top_m,
        "turbines": turbines,
        "time_series_levels": top_level,
        "time_series_top_m": found.mass_heights_m[top_level - 1] if top_level else None,
        "checks": checks,
    }


class SceneBody(BaseModel):
    case: Case
    domain: int = 1
    # Where the relief is on this computer, whatever the names of the folders: the geo_em file of
    # the domain, or a folder holding it or a WPS_GEOG geography (searched below). Empty: the
    # geography of the engine
    relief: str | None = None
    # False: no download of public elevation tiles (flat terrain when nothing else is there)
    tiles: bool = True
    # The public tiles before the geography (chosen in the view); the geography if they fail
    tiles_first: bool = False


def _modified(folder: Path) -> float | None:
    try:
        return folder.stat().st_mtime
    except OSError:
        return None


@router.post("/api/method/scene")
def scene_3d(request: Request, body: SceneBody) -> dict[str, Any]:
    """Terrain and the height of every level over it, for the 3D view of the levels: the relief
    given, else the geography of the engine, else the public tiles, else flat."""
    from owstudio.core.method import scene, vertical

    app = state(request)
    storage = app.storage
    given = Path(body.relief.strip()).expanduser() if body.relief and body.relief.strip() else None
    geo_em: Path | None = None
    geogs: list[Path] = []
    missing: list[str] = []
    if given is not None:
        if given.is_file():
            geo_em = given
        elif given.is_dir():
            geo_em = scene.find_geo_em(given, body.domain)
            if geo_em is None:
                geogs.append(given)
        else:
            missing.append(tr(f"Not found: {given}", f"Introuvable : {given}"))
    engine = engine_geography(app.settings)
    if engine is not None and engine not in geogs:
        geogs.append(engine)
    # A view already drawn comes back at once, even offline
    key = hashlib.sha256(
        json.dumps(
            [
                SCENE_VERSION,
                body.model_dump(mode="json"),
                [str(g) for g in geogs],
                # A geography changed in place (a resolution added) is read again
                [_modified(g) for g in geogs],
                str(geo_em),
                geo_em.stat().st_mtime if geo_em and geo_em.is_file() else None,
            ],
            sort_keys=True,
        ).encode()
    ).hexdigest()[:32]
    folder = storage.input("scenes")
    cached = folder / f"{key}.json"
    if cached.is_file():
        found: dict[str, Any] = json.loads(cached.read_text(encoding="utf-8"))
        return found
    try:
        found = scene.scene(
            body.case,
            body.domain,
            geo_em,
            geogs,
            storage.input("elevation") if body.tiles else None,
            tiles_first=body.tiles_first,
        )
    except vertical.VerticalError as error:
        raise HTTPException(422, str(error)) from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    found["problems"] = missing + found["problems"]
    # Only complete scenes are kept: one that fell back (tiles offline, folder not there yet) is
    # redrawn next time
    if not found["problems"]:
        folder.mkdir(parents=True, exist_ok=True)
        temporary = cached.with_suffix(".part")
        temporary.write_text(json.dumps(found), encoding="utf-8")
        temporary.replace(cached)
        # Keep the 40 most recent scenes
        for old in sorted(folder.glob("*.json"), key=lambda f: f.stat().st_mtime)[:-40]:
            old.unlink(missing_ok=True)
    return found


# Changes when the content of a scene changes, so that cached scenes are redrawn
SCENE_VERSION = 4


def engine_geography(settings: Any) -> Path | None:
    """The WPS_GEOG folder of the default engine, as this computer sees it, when it exists:
    inside the WSL distribution of a WSL engine, or the folder of a local Linux engine."""
    try:
        profile = settings.profile(None)
    except KeyError:
        return None
    path = seen_here(profile, profile.install.geog_dir)
    if path is None:
        return None
    try:
        return path if path.is_dir() else None
    except OSError:
        return None


@router.post("/api/method/cells")
def farm_cells(case: Case) -> dict[str, Any]:
    """The whole grid of the farm domain, for the map: one line per grid line (rank 0 every tenth,
    1 every fifth, 2 the others, so that the map can thin them out when zoomed out), and one
    polygon per cell holding turbines, with their number and names. Exactly the cells of
    cell_of: cell (i, j) covers [west + (i - 1) dx, west + i dx] x [south + (j - 1) dx, south + j dx]
    in the projection, the corners brought back to longitude and latitude."""
    from owstudio.core import tslist
    from owstudio.core.domains import domain_extents, projection_for

    if not case.max_dom or not any(farm.turbines for farm in case.farms):
        return {
            "domain": None,
            "dx_m": None,
            "geojson": {"type": "FeatureCollection", "features": []},
            "cells": [],
        }
    found = tslist.cells(case)
    domain = tslist.farm_domain(case)
    extent = domain_extents(case.grid)[domain - 1]
    spec = case.grid.domains[domain - 1]
    proj = projection_for(case.grid.projection)
    columns, rows = spec.e_we - 1, spec.e_sn - 1

    def point(x: float, y: float) -> list[float]:
        lat, lon = proj.inverse(x, y)
        return [round(lon, 6), round(lat, 6)]

    def rank(n: int) -> int:
        return 0 if n % 10 == 0 else 1 if n % 5 == 0 else 2

    features: list[dict[str, Any]] = []
    # Grid lines, each a polyline dense enough to follow the projection (at most 64 segments)
    steps_y = max(1, -(-rows // 64))
    steps_x = max(1, -(-columns // 64))
    along_y = [*range(0, rows, steps_y), rows]
    along_x = [*range(0, columns, steps_x), columns]
    for n in range(columns + 1):
        x = extent.west + n * extent.dx
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [point(x, extent.south + m * extent.dx) for m in along_y],
                },
                "properties": {"kind": "line", "rank": rank(n)},
            }
        )
    for m in range(rows + 1):
        y = extent.south + m * extent.dx
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": [point(extent.west + n * extent.dx, y) for n in along_x],
                },
                "properties": {"kind": "line", "rank": rank(m)},
            }
        )
    for cell in found:
        x0 = extent.west + (cell.i - 1) * extent.dx
        y0 = extent.south + (cell.j - 1) * extent.dx
        corners = [
            (x0, y0),
            (x0 + extent.dx, y0),
            (x0 + extent.dx, y0 + extent.dx),
            (x0, y0 + extent.dx),
            (x0, y0),
        ]
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [[point(x, y) for x, y in corners]]},
                "properties": {
                    "kind": "cell",
                    "i": cell.i,
                    "j": cell.j,
                    "count": len(cell.turbines),
                    "turbines": ", ".join(t.label for t in cell.turbines),
                    "farms": ", ".join(cell.farms),
                    "prefix": cell.prefix or "",
                },
            }
        )
    return {
        "domain": domain,
        "dx_m": extent.dx,
        "geojson": {"type": "FeatureCollection", "features": features},
        "cells": [
            {
                "i": cell.i,
                "j": cell.j,
                "count": len(cell.turbines),
                "turbines": [t.label for t in cell.turbines],
                "farms": cell.farms,
                "prefix": cell.prefix,
                "prefixes": [t.prefix for t in cell.turbines if t.prefix],
            }
            for cell in found
        ],
    }
