"""The windows planned by core/method/plan.py, as the checks and the readers of outputs see them.

windows.json tells the readers which times each window keeps, with the retention of the method:
]useful_start, useful_end] for every window, and D itself for the history of the first window
(time series always ]D, F]). Outputs of older versions, one folder per window, are read the
same way.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from owstudio.core.case.model import Case, Period
from owstudio.core.i18n import tr
from owstudio.core.method import plan as method
from owstudio.core.method.plan import utc
from owstudio.core.namelist.period import WPS_DATES, WRF_DATES, clear_metadata

MANIFEST_VERSION = 2


def utc_naive(value: datetime) -> datetime:
    return utc(value)


def utc_text(value: datetime) -> str:
    return utc(value).isoformat(timespec="seconds") + "Z"


@dataclass(frozen=True)
class Window:
    number: int
    simulation_start: datetime
    simulation_end: datetime
    useful_start: datetime
    useful_end: datetime
    # The first window also keeps the history at D, the end of its spin-up
    include_start: bool

    @property
    def id(self) -> str:
        return f"window{self.number:03d}"

    def accepts(self, time: datetime, history: bool = True) -> bool:
        stamp = utc(time)
        if stamp == self.useful_start:
            return history and self.include_start
        return self.useful_start < stamp <= self.useful_end

    def as_dict(self, state: str = "planned") -> dict[str, Any]:
        return {
            "id": self.id,
            "number": self.number,
            "simulation_start": utc_text(self.simulation_start),
            "simulation_end": utc_text(self.simulation_end),
            "useful_start": utc_text(self.useful_start),
            "useful_end": utc_text(self.useful_end),
            "include_start": self.include_start,
            "output_dir": f"windows/{self.id}",
            "state": state,
        }


def plan_windows(case: Case) -> list[Window]:
    """Chronological windows of a project; a window's own case has none."""
    if is_window(case):
        return []
    return [
        Window(
            w.index,
            w.simulation_start,
            w.simulation_end,
            w.useful_start,
            w.useful_end,
            w.index == 1,
        )
        for w in method.plan(case).windows
    ]


def simulated_seconds(case: Case) -> float:
    if is_window(case):
        return (case.period.end - case.period.start).total_seconds()
    return float(method.plan(case).simulated_seconds)


def canonical_namelist(groups: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Fortran group and option identifiers are case-insensitive; merge aliases accordingly."""
    result: dict[str, dict[str, Any]] = {}
    for group, options in groups.items():
        normalized = result.setdefault(group.lower(), {})
        for key, value in options.items():
            if key.lower() in ("_start_index", "_complex") and isinstance(value, dict):
                normalized[key.lower()] = {name.lower(): item for name, item in value.items()}
            else:
                normalized[key.lower()] = value
    return result


def is_window(case: Case) -> bool:
    """A window's own case: its period is the simulated interval, spin-up included."""
    return case._window


def forcing_case(case: Case) -> Case:
    """A copy whose period is everything prepared (spin-ups included, to the data time after the
    end): the input data must cover it."""
    if is_window(case):
        return case
    result = case.model_copy(deep=True)
    found = method.plan(case)
    result.period = Period(
        start=found.forcing_start,
        end=found.forcing_end,
        interval_seconds=case.period.interval_seconds,
    )
    result._window = True
    return result


def child_case(case: Case, window: Window | method.Window) -> Case:
    """The case of one window: its simulated interval, a cold start (restart = .false.) or, in a
    continuous simulation, a restart from the previous window with a restart file written at its
    own end, overriding any imported whole-run time or restart values."""
    result = case.model_copy(deep=True)
    result._window = True
    result.period = Period(
        start=window.simulation_start,
        end=window.simulation_end,
        interval_seconds=case.period.interval_seconds,
    )
    result.namelist_input = canonical_namelist(result.namelist_input)
    result.namelist_wps = canonical_namelist(result.namelist_wps)
    n = result.max_dom
    control = result.namelist_input.setdefault("time_control", {})
    clear_metadata(control, WRF_DATES | {"restart", "interval_seconds"})
    for which, time in (("start", window.simulation_start), ("end", window.simulation_end)):
        for part in ("year", "month", "day", "hour", "minute", "second"):
            control[f"{which}_{part}"] = [getattr(time, part)] * n
    duration = int((window.simulation_end - window.simulation_start).total_seconds())
    chained = isinstance(window, method.Window) and window.chained
    restart = isinstance(window, method.Window) and window.restart
    control.update(
        run_days=0,
        run_hours=duration // 3600,
        run_minutes=duration % 3600 // 60,
        run_seconds=duration % 60,
        restart=restart,
        interval_seconds=case.period.interval_seconds,
    )
    if chained:
        clear_metadata(control, {"restart_interval"})
        control["restart_interval"] = duration // 60
    _wps_dates(result, window.simulation_start, window.simulation_end)
    return result


def wps_pass_case(case: Case, wps: method.WpsPass) -> Case:
    """The case of one WPS pass: its year, spin-up included, in namelist.wps."""
    result = case.model_copy(deep=True)
    result._window = True
    result.period = Period(
        start=wps.start, end=wps.end, interval_seconds=case.period.interval_seconds
    )
    result.namelist_wps = canonical_namelist(result.namelist_wps)
    _wps_dates(result, wps.start, wps.end)
    return result


def _wps_dates(case: Case, start: datetime, end: datetime) -> None:
    share = case.namelist_wps.setdefault("share", {})
    clear_metadata(share, WPS_DATES | {"interval_seconds"})
    share.update(
        start_date=[start.strftime("%Y-%m-%d_%H:%M:%S")] * case.max_dom,
        end_date=[end.strftime("%Y-%m-%d_%H:%M:%S")] * case.max_dom,
        interval_seconds=case.period.interval_seconds,
    )


def manifest(case: Case, states: dict[str, str] | None = None) -> dict[str, Any]:
    windows = plan_windows(case)
    if not windows:
        raise ValueError(
            tr(
                "A window has no window plan of its own",
                "Une fenêtre n'a pas de plan de fenêtres propre",
            )
        )
    return {
        "schema_version": MANIFEST_VERSION,
        "mode": "independent_windows",
        "timezone": "UTC",
        "requested_start": utc_text(case.period.start),
        "requested_end": utc_text(case.period.end),
        "useful_hours": case.windows.useful_hours,
        "spin_up_hours": case.spin_up_hours,
        "grouping": case.windows.grouping,
        "retention": "]useful_start,useful_end]; history also keeps D (first window)",
        "raw_outputs_retained": True,
        "windows": [window.as_dict((states or {}).get(window.id, "planned")) for window in windows],
    }
