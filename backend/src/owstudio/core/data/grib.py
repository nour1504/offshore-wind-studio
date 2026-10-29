"""Inventory of GRIB files (editions 1 and 2) from their message headers only.

Each message is located by its length and only its header sections are read (identification,
grid, product definition); data sections are skipped with a seek, so large files are inventoried
in seconds. A truncated or corrupted message is reported, not fatal. Valid times are computed as
WPS 4.7's ungrib computes them (rd_grib1.F, rd_grib2.F), so the checks before a run say what ungrib
will see. Signed GRIB values use a sign bit, not two's complement.
References: WMO Manual on Codes, FM 92 GRIB editions 1 and 2.
"""

from collections import OrderedDict
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import BinaryIO

# Originating centres seen in wind energy work (WMO common code table C-11)
CENTRES = {
    7: "NCEP",
    54: "Canadian Meteorological Centre",
    74: "UK Met Office",
    78: "DWD",
    85: "Météo-France",
    98: "ECMWF",
    34: "JMA",
}

# Smallest possible messages: indicator, mandatory sections, end marker
MIN_LENGTH = {1: 8 + 28 + 11 + 4, 2: 16 + 21 + 5 + 34 + 21 + 5 + 4}

# Level types whose GRIB1 level field is two one-octet values (top, bottom), as in ungrib's gribcode.F
GRIB1_LAYERS = {101, 104, 106, 108, 110, 112, 114, 116, 120, 121, 128, 141, 236}


@dataclass(frozen=True)
class Grid:
    # GRIB2 grid template number (GRIB1 grids are given their GRIB2 equivalent)
    template: int
    ni: int | None = None
    nj: int | None = None
    lat1: float | None = None
    lon1: float | None = None
    lat2: float | None = None
    lon2: float | None = None
    di: float | None = None
    dj: float | None = None
    scanning: int | None = None

    @property
    def kind(self) -> str:
        return {
            0: "lat-lon",
            1: "rotated lat-lon",
            10: "Mercator",
            20: "polar stereographic",
            30: "Lambert conformal",
            40: "Gaussian",
        }.get(self.template, f"grid template {self.template}")

    def bounds(self) -> tuple[float, float, float, float] | None:
        """(south, north, west, east) of a regular or Gaussian lat-lon grid; east may exceed 180
        (grids running eastwards from 0° to 359.75°)."""
        if self.template not in (0, 40):
            return None
        if self.lat1 is None or self.lat2 is None or self.lon1 is None or self.lon2 is None:
            return None
        south, north = sorted((self.lat1, self.lat2))
        west, east = self.lon1, self.lon2
        if self.scanning is not None and self.scanning & 0x80:
            west, east = east, west  # points scan westwards
        if east < west:
            east += 360.0
        return south, north, west, east

    def describe(self) -> str:
        size = f"{self.ni}×{self.nj}" if self.ni and self.nj else "?"
        step = f", {self.di:g}°" if self.template in (0, 40) and self.di else ""
        return f"{self.kind} {size}{step}"


@dataclass(frozen=True)
class Record:
    edition: int
    offset: int
    # GRIB2: discipline, category and number; GRIB1: table version and parameter, category None
    discipline: int
    category: int | None
    parameter: int
    level_type: int
    level1: float | None
    level2: float | None
    # Valid time as ungrib computes it
    valid: datetime
    grid: Grid
    centre: int = 0
    # Product template (GRIB2) or time range indicator (GRIB1)
    product: int = 0


@dataclass
class Inventory:
    path: Path
    records: list[Record] = field(default_factory=list)
    truncated: bool = False
    problems: list[str] = field(default_factory=list)

    def times(self) -> list[datetime]:
        return sorted({r.valid for r in self.records})

    def centres(self) -> list[str]:
        return sorted({CENTRES.get(r.centre, f"centre {r.centre}") for r in self.records})


def _u(data: bytes, start: int, size: int) -> int:
    return int.from_bytes(data[start : start + size], "big")


def _s(data: bytes, start: int, size: int) -> int:
    """Signed GRIB integer: the first bit is the sign, the others the magnitude."""
    value = _u(data, start, size)
    sign_bit = 1 << (8 * size - 1)
    return -(value & (sign_bit - 1)) if value & sign_bit else value


def _scaled(scale_octet: int, value_raw: int) -> float | None:
    """A GRIB2 scaled value (scale factor octet, 4-octet scaled value); None when missing."""
    if scale_octet == 0xFF or value_raw == 0xFFFFFFFF:
        return None
    scale = -(scale_octet & 0x7F) if scale_octet & 0x80 else scale_octet
    value = -(value_raw & 0x7FFFFFFF) if value_raw & 0x80000000 else value_raw
    return value * 10.0 ** (-scale)


def _date(year: int, month: int, day: int, hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, second)


def _grib2_grid(section: bytes) -> Grid:
    template = _u(section, 12, 2)
    if template in (0, 1, 40) and len(section) >= 72:
        basic, subdivisions = _u(section, 38, 4), _u(section, 42, 4)
        unit = 1e-6
        if basic not in (0, 0xFFFFFFFF) and subdivisions not in (0, 0xFFFFFFFF):
            unit = basic / subdivisions
        return Grid(
            template, ni=_u(section, 30, 4), nj=_u(section, 34, 4),
            lat1=_s(section, 46, 4) * unit, lon1=_s(section, 50, 4) * unit,
            lat2=_s(section, 55, 4) * unit, lon2=_s(section, 59, 4) * unit,
            di=_u(section, 63, 4) * unit, dj=None if template == 40 else _u(section, 67, 4) * unit,
            scanning=section[71],
        )  # fmt: skip
    if template in (10, 20, 30) and len(section) >= 46:
        return Grid(
            template, ni=_u(section, 30, 4), nj=_u(section, 34, 4),
            lat1=_s(section, 38, 4) * 1e-6, lon1=_s(section, 42, 4) * 1e-6,
        )  # fmt: skip
    return Grid(template)


def _grib2(handle: BinaryIO, offset: int, total: int, discipline: int, result: Inventory) -> None:
    """Sections 1 to 7 of one message, reading only sections 1, 3 and 4."""
    position = offset + 16
    end = offset + total - 4
    reference = datetime(1970, 1, 1)
    significance = 0
    centre = 0
    grid = Grid(-1)
    while position < end:
        handle.seek(position)
        head = handle.read(5)
        if len(head) < 5:
            result.truncated = True
            return
        length, number = _u(head, 0, 4), head[4]
        if length < 5 or position + length > end:
            result.problems.append(f"Corrupted section {number} in the message at byte {offset}")
            return
        if number in (1, 3, 4):
            section = head + handle.read(length - 5)
            if number == 1 and length >= 19:
                centre = _u(section, 5, 2)
                significance = section[11]
                reference = _date(_u(section, 12, 2), *section[14:19])
            elif number == 3:
                grid = _grib2_grid(section)
            elif number == 4 and length >= 34:
                result.records.append(
                    _grib2_product(
                        section, offset, discipline, reference, significance, grid, centre, result
                    )
                )
        position += length


def _grib2_product(
    section: bytes,
    offset: int,
    discipline: int,
    reference: datetime,
    significance: int,
    grid: Grid,
    centre: int,
    result: Inventory,
) -> Record:
    template = _u(section, 7, 2)
    category, parameter = section[9], section[10]
    unit, forecast = section[17], _u(section, 18, 4)
    level_type, level2_type = section[22], section[28]
    level1 = _scaled(section[23], _u(section, 24, 4)) if level_type != 255 else None
    level2 = _scaled(section[29], _u(section, 30, 4)) if level2_type != 255 else None
    # rd_grib2.F: template 4.8 gives the end of its interval; otherwise reference + forecast time
    # in minutes, hours or days; a reference time that is the verifying time has no offset
    if template == 8 and len(section) >= 41:
        valid = _date(_u(section, 34, 2), *section[36:41])
    else:
        hours = {0: 1 / 60, 1: 1.0, 2: 24.0}.get(unit)
        if hours is None:
            result.problems.append(
                f"Time unit {unit} (GRIB2 code table 4.4) is not supported by ungrib (message at byte {offset})"
            )
            hours = 1.0
        valid = reference + timedelta(hours=0.0 if significance == 2 else hours * forecast)
    return Record(
        2,
        offset,
        discipline,
        category,
        parameter,
        level_type,
        level1,
        level2,
        valid,
        grid,
        centre,
        template,
    )


def _grib1(handle: BinaryIO, offset: int, total: int, result: Inventory) -> None:
    handle.seek(offset + 8)
    head = handle.read(3)
    pds_length = _u(head, 0, 3)
    if pds_length < 28 or 8 + pds_length > total:
        result.problems.append(f"Corrupted product section in the message at byte {offset}")
        return
    pds = head + handle.read(pds_length - 3)
    # rd_grib1.F: year from the century and the year of century
    century, year_of_century = pds[24], pds[12]
    year = century * 100 if year_of_century == 0 else (century - 1) * 100 + year_of_century
    reference = _date(year, pds[13], pds[14], pds[15], pds[16])
    unit, p1, p2, indicator = pds[17], pds[18], pds[19], pds[20]
    if indicator == 10:
        p1 = (p1 << 8) | p2
    forecast = (p1 + p2) / 2 if indicator == 3 else p2 if indicator in (4, 5, 7) else p1
    # ungrib reads every unit other than seconds (254) and minutes (0) as hours
    hours = forecast / 3600 if unit == 254 else forecast / 60 if unit == 0 else float(forecast)
    if unit not in (0, 1, 254):
        result.problems.append(
            f"Time unit {unit} (GRIB1 table 4) is read as hours by ungrib (message at byte {offset})"
        )
    valid = reference + timedelta(hours=hours)
    level_type = pds[9]
    if level_type in GRIB1_LAYERS:
        level1, level2 = float(pds[10]), float(pds[11])
    else:
        level1, level2 = float(_u(pds, 10, 2)), None
    grid = Grid(-1)
    if pds[7] & 0x80:
        gds_head = handle.read(3)
        gds = gds_head + handle.read(max(_u(gds_head, 0, 3) - 3, 0))
        kind = gds[5] if len(gds) > 5 else -1
        if kind in (0, 4, 10) and len(gds) >= 28:
            unit_deg = 1e-3
            grid = Grid(
                {0: 0, 4: 40, 10: 1}[kind], ni=_u(gds, 6, 2), nj=_u(gds, 8, 2),
                lat1=_s(gds, 10, 3) * unit_deg, lon1=_s(gds, 13, 3) * unit_deg,
                lat2=_s(gds, 17, 3) * unit_deg, lon2=_s(gds, 20, 3) * unit_deg,
                di=None if _u(gds, 23, 2) == 0xFFFF else _u(gds, 23, 2) * unit_deg,
                dj=None if kind == 4 else _u(gds, 25, 2) * unit_deg, scanning=gds[27],
            )  # fmt: skip
        elif kind >= 0:
            grid = Grid({1: 10, 3: 30, 5: 20}.get(kind, 1000 + kind))
    result.records.append(
        Record(
            1,
            offset,
            pds[3],
            None,
            pds[8],
            level_type,
            level1,
            level2,
            valid,
            grid,
            pds[4],
            indicator,
        )
    )


def _grib1_large_end(handle: BinaryIO, offset: int, approximate: int, size: int) -> int | None:
    """End of an ECMWF "large" GRIB1 message, whose length is coded in units of 120 octets: the
    "7777" end marker followed by another message or the end of the file."""
    start = max(offset, offset + approximate - 130)
    handle.seek(start)
    window = handle.read(140)
    for index in range(len(window) - 4, -1, -1):
        if window[index : index + 4] == b"7777":
            end = start + index + 4
            if end == size or window[index + 4 : index + 8] == b"GRIB":
                return end
    return None


def messages(handle: BinaryIO, size: int, result: Inventory) -> Iterator[tuple[int, int, int, int]]:
    """(offset, edition, total length, GRIB2 discipline) of each complete message. Bytes before
    and between messages (bulletin headers, padding) are skipped, as ungrib does; problems are
    added to ``result``."""
    offset = 0
    found_any = False
    while offset + 8 <= size:
        handle.seek(offset)
        head = handle.read(16)
        edition = head[7]
        if head[:4] != b"GRIB" or edition not in (1, 2) or (edition == 2 and len(head) < 16):
            marker = _resync(handle, offset, size)
            if marker is None:
                if not found_any:
                    result.problems.append("Not a GRIB file: no GRIB message found")
                return
            offset = marker
            continue
        found_any = True
        discipline = head[6] if edition == 2 else 0
        total = _u(head, 8, 8) if edition == 2 else _u(head, 4, 3)
        if edition == 1 and total & 0x800000:
            end = _grib1_large_end(handle, offset, (total & 0x7FFFFF) * 120, size)
            if end is None:
                result.problems.append(
                    f"Cannot find the end of the large GRIB1 message at byte {offset}"
                )
                return
            total = end - offset
        if total < MIN_LENGTH[edition]:
            result.problems.append(
                f"Invalid message length ({total} bytes) at byte {offset}: the file is damaged"
            )
            return
        if offset + total > size:
            result.truncated = True
            result.problems.append(
                f"The last message (at byte {offset}) is truncated: the file is incomplete"
            )
            return
        handle.seek(offset + total - 4)
        if handle.read(4) != b"7777":
            result.problems.append(
                f"The message at byte {offset} does not end where its length says: the file is damaged"
            )
            return
        yield offset, edition, total, discipline
        offset += total


def _resync(handle: BinaryIO, start: int, size: int, window: int = 1 << 16) -> int | None:
    """Next "GRIB" marker after ``start`` within ``window`` bytes (padding between messages)."""
    handle.seek(start + 1)
    chunk = handle.read(min(window, max(size - start - 1, 0)))
    index = chunk.find(b"GRIB")
    return None if index < 0 else start + 1 + index


def inventory(path: Path, limit: int | None = None) -> Inventory:
    """Every complete message of the file (or the first ``limit``)."""
    result = Inventory(path)
    size = path.stat().st_size
    with path.open("rb") as handle:
        for offset, edition, total, discipline in messages(handle, size, result):
            before = len(result.records)
            try:
                if edition == 2:
                    _grib2(handle, offset, total, discipline, result)
                else:
                    _grib1(handle, offset, total, result)
            except (ValueError, IndexError) as error:  # impossible dates or short sections
                del result.records[before:]
                result.problems.append(
                    f"Unreadable header in the message at byte {offset}: {error}"
                )
            if limit is not None and len(result.records) >= limit:
                break
    return result


# ------------------------------------------------------------------ cache


CACHE_SIZE = 4096
_cache: OrderedDict[tuple[str, int, int], Inventory] = OrderedDict()
_cache_lock = Lock()


def cached_inventory(path: Path, compute: bool = True) -> Inventory | None:
    """Inventory kept in memory until the file changes (size or modification time). With
    ``compute`` False, None when the file has not been inventoried yet."""
    stat = path.stat()
    key = (str(path.resolve()), stat.st_size, stat.st_mtime_ns)
    with _cache_lock:
        found = _cache.get(key)
    if found is not None or not compute:
        return found
    found = inventory(path)
    with _cache_lock:
        _cache[key] = found
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
    return found
