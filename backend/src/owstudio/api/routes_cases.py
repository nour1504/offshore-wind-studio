"""Cases and the helpers used while editing them."""

import json
import shutil
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from functools import cache
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel

from owstudio.api.state import AppState
from owstudio.core.case.checks import check_case
from owstudio.core.case.model import Case, TimeSeries, TurbineType
from owstudio.core.case.presets import default_dynamics, offshore_wind_physics
from owstudio.core.case.transfer import export_name, export_project, missing_folders, read_project
from owstudio.core.domains import domain_outlines
from owstudio.core.engine.windows import child_case, wps_pass_case
from owstudio.core.i18n import tr
from owstudio.core.method.export import namelist_text
from owstudio.core.method.plan import plan
from owstudio.core.namelist.generate import build_namelist_input, build_namelist_wps
from owstudio.core.namelist.period import synchronize_period
from owstudio.core.tslist import locations as tslist_locations
from owstudio.core.tslist import tslist_text
from owstudio.core.windfarm.catalog import load_catalog, power_coefficients, specific_power
from owstudio.core.windfarm.coordinates import CoordinateError, Crs, parse_coordinates, utm_epsg
from owstudio.core.windfarm.files import turbine_table

router = APIRouter()


def state(request: Request) -> AppState:
    app_state: AppState = request.app.state.owstudio
    return app_state


class CaseCreated(BaseModel):
    id: str


class IssueOut(BaseModel):
    severity: str
    message: str
    field: str | None = None
    short: str | None = None
    page: str | None = None


class CoordinatesIn(BaseModel):
    text: str
    crs: Crs = "auto"
    # Projected coordinates: an EPSG code, or a UTM zone and hemisphere
    epsg: int | None = None
    utm_zone: int | None = None
    southern: bool = False
    # Centre of the domain, to choose between latitude/longitude and longitude/latitude
    near_lat: float | None = None
    near_lon: float | None = None


@cache
def namelist_schema() -> dict[str, Any]:
    text = (resources.files("owstudio.data") / "namelist_schema_4.8.0.json").read_text(
        encoding="utf-8"
    )
    schema: dict[str, Any] = json.loads(text)
    return schema


def plain(nml: Any) -> dict[str, dict[str, Any]]:
    """A Namelist as plain JSON-ready dictionaries, keeping the group order."""
    result = {group: dict(options) for group, options in nml.items()}
    for group, options in nml.items():
        if options.start_index:
            result[group]["_start_index"] = dict(options.start_index)
    return result


def preview_cases(case: Case) -> tuple[Case, Case]:
    """The namelists previewed are those exported: namelist.input of the first computed window
    (the latest), namelist.wps of the first WPS pass (its year, spin-up included)."""
    try:
        windows = plan(case)
    except (ValueError, OverflowError) as error:
        raise HTTPException(422, str(error)) from error
    return child_case(case, windows.computation[0]), wps_pass_case(case, windows.wps_passes[0])


def geometry(case: Case) -> dict[str, Any]:
    """Domains, turbines and time series locations as a GeoJSON FeatureCollection."""
    features: list[dict[str, Any]] = []
    try:
        outlines = domain_outlines(case.grid)
    except NotImplementedError:
        outlines = []
    for number, (ring, dx) in enumerate(zip(outlines, case.grid.domain_dx(), strict=False), 1):
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [ring]},
                "properties": {"kind": "domain", "number": number, "dx": dx},
            }
        )
    for farm in case.farms:
        for index, turbine in enumerate(farm.turbines, 1):
            model = case.turbine_types.get(turbine.type)
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [turbine.lon, turbine.lat]},
                    "properties": {
                        "kind": "turbine",
                        "farm": farm.id,
                        "farm_name": farm.name,
                        "farm_color": farm.appearance.color,
                        "farm_symbol": farm.appearance.symbol,
                        "enabled": farm.enabled and case.farm_scheme is not None,
                        "label": turbine.id or f"{farm.id}-{index}",
                        "number": index,
                        "type": turbine.type,
                        # For the card shown when the pointer rests on the turbine
                        "model": model.name if model else None,
                        "hub_m": model.hub_height_m if model else None,
                        "rotor_m": model.rotor_diameter_m if model else None,
                        "power_mw": model.rated_power_mw if model else None,
                    },
                }
            )
    for point in tslist_locations(case):
        if point.prefix.startswith("T") and point.name.startswith("Turbine "):
            continue  # already drawn as turbines
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [point.lon, point.lat]},
                "properties": {"kind": "probe", "name": point.name, "prefix": point.prefix},
            }
        )
    return {"type": "FeatureCollection", "features": features}


@router.get("/api/cases")
def list_cases(request: Request) -> list[dict[str, Any]]:
    app = state(request)
    summaries = []
    for summary in app.workspace.list():
        latest = app.runs.latest(summary.id)
        summaries.append(
            {**asdict(summary), "last_run_state": latest.state, "last_run_id": latest.run_id}
        )
    return summaries


@router.get("/api/blank-case")
def blank_case() -> Case:
    """A new, empty project to fill in step by step, in the order of the guide: no domain, no
    farm, no turbine model, no wind farm scheme yet; the example's physics and map position, a
    72-hour period at the start of last month, measurement points at the turbines and the
    standard windows (72 useful hours after 12 h of spin-up)."""
    example = Case.from_yaml(
        Path(str(resources.files("owstudio.data") / "examples" / "horns-rev.yaml"))
    )
    today = datetime.now(UTC).replace(tzinfo=None, hour=0, minute=0, second=0, microsecond=0)
    start = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
    data = example.model_dump(mode="json")
    data.update(
        name="New project",
        description="",
        farms=[],
        turbine_types={},
        farm_scheme=None,
        time_series=TimeSeries().model_dump(mode="json"),
        namelist_input={},
        namelist_wps={},
    )
    data["period"] = {
        **data["period"],
        "start": start.isoformat(),
        "end": (start + timedelta(hours=72)).isoformat(),
    }
    data["grid"] = {**data["grid"], "domains": []}
    return Case.model_validate(data)


@router.post("/api/cases", status_code=201)
def create_case(request: Request, case: Case) -> CaseCreated:
    return CaseCreated(id=state(request).workspace.create(case))


@router.post("/api/cases/import", status_code=201)
async def import_case(request: Request, filename: str = "") -> dict[str, Any]:
    """A project exported by the application (.zip) or a case.yaml, sent as the request body.
    Stored as a new project; a name already used gets "(imported)" so both stay apart."""
    app = state(request)
    try:
        case = read_project(await request.body(), filename)
    except ValueError as error:  # pydantic's ValidationError is a ValueError too
        raise HTTPException(422, str(error)) from error
    if case.name in {summary.name for summary in app.workspace.list()}:
        case.name = f"{case.name} ({tr('imported', 'importé')})"
    case_id = app.workspace.create(case)
    return {"id": case_id, "name": case.name, "missing_folders": missing_folders(case)}


@router.get("/api/cases/{case_id}/export")
def export_case(request: Request, case_id: str) -> Response:
    """The saved project as a file to share (without runs or results)."""
    workspace = state(request).workspace
    case = workspace.load(case_id)
    name = export_name(case)
    fallback = name.encode("ascii", "replace").decode("ascii").replace("?", "-")
    return Response(
        export_project(case, workspace.case_dir(case_id)),
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(name)}"
        },
    )


@router.get("/api/cases/{case_id}")
def get_case(request: Request, case_id: str) -> Case:
    return state(request).workspace.load(case_id)


@router.put("/api/cases/{case_id}")
def save_case(request: Request, case_id: str, case: Case) -> Case:
    """Saves the case. Queued and running runs are not affected: each runs from its own copy."""
    workspace = state(request).workspace
    synchronize_period(workspace.load(case_id), case)
    workspace.save(case_id, case)
    return case


@router.delete("/api/cases/{case_id}", status_code=204)
def delete_case(request: Request, case_id: str) -> None:
    """Deletes the case and all its runs and results."""
    app = state(request)
    if app.runs.is_running(case_id):
        raise HTTPException(
            409,
            tr(
                "Wait for the import to finish before deleting the project",
                "Attendez la fin de l'import avant de supprimer le projet",
            ),
        )
    folder = app.workspace.case_dir(case_id)
    app.workspace.load(case_id)
    shutil.rmtree(folder)


# Stateless helpers: the interface sends the case being edited, saved or not
@router.post("/api/checks")
def checks(case: Case) -> list[IssueOut]:
    return [IssueOut(**asdict(issue)) for issue in check_case(case)]


@router.post("/api/geometry")
def case_geometry(case: Case) -> dict[str, Any]:
    return geometry(case)


@router.post("/api/namelists")
def namelists(case: Case) -> dict[str, str]:
    case, wps = preview_cases(case)
    texts = {
        "namelist.wps": namelist_text(build_namelist_wps(wps)),
        "namelist.input": namelist_text(build_namelist_input(case)),
    }
    points = tslist_locations(case)
    if points:
        texts["tslist"] = tslist_text(points)
    return texts


@router.post("/api/namelists/structured")
def structured_namelists(case: Case) -> dict[str, Any]:
    """Each file as generated from the case, and after the user's overrides."""
    case, wps = preview_cases(case)
    bare = case.model_copy(update={"namelist_input": {}})
    bare_wps = wps.model_copy(update={"namelist_wps": {}})
    return {
        "namelist.input": {
            "generated": plain(build_namelist_input(bare)),
            "final": plain(build_namelist_input(case)),
        },
        "namelist.wps": {
            "generated": plain(build_namelist_wps(bare_wps)),
            "final": plain(build_namelist_wps(wps)),
        },
    }


@router.get("/api/namelist/schema")
def schema() -> dict[str, Any]:
    return namelist_schema()


@router.post("/api/presets/offshore-wind")
def offshore_wind_preset(case: Case) -> dict[str, dict[str, Any]]:
    return {
        "physics": offshore_wind_physics(case.grid.domain_dx()),
        "dynamics": default_dynamics(case.max_dom),
    }


@router.get("/api/turbines/catalog")
def turbine_catalog() -> list[dict[str, Any]]:
    return [
        {
            **entry.model_dump(),
            "specific_power": specific_power(entry.turbine),
            "max_cp": max(power_coefficients(entry.turbine)),
        }
        for entry in load_catalog()
    ]


@router.post("/api/turbines/wrf-table", response_class=PlainTextResponse)
def wrf_turbine_table(turbine: TurbineType) -> str:
    return turbine_table(turbine)


@router.post("/api/coordinates/parse")
def coordinates_parse(body: CoordinatesIn) -> dict[str, Any]:
    epsg = body.epsg
    if epsg is None and body.utm_zone is not None:
        epsg = utm_epsg(body.utm_zone, body.southern)
    near = (
        (body.near_lat, body.near_lon)
        if body.near_lat is not None and body.near_lon is not None
        else None
    )
    try:
        result = parse_coordinates(body.text, body.crs, epsg, near)
    except CoordinateError as error:
        raise HTTPException(422, str(error)) from error
    return asdict(result)
