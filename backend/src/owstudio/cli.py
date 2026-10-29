"""Command line: ``owstudio serve`` (server), ``owstudio desktop`` (window), ``owstudio run``.
On Linux, ``desktop`` opens a system window or the browser (owstudio.desktop_linux).

Everything the application needs at run time (built interface, catalogues, schemas, examples,
documentation) is inside the owstudio package, so the same entry points work from the
development folder, from an installed wheel and from the Windows installer.
"""

import argparse
import sys
import threading
import time
from importlib import resources
from pathlib import Path

from owstudio.core.i18n import tr
from owstudio.core.settings import SETTINGS_FILE


def interface_dir() -> Path | None:
    """The built browser interface shipped inside the package, if it was built."""
    folder = Path(str(resources.files("owstudio") / "web"))
    return folder if (folder / "index.html").exists() else None


def example_case() -> Path:
    return Path(str(resources.files("owstudio.data") / "examples" / "horns-rev.yaml"))


def build_app(settings_path: Path):  # type: ignore[no-untyped-def]
    from owstudio.api.app import create_app

    return create_app(settings_path, static_dir=interface_dir(), example=example_case())


def _serve(args: argparse.Namespace) -> int:
    import uvicorn

    app = build_app(args.settings)
    host = "0.0.0.0" if args.network else "127.0.0.1"
    uvicorn.run(app, host=host, port=args.port, log_level="warning")
    return 0


def _free_port() -> int:
    import socket

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _log_to_file(settings_path: Path = SETTINGS_FILE) -> Path:
    """The installed application has no console: messages and errors go to a log file in the
    settings folder (shown in Settings), rotated at 5 MB."""
    import logging
    from logging.handlers import RotatingFileHandler

    folder = settings_path.parent / "logs"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "owstudio.log"
    handler = RotatingFileHandler(path, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    # Windowed executables have no standard streams; libraries writing to them must not fail
    if sys.stdout is None or sys.stderr is None:
        stream = path.with_name("output.log").open("a", encoding="utf-8")
        sys.stdout = sys.stdout or stream
        sys.stderr = sys.stderr or stream
    return path


def _desktop(args: argparse.Namespace) -> int:
    """The application in its own window: a local server and an embedded browser view."""
    import logging
    import urllib.request

    import uvicorn

    log = _log_to_file(args.settings)
    logging.getLogger("owstudio").info("Starting the desktop application")

    port = _free_port()
    application = build_app(args.settings)
    server = uvicorn.Server(
        uvicorn.Config(
            application,
            host="127.0.0.1",
            port=port,
            log_level="warning",
            log_config=None,
        )
    )
    threading.Thread(target=server.run, daemon=True).start()
    url = f"http://127.0.0.1:{port}/"
    healthy = False
    for _ in range(100):
        try:
            with urllib.request.urlopen(url + "api/health", timeout=1):
                healthy = True
            break
        except OSError:
            if not server.started and server.should_exit:
                break
            time.sleep(0.1)
    if not healthy:
        server.should_exit = True
        # The application has read the settings: their language is the default one
        _desktop_error(
            tr(
                f"The local server did not start. See the log: {log}",
                f"Le serveur local n'a pas démarré. Consultez le journal : {log}",
            )
        )
        return 1
    if sys.platform.startswith("linux"):
        from owstudio import desktop_linux

        try:
            return desktop_linux.run(url, application.state.owstudio, args.settings.parent, server)
        finally:
            server.should_exit = True
    application.state.owstudio.mode = "window"
    try:
        import webview
    except ImportError:
        import webbrowser

        webbrowser.open(url)
        while server.started:
            time.sleep(1)
        return 0
    # Paths are chosen in the folder tree of the interface, the same in a browser: no native
    # dialog is offered to the page
    webview.create_window(
        "Offshore Wind Studio",
        url,
        width=1440,
        height=900,
        min_size=(1024, 700),
    )
    # Downloads (engine kit, CSV, PDF and MP4 exports) are cancelled by default in pywebview;
    # allowed, each one opens Windows' "Save as" dialog in the Downloads folder
    webview.settings["ALLOW_DOWNLOADS"] = True
    try:
        webview.start(gui="edgechromium" if sys.platform == "win32" else None)
    except Exception:
        logging.getLogger("owstudio").exception("Desktop window failed")
        _desktop_error(
            tr(
                "The window cannot open. On Windows, install Microsoft Edge WebView2 Runtime "
                "(Evergreen) and .NET Framework 4.8. "
                f"Log: {log}\nhttps://developer.microsoft.com/microsoft-edge/webview2/",
                "Impossible d'ouvrir la fenêtre. Sous Windows, installez Microsoft Edge WebView2 "
                "Runtime (Evergreen) et .NET Framework 4.8. "
                f"Journal : {log}\nhttps://developer.microsoft.com/microsoft-edge/webview2/",
            )
        )
        return 1
    finally:
        server.should_exit = True
    return 0


def _desktop_error(message: str) -> None:
    """Windowed builds have no terminal; display an actionable startup error."""
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, "Offshore Wind Studio", 0x10)
    elif sys.platform.startswith("linux"):
        from owstudio.desktop_linux import error_box

        error_box(message)
    else:
        print(message, file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="owstudio")
    parser.add_argument("--settings", type=Path, default=SETTINGS_FILE, help="settings file")
    commands = parser.add_subparsers(dest="command")

    serve = commands.add_parser("serve", help="Start the application server (open it in a browser)")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--network", action="store_true", help="Listen on the network (server mode)")

    commands.add_parser("desktop", help="Open the application in its own window (default)")

    args = parser.parse_args(argv)
    if getattr(sys, "frozen", False):
        _log_to_file(args.settings)
        if sys.platform.startswith("linux"):
            # The bundle's library path must not leak into the system programs it starts
            from owstudio.desktop_linux import restore_system_environment

            restore_system_environment()
    if args.command == "serve":
        return _serve(args)
    return _desktop(args)
