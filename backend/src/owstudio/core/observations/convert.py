"""From a table read from an observation file to series in the common format, as the mapping says:
UTC times (local times with daylight saving converted explicitly), canonical variables and units,
heights above ground or sea level, direction convention, quality flags and missing codes."""

import re
from datetime import timedelta, timezone

import numpy as np
import pandas as pd

from owstudio.core.i18n import tr
from owstudio.core.observations.mapping import ColumnSpec, Flag, Mapping, is_direction, readiness
from owstudio.core.series import (
    QUALITY_BAD,
    QUALITY_GOOD,
    QUALITY_MISSING,
    QUALITY_SUSPECT,
    VARIABLES,
    Series,
    SeriesMeta,
    regular_frequency,
    units,
)

OFFSET = re.compile(r"^(?:UTC|GMT)?\s*([+-])(\d{1,2})(?::?(\d{2}))?$", re.IGNORECASE)


class ConversionError(ValueError):
    """The mapping cannot be applied; the flags say why."""

    def __init__(self, flags: list[Flag]) -> None:
        super().__init__("; ".join(f.message for f in flags))
        self.flags = flags


def parse_times(frame: pd.DataFrame, mapping: Mapping, flags: list[Flag]) -> pd.DatetimeIndex:
    """Time stamps in UTC; rows whose time cannot be read become NaT (reported)."""
    spec = mapping.time
    text = frame[spec.columns].astype(str).agg(" ".join, axis=1).str.strip()
    if spec.format in ("unix", "unix_ms"):
        numbers = pd.to_numeric(text, errors="coerce")
        epoch = pd.to_datetime(numbers, unit="s" if spec.format == "unix" else "ms", utc=True)
        return pd.DatetimeIndex(epoch)
    if spec.format == "excel":
        days = pd.to_numeric(text.str.replace(",", ".", regex=False), errors="coerce")
        naive = pd.Timestamp("1899-12-30") + pd.to_timedelta(days, unit="D")
    elif spec.format in ("", "ISO8601"):
        naive = pd.to_datetime(
            text, format="ISO8601" if spec.format else "mixed", errors="coerce", dayfirst=False
        )
        if not spec.format:
            # A day-first reading that gives other dates is an ambiguity the user must settle;
            # year-first dates (ISO 8601, 2025-10-01) are always year-month-day
            other = pd.to_datetime(text, format="mixed", errors="coerce", dayfirst=True)
            year_first = text.str.match(r"\d{4}[-/.]\d{1,2}[-/.]\d{1,2}")
            if (~year_first & other.notna() & naive.notna() & (other != naive)).any():
                flags.append(
                    Flag(
                        code="date_order_ambiguous",
                        message=tr(
                            "Dates can be read day-first or month-first: give the time format",
                            "Les dates peuvent se lire jour en premier ou mois en premier : indiquez le format des dates",
                        ),
                        severity="error",
                    )
                )
    else:
        naive = pd.to_datetime(text, format=spec.format, errors="coerce")
    stamps = pd.DatetimeIndex(naive)
    if stamps.tz is not None:
        return stamps.tz_convert("UTC")
    zone = (spec.timezone or "").strip()
    match = OFFSET.match(zone)
    if zone.upper() in ("UTC", "GMT", "Z"):
        return stamps.tz_localize("UTC")
    if match:
        sign = 1 if match.group(1) == "+" else -1
        offset = timedelta(hours=int(match.group(2)), minutes=int(match.group(3) or 0)) * sign
        return stamps.tz_localize(timezone(offset)).tz_convert("UTC")
    choices: dict[str, str | bool] = {
        "reject": "raise",
        "infer": "infer",
        "earlier": True,
        "later": False,
        "drop": "NaT",
    }
    ambiguous = choices[spec.ambiguous]
    nonexistent = "raise" if spec.nonexistent == "reject" else "NaT"
    try:
        local = stamps.tz_localize(zone, ambiguous=ambiguous, nonexistent=nonexistent)  # type: ignore[arg-type]
    except Exception as error:  # noqa: BLE001 - pandas raises several kinds for DST problems
        flags.append(
            Flag(
                code="dst_ambiguity",
                message=tr(
                    f"Local times around a daylight saving change cannot be placed in UTC: {error}. Choose how to treat them in the mapping",
                    f"Les heures locales autour d'un changement d'heure ne peuvent pas être placées en UTC : {error}. Choisissez comment les traiter dans la correspondance",
                ),
                severity="error",
            )
        )
        return pd.DatetimeIndex([pd.NaT] * len(stamps), tz="UTC")
    return local.tz_convert("UTC")


def numbers(values: pd.Series, decimal: str, missing: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """Floats and a mask of the cells marked missing."""
    text = values.astype(str).str.strip()
    is_missing = text.isin(missing) | (text == "")
    if decimal == ",":
        text = text.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    parsed = pd.to_numeric(text.where(~is_missing), errors="coerce").to_numpy(dtype=float)
    return parsed, is_missing.to_numpy()


def quality_codes(frame: pd.DataFrame, spec: ColumnSpec, n: int) -> np.ndarray | None:
    if spec.quality is None:
        return None
    codes = frame[spec.quality.column].astype(str).str.strip()
    other = {"good": QUALITY_GOOD, "suspect": QUALITY_SUSPECT, "bad": QUALITY_BAD}[
        spec.quality.other
    ]
    result = np.full(n, other, dtype="int8")
    result[codes.isin(spec.quality.good).to_numpy()] = QUALITY_GOOD
    result[codes.isin(spec.quality.suspect).to_numpy()] = QUALITY_SUSPECT
    result[codes.isin(spec.quality.bad).to_numpy()] = QUALITY_BAD
    return result


def variable_name(spec: ColumnSpec) -> str:
    """Canonical variable, with the statistic appended when it is not the mean (wind_speed_max)."""
    if (
        spec.statistic in ("mean", "sample")
        or spec.variable.endswith(("_std", "_max", "_min"))
        or spec.variable in ("gust", "turbulence_intensity")
    ):
        return spec.variable
    return f"{spec.variable}_{spec.statistic}"


def convert(
    frame: pd.DataFrame,
    mapping: Mapping,
    dataset: str,
    decimal: str = ".",
    file_units: dict[str, str] | None = None,
) -> tuple[list[Series], list[Flag]]:
    """Series of every mapped column. Raises ConversionError when the mapping is incomplete."""
    errors = readiness(mapping)
    if errors:
        raise ConversionError(errors)
    flags: list[Flag] = []
    times = parse_times(frame, mapping, flags)
    if any(f.severity == "error" for f in flags):
        raise ConversionError([f for f in flags if f.severity == "error"])
    unreadable = int(pd.isna(times).sum())
    if unreadable:
        flags.append(
            Flag(
                code="time_unreadable",
                message=tr(
                    f"{unreadable} rows have a time that cannot be read and are left out",
                    f"{unreadable} lignes ont une date illisible et sont écartées",
                ),
            )
        )
    station = mapping.station
    keep = np.asarray(~pd.isna(times))
    index = pd.DatetimeIndex(times[keep])
    duplicated = int(index.duplicated().sum())
    if duplicated:
        flags.append(
            Flag(
                code="duplicate_times",
                message=tr(
                    f"{duplicated} duplicated times: the first value of each is kept",
                    f"{duplicated} dates en double : la première valeur de chacune est gardée",
                ),
            )
        )
    result = []
    direction_columns = [s for s in mapping.columns if is_direction(s.variable)]
    for spec in mapping.columns:
        values, missing = numbers(
            frame[spec.column], decimal, [*mapping.file.missing, *spec.missing]
        )
        unreadable_cells = int(np.sum(np.isnan(values) & ~missing))
        if unreadable_cells:
            flags.append(
                Flag(
                    code="values_unreadable",
                    message=tr(
                        f"{unreadable_cells} cells of {spec.column} are not numbers",
                        f"{unreadable_cells} cellules de {spec.column} ne sont pas des nombres",
                    ),
                    column=spec.column,
                )
            )
        quality = quality_codes(frame, spec, len(values))
        if quality is not None:
            quality = np.where(np.isnan(values), QUALITY_MISSING, quality).astype("int8")
        unit = spec.unit.strip() or (file_units or {}).get(spec.column, "")
        column_flags: list[str] = []
        if spec.variable in VARIABLES and unit:
            target = VARIABLES[spec.variable].unit
            try:
                values = units.convert(values, unit, target)
            except units.UnitError as error:
                raise ConversionError(
                    [
                        Flag(
                            code="unit_unknown",
                            message=f"{spec.column}: {error}",
                            column=spec.column,
                            severity="error",
                        )
                    ]
                ) from error
            if units.canonical(unit) != target:
                column_flags.append(f"converted from {unit} to {target}")
            unit = target
        if is_direction(spec.variable):
            if spec.direction is None:
                column_flags.append(
                    "direction convention not given: taken as meteorological (from)"
                )
            elif spec.direction == "to":
                values = values + 180.0
                column_flags.append("converted from 'blowing to' to 'coming from' (+180°)")
            if spec.direction_offset_deg:
                values = values + spec.direction_offset_deg
                column_flags.append(f"direction offset {spec.direction_offset_deg:+g}° applied")
            values = np.mod(values, 360.0)
        reference = spec.height_reference or station.height_reference
        height = spec.height_m
        height_ref = "surface" if height is None else ("agl" if reference == "agl" else "asl")
        if height is not None and reference == "platform":
            assert station.platform_elevation_m is not None
            height = height + station.platform_elevation_m
            column_flags.append(
                f"height above the platform + {station.platform_elevation_m:g} m platform elevation = height above mean sea level"
            )
        if (
            station.distortion_sectors
            and spec.variable
            in ("wind_speed", "wind_direction", "wind_speed_std", "turbulence_intensity", "gust")
            and direction_columns
        ):
            nearest = min(
                direction_columns, key=lambda d: abs((d.height_m or 0) - (spec.height_m or 0))
            )
            directions, _ = numbers(frame[nearest.column], decimal, mapping.file.missing)
            disturbed = np.array(
                [
                    any(s.contains(d) for s in station.distortion_sectors)
                    if np.isfinite(d)
                    else False
                    for d in directions
                ]
            )
            if disturbed.any():
                base = (
                    quality
                    if quality is not None
                    else np.full(len(values), QUALITY_GOOD, dtype="int8")
                )
                quality = np.where(
                    disturbed & (base == QUALITY_GOOD), QUALITY_SUSPECT, base
                ).astype("int8")
                column_flags.append(
                    f"{int(disturbed.sum())} values in flow distortion sectors flagged suspect (direction from {nearest.column})"
                )
        averaging = (
            spec.averaging_s if spec.averaging_s is not None else (mapping.time.averaging_s or 0.0)
        )
        series_values = pd.Series(values[keep], index=index)
        series_quality = None if quality is None else pd.Series(quality[keep], index=index)
        meta = SeriesMeta(
            variable=variable_name(spec),
            unit=unit,
            source="observation",
            dataset=dataset,
            location=station.id,
            location_name=station.name or station.id,
            lat=station.lat,
            lon=station.lon,
            height_m=height,
            height_ref=height_ref,
            method=tr(
                f"measured ({station.instrument}{', ' + spec.sensor if spec.sensor else ''}), column {spec.column}, {spec.statistic}",
                f"mesuré ({station.instrument}{', ' + spec.sensor if spec.sensor else ''}), colonne {spec.column}, {spec.statistic}",
            ),
            frequency_s=regular_frequency(index),
            averaging_s=float(averaging),
            time_label=mapping.time.label or "instant",
            original_timezone=mapping.time.timezone or "UTC",
            description=station.description,
            flags=column_flags,
            extra={
                "column": spec.column,
                "statistic": spec.statistic,
                "instrument": station.instrument,
            },
        )
        result.append(Series(meta, series_values, series_quality))
    if result and result[0].meta.frequency_s is None:
        flags.append(
            Flag(
                code="irregular_steps",
                message=tr("The time steps are irregular", "Les pas de temps sont irréguliers"),
                severity="info",
            )
        )
    return result, flags
