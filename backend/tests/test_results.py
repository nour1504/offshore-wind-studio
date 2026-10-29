"""Results computed from small synthetic wrfout files with known values."""

import io
from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
import xarray as xr
from helpers import make_client

from owstudio.core.case.model import Case
from owstudio.core.case.workspace import Workspace
from owstudio.core.postproc import wrfout
from owstudio.core.postproc.results import Results
from owstudio.core.storage import Storage

REFERENCE = Path(__file__).parent / "fixtures" / "horns-rev" / "case.yaml"
TIMES = [b"2025-10-01_00:00:00", b"2025-10-01_01:00:00", b"2025-10-01_02:00:00"]
# Mass levels at 25, 75, 125, 175, 225 m: hub height 75 m is the second level
Z_STAG = np.array([0.0, 50.0, 100.0, 150.0, 200.0, 250.0])
FARM_CELL = (49, 49)  # zero-based (j, i) of the cell holding the first turbine on d02


def wrfout_dataset(u_faces: np.ndarray, power: np.ndarray | None) -> xr.Dataset:
    """``u_faces`` (time, y, x + 1) is the west-east wind on cell faces, the same at every level."""
    nt, nz = len(TIMES), len(Z_STAG) - 1
    ny, nx = u_faces.shape[1], u_faces.shape[2] - 1
    speed = 0.5 * (u_faces[..., :-1] + u_faces[..., 1:])
    u = np.repeat(u_faces[:, None, :, :], nz, axis=1)
    ph = np.broadcast_to((Z_STAG * wrfout.GRAVITY)[None, :, None, None], (nt, nz + 1, ny, nx))
    lat, lon = np.meshgrid(np.linspace(54, 57, ny), np.linspace(5, 10, nx), indexing="ij")
    variables: dict[str, Any] = {
        "Times": (("Time",), np.array(TIMES)),
        "U": (("Time", "bottom_top", "south_north", "west_east_stag"), u),
        "V": (
            ("Time", "bottom_top", "south_north_stag", "west_east"),
            np.zeros((nt, nz, ny + 1, nx)),
        ),
        "PH": (("Time", "bottom_top_stag", "south_north", "west_east"), ph.copy()),
        "PHB": (("Time", "bottom_top_stag", "south_north", "west_east"), np.zeros_like(ph)),
        "HGT": (("Time", "south_north", "west_east"), np.zeros((nt, ny, nx))),
        "XLAT": (("Time", "south_north", "west_east"), np.broadcast_to(lat, (nt, ny, nx)).copy()),
        "XLONG": (("Time", "south_north", "west_east"), np.broadcast_to(lon, (nt, ny, nx)).copy()),
        "U10": (("Time", "south_north", "west_east"), speed * 0.8),
        "V10": (("Time", "south_north", "west_east"), np.zeros((nt, ny, nx))),
        "T2": (("Time", "south_north", "west_east"), np.full((nt, ny, nx), 285.15)),
        "PBLH": (("Time", "south_north", "west_east"), np.full((nt, ny, nx), 500.0)),
    }
    if power is not None:
        variables["POWER"] = (("Time", "south_north", "west_east"), power)
    return xr.Dataset(variables)


@pytest.fixture
def case_dir(tmp_path: Path) -> Path:
    """A run of the Horns Rev case with main and control outputs on both domains; returns its
    folder (<tmp>/data/cases/<case>/runs/<run>)."""
    workspace = Workspace(tmp_path / "data")
    case = Case.from_yaml(REFERENCE)
    case_id = workspace.create(case)
    directory = Storage(tmp_path / "data").create_run(case_id).root
    ny = nx = 99
    j, i = FARM_CELL
    control_u = np.full((len(TIMES), ny, nx + 1), 8.0)
    main_u = control_u.copy()
    # Both faces of the farm cell slowed down: 7 m/s there, 7.5 m/s in its two neighbours
    main_u[:, j, i : i + 2] = 7.0
    power = np.zeros((len(TIMES), ny, nx))
    power[1:, j, i] = 40e6  # W; none at the initial time
    for run, u_faces, farm_power in (("main", main_u, power), ("control", control_u, None)):
        out = directory / "outputs" / run
        out.mkdir(parents=True)
        wrfout_dataset(u_faces, None).to_netcdf(out / "wrfout_d01_2025-10-01_00-00-00")
        wrfout_dataset(u_faces, farm_power).to_netcdf(out / "wrfout_d02_2025-10-01_00-00-00")
    case.to_yaml(directory / "outputs" / "main" / "case.yaml")
    return directory


def test_summary_counts_power_after_the_initial_time(case_dir: Path) -> None:
    summary = Results(case_dir).summary()
    assert summary["farm_domain"] == 2
    assert summary["hub_height_m"] == 75  # WRF's generic turbine
    assert summary["installed_mw"] == 160
    assert summary["mean_power_mw"] == pytest.approx(40)
    assert summary["energy_mwh"] == pytest.approx(40)  # 40 MW over one hour
    assert summary["capacity_factor"] == pytest.approx(0.25)


def test_wake_efficiency_compares_with_the_run_without_turbines(case_dir: Path) -> None:
    summary = Results(case_dir).summary()
    # 80 turbines at 8 m/s on WRF's generic curve: 700 kW each
    assert summary["ideal_mean_power_mw"] == pytest.approx(56)
    assert summary["wake_efficiency"] == pytest.approx(40 / 56)


def test_wake_field_is_the_difference_of_the_runs(case_dir: Path) -> None:
    wake = Results(case_dir).field("wake", 2, time=1)
    j, i = FARM_CELL
    np.testing.assert_allclose(wake[j, i - 1 : i + 2], [-0.5, -1.0, -0.5])
    assert np.count_nonzero(wake) == 3


def test_api_serves_summary_power_fields_and_points(case_dir: Path) -> None:
    client = make_client(case_dir.parents[4])
    case_id = case_dir.parents[1].name

    summary = client.get(f"/api/cases/{case_id}/results").json()
    assert summary["has_control"] is True
    assert len(summary["times"]["2"]) == 3

    power = pd.read_csv(io.StringIO(client.get(f"/api/cases/{case_id}/results/power.csv").text))
    assert list(power["farm_power_mw"]) == [0, 40, 40]
    assert power["power_without_wakes_mw"][1] == pytest.approx(56)

    meta = client.get(
        f"/api/cases/{case_id}/results/field", params={"variable": "wake", "domain": 2}
    ).json()
    assert meta["vmin"] == -meta["vmax"]
    assert len(meta["coordinates"]) == 4
    png = client.get(
        f"/api/cases/{case_id}/results/field.png",
        params={"variable": "hub_wind", "domain": 2, "time": 1},
    )
    assert png.headers["content-type"] == "image/png" and png.content[:4] == b"\x89PNG"

    first = Case.from_yaml(REFERENCE).farms[0].turbines[0]
    point = client.get(
        f"/api/cases/{case_id}/results/point",
        params={"domain": 2, "lat": first.lat, "lon": first.lon},
    ).json()
    assert point[1]["hub_wind"] == pytest.approx(7.0) and point[1][
        "hub_wind_control"
    ] == pytest.approx(8.0)


def test_no_results_before_a_run(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    case_id = client.post(
        "/api/cases", json=Case.from_yaml(REFERENCE).model_dump(mode="json")
    ).json()["id"]
    assert client.get(f"/api/cases/{case_id}/results").status_code == 404


def test_wake_needs_a_control_run(case_dir: Path) -> None:
    for path in (case_dir / "outputs" / "control").iterdir():
        path.unlink()
    client = make_client(case_dir.parents[4])
    response = client.get(
        f"/api/cases/{case_dir.parents[1].name}/results/field",
        params={"variable": "wake", "domain": 2},
    )
    assert response.status_code == 404
    assert "without turbines" in response.text


def test_summary_leaves_out_the_spin_up_like_the_energy(case_dir: Path) -> None:
    """Regression: the summary left out only the initial state while the energy figures left
    out the whole spin-up, so the page showed two different energies."""
    out = case_dir / "outputs" / "main"
    ny = nx = 99
    j, i = FARM_CELL
    u = np.full((len(TIMES), ny, nx + 1), 8.0)
    power = np.zeros((len(TIMES), ny, nx))
    power[1, j, i], power[2, j, i] = 20e6, 40e6
    path = out / "wrfout_d02_2025-10-01_00-00-00"
    path.unlink()
    wrfout_dataset(u, power).to_netcdf(path)
    assert Results(case_dir).summary()["mean_power_mw"] == pytest.approx(30)
    case = Case.from_yaml(out / "case.yaml")
    # Two hours of spin-up: the useful period starts after them
    case.spin_up_hours = 2
    case.period.start += timedelta(hours=2)
    case.to_yaml(out / "case.yaml")
    assert Results(case_dir).summary()["mean_power_mw"] == pytest.approx(40)
