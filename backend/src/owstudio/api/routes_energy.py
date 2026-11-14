"""Energy produced over the simulated period, per turbine and per farm, and wake losses."""

from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Request

from owstudio.api.routes_cases import state
from owstudio.core.case.model import Case
from owstudio.core.energy import integrate
from owstudio.core.energy.power_curve import binned_curve
from owstudio.core.energy.production import EnergyError, sites
from owstudio.core.energy.summary import choose_method, energy_series, run_energy
from owstudio.core.extract.quantities import wind_quantity
from owstudio.core.extract.runs import power_source_text
from owstudio.core.i18n import current, tr
from owstudio.core.postproc.results import remember
from owstudio.core.postproc.windowed import history_paths
from owstudio.core.series.sources import SeriesNotFound, SeriesRef, resolve
from owstudio.core.storage import outputs_stamp, stage_folder
from owstudio.core.times import naive_index

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
            "No results yet: import outputs first",
            "Pas encore de résultats : importer d'abord des sorties",
        ),
    )


@router.get("/api/cases/{case_id}/energy")
def energy_summary(
    request: Request,
    case_id: str,
    run: str | None = None,
    method: Literal["auto", "tslist", "wrf", "curve"] = "auto",
) -> dict[str, Any]:
    root, case = run_with_outputs(request, case_id, run)
    try:
        return {"run_id": root.name, **energy_of(root, case, method)}
    except EnergyError as error:
        raise HTTPException(422, str(error)) from error


def energy_of(
    root: Path, case: Case, method: Literal["auto", "tslist", "wrf", "curve"]
) -> dict[str, Any]:
    """The energy summary of a run, kept once computed (a new import is a new key)."""
    summary: dict[str, Any] = remember(
        ("energy", *outputs_stamp(root), method, current()), lambda: run_energy(root, case, method)
    )
    return summary


@router.get("/api/cases/{case_id}/energy/series")
def energy_over_time(
    request: Request, case_id: str, run: str | None = None, method: Literal["auto", "tslist", "wrf", "curve"] = "auto",
    period: Literal["raw", "hour", "day", "month"] = "raw",
    turbine: str | None = None,
    cell: str | None = None,
    farm: str | None = None,
) -> dict[str, Any]:  # fmt: skip
    """Power per farm (MW) at the output times, or energy (MWh) per UTC hour, day or month, with
    the reference without wakes when the run has a control run. Files are written by the
    Exporter tab (routes_export.py)."""
    root, case = run_with_outputs(request, case_id, run)
    try:
        kept: pd.DataFrame = remember(
            ("energy_series", *outputs_stamp(root), method, period, turbine, cell, farm, current()),
            lambda: energy_series(root, case, method, period, turbine, cell, farm),
        )
        frame = kept.copy()
    except EnergyError as error:
        raise HTTPException(422, str(error)) from error
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
    """Energy (MWh) of one turbine per wind direction sector, with and without wakes.

    tslist: each 10-minute interval's mean power x 10 min goes to the sector of the mean hub
    direction of the same steps (from the mean u and v). Without tslist at the turbines, wrfout:
    each interval between two output times, mean of the two powers x its duration, in the sector of
    their mean wind. Each run is sorted by its own wind, the free wind for the run without turbines.
    """
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
    width = 360.0 / sectors

    def series(stage: str, variable: str, reader: str) -> Any:
        ref = SeriesRef(
            kind="run", case_id=case_id, run_id=root.name, stage=stage, variable=variable,
            location=turbine, height_m=site.hub_height_m, reader=reader,
            options={"averaging_s": 600} if reader == "tslist" else {},
        )  # fmt: skip
        return resolve(state(request), ref)

    def sector_of(angles: np.ndarray) -> np.ndarray:
        return np.where(
            np.isfinite(angles), np.floor(((angles + width / 2) % 360.0) / width), -1
        ).astype(int)

    # How the tslist power of the run with turbines was obtained (extract/runs.py POWER_SOURCES)
    obtained = {"main": "fitch"}

    def from_tslist(stage: str) -> tuple[pd.Series, np.ndarray, Any]:
        """Energy (MWh) of each 10-minute interval, mean power (MW) x 1/6 h, and its sector."""
        power = series(stage, "power", "tslist")
        obtained[stage] = str(power.meta.extra.get("power") or "fitch")
        direction = series(stage, "wind_direction", "tslist")
        energy = pd.Series(
            power.values.to_numpy(dtype=float) / 6, index=naive_index(power.values.index)
        )
        angles = (
            pd.Series(
                direction.values.to_numpy(dtype=float), index=naive_index(direction.values.index)
            )
            .groupby(level=0)
            .first()
            .reindex(pd.DatetimeIndex(energy.index))
            .to_numpy(dtype=float)
        )
        return energy, sector_of(angles), direction

    def from_wrfout(
        stage: str, power_mw: pd.Series, initial_left_out: bool
    ) -> tuple[pd.Series, np.ndarray, Any]:
        """Energy (MWh) of each interval between two wrfout times, by trapezoids as the energy
        tables (from the same start), and the sector of the mean wind of its two ends."""
        start = integrate.common_start(case.period.start, initial_left_out)
        power = integrate.clean(power_mw * 1e6, start)
        parts = integrate.segments(power, integrate.tolerance(pd.DatetimeIndex(power.index)))
        u, v = series(stage, "u", "wrfout"), series(stage, "v", "wrfout")

        def ends(wind: Any) -> np.ndarray:
            values = (
                pd.Series(wind.values.to_numpy(dtype=float), index=naive_index(wind.values.index))
                .groupby(level=0)
                .first()
            )
            first = values.reindex(naive_index(parts["start"])).to_numpy(dtype=float)
            last = values.reindex(naive_index(parts["end"])).to_numpy(dtype=float)
            mean: np.ndarray = (first + last) / 2
            return mean

        angles = wind_quantity("wind_direction", ends(u), ends(v))
        energy = pd.Series(
            parts["energy_wh"].to_numpy(dtype=float) / 1e6, index=naive_index(parts["end"])
        )
        return energy, sector_of(angles), u

    free: pd.Series | None = None
    free_codes: np.ndarray | None = None
    try:
        used = choose_method("auto", root, case)
        if used == "tslist":
            energy, codes, direction = from_tslist("main")
            if has_control:
                free, free_codes, _ = from_tslist("control")
            source = power_source_text(obtained["main"], case)
            method_text = tr(
                f"10-minute means of the tslist outputs: turbine power ({source}) and wind direction at the hub; energy = mean power x 10 min",
                f"moyennes sur 10 min des sorties tslist : puissance de l'éolienne ({source}) et direction du vent au moyeu ; énergie = puissance moyenne x 10 min",
            )
        else:
            frame: pd.DataFrame = remember(
                ("energy_series", *outputs_stamp(root), "auto", "raw", turbine, None, None, current()),
                lambda: energy_series(root, case, "auto", "raw", turbine),
            ).copy()  # fmt: skip
            times = pd.DatetimeIndex(frame["time"])
            initial = bool(frame.attrs.get("initial_left_out"))
            energy, codes, direction = from_wrfout(
                "main", pd.Series(frame[turbine].to_numpy(dtype=float), index=times), initial
            )
            without = f"{turbine}_without_wakes"
            if without in frame:
                free, free_codes, _ = from_wrfout(
                    "control",
                    pd.Series(frame[without].to_numpy(dtype=float), index=times),
                    initial,
                )
            source = str(frame.attrs.get("method_text", ""))
            method_text = tr(
                f"{source}: turbine power and wind at the hub at each wrfout time; energy of each interval between two times = mean of the two powers x duration, in the sector of the mean wind of the two times",
                f"{source} : puissance de l'éolienne et vent au moyeu à chaque instant wrfout ; énergie de chaque intervalle entre deux instants = moyenne des deux puissances x durée, dans le secteur du vent moyen des deux instants",
            )
    except (EnergyError, SeriesNotFound) as error:
        raise HTTPException(422, str(error)) from error

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
            "count": int(mask.sum()),
            "energy_mwh": main_mwh,
            "reference_mwh": free_mwh,
            "loss_pct": 100 * (1 - main_mwh / free_mwh) if free_mwh else None,
        })  # fmt: skip
    unknown = codes < 0
    return {
        "run_id": root.name,
        "method": used,
        "method_text": method_text,
        "turbines_approximate": used != "tslist",
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
    method: Literal["auto", "tslist", "wrf", "curve"] = "auto",
) -> dict[str, Any]:
    """Power curve of one turbine rebuilt from the run: its 10-minute mean power against the mean
    free wind of the same interval (hub height, same place, run without turbines), in 0.5 m/s
    bins; without tslist at the turbines, its power at each wrfout time against the free wind
    then. No run without turbines, no curve."""
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
    times = naive_index(frame["time"])
    power = pd.Series(frame[turbine].to_numpy() * 1e6, index=times)
    # The free wind is read where the power comes from: the 10-minute means of the tslist
    # outputs, or the history files at their output times
    from_tslist = frame.attrs.get("method") == "tslist"
    ref = SeriesRef(
        kind="run", case_id=case_id, run_id=root.name, stage="control", variable="wind_speed",
        location=turbine, height_m=site.hub_height_m, reader="tslist" if from_tslist else "wrfout",
        options={"averaging_s": 600} if from_tslist else {},
    )  # fmt: skip
    try:
        wind = resolve(state(request), ref)
    except SeriesNotFound as error:
        raise HTTPException(422, str(error)) from error
    stamps = naive_index(wind.values.index)
    speed = pd.Series(wind.values.to_numpy(dtype=float), index=stamps).groupby(level=0).first()
    # The free wind of the same 10-minute interval, or of the same wrfout time
    at = speed.reindex(times)
    return {
        "run_id": root.name,
        "method": frame.attrs.get("method", ""),
        "method_text": frame.attrs.get("method_text", ""),
        "wind": f"{wind.meta.method} ({wind.meta.dataset})",
        **binned_curve(at, power, site.turbine),
    }
