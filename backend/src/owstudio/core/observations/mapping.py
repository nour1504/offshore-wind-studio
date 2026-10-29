"""Import mappings: how to read an observation file and turn its columns into series.

A mapping says how the file is laid out, how its time stamps are written (format, time zone,
position in the averaging period), where the station is and what every column holds (variable,
height, unit, statistic, quality flags, missing codes, direction convention). Mappings are saved
under ``<observations>/mappings/<name>.json`` and reused for every file of the same logger.
"""

import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from owstudio.core.i18n import tr
from owstudio.core.series import VARIABLES, TimeLabel

NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.()-]{0,63}$")
IDENTIFIER = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$"
MAPPING_FORMAT = "owstudio-observation-mapping/1"

Statistic = Literal["mean", "std", "min", "max", "sample"]
# "platform": height above a platform deck whose elevation above mean sea level is known
HeightReference = Literal["agl", "asl", "platform"]
Instrument = Literal["met_mast", "lidar", "floating_lidar", "buoy", "platform", "other"]
Severity = Literal["info", "warning", "error"]

# Text that marks a missing value in most files; numeric codes such as -999 are never assumed
DEFAULT_MISSING = ["", "NaN", "nan", "NAN", "NA", "N/A", "n/a", "null", "NULL", "None", "#N/A"]

# Variables that have no measurement height
SURFACE_VARIABLES = {
    "surface_pressure", "sea_level_pressure", "pblh", "friction_velocity", "sensible_heat_flux",
    "latent_heat_flux", "moisture_flux", "obukhov_length", "inverse_obukhov_length",
    "roughness_length", "sst", "skin_temperature", "power", "energy", "precipitation",
}  # fmt: skip


class Flag(BaseModel):
    """A problem or an assumption found while reading, converting or comparing.

    ``error`` blocks an import until the mapping says what to do; ``warning`` and ``info`` are
    recorded with the dataset."""

    code: str
    message: str
    column: str | None = None
    severity: Severity = "warning"


class FileOptions(BaseModel):
    """Layout of the file. ``None`` means detected from the file (and reported)."""

    model_config = ConfigDict(extra="forbid")

    format: Literal["auto", "delimited", "netcdf"] = "auto"
    encoding: str | None = None
    # A single character, or "whitespace" for runs of spaces and tabs
    delimiter: str | None = None
    decimal: Literal[".", ","] | None = None
    # Lines skipped at the top of the file, before the header line
    skip_rows: int | None = Field(None, ge=0)
    header: bool | None = None
    # A line of units right after the header
    units_row: bool | None = None
    # Further lines skipped after the header (and units) line, e.g. a "Avg/Smp" line
    skip_after_header: int | None = Field(None, ge=0)
    # Lines starting with this text are ignored wherever they are
    comment: str = "#"
    missing: list[str] = Field(default_factory=lambda: list(DEFAULT_MISSING))


class TimeSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # One column, or several (date and time...) joined with a space before parsing
    columns: list[str] = Field(default_factory=list)
    # strptime format, "ISO8601", "unix" (seconds since 1970-01-01 UTC), "unix_ms", or "excel"
    # (days since 1899-12-30, Windows Excel); "" = detected
    format: str = ""
    # "UTC", a fixed offset ("UTC+01:00", "+0100"), or an IANA zone ("Europe/Berlin") whose
    # daylight saving time changes are applied. None: not given (blocks the import)
    timezone: str | None = None
    # Local times that occur twice when clocks go back (IANA zones only)
    ambiguous: Literal["reject", "infer", "earlier", "later", "drop"] = "reject"
    # Local times skipped when clocks go forward (IANA zones only)
    nonexistent: Literal["reject", "drop"] = "reject"
    # Position of the time stamp in the averaging period; "instant" for samples
    label: TimeLabel | None = None
    averaging_s: float | None = Field(None, ge=0)


class DistortionSector(BaseModel):
    """Directions (from, clockwise) where the mast, boom or platform disturbs the flow."""

    model_config = ConfigDict(extra="forbid")

    start_deg: float = Field(ge=0, le=360)
    end_deg: float = Field(ge=0, le=360)
    note: str = ""

    def contains(self, direction: float) -> bool:
        start, end, d = self.start_deg % 360, self.end_deg % 360, direction % 360
        return start <= d < end if start <= end else d >= start or d < end


class Station(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field("station", pattern=IDENTIFIER)
    name: str = ""
    lat: float | None = Field(None, ge=-90, le=90)
    lon: float | None = Field(None, ge=-180, le=360)
    instrument: Instrument = "met_mast"
    # Default height reference of the columns
    height_reference: HeightReference = "agl"
    # Elevation of the platform deck above mean sea level, for heights given above the platform
    platform_elevation_m: float | None = None
    distortion_sectors: list[DistortionSector] = Field(default_factory=list)
    description: str = ""


class QualitySpec(BaseModel):
    """A column of quality codes for one data column, and what the codes mean."""

    model_config = ConfigDict(extra="forbid")

    column: str
    good: list[str] = Field(default_factory=list)
    suspect: list[str] = Field(default_factory=list)
    bad: list[str] = Field(default_factory=list)
    # Codes not listed above
    other: Literal["good", "suspect", "bad"] = "bad"


class ColumnSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: str
    # A canonical name of owstudio.core.series.VARIABLES, or any other name
    variable: str = Field(min_length=1)
    height_m: float | None = None
    # The station's when None
    height_reference: HeightReference | None = None
    # Unit in the file; values of canonical variables are converted to the canonical unit
    unit: str = ""
    statistic: Statistic = "mean"
    # Averaging period of this column when it differs from the file's (seconds)
    averaging_s: float | None = Field(None, ge=0)
    quality: QualitySpec | None = None
    # Codes marking missing values in this column, on top of the file's
    missing: list[str] = Field(default_factory=list)
    # Directions: "from" (meteorological) or "to" (where the flow goes); None: not given
    direction: Literal["from", "to"] | None = None
    # Added to the directions read, e.g. to correct a vane or LiDAR north misalignment
    direction_offset_deg: float = 0.0
    sensor: str = ""


class Mapping(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = ""
    file: FileOptions = Field(default_factory=FileOptions)
    time: TimeSpec = Field(default_factory=TimeSpec)
    station: Station = Field(default_factory=Station)
    columns: list[ColumnSpec] = Field(default_factory=list)


def is_direction(variable: str) -> bool:
    info = VARIABLES.get(variable)
    return bool(info and info.circular) or (info is None and "direction" in variable)


def needs_height(variable: str) -> bool:
    return variable in VARIABLES and variable not in SURFACE_VARIABLES


def readiness(mapping: Mapping) -> list[Flag]:
    """What the mapping must still say before an import: errors only."""
    errors: list[Flag] = []

    def error(code: str, message: str, column: str | None = None) -> None:
        errors.append(Flag(code=code, message=message, column=column, severity="error"))

    time = mapping.time
    if not time.columns:
        error("time_columns_missing", "Choose the column(s) holding the time stamps.")
    if time.timezone is None and time.format not in ("unix", "unix_ms"):
        error(
            "no_timezone",
            "Give the time zone of the time stamps (UTC, a fixed offset such as UTC+01:00, "
            "or a zone such as Europe/Berlin when the logger follows daylight saving time).",
        )
    if time.label is None:
        error(
            "time_label_unknown",
            "Say whether each time stamp marks the start, the centre or the end of its "
            "averaging period, or that values are instantaneous samples.",
        )
    elif time.label == "instant" and time.averaging_s:
        error("averaging_inconsistent", "Instantaneous values cannot have an averaging period.")
    elif time.label != "instant" and not time.averaging_s:
        error("averaging_unknown", "Give the averaging period of the values (e.g. 600 s).")
    if not mapping.columns:
        error("no_columns", "Choose at least one column to import.")
    seen: dict[tuple[str, float | None, str], str] = {}
    for spec in mapping.columns:
        if spec.column in time.columns:
            error("column_is_time", f"Column {spec.column} is a time column.", spec.column)
        if spec.variable in VARIABLES and not spec.unit.strip():
            error(
                "unit_unknown",
                f"Give the unit of column {spec.column} ({spec.variable}).",
                spec.column,
            )
        if needs_height(spec.variable) and spec.height_m is None:
            error("height_not_found", f"Give the height of column {spec.column}.", spec.column)
        reference = spec.height_reference or mapping.station.height_reference
        if (
            reference == "platform"
            and spec.height_m is not None
            and mapping.station.platform_elevation_m is None
        ):
            error(
                "platform_elevation_missing",
                "Heights above the platform need the elevation of the platform deck above "
                "mean sea level.",
                spec.column,
            )
        key = (spec.variable, spec.height_m, spec.statistic)
        if key in seen and spec.height_reference == mapping.station.height_reference:
            error(
                "duplicate_series",
                f"Columns {seen[key]} and {spec.column} both give {spec.statistic} "
                f"{spec.variable} at {spec.height_m} m: give them different heights or import "
                "one of them.",
                spec.column,
            )
        seen[key] = spec.column
    return errors


# ------------------------------------------------------------------- saved mappings


def mappings_folder(observations: Path) -> Path:
    return observations / "mappings"


def _mapping_path(observations: Path, name: str) -> Path:
    if not NAME.match(name):
        raise ValueError(
            tr(
                "A mapping name uses letters, digits, spaces and . _ - ( ), up to 64 characters",
                "Un nom de correspondance utilise des lettres, chiffres, espaces et . _ - ( ), 64 caractères au plus",
            )
        )
    return mappings_folder(observations) / f"{name}.json"


def save_mapping(observations: Path, name: str, mapping: Mapping) -> Path:
    path = _mapping_path(observations, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {"format": MAPPING_FORMAT, "name": name, "mapping": mapping.model_dump(mode="json")}
    path.write_text(json.dumps(document, indent=1), encoding="utf-8")
    return path


def load_mapping(observations: Path, name: str) -> Mapping:
    path = _mapping_path(observations, name)
    if not path.exists():
        raise KeyError(name)
    document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return Mapping.model_validate(document["mapping"])


def delete_mapping(observations: Path, name: str) -> None:
    path = _mapping_path(observations, name)
    if not path.exists():
        raise KeyError(name)
    path.unlink()


def list_mappings(observations: Path) -> list[dict[str, Any]]:
    folder = mappings_folder(observations)
    found = []
    for path in sorted(folder.glob("*.json")) if folder.exists() else []:
        try:
            mapping = load_mapping(observations, path.stem)
        except (ValueError, KeyError):
            continue
        found.append(
            {
                "name": path.stem,
                "description": mapping.description,
                "station": mapping.station.id,
                "columns": len(mapping.columns),
            }
        )
    return found
