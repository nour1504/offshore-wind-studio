"""Vertical profiles: mean wind speed (or any variable) per height, optionally per group, and the
power-law shear exponent and the wind veer between heights.

Shear exponent (power law U(z) ∝ z^α): pairwise α = ln(U2/U1) / ln(z2/z1); over several heights,
α is the least-squares slope of ln U against ln z at each time. Veer: the circular difference of
the directions (upper minus lower, positive when the wind turns clockwise with height, as in the
northern hemisphere Ekman spiral) divided by the height difference.
"""

from collections.abc import Sequence

import numpy as np
import pandas as pd

from owstudio.core.analysis.common import (
    AnalysisError,
    Grouping,
    Result,
    Selection,
    aligned,
    check_grouping_timing,
    check_heights,
    check_same_timing,
    describe,
    direction_values,
    group_masks,
    no_grouping,
    quality_notes,
    speed_values,
    stats,
)
from owstudio.core.i18n import tr
from owstudio.core.series import Series, circular

# Below this speed the ratio U2/U1 is dominated by noise and the exponent is not computed
MIN_SPEED_FOR_SHEAR = 1.0


def _by_height(series: Sequence[Series], purpose: str) -> list[Series]:
    if len(series) < 2:
        raise AnalysisError(
            tr(
                f"{purpose}: at least two heights are needed",
                f"{purpose} : il faut au moins deux hauteurs",
            )
        )
    check_heights(series, purpose)
    check_same_timing(series, purpose)
    ordered = sorted(series, key=lambda s: float(s.meta.height_m or 0.0))
    heights = [s.meta.height_m for s in ordered]
    if len(set(heights)) != len(heights):
        raise AnalysisError(
            tr(
                f"{purpose}: two series are at the same height",
                f"{purpose} : deux séries sont à la même hauteur",
            )
        )
    variables = {s.meta.variable for s in ordered}
    if len(variables) > 1:
        raise AnalysisError(
            tr(
                f"{purpose}: the series must be the same variable ({', '.join(sorted(variables))})",
                f"{purpose} : les séries doivent être la même variable ({', '.join(sorted(variables))})",
            )
        )
    return ordered


def profile(
    series: Sequence[Series], grouping: Grouping | None = None, selection: Selection | None = None
) -> Result:
    """Mean (circular mean for directions) and spread of a variable at each height, on the times
    where every height has a value, per group of a grouping."""
    selection = selection or Selection()
    grouping = grouping or no_grouping()
    ordered = _by_height(series, "Vertical profile")
    check_grouping_timing(grouping, ordered[0], "Vertical profile")
    frame = aligned({str(s.meta.height_m): selection.values(s) for s in ordered}).dropna()
    if frame.empty:
        raise AnalysisError(
            tr(
                "No time with a value at every height in the selected period",
                "Aucun instant avec une valeur à chaque hauteur sur la période choisie",
            )
        )
    masks, ungrouped = group_masks(grouping, pd.DatetimeIndex(frame.index))
    is_circular = ordered[0].meta.circular
    rows = []
    for group, mask in zip(grouping.groups, masks, strict=True):
        for s, column in zip(ordered, frame.columns, strict=True):
            st = stats(frame[column].to_numpy()[mask], is_circular)
            rows.append(
                {
                    "group": group["key"],
                    "group_label": group["label"],
                    "height_m": s.meta.height_m,
                    **st,
                }
            )
    notes = [*grouping.notes, *quality_notes(ordered, selection)]
    notes.append(
        tr(
            f"{len(frame)} times with a value at every height are used (complete profiles only)",
            f"{len(frame)} instants avec une valeur à chaque hauteur sont utilisés (profils complets seulement)",
        )
    )
    if ungrouped:
        notes.append(
            tr(
                f"{ungrouped} complete profiles belong to no group",
                f"{ungrouped} profils complets n'appartiennent à aucun groupe",
            )
        )
    return Result(
        kind="profile",
        method=tr(
            f"Mean vertical profile of {ordered[0].meta.variable} ({grouping.title})",
            f"Profil vertical moyen de {ordered[0].meta.variable} ({grouping.title})",
        ),
        data={
            "unit": ordered[0].meta.unit,
            "height_ref": ordered[0].meta.height_ref,
            "heights": [s.meta.height_m for s in ordered],
            "groups": grouping.groups,
            "rows": rows,
        },
        tables={"profile": pd.DataFrame(rows)},
        notes=notes,
        inputs=[describe(s.meta) for s in ordered] + grouping.inputs,
        selection=selection,
    )


def shear(
    speeds: Sequence[Series], grouping: Grouping | None = None, selection: Selection | None = None
) -> Result:
    """Power-law shear exponent: pairwise between the lowest and the highest height, and fitted
    by least squares over all heights, at each time; statistics per group."""
    selection = selection or Selection()
    grouping = grouping or no_grouping()
    ordered = _by_height(speeds, "Shear exponent")
    check_grouping_timing(grouping, ordered[0], "Shear exponent")
    frame = aligned({str(s.meta.height_m): speed_values(s, selection) for s in ordered}).dropna()
    z = np.array([float(s.meta.height_m or 0.0) for s in ordered])
    if z[0] <= 0:
        raise AnalysisError(
            tr(
                "Heights must be above 0 m for a power law",
                "Les hauteurs doivent être au-dessus de 0 m pour une loi puissance",
            )
        )
    u = frame.to_numpy(dtype=float)
    usable = np.all(u >= MIN_SPEED_FOR_SHEAR, axis=1)
    log_u = np.log(np.where(usable[:, None], u, np.nan))
    log_z = np.log(z)
    pairwise = (log_u[:, -1] - log_u[:, 0]) / (log_z[-1] - log_z[0])
    centred = log_z - log_z.mean()
    fitted = ((log_u - np.nanmean(log_u, axis=1, keepdims=True)) * centred).sum(axis=1) / (
        centred**2
    ).sum()
    fitted = np.where(usable, fitted, np.nan)
    series_frame = pd.DataFrame(
        {"time": frame.index, "alpha_pairwise": pairwise, "alpha_fit": fitted}
    )
    masks, _ungrouped = group_masks(grouping, pd.DatetimeIndex(frame.index))
    rows = []
    for group, mask in zip(grouping.groups, masks, strict=True):
        rows.append(
            {
                **group,
                "pairwise": stats(pairwise[mask], False),
                "fit": stats(fitted[mask], False) if len(z) > 2 else None,
            }
        )
    notes = [*grouping.notes, *quality_notes(ordered, selection)]
    left_out = int((~usable).sum())
    if left_out:
        notes.append(
            tr(
                f"{left_out} times with a speed below {MIN_SPEED_FOR_SHEAR:g} m/s at some height left out",
                f"{left_out} instants avec une vitesse sous {MIN_SPEED_FOR_SHEAR:g} m/s à une des hauteurs écartés",
            )
        )
    notes.append(
        tr(
            "The power law is an empirical description: in stable conditions or above the surface layer "
            "the profile may not follow it, and α then depends on the heights used",
            "La loi puissance est une description empirique : en conditions stables ou au-dessus de la couche de surface, le profil peut ne pas la suivre, et α dépend alors des hauteurs utilisées",
        )
    )
    return Result(
        kind="shear",
        method=(
            tr(
                f"Power-law shear exponent between {z[0]:g} and {z[-1]:g} m {ordered[0].meta.height_ref}"
                + ("; least-squares fit of ln U on ln z over all heights" if len(z) > 2 else ""),
                f"Exposant de cisaillement (loi puissance) entre {z[0]:g} et {z[-1]:g} m {ordered[0].meta.height_ref}"
                + (
                    " ; ajustement par moindres carrés de ln U sur ln z à toutes les hauteurs"
                    if len(z) > 2
                    else ""
                ),
            )
        ),
        data={
            "heights": z.tolist(),
            "groups": rows,
            "times": [t.isoformat() for t in frame.index],
            "alpha_pairwise": pairwise.tolist(),
            "alpha_fit": fitted.tolist(),
        },
        tables={"series": series_frame, "groups": pd.json_normalize(rows)},
        notes=notes,
        inputs=[describe(s.meta) for s in ordered] + grouping.inputs,
        selection=selection,
    )


def veer(
    lower: Series,
    upper: Series,
    grouping: Grouping | None = None,
    selection: Selection | None = None,
) -> Result:
    """Direction change between two heights (degrees and degrees per metre), with circular
    differences; statistics per group."""
    selection = selection or Selection()
    grouping = grouping or no_grouping()
    ordered = _by_height([lower, upper], "Wind veer")
    check_grouping_timing(grouping, ordered[0], "Wind veer")
    frame = aligned(
        {
            "low": direction_values(ordered[0], selection),
            "high": direction_values(ordered[1], selection),
        }
    ).dropna()
    dz = float((ordered[1].meta.height_m or 0.0) - (ordered[0].meta.height_m or 0.0))
    turn = circular.difference(frame["high"].to_numpy(), frame["low"].to_numpy())
    masks, _ungrouped = group_masks(grouping, pd.DatetimeIndex(frame.index))
    rows = []
    for group, mask in zip(grouping.groups, masks, strict=True):
        st = stats(turn[mask], False)
        rows.append(
            {**group, **st, "mean_deg_per_m": None if st["mean"] is None else st["mean"] / dz}
        )
    notes = [*grouping.notes, *quality_notes(ordered, selection)]
    notes.append(
        tr(
            "Veer = upper minus lower direction, in (-180, 180]; positive: clockwise turning with height",
            "Rotation = direction du haut moins direction du bas, dans (-180, 180] ; positive : rotation dans le sens des aiguilles d'une montre avec la hauteur",
        )
    )
    return Result(
        kind="veer",
        method=tr(
            f"Wind veer between {ordered[0].meta.height_m:g} and {ordered[1].meta.height_m:g} m",
            f"Rotation du vent entre {ordered[0].meta.height_m:g} et {ordered[1].meta.height_m:g} m",
        ),
        data={
            "height_difference_m": dz,
            "groups": rows,
            "times": [t.isoformat() for t in frame.index],
            "veer_deg": turn.tolist(),
        },
        tables={
            "groups": pd.DataFrame(rows),
            "series": pd.DataFrame({"time": frame.index, "veer_deg": turn}),
        },
        notes=notes,
        inputs=[describe(s.meta) for s in ordered] + grouping.inputs,
        selection=selection,
    )
