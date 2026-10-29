"""ERA5 reanalysis from the Copernicus Climate Data Store.

Needs a free CDS account, its API key in ~/.cdsapirc, and the ERA5 licences accepted once on
the CDS website. Files are requested per day in GRIB, over the outer domain plus a margin, and
read by ungrib with WPS's Vtable.ECMWF.
"""

import hashlib
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from owstudio.core.case.model import Grid, Period
from owstudio.core.domains import domain_outlines
from owstudio.core.i18n import tr

CDS_URL = "https://cds.climate.copernicus.eu/api"
CDSAPI_RC = Path.home() / ".cdsapirc"
ARCHIVE_START = datetime(1940, 1, 1)
# ERA5 is published about five days behind real time
PUBLICATION_DELAY = timedelta(days=6)
AREA_MARGIN_DEG = 2.0
GRID_STEP_DEG = 0.25

PRESSURE_LEVELS = [
    "1", "2", "3", "5", "7", "10", "20", "30", "50", "70", "100", "125", "150", "175", "200",
    "225", "250", "300", "350", "400", "450", "500", "550", "600", "650", "700", "750", "775",
    "800", "825", "850", "875", "900", "925", "950", "975", "1000",
]  # fmt: skip
PRESSURE_VARIABLES = [
    "geopotential",
    "relative_humidity",
    "temperature",
    "u_component_of_wind",
    "v_component_of_wind",
]
# Every field of Vtable.ECMWF available on single levels
SINGLE_VARIABLES = [
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
    "2m_temperature",
    "2m_dewpoint_temperature",
    "land_sea_mask",
    "geopotential",
    "surface_pressure",
    "mean_sea_level_pressure",
    "skin_temperature",
    "sea_surface_temperature",
    "sea_ice_cover",
    "snow_depth",
    "soil_temperature_level_1",
    "soil_temperature_level_2",
    "soil_temperature_level_3",
    "soil_temperature_level_4",
    "volumetric_soil_water_layer_1",
    "volumetric_soil_water_layer_2",
    "volumetric_soil_water_layer_3",
    "volumetric_soil_water_layer_4",
]


@dataclass(frozen=True)
class Era5Request:
    dataset: str
    request: dict[str, Any]
    name: str


def area_for(grid: Grid) -> list[float]:
    """[north, west, south, east] covering the outer domain plus a margin, on the 0.25° grid."""
    ring = domain_outlines(grid)[0]
    lons, lats = [p[0] for p in ring], [p[1] for p in ring]

    def snap(value: float, up: bool) -> float:
        steps = value / GRID_STEP_DEG
        return (math.ceil(steps) if up else math.floor(steps)) * GRID_STEP_DEG

    return [
        min(90.0, snap(max(lats) + AREA_MARGIN_DEG, up=True)),
        max(-180.0, snap(min(lons) - AREA_MARGIN_DEG, up=False)),
        max(-90.0, snap(min(lats) - AREA_MARGIN_DEG, up=False)),
        min(180.0, snap(max(lons) + AREA_MARGIN_DEG, up=True)),
    ]


def times_for(period: Period) -> list[datetime]:
    if period.interval_seconds % 3600:
        raise ValueError(
            tr(
                "ERA5 is hourly: interval_seconds must be a multiple of 3600",
                "ERA5 est horaire : interval_seconds doit être un multiple de 3600",
            )
        )
    step = timedelta(seconds=period.interval_seconds)
    times, t = [], period.start
    while t <= period.end:
        times.append(t)
        t += step
    return times


def availability_error(period: Period, now: datetime | None = None) -> str | None:
    """Why ERA5 cannot cover the period, or None."""
    now = now or datetime.now(UTC).replace(tzinfo=None)
    if period.start < ARCHIVE_START:
        return tr(
            f"ERA5 starts on {ARCHIVE_START:%Y-%m-%d}.",
            f"ERA5 commence le {ARCHIVE_START:%d/%m/%Y}.",
        )
    if period.end > now - PUBLICATION_DELAY:
        return tr(
            "ERA5 is published about 5 days behind real time; choose an earlier period or GFS.",
            "ERA5 est publié avec environ 5 jours de retard ; choisissez une période plus ancienne ou GFS.",
        )
    if period.start.minute or period.start.second:
        return tr(
            "ERA5 is hourly: the simulation must start on the hour.",
            "ERA5 est horaire : la simulation doit commencer à une heure pile.",
        )
    return None


def requests_for(period: Period, grid: Grid) -> list[Era5Request]:
    """Two requests per day (pressure and single levels), named after their content."""
    area = area_for(grid)
    hours_by_day: dict[datetime, list[str]] = defaultdict(list)
    for t in times_for(period):
        hours_by_day[t.replace(hour=0)].append(f"{t:%H}:00")
    requests = []
    for day, hours in sorted(hours_by_day.items()):
        common = {
            "product_type": ["reanalysis"],
            "year": [f"{day:%Y}"],
            "month": [f"{day:%m}"],
            "day": [f"{day:%d}"],
            "time": hours,
            "area": area,
            "data_format": "grib",
            "download_format": "unarchived",
        }
        for dataset, kind, extra in (
            (
                "reanalysis-era5-pressure-levels",
                "pl",
                {"variable": PRESSURE_VARIABLES, "pressure_level": PRESSURE_LEVELS},
            ),
            ("reanalysis-era5-single-levels", "sl", {"variable": SINGLE_VARIABLES}),
        ):
            request = {**common, **extra}
            digest = hashlib.sha1(json.dumps(request, sort_keys=True).encode()).hexdigest()[:10]
            requests.append(
                Era5Request(dataset, request, f"era5-{kind}-{day:%Y%m%d}-{digest}.grib")
            )
    return requests


def has_api_key() -> bool:
    return CDSAPI_RC.exists() and "key:" in CDSAPI_RC.read_text(encoding="utf-8")


def save_api_key(key: str) -> None:
    """Writes the CDS configuration read by the official cdsapi client."""
    key = key.strip()
    if not key or any(c in key for c in "\r\n"):
        raise ValueError(
            tr("The key must be a single line", "La clé doit tenir sur une seule ligne")
        )
    CDSAPI_RC.write_text(f"url: {CDS_URL}\nkey: {key}\n", encoding="utf-8")
