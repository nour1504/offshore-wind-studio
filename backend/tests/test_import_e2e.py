"""A cluster return: real export metadata + tiny NetCDF/tslist files, imported through HTTP.

Only the cluster programs are absent. Export, asynchronous import, retained-time readers,
cell deduplication, maps and energy use their normal application paths. No WRF or user data.
"""

import io
import json
import math
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from helpers import make_client
from test_extract import wrfout
from test_tslist import HEADER_FORMAT

from owstudio.core.case.model import Case, Farm, TimeSeries, Turbine, Windows
from owstudio.core.energy.curves import turbine_types, wrf_power_w
from owstudio.core.method.export import ExportOptions, write_folder


def done(client: Any, job_id: str) -> dict[str, Any]:
    for _ in range(200):
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200
        job: dict[str, Any] = response.json()
        if job["state"] != "running":
            assert job["state"] == "succeeded", job
            return job
        time.sleep(0.01)
    raise AssertionError("The tiny synthetic import did not finish")


def returned_export(root: Path, case: Case, control: bool = False) -> dict[str, Any]:
    """The real exported package returned by a cluster; each wrfout is one real NetCDF frame.

    Out-of-period sentinels must never reach a map, series or energy result, even if a user
    brings extra raw files back next to the retained outputs.
    """
    write_folder(case, ExportOptions(target="cluster"), root)
    manifest = json.loads((root / "manifest.json").read_text())
    target = root / "wrf"
    origin = case.period.start
    times = [
        origin - timedelta(hours=1),
        origin,
        origin + timedelta(hours=1),
        case.period.end,
        case.period.end + timedelta(hours=1),
    ]
    first = case.farms[0].turbines[0]
    lat = first.lat + 0.1 * (np.arange(6) - 2)
    lon = first.lon + 0.1 * (np.arange(6) - 2)
    latitude, longitude = np.meshgrid(lat, lon, indexing="ij")
    for stamp in times:
        speed = 7.0 if origin <= stamp <= case.period.end else 90.0
        power = np.zeros((1, 6, 6))
        if not control:
            power[0, 2, 2], power[0, 3, 2] = (0.4e6, 0.2e6) if speed == 7 else (90e6, 90e6)
        dataset = wrfout([stamp.strftime("%Y-%m-%d_%H:%M:%S")])
        dataset["XLAT"].values[:] = latitude
        dataset["XLONG"].values[:] = longitude
        dataset["U"].values[:] = speed
        dataset["V"].values[:] = 0
        dataset["U10"].values[:] = speed
        dataset["V10"].values[:] = 0
        dataset["COSALPHA"].values[:] = 1
        dataset["SINALPHA"].values[:] = 0
        dataset.attrs["DX"] = 3000.0  # written by WRF in every history file
        if not control:
            dataset["POWER"].values[:] = power
        else:
            dataset = dataset.drop_vars("POWER")
        dataset.to_netcdf(target / f"wrfout_d02_{stamp:%Y-%m-%d_%H-%M-%S}")

    series = target / "tslist_periode"
    series.mkdir()
    # One-per-turbine mode deliberately writes two identical point series in one cell.
    for number, point in enumerate(manifest["time_series"]["points"], 1):
        j = 3 if number < 3 else 4
        header = HEADER_FORMAT.format(
            name=point["name"],
            domain=2,
            ts_id=number,
            prefix=point["prefix"],
            lat=point["lat"],
            lon=point["lon"],
            i=3,
            j=j,
            glat=point["lat"],
            glon=point["lon"],
            elev=0,
            start=origin.strftime("%Y-%m-%d_%H:%M:%S"),
        )
        hours = np.arange(-1, 3.1, 1 / 6)
        for kind in ("TS", "PH", "UU", "VV"):
            rows = []
            for hour in hours:
                retained = 0 < hour <= 2 + 1e-8
                speed = (8.0 if control else 6.0) if retained else 90.0
                if kind == "TS":
                    values = [285.15, 0.008, speed, 0, 101325.0] + [0.0] * 9
                    rows.append(f"2 {hour:.6f} {number} 3 {j} " + " ".join(map(str, values)))
                else:
                    values = (
                        [25, 75, 125] if kind == "PH" else [speed] * 3 if kind == "UU" else [0] * 3
                    )
                    rows.append(f"{hour:.6f} " + " ".join(map(str, values)))
            (series / f"{point['prefix']}.d02.{kind}").write_text(
                header + "\n" + "\n".join(rows) + "\n", encoding="ascii"
            )
    return manifest


@pytest.mark.parametrize("mode", ["copy", "link"])
@pytest.mark.parametrize("source_child", [False, True])
def test_export_return_imports_utc_period_cells_power_and_reference(
    tmp_path: Path, reference_case: Case, mode: str, source_child: bool
) -> None:
    case = reference_case.model_copy(deep=True)
    first = case.farms[0].turbines[0]
    case.name = "Synthetic cluster return"
    case.input_source = "era5"
    case.period.interval_seconds = 3600
    case.period.start, case.period.end = datetime(2025, 1, 31, 23), datetime(2025, 2, 1, 1)
    case.windows, case.spin_up_hours = Windows(useful_hours=72), 12
    case.time_series = TimeSeries(turbines="each", max_levels=3)
    case.farms = [
        Farm(
            id="a",
            name="Farm A",
            turbines=[
                Turbine(id="T1", lat=first.lat, lon=first.lon),
                Turbine(id="T2", lat=first.lat + 0.00001, lon=first.lon),
            ],
        ),
        Farm(
            id="b", name="Farm B", turbines=[Turbine(id="T1", lat=first.lat + 0.1, lon=first.lon)]
        ),
    ]
    assert case.farm_scheme is not None
    case.farm_scheme.domains = [2]
    source, control = tmp_path / "cluster-main", tmp_path / "cluster-reference"
    manifest = returned_export(source, case)
    returned_export(control, case, control=True)
    source_hashes = {
        p: p.read_bytes() for folder in (source, control) for p in folder.rglob("*") if p.is_file()
    }
    assert manifest["timezone"] == "UTC"
    assert manifest["conventions"]["time_series"] == "]D, F]"
    assert sorted(len(cell["turbines"]) for cell in manifest["cells"]) == [1, 2]

    client = make_client(tmp_path / "application")
    response = client.post("/api/cases", json=case.model_dump(mode="json"))
    assert response.status_code == 201, response.text
    case_id = response.json()["id"]
    url = f"/api/cases/{case_id}/results"
    child = "wrf" if source_child else ""
    body = {"folder": str(source / child), "control_folder": str(control / child), "mode": mode}
    preview = client.post(url + "/import/preview", json=body)
    assert preview.status_code == 200, preview.text
    assert preview.json()["domains"] == {"main": [2], "control": [2]}
    imported = client.post(url + "/import", json=body)
    assert imported.status_code == 202, imported.text
    run = imported.json()["run_id"]
    done(client, imported.json()["job_id"])
    params = {"run": run}
    summary = client.get(url, params=params)
    assert summary.status_code == 200, summary.text
    assert summary.json()["times"]["2"] == [
        "2025-01-31T23:00:00+00:00",
        "2025-02-01T00:00:00+00:00",
        "2025-02-01T01:00:00+00:00",
    ]
    assert summary.json()["has_control"] is True
    assert summary.json()["windowed"] is True
    powers = pd.read_csv(io.StringIO(client.get(url + "/power.csv", params=params).text))
    assert list(powers["farm_power_mw"]) == pytest.approx([0.6] * 3)
    field = client.get(
        url + "/point", params={**params, "domain": 2, "lat": first.lat, "lon": first.lon}
    ).json()
    assert len(field) == 3 and [row["hub_wind"] for row in field] == pytest.approx([7] * 3)

    locations = client.get(url + "/tslist", params=params).json()["locations"]
    assert len(locations) == 2
    assert sorted(len(location["members"]) for location in locations) == [1, 2]
    assert all(location["has_control"] for location in locations)
    prefix = locations[0]["prefix"]
    series = client.get(
        url + f"/tslist/{prefix}", params={**params, "domain": 2, "height": 75, "average_s": 0}
    ).json()
    times = pd.DatetimeIndex([row["time"] for row in series])
    assert len(series) == 12
    assert times[0] > pd.Timestamp(case.period.start)
    assert times[-1] == pd.Timestamp(case.period.end)
    assert [row["wind_speed_hub"] for row in series] == pytest.approx([6] * 12)
    assert [row["wind_speed_hub_no_farm"] for row in series] == pytest.approx([8] * 12)
    csv = client.get(
        url + f"/tslist/{prefix}/csv", params={**params, "domain": 2, "height": 75, "average_s": 0}
    )
    assert csv.status_code == 200 and "times UTC" in csv.text and "time_utc" in csv.text

    energy = client.get(f"/api/cases/{case_id}/energy", params=params)
    assert energy.status_code == 200, energy.text
    data = energy.json()
    assert data["covered_h"] == pytest.approx(2)
    assert data["total"]["energy_mwh"] == pytest.approx(1.2)
    assert {row["id"]: row["energy_mwh"] for row in data["farms"]} == pytest.approx(
        {"a": 0.8, "b": 0.4}
    )
    assert sum(row["energy_mwh"] for row in data["turbines"]) == pytest.approx(1.2)
    assert len({row["label"] for row in data["turbines"]}) == 3
    model = turbine_types(case)[1]
    free = float(wrf_power_w(np.array([7.0]), model)[0]) / 1e6
    assert data["total"]["reference_energy_mwh"] == pytest.approx(free * 3 * 2)
    assert data["turbines_approximate"] is True
    assert len(data["cells"]) == 2
    assert sum(row["energy_mwh"] for row in data["cells"]) == pytest.approx(1.2)
    assert {row["id"]: row["turbines"] for row in data["cells"]} == {"d02:3:3": 2, "d02:3:4": 1}
    cell_series = client.get(
        f"/api/cases/{case_id}/energy/series", params={**params, "cell": "d02:3:3"}
    )
    assert cell_series.status_code == 200, cell_series.text
    assert cell_series.json()["unit"] == "MW"
    assert cell_series.json()["series"]["d02:3:3"] == pytest.approx([0.4] * 3)
    monthly = client.get(
        f"/api/cases/{case_id}/energy/series",
        params={**params, "period": "month", "cell": "d02:3:3"},
    ).json()
    assert monthly["unit"] == "MWh"
    assert monthly["times"] == ["2025-01-01T00:00:00+00:00", "2025-02-01T00:00:00+00:00"]
    assert monthly["series"]["d02:3:3"] == pytest.approx([0.4, 0.4])
    ambiguous = client.get(
        f"/api/cases/{case_id}/energy/series",
        params={**params, "cell": "d02:3:3", "turbine": data["turbines"][0]["label"]},
    )
    assert ambiguous.status_code == 422
    # Per wind direction, one turbine: each 10-minute interval of the tslist outputs, its mean
    # power x 10 min in the sector of its mean wind (from the west in both runs); without
    # turbines, the power curve at the free wind (8 m/s) over the 2 h
    first = data["turbines"][0]
    by_direction = client.get(
        f"/api/cases/{case_id}/energy/sectors",
        params={**params, "sectors": 4, "turbine": first["label"]},
    ).json()
    west = next(row for row in by_direction["sectors"] if row["centre_deg"] == 270)
    assert by_direction["energy_mwh"] > 0 and west["energy_mwh"] == pytest.approx(
        by_direction["energy_mwh"]
    )
    assert west["hours"] == pytest.approx(2.0)
    free_8 = float(wrf_power_w(np.array([8.0]), model)[0]) / 1e6
    assert by_direction["reference_mwh"] == pytest.approx(free_8 * 2)
    assert by_direction["unclassified_mwh"] == 0
    # Its power curve: WRF's power at each output time against the free wind at that time (the
    # tslist wind of the run without turbines, 8 m/s), in 0.5 m/s bins, Cp with WRF's density
    curve = client.get(
        f"/api/cases/{case_id}/energy/curve", params={**params, "turbine": first["label"]}
    ).json()
    assert curve["points"] and all(p["speed_ms"] == pytest.approx(8.0) for p in curve["points"])
    [only] = curve["bins"]
    assert only["centre_ms"] == 8.0 and only["count"] == len(curve["points"])
    swept = 0.5 * 1.23 * math.pi / 4 * model.rotor_diameter_m**2
    assert only["cp"] == pytest.approx(only["power_mw"] * 1e6 / (swept * 8.0**3))
    assert len(curve["table"]) == len(model.curve)
    assert all(p.read_bytes() == original for p, original in source_hashes.items())


def test_cell_energy_keeps_one_shared_power_and_flags_farm_allocation(tmp_path: Path) -> None:
    from test_energy import SITES, farms_case, write_run

    from owstudio.core.energy.summary import run_energy

    case = farms_case({"A": SITES["A"], "B": SITES["A"]})
    write_run(tmp_path, case, {"A": 0.8}, control=True)
    result = run_energy(tmp_path, case)
    assert len(result["cells"]) == 1
    cell = result["cells"][0]
    assert cell["shared"] is True
    assert cell["farms"] == ["A", "B"] and cell["turbines"] == 2
    assert cell["energy_mwh"] == pytest.approx(0.8)
    assert sum(row["energy_mwh"] for row in result["farms"]) == pytest.approx(cell["energy_mwh"])


def test_outputs_are_found_below_the_chosen_folder_and_shown_by_folder(
    tmp_path: Path, reference_case: Case
) -> None:
    """Choosing the folder of the calculations finds the only export below it; two exports below
    are named instead of guessing; the preview lists the folders of what will be imported."""
    case = reference_case.model_copy(deep=True)
    case.input_source = "era5"
    case.period.interval_seconds = 3600
    case.period.start, case.period.end = datetime(2025, 1, 31, 23), datetime(2025, 2, 1, 1)
    case.windows, case.spin_up_hours = Windows(useful_hours=72), 12
    calculations = tmp_path / "calculs"
    returned_export(calculations / "Test-WRF", case)
    client = make_client(tmp_path / "application")
    case_id = client.post("/api/cases", json=case.model_dump(mode="json")).json()["id"]
    url = f"/api/cases/{case_id}/results/import/preview"
    preview = client.post(
        url, json={"folder": str(calculations), "control_folder": None, "mode": "copy"}
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert Path(body["folder"]) == (calculations / "Test-WRF" / "wrf").resolve()
    tree = body["tree"]
    assert tree["files"] == body["files"] and tree["bytes"] == body["bytes"]
    assert any(f["path"] == "wrf" and f["first"].startswith("wrfout_d") for f in tree["folders"])
    returned_export(calculations / "Other-WRF", case)
    several = client.post(
        url, json={"folder": str(calculations), "control_folder": None, "mode": "copy"}
    )
    assert several.status_code == 422 and "Other-WRF" in several.text and "Test-WRF" in several.text
