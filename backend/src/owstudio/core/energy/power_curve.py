"""A turbine's power curve rebuilt from a run, by the method of bins of IEC 61400-12-1: the
power of WRF at each output time, against the hub-height wind at the same time, sorted in wind
speed bins 0.5 m/s wide centred on multiples of 0.5 m/s. In each bin i:

    U_i = mean speed,  P_i = mean power,  Cp_i = P_i / (½ ρ A U_i³)

with ρ = 1.23 kg/m³, the density WRF's schemes use, and A the rotor area. The table of the
turbine (manufacturer curve) is given beside it with the same Cp formula.
"""

import numpy as np
import pandas as pd

from owstudio.core.case.model import TurbineType
from owstudio.core.energy.curves import WRF_AIR_DENSITY, power_coefficients, rotor_area

BIN_WIDTH = 0.5


def binned_curve(speed: pd.Series, power_w: pd.Series, turbine: TurbineType) -> dict[str, object]:
    """The pairs (speed, power), the curve per bin and the table of the turbine, in m/s and MW."""
    pairs = pd.concat([speed.rename("speed"), power_w.rename("power")], axis=1, join="inner")
    pairs = pairs[np.isfinite(pairs["speed"]) & np.isfinite(pairs["power"])]
    swept = 0.5 * WRF_AIR_DENSITY * rotor_area(turbine)
    codes = np.floor(pairs["speed"].to_numpy() / BIN_WIDTH + 0.5).astype(int)
    bins = []
    for code in sorted(set(codes.tolist())):
        inside = pairs[codes == code]
        u, p = float(inside["speed"].mean()), float(inside["power"].mean())
        bins.append({
            "centre_ms": code * BIN_WIDTH,
            "speed_ms": u,
            "power_mw": p / 1e6,
            "cp": p / (swept * u**3) if u > 0 else None,
            "count": len(inside),
        })  # fmt: skip
    speeds = [p.wind_speed for p in turbine.curve]
    table = [
        {"speed_ms": u, "power_mw": p.power_kw / 1000, "cp": float(cp) if u > 0 else None}
        for u, p, cp in zip(speeds, turbine.curve, power_coefficients(turbine), strict=True)
    ]
    return {
        "points": [
            {"time": t.isoformat(), "speed_ms": float(u), "power_mw": float(p) / 1e6}
            for t, u, p in zip(pairs.index, pairs["speed"], pairs["power"], strict=True)
        ],
        "bins": bins,
        "table": table,
        "rated_mw": turbine.rated_power_mw,
        "rotor_diameter_m": turbine.rotor_diameter_m,
        "hub_height_m": turbine.hub_height_m,
        "air_density": WRF_AIR_DENSITY,
        "bin_width_ms": BIN_WIDTH,
    }
