"""The folder explorer: one folder at a time, roles of the engine folders, checks of the paths."""

import sys
from pathlib import Path

import pytest

from owstudio.core.engine import browse
from owstudio.core.engine.commands import BASH_FIND_BELOW_FUNCTION


def _engine(root: Path) -> None:
    (root / "WRF" / "main").mkdir(parents=True)
    (root / "WRF" / "main" / "wrf.exe").write_text("")
    (root / "WPS" / "geogrid").mkdir(parents=True)
    (root / "WPS" / "geogrid.exe").write_text("")
    (root / "WPS_GEOG" / "topo_gmted2010_5m").mkdir(parents=True)
    (root / "WPS_GEOG" / "topo_gmted2010_5m" / "index").write_text("")
    (root / "env.sh").write_text("")
    (root / "notes.txt").write_text("")


def test_a_folder_lists_its_entries_with_their_role(tmp_path: Path) -> None:
    _engine(tmp_path)
    found = browse.listing("here", None, str(tmp_path))
    assert found["state"] == "ok" and found["role"] == "engine"
    roles = {e["name"]: e["role"] for e in found["entries"]}
    assert roles == {
        "WPS": "wps",
        "WPS_GEOG": "geog",
        "WRF": "wrf",
        "env.sh": None,
        "notes.txt": None,
    }
    # Folders first, then files
    assert [e["kind"] for e in found["entries"]] == ["dir", "dir", "dir", "file", "file"]
    geog = browse.listing("here", None, str(tmp_path / "WPS_GEOG"))
    assert geog["resolutions"] == ["lowres"]
    page = browse.listing("here", None, str(tmp_path), offset=1, limit=2)
    assert page["total"] == 5 and [e["name"] for e in page["entries"]] == ["WPS_GEOG", "WRF"]


def test_a_missing_folder_gives_the_closest_one(tmp_path: Path) -> None:
    found = browse.listing("here", None, str(tmp_path / "a" / "b"))
    assert found["state"] == "missing" and Path(found["nearest"]) == tmp_path
    (tmp_path / "empty").mkdir()
    assert browse.listing("here", None, str(tmp_path / "empty"))["state"] == "empty"


@pytest.mark.skipif(sys.platform == "win32", reason="engine paths are Linux paths")
def test_paths_are_checked_against_what_they_should_hold(tmp_path: Path, monkeypatch) -> None:
    _engine(tmp_path)
    monkeypatch.setattr(browse, "engine_runs_here", lambda profile: True)
    root = tmp_path.as_posix()
    good = {"wrf_dir": f"{root}/WRF", "wps_dir": f"{root}/WPS", "geog_dir": f"{root}/WPS_GEOG"}
    assert browse.check(None, good, ["lowres"]) == {}
    assert browse.check(None, good, ["default"]) == {"geog_dir": "No high resolution"}
    swapped = {"wrf_dir": f"{root}/WPS", "wps_dir": f"{root}/nothing", "geog_dir": f"{root}/WRF"}
    assert browse.check(None, swapped, []) == {
        "wrf_dir": "Not WRF",
        "wps_dir": "Not found",
        "geog_dir": "Not a geography",
    }
    assert browse.needed_resolutions(["default", "lowres", "modis_30s+default", "30s"]) == [
        "default",
        "lowres",
    ]


def test_a_folder_above_the_right_one_is_not_wrong(tmp_path: Path, monkeypatch) -> None:
    """Found twice on the work VM: /app/ows/moteur for WRF, /app/ows/geog for the geography. The
    folder given is accepted when the right one is below it, whatever the names, as the exported
    scripts find it; the folder found is named."""
    _engine(tmp_path / "moteur")
    monkeypatch.setattr(browse, "engine_runs_here", lambda profile: True)
    top = (tmp_path / "moteur").as_posix()
    found: dict[str, str] = {}
    given = {"wrf_dir": top, "wps_dir": top, "geog_dir": top}
    assert browse.check(None, given, ["lowres"], found) == {}
    assert found == {
        "wrf_dir": f"{top}/WRF",
        "wps_dir": f"{top}/WPS",
        "geog_dir": f"{top}/WPS_GEOG",
    }
    assert browse.check(None, {"geog_dir": top}, ["default"]) == {"geog_dir": "No high resolution"}


@pytest.mark.skipif(sys.platform == "win32", reason="bash reads the engine machine")
def test_bash_finds_below_as_python_does(tmp_path: Path) -> None:
    """The engine machine is searched by bash, this computer by Python: the same folder."""
    import subprocess

    _engine(tmp_path / "a b")
    (tmp_path / "a b" / ".hidden" / "main").mkdir(parents=True)
    (tmp_path / "a b" / ".hidden" / "main" / "wrf.exe").write_text("")
    for target in ("main/wrf.exe", "geogrid.exe", "topo_gmted2010_5m/index", "nothing"):
        script = f"{BASH_FIND_BELOW_FUNCTION}\nfind_below '{tmp_path}' '{target}'\n"
        bash = subprocess.run(
            ["bash", "-c", script], check=False, capture_output=True, text=True
        ).stdout.strip()
        assert (bash or None) == browse._find_below_here(str(tmp_path), target)
    assert browse._find_below_here(str(tmp_path), "main/wrf.exe") == f"{tmp_path}/a b/WRF"


@pytest.mark.skipif(sys.platform == "win32", reason="bash reads the engine machine")
def test_bash_reads_a_folder_as_python_does(tmp_path: Path) -> None:
    """A WSL engine may have no Python: its folders are read by bash, with the same result."""
    from owstudio.core.engine.profiles import ComputeProfile

    _engine(tmp_path)
    (tmp_path / "WPS_GEOG" / "topo_gmted2010_30s").mkdir()
    (tmp_path / "WPS_GEOG" / "topo_gmted2010_30s" / "index").write_text("")
    (tmp_path / "loop").symlink_to(tmp_path)
    (tmp_path / "with space é").mkdir()
    local = ComputeProfile(id="here", name="here", kind="local")
    for folder in (tmp_path, tmp_path / "WPS_GEOG", tmp_path / "missing" / "x"):
        python = browse._scan_here(str(folder), 0, 50)
        bash = browse._scan_engine(local, str(folder), 0, 50)
        assert bash == python
    entries = browse._scan_engine(local, str(tmp_path), 0, 50)["entries"]
    assert {e["name"]: e.get("loop") for e in entries}["loop"] is True


def test_a_destination_is_on_the_engine_machine_inside_its_distribution() -> None:
    from owstudio.core.engine.profiles import ComputeProfile

    wsl = ComputeProfile(id="w", name="w", kind="wsl", wsl_distro="Engine")
    assert browse.same_machine(wsl, r"\\wsl.localhost\Engine\home\me")
    assert browse.same_machine(wsl, "//wsl$/engine/")
    assert not browse.same_machine(wsl, r"C:\Calculs")
    assert not browse.same_machine(wsl, r"\\wsl.localhost\Other\home")
    assert not browse.same_machine(wsl, "")


def test_an_engine_that_cannot_be_reached_is_said_so(monkeypatch) -> None:
    """No fake content when the engine machine does not answer: the state is "offline"."""
    from owstudio.core.engine import shells
    from owstudio.core.engine.profiles import ComputeProfile

    monkeypatch.setattr(shells, "execute", lambda *a, **k: shells.Completed(127, "", "not found"))
    wsl = ComputeProfile(id="w", name="w", kind="wsl", wsl_distro="Gone")
    found = browse.listing("engine", wsl, "/home")
    assert found["state"] == "offline" and found["entries"] == []
    assert browse.check(wsl, {"wps_dir": "/home/WPS"}, []) == {}


def test_the_explorer_shows_the_machine_of_the_profile_being_edited(
    tmp_path: Path, monkeypatch
) -> None:
    """A profile's paths are chosen among the folders of its own machine, not the default one's."""
    from helpers import make_client, wsl_profile

    from owstudio.core.engine import shells
    from owstudio.core.engine.profiles import ComputeProfile

    monkeypatch.setattr(shells, "execute", lambda *a, **k: shells.Completed(127, "", "not found"))
    _engine(tmp_path / "engine")
    local = ComputeProfile(id="here", name="Here", kind="local")
    client = make_client(tmp_path, profiles=[wsl_profile(), local])
    folder = str(tmp_path / "engine")
    assert (
        client.get("/api/fs/list", params={"machine": "engine", "path": folder}).json()["state"]
        == "offline"
    )
    found = client.get(
        "/api/fs/list", params={"machine": "engine", "path": folder, "profile": "here"}
    ).json()
    assert {"WRF", "WPS", "WPS_GEOG"} <= {e["name"] for e in found["entries"]}


@pytest.mark.skipif(sys.platform == "win32", reason="bash reads the engine machine")
def test_the_engine_machine_is_checked_in_one_call_as_here(tmp_path: Path, monkeypatch) -> None:
    """The three folders of a WSL engine are checked by one bash call, with the same answers as
    the Python check of this computer."""
    from owstudio.core.engine import shells
    from owstudio.core.engine.profiles import ComputeProfile

    _engine(tmp_path / "moteur")
    top = (tmp_path / "moteur").as_posix()
    cases = [
        ({"wrf_dir": top, "wps_dir": f"{top}/WPS", "geog_dir": top}, ["lowres"]),
        ({"wrf_dir": f"{top}/nothing", "wps_dir": f"{top}/WRF", "geog_dir": top}, ["default"]),
        ({"geog_dir": top}, ["default", "lowres"]),
        ({"geog_dir": top}, []),
    ]
    here = {}
    for folders, needed in cases:
        found: dict[str, str] = {}
        local = ComputeProfile(id="l", name="l", kind="local")
        here[str(folders) + str(needed)] = (browse.check(local, folders, needed, found), found)
    calls: list[str] = []
    real_run = shells.LocalShell.run

    def counted(self, script, timeout=None):  # type: ignore[no-untyped-def]
        calls.append(script)
        return real_run(self, script, timeout=timeout)

    monkeypatch.setattr(browse, "engine_runs_here", lambda profile: False)
    monkeypatch.setattr(shells.LocalShell, "run", counted)
    for folders, needed in cases:
        found = {}
        issues = browse.check(
            ComputeProfile(id="l", name="l", kind="local"), folders, needed, found
        )
        assert (issues, found) == here[str(folders) + str(needed)]
    assert len(calls) == len(cases)
    assert here[str(cases[2][0]) + str(cases[2][1])][0] == {"geog_dir": "No high resolution"}
    assert here[str(cases[3][0]) + str(cases[3][1])][0] == {}
