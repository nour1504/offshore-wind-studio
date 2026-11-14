"""Results computed from small synthetic wrfout files with known values."""

from datetime import timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import xarray as xr
from helpers import make_client

from owstudio.core.case.model import Case
from owstudio.core.case.workspace import Workspace
from owstudio.core.postproc.results import Results
from owstudio.core.storage import Storage

REFERENCE = Path(__file__).parent / "fixtures" / "horns-rev" / "case.yaml"
TIMES = [b"2025-10-01_00:00:00", b"2025-10-01_01:00:00", b"2025-10-01_02:00:00"]
GRAVITY = 9.81  # m s-2, value used by WRF
# Mass levels at 25, 75, 125, 175, 225 m: hub height 75 m is the second level
Z_STAG = np.array([0.0, 50.0, 100.0, 150.0, 200.0, 250.0])
_FIRST = Case.from_yaml(REFERENCE).farms[0].turbines[0]
# Zero-based (j, i) of the cell holding the first turbine on the grid of the files (a regular one,
# 99 x 99 points from 54 to 57 degrees north and 5 to 10 degrees east)
FARM_CELL = (round((_FIRST.lat - 54) / 3 * 98), round((_FIRST.lon - 5) / 5 * 98))


def wrfout_dataset(u_faces: np.ndarray, power: np.ndarray | None) -> xr.Dataset:
    """``u_faces`` (time, y, x + 1) is the west-east wind on cell faces, the same at every level."""
    nt, nz = len(TIMES), len(Z_STAG) - 1
    ny, nx = u_faces.shape[1], u_faces.shape[2] - 1
    speed = 0.5 * (u_faces[..., :-1] + u_faces[..., 1:])
    u = np.repeat(u_faces[:, None, :, :], nz, axis=1)
    ph = np.broadcast_to((Z_STAG * GRAVITY)[None, :, None, None], (nt, nz + 1, ny, nx))
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
        "COSALPHA": (("Time", "south_north", "west_east"), np.ones((nt, ny, nx))),
        "SINALPHA": (("Time", "south_north", "west_east"), np.zeros((nt, ny, nx))),
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


def test_a_run_without_tslist_gets_its_energy_from_the_history_files(case_dir: Path) -> None:
    """A run without tslist outputs at the turbines: the energy tables, the production per
    direction and the power curve come from WRF's POWER of the history files instead of being
    refused, and the summary says where they come from."""
    out = case_dir / "outputs" / "main"
    ny = nx = 99
    j, i = FARM_CELL
    power = np.zeros((len(TIMES), ny, nx))
    power[1:, j, i] = 40e6
    path = out / "wrfout_d02_2025-10-01_00-00-00"
    path.unlink()
    wrfout_dataset(np.full((len(TIMES), ny, nx + 1), 7.0), power).to_netcdf(path)

    client = make_client(case_dir.parents[4])
    case_id = case_dir.parents[1].name
    summary = client.get(f"/api/cases/{case_id}/results").json()
    assert summary["tslist"] is False
    assert summary["energy_error"] is None and summary["energy_source"] == "wrfout"

    energy = client.get(f"/api/cases/{case_id}/energy").json()
    assert energy["method"] == "wrf"
    # 40 MW from 01:00 to 02:00; the initial time, written before the first step, is left out
    assert energy["total"]["energy_mwh"] == pytest.approx(40)
    turbine = next(row for row in energy["turbines"] if row["energy_mwh"] > 0)

    # The wind blows from the west at every time: all the energy of the turbine in that sector
    sectors = client.get(
        f"/api/cases/{case_id}/energy/sectors", params={"turbine": turbine["label"], "sectors": 12}
    ).json()
    assert sectors["method"] == "wrf"
    assert sectors["energy_mwh"] == pytest.approx(turbine["energy_mwh"])
    west = next(row for row in sectors["sectors"] if row["centre_deg"] == 270)
    assert west["energy_mwh"] == pytest.approx(turbine["energy_mwh"]) and west["count"] == 1
    assert sectors["unclassified_mwh"] == 0
    assert sectors["reference_mwh"] == pytest.approx(turbine["reference_energy_mwh"])

    # The power at each wrfout time against the free wind of the same time (8 m/s everywhere)
    curve = client.get(
        f"/api/cases/{case_id}/energy/curve", params={"turbine": turbine["label"]}
    ).json()
    assert curve["method"] == "wrf"
    assert [point["speed_ms"] for point in curve["points"]] == pytest.approx([8, 8])


def test_the_energy_asked_from_the_tslist_says_what_is_missing(case_dir: Path) -> None:
    client = make_client(case_dir.parents[4])
    energy = client.get(
        f"/api/cases/{case_dir.parents[1].name}/energy", params={"method": "tslist"}
    )
    assert energy.status_code == 422 and "tslist" in energy.json()["detail"]


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
    # One time left (02:00): no interval, so no energy and no mean, as in the energy tables
    from owstudio.core.energy.summary import run_energy

    summary = Results(case_dir).summary()
    total = run_energy(case_dir, case)["total"]
    assert summary["mean_power_mw"] is None and total["mean_power_mw"] is None
    assert summary["energy_mwh"] == total["energy_mwh"] == 0
    assert summary["max_power_mw"] == pytest.approx(40)


def test_one_history_file_per_domain_gives_the_figures_of_the_energy_tables(
    case_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: with one wrfout per domain holding every time (WRF's default
    frames_per_outfile), the key figures were the mean of the output values times the duration
    while the energy tables integrate by trapezoids: two energies on the same page."""
    from owstudio.core.energy.summary import run_energy

    times = [*TIMES, b"2025-10-01_03:00:00"]
    monkeypatch.setattr("test_results.TIMES", times)
    ny = nx = 99
    j, i = FARM_CELL
    u = np.full((len(times), ny, nx + 1), 8.0)
    power = np.zeros((len(times), ny, nx))
    power[1:, j, i] = [10e6, 20e6, 60e6]
    for run, farm_power in (("main", power), ("control", None)):
        out = case_dir / "outputs" / run
        for path in out.glob("wrfout_d0*"):
            path.unlink()
        wrfout_dataset(u, None).to_netcdf(out / "wrfout_d01_2025-10-01_00-00-00")
        wrfout_dataset(u, farm_power).to_netcdf(out / "wrfout_d02_2025-10-01_00-00-00")
    results = Results(case_dir)
    summary = results.summary()
    total = run_energy(case_dir, results.case)["total"]
    # Trapezoids from 01:00 to 03:00: (10 + 20) / 2 + (20 + 60) / 2 MWh
    assert total["energy_mwh"] == pytest.approx(55)
    assert summary["energy_mwh"] == pytest.approx(total["energy_mwh"])
    assert summary["mean_power_mw"] == pytest.approx(total["mean_power_mw"])
    assert summary["capacity_factor"] == pytest.approx(total["capacity_factor"])
    assert summary["wake_efficiency"] == pytest.approx(
        total["energy_mwh"] / total["reference_energy_mwh"]
    )
