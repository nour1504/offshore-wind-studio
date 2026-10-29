"""Regression checks for imports, storage cleanup and real export encoders (tiny fixtures)."""

import threading
import time
from pathlib import Path
from typing import Any

import imageio_ffmpeg
import pytest
from helpers import make_client, write_manifest
from test_energy import SITES, farms_case, write_run
from test_extract import wrfout

from owstudio.core import media
from owstudio.core.case.model import Case, Windows
from owstudio.core.energy.production import EnergyError
from owstudio.core.energy.summary import energy_series
from owstudio.core.engine.windows import plan_windows


def finished(client: Any, job_id: str) -> dict[str, Any]:
    for _ in range(200):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["state"] != "running":
            return job
        time.sleep(0.02)
    raise AssertionError("Export job did not finish")


def test_turbine_time_series_keeps_reference_and_metadata(tmp_path: Path) -> None:
    case = farms_case({"A": SITES["A"]})
    write_run(tmp_path, case, {"A": 0.5}, control=True)
    label = case.farms[0].turbines[0].id
    frame = energy_series(tmp_path, case, turbine=label)
    assert frame[label].iloc[-1] == pytest.approx(0.5)
    assert f"{label}_without_wakes" in frame and frame.attrs["method"] == "wrf"
    with pytest.raises(EnergyError, match="Unknown"):
        energy_series(tmp_path, case, turbine="missing")


def test_import_preserves_independent_window_tree_and_retention(tmp_path: Path) -> None:
    from datetime import timedelta

    from owstudio.core.extract.history import HistoryFiles

    client = make_client(tmp_path)
    case = farms_case({"A": SITES["A"]})
    case.windows = Windows(useful_hours=2)
    case.spin_up_hours = 1
    case.period.end = case.period.start + timedelta(hours=3)
    case_id = client.post("/api/cases", json=case.model_dump(mode="json")).json()["id"]
    source = tmp_path / "source"
    write_manifest(case, source)
    case.to_yaml(source / "case.yaml")
    for window in plan_windows(case):
        folder = source / "windows" / window.id
        folder.mkdir(parents=True)
        count = int((window.simulation_end - window.simulation_start).total_seconds() / 3600) + 1
        times = [
            (window.simulation_start + timedelta(hours=h)).strftime("%Y-%m-%d_%H:%M:%S")
            for h in range(count)
        ]
        wrfout(times).to_netcdf(folder / "wrfout_d02_2025-10-01_00-00-00")
    url = f"/api/cases/{case_id}/results/import"
    body = {"folder": str(source), "mode": "link"}
    preview = client.post(url + "/preview", json=body)
    assert preview.status_code == 200 and preview.json()["files"] == 3
    imported = client.post(url, json=body).json()
    assert finished(client, imported["job_id"])["state"] == "succeeded"
    root = client.app.state.owstudio.storage.run(case_id, imported["run_id"]).outputs()
    assert len(HistoryFiles(root, 2).times) == 4
    assert len(list((root / "windows").rglob("wrfout_*"))) == 2
    old = (root / "windows.json").read_bytes()
    (source / "windows.json").write_text("changed by another process")
    assert (root / "windows.json").read_bytes() == old


def test_actual_mp4_encoding_is_incremental(tmp_path: Path, reference_case: Case) -> None:
    source = tmp_path / "outputs"
    source.mkdir()
    wrfout(["2025-10-01_00:00:00", "2025-10-01_01:00:00"]).to_netcdf(
        source / "wrfout_d01_2025-10-01_00-00-00"
    )
    path = tmp_path / "test.mp4"
    observed = []
    result = media.video(
        path,
        source,
        reference_case,
        1,
        "wind_speed",
        100,
        [0, 1],
        2,
        320,
        True,
        threading.Event(),
        observed.append,
    )
    assert result["frames"] == 2 and result["duration_s"] == 1
    assert observed == [0.5, 1.0] and path.stat().st_size > 500
    reader = imageio_ffmpeg.read_frames(str(path))
    metadata = next(reader)
    assert metadata["size"][0] == 320 and len(next(reader)) == 320 * metadata["size"][1] * 3
    reader.close()


def test_video_cancel_preserves_inputs(tmp_path: Path, reference_case: Case) -> None:
    wrfout(["2025-10-01_00:00:00"]).to_netcdf(tmp_path / "wrfout_d01_2025-10-01_00-00-00")
    stop = threading.Event()
    stop.set()
    with pytest.raises(media.MediaCancelled):
        media.video(
            tmp_path / "cancel.mp4",
            tmp_path,
            reference_case,
            1,
            "wind_speed",
            100,
            [0],
            2,
            320,
            False,
            stop,
            lambda _: None,
        )
    assert not (tmp_path / "cancel.mp4").exists()
    assert (tmp_path / "wrfout_d01_2025-10-01_00-00-00").exists()


@pytest.mark.parametrize("spin", [None, 6, 12, 24])
def test_report_without_outputs_is_configuration_only(
    tmp_path: Path, reference: dict[str, Any], spin: int | None
) -> None:
    if spin is not None:
        reference["windows"] = {"useful_hours": 72}
        reference["spin_up_hours"] = spin
    client = make_client(tmp_path)
    case_id = client.post("/api/cases", json=reference).json()["id"]
    response = client.post(f"/api/cases/{case_id}/media/report", json={"lang": "fr"})
    assert response.status_code == 202
    job = finished(client, response.json()["job_id"])
    assert job["state"] == "succeeded", job
    assert job["result"]["has_energy"] is False
    output = client.get(job["result"]["url"])
    assert output.content.startswith(b"%PDF-")
    assert len(client.get(f"/api/cases/{case_id}/media").json()) == 1


def test_import_hardlinks_preserves_original_and_snapshot(
    tmp_path: Path, reference: dict[str, Any]
) -> None:
    client = make_client(tmp_path)
    case_id = client.post("/api/cases", json=reference).json()["id"]
    source = tmp_path / "external"
    source.mkdir()
    file = source / "wrfout_d01_2025-10-01_00-00-00"
    wrfout(["2025-10-01_00:00:00"]).to_netcdf(file)
    original = file.read_bytes()
    base = f"/api/cases/{case_id}/results/import"
    assert client.post(base + "/preview", json={"folder": ""}).status_code == 422
    preview = client.post(base + "/preview", json={"folder": str(source)}).json()
    assert preview["bytes"] == len(original) and preview["files"] == 1 and preview["warnings"]
    result = client.post(base, json={"folder": str(source)}).json()
    job = finished(client, result["job_id"])
    assert job["state"] == "succeeded", job
    geometry = client.get(f"/api/cases/{case_id}/runs/{result['run_id']}/geometry").json()
    reference["farms"] = []
    client.put(f"/api/cases/{case_id}", json=reference)
    assert client.get(f"/api/cases/{case_id}/runs/{result['run_id']}/geometry").json() == geometry
    imported = (
        tmp_path
        / "data"
        / "cases"
        / case_id
        / "runs"
        / result["run_id"]
        / "outputs"
        / "main"
        / file.name
    )
    assert imported.stat().st_ino == file.stat().st_ino and file.read_bytes() == original


def test_cleanup_preflights_all_items_before_deleting(
    tmp_path: Path, reference: dict[str, Any]
) -> None:
    client = make_client(tmp_path)
    case_id = client.post("/api/cases", json=reference).json()["id"]
    app = client.app.state.owstudio
    paths = app.storage.create_run(case_id)
    sentinel = paths.root / "keep.txt"
    sentinel.write_text("keep")
    response = client.post(
        "/api/storage/cleanup", json={"runs": [f"{case_id}/{paths.id}", f"{case_id}/invalid"]}
    )
    assert response.status_code == 422 and sentinel.read_text() == "keep"
