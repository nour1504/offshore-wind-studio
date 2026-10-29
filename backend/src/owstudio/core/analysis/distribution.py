"""Distributions of any variable, statistics per group (direction sector, stability class, value
bin, hour, month), time aggregation with an availability threshold, and daily or yearly cycles.

Directions are never averaged arithmetically: their statistics are circular (mean of unit
vectors, Yamartino standard deviation)."""

from collections.abc import Sequence

import numpy as np
import pandas as pd

from owstudio.core.analysis.common import (
    AnalysisError,
    Grouping,
    Result,
    Selection,
    check_edges,
    check_grouping_timing,
    describe,
    group_masks,
    label_shift,
    no_grouping,
    quality_notes,
    sampling_step,
    stats,
)
from owstudio.core.i18n import tr

PERIOD_FR = {"hour": "heure", "day": "jour", "month": "mois"}
from owstudio.core.series import Series, circular

PERIODS = {"hour": ("h", 3600.0), "day": ("D", 86400.0), "month": ("MS", None)}


def histogram(
    series: Series,
    edges: Sequence[float] | None = None,
    bins: int = 30,
    selection: Selection | None = None,
) -> Result:
    """Counts and densities of the values in bins [lower, upper), with descriptive statistics.
    Without edges, ``bins`` equal bins span the observed range."""
    selection = selection or Selection()
    values = selection.values(series).to_numpy(dtype=float)
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        raise AnalysisError(
            tr(
                f"{series.meta.key} has no valid value in the selected period",
                f"{series.meta.key} n'a aucune valeur valide sur la période choisie",
            )
        )
    if edges is not None:
        e = check_edges(edges, "Histogram")
    else:
        if not 2 <= bins <= 500:
            raise AnalysisError(
                tr(
                    "The number of bins must be between 2 and 500",
                    "Le nombre de classes doit être entre 2 et 500",
                )
            )
        low, high = float(np.min(finite)), float(np.max(finite))
        if series.meta.circular:
            low, high = 0.0, 360.0
        if high <= low:
            high = low + 1.0
        e = np.linspace(low, high, bins + 1)
    counts, _ = np.histogram(finite, bins=e)
    widths = np.diff(e)
    outside = int(finite.size - counts.sum())
    notes = quality_notes([series], selection)
    if outside:
        notes.append(
            tr(
                f"{outside} values outside the bin edges are not counted",
                f"{outside} valeurs hors des bornes des classes ne sont pas comptées",
            )
        )
    density = counts / (finite.size * widths)
    table = pd.DataFrame(
        {
            "lower": e[:-1],
            "upper": e[1:],
            "count": counts,
            "frequency_pct": 100.0 * counts / finite.size,
            "density": density,
        }
    )
    return Result(
        kind="histogram",
        method=tr(
            f"Histogram of {series.meta.variable} ({series.meta.unit}), bins include their lower edge",
            f"Histogramme de {series.meta.variable} ({series.meta.unit}), chaque classe inclut sa borne inférieure",
        ),
        data={
            "unit": series.meta.unit,
            "edges": e.tolist(),
            "counts": counts.tolist(),
            "frequency_pct": (100.0 * counts / finite.size).tolist(),
            "density": density.tolist(),
            "statistics": stats(finite, series.meta.circular),
            "samples": {"total": int(values.size), "valid": int(finite.size), "outside": outside},
        },
        tables={"histogram": table},
        notes=notes,
        inputs=[describe(series.meta)],
        selection=selection,
    )


def grouped(
    series: Series, grouping: Grouping | None = None, selection: Selection | None = None
) -> Result:
    """Descriptive statistics of a series for each group of a grouping (all values without one):
    count, mean, standard deviation, percentiles; circular statistics for directions."""
    selection = selection or Selection()
    grouping = grouping or no_grouping()
    check_grouping_timing(grouping, series, "Statistics per group")
    values = selection.values(series)
    masks, ungrouped = group_masks(grouping, pd.DatetimeIndex(values.index))
    x = values.to_numpy(dtype=float)
    valid = int(np.isfinite(x).sum())
    rows = []
    for group, mask in zip(grouping.groups, masks, strict=True):
        s = stats(x[mask], series.meta.circular)
        rows.append({**group, **s, "share_pct": 100.0 * s["count"] / valid if valid else None})
    notes = [*grouping.notes, *quality_notes([series], selection)]
    if ungrouped:
        notes.append(
            tr(
                f"{ungrouped} times belong to no group (missing class, sector or bin)",
                f"{ungrouped} instants n'appartiennent à aucun groupe (classe, secteur ou intervalle manquant)",
            )
        )
    if series.meta.circular:
        notes.append(
            tr(
                "Directions: circular mean of unit vectors and Yamartino standard deviation",
                "Directions : moyenne circulaire des vecteurs unitaires et écart-type de Yamartino",
            )
        )
    return Result(
        kind="grouped",
        method=tr(
            f"Statistics of {series.meta.key} per group: {grouping.title}",
            f"Statistiques de {series.meta.key} par groupe : {grouping.title}",
        ),
        data={
            "grouping": {"key": grouping.key, "title": grouping.title},
            "groups": rows,
            "unit": series.meta.unit,
        },
        tables={"groups": pd.DataFrame(rows)},
        notes=notes,
        inputs=[describe(series.meta), *grouping.inputs],
        selection=selection,
    )


def aggregate(
    series: Series,
    period: str = "hour",
    min_availability: float = 0.7,
    selection: Selection | None = None,
) -> Result:
    """Means over hours, days or calendar months (UTC), kept only where enough of the expected
    values are present. Averages are assigned to their period by the centre of each value's own
    averaging period; directions use circular means."""
    selection = selection or Selection()
    if period not in PERIODS:
        raise AnalysisError(
            tr(
                f"Unknown aggregation period {period!r} (hour, day or month)",
                f"Période d'agrégation inconnue {period!r} (heure, jour ou mois)",
            )
        )
    if not 0 < min_availability <= 1:
        raise AnalysisError(
            tr(
                "The minimum availability must be in (0, 1]",
                "La disponibilité minimale doit être dans (0, 1]",
            )
        )
    rule, length = PERIODS[period]
    step = sampling_step(series)
    if step is None:
        raise AnalysisError(
            tr(
                f"{series.meta.key} has irregular time steps: the availability of each period cannot be "
                "computed; resample it first",
                f"{series.meta.key} a des pas de temps irréguliers : la disponibilité de chaque période ne peut pas être calculée ; rééchantillonnez-la d'abord",
            )
        )
    if length is not None and step > length:
        raise AnalysisError(
            tr(
                f"{series.meta.key} has one value every {step:g} s: too coarse for {period} means",
                f"{series.meta.key} a une valeur toutes les {step:g} s : trop espacé pour des moyennes par {period}",
            )
        )
    values = selection.values(series)
    shifted = values.copy()
    shifted.index = pd.DatetimeIndex(values.index) + label_shift(series.meta, "centre")
    groups = shifted.resample(rule)
    if series.meta.circular:
        means = groups.apply(lambda v: circular.mean(v.to_numpy()))
    else:
        means = groups.mean()
    counts = groups.count()
    if length is not None:
        expected = pd.Series(length / step, index=counts.index)
    else:
        expected = pd.Series(
            [pd.Timestamp(t).days_in_month * 86400.0 / step for t in counts.index],
            index=counts.index,
        )
    availability = (counts / expected).clip(upper=1.0)
    kept = means.where(availability >= min_availability)
    table = pd.DataFrame(
        {
            "period_start": counts.index,
            "mean": kept.to_numpy(),
            "count": counts.to_numpy(),
            "availability": availability.to_numpy(),
        }
    )
    rejected = int(((availability < min_availability) & (counts > 0)).sum())
    notes = quality_notes([series], selection)
    notes.append(
        tr(
            f"Periods with less than {100 * min_availability:g} % of the expected values are left empty",
            f"Les périodes avec moins de {100 * min_availability:g} % des valeurs attendues restent vides",
        )
    )
    if rejected:
        notes.append(
            tr(
                f"{rejected} periods rejected for low availability",
                f"{rejected} périodes rejetées pour disponibilité insuffisante",
            )
        )
    if series.meta.circular:
        notes.append(
            tr(
                "Directions: circular mean of unit vectors",
                "Directions : moyenne circulaire des vecteurs unitaires",
            )
        )
    return Result(
        kind="aggregate",
        method=tr(
            f"{period.capitalize()} means (UTC periods) of {series.meta.key}",
            f"Moyennes par {PERIOD_FR.get(period, period)} (périodes UTC) de {series.meta.key}",
        ),
        data={
            "period": period,
            "unit": series.meta.unit,
            "times": [t.isoformat() for t in counts.index],
            "mean": kept.tolist(),
            "count": counts.tolist(),
            "availability": availability.tolist(),
            "statistics": stats(kept.to_numpy(dtype=float), series.meta.circular),
        },
        tables={"aggregate": table},
        notes=notes,
        inputs=[describe(series.meta)],
        selection=selection,
    )
