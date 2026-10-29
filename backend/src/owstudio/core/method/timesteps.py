"""Time step of every domain, as WRF computes it from namelist.input.

The outer domain advances by time_step + time_step_fract_num / time_step_fract_den seconds; a
nest by its parent's step divided by its parent_time_step_ratio. With use_adaptive_time_step the
step varies during the run: the post-processing then reads the times written by WRF.
"""

from dataclasses import dataclass
from fractions import Fraction
from typing import Any

from owstudio.core.case.model import Case
from owstudio.core.i18n import tr
from owstudio.core.namelist.generate import build_namelist_input


@dataclass(frozen=True)
class TimeSteps:
    # Seconds, exact, one per domain
    steps: tuple[Fraction, ...]
    adaptive: bool

    def text(self, number: int) -> str:
        step = self.steps[number - 1]
        return f"{float(step):g}" if step.denominator == 1 else f"{float(step):.4f}".rstrip("0")


def _per_domain(value: Any, number: int) -> Any:
    if isinstance(value, list):
        return value[min(number, len(value)) - 1]
    return value


def time_steps(case: Case) -> TimeSteps:
    domains = build_namelist_input(case)["domains"]
    base = Fraction(int(domains.get("time_step", 0)))
    numerator = int(domains.get("time_step_fract_num", 0) or 0)
    denominator = int(domains.get("time_step_fract_den", 1) or 1)
    if numerator:
        base += Fraction(numerator, denominator)
    if base <= 0:
        raise ValueError(
            tr(
                "The time step of domain 1 must be positive",
                "Le pas de temps du domaine 1 doit être positif",
            )
        )
    parents = [0] + [d.parent_id for d in case.grid.domains[1:]]
    ratios = domains.get("parent_time_step_ratio", 1)
    steps: list[Fraction] = []
    for number in range(1, case.max_dom + 1):
        if number == 1:
            steps.append(base)
            continue
        ratio = int(_per_domain(ratios, number) or 1)
        steps.append(steps[parents[number - 1] - 1] / ratio)
    adaptive = _per_domain(domains.get("use_adaptive_time_step", False), 1) is True
    return TimeSteps(tuple(steps), adaptive)


def _interval_seconds(control: Any, stream: str, number: int, default_minutes: int) -> int:
    """Interval of an output stream as WRF sets its alarm (tools/gen_streams.c,
    share/set_timekeeping.F): <stream>_interval (minutes) is used only when <stream>_interval_m
    is zero, and the day, hour, minute and second parts add up."""

    def part(suffix: str) -> int:
        return int(_per_domain(control.get(f"{stream}_interval_{suffix}", 0), number) or 0)

    minutes = part("m") or int(
        _per_domain(control.get(f"{stream}_interval", default_minutes), number) or 0
    )
    return part("d") * 86400 + part("h") * 3600 + minutes * 60 + part("s")


def history_seconds(case: Case) -> list[int]:
    """Interval of the history files of every domain, seconds."""
    control = build_namelist_input(case)["time_control"]
    return [_interval_seconds(control, "history", n, 60) for n in range(1, case.max_dom + 1)]


def restart_seconds(case: Case) -> int:
    """Interval of the restart files, set from domain 1; 0 writes none."""
    return _interval_seconds(build_namelist_input(case)["time_control"], "restart", 1, 0)


def frames_per_outfile(case: Case) -> list[int]:
    control = build_namelist_input(case)["time_control"]
    value = control.get("frames_per_outfile", 1)
    return [int(_per_domain(value, number)) for number in range(1, case.max_dom + 1)]
