"""Power of turbines and farms in a run, by one of two labelled methods, and the power they would
produce without wakes (from a run without turbines), with the same formula.

- "wrf": the POWER output of the wind farm scheme. It is a total per grid cell (all turbines of
  the cell), computed from the cell's hub-height wind (phys/module_wind_fitch.F). A farm's power
  is exact when its cells hold only its turbines; a cell shared with another farm is split by
  turbine count (approximation, reported). Per-turbine values are the cell value split equally
  among its turbines: an approximation, always labelled as such.
- "curve": each turbine's power from the hub-height wind at its position (tslist series at every
  model step when written for the turbine, otherwise the history files interpolated
  bilinearly), with WRF's own conversion (energy/curves.py). An estimate: it ignores what the
  scheme does inside the cell.

The reference without wakes applies the same conversion to the run without turbines: at the
cell of each turbine (nearest mass point, as the scheme uses its cell's wind) for "wrf", at the
turbine's position for "curve".
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

from owstudio.core import tslist as tslist_locations
from owstudio.core.case.model import Case, TurbineType
from owstudio.core.energy import fitch
from owstudio.core.energy.curves import turbine_types, wrf_power_w
from owstudio.core.extract.grid import OutsideGrid, Position, locate
from owstudio.core.extract.history import HistoryFiles
from owstudio.core.extract.points import TimeSeriesFiles, point_series
from owstudio.core.extract.quantities import Unavailable
from owstudio.core.i18n import tr

Method = Literal["wrf", "curve"]


class EnergyError(ValueError):
    """The energy cannot be computed as asked; the message says why."""


@dataclass(frozen=True)
class Site:
    farm: str
    label: str
    type: int
    lat: float
    lon: float
    turbine: TurbineType
    ts_prefix: str | None = None

    @property
    def hub_height_m(self) -> float:
        return self.turbine.hub_height_m

    @property
    def rated_w(self) -> float:
        return self.turbine.rated_power_mw * 1e6


def sites(case: Case) -> list[Site]:
    """Every turbine of every farm (simulated or not), with its turbine model."""
    types = turbine_types(case)
    labels = tslist_locations.turbine_labels(case)
    result = []
    ordinal = 0
    for farm in case.farms:
        for k, t in enumerate(farm.turbines, 1):
            ordinal += 1
            if t.type not in types:
                raise EnergyError(
                    tr(
                        f"Turbine {t.id or f'{farm.id}-{k}'} has type {t.type}, which has no power curve",
                        f"L'éolienne {t.id or f'{farm.id}-{k}'} est du modèle {t.type}, qui n'a pas de courbe de puissance",
                    )
                )
            result.append(
                Site(
                    farm.id,
                    labels[(farm.id, k)],
                    t.type,
                    t.lat,
                    t.lon,
                    types[t.type],
                    f"T{ordinal:04d}"
                    if case.time_series and case.time_series.turbines == "each"
                    else None,
                )
            )
    return result


def farm_domain(case: Case) -> int:
    if case.farm_scheme is not None:
        return max(case.farm_scheme.domains)
    return case.max_dom


@dataclass
class Turbines:
    """Power of each turbine (W) at the output times; ``approximate`` when the value per turbine
    is a reconstruction from its grid cell's POWER."""

    power: dict[str, pd.Series]
    method: str
    approximate: bool = False
    flags: list[str] = field(default_factory=list)
    # Grid cells holding turbines of several farms
    shared_cells: int = 0


class RunPower:
    """Power and winds of one stage (main or control) of a run."""

    def __init__(self, folder: Path, case: Case) -> None:
        self.folder = folder
        self.case = case
        self.domain = farm_domain(case)
        try:
            self.files = HistoryFiles(folder, self.domain)
        except FileNotFoundError as error:
            raise EnergyError(str(error)) from error
        self._positions: dict[str, Position] = {}
        self._cell_winds: dict[tuple[int, int, float], pd.Series] = {}

    def position(self, site: Site) -> Position:
        if site.label not in self._positions:
            try:
                self._positions[site.label] = locate(*self.files.coordinates, site.lat, site.lon)
            except OutsideGrid as error:
                raise EnergyError(
                    tr(
                        f"Turbine {site.label}: {error} (domain {self.domain})",
                        f"Éolienne {site.label} : {error} (domaine {self.domain})",
                    )
                ) from error
        return self._positions[site.label]

    def cell(self, site: Site) -> tuple[int, int]:
        """(j, i) of the mass point whose cell holds the turbine."""
        i, j = self.position(site).nearest
        return j, i

    def hub_wind(self, site: Site, at: Literal["cell", "point"]) -> pd.Series:
        """Hub-height wind speed at the turbine's cell centre, or at its position (tslist series
        when written for the turbine, otherwise the history files)."""
        if at == "point":
            # Prefixes are positional and unique. Names are only display fields truncated to
            # 25 characters by WRF, so they must never identify the turbine's series.
            prefix = site.ts_prefix
            tslist = TimeSeriesFiles(self.folder / "tslist")
            if prefix and tslist.has(prefix, self.domain):
                try:
                    return tslist.series(prefix, self.domain, "wind_speed", site.hub_height_m)[
                        1
                    ].values
                except Unavailable:
                    pass
        else:
            # At the cell centre the wind is the same for every turbine of the cell with the
            # same hub height: read once per cell
            key = (*self.cell(site), site.hub_height_m)
            if key not in self._cell_winds:
                self._cell_winds[key] = point_series(
                    self.files,
                    self.position(site),
                    "wind_speed",
                    site.hub_height_m,
                    "agl",
                    "nearest",
                ).values
            return self._cell_winds[key]
        return point_series(
            self.files, self.position(site), "wind_speed", site.hub_height_m, "agl", "bilinear"
        ).values

    def scheme_power(self, chosen: list[Site]) -> Turbines:
        """WRF's POWER of each cell shared among its turbines: with the Fitch scheme in
        proportion to each turbine's power recomputed with the scheme's own formula from the
        cell's winds (energy/fitch.py), so that the turbines of a cell always add up to WRF's
        value; with MAV in equal shares (approximation)."""
        if not self.files.has("POWER"):
            raise EnergyError(
                tr(
                    "No POWER output in this run: no wind farm scheme ran on this domain",
                    "Pas de sortie POWER dans ce calcul : aucun schéma de parc n'a tourné sur ce domaine",
                )
            )
        scheme = self.case.farm_scheme
        everyone = [
            s
            for s in sites(self.case)
            if scheme and s.farm in {f.id for f in self.case.enabled_farms}
        ]
        cells: dict[tuple[int, int], list[Site]] = {}
        for site in everyone:
            cells.setdefault(self.cell(site), []).append(site)
        wanted = {self.cell(site) for site in chosen}
        cells = {c: m for c, m in cells.items() if c in wanted}
        if not cells:
            return Turbines({}, "wrf")
        js = [c[0] for c in cells]
        is_ = [c[1] for c in cells]
        box = self.files.box("POWER", min(js), max(js) + 1, min(is_), max(is_) + 1)
        result: dict[str, pd.Series] = {}
        shared = 0
        mismatch: list[float] = []
        # The history file of the initial time is written before the first step: no power yet
        # (outputs of the window method have none: their first time ends a spin-up)
        windowed = (self.folder / "windows.json").is_file()
        initial = not windowed and self.files.times[0] == pd.Timestamp(
            self.case.period.start
        ).tz_localize("UTC")
        fitch_shares = scheme is not None and scheme.scheme == "fitch"
        dx = float(self.files.attributes.get("DX", 0.0))
        chosen_labels = {s.label for s in chosen}
        profiles = fitch.cell_profiles(self.files, list(cells)) if fitch_shares and dx > 0 else None
        for n, ((j, i), members) in enumerate(cells.items()):
            values = box[:, j - min(js), i - min(is_)].copy()
            if initial:
                values[0] = np.nan
            if len({m.farm for m in members}) > 1:
                shared += 1
            if profiles is not None:
                z, u, v = (values[..., n] for values in profiles)
                own = {
                    m.label: fitch.turbine_power(
                        z, u, v, m.turbine, len(members), dx, bool(scheme and scheme.induction)
                    )
                    for m in members
                }
                summed = np.sum(list(own.values()), axis=0)
                with np.errstate(divide="ignore", invalid="ignore"):
                    shares = {
                        label: np.where(summed > 0, p / summed, 1.0 / len(members))
                        for label, p in own.items()
                    }
                valid = np.isfinite(values) & (np.abs(values) > 0)
                if valid.any():
                    mismatch.append(
                        float(
                            abs(np.nansum(summed[valid]) - np.nansum(values[valid]))
                            / np.nansum(values[valid])
                        )
                    )
            else:
                shares = {m.label: np.full(len(values), 1.0 / len(members)) for m in members}
            for m in members:
                if m.label in chosen_labels:
                    result[m.label] = pd.Series(values * shares[m.label], index=self.files.times)
        if fitch_shares and dx > 0:
            flags = [
                tr(
                    "per turbine: reconstruction, the cell's POWER shared in proportion to the Fitch formula recomputed from the cell's winds",
                    "par éolienne : reconstitution, le POWER de la maille partagé en proportion de la formule de Fitch recalculée avec les vents de la maille",
                )
            ]
            if mismatch:
                flags.append(
                    tr(
                        f"recomputed Fitch power differs from WRF's POWER by {100 * max(mismatch):.2f} % at most (per cell, over the run)",
                        f"la puissance de Fitch recalculée diffère du POWER de WRF de {100 * max(mismatch):.2f} % au plus (par maille, sur le calcul)",
                    )
                )
        else:
            flags = [
                tr(
                    "per turbine: reconstruction, equal share of the grid cell's POWER",
                    "par éolienne : reconstitution, part égale du POWER de la maille",
                )
            ]
        # POWER is the power of every turbine of a cell: a value per turbine is always a
        # reconstruction, labelled as such; farms add their cells once
        approximate = True
        if initial:
            flags.append(
                tr(
                    "initial time left out: WRF writes POWER before its first time step (zero)",
                    "instant initial écarté : WRF écrit POWER avant son premier pas de temps (zéro)",
                )
            )
        if shared:
            flags.append(
                tr(
                    f"{shared} grid cells hold turbines of several farms: their power is shared as above",
                    f"{shared} mailles contiennent des éoliennes de plusieurs parcs : leur puissance est partagée comme ci-dessus",
                )
            )
        return Turbines(
            result,
            tr("WRF POWER per grid cell", "POWER de WRF par maille"),
            approximate=approximate,
            flags=flags,
            shared_cells=shared,
        )

    def curve_power(
        self, chosen: list[Site], at: Literal["cell", "point"], scheme: Literal["fitch", "mav"]
    ) -> Turbines:
        result = {}
        # The 2 x 2 windows of all the turbines: read as one area from each file
        corners = [self.position(site).window()[:2] for site in chosen]
        if corners:
            self.files.focus(
                min(j for _, j in corners),
                max(j for _, j in corners) + 2,
                min(i for i, _ in corners),
                max(i for i, _ in corners) + 2,
            )
        for site in chosen:
            wind = self.hub_wind(site, at)
            result[site.label] = pd.Series(
                wrf_power_w(wind.to_numpy(), site.turbine, scheme), index=wind.index
            )
        where = (
            tr("grid cell centre (as the scheme)", "centre de la maille (comme le schéma)")
            if at == "cell"
            else tr("turbine position", "position de l'éolienne")
        )
        return Turbines(
            result,
            tr(
                f"power curve on the hub-height wind, {where}, WRF's conversion (ρ = 1.23 kg/m³)",
                f"courbe de puissance appliquée au vent à hauteur de moyeu, {where}, conversion de WRF (ρ = 1,23 kg/m³)",
            ),
        )


def run_power(folder: Path, case: Case, chosen: list[Site], method: Method) -> Turbines:
    """Power of the chosen turbines in a run where they were simulated."""
    source = RunPower(folder, case)
    if method == "wrf":
        return source.scheme_power(chosen)
    scheme = case.farm_scheme.scheme if case.farm_scheme else "fitch"
    turbines = source.curve_power(chosen, "point", scheme)
    turbines.flags.append(
        tr(
            "estimate: ignores what the wind farm scheme does inside the grid cell",
            "estimation : ne tient pas compte de ce que fait le schéma de parc dans la maille",
        )
    )
    return turbines


def reference_power(
    folder: Path, case: Case, chosen: list[Site], method: Method, scheme: Literal["fitch", "mav"]
) -> Turbines:
    """Power the chosen turbines would produce in a run without turbines (no wakes)."""
    source = RunPower(folder, case)
    turbines = source.curve_power(chosen, "cell" if method == "wrf" else "point", scheme)
    return turbines


def total(series: list[pd.Series]) -> pd.Series:
    """Sum of power series on their common times."""
    if not series:
        return pd.Series(dtype=float)
    frame = pd.concat(series, axis=1, join="inner")
    return frame.sum(axis=1, min_count=len(series))


def installed_w(chosen: list[Site]) -> float:
    return float(np.sum([s.rated_w for s in chosen]))
