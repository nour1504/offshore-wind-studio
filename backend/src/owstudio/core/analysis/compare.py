"""Comparison of two series of the same quantity, typically a simulation against a measurement.

Values are paired on equal time stamps (or the nearest within a tolerance); both series must
sample time the same way (same averaging and time label), otherwise one must be aggregated or
relabelled first. Differences are "evaluated minus reference" (model minus measurement).
Directions use circular differences in (-180, 180].
"""

import numpy as np
import pandas as pd

from owstudio.core.analysis.common import (
    AnalysisError,
    Grouping,
    Result,
    Selection,
    check_grouping_timing,
    check_same_timing,
    decimate,
    describe,
    group_masks,
    in_unit,
    no_grouping,
    quality_notes,
)
from owstudio.core.i18n import tr
from owstudio.core.series import Series, circular, units

SCATTER_LIMIT = 5000
QUANTILES = np.arange(1, 100)


def metrics(
    reference: np.ndarray, evaluated: np.ndarray, is_circular: bool
) -> dict[str, float | int | None]:
    """Bias, MAE, RMSE, centred RMSE, correlation, standard deviation ratio, R², OLS and
    orthogonal regressions (linear quantities); circular bias, MAE and RMSE (directions)."""
    ok = np.isfinite(reference) & np.isfinite(evaluated)
    a, b = reference[ok], evaluated[ok]
    n = int(a.size)
    if n == 0:
        return {"count": 0}
    if is_circular:
        d = circular.difference(b, a)
        # Circular mean of the differences, brought back to (-180, 180]
        mean = circular.mean(d)
        return {
            "count": n,
            "bias": float(circular.difference(mean, 0.0)) if np.isfinite(mean) else None,
            "mae": float(np.mean(np.abs(d))),
            "rmse": float(np.sqrt(np.mean(d**2))),
        }
    d = b - a
    result: dict[str, float | int | None] = {
        "count": n,
        "mean_reference": float(np.mean(a)),
        "mean_evaluated": float(np.mean(b)),
        "bias": float(np.mean(d)),
        "mae": float(np.mean(np.abs(d))),
        "rmse": float(np.sqrt(np.mean(d**2))),
        "crmse": float(np.std(d)),
    }
    if n > 2 and np.std(a) > 0 and np.std(b) > 0:
        r = float(np.corrcoef(a, b)[0, 1])
        slope, intercept = np.polyfit(a, b, 1)
        # Orthogonal (total least squares) regression: errors in both series
        sxx, syy = float(np.var(a)), float(np.var(b))
        sxy = float(np.mean((a - a.mean()) * (b - b.mean())))
        tls = (
            (syy - sxx + np.sqrt((syy - sxx) ** 2 + 4 * sxy**2)) / (2 * sxy)
            if sxy != 0
            else float("nan")
        )
        result.update(
            {
                "correlation": r,
                "r2": r * r,
                "std_ratio": float(np.std(b) / np.std(a)),
                "ols_slope": float(slope),
                "ols_intercept": float(intercept),
                "orthogonal_slope": float(tls),
                "orthogonal_intercept": float(b.mean() - tls * a.mean()),
            }
        )
    return result


def pair(
    reference: Series, evaluated: Series, selection: Selection, tolerance_s: float
) -> pd.DataFrame:
    """Columns ``reference`` and ``evaluated`` (evaluated converted to the reference's unit)."""
    check_same_timing([reference, evaluated], "Comparison")
    if reference.meta.variable != evaluated.meta.variable:
        raise AnalysisError(
            tr(
                f"Cannot compare {reference.meta.variable!r} with {evaluated.meta.variable!r}: the same quantity is needed",
                f"Impossible de comparer {reference.meta.variable!r} à {evaluated.meta.variable!r} : il faut la même grandeur",
            )
        )
    a = selection.values(reference)
    b = in_unit(
        evaluated,
        selection.values(evaluated),
        reference.meta.unit,
        f"a value in {reference.meta.unit}",
    )
    if tolerance_s <= 0:
        frame = pd.concat({"reference": a, "evaluated": b}, axis=1, join="inner")
    else:
        left = a.rename("reference").to_frame().reset_index(names="time")
        right = b.rename("evaluated").to_frame().reset_index(names="time_evaluated")
        merged = pd.merge_asof(
            left.sort_values("time"),
            right.sort_values("time_evaluated"),
            left_on="time",
            right_on="time_evaluated",
            direction="nearest",
            tolerance=pd.Timedelta(seconds=tolerance_s),
        )
        frame = merged.set_index("time")[["reference", "evaluated"]]
    return frame.dropna()


def compare(
    reference: Series,
    evaluated: Series,
    grouping: Grouping | None = None,
    tolerance_s: float = 0.0,
    selection: Selection | None = None,
) -> Result:
    """Metrics of ``evaluated`` against ``reference`` overall and per group, with scatter, Q-Q
    and time series data for plotting."""
    selection = selection or Selection()
    grouping = grouping or no_grouping()
    if not 0 <= tolerance_s <= 3600:
        raise AnalysisError(
            tr(
                "The time tolerance must be between 0 and 3600 s",
                "La tolérance en temps doit être entre 0 et 3600 s",
            )
        )
    frame = pair(reference, evaluated, selection, tolerance_s)
    if frame.empty:
        raise AnalysisError(
            tr(
                "The two series have no common time with valid values",
                "Les deux séries n'ont aucun instant commun avec des valeurs valides",
            )
        )
    check_grouping_timing(grouping, reference, "Comparison")
    is_circular = reference.meta.circular
    a, b = frame["reference"].to_numpy(), frame["evaluated"].to_numpy()
    overall = metrics(a, b, is_circular)
    masks, ungrouped = group_masks(grouping, pd.DatetimeIndex(frame.index))
    rows = [
        {**g, **metrics(a[m], b[m], is_circular)}
        for g, m in zip(grouping.groups, masks, strict=True)
    ]
    available = max(int(np.isfinite(selection.values(reference)).sum()), 1)
    keep = decimate(len(frame), SCATTER_LIMIT)
    qq = None
    if not is_circular:
        qq = {
            "quantiles": QUANTILES.tolist(),
            "reference": np.percentile(a, QUANTILES).tolist(),
            "evaluated": np.percentile(b, QUANTILES).tolist(),
        }
    notes = [*grouping.notes, *quality_notes([reference, evaluated], selection)]
    notes.append(
        tr("Differences are evaluated minus reference", "Les écarts sont évalué moins référence")
    )
    if tolerance_s > 0:
        notes.append(
            tr(
                f"Each reference time is paired with the nearest evaluated value within {tolerance_s:g} s",
                f"Chaque instant de référence est apparié à la valeur évaluée la plus proche à {tolerance_s:g} s près",
            )
        )
    if units.canonical(evaluated.meta.unit) != units.canonical(reference.meta.unit):
        notes.append(
            tr(
                f"{evaluated.meta.key} converted from {evaluated.meta.unit} to {reference.meta.unit}",
                f"{evaluated.meta.key} converti de {evaluated.meta.unit} en {reference.meta.unit}",
            )
        )
    if ungrouped:
        notes.append(
            tr(
                f"{ungrouped} pairs belong to no group",
                f"{ungrouped} paires n'appartiennent à aucun groupe",
            )
        )
    if len(frame) > SCATTER_LIMIT:
        notes.append(
            tr(
                f"Scatter plot drawn with {SCATTER_LIMIT} of {len(frame)} pairs (metrics use all pairs)",
                f"Nuage de points tracé avec {SCATTER_LIMIT} des {len(frame)} paires (les indicateurs utilisent toutes les paires)",
            )
        )
    return Result(
        kind="compare",
        method=tr(
            f"Comparison of {evaluated.meta.key} (evaluated) with {reference.meta.key} (reference)",
            f"Comparaison de {evaluated.meta.key} (évalué) avec {reference.meta.key} (référence)",
        ),
        data={
            "unit": reference.meta.unit,
            "circular": is_circular,
            "overall": overall,
            "groups": rows,
            "availability": {
                "pairs": len(frame),
                "reference_values": available,
                "share": len(frame) / available,
            },
            "scatter": {"reference": a[keep].tolist(), "evaluated": b[keep].tolist()},
            "qq": qq,
            "series": {
                "times": [t.isoformat() for t in frame.index[keep]],
                "reference": a[keep].tolist(),
                "evaluated": b[keep].tolist(),
            },
        },
        tables={
            "metrics": pd.DataFrame(
                [
                    {"group": "all", **overall},
                    *[
                        {"group": r["label"], **{k: v for k, v in r.items() if k not in ("label",)}}
                        for r in rows
                    ],
                ]
            ),
            "pairs": frame.reset_index(names="time"),
        },
        notes=notes,
        inputs=[describe(reference.meta), describe(evaluated.meta), *grouping.inputs],
        selection=selection,
    )
