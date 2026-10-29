"""Extraction from synthetic WRF history files with known values: grid location, rotation to
earth-relative winds, heights, interpolation, segments, turbulence from TKE, Obukhov length,
diagnostics availability and the explorer API."""

import math
import re
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import xarray as xr
from helpers import make_client, wsl_profile

from owstudio.api.routes_import import stored_name
from owstudio.core.case.model import Case, Farm, Turbine
from owstudio.core.case.workspace import Workspace
from owstudio.core.extract import quantities
from owstudio.core.extract.catalogue import availability
from owstudio.core.extract.grid import OutsideGrid, locate
from owstudio.core.extract.history import HistoryFiles, domains
from owstudio.core.extract.points import point_series
from owstudio.core.storage import Storage

G = 9.81
NX = NY = 6
Z_STAG = np.array([0.0, 50.0, 100.0, 150.0])  # mass levels at 25, 75, 125 m
SPEEDS = np.array([5.0, 7.0, 9.0])  # grid-relative U on the levels, V = 0
ALPHA = math.radians(30.0)  # map rotation
TKE = 0.6


def wrfout(times: list[str], extra: dict[str, Any] | None = None) -> xr.Dataset:
    nt, nz = len(times), len(SPEEDS)
    lat, lon = np.meshgrid(54.0 + 0.1 * np.arange(NY), 7.0 + 0.1 * np.arange(NX), indexing="ij")
    shape2 = (nt, NY, NX)
    u = np.broadcast_to(SPEEDS[None, :, None, None], (nt, nz, NY, NX + 1)).copy()
    ph = np.broadcast_to((Z_STAG * G)[None, :, None, None], (nt, nz + 1, NY, NX)).copy()
    variables: dict[str, Any] = {
        "Times": (("Time",), np.array([t.encode() for t in times])),
        "XLAT": (("Time", "south_north", "west_east"), np.broadcast_to(lat, shape2).copy()),
        "XLONG": (("Time", "south_north", "west_east"), np.broadcast_to(lon, shape2).copy()),
        "U": (("Time", "bottom_top", "south_north", "west_east_stag"), u),
        "V": (
            ("Time", "bottom_top", "south_north_stag", "west_east"),
            np.zeros((nt, nz, NY + 1, NX)),
        ),
        "PH": (("Time", "bottom_top_stag", "south_north", "west_east"), ph),
        "PHB": (("Time", "bottom_top_stag", "south_north", "west_east"), np.zeros_like(ph)),
        "HGT": (("Time", "south_north", "west_east"), np.zeros(shape2)),
        "COSALPHA": (("Time", "south_north", "west_east"), np.full(shape2, math.cos(ALPHA))),
        "SINALPHA": (("Time", "south_north", "west_east"), np.full(shape2, math.sin(ALPHA))),
        "U10": (("Time", "south_north", "west_east"), np.full(shape2, 4.0)),
        "V10": (("Time", "south_north", "west_east"), np.zeros(shape2)),
        "T": (("Time", "bottom_top", "south_north", "west_east"), np.zeros((nt, nz, NY, NX))),
        "P": (("Time", "bottom_top", "south_north", "west_east"), np.zeros((nt, nz, NY, NX))),
        "PB": (
            ("Time", "bottom_top", "south_north", "west_east"),
            np.full((nt, nz, NY, NX), 1.0e5),
        ),
        "QVAPOR": (("Time", "bottom_top", "south_north", "west_east"), np.zeros((nt, nz, NY, NX))),
        "QKE": (
            ("Time", "bottom_top", "south_north", "west_east"),
            np.full((nt, nz, NY, NX), 2 * TKE),
        ),
        "UST": (("Time", "south_north", "west_east"), np.full(shape2, 0.3)),
        "HFX": (("Time", "south_north", "west_east"), np.full(shape2, -20.0)),
        "QFX": (("Time", "south_north", "west_east"), np.zeros(shape2)),
        "T2": (("Time", "south_north", "west_east"), np.full(shape2, 285.0)),
        "Q2": (("Time", "south_north", "west_east"), np.zeros(shape2)),
        "PSFC": (("Time", "south_north", "west_east"), np.full(shape2, 1.0e5)),
        "POWER": (("Time", "south_north", "west_east"), np.zeros(shape2)),
    }
    variables.update(extra or {})
    return xr.Dataset(variables)


@pytest.fixture
def run_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "outputs" / "main"
    folder.mkdir(parents=True)
    # Two restart segments sharing the time 01:00
    wrfout(["2025-10-01_00:00:00", "2025-10-01_01:00:00"]).to_netcdf(
        folder / "wrfout_d01_2025-10-01_00-00-00"
    )
    wrfout(["2025-10-01_01:00:00", "2025-10-01_02:00:00"]).to_netcdf(
        folder / "wrfout_d01_2025-10-01_01-00-00"
    )
    return folder


def test_location_on_the_grid() -> None:
    lat, lon = np.meshgrid(54.0 + 0.1 * np.arange(NY), 7.0 + 0.1 * np.arange(NX), indexing="ij")
    position = locate(lat, lon, 54.25, 7.32)
    assert position.i == pytest.approx(3.2, abs=1e-6) and position.j == pytest.approx(2.5, abs=1e-6)
    with pytest.raises(OutsideGrid):
        locate(lat, lon, 60.0, 7.2)


def test_segments_are_joined_without_duplicate_times(run_folder: Path) -> None:
    files = HistoryFiles(run_folder, 1)
    assert [t.hour for t in files.times] == [0, 1, 2]
    assert files.window("U", 1, 1).shape == (3, 3, 2, 2)  # destaggered to 2 x 2 mass points


def test_outputs_named_in_a_linux_folder_are_found_and_stored_openable(tmp_path: Path) -> None:
    """WSL shows Windows the ":" of a Linux file name as U+F03A, which the netCDF library cannot
    open: such files are found, and imported under the dashed form of the time."""
    name = "wrfout_d02_2026-10-20_060000"
    (tmp_path / name).write_bytes(b"")
    assert domains(tmp_path) == [2]
    assert stored_name(name) == "wrfout_d02_2026-10-20_06-00-00"


def test_winds_are_rotated_and_interpolated_in_height(run_folder: Path) -> None:
    files = HistoryFiles(run_folder, 1)
    position = locate(*files.coordinates, 54.25, 7.32)
    speed = point_series(files, position, "wind_speed", 100.0).values.to_numpy()
    assert speed == pytest.approx([8.0, 8.0, 8.0])  # between 75 m (7) and 125 m (9)
    u = point_series(files, position, "u", 100.0).values.to_numpy()
    v = point_series(files, position, "v", 100.0).values.to_numpy()
    # Grid-relative (8, 0) rotated by 30°: u_e = u cosα - v sinα, v_e = v cosα + u sinα
    assert u[0] == pytest.approx(8 * math.cos(ALPHA)) and v[0] == pytest.approx(8 * math.sin(ALPHA))
    direction = point_series(files, position, "wind_direction", 100.0).values.to_numpy()
    assert direction[0] == pytest.approx(
        (270.0 - 30.0) % 360.0
    )  # blowing towards 30° north of east
    below = point_series(files, position, "wind_speed", 20.0)
    assert np.isnan(below.values.to_numpy()).all() and "outside the model levels" in below.flags[0]
    ten = point_series(files, position, "wind_speed", 10.0)
    assert ten.values.to_numpy()[0] == pytest.approx(4.0) and "U10" in ten.method


def test_turbulence_from_tke_assumes_isotropy(run_folder: Path) -> None:
    files = HistoryFiles(run_folder, 1)
    position = locate(*files.coordinates, 54.25, 7.32)
    sigma = point_series(files, position, "wind_speed_std", 100.0)
    assert sigma.values.to_numpy()[0] == pytest.approx(math.sqrt(2 * TKE / 3))
    ti = point_series(files, position, "turbulence_intensity", 100.0)
    assert ti.values.to_numpy()[0] == pytest.approx(math.sqrt(2 * TKE / 3) / 8.0)
    assert any("isotropic" in flag for flag in ti.flags)
    with pytest.raises(quantities.Unavailable, match="needs a height"):
        point_series(files, position, "turbulence_intensity", None)


def test_surface_quantity_ignores_a_height(run_folder: Path) -> None:
    files = HistoryFiles(run_folder, 1)
    position = locate(*files.coordinates, 54.25, 7.32)
    surface = point_series(files, position, "friction_velocity", None)
    with_height = point_series(files, position, "friction_velocity", 75.0)
    assert np.allclose(surface.values.to_numpy(), with_height.values.to_numpy(), equal_nan=True)


def test_turbulence_intensity_is_not_given_at_low_speed() -> None:
    tke = quantities.Computed(np.array([0.6, 0.6]), "m2 s-2", "test")
    speed = quantities.Computed(np.array([1.0, 6.0]), "m s-1", "test")
    ti = quantities.turbulence("turbulence_intensity", tke, speed).values
    assert np.isnan(ti[0]) and ti[1] == pytest.approx(math.sqrt(0.4) / 6.0)


def test_obukhov_length_from_fluxes(run_folder: Path) -> None:
    files = HistoryFiles(run_folder, 1)
    position = locate(*files.coordinates, 54.25, 7.32)
    inverse = point_series(files, position, "inverse_obukhov_length", None)
    rho = 1.0e5 / (287.0 * 285.0)
    theta = 285.0  # at p = p0 the potential temperature equals the temperature
    expected = -0.4 * 9.81 * (-20.0 / (rho * 1004.5)) / (0.3**3 * theta)
    assert inverse.values.to_numpy()[0] == pytest.approx(expected, rel=1e-6)
    assert expected > 0  # downward heat flux: stable
    assert "derived" in inverse.flags[0]


def test_power_uses_the_cell_holding_the_point(tmp_path: Path) -> None:
    power = np.zeros((1, NY, NX))
    power[0, 2, 3] = 2.0e6
    folder = tmp_path / "out"
    folder.mkdir()
    wrfout(
        ["2025-10-01_00:00:00"], {"POWER": (("Time", "south_north", "west_east"), power)}
    ).to_netcdf(folder / "wrfout_d01_2025-10-01_00-00-00")
    files = HistoryFiles(folder, 1)
    position = locate(*files.coordinates, 54.24, 7.31)  # inside the cell (j=2, i=3)
    assert point_series(files, position, "power", None).values.to_numpy()[0] == pytest.approx(2.0e6)


def test_availability_of_diagnostics(run_folder: Path) -> None:
    status = {d["key"]: d for d in availability(HistoryFiles(run_folder, 1), tslist=False)}
    assert status["inverse_obukhov_length"]["status"] == "derivable"  # no RMOL: from the fluxes
    assert status["turbulence_intensity"]["status"] == "derivable"
    assert status["roughness_length"]["status"] == "impossible" and status["roughness_length"][
        "missing"
    ] == ["ZNT"]
    assert "ZNT" in status["roughness_length"]["enable"]


# ----------------------------------------------------------------- API


@pytest.fixture
def client_with_run(tmp_path: Path, run_folder: Path) -> tuple[Any, str, str]:
    data = tmp_path / "data"
    workspace = Workspace(data)
    from helpers import REFERENCE

    case = Case.from_yaml(REFERENCE)
    case.farms = [Farm(id="A", name="A", turbines=[Turbine(lat=54.25, lon=7.32, id="A01")])]
    case_id = workspace.create(case)
    run = Storage(data).create_run(case_id)
    target = run.root / "outputs" / "main"
    target.mkdir(parents=True)
    for path in run_folder.iterdir():
        (target / path.name).write_bytes(path.read_bytes())
    case.to_yaml(target / "case.yaml")
    return make_client(tmp_path, profiles=[wsl_profile()]), case_id, run.id


def test_explorer_api(client_with_run: tuple[Any, str, str]) -> None:
    client, case_id, run_id = client_with_run
    listing = client.get(f"/api/cases/{case_id}/runs/{run_id}/variables").json()
    names = {v["name"] for v in listing["domains"]["1"]}
    assert {"U", "QKE", "T2"} <= names and len(listing["times"]["1"]) == 3
    diagnostics = client.get(f"/api/cases/{case_id}/runs/{run_id}/diagnostics").json()[
        "diagnostics"
    ]
    assert next(d for d in diagnostics if d["key"] == "tke")["status"] == "derivable"
    fiche = client.get("/api/variables/RMOL").json()
    assert fiche["in_history_by_default"] is False and "+:h:0:RMOL" in fiche["how_to_add"]
    assert (
        client.get("/api/variables/turbulence_intensity").json()["diagnostic"]["needs_height"]
        is True
    )
    ref = {
        "kind": "run",
        "case_id": case_id,
        "variable": "turbulence_intensity",
        "location": "A01",
        "height_m": 100,
    }
    series = client.post("/api/explore/series", json={"refs": [ref]}).json()["series"][0]
    assert (
        series["values"][0] == pytest.approx(math.sqrt(0.4) / 8.0)
        and series["meta"]["source"] == "wrfout"
    )
    assert series["meta"]["dataset"] == f"{case_id}/{run_id}/main"
    csv = client.post("/api/explore/series", params={"format": "csv"}, json={"refs": [ref]})
    assert csv.text.startswith("# {") and "turbulence_intensity" in csv.text
    missing = client.post("/api/explore/series", json={"refs": [{**ref, "location": "nowhere"}]})
    assert missing.status_code == 404 and "Unknown location" in missing.text
    meta = client.get(
        f"/api/cases/{case_id}/runs/{run_id}/map",
        params={"variable": "wind_speed", "domain": 1, "time": 1, "height": 100},
    ).json()
    assert meta["vmin"] == pytest.approx(8.0) and len(meta["coordinates"]) == 4
    png = client.get(
        f"/api/cases/{case_id}/runs/{run_id}/map.png",
        params={"variable": "wind_speed", "domain": 1, "height": 100},
    )
    assert png.content[:4] == b"\x89PNG"
    refused = client.get(
        f"/api/cases/{case_id}/runs/{run_id}/map", params={"variable": "tke", "domain": 1}
    )
    assert refused.status_code == 422 and "needs a height" in refused.text


def test_variable_search_for_outputs(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    exact = client.get("/api/variables", params={"names": "rmol,U10,unknown"}).json()
    assert [v["name"] for v in exact] == ["RMOL", "U10"]
    assert exact[1]["units"] == "m s-1" and exact[1]["history"] is True
    found = client.get("/api/variables", params={"q": "heat flux", "limit": 20}).json()
    assert found and all(v["file"] not in ("registry.chem",) for v in found[:5])
    assert all(
        re.match(r"^[A-Za-z0-9_]{1,40}$", v["name"])
        for v in client.get("/api/variables", params={"limit": 500}).json()
    )
    assert client.get("/api/variables", params={"q": "ust"}).json()[0]["name"] == "UST"
