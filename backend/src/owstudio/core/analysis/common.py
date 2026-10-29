"""Shared helpers: period and quality selection, unit, timing and height checks, descriptive
statistics, groupings (direction sector, stability class, value bins, hour, month) and results
ready for JSON and CSV."""

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd

from owstudio.core.i18n import tr
from owstudio.core.series import Series, SeriesMeta, circular, regular_frequency, units

PERCENTILES = (1.0, 5.0, 10.0, 25.0, 50.0, 75.0, 90.0, 95.0, 99.0)


class AnalysisError(ValueError):
    """The analysis cannot be done meaningfully; the message says why and is shown to the user."""


def utc(moment: datetime | pd.Timestamp) -> pd.Timestamp:
    """A UTC timestamp; naive times are taken as UTC, like everywhere in the series format."""
    stamp = pd.Timestamp(moment)
    return stamp.tz_localize("UTC") if stamp.tz is None else stamp.tz_convert("UTC")


@dataclass(frozen=True)
class Selection:
    """Which values enter an analysis: a period [start, end) in UTC and the quality accepted."""

    start: datetime | None = None
    end: datetime | None = None
    accept_suspect: bool = False

    def __post_init__(self) -> None:
        if self.start is not None and self.end is not None and utc(self.end) <= utc(self.start):
            raise AnalysisError(
                tr(
                    "The end of the period must be after its start",
                    "La fin de la période doit être après son début",
                )
            )

    def values(self, series: Series) -> pd.Series:
        """Values in the period; those not of good quality (or suspect when accepted) are NaN."""
        values = series.good(self.accept_suspect)
        index = pd.DatetimeIndex(values.index)
        keep = np.ones(len(values), dtype=bool)
        if self.start is not None:
            keep &= np.asarray(index >= utc(self.start))
        if self.end is not None:
            keep &= np.asarray(index < utc(self.end))
        return values[keep]

    def describe(self) -> dict[str, Any]:
        return {
            "start": None if self.start is None else utc(self.start).isoformat(),
            "end": None if self.end is None else utc(self.end).isoformat(),
            "accept_suspect": self.accept_suspect,
        }


def describe(meta: SeriesMeta) -> dict[str, Any]:
    """The metadata shown next to a result, so that every number can be traced to its source."""
    return {
        "key": meta.key,
        "variable": meta.variable,
        "unit": meta.unit,
        "source": meta.source,
        "dataset": meta.dataset,
        "location": meta.location,
        "location_name": meta.location_name,
        "height_m": meta.height_m,
        "height_ref": meta.height_ref,
        "method": meta.method,
        "averaging_s": meta.averaging_s,
        "time_label": meta.time_label,
        "flags": list(meta.flags),
    }


def quality_notes(series: Sequence[Series], selection: Selection) -> list[str]:
    notes = []
    for s in series:
        if s.quality is None:
            notes.append(
                tr(
                    f"{s.meta.key}: no quality flags, all values used as given (unchecked)",
                    f"{s.meta.key} : pas d'indicateurs de qualité, toutes les valeurs sont utilisées telles quelles (non vérifiées)",
                )
            )
        elif selection.accept_suspect:
            notes.append(
                tr(
                    f"{s.meta.key}: values flagged suspect are included",
                    f"{s.meta.key} : les valeurs marquées douteuses sont incluses",
                )
            )
        for flag in s.meta.flags:
            notes.append(f"{s.meta.key}: {flag}")
    return list(dict.fromkeys(notes))


def in_unit(series: Series, values: pd.Series, unit: str, expected: str) -> pd.Series:
    """Values converted to ``unit``; refuses series whose unit cannot be converted."""
    try:
        convert = units.converter(series.meta.unit, unit)
    except units.UnitError as error:
        raise AnalysisError(
            tr(
                f"{series.meta.key} is in {series.meta.unit!r}, which cannot be converted to "
                f"{unit!r}: {expected} expected",
                f"{series.meta.key} est en {series.meta.unit!r}, qui ne se convertit pas en {unit!r} : {expected} attendu",
            )
        ) from error
    return pd.Series(convert(values.to_numpy(dtype=float)), index=values.index)


def speed_values(series: Series, selection: Selection) -> pd.Series:
    """Wind speeds in m s-1 in the selection. Refuses signed components and negative values."""
    if series.meta.variable in ("u", "v", "w") or series.meta.circular:
        raise AnalysisError(
            tr(
                f"{series.meta.key} is {series.meta.variable!r}, not a wind speed (a speed is "
                "never negative and has no direction)",
                f"{series.meta.key} est {series.meta.variable!r}, pas une vitesse de vent (une vitesse n'est jamais négative et n'a pas de direction)",
            )
        )
    values = in_unit(series, selection.values(series), "m s-1", "a wind speed")
    negative = int((values < 0).sum())
    if negative:
        raise AnalysisError(
            tr(
                f"{series.meta.key} has {negative} negative wind speeds: this is not a wind speed "
                "series, or these values (often missing-value codes such as -999) must be flagged "
                "bad first",
                f"{series.meta.key} a {negative} vitesses de vent négatives : ce n'est pas une série de vitesse, ou ces valeurs (souvent des codes de valeur manquante comme -999) doivent d'abord être marquées mauvaises",
            )
        )
    return values


def direction_values(series: Series, selection: Selection) -> pd.Series:
    """Meteorological directions in degrees, in [0, 360). Refuses non-directional series."""
    if not series.meta.circular:
        raise AnalysisError(
            tr(
                f"{series.meta.key} is {series.meta.variable!r}, not a wind direction",
                f"{series.meta.key} est {series.meta.variable!r}, pas une direction du vent",
            )
        )
    values = in_unit(series, selection.values(series), "deg", "a direction in degrees")
    outside = int(((values < 0) | (values > 360)).sum())
    if outside:
        raise AnalysisError(
            tr(
                f"{series.meta.key} has {outside} directions outside [0, 360] degrees (missing-value "
                "codes must be flagged bad first)",
                f"{series.meta.key} a {outside} directions hors de [0, 360] degrés (les codes de valeur manquante doivent d'abord être marqués mauvais)",
            )
        )
    return pd.Series(circular.wrap(values.to_numpy()), index=values.index)


def sampling_step(series: Series) -> float | None:
    """Nominal spacing of the values in seconds: from the metadata, else from the times."""
    if series.meta.frequency_s:
        return float(series.meta.frequency_s)
    return regular_frequency(series.times)


def label_shift(meta: SeriesMeta, to: str) -> pd.Timedelta:
    """Offset to add to the time stamps of a series to reach the ``to`` position ("start",
    "centre" or "end") of each averaging period; zero for instantaneous values."""
    if meta.averaging_s <= 0 or meta.time_label == "instant":
        return pd.Timedelta(0)
    position = {"start": 0.0, "centre": 0.5, "end": 1.0}
    return pd.Timedelta(seconds=meta.averaging_s * (position[to] - position[meta.time_label]))


def timing(meta: SeriesMeta) -> str:
    if meta.averaging_s <= 0:
        return tr("instantaneous values", "valeurs instantanées")
    return tr(
        f"{meta.averaging_s:g} s averages stamped at the {meta.time_label} of the period",
        f"moyennes sur {meta.averaging_s:g} s horodatées au {meta.time_label} de la période",
    )


def check_same_timing(series: Sequence[Series], purpose: str) -> None:
    """Refuses to pair values on time stamps when the series do not sample time the same way."""
    first = series[0].meta
    for s in series[1:]:
        if (s.meta.averaging_s, s.meta.time_label) != (first.averaging_s, first.time_label):
            raise AnalysisError(
                tr(
                    f"{purpose}: {first.key} has {timing(first)} but {s.meta.key} has "
                    f"{timing(s.meta)}. Values are paired on equal time stamps, so both must have "
                    "the same averaging and time label: aggregate or relabel one of them first",
                    f"{purpose} : {first.key} a {timing(first)} mais {s.meta.key} a {timing(s.meta)}. Les valeurs sont appariées sur des horodatages égaux : les deux doivent avoir la même moyenne et la même convention d'horodatage ; agrégez ou réétiquetez d'abord l'une d'elles",
                )
            )


def check_heights(series: Sequence[Series], purpose: str) -> None:
    """Refuses series without height and mixes of above-ground and above-sea-level heights."""
    for s in series:
        if s.meta.height_m is None or s.meta.height_ref == "surface":
            raise AnalysisError(
                tr(
                    f"{purpose}: {s.meta.key} has no height",
                    f"{purpose} : {s.meta.key} n'a pas de hauteur",
                )
            )
    refs = sorted({s.meta.height_ref for s in series})
    if len(refs) > 1:
        raise AnalysisError(
            tr(
                f"{purpose}: heights mix references ({' and '.join(refs)}). Above ground (agl) and "
                "above mean sea level (asl) heights are not comparable without the surface "
                "elevation: use one reference for every series",
                f"{purpose} : les hauteurs mélangent des références ({' et '.join(refs)}). Les hauteurs au-dessus du sol (agl) et au-dessus du niveau moyen de la mer (asl) ne se comparent pas sans l'altitude de la surface : utilisez une seule référence pour toutes les séries",
            )
        )


def aligned(columns: dict[str, pd.Series]) -> pd.DataFrame:
    """Columns joined on equal time stamps (inner join); NaN values are kept."""
    frame = pd.concat(columns, axis=1, join="inner")
    frame.columns = list(columns)
    return frame.sort_index()


def sector_labels(sectors: int) -> list[dict[str, Any]]:
    """Sector 0 centred on north, clockwise; bounds in degrees."""
    width = 360.0 / sectors
    result = []
    for i in range(sectors):
        centre = i * width
        lower, upper = (centre - width / 2.0) % 360.0, (centre + width / 2.0) % 360.0
        result.append(
            {
                "key": i,
                "sector": i,
                "centre_deg": centre,
                "from_deg": lower,
                "to_deg": upper,
                "label": f"{centre:g}° ({lower:g}°–{upper:g}°)",
            }
        )
    return result


def check_sectors(sectors: int) -> None:
    if not 4 <= sectors <= 72:
        raise AnalysisError(
            tr(
                "The number of direction sectors must be between 4 and 72",
                "Le nombre de secteurs de direction doit être entre 4 et 72",
            )
        )


def check_edges(edges: Sequence[float], what: str) -> np.ndarray:
    e = np.asarray(edges, dtype=float)
    if e.size < 2 or not np.all(np.isfinite(e)) or np.any(np.diff(e) <= 0):
        raise AnalysisError(
            tr(
                f"{what}: at least two finite, strictly increasing bin edges needed",
                f"{what} : il faut au moins deux bornes de classes finies et strictement croissantes",
            )
        )
    if e.size > 1001:
        raise AnalysisError(tr(f"{what}: at most 1000 bins", f"{what} : 1000 classes au plus"))
    return e


# ------------------------------------------------------------- statistics


def linear_stats(values: np.ndarray) -> dict[str, Any]:
    """Count, mean, sample standard deviation (n - 1), extremes and percentiles of the finite
    values."""
    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x)]
    result: dict[str, Any] = {"count": int(x.size)}
    if x.size == 0:
        result.update({"mean": None, "std": None, "min": None, "max": None})
        result.update({f"p{q:g}": None for q in PERCENTILES})
        return result
    result.update(
        {
            "mean": float(np.mean(x)),
            "std": float(np.std(x, ddof=1)) if x.size > 1 else None,
            "min": float(np.min(x)),
            "max": float(np.max(x)),
        }
    )
    for q, v in zip(PERCENTILES, np.percentile(x, PERCENTILES), strict=True):
        result[f"p{q:g}"] = float(v)
    return result


def circular_stats(directions: np.ndarray) -> dict[str, Any]:
    """Count, circular mean of unit vectors, mean resultant length R and Yamartino standard
    deviation of directions in degrees."""
    d = np.asarray(directions, dtype=float)
    d = d[np.isfinite(d)]
    if d.size == 0:
        return {"count": 0, "mean": None, "resultant_length": None, "std": None}
    return {
        "count": int(d.size),
        "mean": circular.mean(d),
        "resultant_length": circular.resultant_length(d),
        "std": circular.std_yamartino(d),
    }


def stats(values: np.ndarray, is_circular: bool) -> dict[str, Any]:
    return circular_stats(values) if is_circular else linear_stats(values)


# ------------------------------------------------------------- groupings

Codes = Callable[[pd.DatetimeIndex], np.ndarray]


@dataclass
class Grouping:
    """Assigns each time to a group (direction sector, stability class, value bin, hour or
    month), so that any statistic can be computed per group."""

    key: str
    title: str
    groups: list[dict[str, Any]]
    # Position in ``groups`` of the group of each time stamp, -1 where it is unknown
    codes: Codes
    notes: list[str] = field(default_factory=list)
    inputs: list[dict[str, Any]] = field(default_factory=list)
    # Series whose time stamps the grouped values must share (sector, class and bin series)
    timing_of: Series | None = None


def no_grouping() -> Grouping:
    return Grouping(
        "none",
        tr("All values", "Toutes les valeurs"),
        [{"key": "all", "label": tr("All", "Tout")}],
        lambda index: np.zeros(len(index), dtype=int),
    )


def codes_from(labels: pd.Series) -> Codes:
    """Group positions of given times from a series of positions (exact time stamps)."""

    def codes(index: pd.DatetimeIndex) -> np.ndarray:
        result: np.ndarray = labels.reindex(index, fill_value=-1).to_numpy(dtype=int)
        return result

    return codes


def by_sector(direction: Series, sectors: int, selection: Selection) -> Grouping:
    """Groups by the direction sector of a direction series (sector 0 centred on north)."""
    check_sectors(sectors)
    values = direction_values(direction, selection)
    codes = pd.Series(circular.sector(values.to_numpy(), sectors), index=values.index)
    return Grouping(
        "sector",
        tr(
            f"Direction sectors of {direction.meta.key}",
            f"Secteurs de direction de {direction.meta.key}",
        ),
        sector_labels(sectors),
        codes_from(codes),
        inputs=[describe(direction.meta)],
        timing_of=direction,
    )


def by_bins(series: Series, edges: Sequence[float], selection: Selection) -> Grouping:
    """Groups by bins [lower, upper) of the values of a series (wind speed bins, for example);
    values outside the edges belong to no group."""
    e = check_edges(edges, tr("Bins", "Classes"))
    values = selection.values(series)
    x = values.to_numpy(dtype=float)
    index = np.searchsorted(e, x, side="right") - 1
    inside = np.isfinite(x) & (index >= 0) & (index < e.size - 1)
    codes = pd.Series(np.where(inside, index, -1), index=values.index)
    unit = series.meta.unit
    groups = [
        {"key": i, "lower": float(e[i]), "upper": float(e[i + 1]),
         "label": f"{e[i]:g}–{e[i + 1]:g} {unit}"}
        for i in range(e.size - 1)
    ]  # fmt: skip
    return Grouping(
        "bins",
        tr(f"Bins of {series.meta.key}", f"Classes de {series.meta.key}"),
        groups,
        codes_from(codes),
        notes=[
            tr(
                f"Bins of {series.meta.key} include their lower edge and exclude their upper one",
                f"Les classes de {series.meta.key} incluent leur borne inférieure et excluent la supérieure",
            )
        ],
        inputs=[describe(series.meta)],
        timing_of=series,
    )


def by_time(key: str, data: SeriesMeta, utc_offset_hours: float = 0.0) -> Grouping:
    """Groups by hour of day (0-23) or calendar month (1-12) of the centre of each averaging
    period of ``data``, at a fixed offset from UTC."""
    if not -14 <= utc_offset_hours <= 14:
        raise AnalysisError(
            tr(
                "The offset from UTC must be between -14 and +14 hours",
                "Le décalage par rapport à UTC doit être entre -14 et +14 heures",
            )
        )
    offset = pd.Timedelta(hours=utc_offset_hours) + label_shift(data, "centre")
    # Written the same in both languages
    shift = f"{utc_offset_hours:+g} h"  # internal
    where = "UTC" if utc_offset_hours == 0 else f"UTC{shift}"
    if key == "hour":
        if data.averaging_s > 3600:
            raise AnalysisError(
                tr(
                    f"{data.key} holds {data.averaging_s / 3600:g} h averages: they cannot be "
                    "split by hour of day",
                    f"{data.key} contient des moyennes sur {data.averaging_s / 3600:g} h : elles ne se répartissent pas par heure du jour",
                )
            )
        groups = [{"key": h, "label": f"{h:02d}:00–{h + 1:02d}:00 {where}"} for h in range(24)]

        def hours(index: pd.DatetimeIndex) -> np.ndarray:
            return np.asarray((index + offset).hour, dtype=int)

        return Grouping(
            "hour", tr(f"Hour of day ({where})", f"Heure du jour ({where})"), groups, hours
        )
    if key == "month":
        if data.averaging_s > 28 * 86400:
            raise AnalysisError(
                tr(
                    f"{data.key} holds averages longer than a month",
                    f"{data.key} contient des moyennes de plus d'un mois",
                )
            )
        names = tr(
            "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec",
            "janv. févr. mars avr. mai juin juil. août sept. oct. nov. déc.",
        ).split()
        groups = [{"key": m + 1, "label": names[m]} for m in range(12)]

        def months(index: pd.DatetimeIndex) -> np.ndarray:
            return np.asarray((index + offset).month, dtype=int) - 1

        return Grouping("month", tr(f"Calendar month ({where})", f"Mois ({where})"), groups, months)
    raise AnalysisError(
        tr(
            f"Unknown time grouping {key!r} (hour or month)",
            f"Regroupement temporel inconnu {key!r} (heure ou mois)",
        )
    )


def group_masks(grouping: Grouping, index: pd.DatetimeIndex) -> tuple[list[np.ndarray], int]:
    """A boolean mask per group over ``index``, and the count of times in no group."""
    codes = grouping.codes(index)
    return [codes == i for i in range(len(grouping.groups))], int(np.sum(codes < 0))


def check_grouping_timing(grouping: Grouping, data: Series, purpose: str) -> None:
    if grouping.timing_of is not None:
        check_same_timing([data, grouping.timing_of], purpose)


# ------------------------------------------------------------- results


def jsonable(value: Any) -> Any:
    """Plain JSON values: NaN and infinities become null, numpy and pandas types plain Python."""
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, np.ndarray):
        return [jsonable(v) for v in value.tolist()]
    if value is None or value is pd.NaT or value is pd.NA:
        return None
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.datetime64):
        return None if np.isnat(value) else pd.Timestamp(value).tz_localize("UTC").isoformat()
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


@dataclass
class Result:
    """Chart-ready data, the tables offered as CSV, the method used and the caveats."""

    kind: str
    method: str
    data: dict[str, Any]
    tables: dict[str, pd.DataFrame]
    notes: list[str] = field(default_factory=list)
    inputs: list[dict[str, Any]] = field(default_factory=list)
    selection: Selection = field(default_factory=Selection)

    def to_json(self) -> dict[str, Any]:
        content = {
            "kind": self.kind,
            "method": self.method,
            "notes": list(dict.fromkeys(self.notes)),
            "inputs": self.inputs,
            "selection": self.selection.describe(),
            "tables": list(self.tables),
            **self.data,
        }
        result: dict[str, Any] = jsonable(content)
        return result

    def csv(self, table: str | None = None) -> str:
        """One of the tables as CSV text (the first one by default)."""
        if not self.tables:
            raise AnalysisError(
                tr(
                    "This result has no table to export",
                    "Ce résultat n'a pas de tableau à exporter",
                )
            )
        name = table or next(iter(self.tables))
        if name not in self.tables:
            raise AnalysisError(
                tr(
                    f"No table {name!r} in this result (available: {', '.join(self.tables)})",
                    f"Pas de tableau {name!r} dans ce résultat (disponibles : {', '.join(self.tables)})",
                )
            )
        frame = self.tables[name].copy()
        for column in frame.columns:
            if isinstance(frame[column].dtype, pd.DatetimeTZDtype):
                frame[column] = frame[column].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        text: str = frame.to_csv(index=False, float_format="%.6g", lineterminator="\n")
        return text


def decimate(count: int, limit: int) -> np.ndarray:
    """Indices of at most ``limit`` of ``count`` items, drawn at random with a fixed seed (so
    that a display is reproducible) and kept in their original order."""
    if count <= limit:
        return np.arange(count)
    rng = np.random.default_rng(0)
    return np.sort(rng.choice(count, size=limit, replace=False))
