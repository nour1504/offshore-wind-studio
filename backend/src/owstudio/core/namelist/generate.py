"""Generate namelist.wps and namelist.input from a case."""

from dataclasses import dataclass
from typing import Any

import f90nml

from owstudio.core.case.model import Case, NamelistValue
from owstudio.core.tslist import namelist_settings as tslist_settings

# Placeholder until metgrid has run: the real value depends on the input data
DEFAULT_METGRID_LEVELS = 34
DEFAULT_METGRID_SOIL_LEVELS = 4
WINDFARM_OPT = {"fitch": 1, "mav": 2}


@dataclass(frozen=True)
class EnginePaths:
    """Locations inside the engine image."""

    geog_data: str = "/geog/WPS_GEOG/"
    geogrid_tables: str = "/opt/wrf/WPS/geogrid/"
    metgrid_tables: str = "/opt/wrf/WPS/metgrid/"


DEFAULT_ENGINE_PATHS = EnginePaths()


def _wps_date(case: Case, which: str) -> str:
    value = getattr(case.period, which)
    return str(value.strftime("%Y-%m-%d_%H:%M:%S"))


def _to_namelist(groups: dict[str, dict[str, Any]]) -> f90nml.Namelist:
    """Build a Namelist keeping the insertion order.

    f90nml sorts plain dicts, but WPS reads its groups in sequence without
    rewinding, so &share must stay before &geogrid.
    """
    return f90nml.Namelist(
        [(group, f90nml.Namelist(list(options.items()))) for group, options in groups.items()]
    )


def _apply_overrides(
    nml: dict[str, dict[str, Any]], overrides: dict[str, dict[str, NamelistValue]]
) -> None:
    for group, options in overrides.items():
        target = nml.setdefault(group.lower(), {})
        for key, value in options.items():
            name = key.lower()
            if name in ("_start_index", "_complex") and isinstance(value, dict):
                target[name] = {option.lower(): item for option, item in value.items()}
            else:
                target[name] = value


def build_namelist_wps(case: Case, paths: EnginePaths = DEFAULT_ENGINE_PATHS) -> f90nml.Namelist:
    grid = case.grid
    n = case.max_dom
    proj = grid.projection
    geogrid: dict[str, Any] = {
        # WPS expects the outer domain to be its own parent
        "parent_id": [1] + [d.parent_id for d in grid.domains[1:]],
        "parent_grid_ratio": [d.parent_grid_ratio for d in grid.domains],
        "i_parent_start": [d.i_parent_start for d in grid.domains],
        "j_parent_start": [d.j_parent_start for d in grid.domains],
        "e_we": [d.e_we for d in grid.domains],
        "e_sn": [d.e_sn for d in grid.domains],
        "geog_data_res": [d.geog_data_res for d in grid.domains],
        "dx": grid.dx,
        "dy": grid.dx,
        "map_proj": proj.map_proj,
        "ref_lat": proj.ref_lat,
        "ref_lon": proj.ref_lon,
    }
    for name in ("truelat1", "truelat2", "stand_lon"):
        if getattr(proj, name) is not None:
            geogrid[name] = getattr(proj, name)
    geogrid["geog_data_path"] = paths.geog_data
    geogrid["opt_geogrid_tbl_path"] = paths.geogrid_tables

    nml: dict[str, dict[str, Any]] = {
        "share": {
            "wrf_core": "ARW",
            "max_dom": n,
            "start_date": [_wps_date(case, "start")] * n,
            "end_date": [_wps_date(case, "end")] * n,
            "interval_seconds": case.period.interval_seconds,
            "opt_output_from_geogrid_path": "./",
        },
        "geogrid": geogrid,
        "ungrib": {"out_format": "WPS", "prefix": "FILE"},
        # Later sources take priority in metgrid: the land source, then a separate SST
        "metgrid": {
            "fg_name": fg_names(case) if len(fg_names(case)) > 1 else "FILE",
            "opt_metgrid_tbl_path": paths.metgrid_tables,
        },
    }
    _apply_overrides(nml, case.namelist_wps)
    return _to_namelist(nml)


def fg_names(case: Case) -> list[str]:
    """Sources read by metgrid, in order: the atmosphere, the land source, the separate SST."""
    names = ["FILE"]
    if case.land is not None:
        names.append(case.land.prefix)
    if case.sea_surface.source == "grib":
        names.append("SST")
    return names


def _time_control(case: Case) -> dict[str, Any]:
    n = case.max_dom
    start, end = case.period.start, case.period.end
    seconds = int((end - start).total_seconds())
    return {
        "run_days": 0,
        "run_hours": seconds // 3600,
        "run_minutes": seconds % 3600 // 60,
        "run_seconds": seconds % 60,
        "start_year": [start.year] * n,
        "start_month": [start.month] * n,
        "start_day": [start.day] * n,
        "start_hour": [start.hour] * n,
        "end_year": [end.year] * n,
        "end_month": [end.month] * n,
        "end_day": [end.day] * n,
        "end_hour": [end.hour] * n,
        **({"start_minute": [start.minute] * n} if start.minute else {}),
        **({"start_second": [start.second] * n} if start.second else {}),
        **({"end_minute": [end.minute] * n} if end.minute else {}),
        **({"end_second": [end.second] * n} if end.second else {}),
        "interval_seconds": case.period.interval_seconds,
        "input_from_file": [True] * n,
        "history_interval": [case.history_interval_minutes] * n,
        # One file per time: each window replaces the spin-up files of the next by name
        "frames_per_outfile": [1] * n,
        "restart": False,
        "restart_interval": no_restart_minutes(case),
        "io_form_history": 2,
        "io_form_restart": 2,
        "io_form_input": 2,
        "io_form_boundary": 2,
        "debug_level": 0,
        **_iofields(case),
        **_sst_update_files(case),
    }


def no_restart_minutes(case: Case) -> int:
    """A restart interval longer than any window of the case, so that WRF writes no restart
    file: windows last at most the useful window or the period, plus the spin-up."""
    period = int((case.period.end - case.period.start).total_seconds() // 60)
    return max(period, case.windows.useful_hours * 60) + case.spin_up_hours * 60 + 1440


def sst_update_minutes(case: Case) -> int:
    """Interval of the SST updates: README.namelist says it generally matches interval_seconds,
    since real.exe writes wrflowinp at the times of the boundary data."""
    return case.sea_surface.update_interval_minutes or case.period.interval_seconds // 60


def _sst_update_files(case: Case) -> dict[str, Any]:
    if not case.sea_surface.update:
        return {}
    return {
        "auxinput4_inname": "wrflowinp_d<domain>",
        "auxinput4_interval": [sst_update_minutes(case)] * case.max_dom,
        "io_form_auxinput4": 2,
    }


IOFIELDS_FILE = "iofields.txt"


def iofields_text(case: Case) -> str:
    """Contents of the iofields file: variables added to and removed from the history stream."""
    lines = []
    if case.outputs.add:
        lines.append("+:h:0:" + ",".join(case.outputs.add))
    if case.outputs.remove:
        lines.append("-:h:0:" + ",".join(case.outputs.remove))
    return "".join(f"{line}\n" for line in lines)


def _iofields(case: Case) -> dict[str, Any]:
    if not iofields_text(case):
        return {}
    return {"iofields_filename": [IOFIELDS_FILE] * case.max_dom, "ignore_iofields_warning": True}


def _vertical_levels(case: Case) -> dict[str, Any]:
    """The levels typed by the user (eta_levels), or the automatic levels of real.exe with their
    settings."""
    grid = case.grid
    if grid.eta_levels:
        return {"eta_levels": list(grid.eta_levels)}
    return {
        "auto_levels_opt": 2,
        "dzbot": grid.dzbot,
        "dzstretch_s": grid.dzstretch_s,
        "dzstretch_u": grid.dzstretch_u,
        "max_dz": grid.max_dz,
    }


def _domains(case: Case) -> dict[str, Any]:
    grid = case.grid
    spacing = grid.domain_dx()
    return {
        # Conservative: below the usual 6 s per km limit for stability
        "time_step": int(5 * grid.dx / 1000),
        "time_step_fract_num": 0,
        "time_step_fract_den": 1,
        "max_dom": case.max_dom,
        "e_we": [d.e_we for d in grid.domains],
        "e_sn": [d.e_sn for d in grid.domains],
        "e_vert": [grid.e_vert] * case.max_dom,
        "p_top_requested": grid.p_top_requested,
        **_vertical_levels(case),
        "num_metgrid_levels": DEFAULT_METGRID_LEVELS,
        "num_metgrid_soil_levels": DEFAULT_METGRID_SOIL_LEVELS,
        "dx": spacing,
        "dy": spacing,
        "grid_id": list(range(1, case.max_dom + 1)),
        "parent_id": [0] + [d.parent_id for d in grid.domains[1:]],
        "i_parent_start": [d.i_parent_start for d in grid.domains],
        "j_parent_start": [d.j_parent_start for d in grid.domains],
        "parent_grid_ratio": [d.parent_grid_ratio for d in grid.domains],
        "parent_time_step_ratio": [d.parent_grid_ratio for d in grid.domains],
        "feedback": 1,
        "smooth_option": 0,
        **tslist_settings(case),
    }


# WRF 4.8 defaults of the wind farm options (Registry.EM_COMMON): written only when changed,
# so that the namelist reads like a hand-written one
FARM_OPTION_DEFAULTS = {
    "windfarm_tke_factor": 0.25,
    "windfarm_induction": 1,
    "windfarm_wake_model": 2,
    "windfarm_overlap_method": 4,
}


def _physics(case: Case) -> dict[str, Any]:
    physics = dict(case.physics)
    if case.sea_surface.update:
        # real.exe then writes SST, sea ice, albedo and vegetation fraction to wrflowinp_d<nn>
        physics["sst_update"] = 1
    scheme = case.farm_scheme
    if scheme and case.active_turbines():
        opt = WINDFARM_OPT[scheme.scheme]
        physics["windfarm_opt"] = [
            opt if number in scheme.domains else 0 for number in range(1, case.max_dom + 1)
        ]
        # Fitch reads windturbines.txt (lat-lon, windfarm_ij = 0); MAV only reads
        # windturbines-ll.txt (lat-lon with farm numbers, windfarm_ij = 2) in WRF 4.8
        physics["windfarm_ij"] = 2 if scheme.scheme == "mav" else 0
        options: dict[str, Any] = {"windfarm_tke_factor": scheme.tke_factor}
        if scheme.scheme == "fitch":
            options["windfarm_induction"] = int(scheme.induction)
        else:
            options["windfarm_wake_model"] = [scheme.wake_model] * case.max_dom
            options["windfarm_overlap_method"] = [scheme.overlap_method] * case.max_dom
        for name, value in options.items():
            single = value[0] if isinstance(value, list) else value
            if single != FARM_OPTION_DEFAULTS[name]:
                physics[name] = value
    return physics


def build_namelist_input(case: Case) -> f90nml.Namelist:
    nml: dict[str, dict[str, Any]] = {
        "time_control": _time_control(case),
        "domains": _domains(case),
        "physics": _physics(case),
        "fdda": {},
        "dynamics": dict(case.dynamics),
        "bdy_control": {"spec_bdy_width": 5, "specified": True},
        "grib2": {},
        "namelist_quilt": {"nio_tasks_per_group": 0, "nio_groups": 1},
    }
    _apply_overrides(nml, case.namelist_input)
    return _to_namelist(nml)
