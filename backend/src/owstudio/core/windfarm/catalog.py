"""Turbine catalogue: published reference turbines with power and thrust curves."""

import math
from functools import cache
from importlib import resources

import numpy as np
from pydantic import BaseModel

from owstudio.core.case.model import Case, TurbineType, read_yaml

AIR_DENSITY = 1.225  # kg m-3, standard sea-level air
BETZ_LIMIT = 16 / 27
# The table WRF ships as wind-turbine-1.tbl
WRF_BUILT_IN_TYPE_1 = "wrf-generic-2mw"


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
        CatalogEntry.model_validate(read_yaml(item.read_text(encoding="utf-8")))
        for item in folder.iterdir()
        if item.name.endswith(".yaml")
    ]
    return tuple(sorted(entries, key=lambda e: (e.turbine.rated_power_mw, e.name)))


def turbine_types(case: Case) -> dict[int, TurbineType]:
    """Turbine tables in effect: the case's own, plus WRF's built-in type 1 if used."""
    types = dict(case.turbine_types)
    if 1 not in types and any(t.type == 1 for farm in case.farms for t in farm.turbines):
        types[1] = next(e.turbine for e in load_catalog() if e.id == WRF_BUILT_IN_TYPE_1)
    return types


def rotor_area(turbine: TurbineType) -> float:
    """Swept area of the rotor, m2."""
    return math.pi / 4 * turbine.rotor_diameter_m**2


def specific_power(turbine: TurbineType) -> float:
    """Rated power per swept area, W m-2."""
    return turbine.rated_power_mw * 1e6 / rotor_area(turbine)


def power_coefficients(turbine: TurbineType, density: float = AIR_DENSITY) -> np.ndarray:
    """Cp at each point of the curve, from P = 0.5 rho A U^3 Cp (zero where the speed is
    zero)."""
    speeds = np.array([p.wind_speed for p in turbine.curve], dtype=float)
    powers = np.array([p.power_kw for p in turbine.curve], dtype=float) * 1000
    swept = 0.5 * density * rotor_area(turbine) * speeds**3
    result: np.ndarray = np.divide(powers, swept, out=np.zeros_like(powers), where=swept > 0)
    return result
