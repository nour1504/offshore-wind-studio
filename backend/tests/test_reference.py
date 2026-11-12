"""The run without turbines chosen for a run, from this project or another one on the same grid."""

from pathlib import Path

import numpy as np
import pytest
from helpers import make_client
from test_results import (
    FARM_CELL,
    REFERENCE,
    TIMES,
    case_dir,  # noqa: F401  (fixture: a run imported with its run without turbines)
    wrfout_dataset,
)

from owstudio.core.case.model import Case
from owstudio.core.case.workspace import Workspace
from owstudio.core.storage import Storage


def imported_run(data: Path, case: Case, u_faces: np.ndarray, power: np.ndarray | None) -> Path:
    """One import: a new project holding a run with these outputs (main only)."""
    case_id = Workspace(data).create(case)
    directory = Storage(data).create_run(case_id).root
    out = directory / "outputs" / "main"
    out.mkdir(parents=True)
    wrfout_dataset(u_faces, None).to_netcdf(out / "wrfout_d01_2025-10-01_00-00-00")
    wrfout_dataset(u_faces, power).to_netcdf(out / "wrfout_d02_2025-10-01_00-00-00")
    case.to_yaml(out / "case.yaml")
    (directory / "run.json").write_text(
        f'{{"run_id": "{directory.name}", "state": "succeeded"}}', encoding="utf-8"
    )
    return directory


@pytest.fixture
def runs(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A run with turbines, a run without turbines in another project on the same grid, and a run
    without turbines on another grid."""
    data = tmp_path / "data"
    ny = nx = 99
    j, i = FARM_CELL
    free = np.full((len(TIMES), ny, nx + 1), 8.0)
    waked = free.copy()
    waked[:, j, i : i + 2] = 7.0
    power = np.zeros((len(TIMES), ny, nx))
    power[1:, j, i] = 40e6
    case = Case.from_yaml(REFERENCE)
    with_turbines = imported_run(data, case, waked, power)
    case.name = "Without turbines"
    without = imported_run(data, case, free, None)
    other = case.model_copy(deep=True)
    other.name = "Other grid"
    other.grid.dx = case.grid.dx * 2
    elsewhere = imported_run(data, other, free, None)
    return with_turbines, without, elsewhere


def ids(root: Path) -> tuple[str, str]:
    return root.parents[1].name, root.name


def test_a_run_without_turbines_of_another_project_is_offered_and_compared(
    runs: tuple[Path, Path, Path],
) -> None:
    with_turbines, without, elsewhere = runs
    client = make_client(with_turbines.parents[4])
    case_id, run_id = ids(with_turbines)
    url = f"/api/cases/{case_id}/runs/{run_id}/reference"

    offered = client.get(url).json()
    assert offered["current"] == {"kind": "none"} and offered["included"] is False
    # Only the run without turbines on the same grid; never the run itself or one with turbines
    assert [(o["case_id"], o["run_id"]) for o in offered["options"]] == [ids(without)]
    assert client.get(f"/api/cases/{case_id}/results").json()["has_control"] is False

    other_case, other_run = ids(without)
    chosen = client.put(url, json={"kind": "run", "case_id": other_case, "run_id": other_run})
    assert chosen.status_code == 200
    assert chosen.json()["current"] == {"kind": "run", "case_id": other_case, "run_id": other_run}
    summary = client.get(f"/api/cases/{case_id}/results").json()
    assert summary["has_control"] is True
    assert summary["wake_efficiency"] == pytest.approx(40 / 56)

    far_case, far_run = ids(elsewhere)
    refused = client.put(url, json={"kind": "run", "case_id": far_case, "run_id": far_run})
    assert refused.status_code == 422

    assert client.put(url, json={"kind": "none"}).json()["current"] == {"kind": "none"}
    assert client.get(f"/api/cases/{case_id}/results").json()["has_control"] is False
    # Nothing was copied or moved
    assert not (with_turbines / "outputs" / "control").exists()
    assert (without / "outputs" / "main" / "wrfout_d02_2025-10-01_00-00-00").is_file()


def test_the_run_imported_with_it_can_be_left_out_and_taken_back(case_dir: Path) -> None:  # noqa: F811
    client = make_client(case_dir.parents[4])
    case_id, run_id = ids(case_dir)
    url = f"/api/cases/{case_id}/runs/{run_id}/reference"
    assert client.get(url).json()["current"] == {"kind": "included"}

    assert client.put(url, json={"kind": "none"}).json()["current"] == {"kind": "none"}
    assert client.get(f"/api/cases/{case_id}/results").json()["has_control"] is False
    assert (case_dir / "outputs" / "control").is_dir()  # kept, only left out

    assert client.put(url, json={"kind": "included"}).json()["current"] == {"kind": "included"}
    assert client.get(f"/api/cases/{case_id}/results").json()["has_control"] is True


def test_the_results_open_on_the_latest_run_with_turbines(tmp_path: Path) -> None:
    """A run without turbines imported after the run with turbines is its reference: the pages
    still open on the run with turbines."""
    data = tmp_path / "data"
    ny = nx = 99
    j, i = FARM_CELL
    free = np.full((len(TIMES), ny, nx + 1), 8.0)
    power = np.zeros((len(TIMES), ny, nx))
    power[1:, j, i] = 40e6
    case = Case.from_yaml(REFERENCE)
    with_turbines = imported_run(data, case, free, power)
    case_id = with_turbines.parents[1].name
    later = Storage(data).create_run(case_id).root
    out = later / "outputs" / "main"
    out.mkdir(parents=True)
    wrfout_dataset(free, None).to_netcdf(out / "wrfout_d01_2025-10-01_00-00-00")
    wrfout_dataset(free, None).to_netcdf(out / "wrfout_d02_2025-10-01_00-00-00")
    case.to_yaml(out / "case.yaml")
    assert later.name > with_turbines.name
    client = make_client(data.parent)
    assert client.get(f"/api/cases/{case_id}/results").json()["run_id"] == with_turbines.name
