"""Results of a finished run, read from the history files copied to the case directory:

    outputs/main/     wrfout_d0N_* and the case.yaml that produced them
    outputs/control/  the same case without turbines, for a wake study

Statistics start at the second output time when the first is the initial state (no power yet,
extract/history.py). Fields are also drawn as transparent PNG map overlays.
"""

import io
import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd

from owstudio.core.case.model import Case
from owstudio.core.extract.grid import OutsideGrid, locate
from owstudio.core.extract.history import HistoryFiles
from owstudio.core.extract.points import field_at, point_series
from owstudio.core.i18n import tr
from owstudio.core.postproc.windowed import history_paths
from owstudio.core.storage import outputs_stamp, stage_folder
from owstudio.core.windfarm.catalog import turbine_types

RunName = Literal["main", "control"]
Variable = Literal["hub_wind", "wake", "wind10", "power", "pblh", "t2"]
# Used when the case has no wind farm
DEFAULT_HUB_HEIGHT_M = 100.0


@dataclass(frozen=True)
class VariableInfo:
    label: str
    units: str
    colormap: str
    diverging: bool = False


VARIABLES: dict[str, VariableInfo] = {
    "hub_wind": VariableInfo("Wind speed at hub height", "m/s", "viridis"),
    "wake": VariableInfo("Wind speed change due to the farm (hub height)", "m/s", "RdBu_r", True),
    "wind10": VariableInfo("Wind speed at 10 m", "m/s", "viridis"),
    "power": VariableInfo("Turbine power per grid cell", "MW", "magma"),
    "pblh": VariableInfo("Boundary layer height", "m", "cividis"),
    "t2": VariableInfo("Air temperature at 2 m", "°C", "coolwarm"),
}


# Fields and colour ranges already computed, kept between requests: an animation asks for every
# frame, each an interpolation in height over the whole grid (about 0.4 s), and every frame needs
# the colour range of the whole run. Keyed by run folder and the date of its outputs.
_COMPUTED: OrderedDict[tuple[Any, ...], Any] = OrderedDict()
_COMPUTED_SIZE = 600
_COMPUTED_LOCK = threading.Lock()
# One lock per key being computed: a request for a value already under way (by the background
# warm-up) waits for it instead of computing it a second time
_PENDING: dict[tuple[Any, ...], threading.Lock] = {}


def remember(key: tuple[Any, ...], compute: Callable[[], Any]) -> Any:
    with _COMPUTED_LOCK:
        if key in _COMPUTED:
            _COMPUTED.move_to_end(key)
            return _COMPUTED[key]
        pending = _PENDING.setdefault(key, threading.Lock())
    with pending:
        with _COMPUTED_LOCK:
            if key in _COMPUTED:
                return _COMPUTED[key]
        try:
            value = compute()
            with _COMPUTED_LOCK:
                _COMPUTED[key] = value
                while len(_COMPUTED) > _COMPUTED_SIZE:
                    _COMPUTED.popitem(last=False)
        finally:
            with _COMPUTED_LOCK:
                _PENDING.pop(key, None)
    return value


class Results:
    def __init__(self, root: Path) -> None:
        # The run folder (or an imported results folder) holding outputs/main and outputs/control
        self.root = root
        self.outputs = root / "outputs"
        self.case = Case.from_yaml(self.outputs / "main" / "case.yaml")
        self.windowed = (self.outputs / "main" / "windows.json").is_file()
        self._initial: dict[int, bool] = {}

    @staticmethod
    def exist(root: Path) -> bool:
        main = root / "outputs" / "main"
        return (main / "case.yaml").exists() and bool(history_paths(main))

    def files(self, run: RunName) -> dict[int, Path]:
        return {int(path.name[8:10]): path for path in history_paths(stage_folder(self.root, run))}

    @property
    def has_control(self) -> bool:
        return bool(self.files("control"))

    @property
    def hub_height_m(self) -> float:
        types = turbine_types(self.case)
        heights = [
            types[t.type].hub_height_m for _, t in self.case.active_turbines() if t.type in types
        ]
        return float(np.mean(heights)) if heights else DEFAULT_HUB_HEIGHT_M

    @property
    def farm_domain(self) -> int | None:
        """Innermost domain running the wind farm scheme: power is counted there only."""
        scheme = self.case.farm_scheme
        return max(scheme.domains) if scheme and self.case.active_turbines() else None

    @property
    def installed_mw(self) -> float:
        types = turbine_types(self.case)
        return sum(
            types[t.type].rated_power_mw for _, t in self.case.active_turbines() if t.type in types
        )

    def _history(self, run: RunName, number: int) -> HistoryFiles:
        return HistoryFiles(stage_folder(self.root, run), number)

    def _initial_first(self, number: int) -> bool:
        """Whether the first output time of the run on this domain is the initial state of the
        simulation, left out of the statistics (extract/history.py)."""
        if number not in self._initial:
            files = self._history("main", number)
            self._initial[number] = files.initial_first(self.case.period.start)
        return self._initial[number]

    @property
    def _stamp(self) -> tuple[str, float, float]:
        """The run folder, the date of its outputs and of its reference choice."""
        return outputs_stamp(self.root)

    def _frame(
        self, variable: Variable, number: int, time: int, run: RunName = "main"
    ) -> np.ndarray:
        frame: np.ndarray = remember(
            ("frame", *self._stamp, variable, number, time, run),
            lambda: self._compute_frame(variable, number, time, run),
        )
        return frame

    def _compute_frame(
        self, variable: Variable, number: int, time: int, run: RunName = "main"
    ) -> np.ndarray:
        files = self._history(run, number)
        if variable == "wake":
            if not self.has_control:
                raise LookupError(tr("No run without turbines", "Pas de calcul sans éoliennes"))
            main = self._frame("hub_wind", number, time)
            reference = self._history("control", number)
            matches = np.flatnonzero(reference.times == files.times[time])
            if not len(matches):
                raise LookupError(
                    tr(
                        "No control output at the same retained time",
                        "Aucune sortie de contrôle au même instant gardé",
                    )
                )
            difference: np.ndarray = np.asarray(
                main - self._frame("hub_wind", number, int(matches[0]), "control")
            )
            return difference
        name, height = {
            "hub_wind": ("wind_speed", self.hub_height_m),
            "wind10": ("wind_speed", 10.0),
            "power": ("power", None),
            "pblh": ("pblh", None),
            "t2": ("temperature", 2.0),
        }[variable]
        value, _, _ = field_at(files, time, name, height)
        result: np.ndarray = np.asarray(
            value / 1e6 if variable == "power" else value - 273.15 if variable == "t2" else value
        )
        return result

    def farm_power(self) -> pd.Series:
        """Total farm power from the wind farm scheme, MW."""
        number = self.farm_domain
        if number is None:
            return pd.Series(dtype=float)
        files = self._history("main", number)
        if not files.has("POWER"):
            return pd.Series(dtype=float)
        power: pd.Series = remember(
            ("farm_power", *self._stamp),
            lambda: pd.Series(
                [
                    float(np.nansum(files.at_time("POWER", k))) / 1e6
                    for k in range(len(files.times))
                ],
                index=files.times,
            ),
        )
        return power.copy()

    def ideal_power(self) -> pd.Series | None:
        """Power the turbines would produce without any wake, from the control run's wind.

        Each turbine sees the hub-height wind of its grid cell in the run without turbines,
        converted with its power curve.
        """
        number = self.farm_domain
        if not number or not self.has_control:
            return None
        from owstudio.core.energy.production import reference_power, sites
        from owstudio.core.energy.production import total as total_power

        def compute() -> pd.Series:
            chosen = [
                s for s in sites(self.case) if s.farm in {f.id for f in self.case.enabled_farms}
            ]
            reference = reference_power(
                stage_folder(self.root, "control"),
                self.case,
                chosen,
                "wrf",
                self.case.farm_scheme.scheme if self.case.farm_scheme else "fitch",
            )
            return total_power(list(reference.power.values())) / 1e6

        # Kept once computed: every page of results shows it
        ideal: pd.Series = remember(("ideal", *self._stamp), compute)
        return ideal.copy()

    def _retained(self, series: pd.Series) -> pd.Series:
        """The times the statistics of the farm use, as the energy figures do: outputs of the
        window method already leave out every spin-up; a run in a single folder leaves out the
        initial state of its simulation and the times before the useful start (the former
        spin-up of older versions, see case/model.py)."""
        if self.windowed:
            return series
        number = self.farm_domain
        kept = series.iloc[1:] if number and self._initial_first(number) else series
        start = pd.Timestamp(self.case.period.start)
        index = pd.DatetimeIndex(kept.index)
        if index.tz is not None and start.tzinfo is None:
            start = start.tz_localize(index.tz)
        elif index.tz is None and start.tzinfo is not None:
            start = start.tz_convert(None)
        return kept[index >= start]

    def summary(self) -> dict[str, object]:
        power = self._retained(self.farm_power())
        hours = (power.index[-1] - power.index[0]).total_seconds() / 3600 if len(power) > 1 else 0
        mean = float(power.mean()) if len(power) else None
        summary: dict[str, object] = {
            "name": self.case.name,
            "start": self.case.period.start,
            "end": self.case.period.end,
            "domains": sorted(self.files("main")),
            "farm_domain": self.farm_domain,
            "has_control": self.has_control,
            "hub_height_m": self.hub_height_m,
            "installed_mw": self.installed_mw,
            "turbines": len(self.case.active_turbines()),
            "mean_power_mw": mean,
            "max_power_mw": float(power.max()) if len(power) else None,
            "energy_mwh": float(power.mean() * hours) if len(power) else None,
            "capacity_factor": mean / self.installed_mw
            if mean is not None and self.installed_mw
            else None,
            "ideal_mean_power_mw": None,
            "wake_efficiency": None,
        }
        # The energy tables give the reference without wakes when they can be computed; otherwise
        # it comes from the history files of the run without turbines (read only when needed)
        from_tables = not power.empty and self._energy_figures(summary, power)
        if not from_tables and mean is not None:
            ideal = self.ideal_power()
            if ideal is not None:
                ideal_mean = float(self._retained(ideal).mean())
                summary["ideal_mean_power_mw"] = ideal_mean
                summary["wake_efficiency"] = mean / ideal_mean if ideal_mean > 0 else None
        return summary

    def _energy_figures(self, summary: dict[str, object], power: pd.Series) -> bool:
        """Energy, mean and highest power, capacity factor and wake efficiency as the energy tables,
        the production per direction and the power curve give them (tslist 10-minute means, or
        wrfout POWER without tslist at the turbines); failing that, from the farm domain's total
        POWER (said in the notes). True when the tables gave the reference without wakes."""
        from owstudio.core.energy import integrate
        from owstudio.core.energy.production import EnergyError
        from owstudio.core.energy.summary import energy_series, run_energy
        from owstudio.core.i18n import current

        try:
            energy: dict[str, Any] = remember(
                ("energy", *self._stamp, "auto", current()),
                lambda: run_energy(self.root, self.case),
            )
            series: pd.DataFrame = remember(
                ("energy_series", *self._stamp, "auto", "raw", None, None, None, current()),
                lambda: energy_series(self.root, self.case, "auto", "raw"),
            )
        except EnergyError:
            energy, series = {}, pd.DataFrame()
        total = energy.get("total")
        if isinstance(total, dict) and total.get("covered_h"):
            farms = [c for c in series.columns[1:] if not str(c).endswith("_without_wakes")]
            summary["energy_mwh"] = total["energy_mwh"]
            summary["mean_power_mw"] = total["mean_power_mw"]
            summary["max_power_mw"] = float(series[farms].sum(axis=1).max()) if farms else None
            summary["capacity_factor"] = total["capacity_factor"]
            reference = total.get("reference_energy_mwh")
            if reference:
                summary["ideal_mean_power_mw"] = reference / total["covered_h"]
                summary["wake_efficiency"] = total["energy_mwh"] / reference
            summary["notes"] = [str(energy.get("method_text", ""))]
            return bool(reference)
        production = integrate.integrate(power * 1e6)
        summary["energy_mwh"] = production.energy_wh / 1e6
        summary["mean_power_mw"] = (
            production.mean_power_w / 1e6 if production.mean_power_w is not None else None
        )
        summary["capacity_factor"] = integrate.capacity_factor(production, self.installed_mw * 1e6)
        summary["notes"] = [
            tr(
                "Energy from WRF's POWER of the history files, trapezoidal integration",
                "Énergie tirée du POWER de WRF des wrfout, intégration par trapèzes",
            )
        ]
        return False

    def warm(self) -> None:
        """Computes ahead what the results page shows first: the wind at hub height on the farm
        domain at every time, and its colour range, so that the map and its animation open at
        once. Run in the background (see warm_in_background)."""
        number = self.farm_domain or max(self.files("main"), default=None)
        if number is None:
            return
        self.color_range("hub_wind", number)
        for time in range(len(self.times(number))):
            self.map_image("hub_wind", number, time)

    def available_fields(self) -> dict[str, list[str]]:
        """The map fields of each domain: the power only where the farm scheme wrote POWER, the
        change due to the farms only with the run without turbines."""
        needs = (
            ("hub_wind", "U"),
            ("wind10", "U10"),
            ("power", "POWER"),
            ("pblh", "PBLH"),
            ("t2", "T2"),
        )
        fields: dict[str, list[str]] = {}
        for number in sorted(self.files("main")):
            files = self._history("main", number)
            names = [name for name, variable in needs if files.has(variable)]
            if self.has_control and "hub_wind" in names:
                names.insert(1, "wake")
            fields[str(number)] = names
        return fields

    def times(self, number: int) -> pd.DatetimeIndex:
        return self._history("main", number).times

    def field(self, variable: Variable, number: int, time: int | None) -> np.ndarray:
        """A 2D field at one output time, or averaged over the run (initial state excluded)."""
        if time is not None:
            return self._frame(variable, number, time)
        sums = counts = None
        for index in range(1 if self._initial_first(number) else 0, len(self.times(number))):
            values = self._frame(variable, number, index)
            finite = np.isfinite(values)
            if sums is None:
                sums, counts = np.zeros_like(values), np.zeros_like(values)
            sums += np.where(finite, values, 0)
            counts += finite
        if sums is None or counts is None:
            raise LookupError(tr("No retained outputs", "Aucune sortie gardée"))
        return np.asarray(np.divide(sums, counts, out=np.full_like(sums, np.nan), where=counts > 0))

    def color_range(self, variable: Variable, number: int) -> tuple[float, float]:
        """Fixed for all times so that an animation stays comparable from frame to frame."""
        limits: tuple[float, float] = remember(
            ("range", *self._stamp, variable, number),
            lambda: self._compute_color_range(variable, number),
        )
        return limits

    def map_image(self, variable: Variable, number: int, time: int | None) -> np.ndarray:
        """The field resampled on the map's projection (see mapimage.py), north at the top."""
        from owstudio.core.postproc import mapimage

        return mapimage.reproject(self.field(variable, number, time), self.case.grid, number)

    def map_corners(self, number: int) -> list[list[float]]:
        from owstudio.core.postproc import mapimage

        lat, _ = self._history("main", number).coordinates
        return mapimage.corners(self.case.grid, number, lat.shape)

    def _compute_color_range(self, variable: Variable, number: int) -> tuple[float, float]:
        count = len(self.times(number))
        if not count:
            raise LookupError(tr("No retained outputs", "Aucune sortie gardée"))
        values = np.concatenate(
            [
                self._frame(variable, number, int(k)).ravel()
                for k in np.unique(np.linspace(0, count - 1, min(count, 24), dtype=int))
            ]
        )
        if VARIABLES[variable].diverging:
            limit = float(np.nanpercentile(np.abs(values), 99.5)) or 0.1
            return -limit, limit
        if variable == "power":
            return 0.0, float(np.nanmax(values)) or 1.0
        low, high = np.nanpercentile(values, [1, 99])
        return float(low), float(high)

    def point(self, number: int, lat: float, lon: float) -> pd.DataFrame | None:
        """Hub-height wind at a point, with and without turbines when available."""
        main_files = self._history("main", number)
        try:
            position = locate(*main_files.coordinates, lat, lon)
        except OutsideGrid:
            return None
        main_extracted = point_series(
            main_files, position, "wind_speed", self.hub_height_m, "agl", "nearest"
        )
        frame = main_extracted.values.rename("hub_wind").to_frame()
        if self.has_control:
            files = self._history("control", number)
            reference = point_series(
                files,
                locate(*files.coordinates, lat, lon),
                "wind_speed",
                self.hub_height_m,
                "agl",
                "nearest",
            )
            frame = frame.join(reference.values.rename("hub_wind_control"))
        return frame


_WARMING: set[tuple[Any, ...]] = set()


# Off in the tests: their fixtures write NetCDF files without the lock of ncio.py while the
# warm-up of an earlier test may still be reading
WARMING = True


def warm_in_background(key: tuple[Any, ...], work: Callable[[], object]) -> None:
    """Runs ``work`` once per key in a background thread, in the language of the request."""
    import contextvars

    if not WARMING:
        return
    with _COMPUTED_LOCK:
        if key in _WARMING:
            return
        _WARMING.add(key)

    def run() -> None:
        try:
            work()
        except Exception:  # noqa: BLE001 - the page computes it again and shows the error
            with _COMPUTED_LOCK:
                _WARMING.discard(key)

    threading.Thread(target=contextvars.copy_context().run, args=(run,), daemon=True).start()


# ------------------------------------------------------------------ map images


def field_png(
    field: np.ndarray, vmin: float, vmax: float, colormap: str, north_up: bool = False
) -> bytes:
    """One pixel per value; missing values are transparent. A grid field has south at the bottom
    (row 0 is the southern edge); an image from mapimage.py has north at the top."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    buffer = io.BytesIO()
    masked = np.ma.masked_invalid(field)
    plt.imsave(
        buffer,
        masked,
        vmin=vmin,
        vmax=vmax,
        cmap=colormap,
        origin="upper" if north_up else "lower",
        format="png",
    )
    return buffer.getvalue()


def legend_colors(colormap: str, count: int = 7) -> list[str]:
    """Evenly spaced colours of a colormap, for a gradient legend."""
    import matplotlib

    cmap = matplotlib.colormaps[colormap]
    return [matplotlib.colors.to_hex(cmap(k / (count - 1))) for k in range(count)]
