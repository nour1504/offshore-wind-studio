"""Projects exported to a file and imported back (Projects page)."""

import io
import json
import zipfile
from pathlib import Path
from urllib.parse import unquote

from helpers import make_client


def _first_case(client) -> str:  # type: ignore[no-untyped-def]
    """A saved project: the example's settings under a name with accents."""
    case = client.get("/api/blank-case").json()
    case["name"] = "Étude Normandie"
    return str(client.post("/api/cases", json=case).json()["id"])


def test_export_then_import_gives_the_same_project(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    case_id = _first_case(client)
    original = client.get(f"/api/cases/{case_id}").json()
    exported = client.get(f"/api/cases/{case_id}/export")
    assert exported.status_code == 200 and exported.headers["content-type"] == "application/zip"
    disposition = exported.headers["content-disposition"]
    assert ".owstudio.zip" in disposition and "filename*=UTF-8''" in disposition
    with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
        assert sorted(archive.namelist()) == ["case.yaml", "project.json"]
        about = json.loads(archive.read("project.json"))
    assert about["format"] == "offshore-wind-studio-project" and about["name"] == original["name"]

    imported = client.post(
        "/api/cases/import", params={"filename": "x.owstudio.zip"}, content=exported.content
    )
    assert imported.status_code == 201
    body = imported.json()
    # Same name already in the workspace: kept apart, nothing replaced
    assert body["id"] != case_id and body["name"] == f"{original['name']} (imported)"
    copy = client.get(f"/api/cases/{body['id']}").json()
    assert {**copy, "name": original["name"]} == original
    assert client.get(f"/api/cases/{case_id}").json() == original


def test_import_a_case_yaml_and_report_missing_own_files(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    case = client.get(f"/api/cases/{_first_case(client)}").json()
    case["name"] = "Projet d'un collègue"
    case["input_source"] = "grib"
    case["grib"] = {
        "folder": "D:/Données/ERA5 introuvable",
        "pattern": "*.grib",
        "vtable": "Vtable.ECMWF",
    }
    import yaml

    text = yaml.safe_dump(case, allow_unicode=True).encode("utf-8")
    imported = client.post("/api/cases/import", params={"filename": "case.yaml"}, content=text)
    assert imported.status_code == 201, imported.text
    assert imported.json()["name"] == "Projet d'un collègue"
    assert imported.json()["missing_folders"] == ["D:/Données/ERA5 introuvable"]
    export = client.get(f"/api/cases/{imported.json()['id']}/export")
    assert (
        unquote(export.headers["content-disposition"].split("UTF-8''")[1])
        == "Projet d-un collègue.owstudio.zip"
    )


def test_invalid_files_are_refused_without_creating_anything(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    before = len(client.get("/api/cases").json())
    for filename, content in (
        ("notes.txt", b"hello"),
        ("case.yaml", b"- not\n- a project\n"),
        ("case.yaml", b"name: [unclosed"),
        ("case.yaml", b"name: Incomplete\n"),
    ):
        answer = client.post("/api/cases/import", params={"filename": filename}, content=content)
        assert answer.status_code == 422, (filename, content)
    empty = io.BytesIO()
    with zipfile.ZipFile(empty, "w") as archive:
        archive.writestr("readme.txt", "no project here")
    assert (
        client.post(
            "/api/cases/import", params={"filename": "x.zip"}, content=empty.getvalue()
        ).status_code
        == 422
    )
    assert len(client.get("/api/cases").json()) == before
