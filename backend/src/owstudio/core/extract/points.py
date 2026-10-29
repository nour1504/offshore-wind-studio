"""Series at a point from the history files, fields for maps, and series from the time series
(tslist) files, all in the common series format."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

from owstudio.core.extract.grid import Position
from owstudio.core.extract.history import HistoryFiles
from owstudio.core.extract.quantities import (
    TURBULENCE,
    Computed,
    Unavailable,
    compute,
    turbulence,
    wind_quantity,
)
from owstudio.core.i18n import tr
from owstudio.core.postproc.tslist_reader import (
    Location,
    interpolate_rows,
    read_header,
    read_profile,
    read_surface,
)
from owstudio.core.series import VARIABLES, circular

Interpolation = Literal["bilinear", "nearest"]


@dataclass
class Extracted:
    values: pd.Series
    unit: str
    method: str
    flags: list[str] = field(default_factory=list)
    frequency_s: float | None = None


def _unit(name: str, computed: Computed, files: HistoryFiles) -> str:
    if computed.unit:
        return computed.unit
    if name in VARIABLES:
        return VARIABLES[name].unit
    info = files.variables.get(name)
    return info.units if info else ""


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
            u.method.replace("rotated", "rotated; direction of the interpolated components"),
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
        f"wrfout d{files.domain:02d}, {where}; {computed.method}",
        flags,
    )


def field_at(
    files: HistoryFiles, time: int, name: str, height_m: float | None, height_ref: str = "agl"
) -> tuple[np.ndarray, str, str]:
    """2-D map of ``name`` at output time ``time`` (position in files.times)."""
    cache: dict[str, np.ndarray] = {}

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
}
TS_PROFILES = {
    "potential_temperature": ("TH", "K"),
    "mixing_ratio": ("QV", "kg kg-1"),
    "pressure": ("PR", "Pa"),
}


class TimeSeriesFiles:
    """The tslist files of one run stage (outputs/<stage>/tslist)."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder

    def locations(self) -> list[Location]:
        from owstudio.core.postproc.windowed import time_series_sources

        sources = time_series_sources(self.folder)
        if len(sources) != 1 or sources[0].folder != self.folder:
            found_by_key = {}
            for source in sources:
                for location in TimeSeriesFiles(source.folder).locations():
                    found_by_key[(location.prefix, location.domain)] = location
            return list(found_by_key.values())
        found = []
        for path in sorted(self.folder.glob("*.d[0-9][0-9].TS")):
            with path.open(encoding="ascii", errors="replace") as f:
                found.append(read_header(f.readline()))
        return found

    def path(self, prefix: str, domain: int, kind: str) -> Path:
        return self.folder / f"{prefix}.d{domain:02d}.{kind}"

    def has(self, prefix: str, domain: int) -> bool:
        from owstudio.core.postproc.windowed import time_series_sources

        return any(
            (source.folder / f"{prefix}.d{domain:02d}.TS").is_file()
            for source in time_series_sources(self.folder)
        )

    def series(
        self, prefix: str, domain: int, name: str, height_m: float | None, height_ref: str = "agl"
    ) -> tuple[Location, Extracted]:
        """``name`` at the location at every model time step (instantaneous values).
        Winds of the tslist files are earth-relative (WRF share/wrf_timeseries.F); profile
        heights are the geopotential heights of the mass levels above sea level, minus the
        location's elevation for heights above ground."""
        from owstudio.core.postproc.windowed import time_series_sources

        sources = time_series_sources(self.folder)
        if len(sources) != 1 or sources[0].folder != self.folder:
            parts = []
            flags: list[str] = []
            location = None
            unit, method = "", ""
            for source in sources:
                child = TimeSeriesFiles(source.folder)
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
                        "No time series at this location in the independent windows",
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
                    " ; fenêtres indépendantes : chaque mise en route écartée",
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
            return location, Extracted(
                pd.Series(surface[column].to_numpy(), index=index),
                unit,
                tr(f"tslist TS file: {column}", f"fichier TS de la tslist : {column}"),
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
            u = self._interpolate(z[:rows], u_levels[:rows], height_m)
            v = self._interpolate(z[:rows], v_levels[:rows], height_m)
            values = wind_quantity(name, u, v)
            method = tr(
                "tslist UU/VV profiles (earth-relative), linear interpolation in height",
                "profils UU/VV de la tslist (repère terrestre), interpolation linéaire en hauteur",
            )
            unit = "deg" if name == "wind_direction" else "m s-1"
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
            values = self._interpolate(z[:rows], levels[:rows], height_m)
            method = tr(
                f"tslist {kind} profile, linear interpolation in height",
                f"profil {kind} de la tslist, interpolation linéaire en hauteur",
            )
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
        where = (
            tr("above ground", "au-dessus du sol")
            if height_ref == "agl"
            else tr("above sea level", "au-dessus du niveau de la mer")
        )
        return location, Extracted(
            pd.Series(values, index=index[: len(values)]),
            unit,
            f"{method} {tr('to', 'à')} {height_m:g} m {where}",
            flags,
            step,
        )

    @staticmethod
    def _interpolate(z: np.ndarray, values: np.ndarray, target: float) -> np.ndarray:
        return interpolate_rows(z, values, target)
