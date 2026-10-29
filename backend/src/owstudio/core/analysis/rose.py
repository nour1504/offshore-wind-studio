"""Wind roses: frequency of wind by direction sector and speed bin, mean speed and energy share
per sector, for one record or several pooled (the turbines of a farm, for example)."""

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from owstudio.core.analysis.common import (
    AnalysisError,
    Result,
    Selection,
    check_sectors,
    describe,
    quality_notes,
    sampling_step,
    sector_labels,
    timing,
)
from owstudio.core.analysis.wind import Wind
from owstudio.core.i18n import tr
from owstudio.core.series import circular

DEFAULT_SPEED_BINS = (0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0, 25.0)


@dataclass(frozen=True)
class PowerCurve:
    """Electrical power against hub-height wind speed, linearly interpolated between points and
    zero below the first point and above the last one (taken as cut-in and cut-out)."""

    wind_speed: tuple[float, ...]
    power_kw: tuple[float, ...]
    name: str = ""

    def __post_init__(self) -> None:
        if len(self.wind_speed) < 2 or len(self.wind_speed) != len(self.power_kw):
            raise AnalysisError(
                tr(
                    "A power curve needs at least two (wind speed, power) points",
                    "Une courbe de puissance demande au moins deux points (vitesse, puissance)",
                )
            )
        if not all(np.isfinite(self.wind_speed)) or not all(np.isfinite(self.power_kw)):
            raise AnalysisError(
                tr(
                    "A power curve cannot contain missing values",
                    "Une courbe de puissance ne peut pas contenir de valeurs manquantes",
                )
            )
        if any(b <= a for a, b in zip(self.wind_speed, self.wind_speed[1:], strict=False)):
            raise AnalysisError(
                tr(
                    "The wind speeds of a power curve must strictly increase",
                    "Les vitesses d'une courbe de puissance doivent croître strictement",
                )
            )
        if min(self.wind_speed) < 0 or min(self.power_kw) < 0:
            raise AnalysisError(
                tr(
                    "Wind speeds and powers of a power curve cannot be negative",
                    "Les vitesses et puissances d'une courbe de puissance ne peuvent pas être négatives",
                )
            )

    def power(self, speed: np.ndarray) -> np.ndarray:
        """Power in kW of each wind speed (NaN stays NaN)."""
        s = np.asarray(speed, dtype=float)
        p = np.interp(s, self.wind_speed, self.power_kw, left=0.0, right=0.0)
        return np.where(np.isfinite(s), p, np.nan)

    def describe(self) -> str:
        name = f" {self.name}" if self.name else ""
        return tr(
            f"power curve{name} ({len(self.wind_speed)} points, {self.wind_speed[0]:g} to "
            f"{self.wind_speed[-1]:g} m/s, linear interpolation, zero outside)",
            f"courbe de puissance{name} ({len(self.wind_speed)} points, {self.wind_speed[0]:g} à "
            f"{self.wind_speed[-1]:g} m/s, interpolation linéaire, zéro en dehors)",
        )


def check_speed_bins(edges: Sequence[float]) -> np.ndarray:
    e = np.asarray(edges, dtype=float)
    if e.size < 1 or e[0] != 0 or not np.all(np.isfinite(e)) or np.any(np.diff(e) <= 0):
        raise AnalysisError(
            tr(
                "Speed bins must be strictly increasing edges starting at 0 m/s, for example "
                "0, 4, 8, 12, 16; the last bin is open (at least the last edge)",
                "Les classes de vitesse doivent être des bornes strictement croissantes commençant à 0 m/s, par exemple 0, 4, 8, 12, 16 ; la dernière classe est ouverte (au moins la dernière borne)",
            )
        )
    if e.size > 100:
        raise AnalysisError(tr("At most 100 speed bins", "100 classes de vitesse au plus"))
    return e


def bin_labels(edges: np.ndarray, calm: float) -> list[dict[str, float | str | None]]:
    result: list[dict[str, float | str | None]] = []
    for i, lower in enumerate(edges):
        upper = float(edges[i + 1]) if i + 1 < len(edges) else None
        low = max(float(lower), calm) if i == 0 else float(lower)
        label = f"{low:g}–{upper:g} m/s" if upper is not None else f"≥ {low:g} m/s"
        result.append({"bin": i, "lower": low, "upper": upper, "label": label})
    return result


def check_poolable(winds: Sequence[Wind]) -> list[str]:
    """Pooled records must sample time alike, otherwise their samples would not weigh the
    same. Returns notes on the records that could not be checked."""
    first = winds[0].speed
    step = sampling_step(first)
    notes = []
    for wind in winds[1:]:
        meta = wind.speed.meta
        if meta.averaging_s != first.meta.averaging_s:
            raise AnalysisError(
                tr(
                    f"Pooled records must have the same averaging: {first.meta.key} has "
                    f"{timing(first.meta)} and {meta.key} has {timing(meta)}",
                    f"Les enregistrements regroupés doivent avoir la même moyenne : {first.meta.key} a {timing(first.meta)} et {meta.key} a {timing(meta)}",
                )
            )
        other = sampling_step(wind.speed)
        if step is not None and other is not None and not np.isclose(step, other, rtol=0.01):
            raise AnalysisError(
                tr(
                    f"Pooled records must have the same time step: {first.meta.key} has a value "
                    f"every {step:g} s and {meta.key} every {other:g} s, so their samples would "
                    "not weigh the same",
                    f"Les enregistrements regroupés doivent avoir le même pas de temps : {first.meta.key} a une valeur toutes les {step:g} s et {meta.key} toutes les {other:g} s, leurs échantillons ne pèseraient donc pas autant",
                )
            )
        if step is None or other is None:
            notes.append(
                tr(
                    f"The time step of {meta.key} or {first.meta.key} could not be checked",
                    f"Le pas de temps de {meta.key} ou de {first.meta.key} n'a pas pu être vérifié",
                )
            )
    return notes


def wind_rose(
    winds: Sequence[Wind],
    sectors: int = 12,
    speed_bins: Sequence[float] = DEFAULT_SPEED_BINS,
    calm: float = 0.0,
    power_curve: PowerCurve | None = None,
    selection: Selection | None = None,
) -> Result:
    """Joint frequency of direction sectors and speed bins (percent of valid samples), calms,
    and per sector the mean speed and the share of U³ (or of power with a power curve)."""
    selection = selection or Selection()
    check_sectors(sectors)
    edges = check_speed_bins(speed_bins)
    if not 0 <= calm < 5:
        raise AnalysisError(
            tr(
                "The calm threshold must be between 0 and 5 m/s",
                "Le seuil de calme doit être entre 0 et 5 m/s",
            )
        )
    if not winds:
        raise AnalysisError(
            tr(
                "A wind rose needs at least one wind record",
                "Une rose des vents demande au moins un enregistrement de vent",
            )
        )
    notes = check_poolable(winds)
    frames, inputs = [], []
    for wind in winds:
        frame = wind.frame(selection, need_direction=True)
        frames.append(frame)
        assert wind.direction is not None
        inputs += [
            {**describe(wind.speed.meta), "samples": int(frame["speed"].notna().sum())},
            describe(wind.direction.meta),
        ]
        notes += wind.notes() + quality_notes(wind.series, selection)
    pooled = pd.concat(frames, ignore_index=True)
    speed, direction = pooled["speed"].to_numpy(), pooled["direction"].to_numpy()

    has_speed = np.isfinite(speed)
    is_calm = has_speed & ((speed < calm) | (speed == 0))
    directional = has_speed & ~is_calm & np.isfinite(direction)
    no_direction = int(np.sum(has_speed & ~is_calm & ~np.isfinite(direction)))
    valid = int(np.sum(is_calm | directional))
    if valid == 0:
        raise AnalysisError(
            tr(
                "No valid wind sample (speed and direction) in the selected period",
                "Aucun échantillon de vent valide (vitesse et direction) sur la période choisie",
            )
        )

    sector = circular.sector(np.where(directional, direction, np.nan), sectors)
    speed_bin = np.searchsorted(edges, np.where(directional, speed, 0.0), side="right") - 1
    counts = np.zeros((sectors, len(edges)), dtype=int)
    np.add.at(counts, (sector[directional], speed_bin[directional]), 1)

    if power_curve is None:
        weight = np.where(has_speed, speed, 0.0) ** 3
        energy_basis = tr(
            "share of the sum of U³ (cube of the wind speed)",
            "part de la somme de U³ (cube de la vitesse du vent)",
        )
    else:
        weight = np.nan_to_num(power_curve.power(speed))
        energy_basis = tr(
            f"share of the energy of the {power_curve.describe()}",
            f"part de l'énergie de la {power_curve.describe()}",
        )
    total_weight = float(np.sum(weight[is_calm | directional]))

    rows, sector_rows = [], []
    labels = bin_labels(edges, calm)
    for info in sector_labels(sectors):
        s = info["sector"]
        in_sector = directional & (sector == s)
        n = int(np.sum(in_sector))
        energy = float(np.sum(weight[in_sector]))
        sector_row = {
            **info,
            "count": n,
            "frequency_pct": 100.0 * n / valid,
            "mean_speed": float(np.mean(speed[in_sector])) if n else None,
            "energy_pct": 100.0 * energy / total_weight if total_weight > 0 else None,
        }
        if power_curve is not None:
            sector_row["mean_power_kw"] = float(np.mean(weight[in_sector])) if n else None
        sector_rows.append(sector_row)
        for position, b in enumerate(labels):
            count = int(counts[s, position])
            rows.append(
                {
                    "sector": s,
                    "centre_deg": info["centre_deg"],
                    "speed_lower": b["lower"],
                    "speed_upper": b["upper"],
                    "count": count,
                    "frequency_pct": 100.0 * count / valid,
                }
            )

    calm_count = int(np.sum(is_calm))
    if no_direction:
        notes.append(
            tr(
                f"{no_direction} samples with a speed but no direction were left out",
                f"{no_direction} échantillons avec une vitesse mais sans direction ont été écartés",
            )
        )
    if calm == 0:
        notes.append(
            tr(
                "Calm: only samples of exactly 0 m/s (no direction)",
                "Calme : seulement les échantillons à exactement 0 m/s (sans direction)",
            )
        )
    notes.append(
        tr(
            "Frequencies are percentages of all valid samples, calms included; sector 0 is "
            "centred on north and sectors go clockwise; directions are where the wind blows from",
            "Les fréquences sont des pourcentages de tous les échantillons valides, calmes compris ; le secteur 0 est centré sur le nord et les secteurs tournent dans le sens des aiguilles d'une montre ; les directions indiquent d'où vient le vent",
        )
    )
    if len(winds) > 1:
        notes.append(
            tr(
                f"{len(winds)} wind records pooled: every sample counts once",
                f"{len(winds)} enregistrements de vent regroupés : chaque échantillon compte une fois",
            )
        )
    return Result(
        kind="rose",
        method=(
            tr(
                f"Wind rose, {sectors} sectors, speed bins {', '.join(f'{e:g}' for e in edges)} m/s"
                f" (last bin open), calm below {calm:g} m/s; energy rose: {energy_basis}",
                f"Rose des vents, {sectors} secteurs, classes de vitesse {', '.join(f'{e:g}' for e in edges)} m/s (dernière classe ouverte), calme sous {calm:g} m/s ; rose d'énergie : {energy_basis}",
            )
        ),
        data={
            "sectors": sector_rows,
            "speed_bins": labels,
            # frequency[sector][bin], percent of valid samples
            "frequency": (100.0 * counts / valid).tolist(),
            "counts": counts.tolist(),
            "calm": {
                "threshold": calm,
                "count": calm_count,
                "frequency_pct": 100.0 * calm_count / valid,
                "energy_pct": (
                    100.0 * float(np.sum(weight[is_calm])) / total_weight
                    if total_weight > 0
                    else None
                ),
            },
            "energy_basis": "U3" if power_curve is None else "power_curve",
            "samples": {
                "total": len(pooled),
                "valid": valid,
                "missing_speed": int(np.sum(~has_speed)),
                "missing_direction": no_direction,
            },
            "mean_speed": float(np.mean(speed[is_calm | directional])),
        },
        tables={
            "frequency": pd.DataFrame(rows),
            "sectors": pd.DataFrame(sector_rows).drop(columns=["key"]),
        },
        notes=notes,
        inputs=inputs,
        selection=selection,
    )
