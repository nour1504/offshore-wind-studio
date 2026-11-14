"""Turbine power from the hub-height wind speed, as WRF's wind farm schemes compute it.

Fitch and MAV (WRF 4.8 phys/module_wind_fitch.F and module_wind_mav.F, dragcof) turn
wind-turbine-N.tbl into Cp_k = P_k / (0.5 rho A U_k^3) with a fixed rho = 1.23 kg m-3, interpolate
Cp linearly in wind speed and return P = 0.5 rho A U^3 Cp(U): not a linear interpolation of the
power column, and independent of the real air density. Outside the table the power is zero (Fitch: U
<= first or >= last speed; MAV: U < first or > last).
"""

from typing import Literal

import numpy as np

from owstudio.core.case.model import TurbineType
from owstudio.core.windfarm.catalog import power_coefficients, rotor_area

# Hard-coded in module_wind_fitch.F (power1 = 0.5*1.23*...) and module_wind_mav.F
WRF_AIR_DENSITY = 1.23

Scheme = Literal["fitch", "mav"]


def wrf_power_w(speed: np.ndarray, turbine: TurbineType, scheme: Scheme = "fitch") -> np.ndarray:
    """Electrical power (W) at hub-height wind speeds (m s-1) with WRF's formula; NaN stays NaN."""
    u = np.asarray(speed, dtype=float)
    speeds = np.array([p.wind_speed for p in turbine.curve], dtype=float)
    cp = np.interp(u, speeds, power_coefficients(turbine, WRF_AIR_DENSITY))
    power = 0.5 * WRF_AIR_DENSITY * rotor_area(turbine) * u**3 * cp
    if scheme == "fitch":
        outside = (u <= speeds[0]) | (u >= speeds[-1])
    else:
        outside = (u < speeds[0]) | (u > speeds[-1])
    return np.where(np.isnan(u), np.nan, np.where(outside, 0.0, power))
