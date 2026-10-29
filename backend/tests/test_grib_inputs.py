"""GRIB inventories from message headers, Vtable matching as ungrib does it, and the checks of
own input files before a run: fields, levels, times, SST period, area."""

import os
import re
from datetime import datetime, timedelta
from pathlib import Path

import gribmaker
import pytest
from gribmaker import LatLon, grib1, grib2
from helpers import make_client

from owstudio.core.case.model import Case, GribInput, SeaSurface
from owstudio.core.data import examine, grib, vtables
from owstudio.core.data.examine import Box, Context

DAY = datetime(2025, 10, 1)
TIMES = [DAY + timedelta(hours=6 * k) for k in range(5)]
# Around the Horns Rev outer domain
DOMAIN = Box(51.0, 60.0, 0.0, 15.6)


def context(**changes: object) -> Context:
    values: dict[str, object] = {
        "start": DAY,
        "end": DAY + timedelta(days=1),
        "interval_s": 21600,
        "domain": DOMAIN,
    }
    values.update(changes)
    return Context(**values)  # type: ignore[arg-type]


def own(folder: Path, vtable: str = "Vtable.ECMWF", pattern: str = "*") -> GribInput:
    return GribInput(folder=str(folder), pattern=pattern, vtable=vtable)


def severities(report: examine.Examination, level: str) -> list[str]:
    return [f.message for f in report.findings if f.severity == level]


# --------------------------------------------------------------- inventory


def test_inventory_of_both_editions(tmp_path: Path) -> None:
    path = tmp_path / "mixed.grib"
    path.write_bytes(
        grib1(DAY, 130, 100, 850)
        + grib1(DAY, 139, 112, (0, 7))
        + grib2(DAY, 0, 2, 2, 103, 10, forecast_hours=6, centre=7)
        + grib2(DAY, 10, 3, 0, 1, grid=LatLon(lat1=65, lon1=355, lat2=45, lon2=20))
    )
    found = grib.inventory(path)
    assert not found.problems and not found.truncated
    pressure, soil, wind, sst = found.records
    assert (pressure.edition, pressure.parameter, pressure.level_type, pressure.level1) == (
        1,
        130,
        100,
        850.0,
    )
    assert (soil.level1, soil.level2) == (0.0, 7.0)
    assert (wind.discipline, wind.category, wind.parameter, wind.level1) == (0, 2, 2, 10.0)
    assert wind.valid == DAY + timedelta(hours=6) and wind.centre == 7
    # Signed coordinates and grids crossing the Greenwich meridian
    assert pressure.grid.bounds() == (45.0, 65.0, -5.0, 20.0)
    assert sst.grid.bounds() == (45.0, 65.0, 355.0, 380.0)
    assert pressure.grid.describe() == "lat-lon 101×81, 0.25°"
    assert found.centres() == ["ECMWF", "NCEP"]


def test_statistically_processed_fields_are_valid_at_the_end_of_their_interval(
    tmp_path: Path,
) -> None:
    # rd_grib2.F: product template 4.8 gives the end of the overall time interval
    path = tmp_path / "mean.grib2"
    end = DAY + timedelta(hours=24)
    path.write_bytes(grib2(DAY, 0, 0, 0, 1, template=8, forecast_hours=24, interval_end=end))
    assert grib.inventory(path).records[0].valid == end


def test_damaged_files_are_reported_not_fatal(tmp_path: Path) -> None:
    message = grib1(DAY, 130, 100, 850)
    truncated = tmp_path / "cut.grib"
    truncated.write_bytes(message * 3 + message[:40])
    found = grib.inventory(truncated)
    assert len(found.records) == 3 and found.truncated and "truncated" in found.problems[0]
    padded = tmp_path / "padded.grib"
    padded.write_bytes(message + b"\0" * 7 + message)
    assert len(grib.inventory(padded).records) == 2
    zero = tmp_path / "zero.grib"
    zero.write_bytes(b"GRIB\0\0\0\x01" + b"\0" * 56)
    assert "Invalid message length" in grib.inventory(zero).problems[0]
    text = tmp_path / "notes.grib"
    text.write_text("not a GRIB file at all", encoding="utf-8")
    assert grib.inventory(text).problems == ["Not a GRIB file: no GRIB message found"]
    wrong_end = tmp_path / "wrong.grib"
    wrong_end.write_bytes(message[:-4] + b"XXXX")
    assert "does not end where its length says" in grib.inventory(wrong_end).problems[0]


def test_inventories_are_cached_until_the_file_changes(tmp_path: Path) -> None:
    path = tmp_path / "a.grib"
    path.write_bytes(grib1(DAY, 130, 100, 850))
    assert grib.cached_inventory(path, compute=False) is None
    first = grib.cached_inventory(path)
    assert first is not None and grib.cached_inventory(path) is first
    path.write_bytes(grib1(DAY, 130, 100, 850) * 2)
    os.utime(path, ns=(10**18, 10**18))
    changed = grib.cached_inventory(path)
    assert changed is not None and len(changed.records) == 2


@pytest.mark.skipif(
    not (os.environ.get("OWS_GFS_SAMPLE") and os.environ.get("OWS_G2PRINT")),
    reason="real GFS sample not available (set OWS_GFS_SAMPLE and OWS_G2PRINT)",
)
def test_real_gfs_file_matches_g2print() -> None:
    """Validation on a real NCEP GFS 0.25° file against WPS's g2print listing of it."""
    found = grib.inventory(Path(os.environ["OWS_GFS_SAMPLE"]))
    expected = []
    for line in Path(os.environ["OWS_G2PRINT"]).read_text().splitlines():
        row = re.match(r"\s+\d+\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(-?\d+)\s+(-?\d+)\s", line)
        if row:
            expected.append(tuple(int(v) for v in row.groups()))
    assert found.records and len(found.records) <= len(expected)
    for record, (disc, cat, par, ltype, lvl1, lvl2) in zip(found.records, expected, strict=False):
        assert (record.discipline, record.category, record.parameter, record.level_type) == (
            disc,
            cat,
            par,
            ltype,
        )
        assert (int(record.level1 or 0), int(record.level2 or 0)) == (lvl1, lvl2)
    assert found.records[0].grid.bounds() == (-90.0, 90.0, 0.0, 359.75)


# ------------------------------------------------------------------ Vtables


def test_vtable_rows_are_read_as_ungrib_reads_them() -> None:
    rows = {(e.name, e.grib1_level_type): e for e in vtables.entries(vtables.read("Vtable.ECMWF"))}
    geopotential = rows[("GEOPT", 100)]
    assert geopotential.level1 == vtables.EVERY_LEVEL and not geopotential.output
    soil = rows[("ST000007", 112)]
    assert (soil.grib1_param, soil.level1, soil.level2) == (139, 0, 7) and soil.output
    assert rows[("UU", 1)].grib2 == (0, 2, 2, 103) and rows[("UU", 1)].grib2_template == 0
    assert rows[("RH", 1)].grib1_param == vtables.BLANK  # derived by ungrib, not read


def test_grib1_level_type_unknown_to_ungrib_stops_it(tmp_path: Path) -> None:
    table = vtables.entries(
        "GRIB1| Level| From |  To  | metgrid  | metgrid | metgrid  |\n"
        "Param| Type |Level1|Level2| Name     | Units   | Desc     |\n"
        "-----+------+------+------+----------+---------+----------+\n"
        "  11 |  103 |   2  |      | TT       | K       | T at 2 m |\n"
        "-----+------+------+------+----------+---------+----------+\n"
    )
    path = tmp_path / "t2.grib"
    path.write_bytes(grib1(DAY, 11, 103, 2, centre=7, table=2))
    collected = examine.collect(
        [type("F", (), {"format": "grib1", "path": path, "size": 1, "name": "t2.grib"})()]  # type: ignore[list-item]
    )
    matched = examine.match(collected, table)
    assert matched.stops and "not handled by ungrib" in matched.stops[0]


# ------------------------------------------------------------- examination


@pytest.fixture
def era5(tmp_path: Path) -> Path:
    return gribmaker.era5_folder(tmp_path / "era5", TIMES)


def test_complete_era5_folder_passes(era5: Path) -> None:
    report = examine.examine(own(era5), "atmosphere", context(), with_suggestions=True)
    assert report.findings == []
    assert report.messages == 420 and report.editions == [1] and report.centres == ["ECMWF"]
    assert (report.first, report.last, report.times, report.step_hours) == (
        TIMES[0],
        TIMES[-1],
        5,
        6.0,
    )
    assert report.pressure_levels_hpa[0] == 1000 and len(report.pressure_levels_hpa) == 13
    assert len(report.soil_fields) == 8 and report.unused_messages == 0
    assert report.suggestions[0].vtable == "Vtable.ECMWF" and report.suggestions[0].required_ok


def test_wrong_vtable_points_to_the_right_one(era5: Path) -> None:
    report = examine.examine(own(era5, "Vtable.GFS"), "atmosphere", context())
    assert any(
        "no record of the files matches the Vtable Vtable.GFS" in e and "Vtable.ECMWF" in e
        for e in report.errors
    )


def test_first_and_last_times_are_required_and_others_interpolated(tmp_path: Path) -> None:
    folder = gribmaker.era5_folder(tmp_path / "gap", [t for t in TIMES if t.hour != 12])
    report = examine.examine(own(folder), "atmosphere", context())
    assert not report.errors
    assert any(
        "1 time(s) missing (2025-10-01 12:00)" in w and "interpolates" in w
        for w in severities(report, "warning")
    )
    longer = examine.examine(own(folder), "atmosphere", context(end=DAY + timedelta(hours=30)))
    assert any("no data at 2025-10-02 06:00" in e and "Data not found" in e for e in longer.errors)


def test_fields_missing_at_some_times_stop_metgrid(tmp_path: Path, era5: Path) -> None:
    (era5 / "era5-pl-20251002.grib").unlink()
    report = examine.examine(own(era5), "atmosphere", context())
    assert any("temperature missing at 2025-10-02 00:00" in e for e in report.errors)


def test_missing_required_fields(tmp_path: Path) -> None:
    folder = tmp_path / "pressure-only"
    folder.mkdir()
    (folder / "pl.grib").write_bytes(
        b"".join(
            grib1(t, p, 100, level)
            for t in TIMES
            for p in (130, 131, 132)
            for level in (1000, 500, 100, 10)
        )
    )
    report = examine.examine(own(folder), "atmosphere", context())
    errors = " ".join(report.errors)
    assert "no humidity" in errors and "no surface or sea-level pressure" in errors
    assert "no soil temperature" in errors and "Noah" in errors
    warnings = " ".join(severities(report, "warning"))
    assert "only 4 pressure levels" in warnings and "no skin temperature" in warnings
    # Without a land surface model needing soil data, soil fields are not required
    slab = examine.examine(own(folder), "atmosphere", context(sf_surface_physics=1))
    assert not any("soil temperature" in e for e in slab.errors)


def test_model_top_above_the_data(tmp_path: Path) -> None:
    folder = tmp_path / "low-top"
    folder.mkdir()
    (folder / "pl.grib").write_bytes(
        b"".join(
            grib1(t, p, 100, level)
            for t in TIMES
            for p in (130, 131, 132, 157)
            for level in (1000, 850, 500, 200, 100)
        )
    )
    report = examine.examine(own(folder), "atmosphere", context(p_top_pa=5000.0))
    assert any(
        "highest pressure level is 100 hPa" in e and "p_top_requested" in e for e in report.errors
    )


def test_domain_must_lie_inside_the_data(tmp_path: Path) -> None:
    small = gribmaker.era5_folder(
        tmp_path / "small", TIMES, LatLon(lat1=58, lon1=4, lat2=53, lon2=11)
    )
    report = examine.examine(own(small), "atmosphere", context())
    assert any(
        "extends beyond the data" in e and "latitudes" in e and "longitudes" in e
        for e in report.errors
    )
    tight = gribmaker.era5_folder(
        tmp_path / "tight", TIMES, LatLon(lat1=60.25, lon1=-0.25, lat2=50.75, lon2=15.75)
    )
    report = examine.examine(own(tight), "atmosphere", context())
    assert not report.errors and any("two grid steps" in w for w in severities(report, "warning"))


def test_quick_checks_leave_large_unexamined_folders_for_later(era5: Path) -> None:
    report = examine.examine(own(era5), "atmosphere", context(), budget_bytes=0)
    assert [f.severity for f in report.findings] == [
        "info"
    ] and "not examined yet" in report.findings[0].message
    # Once examined, the inventories are cached and quick checks see everything
    examine.examine(own(era5), "atmosphere", context())
    assert examine.examine(own(era5), "atmosphere", context(), budget_bytes=0).findings == []


# --------------------------------------------------------------------- SST


def test_daily_sst_widens_the_sst_pass(tmp_path: Path) -> None:
    folder = gribmaker.sst_folder(tmp_path / "sst", [datetime(2025, 9, 30), datetime(2025, 10, 2)])
    report = examine.examine(own(folder, "Vtable.SST"), "sst", context())
    assert not report.errors and report.window == (datetime(2025, 9, 30), datetime(2025, 10, 2))
    assert any("interpolates it linearly" in f.message for f in report.findings)


def test_sst_at_noon_starts_the_day_before(tmp_path: Path) -> None:
    noon = [datetime(2025, 9, 30, 12), datetime(2025, 10, 1, 12), datetime(2025, 10, 2, 12)]
    folder = gribmaker.sst_folder(tmp_path / "sst", noon)
    report = examine.examine(own(folder, "Vtable.SST"), "sst", context())
    assert report.window == (datetime(2025, 9, 30, 12), datetime(2025, 10, 2, 12))


def test_sst_must_reach_both_ends(tmp_path: Path) -> None:
    folder = gribmaker.sst_folder(tmp_path / "sst", [datetime(2025, 10, 1)])
    report = examine.examine(own(folder, "Vtable.SST"), "sst", context())
    assert any("must have a time at or before the start" in e for e in report.errors)
    wrong = examine.examine(own(folder, "Vtable.ECMWF"), "sst", context())
    assert wrong.errors


def test_case_level_examination_and_api(tmp_path: Path, reference_case: Case, era5: Path) -> None:
    sst = gribmaker.sst_folder(tmp_path / "sst", [datetime(2025, 9, 30), datetime(2025, 10, 2)])
    case = reference_case.model_copy(deep=True)
    # The files cover the period of the fixture; the useful period starts after the spin-up
    case.period.start += timedelta(hours=case.spin_up_hours)
    case.input_source = "grib"
    case.grib = own(era5)
    case.sea_surface = SeaSurface(source="grib", grib=own(sst, "Vtable.SST"))
    client = make_client(tmp_path)
    body = case.model_dump(mode="json")
    result = client.post("/api/data/examine", json={"case": body, "role": "atmosphere"}).json()
    assert result["errors"] == [] and result["suggestions"][0]["vtable"] == "Vtable.ECMWF"
    assert result["first"] == "2025-10-01T00:00:00" and result["fields"]
    sst_result = client.post("/api/data/examine", json={"case": body, "role": "sst"}).json()
    assert sst_result["window"] == ["2025-09-30T00:00:00", "2025-10-02T00:00:00"]
    gfs_case = reference_case.model_copy(deep=True)
    assert (
        client.post(
            "/api/data/examine", json={"case": gfs_case.model_dump(mode="json")}
        ).status_code
        == 422
    )
