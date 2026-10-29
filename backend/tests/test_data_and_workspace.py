from datetime import datetime
from pathlib import Path

import pytest

from owstudio.core.case.model import Case, Period
from owstudio.core.case.workspace import CaseNotFound, Workspace
from owstudio.core.data import gfs

REFERENCE = Path(__file__).parent / "fixtures" / "horns-rev" / "case.yaml"


def test_gfs_files_cover_the_period_every_six_hours() -> None:
    files = gfs.files_for(Period(start=datetime(2025, 10, 1), end=datetime(2025, 10, 2)))
    assert [f.name for f in files] == [
        "gfs.2025100100.f000.grib2",
        "gfs.2025100106.f000.grib2",
        "gfs.2025100112.f000.grib2",
        "gfs.2025100118.f000.grib2",
        "gfs.2025100200.f000.grib2",
    ]
    assert files[0].url == (
        "https://noaa-gfs-bdp-pds.s3.amazonaws.com/gfs.20251001/00/atmos/gfs.t00z.pgrb2.0p25.f000"
    )


def test_gfs_paths_before_v16_have_no_atmos_directory() -> None:
    files = gfs.files_for(Period(start=datetime(2021, 3, 22, 6), end=datetime(2021, 3, 22, 12)))
    assert "/06/gfs.t06z" in files[0].url
    assert "/12/atmos/gfs.t12z" in files[1].url


def test_gfs_rejects_periods_before_the_archive() -> None:
    with pytest.raises(ValueError, match="from 2021-01-01 only"):
        gfs.files_for(Period(start=datetime(2020, 6, 1), end=datetime(2020, 6, 2)))


def test_gfs_rejects_start_between_cycles() -> None:
    with pytest.raises(ValueError, match="00, 06, 12 or 18"):
        gfs.analysis_times(Period(start=datetime(2025, 10, 1, 3), end=datetime(2025, 10, 2)))


def test_workspace_create_list_load_save(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    case = Case.from_yaml(REFERENCE)
    first = workspace.create(case)
    second = workspace.create(case)
    assert (first, second) == ("horns-rev-reference", "horns-rev-reference-2")

    summaries = workspace.list()
    assert [s.id for s in summaries] == [first, second]
    assert summaries[0].turbines == 80 and summaries[0].domains == 2

    case.description = "edited"
    workspace.save(first, case)
    assert workspace.load(first).description == "edited"


def test_workspace_rejects_unknown_or_unsafe_ids(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    for case_id in ("missing", "../outside", "a/b"):
        with pytest.raises(CaseNotFound):
            workspace.load(case_id)
