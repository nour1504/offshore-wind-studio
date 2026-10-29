"""Turbine power from the hub-height wind speed, computed the way WRF's wind farm schemes do.

Both schemes of WRF 4.8 (phys/module_wind_fitch.F, subroutine dragcof, and phys/module_wind_mav.F,
subroutine dragcof) convert the table of wind-turbine-N.tbl into power coefficients
Cp_k = P_k / (0.5 rho A U_k^3) with a fixed air density rho = 1.23 kg m-3, interpolate Cp linearly
in wind speed, and return P = 0.5 rho A U^3 Cp(U). The power is therefore not a linear
interpolation of the table's power column between its points, and does not depend on the actual
air density. Outside the table the power is zero: Fitch for U <= first speed or U >= last speed,
MAV for U < first speed or U > last speed.
"""

import math
from typing import Literal

import numpy as np

from owstudio.core.case.model import Case, TurbineType
from owstudio.core.postproc.results import turbine_types as _turbine_types

# Hard-coded in module_wind_fitch.F (power1 = 0.5*1.23*...) and module_wind_mav.F
WRF_AIR_DENSITY = 1.23

Scheme = Literal["fitch", "mav"]


def turbine_types(case: Case) -> dict[int, TurbineType]:
    """Turbine tables in effect: the case's own, plus WRF's shipped table for type 1."""
    return _turbine_types(case)


def rotor_area(turbine: TurbineType) -> float:
    return math.pi / 4 * turbine.rotor_diameter_m**2


def power_coefficients(turbine: TurbineType) -> np.ndarray:
    """Cp at the table's speeds as WRF computes it (zero where the speed is zero)."""
    speeds = np.array([p.wind_speed for p in turbine.curve], dtype=float)
    powers = np.array([p.power_kw for p in turbine.curve], dtype=float) * 1000
    swept = 0.5 * WRF_AIR_DENSITY * rotor_area(turbine) * speeds**3
    result: np.ndarray = np.divide(powers, swept, out=np.zeros_like(powers), where=swept > 0)
    return result


def wrf_power_w(speed: np.ndarray, turbine: TurbineType, scheme: Scheme = "fitch") -> np.ndarray:
    """Electrical power (W) at hub-height wind speeds (m s-1) with WRF's formula; NaN stays NaN."""
    u = np.asarray(speed, dtype=float)
    speeds = np.array([p.wind_speed for p in turbine.curve], dtype=float)
    cp = np.interp(u, speeds, power_coefficients(turbine))
    power = 0.5 * WRF_AIR_DENSITY * rotor_area(turbine) * u**3 * cp
    if scheme == "fitch":
        outside = (u <= speeds[0]) | (u >= speeds[-1])
    else:
        outside = (u < speeds[0]) | (u > speeds[-1])
    return np.where(np.isnan(u), np.nan, np.where(outside, 0.0, power))
