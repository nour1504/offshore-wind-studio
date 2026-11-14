"""Minimal GRIB1 and GRIB2 messages for tests: valid headers on a regular lat-lon grid and a
constant field (no packed data). Enough for inventories and Vtable matching, not for ungrib."""

import struct
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class LatLon:
    """Regular grid from (lat1, lon1) to (lat2, lon2), eastwards and north to south. The default
    covers the outer domain of the Horns Rev example."""

    lat1: float = 65.0
    lon1: float = -5.0
    lat2: float = 45.0
    lon2: float = 20.0
    step: float = 0.25

    @property
    def ni(self) -> int:
        return round(((self.lon2 - self.lon1) % 360.0) / self.step) + 1

    @property
    def nj(self) -> int:
        return round(abs(self.lat1 - self.lat2) / self.step) + 1


DEFAULT_GRID = LatLon()


def _signed(value: int, size: int) -> bytes:
    """GRIB sign-and-magnitude integer."""
    magnitude = abs(value)
    if value < 0:
        magnitude |= 1 << (8 * size - 1)
    return magnitude.to_bytes(size, "big")


def _u(value: int, size: int) -> bytes:
    return value.to_bytes(size, "big")


def grib2(
    when: datetime,
    discipline: int,
    category: int,
    parameter: int,
    level_type: int,
    level: float = 0.0,
    level_scale: int = 0,
    grid: LatLon = DEFAULT_GRID,
    centre: int = 98,
    forecast_hours: int = 0,
    template: int = 0,
    level2: tuple[int, float, int] | None = None,
    interval_end: datetime | None = None,
) -> bytes:
    section1 = (
        _u(21, 4) + b"\x01" + _u(centre, 2) + _u(0, 2) + b"\x02\x00\x01"
        + _u(when.year, 2) + bytes([when.month, when.day, when.hour, when.minute, when.second])
        + b"\x00\x01"
    )  # fmt: skip
    micro = 1_000_000
    section3 = (
        _u(72, 4) + b"\x03\x00" + _u(grid.ni * grid.nj, 4) + b"\x00\x00" + _u(0, 2)
        + b"\x06" + b"\x00" * 15
        + _u(grid.ni, 4) + _u(grid.nj, 4) + _u(0, 4) + _u(0xFFFFFFFF, 4)
        + _signed(round(grid.lat1 * micro), 4) + _signed(round(grid.lon1 * micro), 4) + b"\x30"
        + _signed(round(grid.lat2 * micro), 4) + _signed(round(grid.lon2 * micro), 4)
        + _u(round(grid.step * micro), 4) + _u(round(grid.step * micro), 4) + b"\x00"
    )  # fmt: skip
    assert len(section3) == 72
    second_type, second_value, second_scale = level2 if level2 else (255, 0, 255)
    product = (
        _u(0, 2) + _u(template, 2) + bytes([category, parameter, 2, 0, 0]) + _u(0, 2) + b"\x00"
        + b"\x01" + _u(forecast_hours, 4)
        + bytes([level_type]) + _signed(level_scale, 1) + _signed(round(level), 4)
        + bytes([second_type]) + (b"\xff" if second_scale == 255 else _signed(second_scale, 1))
        + (b"\xff" * 4 if second_type == 255 else _signed(round(second_value), 4))
    )  # fmt: skip
    if template == 8:
        # Statistically processed over forecast_hours, ending at interval_end
        end = interval_end or when
        product += (
            _u(end.year, 2) + bytes([end.month, end.day, end.hour, end.minute, end.second])
            + b"\x01" + _u(0, 4) + bytes([0, 2, 1]) + _u(forecast_hours, 4) + b"\xff" + _u(0, 4)
        )  # fmt: skip
    section4 = _u(5 + len(product), 4) + b"\x04" + product
    section5 = (
        _u(21, 4) + b"\x05" + _u(grid.ni * grid.nj, 4) + _u(0, 2) + struct.pack(">f", 280.0)
        + _u(0, 2) + _u(0, 2) + b"\x00\x00"
    )  # fmt: skip
    section6 = _u(6, 4) + b"\x06\xff"
    section7 = _u(5, 4) + b"\x07"
    body = section1 + section3 + section4 + section5 + section6 + section7 + b"7777"
    return b"GRIB\x00\x00" + bytes([discipline, 2]) + _u(16 + len(body), 8) + body


def grib1(
    when: datetime,
    parameter: int,
    level_type: int,
    level: int | tuple[int, int] = 0,
    grid: LatLon = DEFAULT_GRID,
    centre: int = 98,
    table: int = 128,
    p1: int = 0,
    unit: int = 1,
    indicator: int = 0,
) -> bytes:
    century = (when.year - 1) // 100 + 1
    year_of_century = when.year - (century - 1) * 100
    level_bytes = bytes(level) if isinstance(level, tuple) else _u(level, 2)
    pds = (
        _u(28, 3) + bytes([table, centre, 0, 255, 0x80, parameter, level_type]) + level_bytes
        + bytes([year_of_century, when.month, when.day, when.hour, when.minute, unit, p1, 0, indicator])
        + _u(0, 2) + b"\x00" + bytes([century, 0]) + _u(0, 2)
    )  # fmt: skip
    milli = 1000
    gds = (
        _u(32, 3) + b"\x00\xff\x00" + _u(grid.ni, 2) + _u(grid.nj, 2)
        + _signed(round(grid.lat1 * milli), 3) + _signed(round(grid.lon1 * milli), 3) + b"\x80"
        + _signed(round(grid.lat2 * milli), 3) + _signed(round(grid.lon2 * milli), 3)
        + _u(round(grid.step * milli), 2) + _u(round(grid.step * milli), 2) + b"\x00" + b"\x00" * 4
    )  # fmt: skip
    assert len(pds) == 28 and len(gds) == 32
    bds = _u(12, 3) + b"\x00" + _u(0, 2) + b"\x42\x11\x80\x00" + b"\x00\x00"
    body = pds + gds + bds + b"7777"
    return b"GRIB" + _u(8 + len(body), 3) + b"\x01" + body


# ERA5 on pressure levels and single levels, GRIB1 (ECMWF table 128), as read by Vtable.ECMWF
ERA5_PRESSURE = (129, 130, 131, 132, 157)
ERA5_SURFACE = (165, 166, 167, 168, 172, 129, 134, 151, 235, 34, 31)
ERA5_SOIL = ((139, (0, 7)), (170, (7, 28)), (183, (28, 100)), (236, (100, 255)),
             (39, (0, 7)), (40, (7, 28)), (41, (28, 100)), (42, (100, 255)))  # fmt: skip
ERA5_LEVELS_HPA = (1000, 925, 850, 700, 500, 300, 200, 100, 50, 20, 10, 5, 1)


def era5_folder(folder: Path, times: list[datetime], grid: LatLon = DEFAULT_GRID) -> Path:
    """One pressure-level file and one single-level file per day, like CDS downloads."""
    folder.mkdir(parents=True, exist_ok=True)
    by_day: dict[str, list[datetime]] = {}
    for time in times:
        by_day.setdefault(time.strftime("%Y%m%d"), []).append(time)
    for day, day_times in by_day.items():
        pressure = b"".join(
            grib1(t, p, 100, level, grid)
            for t in day_times
            for p in ERA5_PRESSURE
            for level in ERA5_LEVELS_HPA
        )
        surface = b"".join(grib1(t, p, 1, 0, grid) for t in day_times for p in ERA5_SURFACE)
        soil = b"".join(grib1(t, p, 112, layer, grid) for t in day_times for p, layer in ERA5_SOIL)
        (folder / f"era5-pl-{day}.grib").write_bytes(pressure)
        (folder / f"era5-sl-{day}.grib").write_bytes(surface + soil)
    return folder


# GRIB2 grids usually give longitudes from 0 to 360°: this one crosses the Greenwich meridian
SST_GRID = LatLon(lat1=65.0, lon1=355.0, lat2=45.0, lon2=20.0)


def sst_folder(
    folder: Path, times: list[datetime], grid: LatLon = SST_GRID, centre: int = 74
) -> Path:
    """One SST analysis per file in GRIB2, read by Vtable.SST (discipline 0, category 0,
    number 0, surface), named by day like OSTIA files."""
    folder.mkdir(parents=True, exist_ok=True)
    for time in times:
        message = grib2(time, 0, 0, 0, 1, grid=grid, centre=centre)
        (folder / f"sst-{time:%Y%m%d}.grb2").write_bytes(message)
    return folder
