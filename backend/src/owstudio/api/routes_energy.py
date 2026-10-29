"""Energy produced over the simulated period, per turbine and per farm, and wake losses."""

from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response

from owstudio.api.routes_cases import state
from owstudio.api.routes_results import localised
from owstudio.core.case.model import Case
from owstudio.core.energy.power_curve import binned_curve
from owstudio.core.energy.production import EnergyError, sites
from owstudio.core.energy.summary import energy_series, run_energy
from owstudio.core.i18n import current, tr
from owstudio.core.postproc.results import remember
from owstudio.core.postproc.windowed import history_paths
from owstudio.core.series.sources import SeriesNotFound, SeriesRef, resolve
from owstudio.core.storage import outputs_stamp, stage_folder

router = APIRouter()


def run_with_outputs(request: Request, case_id: str, run: str | None) -> tuple[Path, Case]:
    """The run folder (the one asked for, or the latest with history files) and its case."""
    app = state(request)
    app.workspace.load(case_id)
    ids = [run] if run else list(reversed(app.storage.run_ids(case_id)))
    for run_id in ids:
        try:
            root = app.storage.run(case_id, run_id).root
        except KeyError as error:
            raise HTTPException(404, tr("Unknown run", "Calcul inconnu")) from error
        main = root / "outputs" / "main"
        if history_paths(main):
            snapshot = main / "case.yaml" if (main / "case.yaml").exists() else root / "case.yaml"
            return root, Case.from_yaml(snapshot)
        if run:
            raise HTTPException(
                404, tr("This run has no results", "Ce calcul n'a pas de résultats")
            )
    raise HTTPException(
        404,
        tr(
            "No results yet: run the case first",
            "Pas encore de résultats : lancez d'abord le calcul",
        ),
    )


@router.get("/api/cases/{case_id}/energy")
def energy_summary(
    request: Request,
    case_id: str,
    run: str | None = None,
    method: Literal["auto", "wrf", "curve"] = "auto",
) -> dict[str, Any]:
    root, case = run_with_outputs(request, case_id, run)
    try:
        return {"run_id": root.name, **energy_of(root, case, method)}
    except EnergyError as error:
        raise HTTPException(422, str(error)) from error


def energy_of(root: Path, case: Case, method: Literal["auto", "wrf", "curve"]) -> dict[str, Any]:
    """The energy summary of a run, kept once computed (a new import is a new key)."""
    summary: dict[str, Any] = remember(
        ("energy", *outputs_stamp(root), method, current()), lambda: run_energy(root, case, method)
    )
    return summary


@router.get("/api/cases/{case_id}/energy/series", response_model=None)
def energy_over_time(
    request: Request, case_id: str, run: str | None = None, method: Literal["auto", "wrf", "curve"] = "auto",
    period: Literal["raw", "hour", "day", "month"] = "raw", format: Literal["json", "csv"] = "json",
    turbine: str | None = None,
    cell: str | None = None,
    farm: str | None = None,
) -> Response | dict[str, Any]:  # fmt: skip
    """Power per farm (MW) at the output times, or energy (MWh) per UTC hour, day or month, with
    the reference without wakes when the run has a control run."""
    root, case = run_with_outputs(request, case_id, run)
    try:
        kept: pd.DataFrame = remember(
            ("energy_series", *outputs_stamp(root), method, period, turbine, cell, farm, current()),
            lambda: energy_series(root, case, method, period, turbine, cell, farm),
        )
        frame = kept.copy()
    except EnergyError as error:
        raise HTTPException(422, str(error)) from error
    if format == "csv":
        unit = "mw" if period == "raw" else "mwh"
        return PlainTextResponse(
            localised(frame).to_csv(
                index=False, float_format="%.6g", date_format="%Y-%m-%dT%H:%M:%SZ"
            ),
            media_type="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{case_id}-{period}-{unit}.csv"'
            },
        )
    time_column = frame.columns[0]
    return {
        "run_id": root.name,
        **{str(k): v for k, v in frame.attrs.items()},
        "unit": "MW" if period == "raw" else "MWh",
        "times": [t.isoformat() for t in frame[time_column]],
        "series": {
            c: [None if pd.isna(v) else float(v) for v in frame[c]] for c in frame.columns[1:]
        },
    }


@router.get("/api/cases/{case_id}/energy/sectors")
def energy_by_direction(
    request: Request,
    case_id: str,
    turbine: str,
    run: str | None = None,
    sectors: int = 12,
) -> dict[str, Any]:
    """Energy (MWh) of one turbine per wind direction sector, with and without wakes, from the
    tslist outputs: for each 10-minute interval, the mean power of the turbine over its model
    steps and the mean wind direction at its hub over the same steps (from the mean u and v); the energy of the
    interval, mean power x 10 min, goes to the sector of that direction. Each run is sorted by its
    own wind: the run with turbines by the wind present at the turbine, the run without turbines
    (the reference without wakes) by its free wind."""
    if sectors not in (4, 8, 12, 16, 18, 24, 36):
        raise HTTPException(
            422, tr("Unsupported number of sectors", "Nombre de secteurs non pris en charge")
        )
    root, case = run_with_outputs(request, case_id, run)
    site = next((s for s in sites(case) if s.label == turbine), None)
    if site is None:
        raise HTTPException(
            422, tr(f"Unknown turbine {turbine!r}", f"Éolienne inconnue {turbine!r}")
        )
    has_control = bool(history_paths(stage_folder(root, "control")))

    def ten_minutes(stage: str, variable: str) -> Any:
        ref = SeriesRef(
            kind="run", case_id=case_id, run_id=root.name, stage=stage, variable=variable,
            location=turbine, height_m=site.hub_height_m, reader="tslist", options={"averaging_s": 600},
        )  # fmt: skip
        return resolve(state(request), ref)

    def utc(index: Any) -> pd.DatetimeIndex:
        stamps = pd.DatetimeIndex(index)
        return stamps.tz_convert("UTC").tz_localize(None) if stamps.tz is not None else stamps

    try:
        power = ten_minutes("main", "power")
        free_power = ten_minutes("control", "power") if has_control else None
        direction = ten_minutes("main", "wind_direction")
        free_direction = ten_minutes("control", "wind_direction") if has_control else None
    except SeriesNotFound as error:
        raise HTTPException(422, str(error)) from error
    # Energy of each 10-minute interval (MWh): mean power (MW) x 1/6 h
    energy = pd.Series(power.values.to_numpy(dtype=float) / 6, index=utc(power.values.index))
    reference = (
        None
        if free_power is None
        else pd.Series(
            free_power.values.to_numpy(dtype=float) / 6, index=utc(free_power.values.index)
        )
    )
    width = 360.0 / sectors

    def sector_of(series: Any, index: pd.DatetimeIndex) -> np.ndarray:
        angles = (
            pd.Series(series.values.to_numpy(dtype=float), index=utc(series.values.index))
            .groupby(level=0)
            .first()
            .reindex(index)
            .to_numpy(dtype=float)
        )
        return np.where(
            np.isfinite(angles), np.floor(((angles + width / 2) % 360.0) / width), -1
        ).astype(int)

    codes = sector_of(direction, pd.DatetimeIndex(energy.index))
    free = reference
    free_codes = (
        None
        if free is None or free_direction is None
        else sector_of(free_direction, pd.DatetimeIndex(free.index))
    )

    rows = []
    for k in range(sectors):
        mask = codes == k
        main_mwh = float(energy[mask].sum())
        free_mwh = (
            None if free is None or free_codes is None else float(free[free_codes == k].sum())
        )
        rows.append({
            "sector": k,
            "centre_deg": k * width,
            "hours": float(mask.sum()) / 6,
            "energy_mwh": main_mwh,
            "reference_mwh": free_mwh,
            "loss_pct": 100 * (1 - main_mwh / free_mwh) if free_mwh else None,
        })  # fmt: skip
    unknown = codes < 0
    return {
        "run_id": root.name,
        "method_text": tr(
            "10-minute means of the tslist outputs: turbine power (Fitch formula) and wind direction at the hub; energy = mean power x 10 min",
            "moyennes sur 10 min des sorties tslist : puissance de l'éolienne (formule de Fitch) et direction du vent au moyeu ; énergie = puissance moyenne x 10 min",
        ),
        "turbines_approximate": False,
        "direction": f"{direction.meta.method} ({direction.meta.dataset})",
        "sectors": rows,
        "energy_mwh": float(energy.sum()),
        "reference_mwh": None if free is None else float(free.sum()),
        "unclassified_mwh": float(energy[unknown].sum()),
    }


@router.get("/api/cases/{case_id}/energy/curve")
def power_curve(
    request: Request,
    case_id: str,
    turbine: str,
    run: str | None = None,
    method: Literal["auto", "wrf", "curve"] = "auto",
) -> dict[str, Any]:
    """Power curve of one turbine rebuilt from the run: its power at each output time against
    the free wind at the same time, the hub-height wind at its place in the run without
    turbines (tslist outputs, every model step), per 0.5 m/s bin. No run without turbines, no
    free wind: no curve."""
    root, case = run_with_outputs(request, case_id, run)
    if not history_paths(stage_folder(root, "control")):
        raise HTTPException(
            422,
            tr(
                "No run without turbines: the power curve is drawn against its free wind",
                "Pas de calcul sans éoliennes : la courbe de puissance se trace au vent libre de ce calcul",
            ),
        )
    try:
        site = next((s for s in sites(case) if s.label == turbine), None)
        if site is None:
            raise EnergyError(tr(f"Unknown turbine {turbine!r}", f"Éolienne inconnue {turbine!r}"))
        frame: pd.DataFrame = remember(
            ("energy_series", *outputs_stamp(root), method, "raw", turbine, None, None, current()),
            lambda: energy_series(root, case, method, "raw", turbine),
        ).copy()
    except EnergyError as error:
        raise HTTPException(422, str(error)) from error
    times = pd.DatetimeIndex(frame["time"])
    times = times.tz_convert("UTC").tz_localize(None) if times.tz is not None else times
    power = pd.Series(frame[turbine].to_numpy() * 1e6, index=times)
    ref = SeriesRef(
        kind="run", case_id=case_id, run_id=root.name, stage="control", variable="wind_speed",
        location=turbine, height_m=site.hub_height_m, options={"averaging_s": 0},
    )  # fmt: skip
    try:
        wind = resolve(state(request), ref)
    except SeriesNotFound as error:
        raise HTTPException(422, str(error)) from error
    stamps = pd.DatetimeIndex(wind.values.index)
    stamps = stamps.tz_convert("UTC").tz_localize(None) if stamps.tz is not None else stamps
    speed = pd.Series(wind.values.to_numpy(dtype=float), index=stamps).groupby(level=0).first()
    # The wind at each output time (the model step that ends there, within a minute)
    at = speed.reindex(times, method="nearest", tolerance=pd.Timedelta(minutes=1))
    return {
        "run_id": root.name,
        "method_text": frame.attrs.get("method_text", ""),
        "wind": f"{wind.meta.method} ({wind.meta.dataset})",
        **binned_curve(at, power, site.turbine),
    }
