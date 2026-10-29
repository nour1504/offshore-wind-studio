"""The application on Linux: its own window when the system allows it, else the browser.

The interface is served on 127.0.0.1 by the application itself. Then, in this order:

1. a GTK window (WebKitGTK) drawn by the system's own Python, if it has the GTK and WebKit2
   bindings (most desktop Linux do): ``data/linux/window.py``;
2. a Chrome, Chromium, Edge or Brave "application" window (``--app``: no tabs nor address bar),
   with its own profile in the settings folder;
3. the default browser. The page then tells the server it is open (heartbeat); the server stops
   once no page has been open for a while and nothing runs, or when the user clicks Quit.

Nothing of the system is bundled for the window: when none of these exists, the browser remains.
The PyInstaller bundle sets LD_LIBRARY_PATH to its own libraries; system programs started from
here (Python, browsers, the engine's shells) get the original environment back.
"""

import logging
import os
import shutil
import subprocess
import sys
import time
from importlib import resources
from pathlib import Path
from typing import Any

BROWSERS = (
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
    "microsoft-edge", "microsoft-edge-stable", "brave-browser",
)  # fmt: skip
# Browser mode: the server stops this long after the last open page said so
QUIET_SECONDS = 90.0
# ... or this long after start if no page ever opened (no browser could be started)
FIRST_PAGE_SECONDS = 600.0

log = logging.getLogger("owstudio.desktop")


def system_environment(
    environ: dict[str, str] | None = None, frozen: bool | None = None
) -> dict[str, str]:
    """The environment for system programs: without the bundle's own library path."""
    env = dict(os.environ if environ is None else environ)
    if getattr(sys, "frozen", False) if frozen is None else frozen:
        original = env.pop("LD_LIBRARY_PATH_ORIG", None)
        if original:
            env["LD_LIBRARY_PATH"] = original
        else:
            env.pop("LD_LIBRARY_PATH", None)
    return env


def restore_system_environment() -> None:
    """Child processes (engine shells, browsers) must not load the bundle's libraries."""
    clean = system_environment()
    for name in ("LD_LIBRARY_PATH", "LD_LIBRARY_PATH_ORIG"):
        os.environ.pop(name, None)
        if name in clean:
            os.environ[name] = clean[name]


def has_display(env: dict[str, str]) -> bool:
    return bool(env.get("DISPLAY") or env.get("WAYLAND_DISPLAY"))


def window_helper() -> Path:
    return Path(str(resources.files("owstudio.data") / "linux" / "window.py"))


def gtk_window(url: str, env: dict[str, str]) -> list[str] | None:
    """The system Python's GTK window, if its GTK and WebKit2 bindings answer."""
    python = shutil.which("python3", path=env.get("PATH"))
    if python is None:
        return None
    try:
        probe = subprocess.run(
            [python, str(window_helper()), "--probe"], env=env, capture_output=True, timeout=30,
            check=False,
        )  # fmt: skip
    except (OSError, subprocess.TimeoutExpired):
        return None
    return [python, str(window_helper()), url] if probe.returncode == 0 else None


def app_window(url: str, profile: Path, env: dict[str, str]) -> list[str] | None:
    """A Chromium-family browser as an application window, with its own profile."""
    for name in BROWSERS:
        browser = shutil.which(name, path=env.get("PATH"))
        if browser:
            return [
                browser, f"--app={url}", f"--user-data-dir={profile}", "--no-first-run",
                "--no-default-browser-check", "--disable-sync", "--window-size=1440,900",
            ]  # fmt: skip
    return None


def window_commands(url: str, profile: Path, env: dict[str, str]) -> list[list[str]]:
    """The windows to try, best first; none without a graphical session."""
    if not has_display(env):
        return []
    return [command for command in (gtk_window(url, env), app_window(url, profile, env)) if command]


def open_browser(url: str, env: dict[str, str]) -> bool:
    opener = shutil.which("xdg-open", path=env.get("PATH"))
    if opener and has_display(env):
        try:
            subprocess.Popen([opener, url], env=env, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)  # fmt: skip
            return True
        except OSError:
            pass
    import webbrowser

    return webbrowser.open(url)


def browser_finished(app: Any, started: float, now: float) -> bool:
    """Browser mode: the user quit, or no page is open any more and nothing runs."""
    if app.quit_requested.is_set():
        return True
    if app.busy():
        return False
    if app.last_seen is None:
        return now - started > FIRST_PAGE_SECONDS
    return bool(now - app.last_seen > QUIET_SECONDS)


def run(url: str, app: Any, settings_dir: Path, server: Any) -> int:
    """Shows the interface served at ``url`` until it is closed; the caller stops the server."""
    env = system_environment()
    for command in window_commands(url, settings_dir / "browser-window", env):
        app.mode = "window"
        log.info("Opening the window: %s", command[0])
        started = time.monotonic()
        try:
            window = subprocess.run(command, env=env, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.PIPE, check=False)  # fmt: skip
        except OSError as error:
            log.warning("Window could not start: %s", error)
            continue
        # A window that fails at once (missing library, no display access) leaves the next way
        if window.returncode != 0 and time.monotonic() - started < 10:
            log.warning("Window failed: %s", window.stderr.decode(errors="replace")[-2000:])
            continue
        return 0
    app.mode = "browser"
    print(f"Offshore Wind Studio : {url}", flush=True)
    if not open_browser(url, env):
        print("Ouvrez cette adresse dans votre navigateur.", flush=True)
    started = time.monotonic()
    while server.started or time.monotonic() - started < 30:
        if browser_finished(app, started, time.monotonic()):
            break
        time.sleep(2)
    return 0


def error_box(message: str) -> None:
    """A startup error the user can see without a terminal (zenity, kdialog, notification)."""
    env = system_environment()
    for command in (
        ["zenity", "--error", "--title=Offshore Wind Studio", f"--text={message}"],
        ["kdialog", "--title", "Offshore Wind Studio", "--error", message],
        ["notify-send", "Offshore Wind Studio", message],
    ):
        if shutil.which(command[0], path=env.get("PATH")):
            try:
                subprocess.run(command, env=env, check=False, timeout=600)
                return
            except (OSError, subprocess.TimeoutExpired):
                continue
    print(message, file=sys.stderr)
