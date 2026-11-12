"""The Linux version: settings folder, "this computer" engine, window or browser, browser mode.

These checks run on Windows and Linux alike: platforms are passed in, not detected.
"""

import ast
import stat
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from helpers import make_client

from owstudio import desktop_linux
from owstudio.api.routes_system import platform_name
from owstudio.core.engine import local_setup
from owstudio.core.settings import _settings_dir


def test_settings_folder_per_platform(tmp_path: Path) -> None:
    assert _settings_dir("win32", {"APPDATA": str(tmp_path / "Roaming")}, tmp_path) == (
        tmp_path / "Roaming" / "OffshoreWindStudio"
    )
    linux = _settings_dir("linux", {}, tmp_path)
    assert linux == tmp_path / ".config" / "OffshoreWindStudio"
    assert _settings_dir("linux", {"XDG_CONFIG_HOME": str(tmp_path / "xdg")}, tmp_path) == (
        tmp_path / "xdg" / "OffshoreWindStudio"
    )
    assert _settings_dir("darwin", {}, tmp_path) == tmp_path / ".owstudio"


def test_former_linux_settings_are_copied_once_never_moved(tmp_path: Path) -> None:
    former = tmp_path / ".owstudio"
    former.mkdir()
    (former / "settings.json").write_text('{"language": "fr"}', encoding="utf-8")
    folder = _settings_dir("linux", {}, tmp_path)
    assert (folder / "settings.json").read_text(encoding="utf-8") == '{"language": "fr"}'
    assert (former / "settings.json").exists()
    (folder / "settings.json").write_text('{"language": "en"}', encoding="utf-8")
    _settings_dir("linux", {}, tmp_path)
    assert (folder / "settings.json").read_text(encoding="utf-8") == '{"language": "en"}'


def test_this_computer_is_the_linux_itself(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(local_setup.sys, "platform", "linux")
    status = local_setup.status()
    assert status["native"] and status["available"] and status["ready"]
    assert status["managed_exists"] is False and status["distributions"] == []


def test_bundle_library_path_is_not_given_to_system_programs() -> None:
    bundle = {"LD_LIBRARY_PATH": "/tmp/_MEI", "LD_LIBRARY_PATH_ORIG": "/usr/local/lib", "A": "1"}
    assert desktop_linux.system_environment(bundle, frozen=True) == {
        "LD_LIBRARY_PATH": "/usr/local/lib", "A": "1",
    }  # fmt: skip
    assert desktop_linux.system_environment({"LD_LIBRARY_PATH": "/tmp/_MEI"}, frozen=True) == {}
    assert desktop_linux.system_environment({"LD_LIBRARY_PATH": "/x"}, frozen=False) == {
        "LD_LIBRARY_PATH": "/x"
    }


def _fake_program(folder: Path, name: str, code: int = 0) -> None:
    path = folder / name
    path.write_text(f"#!/bin/sh\nexit {code}\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    (folder / f"{name}.bat").write_text(f"@exit /b {code}\n", encoding="utf-8")


def test_window_or_browser_choice(tmp_path: Path) -> None:
    url = "http://127.0.0.1:5000/"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    env = {"PATH": str(bin_dir), "PATHEXT": ".BAT"}
    # Without a graphical session, no window is tried: the address is given for a browser
    assert desktop_linux.window_commands(url, tmp_path / "profile", env) == []
    env["DISPLAY"] = ":0"
    # No system Python with GTK, no Chromium-family browser: browser mode
    assert desktop_linux.window_commands(url, tmp_path / "profile", env) == []
    _fake_program(bin_dir, "chromium")
    [command] = desktop_linux.window_commands(url, tmp_path / "profile", env)
    assert Path(command[0]).stem == "chromium" and f"--app={url}" in command
    assert f"--user-data-dir={tmp_path / 'profile'}" in command


def test_browser_mode_stops_when_no_page_is_left() -> None:
    app = SimpleNamespace(quit_requested=threading.Event(), last_seen=None, busy=lambda: False)
    assert not desktop_linux.browser_finished(app, 0.0, 100.0)
    assert desktop_linux.browser_finished(app, 0.0, desktop_linux.FIRST_PAGE_SECONDS + 1)
    app.last_seen = 100.0
    assert not desktop_linux.browser_finished(app, 0.0, 150.0)
    assert desktop_linux.browser_finished(app, 0.0, 100.0 + desktop_linux.QUIET_SECONDS + 1)
    app.busy = lambda: True
    assert not desktop_linux.browser_finished(app, 0.0, 10_000.0)
    app.busy = lambda: False
    app.last_seen = 10_000.0
    app.quit_requested.set()
    assert desktop_linux.browser_finished(app, 0.0, 10_001.0)


def test_health_heartbeat_and_quit(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    health = client.get("/api/health").json()
    assert health["mode"] == "server"
    assert health["platform"] == platform_name() and health["platform"] in ("windows", "linux")
    assert client.post("/api/system/heartbeat").json() == {"busy": False}
    app = client.app.state.owstudio  # type: ignore[attr-defined]
    assert app.last_seen is not None
    # Only the browser mode can be closed from the interface
    assert client.post("/api/system/quit").status_code == 409
    app.mode = "browser"
    assert client.post("/api/system/quit").json() == {"quitting": True}
    assert app.quit_requested.is_set()


def test_window_helper_is_shipped_and_old_python_compatible() -> None:
    helper = desktop_linux.window_helper()
    assert helper.is_file() and (helper.parent / "owstudio.png").is_file()
    ast.parse(helper.read_text(encoding="utf-8"), feature_version=(3, 7))
