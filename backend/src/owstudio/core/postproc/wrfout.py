"""Diagnostics computed from WRF history (wrfout) files."""

import numpy as np
import pandas as pd
import xarray as xr

GRAVITY = 9.81  # m s-2, value used by WRF


def times(ds: xr.Dataset) -> pd.DatetimeIndex:
    """Valid times of a wrfout dataset, decoded from the ``Times`` character variable."""
    return pd.to_datetime(ds["Times"].values.astype(str), format="%Y-%m-%d_%H:%M:%S")


def destagger(da: xr.DataArray, dim: str, new_dim: str) -> xr.DataArray:
    """Average a staggered field onto mass points along ``dim``, renamed to ``new_dim``."""
    lower = da.isel({dim: slice(None, -1)}).rename({dim: new_dim})
    upper = da.isel({dim: slice(1, None)}).rename({dim: new_dim})
    return 0.5 * (lower + upper)


def height_above_ground(ds: xr.Dataset) -> xr.DataArray:
    """Height of the mass levels above the terrain, in metres."""
    z_stag = (ds["PH"] + ds["PHB"]) / GRAVITY
    return destagger(z_stag, "bottom_top_stag", "bottom_top") - ds["HGT"]


def interp_to_height(field: xr.DataArray, z: xr.DataArray, height_m: float) -> xr.DataArray:
    """Linearly interpolate a mass-level field to a constant height above ground.

    Heights below the lowest model level are extrapolated from the two lowest levels.
    """
    f = field.transpose(..., "bottom_top")
    zz = z.transpose(..., "bottom_top").values
    fv = f.values
    k = np.clip((zz < height_m).sum(axis=-1) - 1, 0, zz.shape[-1] - 2)[..., np.newaxis]
    z0 = np.take_along_axis(zz, k, axis=-1)[..., 0]
    z1 = np.take_along_axis(zz, k + 1, axis=-1)[..., 0]
    f0 = np.take_along_axis(fv, k, axis=-1)[..., 0]
    f1 = np.take_along_axis(fv, k + 1, axis=-1)[..., 0]
    weight = (height_m - z0) / (z1 - z0)
    return xr.DataArray(f0 + weight * (f1 - f0), dims=f.dims[:-1], attrs={"height_m": height_m})


def wind_speed_at_height(ds: xr.Dataset, height_m: float) -> xr.DataArray:
    """Horizontal wind speed at a constant height above ground, in m s-1."""
    u = destagger(ds["U"], "west_east_stag", "west_east")
    v = destagger(ds["V"], "south_north_stag", "south_north")
    speed = (u**2 + v**2) ** 0.5
    result = interp_to_height(speed, height_above_ground(ds), height_m)
    result.attrs["units"] = "m s-1"
    return result


def farm_power(ds: xr.Dataset) -> xr.DataArray:
    """Total power of all turbines in the domain from the Fitch scheme output, in MW."""
    total = ds["POWER"].sum(dim=("south_north", "west_east")) / 1e6
    total.attrs["units"] = "MW"
    return total
