"""Physical quantities computed from WRF history variables, at a height or at the surface.

The same formulas serve time series at a point (on the 2 x 2 window of mass points around it)
and maps (on the whole grid at one time): arrays end with the (south_north, west_east) axes.

Conventions and constants (as in WRF): g = 9.81 m s-2, Rd = 287 J kg-1 K-1, cp = 7 Rd / 2 =
1004.5 J kg-1 K-1, p0 = 1000 hPa, Rv/Rd - 1 = 0.608, von Kármán constant 0.4, Lv = 2.5e6 J kg-1.
Winds are rotated from grid-relative to earth-relative with COSALPHA and SINALPHA:
u_earth = u cosα - v sinα, v_earth = v cosα + u sinα (as WRF's own share/wrf_timeseries.F).
Heights of the mass levels are the average of the geopotential heights (PH + PHB)/g of the
levels around them, above ground once HGT is subtracted. Values are interpolated linearly in
height between model levels; heights below the lowest mass level or above the top give no value
(no extrapolation).
"""

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from owstudio.core.i18n import tr
from owstudio.core.series import circular

G, RD, P0, KARMAN, LV = 9.81, 287.0, 1.0e5, 0.4, 2.5e6
CP = 3.5 * RD
EPS = 0.608
# |1/L| below this (|L| above 10^6 m) is neutral: the Obukhov length itself is not given
NEUTRAL_INVERSE_L = 1.0e-6

Get = Callable[[str], np.ndarray]


@dataclass
class Computed:
    values: np.ndarray
    unit: str
    method: str
    flags: list[str] = field(default_factory=list)


class Unavailable(LookupError):
    """The quantity cannot be computed from these files; the message says what is missing."""


def _require(has: Callable[[str], bool], *names: str) -> None:
    missing = [n for n in names if not has(n)]
    if missing:
        raise Unavailable(
            tr(
                f"missing in the history files: {', '.join(missing)}",
                f"absent des fichiers d'historique : {', '.join(missing)}",
            )
        )


def heights_agl(get: Get) -> np.ndarray:
    z_stag = (get("PH") + get("PHB")) / G
    z = 0.5 * (z_stag[:, :-1] + z_stag[:, 1:])
    result: np.ndarray = z - get("HGT")[:, None]
    return result


def at_height(field3d: np.ndarray, z: np.ndarray, target: float) -> tuple[np.ndarray, int]:
    """Linear interpolation in height of (time, level, ...) fields at ``target`` metres; returns
    the values (time, ...) and the count of columns where the target is outside the levels."""
    below = z < target
    k = below.sum(axis=1) - 1
    valid = (k >= 0) & (k < z.shape[1] - 1)
    kk = np.clip(k, 0, z.shape[1] - 2)[:, None]
    z0 = np.take_along_axis(z, kk, axis=1)[:, 0]
    z1 = np.take_along_axis(z, kk + 1, axis=1)[:, 0]
    f0 = np.take_along_axis(field3d, kk, axis=1)[:, 0]
    f1 = np.take_along_axis(field3d, kk + 1, axis=1)[:, 0]
    with np.errstate(invalid="ignore", divide="ignore"):
        result = f0 + (target - z0) / (z1 - z0) * (f1 - f0)
    return np.where(valid, result, np.nan), int((~valid).sum())


def earth_winds(get: Get, u: str, v: str) -> tuple[np.ndarray, np.ndarray]:
    cosa, sina = get("COSALPHA"), get("SINALPHA")
    uu, vv = get(u), get(v)
    if uu.ndim == 4:
        cosa, sina = cosa[:, None], sina[:, None]
    return uu * cosa - vv * sina, vv * cosa + uu * sina


WIND = ("wind_speed", "wind_direction", "u", "v")
LEVEL_QUANTITIES = (
    *WIND, "temperature", "potential_temperature", "virtual_potential_temperature", "pressure",
    "density", "mixing_ratio", "tke",
)  # fmt: skip
SURFACE = {
    "pblh": ("PBLH", "m"),
    "friction_velocity": ("UST", "m s-1"),
    "sensible_heat_flux": ("HFX", "W m-2"),
    "latent_heat_flux": ("LH", "W m-2"),
    "moisture_flux": ("QFX", "kg m-2 s-1"),
    "sst": ("SST", "K"),
    "skin_temperature": ("TSK", "K"),
    "surface_pressure": ("PSFC", "Pa"),
    "roughness_length": ("ZNT", "m"),
    "power": ("POWER", "W"),
}


def wind_quantity(name: str, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    if name == "wind_speed":
        speed: np.ndarray = np.hypot(u, v)
        return speed
    if name == "wind_direction":
        return circular.from_components(u, v)
    return u if name == "u" else v


def level_field(name: str, get: Get, has: Callable[[str], bool]) -> tuple[np.ndarray, str, str]:
    """A quantity on the mass levels: (time, level, ...) values, unit and method."""
    if name in WIND:
        _require(has, "U", "V", "COSALPHA", "SINALPHA")
        u, v = earth_winds(get, "U", "V")
        unit = "deg" if name == "wind_direction" else "m s-1"
        return (
            wind_quantity(name, u, v),
            unit,
            tr(
                "U and V destaggered to mass points, rotated to earth-relative",
                "U et V ramenés aux points de masse, tournés dans le repère terrestre",
            ),
        )
    if name in ("potential_temperature", "virtual_potential_temperature", "temperature", "density"):
        _require(has, "T", *(("P", "PB") if name in ("temperature", "density") else ()))
        theta = get("T") + 300.0
        if name == "potential_temperature":
            return (
                theta,
                "K",
                tr(
                    "T + 300 K (WRF perturbation potential temperature)",
                    "T + 300 K (perturbation de température potentielle de WRF)",
                ),
            )
        qv = get("QVAPOR") if has("QVAPOR") else np.zeros_like(theta)
        if name == "virtual_potential_temperature":
            return theta * (1 + EPS * qv), "K", tr("θ (1 + 0.608 qv)", "θ (1 + 0,608 qv)")
        p = get("P") + get("PB")
        temperature = theta * (p / P0) ** (RD / CP)
        if name == "temperature":
            return temperature, "K", "θ (p / p0)^(Rd/cp), p = P + PB"
        return (
            p / (RD * temperature * (1 + EPS * qv)),
            "kg m-3",
            tr("p / (Rd T (1 + 0.608 qv))", "p / (Rd T (1 + 0,608 qv))"),
        )
    if name == "pressure":
        _require(has, "P", "PB")
        return get("P") + get("PB"), "Pa", "P + PB"
    if name == "mixing_ratio":
        _require(has, "QVAPOR")
        return get("QVAPOR"), "kg kg-1", "QVAPOR"
    if name == "tke":
        if has("QKE"):
            return (
                get("QKE") / 2.0,
                "m2 s-2",
                tr(
                    "QKE / 2 (MYNN: QKE is twice the TKE)",
                    "QKE / 2 (MYNN : QKE vaut deux fois la TKE)",
                ),
            )
        if has("TKE_PBL"):
            return get("TKE_PBL"), "m2 s-2", "TKE_PBL"
        raise Unavailable(
            tr(
                "no TKE in the history files (QKE or TKE_PBL; MYNN writes QKE)",
                "pas de TKE dans les fichiers d'historique (QKE ou TKE_PBL ; MYNN écrit QKE)",
            )
        )
    raise Unavailable(tr(f"unknown quantity {name!r}", f"grandeur inconnue {name!r}"))


def inverse_obukhov(get: Get, has: Callable[[str], bool]) -> Computed:
    """1/L: RMOL when WRF wrote it, otherwise from the surface fluxes."""
    if has("RMOL"):
        return Computed(
            get("RMOL"),
            "m-1",
            tr(
                "RMOL written by WRF (1/L of the surface layer scheme)",
                "RMOL écrit par WRF (1/L du schéma de couche de surface)",
            ),
        )
    _require(has, "UST", "HFX", "T2", "PSFC", "Q2")
    t2, psfc, q2, ust = get("T2"), get("PSFC"), get("Q2"), get("UST")
    theta = get("TH2") if has("TH2") else t2 * (P0 / psfc) ** (RD / CP)
    rho = psfc / (RD * t2 * (1 + EPS * q2))
    if has("QFX"):
        moisture = get("QFX") / rho
        source = "QFX"
    else:
        _require(has, "LH")
        moisture = get("LH") / (rho * LV)
        source = "LH / Lv"
    buoyancy_flux = get("HFX") / (rho * CP) + EPS * theta * moisture
    theta_v = theta * (1 + EPS * q2)
    with np.errstate(divide="ignore", invalid="ignore"):
        inverse = -KARMAN * G * buoyancy_flux / (ust**3 * theta_v)
    inverse = np.where(ust > 0, inverse, np.nan)
    return Computed(
        inverse,
        "m-1",
        tr(
            f"1/L = -κ g w'θv' / (u*³ θv) from UST, HFX, {source}, T2, Q2, PSFC (w'θv' = HFX/(ρ cp) + 0.608 θ E/ρ)",
            f"1/L = -κ g w'θv' / (u*³ θv) tiré de UST, HFX, {source}, T2, Q2, PSFC (w'θv' = HFX/(ρ cp) + 0,608 θ E/ρ)",
        ),
        [
            tr(
                "derived from 2 m and surface fluxes, not the value used inside WRF's surface layer scheme",
                "tiré des valeurs à 2 m et des flux de surface, pas de la valeur utilisée dans le schéma de couche de surface de WRF",
            )
        ],
    )


def surface_field(name: str, get: Get, has: Callable[[str], bool]) -> Computed:
    """A quantity without height: (time, ...) values."""
    if name in SURFACE:
        variable, unit = SURFACE[name]
        _require(has, variable)
        flags = (
            [
                tr(
                    "power of all turbines in the grid cell",
                    "puissance de toutes les éoliennes de la maille",
                )
            ]
            if name == "power"
            else []
        )
        return Computed(get(variable), unit, variable, flags)
    if name == "inverse_obukhov_length":
        return inverse_obukhov(get, has)
    if name == "obukhov_length":
        inverse = inverse_obukhov(get, has)
        with np.errstate(divide="ignore"):
            length = np.where(
                np.abs(inverse.values) < NEUTRAL_INVERSE_L, np.nan, 1.0 / inverse.values
            )
        return Computed(
            length,
            "m",
            "1 / (1/L) ; " + inverse.method,
            [
                *inverse.flags,
                f"near-neutral values (|1/L| < {NEUTRAL_INVERSE_L:g} m-1) left empty: use 1/L",
            ],
        )
    raise Unavailable(
        tr(
            f"{name!r} has no height: give a height or choose a surface quantity",
            f"{name!r} n'a pas de hauteur : indiquez une hauteur ou choisissez une grandeur de surface",
        )
    )


# Turbulence from the TKE of the PBL scheme, assuming isotropic turbulence
TURBULENCE = ("wind_speed_std", "turbulence_intensity")
# Below this wind speed the turbulence intensity is not given (ratio dominated by noise)
MIN_SPEED_FOR_TI = 2.0


def isotropy_flags() -> list[str]:
    return [
        tr(
            "from the TKE of the PBL scheme assuming isotropic turbulence (σu = σv = σw = √(2 TKE / 3)); "
            "in the surface layer turbulence is anisotropic (σu > σw) and this underestimates the "
            "streamwise σu by about 20 %",
            "à partir de la TKE du schéma de couche limite, en supposant une turbulence isotrope "
            "(σu = σv = σw = √(2 TKE / 3)) ; près de la surface la turbulence est anisotrope (σu > σw) "
            "et σu dans l'axe du vent est sous-estimé d'environ 20 %",
        ),
        tr(
            "the PBL scheme's TKE is the sub-grid turbulence only, not the resolved fluctuations",
            "la TKE du schéma de couche limite n'est que la turbulence sous-maille, pas les "
            "fluctuations résolues",
        ),
    ]


def turbulence(name: str, tke: Computed, speed: Computed) -> Computed:
    """Standard deviation of each wind component, σ = √(2 TKE / 3), from TKE = ½ (σu² + σv² + σw²)
    with σu = σv = σw (isotropy); turbulence intensity σ / U at the same height and time."""
    sigma = np.sqrt(2.0 * np.clip(tke.values, 0.0, None) / 3.0)
    flags = [*isotropy_flags(), *tke.flags]
    if name == "wind_speed_std":
        return Computed(
            sigma,
            "m s-1",
            tr(
                f"√(2 TKE / 3), isotropic turbulence; TKE: {tke.method}",
                f"√(2 TKE / 3), turbulence isotrope ; TKE : {tke.method}",
            ),
            flags,
        )
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(speed.values >= MIN_SPEED_FOR_TI, sigma / speed.values, np.nan)
    return Computed(
        ratio,
        "1",
        tr(
            f"√(2 TKE / 3) / U, isotropic turbulence; TKE: {tke.method}; U: {speed.method}",
            f"√(2 TKE / 3) / U, turbulence isotrope ; TKE : {tke.method} ; U : {speed.method}",
        ),
        [*flags, f"not given where U < {MIN_SPEED_FOR_TI:g} m/s"],
    )


def compute(
    name: str, height_m: float | None, height_ref: str, get: Get, has: Callable[[str], bool]
) -> Computed:
    """``name`` at ``height_m`` (above ground or sea level) or at the surface: (time, ...)."""
    surface = name in SURFACE or name in ("inverse_obukhov_length", "obukhov_length")
    if height_m is None or surface:
        # A surface quantity has no height: one given with it is ignored
        if name in LEVEL_QUANTITIES or name in TURBULENCE:
            raise Unavailable(tr(f"{name} needs a height", f"{name} demande une hauteur"))
        if surface:
            return surface_field(name, get, has)
        return _raw(name, None, get, has)
    if height_m == 10 and name in WIND and has("U10"):
        u, v = earth_winds(get, "U10", "V10")
        unit = "deg" if name == "wind_direction" else "m s-1"
        return Computed(
            wind_quantity(name, u, v),
            unit,
            tr(
                "U10 and V10 (WRF 10 m diagnostic), rotated to earth-relative",
                "U10 et V10 (diagnostic à 10 m de WRF), tournés dans le repère terrestre",
            ),
        )
    if height_m == 2 and name == "temperature" and has("T2"):
        return Computed(
            get("T2"), "K", tr("T2 (WRF 2 m diagnostic)", "T2 (diagnostic à 2 m de WRF)")
        )
    if name in TURBULENCE:
        tke = compute("tke", height_m, height_ref, get, has)
        speed = compute("wind_speed", height_m, height_ref, get, has)
        return turbulence(name, tke, speed)
    if name in LEVEL_QUANTITIES:
        values, unit, method = level_field(name, get, has)
    else:
        return _raw(name, height_m, get, has)
    return _interpolate(
        values,
        unit,
        method,
        height_m,
        height_ref,
        get,
        has,
        circular_values=name == "wind_direction",
    )


def _interpolate(
    values: np.ndarray, unit: str, method: str, height_m: float, height_ref: str, get: Get, has: Callable[[str], bool],
    circular_values: bool = False,
) -> Computed:  # fmt: skip
    _require(has, "PH", "PHB", "HGT")
    z = heights_agl(get)
    target_note = tr(f"{height_m:g} m above ground", f"{height_m:g} m au-dessus du sol")
    if height_ref == "asl":
        z = z + get("HGT")[:, None]
        target_note = tr(
            f"{height_m:g} m above sea level", f"{height_m:g} m au-dessus du niveau de la mer"
        )
    if circular_values:
        # Directions are interpolated through their unit vectors
        s, _ = at_height(np.sin(np.radians(values)), z, height_m)
        c, outside = at_height(np.cos(np.radians(values)), z, height_m)
        result = circular.wrap(np.degrees(np.arctan2(s, c)))
    else:
        result, outside = at_height(values, z, height_m)
    flags = (
        [
            tr(
                f"{outside} values outside the model levels (no extrapolation)",
                f"{outside} valeurs hors des niveaux du modèle (sans extrapolation)",
            )
        ]
        if outside
        else []
    )
    return Computed(
        result,
        unit,
        tr(
            f"{method}; linear interpolation in height to {target_note}",
            f"{method} ; interpolation linéaire en hauteur à {target_note}",
        ),
        flags,
    )


def _raw(name: str, height_m: float | None, get: Get, has: Callable[[str], bool]) -> Computed:
    """Any other WRF variable by its Registry name: surface fields as they are, fields on the
    mass levels interpolated in height."""
    if not has(name):
        raise Unavailable(
            tr(
                f"{name} is not in the history files",
                f"{name} n'est pas dans les fichiers d'historique",
            )
        )
    values = get(name)
    if values.ndim == 3:
        if height_m is not None:
            raise Unavailable(
                tr(
                    f"{name} has no vertical dimension: remove the height",
                    f"{name} n'a pas de dimension verticale : retirez la hauteur",
                )
            )
        return Computed(values, "", name)
    if height_m is None:
        raise Unavailable(
            tr(
                f"{name} is on model levels: give a height",
                f"{name} est sur les niveaux du modèle : indiquez une hauteur",
            )
        )
    if has("PH") and values.shape[1] == get("PH").shape[1]:
        # On the staggered vertical levels (W, PH...): averaged onto the mass levels
        values = 0.5 * (values[:, :-1] + values[:, 1:])
    return _interpolate(values, "", name, height_m, "agl", get, has)
