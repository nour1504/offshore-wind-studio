"""Wind analyses on series: roses, Weibull, distributions, profiles, shear, veer, stability.

Every endpoint takes series references (resolved by the module that reads them: runs,
observations...) and parameters, and returns chart-ready JSON, or one of its tables as CSV
with ?format=csv&table=<name>.
"""

from datetime import datetime
from typing import Any, Literal

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel, Field

from owstudio.api.routes_cases import state
from owstudio.core.analysis import compare as comparing
from owstudio.core.analysis import distribution, profile, rose, stability, weibull
from owstudio.core.analysis.common import (
    AnalysisError,
    Grouping,
    Result,
    Selection,
    by_bins,
    by_sector,
    by_time,
    check_same_timing,
    codes_from,
    describe,
    no_grouping,
    quality_notes,
    stats,
)
from owstudio.core.analysis.wind import Wind
from owstudio.core.i18n import tr
from owstudio.core.series import Series
from owstudio.core.series.sources import SeriesNotFound, SeriesRef, resolve

router = APIRouter()


class SelectionIn(BaseModel):
    start: datetime | None = None
    end: datetime | None = None
    accept_suspect: bool = False

    def build(self) -> Selection:
        return Selection(self.start, self.end, self.accept_suspect)


class WindIn(BaseModel):
    """A wind record: speed (and direction), or earth-relative components u and v."""

    speed: SeriesRef | None = None
    direction: SeriesRef | None = None
    u: SeriesRef | None = None
    v: SeriesRef | None = None


class GroupingIn(BaseModel):
    """Statistics per group: none, direction sector, stability class, value bins, hour or month."""

    kind: Literal["none", "sector", "stability", "bins", "hour", "month"] = "none"
    series: SeriesRef | None = None
    sectors: int = 12
    scheme: str = "gryning2007"
    neutral_band: float = 0.0
    edges: list[float] = Field(default_factory=list)
    utc_offset_hours: float = 0.0


class PowerCurveIn(BaseModel):
    wind_speed: list[float]
    power_kw: list[float]
    name: str = ""


class Common(BaseModel):
    selection: SelectionIn = Field(default_factory=SelectionIn)
    grouping: GroupingIn = Field(default_factory=GroupingIn)


class RoseIn(Common):
    winds: list[WindIn] = Field(min_length=1)
    sectors: int = 12
    speed_bins: list[float] = Field(default_factory=lambda: list(rose.DEFAULT_SPEED_BINS))
    calm: float = 0.0
    power_curve: PowerCurveIn | None = None


class WeibullIn(Common):
    wind: WindIn
    methods: list[str] = Field(default_factory=lambda: ["mle", "moments", "wasp"])
    sectors: int = 0
    min_samples: int = weibull.MIN_SAMPLES
    bin_width: float = 1.0


class SeriesIn(Common):
    series: SeriesRef
    edges: list[float] | None = None
    bins: int = 30
    period: Literal["hour", "day", "month"] = "hour"
    min_availability: float = 0.7
    scheme: str = "gryning2007"
    neutral_band: float = 0.0


class HeightsIn(Common):
    series: list[SeriesRef] = Field(min_length=2)


class CompareIn(Common):
    reference: SeriesRef
    evaluated: SeriesRef
    tolerance_s: float = 0.0


class RichardsonLevelIn(BaseModel):
    """Virtual potential temperature and earth-relative wind components at one height."""

    theta_v: SeriesRef
    u: SeriesRef
    v: SeriesRef


class RichardsonIn(BaseModel):
    lower: RichardsonLevelIn
    upper: RichardsonLevelIn
    selection: SelectionIn = Field(default_factory=SelectionIn)
    classify: bool = False
    neutral_band: float = Field(0.0, ge=0)


def _series(request: Request, ref: SeriesRef) -> Series:
    try:
        return resolve(state(request), ref)
    except SeriesNotFound as error:
        raise HTTPException(404, str(error)) from error


def _wind(request: Request, wind: WindIn) -> Wind:
    if wind.speed is not None:
        return Wind(
            _series(request, wind.speed),
            _series(request, wind.direction) if wind.direction else None,
        )
    if wind.u is not None and wind.v is not None:
        return Wind.from_components(_series(request, wind.u), _series(request, wind.v))
    raise AnalysisError(
        tr(
            "A wind record needs a speed series (and a direction), or the components u and v",
            "Un enregistrement de vent demande une série de vitesse (et une direction), ou les composantes u et v",
        )
    )


def _grouping(request: Request, spec: GroupingIn, data: Series, selection: Selection) -> Grouping:
    if spec.kind == "none":
        return no_grouping()
    if spec.kind in ("hour", "month"):
        return by_time(spec.kind, data.meta, spec.utc_offset_hours)
    if spec.series is None:
        raise AnalysisError(
            tr(
                f"Grouping by {spec.kind} needs a series (direction, stability or binned values)",
                f"Le regroupement par {spec.kind} demande une série (direction, stabilité ou classes de valeurs)",
            )
        )
    source = _series(request, spec.series)
    if spec.kind == "sector":
        return by_sector(source, spec.sectors, selection)
    if spec.kind == "bins":
        return by_bins(source, spec.edges, selection)
    chosen = stability.scheme(spec.scheme, spec.neutral_band)
    classes, _ = stability.classes_of(source, chosen, selection)
    keys = [c.key for c in chosen.classes]
    codes = classes.map(lambda key: keys.index(key) if key in keys else -1).fillna(-1).astype(int)

    return Grouping(
        "stability",
        chosen.title,
        [{"key": c.key, "label": c.label} for c in chosen.classes],
        codes_from(codes),
        notes=list(chosen.notes),
        inputs=[describe(source.meta)],
        timing_of=source,
    )


def _respond(result: Result, format: str, table: str | None) -> Any:
    if format == "csv":
        return PlainTextResponse(
            result.csv(table),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{result.kind}-{table or "table"}.csv"'
            },
        )
    return result.to_json()


def _run(work: Any) -> Any:
    try:
        return work()
    except AnalysisError as error:
        raise HTTPException(422, str(error)) from error


Format = Literal["json", "csv"]


@router.post("/api/analysis/rose", response_model=None)
def analysis_rose(
    request: Request, body: RoseIn, format: Format = "json", table: str | None = None
) -> Response | dict[str, Any]:
    def work() -> Any:
        curve = None
        if body.power_curve:
            curve = rose.PowerCurve(
                tuple(body.power_curve.wind_speed),
                tuple(body.power_curve.power_kw),
                body.power_curve.name,
            )
        winds = [_wind(request, w) for w in body.winds]
        result = rose.wind_rose(
            winds, body.sectors, body.speed_bins, body.calm, curve, body.selection.build()
        )
        return _respond(result, format, table)

    return _run(work)  # type: ignore[no-any-return]


@router.post("/api/analysis/weibull", response_model=None)
def analysis_weibull(
    request: Request, body: WeibullIn, format: Format = "json", table: str | None = None
) -> Response | dict[str, Any]:
    def work() -> Any:
        result = weibull.weibull_analysis(
            _wind(request, body.wind),
            body.methods,
            body.sectors,
            body.min_samples,
            body.bin_width,
            body.selection.build(),
        )
        return _respond(result, format, table)

    return _run(work)  # type: ignore[no-any-return]


@router.post("/api/analysis/histogram", response_model=None)
def analysis_histogram(
    request: Request, body: SeriesIn, format: Format = "json", table: str | None = None
) -> Response | dict[str, Any]:
    def work() -> Any:
        result = distribution.histogram(
            _series(request, body.series), body.edges, body.bins, body.selection.build()
        )
        return _respond(result, format, table)

    return _run(work)  # type: ignore[no-any-return]


@router.post("/api/analysis/grouped", response_model=None)
def analysis_grouped(
    request: Request, body: SeriesIn, format: Format = "json", table: str | None = None
) -> Response | dict[str, Any]:
    """Statistics per group; with grouping hour or month this is the daily or yearly cycle."""

    def work() -> Any:
        selection = body.selection.build()
        data = _series(request, body.series)
        result = distribution.grouped(
            data, _grouping(request, body.grouping, data, selection), selection
        )
        return _respond(result, format, table)

    return _run(work)  # type: ignore[no-any-return]


@router.post("/api/analysis/aggregate", response_model=None)
def analysis_aggregate(
    request: Request, body: SeriesIn, format: Format = "json", table: str | None = None
) -> Response | dict[str, Any]:
    def work() -> Any:
        result = distribution.aggregate(
            _series(request, body.series),
            body.period,
            body.min_availability,
            body.selection.build(),
        )
        return _respond(result, format, table)

    return _run(work)  # type: ignore[no-any-return]


@router.post("/api/analysis/stability", response_model=None)
def analysis_stability(
    request: Request, body: SeriesIn, format: Format = "json", table: str | None = None
) -> Response | dict[str, Any]:
    def work() -> Any:
        result = stability.stability_analysis(
            _series(request, body.series), body.scheme, body.neutral_band, body.selection.build()
        )
        return _respond(result, format, table)

    return _run(work)  # type: ignore[no-any-return]


@router.post("/api/analysis/profile", response_model=None)
def analysis_profile(
    request: Request, body: HeightsIn, format: Format = "json", table: str | None = None
) -> Response | dict[str, Any]:
    def work() -> Any:
        selection = body.selection.build()
        series = [_series(request, ref) for ref in body.series]
        result = profile.profile(
            series, _grouping(request, body.grouping, series[0], selection), selection
        )
        return _respond(result, format, table)

    return _run(work)  # type: ignore[no-any-return]


@router.post("/api/analysis/shear", response_model=None)
def analysis_shear(
    request: Request, body: HeightsIn, format: Format = "json", table: str | None = None
) -> Response | dict[str, Any]:
    def work() -> Any:
        selection = body.selection.build()
        series = [_series(request, ref) for ref in body.series]
        result = profile.shear(
            series, _grouping(request, body.grouping, series[0], selection), selection
        )
        return _respond(result, format, table)

    return _run(work)  # type: ignore[no-any-return]


@router.post("/api/analysis/veer", response_model=None)
def analysis_veer(
    request: Request, body: HeightsIn, format: Format = "json", table: str | None = None
) -> Response | dict[str, Any]:
    def work() -> Any:
        if len(body.series) != 2:
            raise AnalysisError(
                tr(
                    "Wind veer needs the directions at exactly two heights",
                    "La rotation du vent demande les directions à exactement deux hauteurs",
                )
            )
        selection = body.selection.build()
        lower, upper = (_series(request, ref) for ref in body.series)
        result = profile.veer(
            lower, upper, _grouping(request, body.grouping, lower, selection), selection
        )
        return _respond(result, format, table)

    return _run(work)  # type: ignore[no-any-return]


@router.post("/api/analysis/compare", response_model=None)
def analysis_compare(
    request: Request, body: CompareIn, format: Format = "json", table: str | None = None
) -> Response | dict[str, Any]:
    def work() -> Any:
        selection = body.selection.build()
        reference = _series(request, body.reference)
        result = comparing.compare(
            reference,
            _series(request, body.evaluated),
            _grouping(request, body.grouping, reference, selection),
            body.tolerance_s,
            selection,
        )
        return _respond(result, format, table)

    return _run(work)  # type: ignore[no-any-return]


@router.get("/api/analysis/schemes")
def stability_schemes() -> list[dict[str, Any]]:
    """Stability classification schemes with their class limits and references."""
    return [stability.scheme(key).describe() for key in stability.SCHEME_KEYS]


@router.post("/api/analysis/bulk-richardson", response_model=None)
def analysis_bulk_richardson(
    request: Request, body: RichardsonIn, format: Format = "json", table: str | None = None
) -> Response | dict[str, Any]:
    """Derive Ri_b from two resolved vertical levels; it is not a raw WRF output variable."""

    def work() -> Any:
        selection = body.selection.build()
        refs = [
            body.lower.theta_v,
            body.upper.theta_v,
            body.lower.u,
            body.lower.v,
            body.upper.u,
            body.upper.v,
        ]
        values = [_series(request, ref) for ref in refs]
        expected = [
            "virtual_potential_temperature",
            "virtual_potential_temperature",
            "u",
            "v",
            "u",
            "v",
        ]
        if any(
            series.meta.variable != variable
            for series, variable in zip(values, expected, strict=True)
        ):
            raise AnalysisError(
                tr(
                    "Ri_b needs virtual potential temperature, eastward u and northward v at each height",
                    "Ri_b demande la température potentielle virtuelle, u vers l'est et v vers le nord à chaque hauteur",
                )
            )
        check_same_timing(values, "Bulk Richardson number")
        first = values[0].meta
        for series in values[1:]:
            meta = series.meta
            if (
                first.lat is not None
                and first.lon is not None
                and meta.lat is not None
                and meta.lon is not None
            ):
                if abs(first.lat - meta.lat) > 1e-5 or abs(first.lon - meta.lon) > 1e-5:
                    raise AnalysisError(
                        tr(
                            "Ri_b needs all six series at the same horizontal location",
                            "Ri_b demande les six séries au même point horizontal",
                        )
                    )
            elif first.location != meta.location:
                raise AnalysisError(
                    tr(
                        "Ri_b needs all six series at the same horizontal location",
                        "Ri_b demande les six séries au même point horizontal",
                    )
                )
        derived = stability.bulk_richardson(
            values[0], values[1], values[2], values[3], values[4], values[5], selection
        )
        if len(derived.times) == 0:
            raise AnalysisError(
                tr(
                    "No common valid times at both heights for the six required quantities",
                    "Aucun instant valide commun aux deux hauteurs pour les six grandeurs nécessaires",
                )
            )
        ri = derived.values.to_numpy(dtype=float)
        finite = np.isfinite(ri)
        notes = [
            "Ri_b = (g / mean(theta_v)) x (theta_v_upper - theta_v_lower) x (z_upper - z_lower) / ((u_upper - u_lower)^2 + (v_upper - v_lower)^2), g = 9.81 m/s²",
            "Two-level bulk stability describes the layer between the chosen heights; it is not the gradient Richardson number or a direct WRF field",
            "Only common valid times at both heights are used; zero wind shear leaves Ri_b undefined (missing), never infinite",
            *quality_notes(values, selection),
        ]
        classification = None
        tables = {"series": pd.DataFrame({"time": derived.times, "bulk_richardson": ri})}
        if body.classify and finite.any():
            classes = stability.stability_analysis(
                derived, "richardson", body.neutral_band, selection
            )
            classification = classes.to_json()
            tables["classes"] = classes.tables["classes"]
            notes.extend(classes.notes)
        elif body.classify:
            notes.append(
                tr(
                    "No defined Richardson values: classification is unavailable",
                    "Aucune valeur de Richardson définie : classement impossible",
                )
            )
        result = Result(
            kind="bulk-richardson",
            method=derived.meta.method,
            data={
                "unit": "1",
                "times": [t.isoformat() for t in derived.times],
                "values": [float(v) if np.isfinite(v) else None for v in ri],
                "lower_height_m": values[0].meta.height_m,
                "upper_height_m": values[1].meta.height_m,
                "height_ref": first.height_ref,
                "samples": {
                    "paired": len(ri),
                    "valid": int(finite.sum()),
                    "undefined": int((~finite).sum()),
                },
                "statistics": stats(ri, False),
                "classification": classification,
            },
            tables=tables,
            notes=notes,
            inputs=[describe(v.meta) for v in values],
            selection=selection,
        )
        return _respond(result, format, table)

    return _run(work)  # type: ignore[no-any-return]
