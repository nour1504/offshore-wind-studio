"""Retained-time readers agree across independently initialized, overlapping WRF windows."""

import hashlib
import json
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from helpers import write_manifest
from test_energy import SITES, farms_case
from test_extract import wrfout
from test_tslist import write_location

from owstudio.api.runs import Runs, RunStatus
from owstudio.core.case.model import Windows
from owstudio.core.case.workspace import Workspace
from owstudio.core.energy.summary import energy_series, run_energy
from owstudio.core.engine.windows import plan_windows
from owstudio.core.extract.grid import locate
from owstudio.core.extract.history import HistoryFiles
from owstudio.core.extract.points import TimeSeriesFiles, point_series
from owstudio.core.postproc.results import Results
from owstudio.core.postproc.tslist_reader import TimeSeriesSet
from owstudio.core.postproc.windowed import output_sources
from owstudio.core.storage import Storage


def test_every_reader_excludes_prefixes_and_counts_boundary_once(tmp_path: Path) -> None:
    case = farms_case({"A": SITES["A"]})
    case.windows = Windows()
    case.period.end = case.period.start + timedelta(hours=83)
    raw = []
    for stage in ("main", "control"):
        parent = tmp_path / "outputs" / stage
        write_manifest(case, parent)
        for window in plan_windows(case):
            folder = parent / "windows" / window.id
            folder.mkdir(parents=True)
            count = (
                int((window.simulation_end - window.simulation_start).total_seconds() / 3600) + 1
            )
            times = [
                (window.simulation_start + timedelta(hours=k)).strftime("%Y-%m-%d_%H:%M:%S")
                for k in range(count)
            ]
            power = np.zeros((count, 6, 6))
            if stage == "main":
                power[:, 1, 1] = 0.5e6
                power[0, 1, 1] = 0  # raw cold-start state; never a retained useful output
            ds = wrfout(times, {"POWER": (("Time", "south_north", "west_east"), power)})
            path = folder / "wrfout_d02_2025-10-01_00-00-00"
            ds.to_netcdf(path)
            raw.append(path)
            ts = folder / "tslist"
            ts.mkdir()
            write_location(ts, "C0001", 0, np.arange(count, dtype=float))
            for file in ts.iterdir():
                file.write_text(file.read_text().replace("2025-10-01_00:00:00", times[0]))
                raw.append(file)
    case.to_yaml(tmp_path / "outputs" / "main" / "case.yaml")
    checksums = {p: hashlib.sha256(p.read_bytes()).digest() for p in raw}
    expected = pd.date_range(case.period.start, case.period.end, freq="h", tz="UTC")
    files = HistoryFiles(tmp_path / "outputs" / "main", 2)
    assert files.times.equals(expected)
    assert files.window("U10").shape[0] == 84
    wind = point_series(files, locate(*files.coordinates, 54.1, 7.1), "wind_speed", 10)
    assert wind.values.index.equals(expected)
    assert len(wind.values) == 84
    # Time series keep ]D, F]: never D itself, the end of the first spin-up
    _, extracted = TimeSeriesFiles(tmp_path / "outputs" / "main" / "tslist").series(
        "C0001", 2, "wind_speed", 10
    )
    assert extracted.values.index.equals(expected[1:])
    legacy = TimeSeriesSet(tmp_path / "outputs" / "main" / "tslist").series("C0001", 2, 100)
    assert legacy.index.tz_localize("UTC").equals(expected[1:])
    result = run_energy(tmp_path, case, "wrf")
    assert result["total"]["energy_mwh"] == pytest.approx(41.5)
    assert result["total"]["covered_h"] == pytest.approx(83)
    series = energy_series(tmp_path, case)
    assert pd.DatetimeIndex(series["time"]).equals(expected)
    assert series["A"].iloc[0] == pytest.approx(0.5)
    graphical = Results(tmp_path)
    assert graphical.times(2).equals(expected)
    assert graphical.summary()["energy_mwh"] == pytest.approx(41.5)
    assert graphical.field("wind10", 2, 72)[1, 1] == pytest.approx(4)
    assert graphical.field("wake", 2, 72)[1, 1] == pytest.approx(0)
    assert all(hashlib.sha256(p.read_bytes()).digest() == digest for p, digest in checksums.items())


def test_manifest_cannot_read_files_outside_run(tmp_path: Path) -> None:
    (tmp_path / "windows.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "mode": "independent_windows",
                "windows": [
                    {
                        "output_dir": "../private",
                        "useful_start": "2025-01-01",
                        "useful_end": "2025-01-02",
                        "include_end": True,
                    }
                ],
            }
        )
    )
    with pytest.raises(ValueError, match="outside"):
        output_sources(tmp_path)


def test_runs_left_running_are_closed_at_the_next_start(tmp_path: Path) -> None:
    case = farms_case({"A": SITES["A"]})
    case_id = Workspace(tmp_path).create(case)
    storage = Storage(tmp_path)
    runs = Runs(lambda: storage)
    imported, launched = storage.create_run(case_id), storage.create_run(case_id)
    runs.save(imported, RunStatus(run_id=imported.id, state="running", step="import"))
    runs.save(launched, RunStatus(run_id=launched.id, state="queued"))
    assert runs.close_interrupted() == [f"{case_id}/{imported.id}", f"{case_id}/{launched.id}"]
    first, second = runs.status(case_id, imported.id), runs.status(case_id, launched.id)
    assert first.state == second.state == "failed"
    assert "import" in (first.error or "") and "no longer" in (second.error or "")
    assert not runs.is_running(case_id)
    runs.writing(case_id, imported.id, True)
    assert runs.is_running(case_id) and runs.is_running(case_id, imported.id)
    assert not runs.is_running(case_id, launched.id)


def test_graphical_results_join_multiple_ordinary_history_files(tmp_path: Path) -> None:
    case = farms_case({"A": SITES["A"]})
    folder = tmp_path / "outputs" / "main"
    folder.mkdir(parents=True)
    case.to_yaml(folder / "case.yaml")
    for start, wind in ((0, [4.0, 4.0]), (1, [77.0, 9.0])):
        times = [
            (case.period.start + timedelta(hours=h)).strftime("%Y-%m-%d_%H:%M:%S")
            for h in (start, start + 1)
        ]
        power = np.zeros((2, 6, 6))
        power[:, 1, 1] = 0.5e6
        if start == 0:
            power[0] = 0
        ds = wrfout(
            times,
            {
                "POWER": (("Time", "south_north", "west_east"), power),
                "U10": (
                    ("Time", "south_north", "west_east"),
                    np.broadcast_to(np.array(wind)[:, None, None], (2, 6, 6)),
                ),
            },
        )
        ds.to_netcdf(folder / f"wrfout_d02_2025-10-01_0{start}-00-00")
    result = Results(tmp_path)
    assert not result.windowed and result.streaming
    assert len(result.times(2)) == 3  # repeated 01:00 from the earlier file once
    assert result.field("wind10", 2, None)[1, 1] == pytest.approx(6.5)
    assert result.field("wind10", 2, 2)[1, 1] == pytest.approx(9)
    assert result.summary()["energy_mwh"] == pytest.approx(0.5)
