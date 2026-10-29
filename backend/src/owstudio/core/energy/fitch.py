"""Power of each turbine as the Fitch scheme computes it (WRF 4.8 phys/module_wind_fitch.F),
reconstructed from the history files, to split WRF's per-cell POWER among the turbines of a cell.

For each turbine, the scheme takes the wind speed of its grid cell interpolated linearly in
height to the hub (between the mass levels around it), and, with windfarm_induction = 1, divides
it twice by (1 - a)^n, n being the number of turbines in the cell:

    a1 = 0.25 · A / (D · dx · m),   a2 = ½ (1 − √(1 − Ct(U1))) · A / (D · dx · m)

with A the rotor area, D the diameter, dx the grid spacing and m = min(|1/cos θ|, |1/sin θ|),
θ = atan(v̄/ū) from the grid-relative wind averaged over the two levels around the hub. The power
is then ½ ρ A U³ Cp(U) with ρ = 1.23 kg/m³ and Cp interpolated in the turbine table.
Ct is the standing thrust coefficient below the first table speed and the last table value above
the last speed, clamped to [0.0001, 0.9999] with the induction correction.
"""

import math

import numpy as np

from owstudio.core.case.model import TurbineType
from owstudio.core.energy.curves import wrf_power_w
from owstudio.core.extract.history import HistoryFiles
from owstudio.core.extract.quantities import G


def thrust_coefficient(speed: np.ndarray, turbine: TurbineType, induction: bool) -> np.ndarray:
    speeds = np.array([p.wind_speed for p in turbine.curve], dtype=float)
    cts = np.array([p.thrust_coefficient for p in turbine.curve], dtype=float)
    ct = np.interp(speed, speeds, cts)
    ct = np.where(speed <= speeds[0], turbine.standing_thrust_coefficient, ct)
    ct = np.where(speed >= speeds[-1], cts[-1], ct)
    result: np.ndarray = np.clip(ct, 1e-4, 0.9999) if induction else ct
    return result


def cell_profiles(
    files: HistoryFiles, cells: list[tuple[int, int]]
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Mass-level heights above ground and grid-relative u, v of the given (j, i) cells:
    (time, level, cell), each variable read once for all of them."""
    z_stag = (files.cells("PH", cells) + files.cells("PHB", cells)) / G
    z = 0.5 * (z_stag[:, :-1] + z_stag[:, 1:]) - files.cells("HGT", cells)[:, None]
    return z, files.cells("U", cells), files.cells("V", cells)


def turbine_power(
    z: np.ndarray,
    u: np.ndarray,
    v: np.ndarray,
    turbine: TurbineType,
    n_in_cell: int,
    dx: float,
    induction: bool,
) -> np.ndarray:
    """Power (W) of one turbine of the cell at every time, as the Fitch scheme computes it."""
    hub = turbine.hub_height_m
    speed = np.hypot(u, v)
    k = (z <= hub).sum(axis=1) - 1  # kbot: last level at or below the hub
    k = np.clip(k, 0, z.shape[1] - 2)[:, None]
    z1, z2 = np.take_along_axis(z, k, 1)[:, 0], np.take_along_axis(z, k + 1, 1)[:, 0]
    s1, s2 = np.take_along_axis(speed, k, 1)[:, 0], np.take_along_axis(speed, k + 1, 1)[:, 0]
    below = hub < z[:, 0]
    # Below the lowest level the scheme scales the lowest speed linearly from the ground
    hub_speed = np.where(
        below, speed[:, 0] * hub / z[:, 0], s1 + (s2 - s1) / (z2 - z1) * (hub - z1)
    )
    if not induction:
        return wrf_power_w(hub_speed, turbine, "fitch")
    u_mean = 0.5 * (np.take_along_axis(u, k, 1)[:, 0] + np.take_along_axis(u, k + 1, 1)[:, 0])
    v_mean = 0.5 * (np.take_along_axis(v, k, 1)[:, 0] + np.take_along_axis(v, k + 1, 1)[:, 0])
    with np.errstate(divide="ignore", invalid="ignore"):
        theta = np.arctan(v_mean / u_mean)
        factor = np.minimum(np.abs(1 / np.cos(theta)), np.abs(1 / np.sin(theta)))
    factor = np.where(np.isfinite(factor), factor, 1.0)
    area = math.pi / 4 * turbine.rotor_diameter_m**2
    scale = area / (turbine.rotor_diameter_m * dx * factor)
    first = hub_speed / (1 - 0.25 * scale) ** n_in_cell
    a2 = 0.5 * (1 - np.sqrt(1 - thrust_coefficient(first, turbine, induction=True))) * scale
    return wrf_power_w(hub_speed / (1 - a2) ** n_in_cell, turbine, "fitch")
