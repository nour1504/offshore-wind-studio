"""WPS intermediate format, version 5, as written by ungrib and read by metgrid.

Each field is five Fortran unformatted sequential records: the version (5); the header (date,
forecast hour, source, field name, units, description, level, nx, ny, projection); the grid
(here cylindrical equidistant, projection 0: start location, start latitude and longitude,
latitude and longitude steps, earth radius in km); whether winds are grid-relative; and the
nx × ny slab of 32-bit reals, x varying fastest. WPS is built with gfortran's
-fconvert=big-endian -frecord-marker=4 (arch/configure.defaults), so the records are big-endian
with 4-byte length markers before and after each.
References: WPS ungrib/src/output.F and metgrid/src/read_met_module.F; WRF User's Guide,
"Writing Meteorological Data to the Intermediate Format".
"""

import struct
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

import numpy as np

from owstudio.core.i18n import tr

VERSION = 5
# Missing values in slabs, as ungrib writes them for points outside a bitmap (SST over land)
MISSING = -1.0e30
# Surface fields and sea-level pressure are stored at these pseudo-levels
SURFACE_LEVEL = 200100.0
SEA_LEVEL = 201300.0
# Earth radius of ECMWF GRIB1 data, as ungrib writes it for them (km)
ECMWF_EARTH_RADIUS_KM = 6367.47


@dataclass(frozen=True)
class LatLonGrid:
    """Regular latitude-longitude grid; the slab's first row is ``start_lat``."""

    start_lat: float
    start_lon: float
    dlat: float
    dlon: float
    earth_radius_km: float = ECMWF_EARTH_RADIUS_KM
    start_location: str = "SWCORNER"


@dataclass
class Slab:
    date: datetime
    field: str
    units: str
    description: str
    level: float
    grid: LatLonGrid
    # (ny, nx): rows from start_lat, columns from start_lon
    data: np.ndarray
    source: str = "ECMWF"
    forecast_hours: float = 0.0
    grid_relative_winds: bool = False


def _text(value: str, size: int) -> bytes:
    return value.encode("ascii", errors="replace")[:size].ljust(size, b" ")


def _record(handle: BinaryIO, payload: bytes) -> None:
    marker = struct.pack(">i", len(payload))
    handle.write(marker + payload + marker)


def wps_date(date: datetime) -> str:
    return date.strftime("%Y-%m-%d_%H:%M:%S")


def file_date(date: datetime, interval_s: int) -> str:
    """Date in intermediate file names: to the hour, minute or second as ungrib does (datint.F,
    output.F: 13, 16 or 19 characters depending on the interval)."""
    text = wps_date(date)
    if interval_s % 3600 == 0:
        return text[:13]
    if interval_s % 60 == 0:
        return text[:16]
    return text


def write(path: Path, slabs: Iterable[Slab]) -> int:
    """Writes the fields to one intermediate file; returns the number of fields."""
    count = 0
    with path.open("wb") as handle:
        for slab in slabs:
            ny, nx = slab.data.shape
            grid = slab.grid
            _record(handle, struct.pack(">i", VERSION))
            header = (
                _text(wps_date(slab.date), 24)
                + struct.pack(">f", slab.forecast_hours)
                + _text(slab.source, 32)
                + _text(slab.field, 9)
                + _text(slab.units, 25)
                + _text(slab.description, 46)
                + struct.pack(">f", slab.level)
                + struct.pack(">iii", nx, ny, 0)
            )
            _record(handle, header)
            projection = _text(grid.start_location, 8) + struct.pack(
                ">fffff", grid.start_lat, grid.start_lon, grid.dlat, grid.dlon, grid.earth_radius_km
            )
            _record(handle, projection)
            _record(handle, struct.pack(">i", 1 if slab.grid_relative_winds else 0))
            values = np.where(np.isfinite(slab.data), slab.data, MISSING)
            _record(handle, np.ascontiguousarray(values, dtype=">f4").tobytes())
            count += 1
    return count


class FormatError(ValueError):
    """Not an intermediate file of version 5 on a latitude-longitude grid."""


def _read_record(handle: BinaryIO) -> bytes | None:
    head = handle.read(4)
    if not head:
        return None
    (size,) = struct.unpack(">i", head)
    payload = handle.read(size)
    tail = handle.read(4)
    if len(payload) != size or tail != head:
        raise FormatError(
            tr(
                "Truncated or corrupted record (or not big-endian)",
                "Enregistrement tronqué ou abîmé (ou pas en big-endian)",
            )
        )
    return payload


def read(path: Path) -> Iterator[Slab]:
    """The fields of an intermediate file written on a latitude-longitude grid."""
    with path.open("rb") as handle:
        while True:
            version = _read_record(handle)
            if version is None:
                return
            if struct.unpack(">i", version)[0] != VERSION:
                raise FormatError(
                    tr(
                        f"Version {struct.unpack('>i', version)[0]} instead of 5",
                        f"Version {struct.unpack('>i', version)[0]} au lieu de 5",
                    )
                )
            header = _read_record(handle)
            assert header is not None
            date = datetime.strptime(header[:19].decode("ascii"), "%Y-%m-%d_%H:%M:%S")
            (forecast,) = struct.unpack(">f", header[24:28])
            source = header[28:60].decode("ascii").rstrip()
            field = header[60:69].decode("ascii").rstrip()
            units = header[69:94].decode("ascii").rstrip()
            description = header[94:140].decode("ascii").rstrip()
            (level,) = struct.unpack(">f", header[140:144])
            nx, ny, projection = struct.unpack(">iii", header[144:156])
            if projection != 0:
                raise FormatError(
                    tr(
                        f"Projection {projection} is not read here (latitude-longitude only)",
                        f"La projection {projection} n'est pas lue ici (latitude-longitude seulement)",
                    )
                )
            grid_record = _read_record(handle)
            assert grid_record is not None
            start = grid_record[:8].decode("ascii")
            lat, lon, dlat, dlon, radius = struct.unpack(">fffff", grid_record[8:28])
            winds = _read_record(handle)
            assert winds is not None
            values = _read_record(handle)
            assert values is not None
            data = np.frombuffer(values, dtype=">f4").astype(np.float32).reshape(ny, nx)
            yield Slab(
                date, field, units, description, level,
                LatLonGrid(lat, lon, dlat, dlon, radius, start), data, source, forecast,
                struct.unpack(">i", winds)[0] != 0,
            )  # fmt: skip
