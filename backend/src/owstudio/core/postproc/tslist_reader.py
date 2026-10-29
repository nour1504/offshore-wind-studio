"""Read WRF time series output (prefix.dNN.TS and vertical profile files).

The first line of every file describes the location; the TS file then has one line per time
step, the profile files the model time in hours followed by one value per model level.
Profile heights (PH) are geopotential heights above sea level at the mass levels; the header
gives the ground elevation, so heights above ground are PH minus that elevation.
"""

import math
import re
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from owstudio.core.i18n import tr

# Dry air gas constant (J/kg/K), cp = 3.5 Rd, reference pressure (Pa): as core/extract/quantities.py
RD, P0 = 287.0, 1.0e5
CP = 3.5 * RD

# Columns of the TS file without the solar diagnostics, after README.tslist
TS_COLUMNS = [
    "id", "ts_hour", "id_tsloc", "ix", "iy", "t", "q", "u", "v", "psfc",
    "glw", "gsw", "hfx", "lh", "tsk", "tslb1", "rainc", "rainnc", "clw",
]  # fmt: skip
MISSING = 1e29
# Values too wide for their Fortran field are printed as asterisks
STARS = re.compile(r"\*+")
# Parsed files kept in memory, the most recently used first, up to this size
CACHE_BYTES = 512 * 1024 * 1024
HEADER = re.compile(
    r"^(?P<name>.{25}) ?(?P<domain>[ \d]{2})(?P<id>[ \d]{3}) (?P<prefix>\S+)\s+"
    r"\(\s*(?P<lat>-?[\d.]+),\s*(?P<lon>-?[\d.]+)\)\s+"
    r"\(\s*(?P<i>\d+),\s*(?P<j>\d+)\)\s+"
    r"\(\s*(?P<glat>-?[\d.]+),\s*(?P<glon>-?[\d.]+)\)\s+"
    r"(?P<elevation>-?[\d.]+) meters,?\s*(?P<start>\d{4}-\d{2}-\d{2}_\d{2}:\d{2}:\d{2})?"
)


@dataclass(frozen=True)
class Location:
    name: str
    prefix: str
    domain: int
    lat: float
    lon: float
    i: int
    j: int
    grid_lat: float
    grid_lon: float
    elevation: float
    start: datetime | None


def read_header(line: str) -> Location:
    match = HEADER.match(line.rstrip("\n"))
    if not match:
        raise ValueError(
            tr(
                f"Unrecognised time series header: {line!r}",
                f"En-tête de série temporelle non reconnu : {line!r}",
            )
        )
    g = match.groupdict()
    start = datetime.strptime(g["start"], "%Y-%m-%d_%H:%M:%S") if g["start"] else None
    return Location(
        name=g["name"].strip(),
        prefix=g["prefix"],
        domain=int(g["domain"]),
        lat=float(g["lat"]),
        lon=float(g["lon"]),
        i=int(g["i"]),
        j=int(g["j"]),
        grid_lat=float(g["glat"]),
        grid_lon=float(g["glon"]),
        elevation=float(g["elevation"]),
        start=start,
    )


_parsed: OrderedDict[tuple[str, int, int], tuple[str, np.ndarray]] = OrderedDict()
_parsed_lock = threading.Lock()


def _numbers(path: Path) -> tuple[str, np.ndarray]:
    """Header line and table of a time series file. A file is parsed once while it is
    unchanged (same size and modification time): the analyses read the same profiles for
    every height and both wind components."""
    stat = path.stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    with _parsed_lock:
        found = _parsed.get(key)
        if found is not None:
            _parsed.move_to_end(key)
            return found[0], found[1].copy()
    header, values = _parse(path)
    with _parsed_lock:
        _parsed[key] = (header, values)
        while sum(v.nbytes for _, v in _parsed.values()) > CACHE_BYTES and len(_parsed) > 1:
            _parsed.popitem(last=False)
    return header, values.copy()


def _parse(path: Path) -> tuple[str, np.ndarray]:
    with path.open(encoding="ascii", errors="replace") as f:
        header = f.readline()
        text = f.read()
    if "*" in text:
        text = STARS.sub(" nan ", text)
    lines = [line for line in text.splitlines() if line.strip()]
    width = len(lines[0].split()) if lines else 0
    tokens = text.split()
    if width and len(tokens) == len(lines) * width:
        values = np.array(tokens, dtype=float).reshape(len(lines), width)
    else:
        # Lines of different lengths (a file cut while being written): the lines that read as
        # numbers with the usual number of columns
        rows = []
        for line in lines:
            try:
                rows.append([_number(token) for token in line.split()])
            except ValueError:
                continue
        lengths = [len(r) for r in rows]
        width = max(set(lengths), key=lengths.count) if rows else 0
        kept = [r[:width] for r in rows if len(r) >= width]
        values = np.array(kept, dtype=float).reshape(len(kept), width)
    values[values > MISSING] = np.nan
    return header, values


def _number(token: str) -> float:
    """Fortran prints values too wide for their field, such as the 1.E30 marking missing
    data, as asterisks."""
    return math.nan if token.startswith("*") or token == "nan" else float(token)


def _times(location: Location, hours: np.ndarray) -> pd.DatetimeIndex:
    start = pd.Timestamp(location.start) if location.start else pd.Timestamp(0)
    # Hours are written with six decimals (3.6 ms): round to the tenth of a second
    return start + pd.to_timedelta(np.round(hours * 36000) / 10, unit="s")


def read_surface(path: Path) -> tuple[Location, pd.DataFrame]:
    header, values = _numbers(path)
    location = read_header(header)
    columns = TS_COLUMNS[: values.shape[1]] + [
        f"extra{k}" for k in range(max(0, values.shape[1] - len(TS_COLUMNS)))
    ]
    frame = pd.DataFrame(values, columns=columns)
    frame.index = _times(location, frame["ts_hour"].to_numpy())
    return location, frame.drop(columns=["id", "ts_hour", "id_tsloc", "ix", "iy"])


def read_profile(path: Path) -> pd.DataFrame:
    header, values = _numbers(path)
    location = read_header(header)
    frame = pd.DataFrame(values[:, 1:], columns=range(1, values.shape[1]))
    frame.index = _times(location, values[:, 0])
    return frame


def interpolate_rows(heights: np.ndarray, values: np.ndarray, target: float) -> np.ndarray:
    """Each row's value at the height ``target``, linear between the levels around it (heights
    increasing with the level); NaN outside the levels. Rows with a missing level use the
    others."""
    z, v = np.asarray(heights, dtype=float), np.asarray(values, dtype=float)
    out = np.full(len(z), np.nan)
    if z.ndim != 2 or z.shape[1] < 2:
        return out
    complete = np.isfinite(z).all(axis=1) & np.isfinite(v).all(axis=1)
    rows = np.flatnonzero(complete)
    if rows.size:
        zz, vv = z[rows], v[rows]
        k = np.clip((zz <= target).sum(axis=1) - 1, 0, zz.shape[1] - 2)[:, None]
        z1, z2 = np.take_along_axis(zz, k, 1)[:, 0], np.take_along_axis(zz, k + 1, 1)[:, 0]
        v1, v2 = np.take_along_axis(vv, k, 1)[:, 0], np.take_along_axis(vv, k + 1, 1)[:, 0]
        with np.errstate(divide="ignore", invalid="ignore"):
            value = v1 + (target - z1) / (z2 - z1) * (v2 - v1)
        inside = (zz[:, 0] <= target) & (target <= zz[:, -1])
        out[rows] = np.where(inside, value, np.nan)
    for row in np.flatnonzero(~complete):
        ok = np.isfinite(z[row]) & np.isfinite(v[row])
        if ok.sum() >= 2:
            out[row] = np.interp(target, z[row][ok], v[row][ok], left=np.nan, right=np.nan)
    return out


def wind_direction(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Meteorological direction the wind blows from, degrees clockwise from north."""
    return np.asarray((270.0 - np.degrees(np.arctan2(v, u))) % 360.0)


class TimeSeriesSet:
    """All time series files of one run, found in its outputs/<run>/tslist directory."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def locations(self) -> list[Location]:
        from owstudio.core.postproc.windowed import time_series_sources

        sources = time_series_sources(self.directory)
        if len(sources) != 1 or sources[0].folder != self.directory:
            found_by_key = {}
            for source in sources:
                for location in TimeSeriesSet(source.folder).locations():
                    found_by_key[(location.prefix, location.domain)] = location
            return list(found_by_key.values())
        found = []
        for path in sorted(self.directory.glob("*.d[0-9][0-9].TS")):
            with path.open(encoding="ascii", errors="replace") as f:
                found.append(read_header(f.readline()))
        return found

    def _path(self, prefix: str, domain: int, kind: str) -> Path:
        return self.directory / f"{prefix}.d{domain:02d}.{kind}"

    def has(self, prefix: str, domain: int) -> bool:
        from owstudio.core.postproc.windowed import time_series_sources

        return any(
            (s.folder / f"{prefix}.d{domain:02d}.TS").is_file()
            for s in time_series_sources(self.directory)
        )

    def series(self, prefix: str, domain: int, hub_height_m: float) -> pd.DataFrame:
        """Surface variables, and the wind and temperature at hub height, at every model time
        step. The temperature comes from the profiles of potential temperature (TH) and pressure
        (PR): T = θ (p / p0)^(Rd/cp)."""
        from owstudio.core.postproc.windowed import time_series_sources

        sources = time_series_sources(self.directory)
        if len(sources) != 1 or sources[0].folder != self.directory:
            parts = [
                frame[s.mask(pd.DatetimeIndex(frame.index))]
                for s in sources
                if TimeSeriesSet(s.folder).has(prefix, domain)
                for frame in [TimeSeriesSet(s.folder).series(prefix, domain, hub_height_m)]
            ]
            if not parts:
                return pd.DataFrame()
            frame = pd.concat(parts).sort_index()
            return frame[~frame.index.duplicated(keep="first")]
        location, surface = read_surface(self._path(prefix, domain, "TS"))
        frame = pd.DataFrame(index=surface.index)
        frame["wind_speed_10m"] = np.hypot(surface["u"], surface["v"])
        frame["u_10m"] = surface["u"]
        frame["v_10m"] = surface["v"]
        frame["wind_direction_10m"] = wind_direction(
            surface["u"].to_numpy(), surface["v"].to_numpy()
        )
        frame["temperature_2m"] = surface["t"] - 273.15
        frame["pressure_surface_hpa"] = surface["psfc"] / 100
        frame["sensible_heat_flux"] = surface["hfx"]
        frame["latent_heat_flux"] = surface["lh"]
        if self._path(prefix, domain, "PH").exists():
            heights = read_profile(self._path(prefix, domain, "PH"))
            u = read_profile(self._path(prefix, domain, "UU"))
            v = read_profile(self._path(prefix, domain, "VV"))
            rows = min(len(heights), len(u), len(v), len(frame))
            z = heights.to_numpy()[:rows] - location.elevation
            u_hub = interpolate_rows(z, u.to_numpy()[:rows], hub_height_m)
            v_hub = interpolate_rows(z, v.to_numpy()[:rows], hub_height_m)
            hub = pd.DataFrame(
                {
                    "wind_speed_hub": np.hypot(u_hub, v_hub),
                    "wind_direction_hub": wind_direction(u_hub, v_hub),
                    "u_hub": u_hub,
                    "v_hub": v_hub,
                },
                index=frame.index[:rows],
            )
            if (
                self._path(prefix, domain, "TH").exists()
                and self._path(prefix, domain, "PR").exists()
            ):
                theta = read_profile(self._path(prefix, domain, "TH")).to_numpy()
                pressure = read_profile(self._path(prefix, domain, "PR")).to_numpy()
                rows = min(rows, len(theta), len(pressure))
                at_hub = interpolate_rows(z[:rows], theta[:rows], hub_height_m) * (
                    interpolate_rows(z[:rows], pressure[:rows], hub_height_m) / P0
                ) ** (RD / CP)
                hub["temperature_hub"] = pd.Series(at_hub - 273.15, index=frame.index[:rows])
            frame = frame.join(hub)
        return frame


def average(frame: pd.DataFrame, seconds: int, start: pd.Timestamp | None = None) -> pd.DataFrame:
    """Time-weighted means over ]t - seconds, t], stamped at t (core/method/averaging.py):
    each value counts for the model step ending at it; directions from the mean components.
    Incomplete intervals are left out; frame.attrs["averaging"] says what was done."""
    from owstudio.core.method.averaging import weighted_means

    if seconds <= 0 or frame.empty:
        return frame
    vectors = {
        direction: components
        for direction, components in (
            ("wind_direction_hub", ("u_hub", "v_hub")),
            ("wind_direction_10m", ("u_10m", "v_10m")),
        )
        if set(components) <= set(frame.columns)
    }
    means = weighted_means(frame, seconds, start, vectors)
    result = means.frame
    result.attrs["averaging"] = means.note
    result.attrs["excluded_intervals"] = means.excluded
    return result
