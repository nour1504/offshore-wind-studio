"""The WRF history files (wrfout) of one run and domain, read lazily.

Several files per domain form one time line; a time in two files (end of a segment, start of the
next) is kept once, from the earlier file. Only the requested variables and grid windows are read:
the files are hundreds of megabytes.
"""

import json
import re
import threading
from collections import OrderedDict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from functools import cached_property, lru_cache
from pathlib import Path
from typing import Any

import netCDF4
import numpy as np
import pandas as pd

from owstudio.core import ncio
from owstudio.core.i18n import tr
from owstudio.core.postproc.windowed import history_paths, output_sources
from owstudio.core.times import WRF_DATE, utc_stamp

# The colons of the time may also be dashes, or U+F03A: the character WSL and Git's bash show
# Windows for a ":" in a Linux file name (outputs copied from a WSL or Linux folder)
FILE = re.compile("^wrfout_d(\\d\\d)_(\\d{4}-\\d\\d-\\d\\d_\\d\\d[-:]\\d\\d[-:]\\d\\d)")
# Index of the times of each history file, next to the outputs of a run: written once (at the
# import, or at the first reading), it spares reading every file again (about 40 ms each, 12 min
# for a year of hourly files on 2 domains). A file rewritten since (date or size) is read again.
TIMES_INDEX = ".ows-times.json"
_INDEX_LOCK = threading.Lock()
# Fields that do not change in time (coordinates, map rotation), per file and date: every page
# that places a point or a turbine asks for them
_CONSTANTS: OrderedDict[tuple[str, float, str], np.ndarray] = OrderedDict()
_CONSTANTS_SIZE = 64
_CONSTANTS_LOCK = threading.Lock()


def domains(folder: Path) -> list[int]:
    found = {int(m.group(1)) for p in history_paths(folder) if (m := FILE.match(p.name))}
    return sorted(found)


@dataclass(frozen=True)
class VariableInfo:
    name: str
    dims: tuple[str, ...]
    units: str
    description: str
    stagger: str

    @property
    def vertical(self) -> bool:
        return "bottom_top" in self.dims or "bottom_top_stag" in self.dims

    @property
    def horizontal(self) -> bool:
        return any(d.startswith(("west_east", "south_north")) for d in self.dims)


Span = tuple[int, int] | None
# Windows read, per file, date, variable and window. Small windows only (a few grid points around
# a place, or the cells of a farm): many can be kept
_WINDOWS: OrderedDict[tuple[str, float, str, Span, Span], np.ndarray] = OrderedDict()
_WINDOWS_SIZE = 8192
_WINDOWS_LOCK = threading.Lock()


def _read(path: str, mtime: float, name: str, j: Span, i: Span) -> np.ndarray:
    """All times of a variable in a window [j0, j1) x [i0, i1) (or the whole grid)."""
    return _read_many(path, mtime, {name: (j, i)})[name]


def _read_many(
    path: str, mtime: float, windows: dict[str, tuple[Span, Span]]
) -> dict[str, np.ndarray]:
    """The windows of several variables of one file, read with one opening of the file (about
    20 ms, against a fraction of a millisecond for a small window)."""
    keys = {name: (path, mtime, name, j, i) for name, (j, i) in windows.items()}
    found: dict[str, np.ndarray] = {}
    with _WINDOWS_LOCK:
        for name, key in keys.items():
            if key in _WINDOWS:
                _WINDOWS.move_to_end(key)
                found[name] = _WINDOWS[key]
    missing = [name for name in keys if name not in found]
    if not missing:
        return found
    with ncio.LOCK, netCDF4.Dataset(path) as ds:
        for name in missing:
            var = ds.variables[name]
            index: list[Any] = [slice(None)] * var.ndim
            dims = var.dimensions
            j, i = windows[name]
            if j is not None and dims[-2].startswith("south_north"):
                index[-2] = slice(*j)
            if i is not None and dims[-1].startswith("west_east"):
                index[-1] = slice(*i)
            found[name] = np.ma.filled(np.ma.asarray(var[tuple(index)], dtype=float), np.nan)
    with _WINDOWS_LOCK:
        for name in missing:
            _WINDOWS[keys[name]] = found[name]
        while len(_WINDOWS) > _WINDOWS_SIZE:
            _WINDOWS.popitem(last=False)
    return found


@lru_cache(maxsize=512)
def _header(path: str, mtime: float) -> tuple[dict[str, VariableInfo], dict[str, Any]]:
    """Variables and global attributes of one history file, read once per file and date (about
    20 ms each: every page asks for them)."""
    with ncio.LOCK, netCDF4.Dataset(path) as ds:
        variables = {
            name: VariableInfo(
                name,
                tuple(v.dimensions),
                str(getattr(v, "units", "")),
                str(getattr(v, "description", "")),
                str(getattr(v, "stagger", "")),
            )
            for name, v in ds.variables.items()
        }
        return variables, {name: ds.getncattr(name) for name in ds.ncattrs()}


@lru_cache(maxsize=100_000)
def _file_times(path: str, mtime: float) -> pd.DatetimeIndex:
    """Times written in one history file, read once per file and date."""
    with ncio.LOCK, netCDF4.Dataset(path) as ds:
        stamps = netCDF4.chartostring(ds.variables["Times"][:])
    return pd.to_datetime([str(s) for s in np.atleast_1d(stamps)], format=WRF_DATE, utc=True)


def _load_index(folder: Path) -> dict[str, Any]:
    try:
        data = json.loads((folder / TIMES_INDEX).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_index(folder: Path, found: dict[str, Any]) -> None:
    """Adds the times just read to the index; nothing is written where it cannot be."""
    with _INDEX_LOCK:
        index = {**_load_index(folder), **found}
        temporary = folder / f"{TIMES_INDEX}.tmp"
        try:
            temporary.write_text(json.dumps(index), encoding="utf-8")
            temporary.replace(folder / TIMES_INDEX)
        except OSError:
            temporary.unlink(missing_ok=True)


def record_times(folder: Path, copies: list[tuple[Path, Path]]) -> None:
    """At the import: the times of each history file copied (source, destination), read when the
    import was checked, written in the index of the outputs ``folder``. Files that cannot be read
    from here are left for their first reading."""
    found: dict[str, Any] = {}
    for source, destination in copies:
        if not FILE.match(destination.name):
            continue
        try:
            parsed = _file_times(str(source), source.stat().st_mtime)
            stat = destination.stat()
        except (OSError, ValueError, KeyError):
            continue
        found[str(destination)] = {
            "mtime": stat.st_mtime,
            "size": stat.st_size,
            "times": [t.isoformat() for t in parsed],
        }
    if found:
        _save_index(folder, found)


class HistoryFiles:
    def __init__(self, folder: Path, domain: int) -> None:
        self.folder = folder
        self.domain = domain
        self.paths = [p for p in history_paths(folder, domain) if FILE.match(p.name)]
        self._sources = {s.folder: s for s in output_sources(folder)}
        if not self.paths:
            raise FileNotFoundError(
                tr(
                    f"No history file of domain {domain} in {folder}",
                    f"Aucun fichier d'historique du domaine {domain} dans {folder}",
                )
            )
        # Mass points [j0, j1) x [i0, i1) read whole from each file for the windows inside it
        self._area: tuple[int, int, int, int] | None = None

    def focus(self, j0: int, j1: int, i0: int, i1: int) -> None:
        """Windows inside [j0, j1) x [i0, i1) are then cut from one read of that area per file
        and variable: the places of a farm cost one read instead of one each."""
        self._area = (j0, j1, i0, i1)

    def _key(self, path: Path) -> tuple[str, float]:
        return str(path), path.stat().st_mtime

    @cached_property
    def _timeline(self) -> tuple[pd.DatetimeIndex, list[np.ndarray]]:
        """Times of all files, and for each file the positions of its times that are kept."""
        times: list[pd.Timestamp] = []
        keep: list[np.ndarray] = []
        seen: set[pd.Timestamp] = set()
        index = _load_index(self.folder)
        found: dict[str, Any] = {}
        for path in self.paths:
            stat = path.stat()
            entry = index.get(str(path))
            if entry and entry.get("mtime") == stat.st_mtime and entry.get("size") == stat.st_size:
                parsed = pd.to_datetime(entry["times"], utc=True)
            else:
                parsed = _file_times(str(path), stat.st_mtime)
                found[str(path)] = {
                    "mtime": stat.st_mtime,
                    "size": stat.st_size,
                    "times": [t.isoformat() for t in parsed],
                }
            mask = self._sources[path.parent].mask(parsed) & np.array(
                [t not in seen for t in parsed], dtype=bool
            )
            seen.update(parsed[mask])
            times.extend(parsed[mask])
            keep.append(np.flatnonzero(mask))
        if found:
            _save_index(self.folder, found)
        return pd.DatetimeIndex(times), keep

    @property
    def times(self) -> pd.DatetimeIndex:
        return self._timeline[0]

    @cached_property
    def variables(self) -> dict[str, VariableInfo]:
        return _header(*self._key(self.paths[0]))[0]

    @cached_property
    def attributes(self) -> dict[str, Any]:
        return _header(*self._key(self.paths[0]))[1]

    def initial_first(self, period_start: datetime) -> bool:
        """Whether the first time kept is the simulation's initial time, written before the first
        step (POWER still zero). Never with the window method, whose first time ends a spin-up;
        otherwise when SIMULATION_START_DATE says so, or, in files that do not say, when it is
        ``period_start``."""
        if (self.folder / "windows.json").is_file() or not len(self.times):
            return False
        started = self.attributes.get("SIMULATION_START_DATE")
        if started:
            return bool(
                self.times[0] == pd.Timestamp(datetime.strptime(str(started), WRF_DATE), tz="UTC")
            )
        return bool(self.times[0] == utc_stamp(period_start))

    def has(self, name: str) -> bool:
        return name in self.variables

    def constant(self, name: str) -> np.ndarray:
        """A field that does not change in time, at the first output time (read-only array)."""
        key = (*self._key(self.paths[0]), name)
        with _CONSTANTS_LOCK:
            if key in _CONSTANTS:
                _CONSTANTS.move_to_end(key)
                return _CONSTANTS[key]
        values = self.at_time(name, 0)
        values.flags.writeable = False
        with _CONSTANTS_LOCK:
            _CONSTANTS[key] = values
            while len(_CONSTANTS) > _CONSTANTS_SIZE:
                _CONSTANTS.popitem(last=False)
        return values

    @cached_property
    def coordinates(self) -> tuple[np.ndarray, np.ndarray]:
        """XLAT and XLONG of the mass points (first time)."""
        return self.constant("XLAT"), self.constant("XLONG")

    def at_time(self, name: str, position: int) -> np.ndarray:
        """The whole field of a variable at one kept time (position in ``times``), on mass
        points for horizontally staggered variables: for maps."""
        if name not in self.variables:
            raise KeyError(
                tr(
                    f"{name} is not in the history files of domain {self.domain}",
                    f"{name} n'est pas dans les fichiers d'historique du domaine {self.domain}",
                )
            )
        return self.at_time_many((name,), position)[name]

    def at_time_many(self, names: Iterable[str], position: int) -> dict[str, np.ndarray]:
        """``at_time`` for several variables, with one opening of the file (about 20 ms each);
        variables absent from the files are left out."""
        chosen = [name for name in names if name in self.variables]
        _, keep = self._timeline
        offset = position
        for path, kept in zip(self.paths, keep, strict=True):
            if offset < len(kept):
                raw = {}
                with ncio.LOCK, netCDF4.Dataset(path) as ds:
                    for name in chosen:
                        var = ds.variables[name]
                        raw[name] = (
                            var[int(kept[offset])] if var.dimensions[0] == "Time" else var[:]
                        )
                fields = {}
                for name in chosen:
                    values = np.ma.filled(np.ma.asarray(raw[name], dtype=float), np.nan)
                    dims = self.variables[name].dims
                    if dims[-1] == "west_east_stag":
                        values = 0.5 * (values[..., :-1] + values[..., 1:])
                    if len(dims) >= 2 and dims[-2] == "south_north_stag":
                        values = 0.5 * (values[..., :-1, :] + values[..., 1:, :])
                    fields[name] = values
                return fields
            offset -= len(kept)
        raise IndexError(tr(f"No output time {position}", f"Aucun instant de sortie {position}"))

    def box(self, name: str, j0: int, j1: int, i0: int, i1: int) -> np.ndarray:
        """Values of a variable on mass points [j0, j1) x [i0, i1), all kept times."""
        if name not in self.variables:
            raise KeyError(
                tr(
                    f"{name} is not in the history files of domain {self.domain}",
                    f"{name} n'est pas dans les fichiers d'historique du domaine {self.domain}",
                )
            )
        dims = self.variables[name].dims
        jw = (j0, j1 + (1 if dims[-2] == "south_north_stag" else 0))
        iw = (i0, i1 + (1 if dims[-1] == "west_east_stag" else 0))
        _, keep = self._timeline
        parts = [
            _read(*self._key(path), name, jw, iw)[kept]
            for path, kept in zip(self.paths, keep, strict=True)
        ]
        values = np.concatenate(parts)
        if dims[-1] == "west_east_stag":
            values = 0.5 * (values[..., :-1] + values[..., 1:])
        if dims[-2] == "south_north_stag":
            values = 0.5 * (values[..., :-1, :] + values[..., 1:, :])
        return values

    def cells(self, name: str, cells: list[tuple[int, int]]) -> np.ndarray:
        """Values at the mass points of the given (j, i) cells, all kept times: (time, [level,]
        cell). Each file is read once for the box around the cells, and only the cells are
        kept: a long run with many cells stays fast and small."""
        j0, i0 = min(j for j, _ in cells), min(i for _, i in cells)
        j1, i1 = max(j for j, _ in cells) + 1, max(i for _, i in cells) + 1
        dims = self.variables[name].dims
        jw = (j0, j1 + (1 if dims[-2] == "south_north_stag" else 0))
        iw = (i0, i1 + (1 if dims[-1] == "west_east_stag" else 0))
        rows = np.array([j - j0 for j, _ in cells])
        columns = np.array([i - i0 for _, i in cells])
        _, keep = self._timeline
        parts = []
        for path, kept in zip(self.paths, keep, strict=True):
            values = _read(*self._key(path), name, jw, iw)[kept]
            if dims[-1] == "west_east_stag":
                values = 0.5 * (values[..., :-1] + values[..., 1:])
            if dims[-2] == "south_north_stag":
                values = 0.5 * (values[..., :-1, :] + values[..., 1:, :])
            parts.append(values[..., rows, columns])
        return np.concatenate(parts)

    def _span(
        self, name: str, j0: int | None, i0: int | None, size: int
    ) -> tuple[Span, Span, tuple[slice, slice] | None]:
        """The window read from each file for ``window``, and the part of it kept when it is cut
        from the focus area."""
        dims = self.variables[name].dims
        sj = 1 if len(dims) >= 2 and dims[-2] == "south_north_stag" else 0
        si = 1 if dims[-1] == "west_east_stag" else 0
        area = self._area
        horizontal = (
            len(dims) >= 2
            and dims[-2].startswith("south_north")
            and dims[-1].startswith("west_east")
        )
        if (
            area is not None
            and horizontal
            and j0 is not None
            and i0 is not None
            and area[0] <= j0
            and j0 + size <= area[1]
            and area[2] <= i0
            and i0 + size <= area[3]
        ):
            return (
                (area[0], area[1] + sj),
                (area[2], area[3] + si),
                (
                    slice(j0 - area[0], j0 - area[0] + size + sj),
                    slice(i0 - area[2], i0 - area[2] + size + si),
                ),
            )
        jw = None if j0 is None else (j0, j0 + size + sj)
        iw = None if i0 is None else (i0, i0 + size + si)
        return jw, iw, None

    def prefetch(
        self, names: Iterable[str], j0: int | None = None, i0: int | None = None, size: int = 2
    ) -> None:
        """Reads the windows of several variables with one opening of each file, instead of one
        per variable: ``window`` then finds them read. Variables absent from the files are left
        out."""
        spans = {
            name: self._span(name, j0, i0, size)[:2] for name in names if name in self.variables
        }
        if spans:
            for path in self.paths:
                _read_many(*self._key(path), spans)

    def window(
        self, name: str, j0: int | None = None, i0: int | None = None, size: int = 2
    ) -> np.ndarray:
        """Values on mass points, all kept times: (time, [level,] size, size) around (j0, i0),
        or the whole grid without a window. Staggered horizontal dimensions are averaged onto
        the mass points; staggered vertical levels are returned as they are."""
        if name not in self.variables:
            raise KeyError(
                tr(
                    f"{name} is not in the history files of domain {self.domain}",
                    f"{name} n'est pas dans les fichiers d'historique du domaine {self.domain}",
                )
            )
        dims = self.variables[name].dims
        read_j, read_i, cut = self._span(name, j0, i0, size)
        parts = []
        _, keep = self._timeline
        for path, kept in zip(self.paths, keep, strict=True):
            data = _read(*self._key(path), name, read_j, read_i)
            if cut is not None:
                data = data[..., cut[0], cut[1]]
            if dims[0] == "Time":
                data = data[kept]
            parts.append(data)
        values = np.concatenate(parts) if dims[0] == "Time" else parts[0]
        if dims[-1] == "west_east_stag":
            values = 0.5 * (values[..., :-1] + values[..., 1:])
        if len(dims) >= 2 and dims[-2] == "south_north_stag":
            values = 0.5 * (values[..., :-1, :] + values[..., 1:, :])
        return values
