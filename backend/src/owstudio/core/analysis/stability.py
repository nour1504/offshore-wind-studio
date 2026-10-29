"""Atmospheric stability classes from the Obukhov length or the bulk Richardson number.

Classification by the Obukhov length uses 1/L, which is continuous through neutral conditions
(|L| -> infinity, 1/L -> 0) and is what WRF stores (RMOL, "1./Monin Ob. Length" in
Registry.EM_COMMON; L > 0 stable, L < 0 unstable).
"""

from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np
import pandas as pd

from owstudio.core.analysis.common import (
    AnalysisError,
    Result,
    Selection,
    describe,
    in_unit,
    quality_notes,
)
from owstudio.core.i18n import tr
from owstudio.core.series import Series

Quantity = Literal["inverse_obukhov_length", "bulk_richardson"]
INF = float("inf")


@dataclass(frozen=True)
class StabilityClass:
    key: str
    label: str
    # Bounds on the classified quantity (1/L in m-1, or Ri_b)
    lower: float
    upper: float
    lower_closed: bool = True
    upper_closed: bool = False

    def contains(self, x: np.ndarray) -> np.ndarray:
        above = x >= self.lower if self.lower_closed else x > self.lower
        below = x <= self.upper if self.upper_closed else x < self.upper
        result: np.ndarray = above & below
        return result

    def describe(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "lower": self.lower,
            "upper": self.upper,
            "lower_closed": self.lower_closed,
            "upper_closed": self.upper_closed,
        }


@dataclass(frozen=True)
class Scheme:
    key: str
    title: str
    quantity: Quantity
    reference: str
    classes: tuple[StabilityClass, ...]
    notes: tuple[str, ...] = field(default_factory=tuple)

    def describe(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "quantity": self.quantity,
            "reference": self.reference,
            "classes": [c.describe() for c in self.classes],
            "notes": list(self.notes),
        }


GRYNING_REFERENCE = (
    "Gryning, S.-E., Batchvarova, E., Brümmer, B., Jørgensen, H., Larsen, S. (2007): On the "
    "extension of the wind profile over homogeneous terrain beyond the surface boundary layer. "
    "Boundary-Layer Meteorology 124, 251-268, Table 1 (the same limits are used by Sathe, A., "
    "Mann, J., Gottschall, J., Courtney, M. S. (2011), J. Atmos. Oceanic Technol. 28, 853-868)"
)


def gryning_2007(extended: bool = False) -> Scheme:
    """Seven classes by Obukhov length, expressed on 1/L. Boundary values belong to the class
    nearer to neutral. Without ``extended``, 0 < L < 10 m and -50 < L < 0 m are outside the
    scheme; with it they join the very stable and very unstable classes."""
    very_unstable = "L < 0 and L > -100 m" if extended else "-100 < L ≤ -50 m"
    very_stable = "0 < L < 50 m" if extended else "10 ≤ L < 50 m"
    classes = (
        StabilityClass(
            "very_unstable", tr(f"Very unstable ({very_unstable})", f"Très instable ({very_unstable})"), -INF if extended else -1 / 50,
            -1 / 100,
        ),
        StabilityClass("unstable", tr("Unstable (-200 < L ≤ -100 m)", "Instable (-200 < L ≤ -100 m)"), -1 / 100, -1 / 200),
        StabilityClass(
            "near_neutral_unstable", tr("Near-neutral unstable (-500 < L ≤ -200 m)", "Quasi neutre instable (-500 < L ≤ -200 m)"), -1 / 200, -1 / 500
        ),
        StabilityClass("neutral", tr("Neutral (|L| ≥ 500 m)", "Neutre (|L| ≥ 500 m)"), -1 / 500, 1 / 500, True, True),
        StabilityClass(
            "near_neutral_stable", tr("Near-neutral stable (200 ≤ L < 500 m)", "Quasi neutre stable (200 ≤ L < 500 m)"), 1 / 500, 1 / 200,
            False, True,
        ),
        StabilityClass("stable", "Stable (50 ≤ L < 200 m)", 1 / 200, 1 / 50, False, True),
        StabilityClass(
            "very_stable", tr(f"Very stable ({very_stable})", f"Très stable ({very_stable})"), 1 / 50, INF if extended else 1 / 10,
            False, True,
        ),
    )  # fmt: skip
    notes = [
        tr(
            "Limits of Gryning et al. (2007), Table 1, applied to 1/L; a value on a limit "
            "belongs to the class nearer to neutral.",
            "Limites de Gryning et al. (2007), tableau 1, appliquées à 1/L ; une valeur sur une "
            "limite appartient à la classe la plus proche de la neutralité.",
        )
    ]
    if extended:
        notes.append(
            tr(
                "Extended: 0 < L < 10 m counted as very stable and -50 < L < 0 m as very unstable "
                "(outside the published limits).",
                "Étendu : 0 < L < 10 m compté très stable et -50 < L < 0 m très instable (hors des limites publiées).",
            )
        )
    else:
        notes.append(
            tr(
                "0 < L < 10 m and -50 < L < 0 m are outside the published limits.",
                "0 < L < 10 m et -50 < L < 0 m sont hors des limites publiées.",
            )
        )
    return Scheme(
        "gryning2007-extended" if extended else "gryning2007",
        tr(
            "Obukhov length, 7 classes (Gryning et al. 2007)",
            "Longueur d'Obukhov, 7 classes (Gryning et al. 2007)",
        ),
        "inverse_obukhov_length",
        GRYNING_REFERENCE,
        classes,
        tuple(notes),
    )


def gryning_2007_three() -> Scheme:
    """The seven classes merged into unstable, neutral and stable (near-neutral classes join
    the unstable and stable sides)."""
    classes = (
        StabilityClass(
            "unstable",
            tr("Unstable (-500 < L ≤ -50 m)", "Instable (-500 < L ≤ -50 m)"),
            -1 / 50,
            -1 / 500,
        ),
        StabilityClass(
            "neutral",
            tr("Neutral (|L| ≥ 500 m)", "Neutre (|L| ≥ 500 m)"),
            -1 / 500,
            1 / 500,
            True,
            True,
        ),
        StabilityClass("stable", "Stable (10 ≤ L < 500 m)", 1 / 500, 1 / 10, False, True),
    )
    return Scheme(
        "gryning2007-3",
        tr(
            "Obukhov length, 3 classes (Gryning et al. 2007 merged)",
            "Longueur d'Obukhov, 3 classes (Gryning et al. 2007 regroupées)",
        ),
        "inverse_obukhov_length",
        GRYNING_REFERENCE,
        classes,
        (
            (
                tr(
                    "The seven classes of Gryning et al. (2007) merged: near-neutral unstable to very "
                    "unstable form 'unstable', near-neutral stable to very stable form 'stable'.",
                    "Les sept classes de Gryning et al. (2007) regroupées : de quasi neutre instable à "
                    "très instable forment « instable », de quasi neutre stable à très stable « stable ».",
                )
            ),
            "0 < L < 10 m and -50 < L < 0 m are outside the published limits.",
        ),
    )


STULL_REFERENCE = (
    "Stull, R. B. (1988): An Introduction to Boundary Layer Meteorology. Kluwer, Section 5.6 "
    "(critical Richardson number Rc = 0.25 from Miles 1961 and Howard 1961, J. Fluid Mech. 10; "
    "termination value RT = 1.0)"
)


def richardson(neutral_band: float = 0.0) -> Scheme:
    """Bulk Richardson number classes: sign for stable or unstable, the critical value 0.25 and
    the termination value 1.0 (Stull 1988). ``neutral_band`` (|Ri_b| at most this value is
    neutral) is the user's choice: no published value applies to every layer."""
    if not 0.0 <= neutral_band < 0.25:
        raise AnalysisError(
            tr(
                "The near-neutral band of Ri_b must be in [0, 0.25)",
                "La bande quasi neutre de Ri_b doit être dans [0, 0,25)",
            )
        )
    b = neutral_band
    classes = (
        StabilityClass(
            "unstable",
            tr(f"Unstable (Ri_b < -{b:g})", f"Instable (Ri_b < -{b:g})"),
            -INF,
            -b,
            False,
            False,
        ),
        StabilityClass(
            "neutral",
            tr(f"Neutral (|Ri_b| ≤ {b:g})", f"Neutre (|Ri_b| ≤ {b:g})"),
            -b,
            b,
            True,
            True,
        ),
        StabilityClass(
            "stable_turbulent", f"Stable, turbulent ({b:g} < Ri_b < 0.25)", b, 0.25, False, False
        ),
        StabilityClass(
            "stable_transitional",
            tr("Stable, transitional (0.25 ≤ Ri_b < 1)", "Stable, de transition (0.25 ≤ Ri_b < 1)"),
            0.25,
            1.0,
        ),
        StabilityClass(
            "stable_strong",
            tr(
                "Strongly stable, turbulence suppressed (Ri_b ≥ 1)",
                "Très stable, turbulence supprimée (Ri_b ≥ 1)",
            ),
            1.0,
            INF,
        ),
    )
    return Scheme(
        "richardson",
        tr(
            "Bulk Richardson number (Stull 1988 limits)",
            "Nombre de Richardson global (limites de Stull 1988)",
        ),
        "bulk_richardson",
        STULL_REFERENCE,
        classes,
        (
            (
                tr(
                    "The limits 0.25 and 1 come from the gradient Richardson number; applied to a bulk "
                    "number over a finite layer they are indicative only and depend on the layer depth.",
                    "Les limites 0,25 et 1 viennent du nombre de Richardson de gradient ; appliquées à un "
                    "nombre global sur une couche finie, elles sont indicatives et dépendent de l'épaisseur.",
                )
            ),
            tr(
                f"Near-neutral band |Ri_b| ≤ {b:g} chosen by the user (no universal value).",
                f"Bande quasi neutre |Ri_b| ≤ {b:g} choisie par l'utilisateur (pas de valeur universelle).",
            ),
        ),
    )


def scheme(key: str, neutral_band: float = 0.0) -> Scheme:
    if key == "gryning2007":
        return gryning_2007()
    if key == "gryning2007-extended":
        return gryning_2007(extended=True)
    if key == "gryning2007-3":
        return gryning_2007_three()
    if key == "richardson":
        return richardson(neutral_band)
    raise AnalysisError(
        tr(
            f"Unknown stability scheme {key!r} (known: {', '.join(SCHEME_KEYS)})",
            f"Classement de stabilité inconnu {key!r} (connus : {', '.join(SCHEME_KEYS)})",
        )
    )


SCHEME_KEYS = ("gryning2007", "gryning2007-extended", "gryning2007-3", "richardson")


def stability_quantity(series: Series, selection: Selection) -> tuple[Quantity, pd.Series, int]:
    """The classified quantity (1/L in m-1, or Ri_b), and the count of L = 0 values (invalid)."""
    variable = series.meta.variable
    values = selection.values(series)
    if variable == "obukhov_length":
        length = in_unit(series, values, "m", "an Obukhov length in metres").to_numpy()
        zero = int(np.sum(length == 0))
        with np.errstate(divide="ignore"):
            inverse = np.where(length == 0, np.nan, 1.0 / length)
        return "inverse_obukhov_length", pd.Series(inverse, index=values.index), zero
    if variable == "inverse_obukhov_length":
        if series.meta.unit.strip() not in ("m-1", "1/m", "m^-1"):
            raise AnalysisError(
                tr(
                    f"{series.meta.key}: 1/L must be in m-1, not {series.meta.unit!r}",
                    f"{series.meta.key} : 1/L doit être en m-1, pas en {series.meta.unit!r}",
                )
            )
        return "inverse_obukhov_length", values, 0
    if variable == "bulk_richardson":
        return "bulk_richardson", values, 0
    raise AnalysisError(
        tr(
            f"{series.meta.key} is {variable!r}: stability classes need obukhov_length, "
            "inverse_obukhov_length or bulk_richardson",
            f"{series.meta.key} est {variable!r} : les classes de stabilité demandent obukhov_length, inverse_obukhov_length ou bulk_richardson",
        )
    )


def classify(values: pd.Series, chosen: Scheme) -> pd.Series:
    """Class key for each value; '' outside the scheme, NaN where the value is missing."""
    x = values.to_numpy(dtype=float)
    labels = np.full(x.shape, "", dtype=object)
    for c in chosen.classes:
        labels[c.contains(x)] = c.key
    labels[np.isnan(x)] = np.nan
    return pd.Series(labels, index=values.index, dtype=object)


def classes_of(series: Series, chosen: Scheme, selection: Selection) -> tuple[pd.Series, int]:
    quantity, values, zero = stability_quantity(series, selection)
    if quantity != chosen.quantity:
        raise AnalysisError(
            tr(
                f"The scheme {chosen.key!r} classifies {chosen.quantity}, but {series.meta.key} gives "
                f"{quantity}",
                f"Le classement {chosen.key!r} porte sur {chosen.quantity}, mais {series.meta.key} donne {quantity}",
            )
        )
    return classify(values, chosen), zero


def stability_analysis(
    series: Series, scheme_key: str = "gryning2007", neutral_band: float = 0.0,
    selection: Selection | None = None,
) -> Result:  # fmt: skip
    """Class frequencies of a series of L, 1/L or Ri_b."""
    selection = selection or Selection()
    chosen = scheme(scheme_key, neutral_band)
    classes, zero = classes_of(series, chosen, selection)
    valid = classes.notna()
    n_valid = int(valid.sum())
    if n_valid == 0:
        raise AnalysisError(
            tr(
                f"{series.meta.key} has no valid value in the selected period",
                f"{series.meta.key} n'a aucune valeur valide sur la période choisie",
            )
        )
    rows = []
    for c in chosen.classes:
        count = int((classes == c.key).sum())
        rows.append({**c.describe(), "count": count, "frequency_pct": 100.0 * count / n_valid})
    outside = int((classes == "").sum())
    notes = [*chosen.notes, *quality_notes([series], selection)]
    if zero:
        notes.append(
            tr(
                f"{zero} values with L = 0 are meaningless and were left out",
                f"{zero} valeurs avec L = 0 n'ont pas de sens et ont été écartées",
            )
        )
    if outside:
        notes.append(
            tr(
                f"{outside} valid values fall outside the classes of the scheme",
                f"{outside} valeurs valides tombent hors des classes du classement",
            )
        )
    table = pd.DataFrame(rows)[["key", "label", "lower", "upper", "count", "frequency_pct"]]
    series_table = pd.DataFrame({"time": classes.index, "class": classes.to_numpy()})
    return Result(
        kind="stability",
        method=f"{chosen.title}. {chosen.reference}",
        data={
            "scheme": chosen.describe(),
            "classes": rows,
            "counts": {
                "values": len(classes),
                "valid": n_valid,
                "outside_scheme": outside,
                "outside_scheme_pct": 100.0 * outside / n_valid,
                "zero_length": zero,
            },
        },
        tables={"classes": table, "series": series_table},
        notes=notes,
        inputs=[describe(series.meta)],
        selection=selection,
    )


def bulk_richardson(
    theta_v_low: Series, theta_v_high: Series, u_low: Series, v_low: Series,
    u_high: Series, v_high: Series, selection: Selection | None = None,
) -> Series:  # fmt: skip
    """Bulk Richardson number between two heights (Stull 1988, Section 5.6):
    Ri_b = (g / θv_mean) Δθv Δz / (Δu² + Δv²), with θv_mean the mean of the two levels.
    NaN where the wind does not change with height (the number is undefined)."""
    selection = selection or Selection()
    levels = [theta_v_low, theta_v_high, u_low, v_low, u_high, v_high]
    for s in levels:
        if s.meta.height_m is None or s.meta.height_ref == "surface":
            raise AnalysisError(
                tr(
                    f"{s.meta.key} has no height: Ri_b needs two heights",
                    f"{s.meta.key} n'a pas de hauteur : Ri_b demande deux hauteurs",
                )
            )
    refs = {s.meta.height_ref for s in levels}
    if len(refs) > 1:
        raise AnalysisError(
            tr(
                "Heights mix above-ground and above-sea-level references",
                "Les hauteurs mélangent les références au-dessus du sol et au-dessus du niveau de la mer",
            )
        )
    z_low, z_high = theta_v_low.meta.height_m, theta_v_high.meta.height_m
    assert z_low is not None and z_high is not None
    if not (u_low.meta.height_m == v_low.meta.height_m == z_low) or not (
        u_high.meta.height_m == v_high.meta.height_m == z_high
    ):
        raise AnalysisError(
            tr(
                "Temperatures and wind components must be at the same two heights",
                "Les températures et les composantes du vent doivent être aux deux mêmes hauteurs",
            )
        )
    if z_high <= z_low:
        raise AnalysisError(
            tr(
                "The upper height must be above the lower height",
                "La hauteur supérieure doit être au-dessus de la hauteur inférieure",
            )
        )
    for s in (theta_v_low, theta_v_high):
        if s.meta.variable not in ("virtual_potential_temperature", "potential_temperature"):
            raise AnalysisError(
                tr(
                    f"{s.meta.key}: a (virtual) potential temperature is needed",
                    f"{s.meta.key} : une température potentielle (virtuelle) est nécessaire",
                )
            )
    frame = pd.concat(
        [
            in_unit(theta_v_low, selection.values(theta_v_low), "K", "a temperature"),
            in_unit(theta_v_high, selection.values(theta_v_high), "K", "a temperature"),
            in_unit(u_low, selection.values(u_low), "m s-1", "a wind component"),
            in_unit(v_low, selection.values(v_low), "m s-1", "a wind component"),
            in_unit(u_high, selection.values(u_high), "m s-1", "a wind component"),
            in_unit(v_high, selection.values(v_high), "m s-1", "a wind component"),
        ],
        axis=1,
        join="inner",
    ).dropna()
    t1, t2, u1, v1, u2, v2 = (frame.iloc[:, i].to_numpy() for i in range(6))
    shear2 = (u2 - u1) ** 2 + (v2 - v1) ** 2
    g = 9.81
    with np.errstate(divide="ignore", invalid="ignore"):
        ri = np.where(
            shear2 > 0, g / ((t1 + t2) / 2) * (t2 - t1) * (z_high - z_low) / shear2, np.nan
        )
    flags = []
    if "potential_temperature" in (theta_v_low.meta.variable, theta_v_high.meta.variable):
        flags.append(
            tr(
                "dry potential temperature used: the effect of humidity is neglected",
                "température potentielle sèche utilisée : l'effet de l'humidité est négligé",
            )
        )
    meta = theta_v_low.meta.model_copy(
        update={
            "variable": "bulk_richardson",
            "unit": "1",
            "source": "derived",
            "height_m": z_high,
            "method": f"derived: bulk Richardson number between {z_low:g} and {z_high:g} m "
            f"{theta_v_low.meta.height_ref} (g = 9.81 m s-2)",
            "flags": flags,
            "extra": {"lower_height_m": z_low, "upper_height_m": z_high},
        }
    )
    return Series(meta, pd.Series(ri, index=frame.index))
