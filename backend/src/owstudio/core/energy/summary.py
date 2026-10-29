"""Energy over the computed period of one run: per farm and per turbine, with the reference
without wakes from the run without turbines when it exists, losses, capacity factors, AEP when a
full year is covered, and power and energy series by period."""

from pathlib import Path
from typing import Any, Literal

import pandas as pd

from owstudio.core.case.model import Case
from owstudio.core.energy import integrate
from owstudio.core.energy.production import (
    EnergyError,
    Method,
    RunPower,
    Site,
    Turbines,
    installed_w,
    reference_power,
    run_power,
    sites,
    total,
)
from owstudio.core.i18n import tr
from owstudio.core.postproc.windowed import history_paths
from owstudio.core.storage import stage_folder


def windowed(root: Path) -> bool:
    """Outputs of the window method: their retained times already exclude every spin-up."""
    return (root / "outputs" / "main" / "windows.json").is_file()


def simulated(case: Case) -> list[Site]:
    """Turbines of the farms WRF simulated in this run."""
    if case.farm_scheme is None:
        return []
    enabled = {f.id for f in case.enabled_farms}
    return [s for s in sites(case) if s.farm in enabled]


def choose_method(method: str, root: Path) -> Method:
    if method in ("wrf", "curve"):
        return method  # type: ignore[return-value]
    if method != "auto":
        raise EnergyError(
            tr(
                f"Unknown method {method!r} (wrf, curve or auto)",
                f"Méthode inconnue {method!r} (wrf, curve ou auto)",
            )
        )
    return "wrf"


def _energy_row(power: pd.Series, start: Any, rated_w: float) -> dict[str, Any]:
    energy = integrate.integrate(power, start)
    return {
        "energy_mwh": energy.energy_wh / 1e6,
        "mean_power_mw": None if energy.mean_power_w is None else energy.mean_power_w / 1e6,
        "capacity_factor": integrate.capacity_factor(energy, rated_w),
        "covered_h": energy.covered_h,
        "gaps": energy.gaps,
    }


def cell_members(folder: Path, case: Case, chosen: list[Site]) -> dict[str, list[Site]]:
    """Group turbines by the actual output grid, using the same location as POWER.

    Public labels are one-based WRF (i, j); this is a grouping, never a second allocation of
    shared-cell power. The reconstructed turbine shares already sum to their source cell.
    """
    run = RunPower(folder, case)
    cells: dict[str, list[Site]] = {}
    for site in chosen:
        j, i = run.cell(site)
        cells.setdefault(f"d{run.domain:02d}:{i + 1}:{j + 1}", []).append(site)
    return cells


def run_energy(root: Path, case: Case, method: str = "auto") -> dict[str, Any]:
    """Energy of the run in ``root`` (its outputs/main and, if present, outputs/control)."""
    chosen = simulated(case)
    if not chosen:
        raise EnergyError(
            tr(
                "No turbine was simulated in this run (no enabled farm or no wind farm scheme)",
                "Aucune éolienne n'a été simulée dans ce calcul (aucun parc activé ou aucun schéma de parc)",
            )
        )
    used: Method = choose_method(method, root)
    main = root / "outputs" / "main"
    control = stage_folder(root, "control")
    start = integrate.common_start(case.period.start, 0, "windowed" if windowed(root) else used)
    turbines = run_power(main, case, chosen, used)
    reference: Turbines | None = None
    if history_paths(control):
        scheme = case.farm_scheme.scheme if case.farm_scheme else "fitch"
        reference = reference_power(control, case, chosen, used, scheme)
    notes = [
        tr(
            f"Spin-up: each simulation starts {case.spin_up_hours} h before its useful time; those hours are excluded",
            f"Mise en route : chaque simulation commence {case.spin_up_hours} h avant sa période utile ; ces heures sont écartées",
        ),
        tr(
            "Energy: trapezoidal integration of the instantaneous power between output times; intervals longer than 1.5 times the usual step are not bridged",
            "Énergie : intégration par trapèzes de la puissance instantanée entre les instants de sortie ; les intervalles de plus de 1,5 fois le pas habituel ne sont pas comblés",
        ),
        tr(
            "Capacity factor: energy / (installed power x covered duration)",
            "Facteur de charge : énergie / (puissance installée x durée couverte)",
        ),
        *turbines.flags,
    ]
    farms_rows = []
    by_farm: dict[str, list[Site]] = {}
    for site in chosen:
        by_farm.setdefault(site.farm, []).append(site)
    names = {f.id: f.name for f in case.farms}
    for farm, members in by_farm.items():
        power = total([turbines.power[m.label] for m in members])
        row: dict[str, Any] = {
            "id": farm,
            "name": names.get(farm, farm),
            "turbines": len(members),
            "installed_mw": installed_w(members) / 1e6,
            **_energy_row(power, start, installed_w(members)),
        }
        if reference is not None:
            free = total([reference.power[m.label] for m in members])
            reference_energy = integrate.integrate(free, start).energy_wh / 1e6
            row["reference_energy_mwh"] = reference_energy
            row["loss_mwh"] = reference_energy - row["energy_mwh"]
            row["loss_pct"] = (
                100.0 * row["loss_mwh"] / reference_energy if reference_energy > 0 else None
            )
        farms_rows.append(row)
    turbine_rows = []
    for site in chosen:
        row = {
            "label": site.label,
            "farm": site.farm,
            "type": site.type,
            **_energy_row(turbines.power[site.label], start, site.rated_w),
        }
        row.pop("gaps")
        if reference is not None:
            free_mwh = integrate.integrate(reference.power[site.label], start).energy_wh / 1e6
            row.update(
                {
                    "reference_energy_mwh": free_mwh,
                    "loss_mwh": free_mwh - row["energy_mwh"],
                    "loss_pct": 100 * (free_mwh - row["energy_mwh"]) / free_mwh
                    if free_mwh > 0
                    else None,
                }
            )
        turbine_rows.append(row)
    cell_rows = []
    for key, members in cell_members(main, case, chosen).items():
        domain, i, j = key.split(":")
        power = total([turbines.power[m.label] for m in members])
        row = {
            "id": key,
            "domain": int(domain[1:]),
            "i": int(i),
            "j": int(j),
            "turbines": len(members),
            "farms": sorted({m.farm for m in members}),
            "shared": len({m.farm for m in members}) > 1,
            "installed_mw": installed_w(members) / 1e6,
            **_energy_row(power, start, installed_w(members)),
        }
        if reference is not None:
            free = total([reference.power[m.label] for m in members])
            free_mwh = integrate.integrate(free, start).energy_wh / 1e6
            row.update(reference_energy_mwh=free_mwh, loss_mwh=free_mwh - row["energy_mwh"])
            row["loss_pct"] = 100 * row["loss_mwh"] / free_mwh if free_mwh > 0 else None
        cell_rows.append(row)
    all_power = total(list(turbines.power.values()))
    overall = integrate.integrate(all_power, start)
    annual, annual_note = integrate.aep(overall)
    if reference is None:
        notes.append(
            tr(
                "No run without turbines in this run: wake losses need a control run",
                "Pas de calcul sans éoliennes dans ce calcul : les pertes de sillage demandent un calcul de contrôle",
            )
        )
    else:
        notes.append(
            tr(
                f"Reference without wakes: {reference.method}",
                f"Référence sans sillage : {reference.method}",
            )
        )
    if used == "wrf" and turbines.shared_cells:
        notes.append(
            tr(
                "Some cells are shared between farms: the per-farm split of their power is approximate",
                "Des mailles sont partagées entre parcs : la répartition de leur puissance par parc est approchée",
            )
        )
    return {
        "method": used,
        "method_text": turbines.method,
        "turbines_approximate": turbines.approximate,
        "spin_up_end": start.isoformat(),
        "covered_h": overall.covered_h,
        "total": {
            "installed_mw": installed_w(chosen) / 1e6,
            **_energy_row(all_power, start, installed_w(chosen)),
            "reference_energy_mwh": sum(r.get("reference_energy_mwh", 0.0) for r in farms_rows)
            if reference
            else None,
        },
        "aep_mwh": None if annual is None else annual / 1e6,
        "aep_note": annual_note,
        "farms": farms_rows,
        "turbines": turbine_rows,
        "cells": cell_rows,
        "notes": notes,
    }


def energy_series(
    root: Path,
    case: Case,
    method: str = "auto",
    period: Literal["raw", "hour", "day", "month"] = "raw",
    turbine: str | None = None,
    cell: str | None = None,
    farm: str | None = None,
) -> pd.DataFrame:
    """Power (MW) per farm at the output times, or energy (MWh) per period, with the reference
    without wakes when the run has a control run."""
    chosen = simulated(case)
    if not chosen:
        raise EnergyError(
            tr(
                "No turbine was simulated in this run",
                "Aucune éolienne n'a été simulée dans ce calcul",
            )
        )
    if farm is not None:
        if turbine is not None or cell is not None:
            raise EnergyError(
                tr(
                    "Choose a farm, a turbine or a grid cell, not several",
                    "Choisissez un parc, une éolienne ou une maille, pas plusieurs",
                )
            )
        chosen = [site for site in chosen if site.farm == farm]
        if not chosen:
            raise EnergyError(
                tr(f"Unknown simulated farm {farm!r}", f"Parc simulé inconnu {farm!r}")
            )
    if turbine is not None:
        chosen = [site for site in chosen if site.label == turbine]
        if not chosen:
            raise EnergyError(
                tr(
                    f"Unknown simulated turbine {turbine!r}",
                    f"Éolienne simulée inconnue {turbine!r}",
                )
            )
    if cell is not None:
        if turbine is not None:
            raise EnergyError(
                tr(
                    "Choose a turbine or a grid cell, not both",
                    "Choisissez une éolienne ou une maille, pas les deux",
                )
            )
        chosen = cell_members(root / "outputs" / "main", case, chosen).get(cell, [])
        if not chosen:
            raise EnergyError(
                tr(f"Unknown simulated grid cell {cell!r}", f"Maille simulée inconnue {cell!r}")
            )
    used = choose_method(method, root)
    start = integrate.common_start(case.period.start, 0, "windowed" if windowed(root) else used)
    turbines = run_power(root / "outputs" / "main", case, chosen, used)
    control = stage_folder(root, "control")
    reference = None
    if history_paths(control):
        reference = reference_power(
            control, case, chosen, used, case.farm_scheme.scheme if case.farm_scheme else "fitch"
        )
    columns: dict[str, pd.Series] = {}
    selected = turbine if turbine is not None else cell
    for name in [selected] if selected is not None else sorted({s.farm for s in chosen}):
        members = chosen if selected is not None else [s for s in chosen if s.farm == name]
        columns[name] = total([turbines.power[m.label] for m in members])
        if reference is not None:
            columns[f"{name}_without_wakes"] = total([reference.power[m.label] for m in members])
    if period == "raw":
        frame = pd.DataFrame({k: v / 1e6 for k, v in columns.items()})
        frame.index.name = "time"
        frame.attrs.update(
            method=used,
            method_text=turbines.method,
            turbines_approximate=turbines.approximate,
            notes=turbines.flags,
        )
        return frame.reset_index()
    parts = []
    for name, power in columns.items():
        part = integrate.by_period(power, period, start).set_index("period_start")
        parts.append((part["energy_wh"] / 1e6).rename(name))
    frame = pd.concat(parts, axis=1)
    frame.index.name = "period_start"
    frame.attrs.update(
        method=used,
        method_text=turbines.method,
        turbines_approximate=turbines.approximate,
        notes=turbines.flags,
    )
    return frame.reset_index()
