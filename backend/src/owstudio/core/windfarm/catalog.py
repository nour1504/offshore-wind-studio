"""Turbine catalogue: published reference turbines with power and thrust curves."""

import math
from functools import cache
from importlib import resources

import yaml
from pydantic import BaseModel

from owstudio.core.case.model import TurbineType

AIR_DENSITY = 1.225  # kg m-3, standard sea-level air
BETZ_LIMIT = 16 / 27


class CatalogEntry(BaseModel):
    id: str
    name: str
    origin: str | None = None
    power_curve_type: str | None = None
    cut_in_wind_speed: float | None = None
    rated_wind_speed: float | None = None
    cut_out_wind_speed: float | None = None
    source: str
    license: str
    turbine: TurbineType


@cache
def load_catalog() -> tuple[CatalogEntry, ...]:
    folder = resources.files("owstudio.data") / "turbines"
    entries = [
        CatalogEntry.model_validate(yaml.safe_load(item.read_text(encoding="utf-8")))
        for item in folder.iterdir()
        if item.name.endswith(".yaml")
    ]
    return tuple(sorted(entries, key=lambda e: (e.turbine.rated_power_mw, e.name)))


def specific_power(turbine: TurbineType) -> float:
    """Rated power per swept area, W m-2."""
    area = math.pi * (turbine.rotor_diameter_m / 2) ** 2
    return turbine.rated_power_mw * 1e6 / area


def power_coefficients(turbine: TurbineType) -> list[float]:
    """Cp at each curve point, from P = 0.5 rho A U^3 Cp."""
    area = math.pi * (turbine.rotor_diameter_m / 2) ** 2
    return [
        p.power_kw * 1000 / (0.5 * AIR_DENSITY * area * p.wind_speed**3) if p.wind_speed > 0 else 0
        for p in turbine.curve
    ]
