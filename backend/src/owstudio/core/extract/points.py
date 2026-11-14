"""Series at a point from the history files, fields for maps, and series from the time series
(tslist) files, all in the common series format."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

from owstudio.core.extract.catalogue import DIAGNOSTICS
from owstudio.core.extract.grid import Position
from owstudio.core.extract.history import HistoryFiles
from owstudio.core.extract.quantities import (
    NEUTRAL_INVERSE_L,
    TURBULENCE,
    Computed,
    Unavailable,
    compute,
    turbulence,
    wind_quantity,
)
from owstudio.core.i18n import num, tr
from owstudio.core.postproc.tslist_reader import (
    Location,
    interpolate_rows,
    read_header,
    read_profile,
    read_surface,
)
from owstudio.core.postproc.windowed import OutputSource, time_series_sources
from owstudio.core.series import VARIABLES, circular

Interpolation = Literal["bilinear", "nearest"]


@dataclass
class Extracted:
    values: pd.Series
    unit: str
    method: str
    flags: list[str] = field(default_factory=list)
    frequency_s: float | None = None
    # Which of several ways gave the values, as a short code (the power of turbines at a tslist
    # location: extract/runs.py POWER_SOURCES)
    how: str = ""


def _unit(name: str, computed: Computed, files: HistoryFiles) -> str:
    if computed.unit:
        return computed.unit
    if name in VARIABLES:
        return VARIABLES[name].unit
    info = files.variables.get(name)
    return info.units if info else ""


# The history variables each quantity may read: read together, with one opening of each file
_INPUTS = {d.key: {v for way in d.ways for v in way[0]} for d in DIAGNOSTICS}


def point_series(
    files: HistoryFiles,
    position: Position,
    name: str,
    height_m: float | None,
    height_ref: str = "agl",
    interpolation: Interpolation = "bilinear",
) -> Extracted:
    """``name`` at the point for every output time. Grid-cell totals (power) use the cell that
    holds the point; directions are interpolated through the wind components."""
    i0, j0, weights = position.window()
    files.prefetch(_INPUTS.get(name, ()), j0, i0)
    if interpolation == "nearest" or name == "power":
        ni, nj = position.nearest
        weights = np.zeros((2, 2))
        weights[min(max(nj - j0, 0), 1), min(max(ni - i0, 0), 1)] = 1.0
    cache: dict[str, np.ndarray] = {}

    def get(variable: str) -> np.ndarray:
        if variable not in cache:
            cache[variable] = files.window(variable, j0, i0)
        return cache[variable]

    def combine(values: np.ndarray) -> np.ndarray:
        combined: np.ndarray = np.einsum("tji,ji->t", values, weights)
        return combined

    if name == "wind_direction":
        u = compute("u", height_m, height_ref, get, files.has)
        v = compute("v", height_m, height_ref, get, files.has)
        values = circular.from_components(combine(u.values), combine(v.values))
        computed = Computed(
            values,
            "deg",
            tr(
                f"{u.method}; direction of the interpolated components",
                f"{u.method} ; direction des composantes interpolées",
            ),
            u.flags,
        )
    elif name in TURBULENCE:
        # The ratio is taken after interpolation of its two terms to the point
        tke = compute("tke", height_m, height_ref, get, files.has)
        speed = compute("wind_speed", height_m, height_ref, get, files.has)
        tke.values, speed.values = combine(tke.values), combine(speed.values)
        computed = turbulence(name, tke, speed)
    else:
        computed = compute(name, height_m, height_ref, get, files.has)
        computed.values = combine(computed.values)
    nearest = interpolation == "nearest" or name == "power"
    where = (
        tr("grid cell holding the point", "maille contenant le point")
        if nearest
        else tr(
            "bilinear between the 4 surrounding mass points",
            "bilinéaire entre les 4 points de masse voisins",
        )
    )
    flags = list(computed.flags)
    if interpolation == "nearest" and name != "power":
        flags.append(
            tr(
                "nearest grid point, no horizontal interpolation",
                "point de grille le plus proche, sans interpolation horizontale",
            )
        )
    return Extracted(
        pd.Series(computed.values, index=files.times),
        _unit(name, computed, files),
        tr(
            f"wrfout d{files.domain:02d}, {where}; {computed.method}",
            f"wrfout d{files.domain:02d}, {where} ; {computed.method}",
        ),
        flags,
    )


def field_at(
    files: HistoryFiles, time: int, name: str, height_m: float | None, height_ref: str = "agl"
) -> tuple[np.ndarray, str, str]:
    """2-D map of ``name`` at output time ``time`` (position in files.times)."""
    cache = {k: v[None] for k, v in files.at_time_many(_INPUTS.get(name, ()), time).items()}

    def get(variable: str) -> np.ndarray:
        if variable not in cache:
            cache[variable] = files.at_time(variable, time)[None]
        return cache[variable]

    computed = compute(name, height_m, height_ref, get, files.has)
    return computed.values[0], _unit(name, computed, files), computed.method


# ------------------------------------------------------------------ tslist

TS_SURFACE = {
    "temperature": ("t", 2.0, "K"),
    "mixing_ratio": ("q", 2.0, "kg kg-1"),
    "surface_pressure": ("psfc", None, "Pa"),
    "sensible_heat_flux": ("hfx", None, "W m-2"),
    "latent_heat_flux": ("lh", None, "W m-2"),
    "skin_temperature": ("tsk", None, "K"),
    "longwave_down": ("glw", None, "W m-2"),
    "shortwave_down": ("gsw", None, "W m-2"),
    # Top soil layer: over the sea, WRF keeps there the temperature it was given
    "soil_temperature": ("tslb1", None, "K"),
    # Accumulated since the start of the run
    "rain_convective": ("rainc", None, "mm"),
    "rain_grid": ("rainnc", None, "mm"),
    "cloud_water": ("clw", None, "kg m-2"),
    # Written by the installer's patch only
    "bulk_richardson": ("br", None, "1"),
    "friction_velocity": ("ust", None, "m s-1"),
    "boundary_layer_height": ("pblh", None, "m"),
}
TS_PROFILES = {
    "potential_temperature": ("TH", "K"),
    "mixing_ratio": ("QV", "kg kg-1"),
    "pressure": ("PR", "Pa"),
    # W at the cell centre (WRF's share/wrf_timeseries.F averages the two faces)
    "vertical_wind": ("WW", "m s-1"),
}
# Dry air gas constant (J/kg/K), cp = 3.5 Rd, reference pressure (Pa): as postproc/tslist_reader.py
RD, P0 = 287.0, 1.0e5
CP = 3.5 * RD
# Read in what a WRF compiled with the installer's patch adds (postproc/tslist_reader.py): 1/L and
# the cell's wind farm power in the TS file, the TKE in the TK profile file (QK with the patch of
# 0.7.4)
STABILITY = ("inverse_obukhov_length", "obukhov_length")
# The power of the wind farm parameterization in the grid cell of the location (W), all its
# turbines together: shared among them in extract/runs.py, never shown as it is
CELL_POWER = "cell_power"


def _not_written(what: str, surface: pd.DataFrame | None = None) -> Unavailable:
    """Why the tslist files lack ``what``; ``surface``, the TS table read, tells its layout: the
    WRF-Solar line (solar_diagnostics = 1) never carries the installer's values."""
    if surface is not None and any(str(column).startswith("extra") for column in surface.columns):
        return Unavailable(
            tr(
                f"no {what} in these tslist files: with the WRF-Solar diagnostics (solar_diagnostics = 1), WRF writes its solar TS line, without it",
                f"pas de {what} dans ces fichiers tslist : avec les diagnostics WRF-Solar (solar_diagnostics = 1), WRF écrit sa ligne TS solaire, sans lui",
            )
        )
    return Unavailable(
        tr(
            f"no {what} in these tslist files: written by a WRF compiled with the tslist outputs of the engine installer",
            f"pas de {what} dans ces fichiers tslist : écrit par un WRF compilé avec les sorties tslist de l'installateur du moteur",
        )
    )


class TimeSeriesFiles:
    """The tslist files of one run stage (outputs/<stage>/tslist). The folders holding them, and
    which locations they have, are looked up once per instance: the export asks for hundreds of
    series of the same files in one request."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self._sources: list[OutputSource] | None = None
        self._windows: dict[Path, TimeSeriesFiles] = {}
        self._has: dict[tuple[str, int], bool] = {}

    def sources(self) -> list[OutputSource]:
        """The folders of the files: this one, or the folder of each independent window."""
        if self._sources is None:
            self._sources = time_series_sources(self.folder)
        return self._sources

    def window(self, folder: Path) -> "TimeSeriesFiles":
        """The files of one independent window."""
        if folder not in self._windows:
            self._windows[folder] = TimeSeriesFiles(folder)
        return self._windows[folder]

    def locations(self) -> list[Location]:
        sources = self.sources()
        if len(sources) != 1 or sources[0].folder != self.folder:
            found_by_key = {}
            for source in sources:
                for location in self.window(source.folder).locations():
                    found_by_key[(location.prefix, location.domain)] = location
            return list(found_by_key.values())
        found = []
        for path in sorted(self.folder.glob("*.d[0-9][0-9].TS")):
            with path.open(encoding="ascii", errors="replace") as f:
                found.append(read_header(f.readline()))
        return found

    def path(self, prefix: str, domain: int, kind: str) -> Path:
        return self.folder / f"{prefix}.d{domain:02d}.{kind}"

    def patched(self) -> bool:
        """Whether these files come from a WRF compiled with the tslist outputs of the engine
        installer: it writes a TK profile file (QK with the patch of 0.7.4) next to every TS
        file."""
        return any(
            next(source.folder.glob(f"*.d[0-9][0-9].{kind}"), None) is not None
            for source in self.sources()
            for kind in ("TK", "QK")
        )

    def has(self, prefix: str, domain: int) -> bool:
        key = (prefix, domain)
        if key not in self._has:
            self._has[key] = any(
                (source.folder / f"{prefix}.d{domain:02d}.TS").is_file()
                for source in self.sources()
            )
        return self._has[key]

    def series(
        self, prefix: str, domain: int, name: str, height_m: float | None, height_ref: str = "agl"
    ) -> tuple[Location, Extracted]:
        """``name`` at the location at every model time step (instantaneous values).
        Winds of the tslist files are earth-relative (WRF share/wrf_timeseries.F); profile
        heights are the geopotential heights of the mass levels above sea level, minus the
        location's elevation for heights above ground."""
        sources = self.sources()
        if len(sources) != 1 or sources[0].folder != self.folder:
            parts = []
            flags: list[str] = []
            location = None
            unit, method = "", ""
            for source in sources:
                child = self.window(source.folder)
                if not child.has(prefix, domain):
                    continue
                location, extracted = child.series(prefix, domain, name, height_m, height_ref)
                parts.append(
                    extracted.values[source.mask(pd.DatetimeIndex(extracted.values.index))]
                )
                unit, method = extracted.unit, extracted.method
                flags.extend(extracted.flags)
            if not parts or location is None:
                raise Unavailable(
                    tr(
                        "No time series at this point in the independent windows",
                        "Aucune série temporelle à ce point dans les fenêtres indépendantes",
                    )
                )
            values = pd.concat(parts).sort_index()
            values = values[~values.index.duplicated(keep="first")]
            return location, Extracted(
                values,
                unit,
                method
                + tr(
                    "; independent windows: each spin-up excluded",
                    " ; fenêtres indépendantes : chaque spin-up écarté",
                ),
                list(dict.fromkeys(flags)),
                None,
            )
        location, surface = read_surface(self.path(prefix, domain, "TS"))
        times = pd.DatetimeIndex(surface.index)
        nanoseconds = times.to_numpy(dtype="datetime64[ns]").astype("int64")
        step = float(np.median(np.diff(nanoseconds)) / 1e9) if len(times) > 1 else None
        index = times.tz_localize("UTC")
        if name in ("wind_speed", "wind_direction", "u", "v") and height_m == 10:
            u, v = surface["u"].to_numpy(), surface["v"].to_numpy()
            values = wind_quantity(name, u, v)
            return location, Extracted(
                pd.Series(values, index=index),
                "deg" if name == "wind_direction" else "m s-1",
                tr(
                    "tslist TS file: 10 m wind (earth-relative)",
                    "fichier TS de la tslist : vent à 10 m (repère terrestre)",
                ),
                [],
                step,
            )
        if name in TS_SURFACE and (height_m is None or height_m == TS_SURFACE[name][1]):
            column, _, unit = TS_SURFACE[name]
            if column not in surface:
                raise _not_written(column.upper(), surface)
            return location, Extracted(
                pd.Series(surface[column].to_numpy(), index=index),
                unit,
                tr(f"tslist TS file: {column}", f"fichier TS de la tslist : {column}"),
                [],
                step,
            )
        if name in STABILITY:
            # A surface quantity: a height given with it is ignored, as in the history files
            if "rmol" not in surface:
                raise _not_written("RMOL", surface)
            inverse = surface["rmol"].to_numpy()
            method = tr(
                "tslist TS file: RMOL (1/L of the surface layer scheme)",
                "fichier TS de la tslist : RMOL (1/L du schéma de couche de surface)",
            )
            if name == "inverse_obukhov_length":
                return location, Extracted(pd.Series(inverse, index=index), "m-1", method, [], step)
            with np.errstate(divide="ignore", invalid="ignore"):
                length = np.where(np.abs(inverse) < NEUTRAL_INVERSE_L, np.nan, 1.0 / inverse)
            return location, Extracted(
                pd.Series(length, index=index),
                "m",
                tr(f"1 / (1/L); {method}", f"1 / (1/L) ; {method}"),
                [
                    tr(
                        f"near-neutral values (|1/L| < {NEUTRAL_INVERSE_L:g} m-1) left empty: use 1/L",
                        f"valeurs quasi neutres (|1/L| < {num(NEUTRAL_INVERSE_L)} m-1) laissées vides : utiliser 1/L",
                    )
                ],
                step,
            )
        if name == CELL_POWER:
            if "power" not in surface:
                raise _not_written("POWER", surface)
            return location, Extracted(
                pd.Series(surface["power"].to_numpy() * 1000.0, index=index),
                "W",
                tr(
                    "tslist TS file: POWER of the grid cell",
                    "fichier TS de la tslist : POWER de la maille",
                ),
                [],
                step,
            )
        if height_m is None:
            raise Unavailable(
                tr(
                    f"{name} is not in the tslist surface file (TS)",
                    f"{name} n'est pas dans le fichier de surface tslist (TS)",
                )
            )
        if not self.path(prefix, domain, "PH").exists():
            raise Unavailable(
                tr(
                    "no vertical profiles in the tslist output (PH file missing)",
                    "pas de profils verticaux dans la sortie tslist (fichier PH manquant)",
                )
            )
        heights = read_profile(self.path(prefix, domain, "PH")).to_numpy()
        z = heights - (location.elevation if height_ref == "agl" else 0.0)
        if name in ("wind_speed", "wind_direction", "u", "v"):
            u_levels = read_profile(self.path(prefix, domain, "UU")).to_numpy()
            v_levels = read_profile(self.path(prefix, domain, "VV")).to_numpy()
            rows = min(len(z), len(u_levels), len(v_levels), len(index))
            u = interpolate_rows(z[:rows], u_levels[:rows], height_m)
            v = interpolate_rows(z[:rows], v_levels[:rows], height_m)
            values = wind_quantity(name, u, v)
            method = tr(
                "tslist UU/VV profiles (earth-relative), linear interpolation in height",
                "profils UU/VV de la tslist (repère terrestre), interpolation linéaire en hauteur",
            )
            unit = "deg" if name == "wind_direction" else "m s-1"
        elif name == "temperature":
            # T = θ (p / p0)^(Rd/cp), both interpolated to the height, as the point table did
            for kind in ("TH", "PR"):
                if not self.path(prefix, domain, kind).exists():
                    raise Unavailable(
                        tr(
                            f"no {kind} profile in the tslist output",
                            f"pas de profil {kind} dans la sortie tslist",
                        )
                    )
            theta = read_profile(self.path(prefix, domain, "TH")).to_numpy()
            pressure = read_profile(self.path(prefix, domain, "PR")).to_numpy()
            rows = min(len(z), len(theta), len(pressure), len(index))
            values = interpolate_rows(z[:rows], theta[:rows], height_m) * (
                interpolate_rows(z[:rows], pressure[:rows], height_m) / P0
            ) ** (RD / CP)
            method = tr(
                "tslist TH and PR profiles, T = θ (p / p0)^(Rd/cp), linear interpolation in height",
                "profils TH et PR de la tslist, T = θ (p / p0)^(Rd/cp), interpolation linéaire en hauteur",
            )
            unit = "K"
        elif name in TS_PROFILES:
            kind, unit = TS_PROFILES[name]
            if not self.path(prefix, domain, kind).exists():
                raise Unavailable(
                    tr(
                        f"no {kind} profile in the tslist output",
                        f"pas de profil {kind} dans la sortie tslist",
                    )
                )
            levels = read_profile(self.path(prefix, domain, kind)).to_numpy()
            rows = min(len(z), len(levels), len(index))
            values = interpolate_rows(z[:rows], levels[:rows], height_m)
            method = tr(
                f"tslist {kind} profile, linear interpolation in height",
                f"profil {kind} de la tslist, interpolation linéaire en hauteur",
            )
        elif name == "tke" or name in TURBULENCE:
            if self.path(prefix, domain, "TK").exists():
                # The TKE itself (installer's patch of 0.7.5): QKE / 2 with MYNN, TKE_PBL with
                # MYJ, QNSE and BouLac, missing (asterisks) with the schemes that have none
                tke = read_profile(self.path(prefix, domain, "TK")).to_numpy()
                if not np.isfinite(tke).any():
                    raise Unavailable(
                        tr(
                            "no TKE in the tslist output: the boundary layer scheme of this run computes none (MYNN, MYJ, QNSE and BouLac do)",
                            "pas de TKE dans la sortie tslist : le schéma de couche limite de ce calcul n'en calcule pas (MYNN, MYJ, QNSE et BouLac en calculent)",
                        )
                    )
                method = tr(
                    "tslist TK profile (TKE of the boundary layer scheme), linear interpolation in height",
                    "profil TK de la tslist (TKE du schéma de couche limite), interpolation linéaire en hauteur",
                )
            elif self.path(prefix, domain, "QK").exists():
                # The QKE of the patch of 0.7.4 (MYNN only)
                qke = read_profile(self.path(prefix, domain, "QK")).to_numpy()
                if not np.nanmax(qke, initial=0.0) > 0:
                    raise Unavailable(
                        tr(
                            "QKE is zero in the tslist output: it is computed by the MYNN boundary layer scheme only",
                            "QKE est nul dans la sortie tslist : seul le schéma de couche limite MYNN le calcule",
                        )
                    )
                tke = qke / 2.0
                method = tr(
                    "tslist QK profile, QKE / 2 (MYNN: QKE is twice the TKE), linear interpolation in height",
                    "profil QK de la tslist, QKE / 2 (MYNN : QKE vaut deux fois la TKE), interpolation linéaire en hauteur",
                )
            else:
                raise _not_written(tr("TKE (TK file)", "TKE (fichier TK)"))
            rows = min(len(z), len(tke), len(index))
            values = interpolate_rows(z[:rows], tke[:rows], height_m)
            unit = "m2 s-2"
        else:
            raise Unavailable(
                tr(f"{name} is not in the tslist output", f"{name} n'est pas dans la sortie tslist")
            )
        outside = int(np.isnan(values).sum())
        flags = (
            [
                tr(
                    f"{outside} values outside the written levels (max_ts_level)",
                    f"{outside} valeurs hors des niveaux écrits (max_ts_level)",
                )
            ]
            if outside
            else []
        )
        if name in TURBULENCE:
            # σu and TI of every model time step. Their 10-minute values are not the means of
            # these: they come from the means of the TKE and of the speed (extract/runs.py)
            u_levels = read_profile(self.path(prefix, domain, "UU")).to_numpy()
            v_levels = read_profile(self.path(prefix, domain, "VV")).to_numpy()
            rows = min(len(values), len(u_levels), len(v_levels))
            speed = np.hypot(
                interpolate_rows(z[:rows], u_levels[:rows], height_m),
                interpolate_rows(z[:rows], v_levels[:rows], height_m),
            )
            computed = turbulence(
                name,
                Computed(values[:rows], unit, method, flags),
                Computed(speed, "m s-1", tr("tslist UU/VV profiles", "profils UU/VV de la tslist")),
            )
            values, unit, method, flags = (
                computed.values,
                computed.unit,
                computed.method,
                computed.flags,
            )
        where = (
            tr("above ground", "au-dessus du sol")
            if height_ref == "agl"
            else tr("above sea level", "au-dessus du niveau de la mer")
        )
        return location, Extracted(
            pd.Series(values, index=index[: len(values)]),
            unit,
            tr(f"{method} to {height_m:g} m {where}", f"{method} à {num(height_m)} m {where}"),
            flags,
            step,
        )
