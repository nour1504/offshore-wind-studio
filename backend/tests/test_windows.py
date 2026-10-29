"""Independent windows: planning, fresh initialization, raw retention and simulated resumption.

No WRF binary, engine shell, download or external network is used.
"""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from owstudio.core.case.checks import _check_input_data, _check_method
from owstudio.core.case.model import Case, Windows
from owstudio.core.data import gfs
from owstudio.core.engine.windows import (
    plan_windows,
    simulated_seconds,
)
from owstudio.core.method import timesteps


def window_case(case: Case, hours: int = 180) -> Case:
    result = case.model_copy(deep=True)
    result.period.start = datetime(2025, 10, 1)
    result.period.end = result.period.start + timedelta(hours=hours)
    result.spin_up_hours = 12
    result.windows = Windows()
    return result


def test_72_useful_plus_12_preceding_and_short_first(reference_case: Case) -> None:
    case = window_case(reference_case)
    original = case.model_dump_json()
    windows = plan_windows(case)
    # Cut from the end: the shortest window comes first
    assert [(w.useful_end - w.useful_start).total_seconds() / 3600 for w in windows] == [36, 72, 72]
    assert [(w.simulation_end - w.simulation_start).total_seconds() / 3600 for w in windows] == [
        48,
        84,
        84,
    ]
    assert windows[0].simulation_start == datetime(2025, 9, 30, 12)
    assert windows[1].simulation_start == datetime(2025, 10, 2)
    assert windows[1].useful_start == windows[0].useful_end
    assert windows[-1].useful_end == case.period.end
    assert simulated_seconds(case) == 216 * 3600
    assert case.model_dump_json() == original


def test_retention_no_gap_duplicate_or_spinup(reference_case: Case) -> None:
    case = window_case(reference_case)
    windows = plan_windows(case)
    retained = []
    series = []
    for window in windows:
        time = window.simulation_start
        while time <= window.simulation_end:
            if window.accepts(time):
                retained.append(time)
            if window.accepts(time, history=False):
                series.append(time)
            time += timedelta(hours=1)
    # History [D, F], time series ]D, F]
    expected = [case.period.start + timedelta(hours=hour) for hour in range(181)]
    assert retained == expected
    assert series == expected[1:]
    assert windows[-1].accepts(case.period.end.replace(tzinfo=UTC))
    assert not windows[0].accepts(windows[0].simulation_start)


def test_former_case_files_are_converted(reference_case: Case) -> None:
    data = reference_case.model_dump(mode="json")
    data.pop("format_version")
    data.pop("windows")
    data.pop("spin_up_hours")
    data["period"] = {"start": "2025-10-01T00:00:00", "end": "2025-10-08T00:00:00"}
    # Independent windows: the same useful period and spin-up
    case = Case.model_validate(
        {**data, "spin_up_hours": 0, "windowing": {"useful_hours": 48, "spin_up_hours": 6}}
    )
    assert case.spin_up_hours == 6 and case.windows.useful_hours == 48
    assert case.period.start == datetime(2025, 10, 1)
    # Empty windowing: the defaults of the time, 72 h after 12 h
    case = Case.model_validate({**data, "spin_up_hours": 0, "windowing": {}})
    assert case.spin_up_hours == 12 and case.windows.useful_hours == 72
    # Statistics spin-up: those hours become the spin-up, the useful period starts after them
    case = Case.model_validate({**data, "spin_up_hours": 24, "segment_hours": 48})
    assert case.spin_up_hours == 24
    assert case.period.start == datetime(2025, 10, 2)
    assert case.period.end == datetime(2025, 10, 8)
    # Restart segments are dropped; no spin-up at all: the default one is added before
    case = Case.model_validate({**data, "segment_hours": 48})
    assert case.spin_up_hours == 12 and case.period.start == datetime(2025, 10, 1)
    assert case.format_version == 2
    with pytest.raises(ValidationError):
        Case.model_validate({**data, "format_version": 2, "spin_up_hours": 0})


def test_input_checks_include_spinup_before_gfs_archive(reference_case: Case) -> None:
    case = window_case(reference_case)
    case.period.start = datetime(2021, 1, 1)
    case.period.end = datetime(2021, 1, 4)
    assert gfs.files_for(case.period)  # requested useful dates alone would appear valid
    issues = _check_input_data(case)
    assert any(issue.severity == "error" and "GFS from" in issue.message for issue in issues)


def test_era5_availability_checked_with_preceding_spinup(
    reference_case: Case, monkeypatch: pytest.MonkeyPatch
) -> None:
    from owstudio.core.data import era5

    case = window_case(reference_case)
    case.input_source = "era5"
    calls = []
    monkeypatch.setattr(
        era5,
        "availability_error",
        lambda period: calls.append(period.start) or "synthetic unavailable prefix",
    )
    issues = _check_input_data(case)
    assert calls == [datetime(2025, 9, 30, 12)]
    assert any("unavailable prefix" in issue.message for issue in issues)


def method_errors(case: Case) -> list[str]:
    return [i.message for i in _check_method(case) if i.severity == "error"]


def test_history_interval_must_fit_the_windows(reference_case: Case) -> None:
    case = window_case(reference_case)
    assert _check_method(case) == []
    case.history_interval_minutes = 300
    errors = method_errors(case)
    assert len(errors) == case.max_dom and all("300 min" in e for e in errors)
    # The same checks in French
    from owstudio.core import i18n

    with i18n.using("fr"):
        assert all("Domaine" in i.message and "300 min" in i.message for i in _check_method(case))


def test_history_interval_parts_add_up_as_in_wrf(reference_case: Case) -> None:
    case = window_case(reference_case)
    # WRF uses history_interval only when history_interval_m is 0, and adds the parts
    case.namelist_input = {"time_control": {"history_interval_h": [1, 1]}}
    assert timesteps.history_seconds(case) == [7200, 7200]
    case.namelist_input = {"time_control": {"history_interval_m": [300, 60]}}
    assert timesteps.history_seconds(case) == [18000, 3600]
    errors = method_errors(case)
    assert len(errors) == 1 and "Domain 1" in errors[0]


def test_short_first_window_must_fit_the_history_interval(reference_case: Case) -> None:
    case = window_case(reference_case, hours=83)
    case.history_interval_minutes = 120
    # 83 h = 11 + 72: the first window's 11 h do not fit a 2 h history interval
    assert len([e for e in method_errors(case) if "history" in e]) == case.max_dom


def test_one_file_per_time_and_no_restart_are_required(reference_case: Case) -> None:
    case = window_case(reference_case)
    case.namelist_input = {"time_control": {"frames_per_outfile": [24, 24]}}
    assert any("frames_per_outfile" in e for e in method_errors(case))
    case.namelist_input = {"time_control": {"restart_interval": 1440}}
    assert any("restart_interval" in e for e in method_errors(case))


def test_windows_off_data_times_start_at_the_data_time_before(reference_case: Case) -> None:
    """A spin-up of 9 h with data every 6 h: accepted, the window starts at the data time
    before (12 h of spin-up); only a chained window must itself start on a data time."""
    from owstudio.core.method import plan as method

    case = window_case(reference_case)
    case.period.interval_seconds = 21600
    case.spin_up_hours = 9
    assert not any("boundary data" in e for e in method_errors(case))
    for window in method.plan(case).windows:
        assert window.spin_up.total_seconds() >= 9 * 3600
        assert window.simulation_start.hour % 6 == 0 and window.simulation_start.minute == 0
    case.windows = Windows(useful_hours=27, grouping="window", restart=True)
    assert any("boundary data" in e for e in method_errors(case))
