"""Synthetic NetCDF files in the layouts of the Copernicus Climate Data Store (ERA5, current and
legacy) and of OSTIA, with values that are known functions of time, level and position."""

from datetime import datetime
from pathlib import Path

import netCDF4
import numpy as np

EPOCH = datetime(1970, 1, 1)
LEGACY_EPOCH = datetime(1900, 1, 1)
LEVELS_HPA = (1000, 925, 850, 700, 500, 300, 200, 100, 50, 20, 10, 5, 1)
SURFACE = ("u10", "v10", "t2m", "d2m", "sp", "msl", "skt", "sst", "lsm", "z", "siconc", "sd",
           "stl1", "stl2", "stl3", "stl4", "swvl1", "swvl2", "swvl3", "swvl4")  # fmt: skip
UNITS = {
    "z": "m**2 s**-2", "t": "K", "u": "m s**-1", "v": "m s**-1", "r": "%", "q": "kg kg**-1",
    "u10": "m s**-1", "v10": "m s**-1", "t2m": "K", "d2m": "K", "sp": "Pa", "msl": "Pa",
    "skt": "K", "sst": "K", "lsm": "(0 - 1)", "siconc": "(0 - 1)", "sd": "m of water equivalent",
    "stl1": "K", "stl2": "K", "stl3": "K", "stl4": "K",
    "swvl1": "m**3 m**-3", "swvl2": "m**3 m**-3", "swvl3": "m**3 m**-3", "swvl4": "m**3 m**-3",
}  # fmt: skip


def hours(time: datetime) -> float:
    return (time - EPOCH).total_seconds() / 3600


def value(
    name: str, time: datetime, lat: np.ndarray, lon: np.ndarray, level_hpa: float = 0.0
) -> np.ndarray:
    """The value written for a variable: linear in time, latitude and longitude."""
    lat2, lon2 = np.meshgrid(lat, lon, indexing="ij")
    base = {"z": 9.81 * (10_000 - 8 * level_hpa), "t": 200 + level_hpa / 10, "u": 5.0, "v": -3.0,
            "r": 70.0, "q": 0.005, "u10": 4.0, "v10": 2.0, "t2m": 285.0, "d2m": 280.0, "sp": 101000.0,
            "msl": 101300.0, "skt": 286.0, "sst": 288.0, "lsm": 0.0, "z_surface": 9.81 * 10, "siconc": 0.0,
            "sd": 0.0, "swvl1": 0.3}.get(name, 280.0)  # fmt: skip
    data = base + 0.1 * lat2 + 0.01 * lon2 + 0.5 * (hours(time) % 240)
    if name in ("lsm", "siconc"):
        data = (lon2 > 8.0).astype(float) if name == "lsm" else np.zeros_like(lat2)
    if name == "sst":
        data = np.where(lon2 > 8.0, np.nan, data)
    return np.asarray(data, dtype=float)


def _axis(
    dataset: netCDF4.Dataset, name: str, values: np.ndarray, units: str, dtype: str = "f4"
) -> None:
    dataset.createDimension(name, len(values))
    axis = dataset.createVariable(name, dtype, (name,))
    axis.units = units
    axis[:] = values


def era5(
    path: Path, times: list[datetime], lat: np.ndarray, lon: np.ndarray, pressure: bool
) -> Path:
    """Current CDS layout: valid_time in seconds since 1970, pressure_level in hPa, float32."""
    with netCDF4.Dataset(path, "w", format="NETCDF4") as dataset:
        dataset.institution = "European Centre for Medium-Range Weather Forecasts"
        dataset.GRIB_centre = "ecmf"
        _axis(dataset, "valid_time", np.array([hours(t) * 3600 for t in times], dtype="i8"),
              "seconds since 1970-01-01", "i8")  # fmt: skip
        if pressure:
            _axis(dataset, "pressure_level", np.array(LEVELS_HPA, dtype=float), "hPa", "f8")
        _axis(dataset, "latitude", lat, "degrees_north", "f8")
        _axis(dataset, "longitude", lon, "degrees_east", "f8")
        names = ("z", "t", "u", "v", "r") if pressure else SURFACE
        for name in names:
            dims = (
                ("valid_time", "pressure_level", "latitude", "longitude")
                if pressure
                else ("valid_time", "latitude", "longitude")
            )
            variable = dataset.createVariable(name, "f4", dims, fill_value=np.float32(np.nan))
            variable.units = UNITS[name]
            for k, time in enumerate(times):
                if pressure:
                    for j, level in enumerate(LEVELS_HPA):
                        variable[k, j, :, :] = value(name, time, lat, lon, level)
                else:
                    variable[k, :, :] = value("z_surface" if name == "z" else name, time, lat, lon)
    return path


def era5_legacy(path: Path, times: list[datetime], lat: np.ndarray, lon: np.ndarray) -> Path:
    """Legacy CDS layout: time in hours since 1900, level in millibars, packed int16, and an
    expver dimension mixing ERA5 (first times) and ERA5T (last time)."""
    with netCDF4.Dataset(path, "w", format="NETCDF3_64BIT_OFFSET") as dataset:
        dataset.history = "2025-10-14 CDS: data from ecmwf MARS"
        _axis(dataset, "longitude", lon, "degrees_east")
        _axis(dataset, "latitude", lat, "degrees_north")
        _axis(dataset, "expver", np.array([1, 5], dtype="i4"), "1", "i4")
        _axis(
            dataset, "level", np.array([1000, 850, 500, 100, 10, 1], dtype="i4"), "millibars", "i4"
        )
        _axis(dataset, "time", np.array([(t - LEGACY_EPOCH).total_seconds() / 3600 for t in times], dtype="i4"),
              "hours since 1900-01-01 00:00:00.0", "i4")  # fmt: skip
        variable = dataset.createVariable(
            "t", "i2", ("time", "expver", "level", "latitude", "longitude"), fill_value=-32767
        )
        variable.scale_factor, variable.add_offset = 0.002, 250.0
        variable.units = "K"
        for k, time in enumerate(times):
            for j, level in enumerate((1000, 850, 500, 100, 10, 1)):
                data = value("t", time, lat, lon, level)
                packed = np.round((data - 250.0) / 0.002).astype("i2")
                ours = 1 if k == len(times) - 1 else 0
                variable.set_auto_maskandscale(False)
                variable[k, ours, j, :, :] = packed
                variable[k, 1 - ours, j, :, :] = -32767
                variable.set_auto_maskandscale(True)
    return path


def ostia(path: Path, times: list[datetime], lat: np.ndarray, lon: np.ndarray) -> Path:
    """OSTIA-like SST analysis: time in seconds since 1981, ascending latitudes, packed shorts,
    missing over land."""
    with netCDF4.Dataset(path, "w", format="NETCDF4") as dataset:
        dataset.institution = "UKMO"
        _axis(dataset, "time", np.array([(t - datetime(1981, 1, 1)).total_seconds() for t in times], dtype="i4"),
              "seconds since 1981-01-01 00:00:00", "i4")  # fmt: skip
        _axis(dataset, "lat", lat, "degrees_north")
        _axis(dataset, "lon", lon, "degrees_east")
        sst = dataset.createVariable(
            "analysed_sst", "i2", ("time", "lat", "lon"), fill_value=-32768
        )
        sst.scale_factor, sst.add_offset = 0.01, 273.15
        sst.units = "kelvin"
        sst.standard_name = "sea_surface_foundation_temperature"
        for k, time in enumerate(times):
            data = value("sst", time, lat, lon)
            sst[k, :, :] = np.ma.array(np.nan_to_num(data, nan=273.15), mask=np.isnan(data))
        mask = dataset.createVariable("mask", "i1", ("time", "lat", "lon"))
        mask[:] = 1
    return path
