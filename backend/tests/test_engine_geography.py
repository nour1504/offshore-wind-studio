"""The geography of an engine installation never typed by hand: a proxy's 403 told as such, the
NCAR archive sent from this computer, a WPS_GEOG folder already on the target found, and the
choice changed when an installation is resumed."""

import copy
import sys
from pathlib import Path
from typing import Any

import pytest
from helpers import make_client
from test_engine_install import PROBE, FakeJob, FakeTarget, status, target_profile

from owstudio.core.engine import install
from owstudio.core.engine.shells import Completed

BLOCKED = PROBE.replace("https://www2.mmm.ucar.edu fail", "https://www2.mmm.ucar.edu 403")


def test_a_proxy_answering_403_is_named() -> None:
    target = FakeTarget([status("queued")], probe=BLOCKED)
    checked = install.preflight(install.InstallRequest(profile=target_profile()), target)
    network = next(c for c in checked["checks"] if c["key"] == "network")
    assert network["status"] == "fail" and network["detail"] == "www2.mmm.ucar.edu 403"
    assert checked["blocked"] == ["https://www2.mmm.ucar.edu"]
    # The archive sent from this computer: NCAR is no longer needed
    sent = install.preflight(
        install.InstallRequest(profile=target_profile()), target, uploaded={"mandatory-high"}
    )
    assert next(c for c in sent["checks"] if c["key"] == "network")["status"] == "ok"


@pytest.fixture
def small_archives(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """The same catalogue with a 10-byte low-resolution archive."""
    value = copy.deepcopy(install.spec())
    for choice in value["geography"]:
        if choice["id"] == "mandatory-low":
            choice["download_bytes"] = 10
    monkeypatch.setattr(install, "spec", lambda: value)
    return value


def test_the_ncar_archive_is_sent_from_the_browser(tmp_path: Path, small_archives: Any) -> None:
    client = make_client(tmp_path)
    assert client.get("/api/engine/geography/uploads").json() == {}
    wrong = client.put("/api/engine/geography/mandatory-low", content=b"123")
    assert wrong.status_code == 422
    sent = client.put("/api/engine/geography/mandatory-low", content=b"0123456789")
    assert sent.status_code == 200 and sent.json() == {"mandatory-low": 10}
    assert client.put("/api/engine/geography/existing", content=b"x").status_code == 404


def test_the_archive_sent_goes_to_the_target_before_the_worker(tmp_path: Path) -> None:
    archive = tmp_path / "geog_low_res_mandatory.tar.gz"
    archive.write_bytes(b"archive")
    target = FakeTarget([status("queued")])
    body = install.InstallRequest(profile=target_profile(), geography="mandatory-low")
    install.begin(
        body, tmp_path / "receipts", tmp_path / "kits", FakeJob(), target, archive=archive
    )
    assert any(
        remote.endswith("/downloads") and names == [archive.name]
        for _, remote, names in target.uploads
    )
    assert not archive.exists()


class Found(FakeTarget):
    def run(self, script: str, timeout: float | None = 600) -> Completed:
        if "topo_gmted2010" in script:
            return Completed(0, "/home/me/WPS_GEOG 30s\n/home/me/WPS_GEOG 5m\n/app/geog 5m\n", "")
        return super().run(script, timeout)


def test_a_geography_already_on_the_target_is_found() -> None:
    found = install.find_geography(Found([status("queued")]))
    assert found == [
        {"path": "/app/geog", "resolutions": ["lowres"]},
        {"path": "/home/me/WPS_GEOG", "resolutions": ["default", "lowres"]},
    ]


def test_a_resumption_may_change_the_geography() -> None:
    receipt = {
        "root": "/home/me/engine",
        "profile": target_profile().model_dump(mode="json"),
        "options": {"geography": "mandatory-high", "geog_path": "", "extras": [], "jobs": 4},
    }
    same = install.resume_request(receipt)
    assert same.geography == "mandatory-high"
    changed = install.resume_request(
        receipt, {"geography": "existing", "geog_path": "/home/me/WPS_GEOG", "extras": None}
    )
    assert changed.geography == "existing" and changed.geog_path == "/home/me/WPS_GEOG"


@pytest.mark.skipif(sys.platform == "win32", reason="bash of Linux")
def test_the_search_finds_a_real_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from owstudio.core.engine.shells import LocalShell

    (tmp_path / "x" / "WPS_GEOG" / "topo_gmted2010_5m").mkdir(parents=True)
    (tmp_path / "x" / "WPS_GEOG" / "topo_gmted2010_5m" / "index").write_text("")
    monkeypatch.setenv("HOME", str(tmp_path))
    found = install.find_geography(LocalShell())
    assert {"path": f"{tmp_path}/x/WPS_GEOG", "resolutions": ["lowres"]} in found
