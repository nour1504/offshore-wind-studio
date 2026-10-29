"""The copy of the base map kept on disk, used only when the network is not there.

The window loads the base map (OpenFreeMap "Positron": style, vector tiles, fonts, symbols) and the
relief (Terrarium elevation tiles, AWS Open Data) straight from their public servers. It tells
the application which addresses it loaded (POST /api/map/keep) and a background thread keeps a
copy of each on disk. Offline, the window asks for that copy (GET /api/map/style.json and the
files it points to), read from disk only: nothing here downloads while the window waits, so
nothing here can keep the map from showing. Every failure is written in the log with its cause,
and so are the problems the window reports (POST /api/map/problem).

Online requests deliberately bypass this application: proxied tiles that failed became empty
tiles with nothing in the log, and the map could stay blank.
"""

import gzip
import json
import logging
import queue
import re
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from owstudio.api.routes_cases import state
from owstudio.api.state import AppState
from owstudio.core import web
from owstudio.core.i18n import tr
from owstudio.core.method.scene import TERRARIUM_URL

router = APIRouter()
log = logging.getLogger("owstudio.map")

UPSTREAM = "https://tiles.openfreemap.org/"
STYLE_URL = f"{UPSTREAM}styles/positron"
ELEVATION = TERRARIUM_URL.split("{z}")[0]
# The style and the description of the tiles have fixed addresses but change: kept again after a
# week. Tiles, fonts and symbols never change at a given address.
REFRESH_S = 7 * 86400
FOREVER = {"Cache-Control": "public, max-age=31536000, immutable"}
SAFE_PATH = re.compile(r"^[A-Za-z0-9_\-./@ ,]+$")
TILE = re.compile(r"^(\d+)/(\d+)/(\d+)\.png$")
MEDIA = {".pbf": "application/x-protobuf", ".png": "image/png", ".json": "application/json"}
# At most this many addresses waiting to be kept (a long session panning around the world)
MAX_WAITING = 5000


def address(url: str) -> str:
    """`url` written as a request needs it: MapLibre leaves the spaces of the font names."""
    parts = urlsplit(url)
    return parts._replace(path=quote(unquote(parts.path), safe="/@,")).geturl()


def download(url: str) -> bytes:
    """The file at `url`; raises with the cause when it cannot be had whole."""
    request = urllib.request.Request(
        address(url), headers={"User-Agent": "OffshoreWindStudio", "Accept-Encoding": "gzip"}
    )
    with web.urlopen(request, timeout=30) as response:
        data: bytes = response.read()
        encoding = (response.headers.get("Content-Encoding") or "identity").lower()
        if response.status != 200:
            raise ValueError(f"HTTP {response.status}")
    if encoding == "gzip":
        data = gzip.decompress(data)
    elif encoding != "identity":
        raise ValueError(f"unexpected compression {encoding!r}")  # internal
    if not data:
        raise ValueError("empty answer")  # internal
    return data


# Replaced in the tests
fetch = download


def _safe(path: str) -> bool:
    return bool(SAFE_PATH.match(path)) and ".." not in path.split("/") and not path.startswith("/")


def copy_path(app: AppState, url: str) -> Path | None:
    """Where the copy of `url` is kept, or None for an address that is not the base map's."""
    if url.startswith(UPSTREAM):
        return _upstream_copy(app.storage.input("basemap"), url)
    if url.startswith(ELEVATION):
        tile = TILE.match(url[len(ELEVATION) :].split("?")[0])
        if tile:
            z, x, y = tile.groups()
            return app.storage.input("elevation") / z / x / f"{y}.png"
    return None


def _upstream_copy(folder: Path, url: str) -> Path | None:
    """Files under `files/` at their address; the style and the description of the tiles, whose
    addresses have no extension (and would clash with the folder of the tiles: `planet` and
    `planet/<edition>/...`), under `described/` with `.json` added."""
    path = unquote(urlsplit(url).path).lstrip("/")
    if not _safe(path):
        return None
    if "." not in path.rsplit("/", 1)[-1]:
        return folder / "described" / f"{path}.json"
    return folder / "files" / path


def _stale(path: Path) -> bool:
    """Tiles, fonts and symbols are kept once; the style and the description of the tiles are
    kept again after a week."""
    if not path.is_file():
        return True
    return "described" in path.parts and time.time() - path.stat().st_mtime > REFRESH_S


class Keeper:
    """Downloads the addresses given to it, one after the other in a background thread, and keeps
    them on disk. A failure is written in the log once per cause, with how many followed."""

    def __init__(self) -> None:
        self._queue: queue.Queue[tuple[str, Path]] = queue.Queue()
        self._waiting: set[Path] = set()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self.failures: dict[str, int] = {}
        self.kept = 0

    def keep(self, url: str, path: Path) -> bool:
        with self._lock:
            if path in self._waiting or len(self._waiting) >= MAX_WAITING:
                return False
            self._waiting.add(path)
            if self._thread is None or not self._thread.is_alive():
                self._thread = threading.Thread(target=self._work, name="map-copy", daemon=True)
                self._thread.start()
        self._queue.put((url, path))
        return True

    def wait(self) -> None:
        """Until everything given has been kept or has failed (tests)."""
        self._queue.join()

    def _work(self) -> None:
        while True:
            url, path = self._queue.get()
            try:
                data = fetch(url)
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_name(f"{path.name}.{threading.get_ident()}.part")
                temporary.write_bytes(data)
                temporary.replace(path)
                self.kept += 1
            except Exception as error:  # noqa: BLE001 - every cause is logged, none stops the copy
                self._failed(url, error)
            finally:
                with self._lock:
                    self._waiting.discard(path)
                self._queue.task_done()

    def _failed(self, url: str, error: Exception) -> None:
        cause = f"{type(error).__name__}: {error}"
        count = self.failures.get(cause, 0) + 1
        self.failures[cause] = count
        if count == 1:
            log.warning("Base map copy: %s could not be kept (%s)", url, cause)
        elif count in (10, 100, 1000):
            log.warning("Base map copy: %d addresses could not be kept (%s)", count, cause)


keeper = Keeper()


class KeepRequest(BaseModel):
    urls: list[str] = Field(default_factory=list, max_length=1000)


class Problem(BaseModel):
    message: str = Field(max_length=2000)


@router.post("/api/map/keep", status_code=204)
def keep(body: KeepRequest, request: Request) -> Response:
    """Keeps a copy of what the window has just loaded (in the background)."""
    app = state(request)
    for url in body.urls:
        path = copy_path(app, url)
        if path is not None and _stale(path):
            keeper.keep(url, path)
    return Response(status_code=204)


@router.post("/api/map/problem", status_code=204)
def problem(body: Problem) -> Response:
    """A problem of the map in the window, written in the log with its cause."""
    log.warning("Base map in the window: %s", body.message)
    return Response(status_code=204)


def _kept(folder: Path, url: str, *older: str) -> Any:
    """The JSON kept for `url` (or under a name used by older versions), None when there is none."""
    path = _upstream_copy(folder, url)
    for candidate in (path, *(folder / name for name in older)):
        if candidate is not None and candidate.is_file():
            try:
                return json.loads(candidate.read_bytes())
            except ValueError as error:
                log.warning("Base map copy: %s is damaged (%s)", candidate, error)
    return None


@router.get("/api/map/style.json")
def style(request: Request) -> JSONResponse:
    """The style kept on disk, pointing to the copies of its files (offline only)."""
    folder = state(request).storage.input("basemap")
    found = _kept(folder, STYLE_URL, "style.json")
    if not isinstance(found, dict):
        log.warning("Base map copy: no style kept in %s", folder)
        raise HTTPException(
            404,
            tr(
                "No copy of the base map was kept on this computer",
                "Aucune copie du fond de carte n'a été gardée sur cet ordinateur",
            ),
        )
    local = f"{str(request.base_url).rstrip('/')}/api/map/files/"
    sources: dict[str, Any] = {}
    for name, source in found.get("sources", {}).items():
        if source.get("type") == "raster":
            continue  # the shaded Natural Earth: the relief comes from the elevation tiles
        if "url" in source:
            described = _kept(folder, source["url"], f"{name}.tilejson")
            if not isinstance(described, dict):
                log.warning("Base map copy: no description of %s kept", source["url"])
                raise HTTPException(
                    404,
                    tr(
                        "No copy of the base map was kept on this computer",
                        "Aucune copie du fond de carte n'a été gardée sur cet ordinateur",
                    ),
                )
            source = {k: v for k, v in source.items() if k != "url"}
            source["tiles"] = [t.replace(UPSTREAM, local) for t in described.get("tiles", [])]
            for key in ("minzoom", "maxzoom", "bounds", "attribution"):
                if key in described:
                    source[key] = described[key]
        sources[name] = source
    found["sources"] = sources
    found["layers"] = [
        layer for layer in found.get("layers", []) if layer.get("source") in (None, *sources)
    ]
    for key in ("sprite", "glyphs"):
        if isinstance(found.get(key), str):
            found[key] = found[key].replace(UPSTREAM, local)
    return JSONResponse(found, headers={"Cache-Control": "no-cache"})


@router.get("/api/map/files/{path:path}")
def kept_file(path: str, request: Request) -> Response:
    """A tile, font range or symbol sheet kept on disk. A tile never kept is drawn empty (204); a
    tile kept from an earlier edition of the map stands in for one of the current edition."""
    if not _safe(path):
        raise HTTPException(404)
    files = state(request).storage.input("basemap") / "files"
    target = files / path
    if not target.is_file() and path.endswith(".pbf"):
        edition = Path(path).parts
        if len(edition) == 5:  # planet/<edition>/z/x/y.pbf
            others = sorted((files / edition[0]).glob(f"*/{'/'.join(edition[2:])}"), reverse=True)
            target = others[0] if others else target
    if not target.is_file():
        if path.endswith(".pbf"):
            return Response(status_code=204)
        raise HTTPException(404)
    return Response(
        target.read_bytes(),
        media_type=MEDIA.get(Path(path).suffix, "application/octet-stream"),
        headers=FOREVER,
    )


@router.get("/api/map/elevation/{z}/{x}/{y}.png")
def elevation(z: int, x: int, y: int, request: Request) -> Response:
    """An elevation tile kept on disk (the same copies as the 3D view of the levels)."""
    if not (0 <= z <= 15 and 0 <= x < 2**z and 0 <= y < 2**z):
        raise HTTPException(404)
    target = state(request).storage.input("elevation") / str(z) / str(x) / f"{y}.png"
    if not target.is_file():
        raise HTTPException(404)
    return Response(target.read_bytes(), media_type="image/png", headers=FOREVER)
