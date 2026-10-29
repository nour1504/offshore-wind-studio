from pathlib import Path
from typing import Any

import pytest
from helpers import make_client, wsl_profile


def test_create_list_get_save_and_delete(tmp_path: Path, reference: dict[str, Any]) -> None:
    client = make_client(tmp_path)
    created = client.post("/api/cases", json=reference)
    assert created.status_code == 201
    case_id = created.json()["id"]

    listed = client.get("/api/cases").json()
    assert [c["id"] for c in listed] == [case_id] and listed[0]["last_run_state"] == "idle"
    case = client.get(f"/api/cases/{case_id}").json()
    assert case["name"] == "Horns Rev reference"
    assert case["farms"][0]["id"] == "main" and len(case["farms"][0]["turbines"]) == 80

    case["description"] = "edited from the interface"
    assert client.put(f"/api/cases/{case_id}", json=case).status_code == 200
    assert client.get(f"/api/cases/{case_id}").json()["description"] == "edited from the interface"
    assert client.delete(f"/api/cases/{case_id}").status_code == 204
    assert client.get("/api/cases").json() == []


def test_invalid_case_is_rejected_with_reason(tmp_path: Path, reference: dict[str, Any]) -> None:
    client = make_client(tmp_path)
    reference["grid"]["domains"][1]["i_parent_start"] = 90
    response = client.post("/api/cases", json=reference)
    assert response.status_code == 422
    assert "extends beyond its parent" in response.text


def test_unknown_case_is_404(tmp_path: Path) -> None:
    assert make_client(tmp_path).get("/api/cases/nope").status_code == 404


def test_geometry_has_domains_and_turbines(tmp_path: Path, reference: dict[str, Any]) -> None:
    features = make_client(tmp_path).post("/api/geometry", json=reference).json()["features"]
    kinds = [f["properties"]["kind"] for f in features]
    assert kinds.count("domain") == 2 and kinds.count("turbine") == 80
    assert features[1]["properties"]["dx"] == 3000


def test_checks_and_namelists_for_unsaved_case(tmp_path: Path, reference: dict[str, Any]) -> None:
    client = make_client(tmp_path)
    reference["physics"]["bl_pbl_physics"] = [1, 1]
    issues = client.post("/api/checks", json=reference).json()
    assert issues[0]["severity"] == "error"
    texts = client.post("/api/namelists", json=reference).json()
    assert texts["namelist.wps"].startswith("&share")
    assert "windfarm_opt = 0, 1" in texts["namelist.input"]


def test_profiles_can_be_saved_without_any_connection(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    profile = wsl_profile().model_dump()
    saved = client.put("/api/profiles/wsl-test", json=profile).json()
    assert [p["id"] for p in saved["profiles"]] == ["wsl-test"] and saved["profiles"][0][
        "missing"
    ] == []
    assert client.get("/api/settings").json()["default_profile"] == "wsl-test"
    assert client.delete("/api/profiles/wsl-test").json()["profiles"] == []


def test_storage_lists_every_location(tmp_path: Path) -> None:
    usage = make_client(tmp_path).get("/api/storage").json()
    keys = [loc["key"] for loc in usage["locations"]]
    assert keys == ["cases", "input", "observations", "exports", "videos", "reports", "jobs"]
    assert usage["data_root"] == str(tmp_path / "data")


def test_the_old_input_folder_becomes_the_map_cache(tmp_path: Path) -> None:
    from owstudio.core.storage import Storage

    (tmp_path / "input" / "basemap").mkdir(parents=True)
    storage = Storage(tmp_path)
    storage.ensure()
    assert storage.input_root == tmp_path / "cache"
    assert (tmp_path / "cache" / "basemap").is_dir() and not (tmp_path / "input").exists()


def test_turbine_catalogue_has_curves_and_metrics(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    catalog = client.get("/api/turbines/catalog").json()
    names = [entry["name"] for entry in catalog]
    assert "IEA Reference 15MW 240" in names and "WRF generic 2 MW" in names
    iea = next(e for e in catalog if e["id"] == "iea-reference-15mw-240")
    assert iea["turbine"]["hub_height_m"] == 150
    assert 0.4 < iea["max_cp"] < 16 / 27
    assert iea["specific_power"] == pytest.approx(15e6 / (3.14159265 * 120**2), rel=1e-6)
    table = client.post("/api/turbines/wrf-table", json=iea["turbine"]).text
    assert table.splitlines()[1] == "150 240 0.1 15"


def test_coordinates_endpoint_reads_pasted_text(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    response = client.post(
        "/api/coordinates/parse", json={"text": "Easting;Northing\n423000;6150000", "utm_zone": 32}
    ).json()
    assert response["points"][0]["lat"] == pytest.approx(55.49, abs=1e-2)
    bad = client.post("/api/coordinates/parse", json={"text": "423000;6150000"})
    assert bad.status_code == 422 and "UTM" in bad.text


def test_structured_namelists_separate_generated_and_overridden(
    tmp_path: Path, reference: dict[str, Any]
) -> None:
    client = make_client(tmp_path)
    reference["namelist_input"] = {"dynamics": {"epssm": 0.2}, "diags": {"p_lev_diags": 1}}
    files = client.post("/api/namelists/structured", json=reference).json()
    namelist = files["namelist.input"]
    assert "epssm" not in namelist["generated"]["dynamics"]
    assert namelist["final"]["dynamics"]["epssm"] == 0.2
    assert list(namelist["final"])[-1] == "diags"
    schema = client.get("/api/namelist/schema").json()
    assert schema["groups"]["dynamics"]["epssm"]["type"] == "real"


def test_a_blank_project_starts_empty_with_the_standard_windows(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    blank = client.get("/api/blank-case").json()
    assert blank["farms"] == [] and blank["turbine_types"] == {}
    assert blank["windows"] == {"useful_hours": 72, "grouping": "month", "restart": False}
    assert blank["spin_up_hours"] == 12 and blank["format_version"] == 2
    assert blank["namelist_input"] == {} and blank["time_series"]["points"] == []
    # Nothing placed yet: no domain, no scheme; what is missing is something to do, not an error
    assert blank["grid"]["domains"] == [] and blank["farm_scheme"] is None
    blank["farms"] = [
        {"id": "f1", "name": "Farm 1", "enabled": True, "properties": {}, "turbines": []}
    ]
    issues = client.post("/api/checks", json=blank).json()
    assert issues and all(i["severity"] == "info" for i in issues)
    assert client.post("/api/geometry", json=blank).status_code == 200
