"""Map layers and imports: KML, GeoJSON, shapefiles, zones with automatic turbine placement, namelist import."""

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from pyproj.exceptions import CRSError, ProjError
from shapefile import ShapefileException
from shapely.errors import ShapelyError

from owstudio.core.case.model import Case
from owstudio.core.geo import import_map, import_namelists, turbine_layout

router = APIRouter()


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class MapImport(Strict):
    path: str = Field(min_length=1, max_length=4096)
    crs: str | None = Field(None, max_length=4096)


class LayoutIn(Strict):
    polygon: list[list[float]] = Field(min_length=3, max_length=200_000)
    holes: list[list[list[float]]] = Field(default_factory=list)
    spacing_m: float = Field(gt=0)
    rotation_deg: float = 0
    turbine_type: int = Field(1, ge=1)
    # Between the rows (spacing_m along them by default), stagger of every other row (0 to 1),
    # distance kept from the edge of the zone
    spacing_across_m: float | None = Field(None, gt=0)
    stagger: float = Field(0.0, ge=0, lt=1)
    setback_m: float = Field(0.0, ge=0)


class NamelistImport(Strict):
    case: Case
    input: str = Field("", max_length=2_000_000)
    wps: str = Field("", max_length=2_000_000)


@router.post("/api/geo/import")
def map_import(body: MapImport) -> dict[str, Any]:
    try:
        return import_map(Path(body.path).expanduser(), body.crs)
    except FileNotFoundError as error:
        raise HTTPException(404, str(error)) from error
    except (
        ValueError,
        TypeError,
        OSError,
        ET.ParseError,
        CRSError,
        ProjError,
        ShapelyError,
        ShapefileException,
    ) as error:
        raise HTTPException(422, str(error)) from error


@router.post("/api/geo/layout")
def layout(body: LayoutIn) -> dict[str, Any]:
    try:
        return turbine_layout(
            body.polygon,
            body.spacing_m,
            body.rotation_deg,
            body.turbine_type,
            body.holes,
            body.spacing_across_m,
            body.stagger,
            body.setback_m,
        )
    except (ValueError, ProjError, ShapelyError) as error:
        raise HTTPException(422, str(error)) from error


@router.post("/api/geo/namelist-import")
def namelist_import(body: NamelistImport) -> dict[str, Any]:
    try:
        return import_namelists(body.case, body.input, body.wps)
    except (ValueError, TypeError, OverflowError) as error:
        raise HTTPException(422, str(error)) from error
