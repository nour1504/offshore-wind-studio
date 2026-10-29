"""Planning of the windows and WPS passes (core/method/plan.py)."""

import itertools
from datetime import datetime, timedelta
from fractions import Fraction

import pytest
from helpers import history_source, history_times

from owstudio.core.method.plan import (
    kept_steps,
    plan_period,
)

H = timedelta(hours=1)


def d(text: str) -> datetime:
    return datetime.fromisoformat(text)


def test_antichronological_order_with_the_short_window_first() -> None:
    plan = plan_period(d("2024-03-01"), d("2024-03-11"), 12, 72, "month")
    windows = plan.windows
    # 240 h from the end by 72 h: 24 + 72 + 72 + 72
    assert [w.useful_hours for w in windows] == [24, 72, 72, 72]
    assert windows[-1].useful_end == d("2024-03-11")
    assert windows[0].useful_start == d("2024-03-01")
    assert [w.order for w in windows] == [4, 3, 2, 1]
    assert [w.index for w in plan.computation] == [4, 3, 2, 1]
    for before, after in itertools.pairwise(windows):
        assert before.useful_end == after.useful_start
    for window in windows:
        assert window.simulation_start == window.useful_start - 12 * H
        assert window.simulation_end == window.useful_end


def test_month_blocks_never_cross_a_month_and_are_cut_from_their_end() -> None:
    # Across the end of February of a leap year
    plan = plan_period(d("2024-02-20"), d("2024-03-08"), 12, 72, "month")
    assert [b.id for b in plan.blocks] == ["2024-02", "2024-03"]
    february, march = plan.blocks
    assert february.end == march.start == d("2024-03-01")
    # 20 February -> 1 March 2024 = 10 days = 240 h = 24 + 3 x 72
    assert [w.useful_hours for w in february.windows] == [24, 72, 72, 72]
    # 1 -> 8 March = 168 h = 24 + 72 + 72
    assert [w.useful_hours for w in march.windows] == [24, 72, 72]
    for block in plan.blocks:
        for window in block.windows:
            assert block.start <= window.useful_start < window.useful_end <= block.end
    # Blocks are computed antichronologically too: all of March before February
    order = [w.block for w in plan.computation]
    assert order == ["2024-03"] * 3 + ["2024-02"] * 4


def test_29_february_and_a_whole_february() -> None:
    plan = plan_period(d("2024-02-01"), d("2024-03-01"), 12, 72, "month")
    # 29 days = 696 h = 48 + 9 x 72
    assert [w.useful_hours for w in plan.windows] == [48] + [72] * 9
    assert plan.windows[-1].useful_start == d("2024-02-27")
    plan = plan_period(d("2023-02-01"), d("2023-03-01"), 12, 72, "month")
    assert [w.useful_hours for w in plan.windows] == [24] + [72] * 9


def test_change_of_year() -> None:
    plan = plan_period(d("2023-12-28"), d("2024-01-03"), 12, 72, "month")
    assert [b.id for b in plan.blocks] == ["2023-12", "2024-01"]
    assert plan.blocks[0].windows[-1].useful_end == d("2024-01-01")
    # The first January window spins up in December
    assert plan.blocks[1].windows[0].simulation_start == d("2023-12-31T12:00")
    # One WPS pass per year, cut to the period, each starting S before its own start
    assert [(p.year, p.start, p.end) for p in plan.wps_passes] == [
        (2023, d("2023-12-27T12:00"), d("2024-01-01")),
        (2024, d("2023-12-31T12:00"), d("2024-01-03")),
    ]


def test_wps_single_pass_within_a_year_and_end_on_new_year() -> None:
    plan = plan_period(d("2024-06-01"), d("2024-06-10"), 24, 72, "month")
    assert [(p.year, p.start, p.end) for p in plan.wps_passes] == [
        (2024, d("2024-05-31"), d("2024-06-10"))
    ]
    # Ending exactly on 1 January: nothing useful in the new year, no pass for it
    plan = plan_period(d("2024-12-20"), d("2025-01-01"), 12, 72, "month")
    assert [p.year for p in plan.wps_passes] == [2024]


def test_week_blocks_start_on_monday() -> None:
    # Thursday 29 February 2024 to Wednesday 13 March
    plan = plan_period(d("2024-02-29"), d("2024-03-13"), 12, 72, "week")
    assert [b.id for b in plan.blocks] == ["2024-02-26", "2024-03-04", "2024-03-11"]
    assert [b.start for b in plan.blocks] == [d("2024-02-29"), d("2024-03-04"), d("2024-03-11")]
    # A full week: 168 h = 24 + 72 + 72
    assert [w.useful_hours for w in plan.blocks[1].windows] == [24, 72, 72]
    for block in plan.blocks:
        assert block.end.weekday() == 0 or block.end == plan.end


def test_quarter_blocks_follow_the_calendar_quarters() -> None:
    plan = plan_period(d("2024-02-15"), d("2024-07-10"), 12, 72, "quarter")
    assert [(b.id, b.start, b.end) for b in plan.blocks] == [
        ("2024-Q1", d("2024-02-15"), d("2024-04-01")),
        ("2024-Q2", d("2024-04-01"), d("2024-07-01")),
        ("2024-Q3", d("2024-07-01"), d("2024-07-10")),
    ]
    for block in plan.blocks:
        assert all(block.start <= w.useful_start < w.useful_end <= block.end for w in block.windows)
        assert block.windows[-1].useful_end == block.end
    # Across the year: the 4th quarter ends on 1 January
    plan = plan_period(d("2024-11-20"), d("2025-01-05"), 12, 72, "quarter")
    assert [b.id for b in plan.blocks] == ["2024-Q4", "2025-Q1"]
    assert plan.blocks[0].end == d("2025-01-01")


def test_each_window_is_its_own_block() -> None:
    plan = plan_period(d("2024-02-28"), d("2024-03-05"), 12, 72, "window")
    # 144 h = 72 + 72, cut from the end across the month limit
    assert [(b.id, b.start, b.end) for b in plan.blocks] == [
        ("f001", d("2024-02-28"), d("2024-03-02")),
        ("f002", d("2024-03-02"), d("2024-03-05")),
    ]


@pytest.mark.parametrize("spin", [6, 12, 24, 36])
def test_spin_up_lengths(spin: int) -> None:
    plan = plan_period(d("2024-03-01"), d("2024-03-07"), spin, 72, "month")
    for window in plan.windows:
        assert window.useful_start - window.simulation_start == spin * H
    assert plan.forcing_start == d("2024-03-01") - spin * H
    assert plan.wps_passes[0].start == d("2024-03-01") - spin * H


def test_period_not_longer_than_the_useful_window() -> None:
    for hours in (24, 72):
        plan = plan_period(d("2024-02-28"), d("2024-02-28") + hours * H, 12, 72, "month")
        assert plan.single
        (window,) = plan.windows
        assert window.simulation_start == d("2024-02-27T12:00")
        assert window.simulated_seconds == (hours + 12) * 3600
    # 73 h crosses the month limit: two months, cut at 1 March
    plan = plan_period(d("2024-02-28"), d("2024-02-28") + 73 * H, 12, 72, "month")
    assert [w.useful_hours for w in plan.windows] == [48, 25]


def test_history_source_and_times() -> None:
    plan = plan_period(d("2024-03-01"), d("2024-03-08"), 12, 72, "month")
    first, second, third = plan.windows
    assert history_source(plan, d("2024-03-01")) is first  # D: end of the first spin-up
    assert history_source(plan, first.useful_end) is first  # a junction: the earlier window
    assert history_source(plan, first.useful_end + H) is second
    assert history_source(plan, d("2024-03-08")) is third
    times = history_times(plan, H)
    assert times[0] == d("2024-03-01") and times[-1] == d("2024-03-08")
    assert len(times) == 7 * 24 + 1


def test_kept_steps() -> None:
    plan = plan_period(d("2024-03-01"), d("2024-03-04"), 12, 72, "month")
    (window,) = plan.windows
    # Reference script: time_step 30 s, nest ratio 3 -> 10 s; 4320 spin-up lines
    first, last = kept_steps(window, Fraction(10))
    assert first == 4321 and last == 84 * 360
    assert last - first + 1 == 72 * 360
    # A step not dividing the spin-up: 35/3 s
    first, last = kept_steps(window, Fraction(35, 3))
    assert (first - 1) * Fraction(35, 3) <= 12 * 3600 < first * Fraction(35, 3)
    assert last * Fraction(35, 3) <= 84 * 3600 < (last + 1) * Fraction(35, 3)


def test_restart_chains_the_same_windows_chronologically_with_one_spin_up() -> None:
    cold = plan_period(datetime(2016, 1, 1), datetime(2017, 1, 1), 12, 72, "month")
    chained = plan_period(datetime(2016, 1, 1), datetime(2017, 1, 1), 12, 72, "month", restart=True)
    assert chained.restart and not cold.restart
    assert [(w.useful_start, w.useful_end) for w in chained.windows] == [
        (w.useful_start, w.useful_end) for w in cold.windows
    ]
    assert [w.index for w in chained.computation] == list(range(1, len(chained.windows) + 1))
    assert chained.windows[0].simulation_start == datetime(2015, 12, 31, 12)
    assert all(w.simulation_start == w.useful_start for w in chained.windows[1:])
    assert [w.restart for w in chained.windows[:2]] == [False, True]
    single = plan_period(datetime(2016, 1, 1), datetime(2016, 1, 3), 12, 72, "month", True)
    assert not single.restart and not single.windows[0].restart
