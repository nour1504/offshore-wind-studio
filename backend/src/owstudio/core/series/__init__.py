"""Common internal format for time series, from simulations and observations alike.

A series is one variable at one location and one height, on UTC times, with the metadata needed
to compare it honestly with another series: where it comes from, how it was obtained, its unit,
its height reference, its sampling and averaging. Every reader (wrfout, tslist, observation files)
produces this format; every analysis, comparison and export consumes it.

Conventions, applied by the readers so that analyses never have to guess:

- Times are timezone-aware UTC, sorted, without duplicates.
- ``averaging_s == 0`` means instantaneous values. For averages, ``time_label`` says whether the
  time stamp marks the start, the centre or the end of the averaging period; readers keep the
  source's convention and record it, :func:`relabel` converts between conventions.
- Wind components ``u`` and ``v`` are earth-relative (eastward, northward), never grid-relative.
- Directions are meteorological: where the wind blows from, degrees clockwise from true north,
  in [0, 360).
- Heights are metres, above ground level (``agl``) or above mean sea level (``asl``); offshore
  the two only differ by the sea-surface elevation used by the source. ``surface`` marks
  variables without a height (fluxes, PBLH, SST...).
- Units follow :data:`VARIABLES`; :mod:`owstudio.core.series.units` converts others on import.
- Missing values are NaN. ``quality`` holds per-value flags: 0 good, 1 suspect, 2 bad,
  9 missing; a series without flags is considered unchecked, not good.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

HeightRef = Literal["agl", "asl", "surface"]
TimeLabel = Literal["instant", "start", "centre", "end"]
Source = Literal["wrfout", "tslist", "observation", "derived", "import"]

QUALITY_GOOD, QUALITY_SUSPECT, QUALITY_BAD, QUALITY_MISSING = 0, 1, 2, 9


@dataclass(frozen=True)
class VariableInfo:
    unit: str
    description: str
    # Circular quantities need vector or circular statistics, never plain means
    circular: bool = False


# Canonical variable names. Other names are accepted (any WRF variable, any measured quantity),
# with the unit given by the source.
VARIABLES: dict[str, VariableInfo] = {
    "wind_speed": VariableInfo("m s-1", "Horizontal wind speed"),
    "wind_direction": VariableInfo(
        "deg", "Direction the wind blows from, clockwise from true north", circular=True
    ),
    "u": VariableInfo("m s-1", "Eastward wind component (earth-relative)"),
    "v": VariableInfo("m s-1", "Northward wind component (earth-relative)"),
    "w": VariableInfo("m s-1", "Vertical wind component"),
    "wind_speed_std": VariableInfo(
        "m s-1", "Standard deviation of the wind speed over the averaging period"
    ),
    "turbulence_intensity": VariableInfo(
        "1", "Wind speed standard deviation divided by the mean wind speed"
    ),
    "gust": VariableInfo("m s-1", "Maximum wind speed over the averaging period"),
    "temperature": VariableInfo("K", "Air temperature"),
    "potential_temperature": VariableInfo("K", "Potential temperature"),
    "virtual_potential_temperature": VariableInfo("K", "Virtual potential temperature"),
    "pressure": VariableInfo("Pa", "Air pressure"),
    "surface_pressure": VariableInfo("Pa", "Pressure at the surface"),
    "sea_level_pressure": VariableInfo("Pa", "Pressure reduced to mean sea level"),
    "density": VariableInfo("kg m-3", "Air density"),
    "relative_humidity": VariableInfo("%", "Relative humidity"),
    "mixing_ratio": VariableInfo("kg kg-1", "Water vapour mixing ratio"),
    "specific_humidity": VariableInfo("kg kg-1", "Specific humidity"),
    "tke": VariableInfo("m2 s-2", "Turbulent kinetic energy"),
    "pblh": VariableInfo("m", "Planetary boundary layer height"),
    "friction_velocity": VariableInfo("m s-1", "Friction velocity u*"),
    "sensible_heat_flux": VariableInfo("W m-2", "Upward sensible heat flux at the surface"),
    "latent_heat_flux": VariableInfo("W m-2", "Upward latent heat flux at the surface"),
    "moisture_flux": VariableInfo("kg m-2 s-1", "Upward moisture flux at the surface"),
    "obukhov_length": VariableInfo("m", "Monin-Obukhov length L"),
    "inverse_obukhov_length": VariableInfo("m-1", "Inverse Monin-Obukhov length 1/L"),
    "roughness_length": VariableInfo("m", "Aerodynamic roughness length"),
    "sst": VariableInfo("K", "Sea surface temperature"),
    "skin_temperature": VariableInfo("K", "Skin (surface) temperature"),
    "bulk_richardson": VariableInfo("1", "Bulk Richardson number between two heights"),
    "shear_exponent": VariableInfo("1", "Power-law wind shear exponent between two heights"),
    "veer": VariableInfo("deg m-1", "Change of wind direction with height"),
    "power": VariableInfo("W", "Electrical power"),
    "energy": VariableInfo("Wh", "Electrical energy"),
    "precipitation": VariableInfo("mm", "Accumulated precipitation"),
}


class SeriesMeta(BaseModel):
    """Everything needed to interpret one series, kept alongside its values."""

    model_config = ConfigDict(extra="forbid")

    variable: str = Field(min_length=1)
    unit: str
    source: Source
    # Run id, observation dataset id, or any name identifying where the series comes from
    dataset: str
    location: str
    location_name: str = ""
    lat: float | None = None
    lon: float | None = None
    height_m: float | None = None
    height_ref: HeightRef = "surface"
    # How values were obtained: "measured", "tslist", "nearest cell", "bilinear", "derived: ..."
    method: str = ""
    # Nominal spacing of the values, seconds (None when irregular or unknown)
    frequency_s: float | None = None
    averaging_s: float = 0.0
    time_label: TimeLabel = "instant"
    # Original time reference of the source, e.g. "UTC+01:00" or "Europe/Paris", for the record
    original_timezone: str = "UTC"
    # Instrument, model configuration, processing notes...
    description: str = ""
    # Problems found while reading: ambiguous columns, assumed units, gaps...
    flags: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)

    @property
    def key(self) -> str:
        height = "" if self.height_m is None else f"@{self.height_m:g}{self.height_ref}"
        return f"{self.dataset}/{self.location}/{self.variable}{height}"

    @property
    def circular(self) -> bool:
        info = VARIABLES.get(self.variable)
        return info.circular if info else self.unit == "deg" and "direction" in self.variable


@dataclass
class Series:
    meta: SeriesMeta
    values: pd.Series
    # Per-value quality flags aligned with ``values``; None when the source gives none
    quality: pd.Series | None = None

    def __post_init__(self) -> None:
        self.values = normalise_index(self.values).astype("float64")
        if self.quality is not None:
            self.quality = (
                normalise_index(self.quality)
                .reindex(self.values.index)
                .fillna(QUALITY_MISSING)
                .astype("int8")
            )

    @property
    def times(self) -> pd.DatetimeIndex:
        index: pd.DatetimeIndex = self.values.index  # type: ignore[assignment]
        return index

    def good(self, accept_suspect: bool = False) -> pd.Series:
        """Values whose quality flag is good (or suspect when accepted), NaN elsewhere."""
        if self.quality is None:
            return self.values
        limit = QUALITY_SUSPECT if accept_suspect else QUALITY_GOOD
        return self.values.where(self.quality <= limit)

    def with_values(self, values: pd.Series, **changes: Any) -> "Series":
        """A new series with other values (and metadata changes), keeping the rest."""
        quality = self.quality.reindex(values.index) if self.quality is not None else None
        return Series(self.meta.model_copy(update=changes), values, quality)


def normalise_index(values: pd.Series) -> pd.Series:
    """Sorted, duplicate-free, timezone-aware UTC time index. Naive times are taken as UTC."""
    index = pd.DatetimeIndex(values.index)
    index = index.tz_localize("UTC") if index.tz is None else index.tz_convert("UTC")
    result = values.copy()
    result.index = index
    result = result[~result.index.duplicated(keep="first")]
    return result.sort_index()


def relabel(series: Series, to: TimeLabel) -> Series:
    """Moves the time stamps of an averaged series to another position in the averaging period."""
    meta = series.meta
    if meta.averaging_s <= 0 or meta.time_label in ("instant", to) or to == "instant":
        return series
    position = {"start": 0.0, "centre": 0.5, "end": 1.0}
    shift = pd.Timedelta(seconds=meta.averaging_s * (position[to] - position[meta.time_label]))
    values = series.values.copy()
    values.index = values.index + shift
    quality = None
    if series.quality is not None:
        quality = series.quality.copy()
        quality.index = quality.index + shift
    return Series(meta.model_copy(update={"time_label": to}), values, quality)


def regular_frequency(index: pd.DatetimeIndex) -> float | None:
    """The spacing of the times in seconds when (nearly) all steps are equal, else None."""
    if len(index) < 2:
        return None
    steps = np.diff(index.to_numpy(dtype="datetime64[ns]").astype("int64")) / 1e9
    median = float(np.median(steps))
    return median if median > 0 and np.mean(np.isclose(steps, median)) >= 0.9 else None


# ------------------------------------------------------------- tables and files

FRAME_COLUMNS = [
    "time",
    "dataset",
    "location",
    "variable",
    "height_m",
    "height_ref",
    "value",
    "unit",
    "quality",
]


def to_frame(series: list[Series]) -> pd.DataFrame:
    """Long table, one row per value: the exchange format for exports and comparisons."""
    parts = []
    for s in series:
        quality = (
            s.quality
            if s.quality is not None
            else pd.Series(-1, index=s.values.index, dtype="int8")
        )
        parts.append(
            pd.DataFrame(
                {
                    "time": s.values.index,
                    "dataset": s.meta.dataset,
                    "location": s.meta.location,
                    "variable": s.meta.variable,
                    "height_m": np.nan if s.meta.height_m is None else s.meta.height_m,
                    "height_ref": s.meta.height_ref,
                    "value": s.values.to_numpy(),
                    "unit": s.meta.unit,
                    "quality": quality.to_numpy(),
                }
            )
        )
    if not parts:
        return pd.DataFrame(columns=FRAME_COLUMNS)
    return pd.concat(parts, ignore_index=True)[FRAME_COLUMNS]


def save(series: list[Series], stem: Path) -> tuple[Path, Path]:
    """Writes ``<stem>.csv`` (long table) and ``<stem>.json`` (metadata of every series)."""
    stem.parent.mkdir(parents=True, exist_ok=True)
    table, metadata = stem.with_suffix(".csv"), stem.with_suffix(".json")
    frame = to_frame(series)
    frame["time"] = (
        pd.DatetimeIndex(frame["time"]).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        if len(frame)
        else frame["time"]
    )
    frame.to_csv(table, index=False, float_format="%.9g")
    metas = [s.meta.model_dump(mode="json") for s in series]
    metadata.write_text(
        json.dumps({"format": "owstudio-series/1", "series": metas}, indent=1), encoding="utf-8"
    )
    return table, metadata


def load(stem: Path) -> list[Series]:
    """Reads series written by :func:`save`."""
    metas = [
        SeriesMeta.model_validate(m)
        for m in json.loads(stem.with_suffix(".json").read_text(encoding="utf-8"))["series"]
    ]
    frame = pd.read_csv(stem.with_suffix(".csv"), keep_default_na=True)
    frame["time"] = pd.to_datetime(frame["time"], utc=True, format="ISO8601")
    result = []
    for meta in metas:
        rows = frame[
            (frame["dataset"].astype(str) == meta.dataset)
            & (frame["location"].astype(str) == meta.location)
        ]
        rows = rows[rows["variable"] == meta.variable]
        if meta.height_m is None:
            rows = rows[rows["height_m"].isna()]
        else:
            rows = rows[
                np.isclose(rows["height_m"].astype(float), meta.height_m)
                & (rows["height_ref"] == meta.height_ref)
            ]
        values = pd.Series(
            rows["value"].to_numpy(dtype=float), index=pd.DatetimeIndex(rows["time"])
        )
        flags = rows["quality"].to_numpy()
        quality = (
            None if len(flags) == 0 or (flags == -1).all() else pd.Series(flags, index=values.index)
        )
        result.append(Series(meta, values, quality))
    return result
