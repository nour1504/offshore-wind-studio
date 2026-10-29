"""Pure API/date tests: synthetic projects only, no calculation or external data."""

import copy
import io
from datetime import timedelta
from pathlib import Path
from typing import Any

import f90nml
import pytest
from helpers import make_client

from owstudio.core.case.model import Case, Windows
from owstudio.core.engine.windows import child_case, manifest, plan_windows


@pytest.mark.parametrize("spin", [6, 12, 24])
def test_namelist_preview_is_first_real_window(
    tmp_path: Path, reference: dict[str, Any], spin: int
) -> None:
    reference["period"] = {
        "start": "2025-10-01T00:00:00",
        "end": "2025-10-08T00:00:00",
        "interval_seconds": 3600,
    }
    reference["spin_up_hours"] = spin
    reference["windows"] = {"useful_hours": 72}
    original = copy.deepcopy(reference)
    client = make_client(tmp_path)
    plan = manifest(Case.model_validate(reference))
    assert len(plan["windows"]) == 3
    assert plan["windows"][2]["useful_end"] == "2025-10-08T00:00:00Z"
    # The namelists shown are those exported: namelist.input of the first computed window (the
    # latest), namelist.wps of the first WPS pass (the year, spin-up included)
    first = plan["windows"][2]
    texts = client.post("/api/namelists", json=reference).json()
    wps = f90nml.read(io.StringIO(texts["namelist.wps"]))["share"]
    wrf = f90nml.read(io.StringIO(texts["namelist.input"]))["time_control"]
    forcing = plan["windows"][0]["simulation_start"].replace("T", "_").removesuffix("Z")
    assert wps["start_date"] == [forcing] * 2
    assert wps["end_date"] == ["2025-10-08_00:00:00"] * 2
    assert wrf["start_day"] == [int(first["simulation_start"][8:10])] * 2
    assert wrf["run_hours"] == 72 + spin
    assert wrf["restart"] is False
    assert wrf["interval_seconds"] == wps["interval_seconds"] == 3600
    structured = client.post("/api/namelists/structured", json=reference).json()
    assert structured["namelist.wps"]["generated"]["share"]["start_date"] == wps["start_date"]
    assert structured["namelist.input"]["final"]["time_control"]["start_hour"] == wrf["start_hour"]
    assert reference == original


def test_child_dates_clear_only_replaced_index_metadata(reference_case: Case) -> None:
    case = reference_case
    case.windows = Windows(useful_hours=72)
    case.namelist_input = {
        "TIME_CONTROL": {
            "START_YEAR": [1999],
            "INTERVAL_SECONDS": 123,
            "_START_INDEX": {
                "START_YEAR": [2],
                "END_HOUR": [2],
                "RUN_HOURS": [3],
                "RESTART": [2],
                "INTERVAL_SECONDS": [2],
                "HISTORY_INTERVAL": [2],
            },
            "_COMPLEX": {"START_YEAR": True, "HISTORY_INTERVAL": False},
            "HISTORY_INTERVAL": [30],
        }
    }
    case.namelist_wps = {
        "SHARE": {
            "START_DATE": ["1999-01-01_00:00:00"],
            "INTERVAL_SECONDS": 123,
            "_START_INDEX": {
                "START_DATE": [2],
                "END_DATE": [2],
                "INTERVAL_SECONDS": [2],
                "ACTIVE_GRID": [2],
            },
            "ACTIVE_GRID": [True],
        }
    }
    child = child_case(case, plan_windows(case)[0])
    control = child.namelist_input["time_control"]
    assert control["_start_index"] == {"history_interval": [2]}
    assert control["_complex"] == {"history_interval": False}
    assert child.namelist_wps["share"]["_start_index"] == {"active_grid": [2]}
    assert control["interval_seconds"] == case.period.interval_seconds
    assert case.namelist_input["TIME_CONTROL"]["START_YEAR"] == [1999]


def test_save_period_resets_stale_import_dates_and_preserves_other_options(
    tmp_path: Path, reference: dict[str, Any]
) -> None:
    reference["namelist_input"] = {
        "TIME_CONTROL": {
            "START_YEAR": [1999, 1999],
            "END_YEAR": [1999, 1999],
            "RUN_HOURS": 999,
            "INTERVAL_SECONDS": 21600,
            "HISTORY_INTERVAL": [30],
            "_START_INDEX": {"START_YEAR": [2], "RUN_HOURS": [3], "HISTORY_INTERVAL": [2]},
        },
        "physics": {"_start_index": {"mp_physics": [2]}, "mp_physics": [8]},
    }
    reference["namelist_wps"] = {
        "SHARE": {
            "START_DATE": ["1999-01-01_00:00:00"] * 2,
            "END_DATE": ["1999-01-02_00:00:00"] * 2,
            "INTERVAL_SECONDS": 21600,
            "_START_INDEX": {"START_DATE": [2], "ACTIVE_GRID": [2]},
            "ACTIVE_GRID": [True],
        }
    }
    client = make_client(tmp_path)
    case_id = client.post("/api/cases", json=reference).json()["id"]
    reference["period"] = {
        "start": "2026-01-10T06:00:00",
        "end": "2026-01-11T06:00:00",
        "interval_seconds": 3600,
    }
    response = client.put(f"/api/cases/{case_id}", json=reference)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["namelist_input"]["TIME_CONTROL"] == {
        "HISTORY_INTERVAL": [30],
        "_START_INDEX": {"HISTORY_INTERVAL": [2]},
    }
    assert saved["namelist_input"]["physics"] == reference["namelist_input"]["physics"]
    assert saved["namelist_wps"]["SHARE"] == {
        "ACTIVE_GRID": [True],
        "_START_INDEX": {"ACTIVE_GRID": [2]},
    }
    texts = client.post("/api/namelists", json=saved).json()
    wrf = f90nml.read(io.StringIO(texts["namelist.input"]))["time_control"]
    wps = f90nml.read(io.StringIO(texts["namelist.wps"]))["share"]
    assert wrf["start_year"] == [2026, 2026]
    assert wrf["start_day"] == [9, 9]
    assert wrf["start_hour"] == [18, 18]
    # The 24 useful hours after the 12 h of spin-up
    assert wrf["run_hours"] == 36
    assert wrf["interval_seconds"] == wps["interval_seconds"] == 3600
    assert wps["start_date"] == ["2026-01-09_18:00:00"] * 2


def test_short_standard_study_has_one_window(reference_case: Case) -> None:
    reference_case.spin_up_hours = 6
    reference_case.period.end = reference_case.period.start + timedelta(hours=48)
    windows = plan_windows(reference_case)
    assert len(windows) == 1
    assert windows[0].simulation_start == windows[0].useful_start - timedelta(hours=6)
    assert windows[0].include_start


def test_a_year_previews_the_wps_pass_and_the_latest_window(
    tmp_path: Path, reference: dict[str, Any]
) -> None:
    reference["period"] = {
        "start": "2016-01-01T00:00:00",
        "end": "2017-01-01T00:00:00",
        "interval_seconds": 3600,
    }
    reference["spin_up_hours"] = 12
    reference["windows"] = {"useful_hours": 72, "grouping": "month"}
    texts = make_client(tmp_path).post("/api/namelists", json=reference).json()
    wps = f90nml.read(io.StringIO(texts["namelist.wps"]))["share"]
    wrf = f90nml.read(io.StringIO(texts["namelist.input"]))["time_control"]
    assert wps["start_date"] == ["2015-12-31_12:00:00"] * 2
    assert wps["end_date"] == ["2017-01-01_00:00:00"] * 2
    assert (wrf["start_month"], wrf["start_day"], wrf["start_hour"]) == (
        [12] * 2,
        [28] * 2,
        [12] * 2,
    )
    assert wrf["run_hours"] == 84
