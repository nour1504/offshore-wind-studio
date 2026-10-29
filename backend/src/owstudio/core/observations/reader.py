"""Reading observation files: delimited text (CSV, TXT, DAT) and NetCDF, with the detection of
their layout, and suggestions of what each column holds.

Nothing is guessed silently: every detected or suggested choice is returned so that the user
confirms it in the import mapping, and ambiguities are reported as flags.
"""

import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd
from charset_normalizer import from_bytes

from owstudio.core import ncio
from owstudio.core.i18n import tr
from owstudio.core.observations.mapping import FileOptions, Flag

SAMPLE_BYTES = 256_000
NUMBER = re.compile(r"^[+-]?(\d+([.,]\d*)?|[.,]\d+)([eE][+-]?\d+)?$")
UNIT_HINT = re.compile(
    r"(m/s|m s-1|ms-1|deg|°|%|hpa|mbar|pa\b|kn|k\b|degc|°c|w/m|\[.*\]|\(.*\))", re.IGNORECASE
)


@dataclass
class Layout:
    format: str
    encoding: str
    delimiter: str
    decimal: str
    skip_rows: int
    header: bool
    units_row: bool
    columns: list[str]
    units: dict[str, str] = field(default_factory=dict)
    flags: list[Flag] = field(default_factory=list)


def _lines(text: str, comment: str) -> list[tuple[int, str]]:
    return [
        (n, line)
        for n, line in enumerate(text.splitlines())
        if line.strip() and not (comment and line.lstrip().startswith(comment))
    ]


def _split(line: str, delimiter: str) -> list[str]:
    if delimiter == "whitespace":
        return line.split()
    return next(csv.reader([line], delimiter=delimiter))


def _numeric(cell: str) -> bool:
    return bool(NUMBER.match(cell.strip()))


def detect(path: Path, options: FileOptions | None = None) -> Layout:
    """Encoding, delimiter, decimal mark, header and units lines of a delimited text file."""
    options = options or FileOptions()
    raw = path.read_bytes()[:SAMPLE_BYTES]
    flags: list[Flag] = []
    encoding = options.encoding
    if encoding is None:
        try:
            raw.decode("utf-8-sig")
            encoding = "utf-8-sig"
        except UnicodeDecodeError:
            best = from_bytes(raw).best()
            encoding = best.encoding if best else "latin-1"
            flags.append(
                Flag(
                    code="encoding_detected",
                    message=tr(
                        f"Text encoding detected as {encoding}",
                        f"Encodage du texte détecté : {encoding}",
                    ),
                    severity="info",
                )
            )
    text = raw.decode(encoding, errors="replace")
    lines = _lines(text, options.comment)[:60]
    if not lines:
        raise ValueError(tr("The file is empty", "Le fichier est vide"))
    delimiter = options.delimiter
    if delimiter is None:
        best_score, delimiter = -1.0, ","
        for candidate in (";", "\t", ",", "|", "whitespace"):
            counts = [len(_split(line, candidate)) for _, line in lines[-30:]]
            common = max(set(counts), key=counts.count)
            score = counts.count(common) / len(counts) * (common > 1) * min(common, 50)
            if score > best_score:
                best_score, delimiter = score, candidate
    rows = [_split(line, delimiter) for _, line in lines]
    width = max({len(r) for r in rows[-30:]}, key=[len(r) for r in rows[-30:]].count)
    # First data line: as wide as the table and mostly numeric (dates count as non-numeric)
    first_data = next(
        (
            k
            for k, r in enumerate(rows)
            if len(r) == width and sum(_numeric(c) for c in r) >= max(1, width // 2)
        ),
        0,
    )
    header = (
        options.header
        if options.header is not None
        else first_data > 0 and len(rows[first_data - 1]) >= width - 1
    )
    header_index = first_data - 1 if header else -1
    units_row = options.units_row
    if units_row is None:
        units_row = (
            header
            and header_index >= 1
            and sum(bool(UNIT_HINT.search(c)) for c in rows[header_index]) >= max(1, width // 3)
        )
        if units_row:
            header_index -= 1
    skip = (
        options.skip_rows
        if options.skip_rows is not None
        else (lines[header_index][0] if header and header_index >= 0 else lines[first_data][0])
    )
    names = (
        [c.strip() for c in rows[header_index]]
        if header and header_index >= 0
        else [f"column {k + 1}" for k in range(width)]
    )
    names = [n or f"column {k + 1}" for k, n in enumerate(names)]
    duplicates = sorted({n for n in names if names.count(n) > 1})
    if duplicates:
        flags.append(
            Flag(
                code="duplicate_columns",
                message=tr(
                    f"Duplicated column names: {', '.join(duplicates)}",
                    f"Noms de colonnes en double : {', '.join(duplicates)}",
                ),
            )
        )
        seen: dict[str, int] = {}
        renamed = []
        for n in names:
            seen[n] = seen.get(n, 0) + 1
            renamed.append(n if seen[n] == 1 else f"{n} ({seen[n]})")
        names = renamed
    units: dict[str, str] = {}
    if units_row:
        units = {
            n: u.strip() for n, u in zip(names, rows[header_index + 1], strict=False) if u.strip()
        }
    decimal = options.decimal
    if decimal is None:
        sample = [c for r in rows[first_data : first_data + 30] for c in r if _numeric(c)]
        comma = sum("," in c and "." not in c for c in sample)
        decimal = "," if delimiter != "," and comma > len(sample) / 4 else "."
        if decimal == ",":
            flags.append(
                Flag(
                    code="decimal_comma",
                    message=tr("Decimal comma detected", "Virgule décimale détectée"),
                    severity="info",
                )
            )
    return Layout(
        "delimited",
        encoding,
        delimiter,
        decimal,
        int(skip),
        bool(header),
        bool(units_row),
        names,
        units,
        flags,
    )


def read_delimited(path: Path, layout: Layout, nrows: int | None = None) -> pd.DataFrame:
    """The table as text cells (conversion happens with the mapping)."""
    text = path.read_bytes().decode(layout.encoding, errors="replace")
    skip = layout.skip_rows + (1 if layout.header else 0) + (1 if layout.units_row else 0)
    lines = text.splitlines()[skip:]
    body = "\n".join(line for line in lines if line.strip() and not line.lstrip().startswith("#"))
    sep = r"\s+" if layout.delimiter == "whitespace" else layout.delimiter
    frame = pd.read_csv(
        io.StringIO(body), sep=sep, header=None, names=layout.columns, dtype=str, keep_default_na=False,
        nrows=nrows, engine="python", index_col=False, skipinitialspace=True,
    )  # fmt: skip
    return frame


def read_netcdf(path: Path) -> tuple[pd.DataFrame, dict[str, str]]:
    """One-dimensional variables along the time dimension as columns, plus a column ``time``
    (decoded CF times); variables with a second dimension of heights become one column per
    height (``name@<height>``). Units from the variables' attributes."""
    import xarray as xr

    with ncio.LOCK, xr.open_dataset(path) as ds:
        time_name = next((n for n in ds.coords if "time" in str(n).lower()), None) or next(
            (n for n in ds.dims if "time" in str(n).lower()), None
        )
        if time_name is None:
            raise ValueError(
                tr(
                    "No time coordinate in this NetCDF file",
                    "Aucune coordonnée de temps dans ce fichier NetCDF",
                )
            )
        columns: dict[str, Any] = {"time": pd.to_datetime(ds[time_name].values).astype(str)}
        units: dict[str, str] = {}
        for name, var in ds.data_vars.items():
            dims = list(var.dims)
            if dims == [time_name]:
                columns[str(name)] = var.values
                units[str(name)] = str(var.attrs.get("units", ""))
            elif len(dims) == 2 and time_name in dims:
                other = next(d for d in dims if d != time_name)
                levels = ds[other].values if other in ds.coords else range(ds.sizes[other])
                for k, level in enumerate(levels):
                    column = f"{name}@{level}"
                    columns[column] = var.isel({other: k}).values
                    units[column] = str(var.attrs.get("units", ""))
        return pd.DataFrame(columns).astype(str), units


# ------------------------------------------------------------- suggestions

PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(r"(^|[_\s])(ti|turb(ulence)?[_\s]?int)", re.IGNORECASE),
        "turbulence_intensity",
        "mean",
    ),
    (
        re.compile(
            r"(std|stdev|sigma|sd)[_\s]?(ws|wspd|speed|hws)|((ws|wspd|speed|hws)[_\s]?(std|stdev|sigma|sd))",
            re.IGNORECASE,
        ),
        "wind_speed_std",
        "mean",
    ),
    (
        re.compile(r"(gust|ws[_\s]?max|wspd[_\s]?max|max[_\s]?(ws|wspd))", re.IGNORECASE),
        "gust",
        "max",
    ),
    (
        re.compile(r"(^|[_\s])(wd|wdir|dir(ection)?|winddir)", re.IGNORECASE),
        "wind_direction",
        "mean",
    ),
    (
        re.compile(r"(^|[_\s])(ws|wspd|hws|wind[_\s]?speed|speed|v[_\s]?hor|spd)", re.IGNORECASE),
        "wind_speed",
        "mean",
    ),
    (re.compile(r"(^|[_\s])(sst|water[_\s]?temp)", re.IGNORECASE), "sst", "mean"),
    (
        re.compile(r"(^|[_\s])(t|ta|temp|tair|air[_\s]?temp)([_\s]|\d|$)", re.IGNORECASE),
        "temperature",
        "mean",
    ),
    (re.compile(r"(^|[_\s])(rh|hum(idity)?)", re.IGNORECASE), "relative_humidity", "mean"),
    (
        re.compile(r"(^|[_\s])(p|pres|press(ure)?|baro)([_\s]|\d|$)", re.IGNORECASE),
        "pressure",
        "mean",
    ),
    (
        re.compile(r"(^|[_\s])(w|vert(ical)?[_\s]?(speed|wind))([_\s]|\d|$)", re.IGNORECASE),
        "w",
        "mean",
    ),
]
HEIGHT = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*m(?![a-z])|[_@\s](\d+(?:[.,]\d+)?)$|^(\d+(?:[.,]\d+)?)[_\s]",
    re.IGNORECASE,
)
TIME_NAME = re.compile(r"(date|time|timestamp|datetime|^t$)", re.IGNORECASE)
UNIT_IN_NAME = re.compile(r"\[(.*?)\]|\((.*?)\)")


def suggest(
    columns: list[str], units: dict[str, str], sample: pd.DataFrame
) -> tuple[list[str], list[dict[str, Any]], list[Flag]]:
    """Candidate time columns, and for each other column a suggested variable, height, unit and
    statistic, with the reason; flags for ambiguities."""
    flags: list[Flag] = []
    time_columns = [c for c in columns if TIME_NAME.search(c) and not _all_numeric(sample.get(c))]
    if not time_columns:
        time_columns = [c for c in columns if _looks_like_dates(sample.get(c))]
    if len(time_columns) > 2:
        flags.append(
            Flag(
                code="several_time_columns",
                message=tr(
                    f"Several candidate time columns: {', '.join(time_columns)}",
                    f"Plusieurs colonnes de date possibles : {', '.join(time_columns)}",
                ),
            )
        )
    suggestions = []
    for column in columns:
        if column in time_columns:
            continue
        variable, statistic, reason = None, "mean", "not recognised from its name"
        for pattern, name, stat in PATTERNS:
            if pattern.search(column):
                variable, statistic, reason = name, stat, f"name matches {name}"
                break
        height = None
        match = HEIGHT.search(column)
        if match and variable not in ("sst", "pressure"):
            height = float(next(g for g in match.groups() if g).replace(",", "."))
        unit = units.get(column, "")
        found = UNIT_IN_NAME.search(column)
        if not unit and found:
            unit = next(g for g in found.groups() if g)
        entry = {
            "column": column,
            "variable": variable,
            "height_m": height,
            "unit": unit,
            "statistic": statistic,
            "reason": reason,
            "numeric_share": _numeric_share(sample.get(column)),
        }
        if variable and not unit:
            flags.append(
                Flag(
                    code="unit_unknown",
                    message=tr(
                        f"Unit of {column} not given in the file",
                        f"Unité de {column} absente du fichier",
                    ),
                    column=column,
                )
            )
        if (
            variable
            in (
                "wind_speed",
                "wind_direction",
                "temperature",
                "wind_speed_std",
                "turbulence_intensity",
                "gust",
            )
            and height is None
        ):
            flags.append(
                Flag(
                    code="height_not_found",
                    message=tr(
                        f"Height of {column} not found in its name",
                        f"Hauteur de {column} introuvable dans son nom",
                    ),
                    column=column,
                )
            )
        if variable == "wind_direction":
            flags.append(
                Flag(
                    code="direction_convention",
                    message=tr(
                        f"Check that {column} gives where the wind comes from (meteorological convention)",
                        f"Vérifiez que {column} indique d'où vient le vent (convention météorologique)",
                    ),
                    column=column,
                    severity="info",
                )
            )
        suggestions.append(entry)
    return time_columns, suggestions, flags


def _cells(values: Any) -> list[str]:
    return [] if values is None else [str(v).strip() for v in list(values)[:50] if str(v).strip()]


def _all_numeric(values: Any) -> bool:
    cells = _cells(values)
    return bool(cells) and all(_numeric(c) for c in cells)


def _numeric_share(values: Any) -> float:
    cells = _cells(values)
    return sum(_numeric(c) for c in cells) / len(cells) if cells else 0.0


def _looks_like_dates(values: Any) -> bool:
    cells = _cells(values)
    return (
        bool(cells)
        and sum(bool(re.search(r"\d{1,4}[-/.]\d{1,2}[-/.]\d{1,4}|\d{1,2}:\d{2}", c)) for c in cells)
        > len(cells) / 2
    )
