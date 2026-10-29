"""The base map: loaded by the window from its public servers, a copy kept on disk in the
background and served only offline; every failure written in the log with its cause."""

import gzip
import io
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

import pytest
from helpers import make_client

from owstudio.api import routes_map

UP = routes_map.UPSTREAM
STYLE = {
    "version": 8,
    "sources": {
        "ne2_shaded": {"type": "raster", "tiles": [f"{UP}natural_earth/{{z}}/{{x}}/{{y}}.png"]},
        "openmaptiles": {"type": "vector", "url": f"{UP}planet"},
    },
    "sprite": f"{UP}sprites/ofm/ofm",
    "glyphs": f"{UP}fonts/{{fontstack}}/{{range}}.pbf",
    "layers": [
        {"id": "ne2", "type": "raster", "source": "ne2_shaded"},
        {"id": "water", "type": "fill", "source": "openmaptiles", "source-layer": "water"},
        {"id": "background", "type": "background"},
    ],
}
TILEJSON = {"tiles": [f"{UP}planet/20261018/{{z}}/{{x}}/{{y}}.pbf"], "maxzoom": 14}
TILE = f"{UP}planet/20261018/5/16/10.pbf"
FONT = f"{UP}fonts/Noto%20Sans%20Regular/0-255.pbf"
RELIEF = routes_map.TERRARIUM_URL.format(z=6, x=33, y=20)


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []

    def fetch(url: str) -> bytes:
        seen.append(url)
        if url == routes_map.STYLE_URL:
            return json.dumps(STYLE).encode()
        if url.endswith("/planet"):
            return json.dumps(TILEJSON).encode()
        return b"copy:" + url.encode()

    monkeypatch.setattr(routes_map, "fetch", fetch)
    return seen


def keep(client: Any, *urls: str) -> None:
    assert client.post("/api/map/keep", json={"urls": list(urls)}).status_code == 204
    routes_map.keeper.wait()


def test_empty_data_folder_answers_at_once_and_says_why(
    tmp_path: Path, calls: list[str], caplog: pytest.LogCaptureFixture
) -> None:
    """A computer that never kept anything: nothing is downloaded while the window waits, the
    window gets a clear answer (and falls back to a plain background), the log says why."""
    client = make_client(tmp_path)
    with caplog.at_level(logging.WARNING, logger="owstudio.map"):
        assert client.get("/api/map/style.json").status_code == 404
    assert "no style kept" in caplog.text
    assert client.get("/api/map/files/planet/20261018/5/16/10.pbf").status_code == 204
    assert client.get("/api/map/files/sprites/ofm/ofm.json").status_code == 404
    assert client.get("/api/map/elevation/6/33/20.png").status_code == 404
    assert calls == []  # the routes the window waits on never download


def test_what_the_window_loaded_is_kept_then_served_offline(
    tmp_path: Path, calls: list[str]
) -> None:
    client = make_client(tmp_path)
    keep(
        client,
        routes_map.STYLE_URL,
        f"{UP}planet",
        TILE,
        FONT,
        f"{UP}sprites/ofm/ofm.json",
        RELIEF,
        "https://example.com/other.png",
        f"{UP}../secret",
    )
    assert sorted(calls) == sorted(
        [routes_map.STYLE_URL, f"{UP}planet", TILE, FONT, f"{UP}sprites/ofm/ofm.json", RELIEF]
    )
    style = client.get("/api/map/style.json").json()
    assert list(style["sources"]) == ["openmaptiles"]  # the raster relief is left out
    assert [layer["id"] for layer in style["layers"]] == ["water", "background"]
    tiles = style["sources"]["openmaptiles"]["tiles"][0]
    assert tiles.startswith("http") and tiles.endswith(
        "/api/map/files/planet/20261018/{z}/{x}/{y}.pbf"
    )
    assert style["glyphs"].endswith("/api/map/files/fonts/{fontstack}/{range}.pbf")
    assert style["sprite"].endswith("/api/map/files/sprites/ofm/ofm")
    tile = client.get("/api/map/files/planet/20261018/5/16/10.pbf")
    assert tile.status_code == 200 and tile.content == b"copy:" + TILE.encode()
    assert "immutable" in tile.headers["cache-control"]
    assert client.get("/api/map/files/fonts/Noto Sans Regular/0-255.pbf").content.startswith(
        b"copy:"
    )
    assert client.get("/api/map/elevation/6/33/20.png").content == b"copy:" + RELIEF.encode()
    # The relief is the same copy as the 3D view of the levels
    assert any(tmp_path.rglob("elevation/6/33/20.png"))
    # Kept once: asked again, nothing is downloaded again
    count = len(calls)
    keep(client, TILE, FONT, RELIEF)
    assert len(calls) == count
    # A tile never seen is drawn empty; a path out of the folder is refused
    assert client.get("/api/map/files/planet/20261018/5/16/11.pbf").status_code == 204
    assert client.get("/api/map/files/../secret").status_code == 404
    assert client.get("/api/map/elevation/3/9/0.png").status_code == 404  # outside the zoom 3 grid


def test_a_tile_of_an_earlier_edition_stands_in(tmp_path: Path, calls: list[str]) -> None:
    client = make_client(tmp_path)
    keep(client, TILE)
    newer = client.get("/api/map/files/planet/20261025/5/16/10.pbf")
    assert newer.status_code == 200 and newer.content == b"copy:" + TILE.encode()


def test_failed_downloads_are_logged_with_their_cause_and_never_block(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def refused(url: str) -> bytes:
        raise OSError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")

    monkeypatch.setattr(routes_map, "fetch", refused)
    client = make_client(tmp_path)
    before = dict(routes_map.keeper.failures)
    with caplog.at_level(logging.WARNING, logger="owstudio.map"):
        keep(client, TILE, f"{UP}planet/20261018/5/16/11.pbf", RELIEF)
    cause = "OSError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed"
    assert routes_map.keeper.failures[cause] - before.get(cause, 0) == 3
    assert "CERTIFICATE_VERIFY_FAILED" in caplog.text
    assert not any(tmp_path.rglob("*.pbf")) and not any(tmp_path.rglob("*.part"))
    assert client.get("/api/map/files/planet/20261018/5/16/10.pbf").status_code == 204


def test_problems_of_the_window_go_to_the_log(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    client = make_client(tmp_path)
    with caplog.at_level(logging.WARNING, logger="owstudio.map"):
        response = client.post("/api/map/problem", json={"message": "tiles: Failed to fetch"})
    assert response.status_code == 204
    assert "Base map in the window: tiles: Failed to fetch" in caplog.text


def test_copies_of_version_0_4_2_are_still_used(tmp_path: Path, calls: list[str]) -> None:
    client = make_client(tmp_path)
    keep(client, TILE)  # creates the folder of the copies
    folder = next(tmp_path.rglob("basemap"))
    (folder / "style.json").write_text(json.dumps(STYLE))
    (folder / "openmaptiles.tilejson").write_text(json.dumps(TILEJSON))
    assert client.get("/api/map/style.json").status_code == 200


class Answer(io.BytesIO):
    def __init__(self, data: bytes, status: int = 200, encoding: str | None = None) -> None:
        super().__init__(data)
        self.status = status
        self.headers = {"Content-Encoding": encoding} if encoding else {}


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        (Answer(gzip.compress(b"tile"), encoding="gzip"), b"tile"),
        (Answer(b"tile"), b"tile"),
        (Answer(b"tile", encoding="identity"), b"tile"),
        (Answer(b"\x1b\x00", encoding="br"), ValueError),
        (Answer(b""), ValueError),
        (Answer(b"", status=204), ValueError),
    ],
)
def test_download_reads_compressed_answers_and_refuses_odd_ones(
    monkeypatch: pytest.MonkeyPatch, answer: Answer, expected: bytes | type[Exception]
) -> None:
    monkeypatch.setattr(routes_map.web, "urlopen", lambda request, timeout: answer)
    if isinstance(expected, bytes):
        assert routes_map.download(TILE) == expected
    else:
        with pytest.raises(expected):
            routes_map.download(TILE)


def test_font_addresses_are_written_as_a_request_needs() -> None:
    raw = f"{UP}fonts/Noto Sans Regular,Noto Sans Bold/0-255.pbf"
    assert (
        routes_map.address(raw) == f"{UP}fonts/Noto%20Sans%20Regular,Noto%20Sans%20Bold/0-255.pbf"
    )
    assert routes_map.address(FONT) == FONT
    assert routes_map.address(TILE) == TILE


@pytest.mark.skipif(sys.platform == "win32", reason="the bundles of Linux distributions")
def test_downloads_trust_the_certificates_of_the_computer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Found on the work VM: the packaged application trusted no certificate (its OpenSSL looks
    in a folder of the build machine), so the public tiles failed with CERTIFICATE_VERIFY_FAILED.
    The system bundle, the one wget uses, is loaded."""
    import ssl

    from owstudio.core import web

    bundle = next((p for p in web.SYSTEM_BUNDLES if os.path.isfile(p)), None)
    if bundle is None:
        pytest.skip("no certificate bundle on this computer")
    empty = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    monkeypatch.setattr(web.ssl, "create_default_context", lambda: empty)
    web.context.cache_clear()
    try:
        assert web.context() is empty and empty.cert_store_stats()["x509_ca"] > 0
    finally:
        web.context.cache_clear()
