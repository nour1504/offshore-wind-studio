"""Input files provided by the user (own GRIB or NetCDF files, separate SST): listing and
format detection.

WPS's ungrib reads GRIB editions 1 and 2 only. NetCDF files (the default download format of the
new Copernicus Climate Data Store) are converted to WPS intermediate files before the run
(netcdf.py); a folder must hold one kind or the other.
"""

import fnmatch
import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from owstudio.core.i18n import tr

Format = Literal["grib1", "grib2", "netcdf", "unknown"]

# Files checked for their format before a run: enough to catch a wrong folder or format
SNIFF_LIMIT = 50
# How far below the chosen folder files are searched; how many matching files at most, and how
# many files looked at in all (a folder given by mistake, such as /, stops instead of hanging)
DEPTH = 8
MAX_FILES = 50_000
MAX_SCANNED = 500_000


class TooManyFiles(OSError):
    """More files than are listed below a folder: a narrower folder or pattern is needed."""


@dataclass(frozen=True)
class UserFile:
    # Path from the chosen folder, with / (a file of a subfolder: 2025/gfs.2025100100.f000.grib2)
    name: str
    path: Path
    size: int
    mtime_ns: int
    format: Format


def sniff(path: Path) -> Format:
    """Format from the first bytes: GRIB indicator section with its edition, NetCDF or HDF5."""
    try:
        with path.open("rb") as handle:
            head = handle.read(8)
    except OSError:
        return "unknown"
    if head[:4] == b"GRIB" and len(head) >= 8:
        return "grib2" if head[7] == 2 else "grib1" if head[7] == 1 else "unknown"
    if head[:3] == b"CDF" or head[:4] == b"\x89HDF":
        return "netcdf"
    return "unknown"


def walk(root: Path) -> Iterator[tuple[str, Path]]:
    """Every file of ``root`` and of its subfolders (hidden ones left out, linked ones followed
    once), as (path from ``root`` with /, path)."""
    seen: set[str] = set()
    scanned = 0
    for current, folders, files in os.walk(root, followlinks=True):
        real = os.path.realpath(current)
        relative = Path(os.path.relpath(current, root)).as_posix()
        depth = 0 if relative == "." else relative.count("/") + 1
        if real in seen or depth > DEPTH:
            folders[:] = []
            continue
        seen.add(real)
        folders[:] = sorted(f for f in folders if not f.startswith("."))
        scanned += len(files)
        if scanned > MAX_SCANNED:
            raise TooManyFiles(too_many(root, MAX_SCANNED))
        for name in files:
            path = Path(current) / name
            if not name.startswith(".") and path.is_file():
                yield (name if relative == "." else f"{relative}/{name}", path)


def too_many(root: Path, count: int) -> str:
    return tr(
        f"More than {count} files in {root} and its subfolders: choose a narrower folder or pattern",
        f"Plus de {count} fichiers dans {root} et ses sous-dossiers : choisir un dossier ou un motif plus précis",
    )


def list_files(folder: str, pattern: str = "*", sniff_all: bool = False) -> list[UserFile]:
    """Files of ``folder`` and of its subfolders whose name matches ``pattern`` (glob,
    case-insensitive; a pattern with / is matched against the path from ``folder``), sorted by
    that path.

    Raises FileNotFoundError when the folder does not exist, TooManyFiles above MAX_FILES
    matching files.
    """
    root = Path(folder).expanduser()
    if not root.is_dir():
        raise FileNotFoundError(tr(f"Folder not found: {root}", f"Dossier introuvable : {root}"))
    wanted = (pattern or "*").lower()
    entries = []
    for relative, path in walk(root):
        if fnmatch.fnmatch((relative if "/" in wanted else path.name).lower(), wanted):
            entries.append((relative, path))
            if len(entries) > MAX_FILES:
                raise TooManyFiles(too_many(root, MAX_FILES))
    entries.sort()
    result = []
    for index, (relative, path) in enumerate(entries):
        stat = path.stat()
        kind: Format = sniff(path) if sniff_all or index < SNIFF_LIMIT else "unknown"
        result.append(UserFile(relative, path, stat.st_size, stat.st_mtime_ns, kind))
    return result


def problems(files: list[UserFile], what: str) -> list[str]:
    """Why these files cannot be read by ungrib, in the user's terms."""
    if not files:
        return [
            tr(
                f"{what}: no file matches the folder and pattern.",
                f"{what} : aucun fichier ne correspond au dossier et au motif.",
            )
        ]
    issues = []
    netcdf = [f.name for f in files if f.format == "netcdf"]
    grib = [f.name for f in files if f.format in ("grib1", "grib2")]
    if netcdf and grib:
        issues.append(
            tr(
                f"{what}: the files mix NetCDF ({netcdf[0]}…) and GRIB ({grib[0]}…): narrow the file "
                "pattern to one kind.",
                f"{what} : les fichiers mélangent NetCDF ({netcdf[0]}…) et GRIB ({grib[0]}…) : restreignez le motif des fichiers à un seul type.",
            )
        )
    unknown = [f.name for f in files[:SNIFF_LIMIT] if f.format == "unknown"]
    if unknown:
        issues.append(
            tr(
                f"{what}: {len(unknown)} file(s) are not GRIB ({unknown[0]}…): narrow the file pattern.",
                f"{what} : {len(unknown)} fichier(s) ne sont pas en GRIB ({unknown[0]}…) : restreignez le motif des fichiers.",
            )
        )
    return issues


def repeated_names(files: list[UserFile], what: str) -> list[str]:
    """A file name found in several subfolders (a backup copy?): ungrib would read both. Only a
    warning: dated folders may hold files of the same name (20251001/sst.grb2)."""
    folders: dict[str, list[str]] = {}
    for f in files:
        folders.setdefault(f.path.name.lower(), []).append(f.name)
    repeated = [names for names in folders.values() if len(names) > 1]
    if not repeated:
        return []
    first = repeated[0]
    return [
        tr(
            f"{what}: {len(repeated)} file name(s) in several folders ({first[0]}, {first[1]}): "
            "check that they are not copies, ungrib reads every file found.",
            f"{what} : {len(repeated)} nom(s) de fichier dans plusieurs dossiers ({first[0]}, {first[1]}) : "
            "vérifier qu'il ne s'agit pas de copies, ungrib lit tous les fichiers trouvés.",
        )
    ]


def all_netcdf(files: list[UserFile]) -> bool:
    """The files are NetCDF, converted before the run instead of being read by ungrib."""
    return bool(files) and all(f.format == "netcdf" for f in files)
