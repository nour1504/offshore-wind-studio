"""Compute profiles, settings of older versions, shells and the check of an installation."""

import sys
from pathlib import Path

import pytest
from helpers import wsl_profile

from owstudio.core.engine import commands
from owstudio.core.engine.profiles import ComputeProfile
from owstudio.core.engine.shells import WslShell, windows_to_wsl

# ------------------------------------------------------------------ profiles


def test_profile_reports_what_is_missing() -> None:
    profile = ComputeProfile(id="empty", name="Empty", kind="wsl")
    missing = profile.missing()
    assert "WRF directory not set" in missing and "WSL distribution not set" in missing
    assert wsl_profile().missing() == []
    windows = wsl_profile()
    windows.install.geog_dir = "C:\\WPS_GEOG"
    assert any("absolute Linux path" in m for m in windows.missing())
    home = wsl_profile()
    home.install.geog_dir = "~/WPS_GEOG"  # namelist.wps cannot expand ~
    assert any("geography directory must be an absolute" in m for m in home.missing())


def test_settings_without_the_former_container_profiles(tmp_path: Path) -> None:
    """A settings file of an older version with a container profile still loads, without it."""
    from owstudio.core.settings import load_settings

    path = tmp_path / "settings.json"
    path.write_text(
        '{"profiles": [{"id": "old", "name": "Old", "kind": "docker"},'
        ' {"id": "pc", "name": "PC", "kind": "wsl", "wsl_distro": "Ubuntu", "docker": null}],'
        ' "default_profile": "old"}',
        encoding="utf-8",
    )
    settings = load_settings(path)
    assert [p.id for p in settings.profiles] == ["pc"] and settings.default_profile != "old"


def test_settings_saved_with_a_byte_order_mark(tmp_path: Path) -> None:
    """Notepad or PowerShell may start the file with a BOM: it still loads."""
    from owstudio.core.settings import load_settings

    path = tmp_path / "settings.json"
    path.write_bytes(b"\xef\xbb\xbf" + b'{"language": "fr"}')
    assert load_settings(path).language == "fr"


# -------------------------------------------------------------------- shells


def test_shell_command_lines() -> None:
    # --exec: the script reaches bash untouched (no expansion by WSL's default shell)
    assert WslShell("Ubuntu").command("echo $HOME") == [
        "wsl.exe",
        "-d",
        "Ubuntu",
        "--exec",
        "bash",
        "-lc",
        "echo $HOME",
    ]
    assert WslShell("OffshoreWindStudio-WRF", "owstudio").command("ls")[3:6] == [
        "-u",
        "owstudio",
        "--exec",
    ]


@pytest.mark.skipif(sys.platform != "win32", reason="WSL reads Windows paths on Windows only")
def test_windows_paths_seen_from_wsl() -> None:
    assert windows_to_wsl(Path("C:/Users/me/data")) == "/mnt/c/Users/me/data"
    assert windows_to_wsl(Path("D:/WRF data/x")) == "/mnt/d/WRF data/x"
    # Found with a relative settings path: the first folder was dropped and WSL read its own cwd
    assert windows_to_wsl(Path(".qa/kits")) == windows_to_wsl(Path.cwd() / ".qa" / "kits")
    assert windows_to_wsl(Path(".qa/kits")).startswith("/mnt/")


# ------------------------------------------------------------- installation check


def test_verify_output_is_parsed() -> None:
    checks = commands.parse_verify("ok\twrf.exe\tfound\nnoise\nfail\tGeography\tmissing: /x\n")
    assert [c["status"] for c in checks] == ["ok", "fail"]


@pytest.mark.skipif(sys.platform == "win32", reason="the check runs under Linux")
def test_verify_finds_the_installation_below_the_folders_given(tmp_path: Path) -> None:
    """A profile whose folders are one level too high (the engine root, the folder above the
    geography) is checked on what is below them, as the exported scripts use it."""
    import subprocess

    from owstudio.core.engine.profiles import EngineInstall

    root = tmp_path / "moteur"
    for program in (
        "WRF/main/wrf.exe",
        "WRF/main/real.exe",
        "WPS/geogrid.exe",
        "WPS/ungrib.exe",
        "WPS/metgrid.exe",
    ):
        (root / program).parent.mkdir(parents=True, exist_ok=True)
        (root / program).write_text("#!/bin/sh\n")
        (root / program).chmod(0o755)
    (root / "WRF" / "run").mkdir()
    (root / "WRF" / "run" / "README.namelist").write_text("")
    geography = tmp_path / "geog" / "WPS_GEOG_LOW_RES" / "topo_gmted2010_5m"
    geography.mkdir(parents=True)
    (geography / "index").write_text("")
    profile = ComputeProfile(
        id="pc",
        name="PC",
        kind="local",
        install=EngineInstall(
            wrf_dir=str(root),
            wps_dir=str(root),
            geog_dir=str(tmp_path / "geog"),
            input_dir=str(tmp_path / "donnees"),
        ),
    )
    done = subprocess.run(
        ["bash", "-c", commands.verify_script(profile)], check=False, capture_output=True, text=True
    )
    checks = {c["label"]: c for c in commands.parse_verify(done.stdout)}
    assert checks["wrf.exe"]["status"] == "ok" and checks["geogrid.exe"]["status"] == "ok"
    assert checks["WRF"]["detail"].endswith("moteur/WRF") and checks["WPS"]["detail"].endswith(
        "moteur/WPS"
    )
    assert (
        checks["Geography"]["status"] == "ok"
        and "WPS_GEOG_LOW_RES" in checks["Geography"]["detail"]
    )
    assert "low" in checks["Geography"]["detail"]
