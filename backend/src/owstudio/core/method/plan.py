"""Planning of the simulation windows and of the WPS passes.

Period [D, F] in UTC, spin-up S (always applied), useful window L.
- Up to L: one window, simulated from D - S to F.
- Longer: blocks (calendar month or quarter, week from Monday 00:00 UTC, or each window alone), each
  cut from its end into windows of L hours, the shortest at its start; no window crosses a block
  limit. Window k simulates [useful_start - S, useful_end] from a cold start (real.exe, wrf.exe,
  restart = .false.).
- Computing order: antichronological, in one run folder. A window's spin-up lies in the useful time
  of earlier windows computed afterwards, whose files (frames_per_outfile = 1) replace the spin-up
  ones; the file at D, end of the first spin-up, is kept, earlier ones are set aside.
- Retention: each window keeps ]useful_start, useful_end]; history covers [D, F], time series and
  averages ]D, F].
- WPS: one pass per calendar year, cut to the period, each starting S hours before its own start;
  every met_em file in one folder, so a window crossing 1 January finds both passes.
- Continuous with restart (option): the same windows in time order, one spin-up, each next window
  starting from the previous restart file (restart = .true., restart_interval = its length).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from fractions import Fraction
from typing import Literal

from owstudio.core.case.model import Case
from owstudio.core.i18n import tr
from owstudio.core.times import naive_utc

MAX_WINDOWS = 10_000
Grouping = Literal["month", "quarter", "week", "window"]


@dataclass(frozen=True)
class Window:
    # Chronological number, 1 = earliest
    index: int
    # Order of computation, 1 = computed first (the latest window)
    order: int
    block: str
    useful_start: datetime
    useful_end: datetime
    spin_up: timedelta
    # Continuous simulation with restart files: every window but the first starts from one
    chained: bool = False
    # End of what real.exe prepares (the boundary data time at or after the useful end), when it
    # differs from the end of the simulation
    prepared_end: datetime | None = None

    @property
    def id(self) -> str:
        return f"{self.index:03d}"

    @property
    def preparation_end(self) -> datetime:
        """real.exe's end: a boundary data time; wrf.exe stops at the useful end (run_*)."""
        return self.prepared_end or self.useful_end

    @property
    def preparation_seconds(self) -> int:
        return int((self.preparation_end - self.simulation_start).total_seconds())

    @property
    def restart(self) -> bool:
        return self.chained and self.index > 1

    @property
    def simulation_start(self) -> datetime:
        return self.useful_start - self.spin_up

    @property
    def simulation_end(self) -> datetime:
        return self.useful_end

    @property
    def simulated_seconds(self) -> int:
        return int((self.simulation_end - self.simulation_start).total_seconds())

    @property
    def useful_hours(self) -> float:
        return (self.useful_end - self.useful_start).total_seconds() / 3600


@dataclass(frozen=True)
class Block:
    id: str
    start: datetime
    end: datetime
    # Chronological
    windows: tuple[Window, ...]


@dataclass(frozen=True)
class WpsPass:
    year: int
    # The pass covers [start, end]: S hours before its useful start, to its useful end
    start: datetime
    end: datetime


@dataclass(frozen=True)
class Plan:
    start: datetime
    end: datetime
    spin_up_hours: int
    useful_hours: int
    grouping: Grouping
    # Chronological
    blocks: tuple[Block, ...]
    wps_passes: tuple[WpsPass, ...]
    restart: bool = False

    @property
    def windows(self) -> list[Window]:
        """Chronological."""
        return [window for block in self.blocks for window in block.windows]

    @property
    def computation(self) -> list[Window]:
        """In the order of computation: antichronological, chronological with restart."""
        return sorted(self.windows, key=lambda window: window.order)

    @property
    def single(self) -> bool:
        return len(self.windows) == 1

    @property
    def simulated_seconds(self) -> int:
        return sum(window.simulated_seconds for window in self.windows)

    @property
    def forcing_start(self) -> datetime:
        """First time the input data must cover: the first window's simulation start."""
        return min(window.simulation_start for window in self.windows)

    @property
    def forcing_end(self) -> datetime:
        """Last time the input data must cover: the last boundary data time real.exe reads."""
        return max(window.preparation_end for window in self.windows)


def _next_limit(time: datetime, grouping: Grouping) -> datetime | None:
    """First block limit strictly after ``time``; None when blocks have no calendar limit."""
    if grouping == "month":
        first = time.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return (
            first.replace(year=first.year + 1, month=1)
            if first.month == 12
            else first.replace(month=first.month + 1)
        )
    if grouping == "quarter":
        month = (time.month - 1) // 3 * 3 + 4
        first = time.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return (
            first.replace(year=first.year + 1, month=1)
            if month > 12
            else first.replace(month=month)
        )
    if grouping == "week":
        monday = (time - timedelta(days=time.weekday())).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return monday + timedelta(days=7)
    return None


def _block_id(start: datetime, grouping: Grouping) -> str:
    if grouping == "month":
        return start.strftime("%Y-%m")
    if grouping == "quarter":
        return f"{start.year}-Q{(start.month - 1) // 3 + 1}"
    monday = start - timedelta(days=start.weekday())
    return monday.strftime("%Y-%m-%d")


def _cut(start: datetime, end: datetime, step: timedelta) -> list[tuple[datetime, datetime]]:
    """Useful intervals of [start, end] cut from the end: the shortest first."""
    parts: list[tuple[datetime, datetime]] = []
    limit = end
    while limit > start:
        parts.append((max(start, limit - step), limit))
        limit = parts[-1][0]
        if len(parts) > MAX_WINDOWS:
            raise ValueError(
                tr("The plan is limited to 10 000 windows", "Le plan est limité à 10 000 fenêtres")
            )
    return parts[::-1]


_EPOCH = datetime(1970, 1, 1)


def _floor(time: datetime, seconds: int) -> datetime:
    """The boundary data time at or before ``time`` (data every ``seconds``; 0: unchanged)."""
    if seconds <= 0:
        return time
    return time - timedelta(seconds=int((time - _EPOCH).total_seconds()) % seconds)


def _ceil(time: datetime, seconds: int) -> datetime:
    """The boundary data time at or after ``time``."""
    below = _floor(time, seconds)
    return below if below == time else below + timedelta(seconds=seconds)


def _wps_passes(
    start: datetime, end: datetime, spin_up: timedelta, interval: int
) -> tuple[WpsPass, ...]:
    passes = []
    for year in range(start.year, end.year + 1):
        first = max(start, datetime(year, 1, 1))
        last = min(end, datetime(year + 1, 1, 1))
        if first < last:
            passes.append(WpsPass(year, _floor(first - spin_up, interval), _ceil(last, interval)))
    return tuple(passes)


def plan(case: Case) -> Plan:
    return plan_period(
        case.period.start,
        case.period.end,
        case.spin_up_hours,
        case.windows.useful_hours,
        case.windows.grouping,
        case.windows.restart,
        case.period.interval_seconds,
    )


def plan_period(
    start: datetime,
    end: datetime,
    spin_up_hours: int,
    useful_hours: int,
    grouping: Grouping,
    restart: bool = False,
    interval_seconds: int = 0,
) -> Plan:
    """The windows of [start, end]. With ``interval_seconds``, a window off the data times is
    prepared over the data times around it: spin-up from the data time at or before useful start
    - S, real.exe up to the data time at or after its useful end, wrf.exe stopping at the useful
    end (run_* wins over the end times, README.namelist)."""
    start, end = naive_utc(start), naive_utc(end)
    if end <= start:
        raise ValueError(
            tr(
                "The end of the period must be after its start",
                "La fin de la période doit être après son début",
            )
        )
    if spin_up_hours < 1 or useful_hours < 1:
        raise ValueError(
            tr(
                "Spin-up and useful window are at least one hour",
                "Le spin-up et la fenêtre utile durent au moins une heure",
            )
        )
    spin_up, step = timedelta(hours=spin_up_hours), timedelta(hours=useful_hours)
    # Chronological (block id, block start, block end, useful intervals)
    groups: list[tuple[str, datetime, datetime, list[tuple[datetime, datetime]]]] = []
    if end - start <= step:
        groups.append(("f001", start, end, [(start, end)]))
    elif grouping == "window":
        parts = _cut(start, end, step)
        groups += [(f"f{k:03d}", a, b, [(a, b)]) for k, (a, b) in enumerate(parts, 1)]
    else:
        limit = start
        while limit < end:
            following = _next_limit(limit, grouping)
            block_end = end if following is None else min(end, following)
            groups.append(
                (_block_id(limit, grouping), limit, block_end, _cut(limit, block_end, step))
            )
            limit = block_end
    count = sum(len(parts) for *_, parts in groups)
    if count > MAX_WINDOWS:
        raise ValueError(
            tr("The plan is limited to 10 000 windows", "Le plan est limité à 10 000 fenêtres")
        )
    blocks = []
    index = 0
    chained = restart and count > 1
    for block_id, block_start, block_end, parts in groups:
        windows = []
        for useful_start, useful_end in parts:
            index += 1
            order = index if restart else count - index + 1
            if index == 1 or not restart:
                spin = useful_start - _floor(useful_start - spin_up, interval_seconds)
            else:
                spin = timedelta(0)
            prepared = _ceil(useful_end, interval_seconds)
            windows.append(
                Window(
                    order=order,
                    index=index,
                    block=block_id,
                    useful_start=useful_start,
                    useful_end=useful_end,
                    spin_up=spin,
                    chained=chained,
                    prepared_end=prepared if prepared != useful_end else None,
                )
            )
        blocks.append(Block(block_id, block_start, block_end, tuple(windows)))
    return Plan(
        start,
        end,
        spin_up_hours,
        useful_hours,
        grouping,
        tuple(blocks),
        _wps_passes(start, end, spin_up, interval_seconds),
        chained,
    )


def kept_steps(window: Window, dt: Fraction) -> tuple[int, int]:
    """First and last step numbers kept from a window's time series, for a fixed step ``dt``
    in seconds. WRF writes them after each step, at n x dt from the simulation start
    (share/wrf_timeseries.F, called from med_after_solve_io once the clock has advanced);
    ]useful_start, useful_end] keeps the steps with S < n x dt <= S + useful duration."""
    spin = int(window.spin_up.total_seconds())
    total = window.simulated_seconds
    first = int(Fraction(spin) / dt) + 1
    last = int(Fraction(total) / dt)
    return first, last
