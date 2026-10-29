"""The case: every user choice for one simulation, independent of how WRF spells it."""

import itertools
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from owstudio.core.i18n import tr

# A namelist value: a scalar, or one value per domain
NamelistValue = Any


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Period(StrictModel):
    start: datetime
    end: datetime
    interval_seconds: int = Field(21600, gt=0, description="Spacing of the boundary data")

    @model_validator(mode="after")
    def _end_after_start(self) -> Self:
        if self.end <= self.start:
            raise ValueError(tr("end must be after start", "la fin doit être après le début"))
        return self


class Projection(StrictModel):
    map_proj: Literal["lambert", "mercator", "polar", "lat-lon"] = "lambert"
    ref_lat: float = Field(ge=-90, le=90)
    ref_lon: float = Field(ge=-180, le=180)
    truelat1: float | None = None
    truelat2: float | None = None
    stand_lon: float | None = None


class Domain(StrictModel):
    """One domain. For the outermost domain the parent fields are ignored."""

    e_we: int = Field(gt=1, description="Grid points west-east (staggered)")
    e_sn: int = Field(gt=1, description="Grid points south-north (staggered)")
    parent_id: int = Field(1, ge=1)
    parent_grid_ratio: int = Field(1, ge=1)
    i_parent_start: int = Field(1, ge=1)
    j_parent_start: int = Field(1, ge=1)
    geog_data_res: str = "default"


class Grid(StrictModel):
    projection: Projection
    dx: float = Field(gt=0, description="Grid spacing of the outermost domain, metres")
    # Empty while a new project is being prepared (a launch needs at least one, see checks.py)
    domains: list[Domain] = Field(default_factory=list)
    e_vert: int = Field(51, gt=2)
    p_top_requested: float = Field(5000.0, gt=0, description="Model top, Pa")
    # Automatic levels of real.exe (auto_levels_opt = 2, WRF 4.8 defaults): first layer
    # thickness, stretching near the surface and above, largest thickness
    dzbot: float = Field(50.0, gt=0, description="m")
    dzstretch_s: float = Field(1.3, ge=1.0)
    dzstretch_u: float = Field(1.1, ge=1.0)
    max_dz: float = Field(1000.0, gt=0, description="m")
    # Levels typed by the user instead of the automatic ones: full eta levels from 1 (surface) to
    # 0 (top), as many as e_vert (real.exe checks them, as vertical.py does); None: automatic
    eta_levels: list[float] | None = None

    @model_validator(mode="after")
    def _nests_fit_parents(self) -> Self:
        for number, nest in enumerate(self.domains[1:], start=2):
            if nest.parent_id >= number:
                raise ValueError(
                    tr(
                        f"domain {number}: parent must be an earlier domain",
                        f"domaine {number} : le parent doit être un domaine précédent",
                    )
                )
            parent = self.domains[nest.parent_id - 1]
            ratio = nest.parent_grid_ratio
            for size, start, parent_size, axis in (
                (nest.e_we, nest.i_parent_start, parent.e_we, "west-east"),
                (nest.e_sn, nest.j_parent_start, parent.e_sn, "south-north"),
            ):
                if (size - 1) % ratio:
                    raise ValueError(
                        tr(
                            f"domain {number}: {axis} size minus one must be a multiple of the ratio",
                            f"domaine {number} : la taille en {axis} moins un doit être un multiple du rapport",
                        )
                    )
                if start + (size - 1) // ratio >= parent_size:
                    raise ValueError(
                        tr(
                            f"domain {number} extends beyond its parent ({axis})",
                            f"le domaine {number} dépasse de son parent ({axis})",
                        )
                    )
        return self

    def domain_dx(self) -> list[float]:
        """Grid spacing of every domain, metres."""
        spacing: list[float] = []
        for number, domain in enumerate(self.domains, start=1):
            if number == 1:
                spacing.append(self.dx)
            else:
                spacing.append(spacing[domain.parent_id - 1] / domain.parent_grid_ratio)
        return spacing


class CurvePoint(StrictModel):
    wind_speed: float = Field(ge=0, description="m/s")
    thrust_coefficient: float = Field(ge=0)
    power_kw: float = Field(ge=0)


class TurbineType(StrictModel):
    name: str = ""
    hub_height_m: float = Field(gt=0)
    rotor_diameter_m: float = Field(gt=0)
    standing_thrust_coefficient: float = Field(ge=0)
    rated_power_mw: float = Field(gt=0)
    curve: list[CurvePoint] = Field(min_length=2)

    @model_validator(mode="after")
    def _wind_speeds_increase(self) -> Self:
        speeds = [p.wind_speed for p in self.curve]
        if any(b <= a for a, b in itertools.pairwise(speeds)):
            raise ValueError(
                tr(
                    f"turbine '{self.name}': curve wind speeds must strictly increase",
                    f"éolienne '{self.name}' : les vitesses de vent de la courbe doivent croître strictement",
                )
            )
        return self


class Turbine(StrictModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    type: int = Field(1, ge=1)
    # Label shown on maps and in tables, e.g. "A01"
    id: str | None = Field(None, max_length=32)


class FarmAppearance(StrictModel):
    """Presentation only, saved with the project and never sent to WRF."""

    color: str | None = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")
    symbol: Literal["auto", "circle", "cross", "plus", "square", "diamond", "triangle"] = "auto"


class Farm(StrictModel):
    """One wind farm: its turbines and descriptive properties."""

    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,32}$")
    name: str = Field(min_length=1, max_length=80)
    # Disabled farms stay in the project but are left out of the simulation
    enabled: bool = True
    # Free descriptive properties: operator, status, commissioning year...
    properties: dict[str, str] = Field(default_factory=dict)
    appearance: FarmAppearance = Field(default_factory=FarmAppearance)
    # Empty right after the farm is created; a launch needs at least one turbine per farm
    turbines: list[Turbine] = Field(default_factory=list)


class FarmScheme(StrictModel):
    """WRF wind farm parameterization, applied to every turbine of the enabled farms.

    Option values and defaults follow WRF 4.8's Registry and README.namelist.
    """

    # windfarm_opt: 1 = Fitch et al. (2012), 2 = MAV (Ma et al. 2022, sub-grid wake models)
    scheme: Literal["fitch", "mav"] = "fitch"
    domains: list[int] = Field(min_length=1, description="Domain numbers where the scheme runs")
    # windfarm_tke_factor: correction of the TKE coefficient (Archer et al. 2020)
    tke_factor: float = Field(0.25, ge=0)
    # windfarm_induction: axial induction correction (Vollmer et al. 2024), Fitch only
    induction: bool = True
    # windfarm_wake_model, MAV only: 1 Jensen, 2 XA, 3 GM, 4 Jensen+XA, 5 Jensen+XA+GM
    wake_model: Literal[1, 2, 3, 4, 5] = 2
    # windfarm_overlap_method, MAV with Jensen/XA: 1 linear, 2 squared, 3 modified squared,
    # 4 superposition of the hub-height wind speed (Ma et al. 2022)
    overlap_method: Literal[1, 2, 3, 4] = 4


def _legacy_wind_farm(data: dict[str, Any]) -> dict[str, Any]:
    """Converts the single ``wind_farm`` of early case files to farms and a farm scheme."""
    farm = data.pop("wind_farm", None)
    if not farm:
        return data
    data.setdefault(
        "farm_scheme", {"scheme": farm.get("scheme", "fitch"), "domains": farm["domains"]}
    )
    data.setdefault("turbine_types", farm.get("turbine_types", {}))
    groups: dict[str, list[dict[str, Any]]] = {}
    for turbine in farm.get("turbines", []):
        turbine = dict(turbine)
        groups.setdefault(str(turbine.pop("group", "main")), []).append(turbine)
    data.setdefault(
        "farms",
        [
            {"id": group, "name": "Wind farm" if group == "main" else group, "turbines": turbines}
            for group, turbines in groups.items()
        ],
    )
    return data


class TimeSeriesPoint(StrictModel):
    """A location written to WRF's tslist file."""

    name: str = Field(min_length=1, max_length=25)
    # Start of the output file names (prefix.d02.TS, ...): five characters at most
    prefix: str = Field(pattern=r"^[A-Za-z0-9_]{1,5}$")
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class TimeSeries(StrictModel):
    """WRF time series output (tslist): every model time step at chosen locations."""

    # One location per grid cell holding turbines (default), one per turbine, or none
    turbines: Literal["none", "each", "cells"] = "cells"
    # Additional locations: met masts, LiDARs, buoys...
    points: list[TimeSeriesPoint] = Field(default_factory=list)
    # Model levels written in the vertical profiles (max_ts_level)
    max_levels: int = Field(15, ge=1)


class GribInput(StrictModel):
    """Your own GRIB files, read by ungrib with a WPS Variable Table (Vtable)."""

    # Folder on this computer; its files are sent to the engine. Empty until chosen, so that a
    # project being prepared stays valid (a run is refused until it is set, see checks.py)
    folder: str = ""
    # Files of the folder to use, as a glob pattern
    pattern: str = "*"
    # Name of a table in WPS's ungrib/Variable_Tables (Vtable.GFS, Vtable.ECMWF...) or "custom"
    vtable: str = "Vtable.GFS"
    # Contents of the table when vtable is "custom"
    custom_vtable: str = ""


class LandInput(GribInput):
    """A land-surface source read by metgrid after the atmosphere, e.g. ERA5-Land (soil
    temperature and moisture, skin temperature, snow): metgrid gives priority to the later
    source for a field both provide (WPS metgrid/src/process_domain_module.F)."""

    # Prefix of its intermediate files, also its name in fg_name
    prefix: str = Field("LAND", pattern=r"^[A-Za-z][A-Za-z0-9_]{0,15}$")


class SeaSurface(StrictModel):
    """Sea surface temperature: taken from the atmospheric input, or from a separate product."""

    source: Literal["input", "grib"] = "input"
    # Separate SST files (OSTIA, RTG, ERA5 SST...), processed by ungrib under their own prefix
    grib: GribInput | None = None
    # Update the SST during the run (sst_update = 1, wrflowinp files): needed beyond a few days
    update: bool = False
    # Interval of the updates; None: the interval of the boundary data, as WRF expects
    update_interval_minutes: int | None = Field(None, gt=0)


# A WRF Registry variable name, as written in iofields files
REGISTRY_NAME = r"^[A-Za-z0-9_]{1,40}$"


class Outputs(StrictModel):
    """Variables added to or removed from WRF's history files (iofields_filename)."""

    # Registry names, e.g. RMOL (1/L, restart-only by default), ZNT, QKE
    add: list[Annotated[str, Field(pattern=REGISTRY_NAME)]] = Field(default_factory=list)
    remove: list[Annotated[str, Field(pattern=REGISTRY_NAME)]] = Field(default_factory=list)


class Windows(StrictModel):
    """Windows of a period longer than useful_hours (core/method/plan.py).

    By default independent cold starts: each window simulates its useful hours preceded by the
    case's spin-up, with no restart. With ``restart``, the same windows form one continuous
    simulation: a single spin-up before the first, then each window starts from the restart file
    written at the end of the previous one, in chronological order.
    Windows never cross the limit of a block (calendar month or quarter, week from Monday 00:00 UTC, or
    each window alone) and are cut from the end of their block.
    """

    useful_hours: int = Field(72, ge=1)
    grouping: Literal["month", "quarter", "week", "window"] = "month"
    restart: bool = False


# Version of the case format: 2 introduced the single spin-up and the windows
FORMAT_VERSION = 2


def _legacy_period(data: dict[str, Any]) -> dict[str, Any]:
    """Converts format 1 (optional windowing, restart segments, statistics spin-up) to format 2.

    - windowing {useful_hours, spin_up_hours}: the same useful period and spin-up;
    - otherwise the former spin_up_hours were the first simulated hours left out of statistics:
      the useful period then starts after them and they become the spin-up, so the same hours
      are simulated and kept; without them, the default spin-up of 12 h is added before;
    - restart segments are dropped: every window now starts cold.
    """
    legacy = ("windowing", "segment_hours", "spin_up_hours")
    if "format_version" in data or not any(key in data for key in legacy):
        return data
    data = dict(data)
    windowing = data.pop("windowing", None)
    data.pop("segment_hours", None)
    former = data.pop("spin_up_hours", 0) or 0
    if windowing is not None:
        data["spin_up_hours"] = windowing.get("spin_up_hours", 12)
        data.setdefault("windows", {"useful_hours": windowing.get("useful_hours", 72)})
    elif former > 0:
        data["spin_up_hours"] = former
        period = data.get("period")
        if isinstance(period, dict) and "start" in period and "end" in period:
            start = datetime.fromisoformat(str(period["start"]))
            end = datetime.fromisoformat(str(period["end"]))
            if start + timedelta(hours=former) < end:
                data["period"] = {**period, "start": start + timedelta(hours=former)}
    data["format_version"] = FORMAT_VERSION
    return data


class Case(StrictModel):
    format_version: int = FORMAT_VERSION
    name: str = Field(min_length=1)
    description: str = ""
    period: Period
    grid: Grid
    physics: dict[str, NamelistValue] = Field(default_factory=dict)
    dynamics: dict[str, NamelistValue] = Field(default_factory=dict)
    # Turbine models by WRF type number; types not listed use the tables shipped with WRF
    turbine_types: dict[int, TurbineType] = Field(default_factory=dict)
    farms: list[Farm] = Field(default_factory=list)
    # None: no wind farm parameterization, farms are ignored by WRF
    farm_scheme: FarmScheme | None = None
    history_interval_minutes: int = Field(60, gt=0)
    # Initial and boundary conditions: GFS analyses (NOAA, no account), ERA5 (Copernicus),
    # or your own GRIB files
    input_source: Literal["gfs", "era5", "grib"] = "gfs"
    grib: GribInput | None = None
    sea_surface: SeaSurface = Field(default_factory=SeaSurface)
    # Optional land-surface source (ERA5-Land...), used by the exported WPS script
    land: LandInput | None = None
    outputs: Outputs = Field(default_factory=Outputs)
    time_series: TimeSeries | None = None
    # period is the useful interval [D, F]. Every simulation starts this many hours before its
    # useful start (spin-up S), always applied, then discarded
    spin_up_hours: int = Field(12, ge=1)
    # Periods longer than useful_hours are cut into independent windows (core/method/plan.py)
    windows: Windows = Field(default_factory=Windows)
    # True for the case of one window (core/engine/windows.py): its period is then the
    # simulated interval, spin-up included. Never saved
    _window: bool = PrivateAttr(False)
    # Raw overrides applied last, {group: {option: value}}: every WRF option stays reachable
    namelist_wps: dict[str, dict[str, NamelistValue]] = Field(default_factory=dict)
    namelist_input: dict[str, dict[str, NamelistValue]] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _upgrade(cls, data: Any) -> Any:
        return _legacy_period(_legacy_wind_farm(dict(data))) if isinstance(data, dict) else data

    @model_validator(mode="after")
    def _farms_consistent(self) -> Self:
        if self.farm_scheme:
            count = len(self.grid.domains)
            for number in self.farm_scheme.domains:
                if not 1 <= number <= count:
                    raise ValueError(
                        tr(
                            f"wind farm domain {number} does not exist",
                            f"le domaine du parc {number} n'existe pas",
                        )
                    )
        if self.input_source == "grib" and self.grib is None:
            raise ValueError(
                tr(
                    "input_source 'grib' needs the grib settings (folder, Vtable)",
                    "la source 'grib' demande ses réglages (dossier, Vtable)",
                )
            )
        if self.land and self.land.prefix.upper() in ("FILE", "SST"):
            raise ValueError(
                tr(
                    "the land source needs a prefix other than FILE and SST",
                    "la source sol demande un préfixe autre que FILE et SST",
                )
            )
        if self.sea_surface.source == "grib" and self.sea_surface.grib is None:
            raise ValueError(
                tr(
                    "sea surface source 'grib' needs its grib settings (folder, Vtable)",
                    "la source 'grib' de la surface de la mer demande ses réglages (dossier, Vtable)",
                )
            )
        ids = [farm.id for farm in self.farms]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ValueError(
                tr(
                    f"farm identifiers must be unique: {', '.join(duplicates)}",
                    f"les identifiants des parcs doivent être uniques : {', '.join(duplicates)}",
                )
            )
        return self

    @property
    def max_dom(self) -> int:
        return len(self.grid.domains)

    @property
    def enabled_farms(self) -> list[Farm]:
        return [farm for farm in self.farms if farm.enabled]

    def active_turbines(self) -> list[tuple[Farm, Turbine]]:
        """Turbines WRF simulates: those of the enabled farms, when a farm scheme is set."""
        if self.farm_scheme is None:
            return []
        return [(farm, turbine) for farm in self.enabled_farms for turbine in farm.turbines]

    def with_farms(self, enabled: set[str]) -> "Case":
        """A copy where exactly the farms in ``enabled`` are simulated (a scenario)."""
        copy = self.model_copy(deep=True)
        for farm in copy.farms:
            farm.enabled = farm.id in enabled
        return copy

    @classmethod
    def from_yaml(cls, path: Path) -> Self:
        return cls.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))

    def to_yaml(self, path: Path) -> None:
        # The format version is always written, so that a later version reads it as such
        data = {
            "format_version": self.format_version,
            **self.model_dump(mode="json", exclude_defaults=True),
        }
        text = yaml.dump(data, Dumper=_CaseDumper, sort_keys=False, width=100)
        path.write_text(text, encoding="utf-8", newline="\n")


class _CaseDumper(yaml.SafeDumper):
    """Keeps short lists and small mappings on one line, e.g. ``mp_physics: [8, 8]``."""


def _is_scalar(value: object) -> bool:
    return not isinstance(value, (list, dict))


def _represent_list(dumper: yaml.SafeDumper, data: list[Any]) -> yaml.Node:
    flow = all(_is_scalar(v) for v in data)
    return dumper.represent_sequence("tag:yaml.org,2002:seq", data, flow_style=flow)


def _represent_dict(dumper: yaml.SafeDumper, data: dict[str, Any]) -> yaml.Node:
    flow = len(data) <= 3 and all(_is_scalar(v) for v in data.values())
    return dumper.represent_mapping("tag:yaml.org,2002:map", data.items(), flow_style=flow)


_CaseDumper.add_representer(list, _represent_list)
_CaseDumper.add_representer(dict, _represent_dict)
