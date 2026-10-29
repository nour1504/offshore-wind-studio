"""Weibull distributions of the wind speed: maximum likelihood, method of moments and the WAsP
fit (same mean cube and same frequency above the mean as the data), with goodness of fit, for
all directions and per direction sector.

The two-parameter Weibull distribution has the density f(u) = (k/A) (u/A)^(k-1) exp(-(u/A)^k)
and the cumulative distribution F(u) = 1 - exp(-(u/A)^k), for u > 0. Its moments are
E[U^n] = A^n Γ(1 + n/k).
"""

import math
from collections.abc import Callable, Sequence
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
    sector_labels,
)
from owstudio.core.analysis.wind import Wind
from owstudio.core.i18n import tr
from owstudio.core.series import circular

METHODS: dict[str, str] = {
    "mle": "maximum likelihood",
    "moments": "method of moments (mean and standard deviation)",
    "wasp": "WAsP fit (same mean cube of the speed and same frequency above the mean speed)",
}
METHODS_FR: dict[str, str] = {
    "mle": "maximum de vraisemblance",
    "moments": "méthode des moments (moyenne et écart-type)",
    "wasp": "ajustement WAsP (même moyenne du cube de la vitesse et même fréquence au-dessus de la "
    "vitesse moyenne)",
}
MIN_SAMPLES = 100
# Shape factors searched; wind speed distributions have k between about 1 and 5
K_LOW, K_HIGH = 0.1, 100.0
# Standard sea-level air density (ISA), used only for the indicative power density
RHO_STANDARD = 1.225


@dataclass(frozen=True)
class WeibullFit:
    method: str
    k: float
    A: float

    def cdf(self, u: np.ndarray) -> np.ndarray:
        x = np.clip(np.asarray(u, dtype=float), 0.0, None) / self.A
        result: np.ndarray = 1.0 - np.exp(-(x**self.k))
        return result

    def pdf(self, u: np.ndarray) -> np.ndarray:
        x = np.asarray(u, dtype=float) / self.A
        with np.errstate(divide="ignore", invalid="ignore"):
            density = (self.k / self.A) * x ** (self.k - 1.0) * np.exp(-(x**self.k))
        result: np.ndarray = np.where(x > 0, density, 0.0)
        return result

    def moment(self, n: int) -> float:
        """E[U^n] = A^n Γ(1 + n/k)."""
        return float(self.A**n * math.gamma(1.0 + n / self.k))


def _bisect(f: Callable[[float], float], low: float, high: float) -> float:
    """Root of an increasing or decreasing function with a sign change on [low, high], found
    on a logarithmic scale (the shape factor spans orders of magnitude)."""
    a, b = math.log(low), math.log(high)
    fa = f(low)
    for _ in range(200):
        m = 0.5 * (a + b)
        fm = f(math.exp(m))
        if fm == 0:
            return math.exp(m)
        if (fm > 0) == (fa > 0):
            a, fa = m, fm
        else:
            b = m
        if b - a < 1e-12:
            break
    return math.exp(0.5 * (a + b))


def fit_mle(u: np.ndarray) -> WeibullFit:
    """Maximum likelihood: k solves sum(u^k ln u)/sum(u^k) - 1/k - mean(ln u) = 0 (an
    increasing function of k with a single root), then A = mean(u^k)^(1/k)."""
    top = float(np.max(u))
    x, ln = u / top, np.log(u)
    mean_ln = float(np.mean(ln))
    if float(np.max(ln) - mean_ln) < 1e-12:
        raise AnalysisError(
            tr(
                "All wind speeds are equal: no Weibull distribution fits them",
                "Toutes les vitesses sont égales : aucune loi de Weibull ne s'y ajuste",
            )
        )

    def g(k: float) -> float:
        xk = x**k
        return float(np.sum(xk * ln) / np.sum(xk)) - 1.0 / k - mean_ln

    if g(K_LOW) > 0 or g(K_HIGH) < 0:
        raise AnalysisError(
            tr(
                f"The maximum likelihood shape factor is outside [{K_LOW:g}, {K_HIGH:g}]",
                f"Le facteur de forme du maximum de vraisemblance est hors de [{K_LOW:g}, {K_HIGH:g}]",
            )
        )
    k = _bisect(g, K_LOW, K_HIGH)
    return WeibullFit("mle", k, top * float(np.mean(x**k)) ** (1.0 / k))


def fit_moments(u: np.ndarray) -> WeibullFit:
    """Method of moments: k solves Γ(1+2/k)/Γ(1+1/k)² - 1 = (s/ū)² (s: standard deviation with
    n - 1), then A = ū / Γ(1+1/k)."""
    mean, std = float(np.mean(u)), float(np.std(u, ddof=1))
    cv2 = (std / mean) ** 2

    def h(k: float) -> float:
        return math.exp(math.lgamma(1 + 2 / k) - 2 * math.lgamma(1 + 1 / k)) - 1.0 - cv2

    if h(K_LOW) < 0 or h(K_HIGH) > 0:
        raise AnalysisError(
            tr(
                f"The coefficient of variation of the speeds ({math.sqrt(cv2):.3g}) gives a shape "
                f"factor outside [{K_LOW:g}, {K_HIGH:g}]",
                f"Le coefficient de variation des vitesses ({math.sqrt(cv2):.3g}) donne un facteur de forme hors de [{K_LOW:g}, {K_HIGH:g}]",
            )
        )
    k = _bisect(h, K_LOW, K_HIGH)
    return WeibullFit("moments", k, mean / math.gamma(1.0 + 1.0 / k))


def fit_wasp(u: np.ndarray) -> WeibullFit:
    """WAsP fit (European Wind Atlas, Troen and Petersen 1989): the fitted distribution has the
    observed mean of u³, A³ Γ(1+3/k) = mean(u³), and the observed frequency of speeds above
    the observed mean speed ū, exp(-(ū/A)^k) = Q. Eliminating A, k solves
    (k/3) ln(ū³ Γ(1+3/k) / mean(u³)) = ln(-ln Q)."""
    mean, cube = float(np.mean(u)), float(np.mean(u**3))
    q = float(np.mean(u > mean))
    if not 0 < q < 1:
        raise AnalysisError(
            tr(
                "No speed above (or below) the mean: the WAsP fit is undefined",
                "Aucune vitesse au-dessus (ou en dessous) de la moyenne : l'ajustement WAsP n'est pas défini",
            )
        )
    target = math.log(-math.log(q))

    def w(k: float) -> float:
        return (k / 3.0) * (3 * math.log(mean) + math.lgamma(1 + 3 / k) - math.log(cube)) - target

    grid = np.geomspace(0.3, 30.0, 600)
    values = np.array([w(float(k)) for k in grid])
    changes = np.flatnonzero(np.sign(values[:-1]) != np.sign(values[1:]))
    if changes.size != 1:
        raise AnalysisError(
            tr(
                "The WAsP equations have "
                + ("no solution" if changes.size == 0 else f"{changes.size} solutions")
                + " for shape factors between 0.3 and 30: this sample is not Weibull-like",
                "Les équations de WAsP ont "
                + ("aucune solution" if changes.size == 0 else f"{changes.size} solutions")
                + " pour des facteurs de forme entre 0,3 et 30 : cet échantillon ne ressemble pas à une loi de Weibull",
            )
        )
    i = int(changes[0])
    k = _bisect(w, float(grid[i]), float(grid[i + 1]))
    return WeibullFit("wasp", k, (cube / math.gamma(1.0 + 3.0 / k)) ** (1.0 / 3.0))


FITTERS: dict[str, Callable[[np.ndarray], WeibullFit]] = {
    "mle": fit_mle,
    "moments": fit_moments,
    "wasp": fit_wasp,
}


def goodness(fit: WeibullFit, u: np.ndarray) -> dict[str, float]:
    """R² between the empirical and fitted cumulative distributions at the distinct observed
    speeds, and the Kolmogorov-Smirnov statistic D = sup |F_n - F| (no p-value: successive
    wind speeds are correlated and the parameters come from the same data)."""
    distinct, counts = np.unique(u, return_counts=True)
    n = float(u.size)
    after = np.cumsum(counts) / n
    before = after - counts / n
    fitted = fit.cdf(distinct)
    ks = float(max(np.max(np.abs(after - fitted)), np.max(np.abs(before - fitted))))
    total = float(np.sum((after - np.mean(after)) ** 2))
    r2 = 1.0 - float(np.sum((after - fitted) ** 2)) / total if total > 0 else float("nan")
    return {"r2_cdf": r2, "ks": ks}


def observed(u: np.ndarray) -> dict[str, float]:
    mean = float(np.mean(u))
    cube = float(np.mean(u**3))
    return {
        "count": int(u.size),
        "mean": mean,
        "std": float(np.std(u, ddof=1)) if u.size > 1 else float("nan"),
        "mean_cube": cube,
        "power_density": 0.5 * RHO_STANDARD * cube,
        "share_above_mean": float(np.mean(u > mean)),
    }


def fit_all(u: np.ndarray, methods: Sequence[str], min_samples: int) -> dict[str, object]:
    """Every requested fit of the positive speeds ``u``, with its goodness of fit; a failed fit
    gives its reason instead of parameters."""
    if u.size < min_samples:
        return {
            "observed": observed(u) if u.size > 1 else {"count": int(u.size)},
            "fits": {},
            "refused": f"{u.size} samples, fewer than the minimum of {min_samples} for a fit",
        }
    obs = observed(u)
    fits: dict[str, object] = {}
    for method in methods:
        try:
            fit = FITTERS[method](u)
        except AnalysisError as error:
            fits[method] = {"method": method, "refused": str(error)}
            continue
        cube = fit.moment(3)
        fits[method] = {
            "method": method,
            "k": fit.k,
            "A": fit.A,
            "mean": fit.moment(1),
            "mean_cube": cube,
            "power_density": 0.5 * RHO_STANDARD * cube,
            "mean_cube_ratio": cube / obs["mean_cube"],
            "share_above_mean": float(math.exp(-((obs["mean"] / fit.A) ** fit.k))),
            **goodness(fit, u),
        }
    return {"observed": obs, "fits": fits, "refused": None}


def weibull_analysis(
    wind: Wind,
    methods: Sequence[str] = ("mle", "moments", "wasp"),
    sectors: int = 0,
    min_samples: int = MIN_SAMPLES,
    bin_width: float = 1.0,
    selection: Selection | None = None,
) -> Result:
    """Weibull fits of the wind speeds above 0, for all directions and, with ``sectors`` > 0
    and a direction series, per direction sector; curves and histogram for plotting."""
    selection = selection or Selection()
    unknown = [m for m in methods if m not in METHODS]
    if unknown or not methods:
        raise AnalysisError(
            tr(
                f"Weibull methods must be among {', '.join(METHODS)}",
                f"Les méthodes de Weibull doivent être parmi {', '.join(METHODS)}",
            )
        )
    if min_samples < 20:
        raise AnalysisError(
            tr(
                "A Weibull fit needs at least 20 samples",
                "Un ajustement de Weibull demande au moins 20 échantillons",
            )
        )
    if not 0.05 <= bin_width <= 5:
        raise AnalysisError(
            tr(
                "The histogram bin width must be between 0.05 and 5 m/s",
                "La largeur des classes de l'histogramme doit être entre 0,05 et 5 m/s",
            )
        )
    if sectors:
        check_sectors(sectors)
    frame = wind.frame(selection, need_direction=bool(sectors))
    speed = frame["speed"].to_numpy()
    valid = np.isfinite(speed)
    positive = valid & (speed > 0)
    zeros = int(np.sum(valid & (speed == 0)))
    u = speed[positive]
    overall = fit_all(u, methods, min_samples)
    if overall["refused"]:
        raise AnalysisError(f"{wind.key}: {overall['refused']}")
    notes = [*wind.notes(), *quality_notes(wind.series, selection)]
    notes.append(
        tr(
            "Fits use the speeds above 0 m/s; speeds of exactly 0 are counted separately (a "
            "Weibull distribution has no mass at 0)",
            "Les ajustements utilisent les vitesses au-dessus de 0 m/s ; les vitesses d'exactement 0 sont comptées à part (une loi de Weibull n'a pas de masse en 0)",
        )
    )
    if zeros:
        notes.append(
            tr(
                f"{zeros} speeds of 0 m/s ({100.0 * zeros / int(valid.sum()):.2f} %) left out",
                f"{zeros} vitesses de 0 m/s ({100.0 * zeros / int(valid.sum()):.2f} %) écartées",
            )
        )
    notes.append(
        tr(
            "Successive samples are correlated, so the number of independent samples is smaller "
            "than the count; no p-value is given for the Kolmogorov-Smirnov statistic",
            "Des échantillons successifs sont corrélés : le nombre d'échantillons indépendants est plus petit que leur nombre ; aucune valeur p n'est donnée pour la statistique de Kolmogorov-Smirnov",
        )
    )

    top = math.ceil(float(np.max(u)) * 1.05)
    grid = np.round(np.arange(0.0, top + 0.05, 0.1), 6)
    curves: dict[str, list[float]] = {"speed": grid.tolist()}
    fitted = {m: f for m, f in overall["fits"].items() if "k" in f}  # type: ignore[attr-defined]
    for m, f in fitted.items():
        curves[m] = WeibullFit(m, f["k"], f["A"]).pdf(grid).tolist()
    edges = np.arange(0.0, top + bin_width, bin_width)
    counts, _ = np.histogram(u, bins=edges)
    density = counts / (u.size * bin_width)
    # Every valid speed, calms of 0 m/s included (in the first class): the share of time
    every = speed[valid]
    counts_all, _ = np.histogram(every, bins=edges)

    sector_rows: list[dict[str, object]] = []
    fit_rows = [_fit_row("all", None, overall)]
    if sectors:
        direction = frame["direction"].to_numpy()
        with_direction = positive & np.isfinite(direction)
        missing = int(np.sum(positive & ~np.isfinite(direction)))
        if missing:
            notes.append(
                tr(
                    f"{missing} speeds without direction are left out of the sector fits",
                    f"{missing} vitesses sans direction sont écartées des ajustements par secteur",
                )
            )
        index = circular.sector(np.where(with_direction, direction, np.nan), sectors)
        total = int(with_direction.sum())
        for info in sector_labels(sectors):
            us = speed[with_direction & (index == info["sector"])]
            result = fit_all(us, methods, min_samples)
            row = {
                **info,
                "count": int(us.size),
                "frequency_pct": 100.0 * us.size / total if total else None,
                **result,
                "curves": {
                    m: WeibullFit(m, f["k"], f["A"]).pdf(grid).tolist()
                    for m, f in result["fits"].items()  # type: ignore[attr-defined]
                    if "k" in f
                },
            }
            sector_rows.append(row)
            fit_rows.append(_fit_row("sector", info["sector"], result))
    table = pd.DataFrame([r for rows in fit_rows for r in rows])
    return Result(
        kind="weibull",
        method=tr(
            "Weibull fits of the wind speed: "
            + "; ".join(METHODS[m] for m in methods)
            + (f"; per sector ({sectors} sectors, sector 0 centred on north)" if sectors else ""),
            "Ajustements de Weibull de la vitesse du vent : "
            + " ; ".join(METHODS_FR[m] for m in methods)
            + (
                f" ; par secteur ({sectors} secteurs, secteur 0 centré sur le nord)"
                if sectors
                else ""
            ),
        ),
        data={
            "methods": list(methods),
            "samples": {
                "total": len(speed),
                "valid": int(valid.sum()),
                "zero": zeros,
                "fitted": int(u.size),
            },
            "all": overall,
            # Statistics of every valid speed, calms included (the fits use the positive ones)
            "observed_all": observed(every),
            "sectors": sector_rows,
            "curves": curves,
            "histogram": {
                "edges": edges.tolist(),
                "counts": counts.tolist(),
                "counts_all": counts_all.tolist(),
                "density": density.tolist(),
            },
            "air_density_for_power_density": RHO_STANDARD,
        },
        tables={
            "fits": table,
            "curves": pd.DataFrame(curves),
            "histogram": pd.DataFrame(
                {"lower": edges[:-1], "upper": edges[1:], "count": counts, "density": density}
            ),
        },
        notes=notes,
        inputs=[describe(s.meta) for s in wind.series],
        selection=selection,
    )


def _fit_row(scope: str, sector: int | None, result: dict[str, object]) -> list[dict[str, object]]:
    obs: dict[str, object] = result["observed"]  # type: ignore[assignment]
    fits: dict[str, dict[str, object]] = result["fits"]  # type: ignore[assignment]
    base = {"scope": scope, "sector": sector, "count": obs.get("count"), "mean": obs.get("mean")}
    if not fits:
        return [{**base, "method": None, "refused": result["refused"]}]
    return [
        {
            **base,
            "method": m,
            "k": f.get("k"),
            "A": f.get("A"),
            "fitted_mean": f.get("mean"),
            "mean_cube_ratio": f.get("mean_cube_ratio"),
            "r2_cdf": f.get("r2_cdf"),
            "ks": f.get("ks"),
            "refused": f.get("refused"),
        }
        for m, f in fits.items()
    ]
