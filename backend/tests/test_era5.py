from datetime import datetime
from pathlib import Path

import pytest

from owstudio.core.case.checks import check_case
from owstudio.core.case.model import Case, Period
from owstudio.core.data import era5

REFERENCE = Path(__file__).parent / "fixtures" / "horns-rev" / "case.yaml"


@pytest.fixture
def case() -> Case:
    case = Case.from_yaml(REFERENCE)
    case.input_source = "era5"
    return case


def test_area_covers_the_outer_domain_with_a_margin(case: Case) -> None:
    north, west, south, east = era5.area_for(case.grid)
    # Outer domain: 51.31-59.51 N (the Lambert top edge bulges north of its corners), -0.05-15.65 E
    assert (north, west, south, east) == (61.75, -2.25, 49.25, 17.75)
    assert all(value % 0.25 == 0 for value in (north, west, south, east))


def test_two_requests_per_day_with_the_needed_hours(case: Case) -> None:
    requests = era5.requests_for(case.period, case.grid)
    assert [r.dataset for r in requests] == [
        "reanalysis-era5-pressure-levels",
        "reanalysis-era5-single-levels",
        "reanalysis-era5-pressure-levels",
        "reanalysis-era5-single-levels",
    ]
    first_day, second_day = requests[0].request, requests[2].request
    assert first_day["time"] == ["00:00", "06:00", "12:00", "18:00"]
    assert second_day["day"] == ["02"] and second_day["time"] == ["00:00"]
    assert len(first_day["pressure_level"]) == 37
    assert "sea_surface_temperature" in requests[1].request["variable"]
    assert requests[0].name.startswith("era5-pl-20251001-") and requests[0].name.endswith(".grib")


def test_request_names_change_with_the_content(case: Case) -> None:
    before = era5.requests_for(case.period, case.grid)[0].name
    case.grid.projection.ref_lon += 5
    assert era5.requests_for(case.period, case.grid)[0].name != before


def test_availability() -> None:
    now = datetime(2026, 10, 13)
    assert (
        era5.availability_error(Period(start=datetime(2025, 10, 1), end=datetime(2025, 10, 2)), now)
        is None
    )
    assert "1940" in era5.availability_error(
        Period(start=datetime(1930, 1, 1), end=datetime(1930, 1, 2)), now
    )
    recent = Period(start=datetime(2026, 10, 10), end=datetime(2026, 10, 11))
    assert "5 days" in era5.availability_error(recent, now)


def test_checks_report_input_data_problems(case: Case) -> None:
    assert check_case(case) == []
    case.input_source = "gfs"
    case.period = Period(start=datetime(2019, 6, 1), end=datetime(2019, 6, 2))
    issues = check_case(case)
    assert issues[0].severity == "error" and "GFS from" in issues[0].message
    case.input_source = "era5"
    assert check_case(case) == []


def test_api_key_is_saved_where_cdsapi_reads_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(era5, "CDSAPI_RC", tmp_path / ".cdsapirc")
    assert not era5.has_api_key()
    era5.save_api_key("abcd-1234")
    assert (tmp_path / ".cdsapirc").read_text() == f"url: {era5.CDS_URL}\nkey: abcd-1234\n"
    assert era5.has_api_key()
    with pytest.raises(ValueError):
        era5.save_api_key("a\nb")
