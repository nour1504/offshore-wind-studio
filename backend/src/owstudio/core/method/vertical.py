"""Vertical levels as real.exe computes them (WRF 4.8), and their heights.

Ported from:
- dyn_em/module_initialize_real.F, compute_eta and levels: the full eta levels (znw), either
  given in eta_levels, or from auto_levels_opt = 2: a first layer dzbot thick, stretched by
  dzstretch_s near the surface and dzstretch_u above (the factor moves from one to the other as
  the layer thickness reaches max_dz / 2), until a constant thickness reaches the top p_top in an
  isothermal 290 K atmosphere; errors are those of real.exe;
- dyn_em/nest_init_utils.F, compute_vcoord_1d_coeffs: the hybrid coordinate (hybrid_opt), with
  B(eta) the share of the surface pressure in each level's pressure;
- dyn_em/module_initialize_real.F, the base state: surface pressure from the terrain height,
  temperature max(iso_temp, base_temp + base_lapse * ln(p / base_pres)), geopotential integrated
  from the terrain (hypsometric_opt 1 or 2).
Heights are those of WRF's reference atmosphere (base state); actual heights move a little with
the weather (temperature).
"""

import itertools
import math
from dataclasses import dataclass
from typing import Any

from owstudio.core.case.model import Case
from owstudio.core.i18n import tr
from owstudio.core.namelist.generate import build_namelist_input

# share/module_model_constants.F
G = 9.81
R_D = 287.0
CP = 7.0 * R_D / 2.0
CVPM = -(CP - R_D) / CP
P1000MB = 100000.0
T0 = 300.0
# Isothermal temperature of the levels routine
TT_LEVELS = 290.0


class VerticalError(ValueError):
    """A configuration real.exe refuses, with its explanation and a short keyword for the screen."""

    def __init__(self, message: str, keyword: str = "") -> None:
        super().__init__(message)
        self.keyword = keyword or message


@dataclass(frozen=True)
class VerticalSettings:
    e_vert: int
    p_top: float
    auto_levels_opt: int
    dzbot: float
    dzstretch_s: float
    dzstretch_u: float
    max_dz: float
    eta_levels: tuple[float, ...] | None
    hybrid_opt: int
    etac: float
    base_temp: float
    base_lapse: float
    iso_temp: float
    base_pres: float
    base_pres_strat: float
    base_lapse_strat: float
    hypsometric_opt: int


def _first(value: Any, default: Any) -> Any:
    if isinstance(value, list):
        return value[0] if value else default
    return default if value is None else value


def settings(case: Case) -> VerticalSettings:
    """The vertical options of the final namelist.input, with WRF 4.8's defaults."""
    nml = build_namelist_input(case)
    domains, dynamics = nml["domains"], nml.get("dynamics", {})
    eta = domains.get("eta_levels")
    levels = None
    if isinstance(eta, list) and eta and abs(float(eta[0]) + 1.0) > 1e-7:
        levels = tuple(float(v) for v in eta)
    elif isinstance(eta, (int, float)) and abs(float(eta) + 1.0) > 1e-7:
        levels = (float(eta),)
    return VerticalSettings(
        e_vert=int(_first(domains.get("e_vert"), case.grid.e_vert)),
        p_top=float(_first(domains.get("p_top_requested"), 5000.0)),
        auto_levels_opt=int(_first(domains.get("auto_levels_opt"), 2)),
        dzbot=float(_first(domains.get("dzbot"), 50.0)),
        dzstretch_s=float(_first(domains.get("dzstretch_s"), 1.3)),
        dzstretch_u=float(_first(domains.get("dzstretch_u"), 1.1)),
        max_dz=float(_first(domains.get("max_dz"), 1000.0)),
        eta_levels=levels,
        hybrid_opt=int(_first(dynamics.get("hybrid_opt"), 2)),
        etac=float(_first(dynamics.get("etac"), 0.2)),
        base_temp=float(_first(dynamics.get("base_temp"), 290.0)),
        base_lapse=float(_first(dynamics.get("base_lapse"), 50.0)),
        iso_temp=float(_first(dynamics.get("iso_temp"), 200.0)),
        base_pres=float(_first(dynamics.get("base_pres"), 100000.0)),
        base_pres_strat=float(_first(dynamics.get("base_pres_strat"), 0.0)),
        base_lapse_strat=float(_first(dynamics.get("base_lapse_strat"), -11.0)),
        hypsometric_opt=int(_first(domains.get("hypsometric_opt"), 2)),
    )


def auto_levels(
    nlev: int, ptop: float, dzmax: float, dzbot: float, s: float, u: float
) -> list[float]:
    """The levels routine: eta(0..nlev), from 1 at the surface to 0 at the top."""
    tt = TT_LEVELS
    ztop = R_D * tt / G * math.log(1.0e5 / ptop)

    def eta_of(z: float) -> float:
        p = 1.0e5 * math.exp(-G * z / R_D / tt)
        return (p - ptop) / (1.0e5 - ptop)

    eta = [0.0] * (nlev + 1)
    zup = [0.0] * (nlev + 1)
    dz = dzbot
    zup[1] = dz
    eta[0] = 1.0
    eta[1] = eta_of(zup[1])
    isave = 1
    for i in range(1, nlev):
        a = u + (s - u) * max((dzmax * 0.5 - dz) / (dzmax * 0.5), 0.0)
        dz = a * dz
        dztest = (ztop - zup[isave]) / (nlev - isave)
        if dztest < dz:
            break
        isave = i + 1
        zup[i + 1] = zup[i] + dz
        eta[i + 1] = eta_of(zup[i + 1])
        if i == nlev - 1:
            raise VerticalError(
                tr(
                    "not enough eta levels to reach p_top: more levels (e_vert), a lower top "
                    "(p_top_requested), a thicker first layer (dzbot) or more stretching "
                    "(dzstretch_s, dzstretch_u)",
                    "pas assez de niveaux pour atteindre le sommet : plus de niveaux (e_vert), un sommet plus bas (p_top_requested), une première couche plus épaisse (dzbot) ou plus d'étirement (dzstretch_s, dzstretch_u)",
                ),
                tr("Top not reached", "Sommet non atteint"),
            )
    dz = (ztop - zup[isave]) / (nlev - isave)
    if dz > 1.5 * dzmax:
        raise VerticalError(
            tr(
                f"upper levels too thick ({dz:.0f} m > 1.5 x max_dz): more levels (e_vert), a lower "
                "top (p_top_requested), a thicker first layer (dzbot), more stretching or a larger "
                "max_dz",
                f"niveaux du haut trop épais ({dz:.0f} m > 1,5 x max_dz) : plus de niveaux (e_vert), un sommet plus bas (p_top_requested), une première couche plus épaisse (dzbot), plus d'étirement ou un max_dz plus grand",
            ),
            tr("Upper layers > 1.5 x max_dz", "Couches du haut > 1,5 x max_dz"),
        )
    for i in range(isave, nlev):
        zup[i + 1] = zup[i] + dz
        eta[i + 1] = eta_of(zup[i + 1])
    eta[nlev] = 0.0
    return eta


def full_levels(s: VerticalSettings) -> list[float]:
    """znw, full eta levels from 1 (surface) to 0 (top), e_vert values."""
    if s.eta_levels is not None:
        eta = list(s.eta_levels)
        if len(eta) != s.e_vert:
            raise VerticalError(
                tr(
                    f"eta_levels has {len(eta)} values: it needs exactly e_vert = {s.e_vert}",
                    f"eta_levels compte {len(eta)} valeurs : il en faut exactement e_vert = {s.e_vert}",
                ),
                tr("eta: count \u2260 levels", "eta : nombre \u2260 niveaux"),
            )
        if abs(eta[-1] - 1.0) < 1e-7 and abs(eta[0]) < 1e-7:
            eta = eta[::-1]
        if abs(eta[0] - 1.0) >= 1e-7 or abs(eta[-1]) >= 1e-7:
            raise VerticalError(
                tr(
                    "the first eta level must be 1.0 and the last 0.0",
                    "le premier niveau eta doit valoir 1,0 et le dernier 0,0",
                ),
                tr("eta: from 1 to 0", "eta : de 1 \u00e0 0"),
            )
        if any(b >= a for a, b in itertools.pairwise(eta)):
            raise VerticalError(
                tr(
                    "eta_levels must decrease strictly from 1.0 to 0.0",
                    "eta_levels doit décroître strictement de 1,0 à 0,0",
                ),
                tr("eta: not decreasing", "eta : pas d\u00e9croissants"),
            )
        return eta
    if s.auto_levels_opt != 2:
        raise VerticalError(
            tr(
                "only auto_levels_opt = 2 or explicit eta_levels are shown",
                "seuls auto_levels_opt = 2 ou des eta_levels explicites sont calculés",
            ),
            "auto_levels_opt \u2260 2",
        )
    return auto_levels(s.e_vert - 1, s.p_top, s.max_dz, s.dzbot, s.dzstretch_s, s.dzstretch_u)


@dataclass(frozen=True)
class Coefficients:
    c3f: list[float]
    c4f: list[float]
    c3h: list[float]
    c4h: list[float]
    c1h: list[float]
    c2h: list[float]
    znu: list[float]


def coefficients(znw: list[float], hybrid_opt: int, etac: float, p_top: float) -> Coefficients:
    """compute_vcoord_1d_coeffs: B(eta) on full (c3f) and half levels, and the other terms."""
    kde = len(znw)
    c3f = []
    for k, eta in enumerate(znw):
        if hybrid_opt in (0, 1):
            value = eta
        elif hybrid_opt == 2:
            b1 = 2.0 * etac**2 * (1.0 - etac)
            b2 = -etac * (4.0 - 3.0 * etac - etac**3)
            b3 = 2.0 * (1.0 - etac**3)
            b4 = -(1.0 - etac**2)
            b5 = (1.0 - etac) ** 4
            value = (b1 + b2 * eta + b3 * eta**2 + b4 * eta**3) / b5
            if eta < etac:
                value = 0.0
            if k == 0:
                value = 1.0
            elif k == kde - 1:
                value = 0.0
        elif hybrid_opt == 3:
            value = eta * math.sin(0.5 * 3.14159 * eta) ** 2
            if k == 0:
                value = 1.0
            elif k == kde - 1:
                value = 0.0
        else:
            raise VerticalError(
                tr("hybrid_opt must be 0, 1, 2 or 3", "hybrid_opt doit valoir 0, 1, 2 ou 3"),
                "hybrid_opt ∉ {0, 1, 2, 3}",
            )
        c3f.append(value)
    c4f = [(znw[k] - c3f[k]) * (P1000MB - p_top) for k in range(kde)]
    znu = [(znw[k + 1] + znw[k]) * 0.5 for k in range(kde - 1)]
    c3h = [(c3f[k + 1] + c3f[k]) * 0.5 for k in range(kde - 1)]
    c4h = [(znu[k] - c3h[k]) * (P1000MB - p_top) for k in range(kde - 1)]
    c1h = [(c3f[k + 1] - c3f[k]) / (znw[k + 1] - znw[k]) for k in range(kde - 1)]
    c2h = [(1.0 - c1h[k]) * (P1000MB - p_top) for k in range(kde - 1)]
    return Coefficients(c3f, c4f, c3h, c4h, c1h, c2h, znu)


def column(
    s: VerticalSettings, znw: list[float], c: Coefficients, terrain_m: float = 0.0
) -> list[float]:
    """Heights above sea level (m) of the full levels over a terrain height, base state of
    real.exe; also checks the reference pressure decreases (else real.exe stops)."""
    p00, t00, a = s.base_pres, s.base_temp, s.base_lapse
    p_top = s.p_top
    p_surf = p00 * math.exp(-t00 / a + ((t00 / a) ** 2 - 2.0 * G * terrain_m / a / R_D) ** 0.5)
    mub = p_surf - p_top
    kde = len(znw)
    for k in range(kde - 1):
        below = c.c3f[k] * mub + c.c4f[k] + p_top
        above = c.c3f[k + 1] * mub + c.c4f[k + 1] + p_top
        if below - above <= 0:
            raise VerticalError(
                tr(
                    f"the reference pressure does not decrease above {terrain_m:.0f} m of terrain: "
                    "reduce etac",
                    f"la pression de référence ne décroît pas au-dessus de {terrain_m:.0f} m de relief : réduisez etac",
                ),
                tr("Pressure not decreasing: etac", "Pression non d\u00e9croissante : etac"),
            )
    alb = []
    for k in range(kde - 1):
        pb = c.c3h[k] * mub + c.c4h[k] + p_top
        temp = max(s.iso_temp, t00 + a * math.log(pb / p00))
        if pb < s.base_pres_strat:
            temp = s.iso_temp + s.base_lapse_strat * math.log(pb / s.base_pres_strat)
        t_init = temp * (p00 / pb) ** (R_D / CP) - T0
        alb.append((R_D / P1000MB) * (t_init + T0) * (pb / P1000MB) ** CVPM)
    phb = [terrain_m * G]
    for k in range(1, kde):
        if s.hypsometric_opt == 1:
            dnw = znw[k] - znw[k - 1]
            phb.append(phb[-1] - dnw * (c.c1h[k - 1] * mub + c.c2h[k - 1]) * alb[k - 1])
        else:
            pfu = c.c3f[k] * mub + c.c4f[k] + p_top
            pfd = c.c3f[k - 1] * mub + c.c4f[k - 1] + p_top
            phm = c.c3h[k - 1] * mub + c.c4h[k - 1] + p_top
            phb.append(phb[-1] + alb[k - 1] * phm * math.log(pfd / pfu))
    return [value / G for value in phb]


@dataclass(frozen=True)
class Level:
    # Full level number from 1 (surface) to e_vert (top)
    number: int
    eta: float
    # Above the ground, base state over a flat sea-level surface
    height_m: float
    # Thickness of the layer below this full level (0 for the surface)
    dz_m: float


@dataclass(frozen=True)
class Profile:
    settings: VerticalSettings
    full: list[Level]
    # Heights of the mass (half) levels: winds, temperature, time series profiles
    mass_heights_m: list[float]
    top_m: float


def profile(case: Case, terrain_m: float = 0.0) -> Profile:
    s = settings(case)
    znw = full_levels(s)
    c = coefficients(znw, s.hybrid_opt, s.etac, s.p_top)
    z = column(s, znw, c, terrain_m)
    heights = [value - terrain_m for value in z]
    full = [
        Level(k + 1, znw[k], heights[k], heights[k] - heights[k - 1] if k else 0.0)
        for k in range(len(znw))
    ]
    mass = [(heights[k] + heights[k + 1]) / 2 for k in range(len(heights) - 1)]
    return Profile(s, full, mass, heights[-1])
