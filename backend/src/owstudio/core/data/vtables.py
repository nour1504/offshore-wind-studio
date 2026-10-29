"""WPS variable tables (Vtables): which GRIB records ungrib extracts and under which names.

The standard tables of WPS 4.7.0 ship with the application (owstudio/data/vtables). A run with a
standard table uses the engine's own copy; a custom table is written into the case files.
"""

import re
from dataclasses import dataclass
from functools import cache
from importlib import resources
from importlib.resources.abc import Traversable

from owstudio.core.i18n import tr

# Recommended tables for common sources, shown first in the interface
RECOMMENDED: dict[str, str] = {
    "Vtable.GFS": "NCEP GFS (0.25°, 0.5°) and GDAS analyses and forecasts",
    "Vtable.ECMWF": "ECMWF IFS and ERA5 reanalysis (pressure levels and single levels, GRIB1 or GRIB2)",
    "Vtable.SST": "Sea surface temperature analyses (OSTIA, RTG, ERA5 SST...), field SST only",
    "Vtable.ERA-interim.pl": "ERA-Interim on pressure levels",
    "Vtable.CFSR": "NCEP CFSR / CFSv2 reanalysis",
    "Vtable.NAM": "NCEP NAM",
    "Vtable.UKMO_ENDGame": "UK Met Office Unified Model (ENDGame)",
    "Vtable.ICONp": "DWD ICON on pressure levels",
}

ROW = re.compile(r"^\s*[^|]*\|[^|]*\|[^|]*\|[^|]*\|\s*([A-Za-z0-9_]+)\s*\|")


@dataclass(frozen=True)
class VtableInfo:
    name: str
    description: str
    recommended: bool
    fields: list[str]


def _folder() -> Traversable:
    return resources.files("owstudio.data") / "vtables"


@cache
def names() -> list[str]:
    return sorted(p.name for p in _folder().iterdir() if p.name.startswith("Vtable."))


def read(name: str) -> str:
    """Contents of a standard table. Raises KeyError for an unknown name."""
    if name not in names():
        raise KeyError(tr(f"Unknown Vtable {name!r}", f"Vtable inconnue {name!r}"))
    text: str = (_folder() / name).read_bytes().decode("ascii", errors="replace")
    return text


def rows(text: str) -> list[tuple[int, str]]:
    """(line number, text) of the table rows: between the separator under the header and the
    closing separator; notes written after the table are not rows."""
    lines = text.splitlines()
    separators = [i for i, line in enumerate(lines) if line.startswith("-----")]
    if len(separators) < 2:
        return [
            (i + 1, line)
            for i, line in enumerate(lines)
            if line.strip() and not line.startswith(("GRIB", "Param", "Code", "-----"))
        ]
    first, last = separators[0], separators[-1]
    # The closing separator is the first one followed only by notes (the header has one too)
    for index in separators[1:]:
        following = [line for line in lines[index + 1 :] if line.strip()]
        if not following or not any(ROW.match(line) for line in following):
            last = index
            break
    return [
        (i + 1, lines[i])
        for i in range(first + 1, last)
        if lines[i].strip() and not lines[i].startswith("-----")
    ]


def fields(text: str) -> list[str]:
    """metgrid field names produced by a table, in order, without duplicates."""
    found: list[str] = []
    for _, line in rows(text):
        match = ROW.match(line)
        if match and match.group(1) not in found:
            found.append(match.group(1))
    return found


# parse_table.F: a blank column is -99, a "*" in the first level column is -88 (every level)
BLANK = -99
EVERY_LEVEL = -88


@dataclass(frozen=True)
class Entry:
    """One row of a table, read as ungrib's parse_table.F reads it."""

    line: int
    grib1_param: int
    grib1_level_type: int
    level1: int
    level2: int
    name: str
    units: str
    description: str
    # GRIB2 discipline, category, parameter, level type and product template (0 when absent)
    grib2: tuple[int, int, int, int]
    grib2_template: int = 0

    @property
    def output(self) -> bool:
        """Rows with a description are written by ungrib; the others only help derive fields."""
        return bool(self.description)


def _number(text: str) -> int:
    text = text.strip()
    if not text:
        return BLANK
    if "*" in text:
        return EVERY_LEVEL
    return int(float(text))


def entries(text: str) -> list[Entry]:
    """The rows of a table with their codes; rows that cannot be read are left out (see
    ``validate``)."""
    found = []
    for number, line in rows(text):
        cells = line.split("|")
        if len(cells) < 7:
            continue
        try:
            grib2 = [_number(c) for c in cells[7:11]] + [BLANK] * (4 - len(cells[7:11]))
            template = _number(cells[11]) if len(cells) > 12 else BLANK
            found.append(
                Entry(
                    line=number,
                    grib1_param=_number(cells[0]),
                    grib1_level_type=_number(cells[1]),
                    level1=_number(cells[2]),
                    level2=_number(cells[3]),
                    name=cells[4].strip(),
                    units=cells[5].strip(),
                    description=cells[6].strip(),
                    grib2=(grib2[0], grib2[1], grib2[2], grib2[3]),
                    grib2_template=0 if template == BLANK else template,
                )
            )
        except ValueError:
            continue
    return found


def catalogue() -> list[VtableInfo]:
    result = [
        VtableInfo(name, RECOMMENDED.get(name, ""), name in RECOMMENDED, fields(read(name)))
        for name in names()
    ]
    return sorted(result, key=lambda v: (not v.recommended, v.name))


def validate(text: str) -> list[str]:
    """Problems of a custom table, in the user's terms; empty when ungrib can read it."""
    lines = [line for line in text.splitlines() if line.strip()]
    problems = []
    # GRIB1-only tables start with "GRIB |", tables for both editions with "GRIB1|"
    if not lines or not lines[0].startswith("GRIB"):
        problems.append(
            tr(
                "The first line must be the header starting with 'GRIB1|' (or 'GRIB |'), as in the standard tables.",
                "La première ligne doit être l'en-tête commençant par 'GRIB1|' (ou 'GRIB |'), comme dans les tables standard.",
            )
        )
    separators = [i for i, line in enumerate(lines) if line.startswith("-----")]
    if len(separators) < 2:
        problems.append(
            tr(
                "The table must have a '-----' line after the header and another one after the last row.",
                "La table doit avoir une ligne '-----' après l'en-tête et une autre après la dernière ligne.",
            )
        )
    if not fields(text):
        problems.append(
            tr(
                "No row gives a metgrid field name (5th column).",
                "Aucune ligne ne donne de nom de champ pour metgrid (5e colonne).",
            )
        )
    for number, line in rows(text):
        if line.count("|") < 6:
            problems.append(
                tr(
                    f"Line {number} does not have the columns of a Vtable row: {line.strip()[:60]}",
                    f"La ligne {number} n'a pas les colonnes d'une ligne de Vtable : {line.strip()[:60]}",
                )
            )
    return problems
