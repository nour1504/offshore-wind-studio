"""Explicit alignment of a simulated series on a measured one before comparing them, with the
representativeness caveats.

Both are averaged over the same UTC periods (for example 10 min or 1 h, starting at multiples of the
period), each value placed by the centre of its own averaging period; periods below the minimum
share of expected values stay empty; directions use circular means. The result says what was done.
"""

from typing import Any

import numpy as np
import pandas as pd

from owstudio.core.i18n import num, tr
from owstudio.core.series import Series, circular, height_text, stamp_position
from owstudio.core.series import relabel as move_labels


class AlignmentError(ValueError):
    pass


def model_steps(series: Series, period_s: float) -> tuple[Series, int]:
    """A model time series (one value per model step, tslist) as time-weighted means over
    ]t - period, t] (core/method/averaging.py), each value counting for the step ending at it;
    stamped at the start of each period like the other series here. Directions: mean of unit
    vectors. Returns the series and the number of incomplete periods left out."""
    from owstudio.core.method.averaging import weighted_means

    values = series.good(accept_suspect=False)
    frame = pd.DataFrame(index=pd.DatetimeIndex(values.index))
    if series.meta.circular:
        radians = np.radians(values.to_numpy(dtype=float))
        frame["east"], frame["north"] = np.sin(radians), np.cos(radians)
        means = weighted_means(frame, int(period_s))
        result = pd.Series(
            np.degrees(np.arctan2(means.frame["east"], means.frame["north"])) % 360.0,
            index=means.frame.index,
        )
    else:
        frame["x"] = values.to_numpy(dtype=float)
        means = weighted_means(frame, int(period_s))
        result = means.frame["x"]
    result.index = pd.DatetimeIndex(result.index) - pd.Timedelta(seconds=period_s)
    meta = series.meta.model_copy(
        update={
            "averaging_s": period_s,
            "time_label": "start",
            "frequency_s": period_s,
            "flags": [*series.meta.flags, means.note],
        }
    )
    return Series(meta, result.dropna()), means.excluded


def resample(series: Series, period_s: float, min_availability: float) -> tuple[Series, int]:
    """Means over ``period_s``-long UTC periods, stamped at their start; returns the series and
    the number of periods rejected for low availability. Model time series (tslist, one value
    per model step) are time-weighted (model_steps)."""
    if series.meta.source == "tslist" and series.meta.averaging_s == 0:
        return model_steps(series, period_s)
    step = series.meta.frequency_s
    if step is None or step <= 0:
        raise AlignmentError(
            tr(
                f"{series.meta.key}: irregular time steps, the availability per period cannot be computed",
                f"{series.meta.key} : pas de temps irréguliers, la disponibilité par période ne peut pas être calculée",
            )
        )
    if step > period_s + 1e-6:
        raise AlignmentError(
            tr(
                f"{series.meta.key} has one value every {step:g} s: it cannot be averaged over {period_s:g} s",
                f"{series.meta.key} a une valeur toutes les {num(step)} s : impossible d'en faire la moyenne sur {num(period_s)} s",
            )
        )
    centred = move_labels(series, "centre") if series.meta.averaging_s > 0 else series
    values = centred.good(accept_suspect=False)
    groups = values.resample(
        pd.Timedelta(seconds=period_s), origin="epoch", label="left", closed="left"
    )
    if series.meta.circular:
        means = groups.apply(
            lambda v: circular.mean(v.dropna().to_numpy()) if v.notna().any() else np.nan
        )
    else:
        means = groups.mean()
    counts = groups.count().to_numpy(dtype=float)
    expected = period_s / step
    kept = means.where(counts >= min_availability * expected)
    rejected = int(((counts > 0) & (counts < min_availability * expected)).sum())
    meta = series.meta.model_copy(
        update={
            "averaging_s": period_s,
            "time_label": "start",
            "frequency_s": period_s,
            "flags": [
                *series.meta.flags,
                tr(
                    f"averaged over {period_s:g} s periods (at least {100 * min_availability:g} % of the values)",
                    f"moyenné sur des périodes de {num(period_s)} s (au moins {num(100 * min_availability)} % des valeurs)",
                ),
            ],
        }
    )
    return Series(meta, kept.dropna()), rejected


def align(
    observation: Series, simulation: Series, period_s: float | None, min_availability: float = 0.7
) -> tuple[Series, Series, list[str]]:
    """The two series on the same periods. Without ``period_s``, they must already sample time
    the same way (same averaging and time stamp convention)."""
    notes: list[str] = []
    if observation.meta.height_ref != simulation.meta.height_ref or (
        observation.meta.height_m is not None
        and simulation.meta.height_m is not None
        and abs(observation.meta.height_m - simulation.meta.height_m) > 0.5
    ):
        measured = height_text(observation.meta.height_m, observation.meta.height_ref)
        simulated = height_text(simulation.meta.height_m, simulation.meta.height_ref)
        notes.append(
            tr(
                f"Heights differ: measured at {measured}, simulated at {simulated}",
                f"Hauteurs différentes : mesure à {measured}, simulation à {simulated}",
            )
        )
    if period_s is None:
        same = (observation.meta.averaging_s, observation.meta.time_label) == (
            simulation.meta.averaging_s,
            simulation.meta.time_label,
        )
        if not same:
            raise AlignmentError(
                tr(
                    "The series do not sample time the same way (measured: "
                    f"{observation.meta.averaging_s:g} s averages stamped {stamp_position(observation.meta.time_label)}; simulated: "
                    f"{simulation.meta.averaging_s:g} s, {stamp_position(simulation.meta.time_label)}): choose a common averaging period",
                    "Les séries n'échantillonnent pas le temps de la même façon (mesure : "
                    f"moyennes sur {num(observation.meta.averaging_s)} s datées {stamp_position(observation.meta.time_label)} ; simulation : "
                    f"{num(simulation.meta.averaging_s)} s, {stamp_position(simulation.meta.time_label)}) : choisir une période de moyenne commune",
                )
            )
        return observation, simulation, notes
    if not 60 <= period_s <= 86400 * 31:
        raise AlignmentError(
            tr(
                "The averaging period must be between 1 minute and 31 days",
                "La période de moyenne doit être comprise entre 1 minute et 31 jours",
            )
        )
    if not 0 < min_availability <= 1:
        raise AlignmentError(
            tr(
                "The minimum availability must be in (0, 1]",
                "La disponibilité minimale doit être dans ]0, 1]",
            )
        )
    obs, rejected_obs = resample(observation, period_s, min_availability)
    sim, rejected_sim = resample(simulation, period_s, min_availability)
    notes.append(
        tr(
            f"Both series averaged over {period_s / 60:g} min UTC periods; values placed by the centre of their own averaging period",
            f"Les deux séries sont moyennées sur des périodes UTC de {num(period_s / 60)} min ; chaque valeur est placée au centre de sa propre période de moyenne",
        )
    )
    if simulation.meta.source == "tslist" and simulation.meta.averaging_s == 0:
        notes.append(
            tr(
                "The simulated values (one per model time step) are time-weighted over ]t - period, t], "
                "each value counting for the step ending at it; incomplete periods are left out",
                "Les valeurs simulées (une par pas de temps du modèle) sont pondérées dans le temps sur ]t - période, t], "
                "chaque valeur comptant pour le pas qui se termine sur elle ; les périodes incomplètes sont écartées",
            )
        )
    elif simulation.meta.averaging_s == 0 and simulation.meta.frequency_s is not None:
        notes.append(
            tr(
                f"The simulated values are instantaneous (one every {simulation.meta.frequency_s:g} s): their period mean is a mean of samples, "
                "not a true average",
                f"Les valeurs simulées sont instantanées (une toutes les {num(simulation.meta.frequency_s)} s) : leur moyenne par période est une moyenne d'échantillons, "
                "pas une vraie moyenne",
            )
        )
    if rejected_obs or rejected_sim:
        notes.append(
            tr(
                f"Periods left empty for low availability: {rejected_obs} measured, {rejected_sim} simulated",
                f"Périodes laissées vides faute de disponibilité : {rejected_obs} en mesure, {rejected_sim} en simulation",
            )
        )
    return obs, sim, notes


# How the method of a series says that it was interpolated in height (extract/points.py,
# extract/quantities.py), in English and in French: the method is written in the language asked
HEIGHT_INTERPOLATION = ("interpolation in height", "interpolation linéaire en hauteur")


def caveats(observation: Series, simulation: Series, grid_spacing_m: float | None) -> list[str]:
    """What limits the comparison of a point measurement with a model value."""
    notes = []
    if grid_spacing_m:
        notes.append(
            tr(
                f"The model value represents a grid cell of {grid_spacing_m / 1000:g} km, the measurement a point: "
                "sub-grid variability is not in the model",
                f"La valeur du modèle représente une maille de {num(grid_spacing_m / 1000)} km, la mesure un point : "
                "la variabilité sous-maille n'est pas dans le modèle",
            )
        )
    instrument = str(observation.meta.extra.get("instrument", ""))
    if "lidar" in instrument:
        notes.append(
            tr(
                "LiDAR wind speeds are averaged over a probe volume along the beam and over the scan cone, not at a point",
                "Les vitesses du LiDAR sont moyennées sur un volume le long du faisceau et sur le cône de balayage, pas en un point",
            )
        )
    if instrument == "floating_lidar":
        notes.append(
            tr(
                "A floating LiDAR moves with the waves: check that motion compensation was applied",
                "Un LiDAR flottant bouge avec les vagues : vérifier que la compensation du mouvement a été appliquée",
            )
        )
    if instrument in ("met_mast", "platform"):
        notes.append(
            tr(
                "Masts and platforms disturb the flow in some directions: check the flow distortion sectors",
                "Mâts et plateformes perturbent l'écoulement dans certaines directions : vérifier les secteurs perturbés",
            )
        )
    if any(words in simulation.meta.method for words in HEIGHT_INTERPOLATION):
        notes.append(
            tr(
                "The simulated value is interpolated in height between model levels",
                "La valeur simulée est interpolée en hauteur entre les niveaux du modèle",
            )
        )
    if simulation.meta.variable in ("turbulence_intensity", "wind_speed_std"):
        notes.append(
            tr(
                "The simulated turbulence comes from the sub-grid TKE, as σu along the wind (σu = √(TKE / 0.945)); "
                "a measured 10-minute TI also includes resolved and mesoscale fluctuations",
                "La turbulence simulée vient de la TKE sous-maille, en σu le long du vent (σu = √(TKE / 0,945)) ; "
                "une TI mesurée sur 10 minutes contient aussi les fluctuations résolues et de méso-échelle",
            )
        )
    return notes


def summary(notes: list[str], obs: Series, sim: Series) -> dict[str, Any]:
    return {
        "notes": notes,
        "observation": obs.meta.model_dump(mode="json"),
        "simulation": sim.meta.model_dump(mode="json"),
    }
