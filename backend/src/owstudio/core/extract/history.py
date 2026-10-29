"""The WRF history files (wrfout) of one run and domain, read lazily.

A run may have several files per domain (frames_per_outfile, restart segments). They are read
as one time line; a time present in two files (the end of a segment and the start of the next)
is kept once, from the earlier file. Only the requested variables and grid windows are read:
the files are hundreds of megabytes.
"""

import json
import re
import threading
from dataclasses import dataclass
from functools import cached_property, lru_cache
from pathlib import Path
from typing import Any

import netCDF4
import numpy as np
import pandas as pd

from owstudio.core import ncio
from owstudio.core.i18n import tr
from owstudio.core.postproc.windowed import history_paths, output_sources

# The colons of the time may also be dashes, or U+F03A: the character WSL and Git's bash show
# Windows for a ":" in a Linux file name (outputs copied from a WSL or Linux folder)
FILE = re.compile("^wrfout_d(\\d\\d)_(\\d{4}-\\d\\d-\\d\\d_\\d\\d[-:]\\d\\d[-:]\\d\\d)")
# Index of the times of each history file, next to the outputs of a run: written once (at the
# import, or at the first reading), it spares reading every file again (about 40 ms each, 12 min
# for a year of hourly files on 2 domains). A file rewritten since (date or size) is read again.
TIMES_INDEX = ".ows-times.json"
_INDEX_LOCK = threading.Lock()


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


# Small windows only (a few grid points around a place, or the cells of a farm): many can be kept
@lru_cache(maxsize=8192)
def _read(
    path: str, mtime: float, name: str, j: tuple[int, int] | None, i: tuple[int, int] | None
) -> np.ndarray:
    """All times of a variable in a window [j0, j1) x [i0, i1) (or the whole grid)."""
    with ncio.LOCK, netCDF4.Dataset(path) as ds:
        var = ds.variables[name]
        index: list[Any] = [slice(None)] * var.ndim
        dims = var.dimensions
        if j is not None and dims[-2].startswith("south_north"):
            index[-2] = slice(*j)
        if i is not None and dims[-1].startswith("west_east"):
            index[-1] = slice(*i)
        data = var[tuple(index)]
    return np.ma.filled(np.ma.asarray(data, dtype=float), np.nan)


@lru_cache(maxsize=100_000)
def _file_times(path: str, mtime: float) -> pd.DatetimeIndex:
    """Times written in one history file, read once per file and date."""
    with ncio.LOCK, netCDF4.Dataset(path) as ds:
        stamps = netCDF4.chartostring(ds.variables["Times"][:])
    return pd.to_datetime(
        [str(s) for s in np.atleast_1d(stamps)], format="%Y-%m-%d_%H:%M:%S", utc=True
    )


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
        with ncio.LOCK, netCDF4.Dataset(self.paths[0]) as ds:
            return {
                name: VariableInfo(
                    name,
                    tuple(v.dimensions),
                    str(getattr(v, "units", "")),
                    str(getattr(v, "description", "")),
                    str(getattr(v, "stagger", "")),
                )
                for name, v in ds.variables.items()
            }

    @cached_property
    def attributes(self) -> dict[str, Any]:
        with ncio.LOCK, netCDF4.Dataset(self.paths[0]) as ds:
            return {name: ds.getncattr(name) for name in ds.ncattrs()}

    def has(self, name: str) -> bool:
        return name in self.variables

    @cached_property
    def coordinates(self) -> tuple[np.ndarray, np.ndarray]:
        """XLAT and XLONG of the mass points (first time)."""
        return self.at_time("XLAT", 0), self.at_time("XLONG", 0)

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
        _, keep = self._timeline
        offset = position
        for path, kept in zip(self.paths, keep, strict=True):
            if offset < len(kept):
                with ncio.LOCK, netCDF4.Dataset(path) as ds:
                    var = ds.variables[name]
                    raw = var[int(kept[offset])] if var.dimensions[0] == "Time" else var[:]
                values = np.ma.filled(np.ma.asarray(raw, dtype=float), np.nan)
                dims = self.variables[name].dims
                if dims[-1] == "west_east_stag":
                    values = 0.5 * (values[..., :-1] + values[..., 1:])
                if len(dims) >= 2 and dims[-2] == "south_north_stag":
                    values = 0.5 * (values[..., :-1, :] + values[..., 1:, :])
                return values
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
        sj = 1 if len(dims) >= 2 and dims[-2] == "south_north_stag" else 0
        si = 1 if dims[-1] == "west_east_stag" else 0
        jw = None if j0 is None else (j0, j0 + size + sj)
        iw = None if i0 is None else (i0, i0 + size + si)
        area = self._area
        read_j: tuple[int, int] | None
        read_i: tuple[int, int] | None
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
            inside = True
            read_j, read_i = (area[0], area[1] + sj), (area[2], area[3] + si)
            cut_j = slice(j0 - area[0], j0 - area[0] + size + sj)
            cut_i = slice(i0 - area[2], i0 - area[2] + size + si)
        else:
            inside = False
            read_j, read_i, cut_j, cut_i = jw, iw, slice(None), slice(None)
        parts = []
        _, keep = self._timeline
        for path, kept in zip(self.paths, keep, strict=True):
            data = _read(*self._key(path), name, read_j, read_i)
            if inside:
                data = data[..., cut_j, cut_i]
            if dims[0] == "Time":
                data = data[kept]
            parts.append(data)
        values = np.concatenate(parts) if dims[0] == "Time" else parts[0]
        if dims[-1] == "west_east_stag":
            values = 0.5 * (values[..., :-1] + values[..., 1:])
        if len(dims) >= 2 and dims[-2] == "south_north_stag":
            values = 0.5 * (values[..., :-1, :] + values[..., 1:, :])
        return values
