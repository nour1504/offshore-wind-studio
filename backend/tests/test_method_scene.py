"""Terrain and level heights of the 3D view (core/method/scene.py); no network."""

import base64
from io import BytesIO
from pathlib import Path

import netCDF4
import numpy as np
import pytest
from PIL import Image

from owstudio.core.case.model import Case
from owstudio.core.domains import domain_extents, projection_for
from owstudio.core.method import scene, vertical


def floats(text: str) -> np.ndarray:
    return np.frombuffer(base64.b64decode(text), dtype="<f4")


def write_geo_em(path: Path, case: Case, domain: int = 1, shift_cells: float = 0.0) -> None:
    """Synthetic geogrid output with geographically correct mass coordinates, stored as f4."""
    spec = case.grid.domains[domain - 1]
    extent = domain_extents(case.grid)[domain - 1]
    projection = projection_for(case.grid.projection)
    ny, nx = spec.e_sn - 1, spec.e_we - 1
    latitudes, longitudes = np.empty((ny, nx)), np.empty((ny, nx))
    for j in range(ny):
        for i in range(nx):
            latitudes[j, i], longitudes[j, i] = projection.inverse(
                extent.west + (i + 0.5 + shift_cells) * extent.dx,
                extent.south + (j + 0.5) * extent.dx,
            )
    with netCDF4.Dataset(path, "w") as data:
        data.createDimension("Time", 1)
        data.createDimension("south_north", ny)
        data.createDimension("west_east", nx)
        data.GRID_ID = domain
        data.DX = extent.dx
        dims = ("Time", "south_north", "west_east")
        data.createVariable("XLAT_M", "f4", dims)[0] = latitudes
        data.createVariable("XLONG_M", "f4", dims)[0] = longitudes
        field = np.zeros((ny, nx))
        field[:, : nx // 2] = 300.0
        field[:, -1] = -20.0
        data.createVariable("HGT_M", "f4", dims)[0] = field


def test_columns_match_the_single_column(reference_case: Case) -> None:
    s = vertical.settings(reference_case)
    znw = vertical.full_levels(s)
    c = vertical.coefficients(znw, s.hybrid_opt, s.etac, s.p_top)
    terrain = np.array([0.0, 350.0, 1200.0])
    many = scene.columns(s, znw, c, terrain)
    for index, height in enumerate(terrain):
        assert many[:, index] == pytest.approx(vertical.column(s, znw, c, float(height)), abs=1e-6)


def test_flat_scene_without_any_source(reference_case: Case) -> None:
    found = scene.scene(reference_case, 1)
    assert found["source"] == "flat"
    nx, ny = found["nx"], found["ny"]
    assert len(floats(found["terrain_m"])) == nx * ny
    heights = floats(found["heights_m"]).reshape(found["levels"], ny, nx)
    assert heights[0].max() == 0 and heights[1].mean() == pytest.approx(50, abs=0.5)
    assert [d["number"] for d in found["domains"]] == [1, 2]
    assert len(found["turbines"]) == sum(len(f.turbines) for f in reference_case.farms)


def test_terrain_of_a_geo_em_file(reference_case: Case, tmp_path: Path) -> None:
    path = tmp_path / "geo_em.d01.nc"
    write_geo_em(path, reference_case)
    found = scene.scene(reference_case, 1, geo_em=path)
    assert found["source"] == "geo_em"
    terrain = floats(found["terrain_m"]).reshape(found["ny"], found["nx"])
    assert terrain[:, 0].max() == 300 and terrain[:, -1].min() == 0
    heights = floats(found["heights_m"]).reshape(found["levels"], found["ny"], found["nx"])
    # Levels follow the terrain near the ground
    assert heights[1, 0, 0] == pytest.approx(300 + heights[1, 0, -1], abs=10)
    wrong = scene.scene(reference_case, 2, geo_em=path)
    assert wrong["source"] == "flat" and "not domain 2" in wrong["problems"][0]


@pytest.mark.parametrize("difference", ["location", "projection"])
def test_geo_em_from_another_grid_is_rejected_even_with_the_same_size_and_spacing(
    reference_case: Case, tmp_path: Path, difference: str
) -> None:
    path = tmp_path / "other-project.nc"
    other = reference_case.model_copy(deep=True)
    if difference == "location":
        other.grid.projection.ref_lat += 0.5
    else:
        other.grid.projection.truelat1 = 20
        other.grid.projection.truelat2 = 25
    write_geo_em(path, other)
    found = scene.scene(reference_case, 1, geo_em=path)
    assert found["source"] == "flat"
    assert any("location or projection differs" in problem for problem in found["problems"])


@pytest.mark.parametrize("shift", [0.005, 0.25])
def test_geo_em_geographical_tolerance_is_a_small_fraction_of_a_cell(
    reference_case: Case, tmp_path: Path, shift: float
) -> None:
    path = tmp_path / "rounded.nc"
    write_geo_em(path, reference_case, shift_cells=shift)
    found = scene.scene(reference_case, 1, geo_em=path)
    assert found["source"] == ("geo_em" if shift < 0.02 else "flat")


@pytest.mark.parametrize(
    "projection", ["southern_lambert", "mercator_dateline", "mercator_fine_high_latitude"]
)
def test_geo_em_float32_coordinates_are_accepted_in_supported_projections(
    reference_case: Case, tmp_path: Path, projection: str
) -> None:
    case = reference_case.model_copy(deep=True)
    if projection == "southern_lambert":
        case.grid.projection.ref_lat = -38
        case.grid.projection.ref_lon = 145
        case.grid.projection.truelat1 = -35
        case.grid.projection.truelat2 = -41
        case.grid.projection.stand_lon = 145
    else:
        case.grid.projection.map_proj = "mercator"
        case.grid.projection.ref_lat = 20
        case.grid.projection.ref_lon = 179.5
        case.grid.projection.truelat1 = 20
        if projection == "mercator_fine_high_latitude":
            case.grid.projection.ref_lat = 85
            case.grid.dx = 100
    path = tmp_path / "coordinates.nc"
    write_geo_em(path, case)
    assert scene.scene(case, 1, geo_em=path)["source"] == "geo_em"


def test_geo_em_geographical_corners_are_checked_not_only_the_centre(
    reference_case: Case, tmp_path: Path
) -> None:
    path = tmp_path / "bad-corner.nc"
    write_geo_em(path, reference_case)
    with netCDF4.Dataset(path, "a") as data:
        data.variables["XLAT_M"][0, 0, 0] += 0.1
    found = scene.scene(reference_case, 1, geo_em=path)
    assert found["source"] == "flat"
    assert any("location or projection differs" in problem for problem in found["problems"])


def test_geo_em_missing_geographical_coordinates_are_not_assumed_correct(
    reference_case: Case, tmp_path: Path
) -> None:
    path = tmp_path / "missing-location.nc"
    write_geo_em(path, reference_case)
    with netCDF4.Dataset(path, "a") as data:
        data.renameVariable("XLAT_M", "old_latitude")
    found = scene.scene(reference_case, 1, geo_em=path)
    assert found["source"] == "flat"
    assert any("cannot verify its location" in problem for problem in found["problems"])


@pytest.mark.parametrize("latitude", [float("nan"), -95.0, -90.0])
def test_geo_em_invalid_coordinates_do_not_create_a_scene(
    reference_case: Case, tmp_path: Path, latitude: float
) -> None:
    path = tmp_path / "invalid-location.nc"
    write_geo_em(path, reference_case)
    with netCDF4.Dataset(path, "a") as data:
        data.variables["XLAT_M"][0, 0, 0] = latitude
    found = scene.scene(reference_case, 1, geo_em=path)
    assert found["source"] == "flat"
    assert found["problems"]


def write_geog(root: Path) -> None:
    """A tiny global 30-degree dataset in the geogrid binary format: one tile of 12 x 6 pixels,
    big-endian signed 2-byte words, bottom to top; heights = 10 x row + column."""
    folder = root / "topo_gmted2010_30s"
    folder.mkdir(parents=True)
    (folder / "index").write_text(
        "type=continuous\nsigned=yes\nprojection=regular_ll\ndx=30.0\ndy=30.0\n"
        "known_x=1.0\nknown_y=1.0\nknown_lat=-75.0\nknown_lon=-165.0\nwordsize=2\n"
        'tile_x=12\ntile_y=6\ntile_z=1\nunits="meters MSL"\nendian=big\n',
        encoding="ascii",
    )
    values = np.array([[10 * row + column for column in range(12)] for row in range(6)])
    (folder / "00001-00012.00001-00006").write_bytes(values.astype(">i2").tobytes())


def test_terrain_of_wps_geog(tmp_path: Path) -> None:
    write_geog(tmp_path / "WPS_GEOG")
    folder = scene.geog_topography(tmp_path / "WPS_GEOG")
    assert folder is not None
    # 55.5 N 7.8 E: row (55.5 + 75) / 30 = 4.35 -> 4, column (7.8 + 165) / 30 = 5.76 -> 6
    heights = scene.from_wps_geog(folder, np.array([[55.5]]), np.array([[7.8]]))
    assert heights[0, 0] == 46


def test_the_geography_is_found_by_its_content_whatever_the_names(tmp_path: Path) -> None:
    """Found on the work VM: /app/ows/geog holds WPS_GEOG_LOW_RES, whose relief is
    topo_gmted2010_5m, which was not looked for. The topography is now recognised by its index
    (heights above sea level), below the folder given and whatever the names; the finest wins;
    other continuous data (variance of the orography, in m2) are not taken for it."""
    root = tmp_path / "anything"
    write_geog(root / "my geography" / "coarse")
    coarse = root / "my geography" / "coarse" / "topo_gmted2010_30s"
    coarse.rename(coarse.with_name("relief_grossier"))
    coarse = coarse.with_name("relief_grossier")
    other = root / "my geography" / "coarse" / "varsso"
    other.mkdir()
    (other / "index").write_text(
        'type=continuous\nprojection=regular_ll\ndx=1.0\ndy=1.0\nunits="m^2"\n'
        'description="Variance of subgrid-scale orography"\n',
        encoding="ascii",
    )
    assert scene.geog_topography(tmp_path) == coarse
    assert scene.geog_topography(coarse) == coarse
    finer = root / "other" / "fine"
    write_geog(finer)
    index = finer / "topo_gmted2010_30s" / "index"
    index.write_text(index.read_text().replace("dx=30.0", "dx=15.0"), encoding="ascii")
    assert scene.geog_topography(tmp_path) == finer / "topo_gmted2010_30s"
    assert scene.geog_topography(tmp_path / "nothing") is None


def test_terrain_of_public_tiles_is_cached(reference_case: Case, tmp_path: Path) -> None:
    calls: list[str] = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        # Terrarium: 32768 + 125 m = red 128, green 125
        image = Image.new("RGB", (256, 256), (128, 125, 0))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    cache = tmp_path / "elevation"
    found = scene.scene(reference_case, 2, cache=cache, fetch=fetch)
    assert found["source"] == "tiles" and calls
    assert set(floats(found["terrain_m"]).round(3)) == {125.0}
    count = len(calls)
    scene.scene(reference_case, 2, cache=cache, fetch=fetch)
    assert len(calls) == count  # read from the cache
    assert all("terrarium" in url for url in calls)


def test_the_public_tiles_chosen_come_before_the_geography(
    reference_case: Case, tmp_path: Path
) -> None:
    """The tiles chosen in the view are taken even when a geography is there; when they cannot
    be had (a proxy), the geography is taken and the reason is said."""

    def fetch(url: str) -> bytes:
        image = Image.new("RGB", (256, 256), (128, 125, 0))
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    def refused(url: str) -> bytes:
        raise OSError("CERTIFICATE_VERIFY_FAILED")

    write_geog(tmp_path / "geog" / "WPS_GEOG")
    geog = [tmp_path / "geog"]
    cache = tmp_path / "elevation"
    assert (
        scene.scene(reference_case, 2, geog=geog, cache=cache, fetch=fetch)["source"] == "wps_geog"
    )
    chosen = scene.scene(reference_case, 2, geog=geog, cache=cache, fetch=fetch, tiles_first=True)
    assert chosen["source"] == "tiles" and chosen["problems"] == []
    blocked = scene.scene(
        reference_case, 2, geog=geog, cache=tmp_path / "other", fetch=refused, tiles_first=True
    )
    assert blocked["source"] == "wps_geog"
    assert any("CERTIFICATE_VERIFY_FAILED" in problem for problem in blocked["problems"])


def test_profile_and_3d_view_give_the_same_heights(reference_case: Case) -> None:
    """The 2D profile (over the sea) and the 3D scene over a sea-level point use the same heights."""
    profile = vertical.profile(reference_case)
    found = scene.scene(reference_case, 1)
    assert found["sea_level_heights_m"] == pytest.approx(
        [level.height_m for level in profile.full], abs=1e-6
    )
    s = vertical.settings(reference_case)
    znw = vertical.full_levels(s)
    c = vertical.coefficients(znw, s.hybrid_opt, s.etac, s.p_top)
    flat = scene.columns(s, znw, c, np.zeros(1))[:, 0]
    assert list(flat) == pytest.approx([level.height_m for level in profile.full], abs=1e-6)


def test_display_grid_refines_the_model_grid(reference_case: Case, tmp_path: Path) -> None:
    """A finer terrain for the eye; the model terrain is its mean over each cell, water at 0 m,
    and the levels are computed over the model terrain only."""

    def fetch(url: str) -> bytes:
        # A sloping sea floor and coast: heights from -40 m to +60 m across each tile
        array = np.zeros((256, 256, 3), dtype=np.uint8)
        heights = np.linspace(-40, 60, 256)[None, :] + np.zeros((256, 1))
        value = heights + 32768
        array[..., 0] = (value // 256).astype(np.uint8)
        array[..., 1] = (value % 256).astype(np.uint8)
        buffer = BytesIO()
        Image.fromarray(array, "RGB").save(buffer, format="PNG")
        return buffer.getvalue()

    found = scene.scene(reference_case, 2, cache=tmp_path / "elevation", fetch=fetch)
    display = found["display"]
    factor = display["factor"]
    assert display["nx"] == found["nx"] * factor and display["ny"] == found["ny"] * factor
    fine = floats(display["terrain_m"]).reshape(display["ny"], display["nx"])
    model = floats(found["terrain_m"]).reshape(found["ny"], found["nx"])
    assert fine.min() < 0  # the sea floor is kept for the colour of the sea
    expected = (
        np.maximum(fine, 0).reshape(found["ny"], factor, found["nx"], factor).mean(axis=(1, 3))
    )
    assert model == pytest.approx(expected, abs=1e-3)
    assert len(found["b_full"]) == found["levels"] and found["b_full"][0] == 1.0


def test_upsample_keeps_cell_centres() -> None:
    model = np.array([[0.0, 10.0], [20.0, 30.0]])
    fine = scene.upsample(model, 2)
    assert fine.shape == (4, 4)
    assert fine.min() >= 0 and fine.max() <= 30
    assert scene.cell_means(fine, 2) == pytest.approx(model, abs=6)


def test_engine_geography_of_a_wsl_engine(tmp_path: Path) -> None:
    from owstudio.api.routes_method import engine_geography
    from owstudio.core.engine.profiles import ComputeProfile, EngineInstall
    from owstudio.core.settings import Settings

    local = ComputeProfile(
        id="pc", name="PC", kind="local", install=EngineInstall(geog_dir=str(tmp_path))
    )
    assert engine_geography(Settings(profiles=[local])) == tmp_path
    missing = ComputeProfile(
        id="pc", name="PC", kind="local", install=EngineInstall(geog_dir=str(tmp_path / "no"))
    )
    assert engine_geography(Settings(profiles=[missing])) is None
    assert engine_geography(Settings()) is None


def test_a_scene_already_drawn_comes_back_from_the_disk(
    reference_case: Case, tmp_path: Path
) -> None:
    from helpers import make_client

    client = make_client(tmp_path)
    body = {"case": reference_case.model_dump(mode="json"), "domain": 1, "tiles": False}
    first = client.post("/api/method/scene", json=body)
    assert first.status_code == 200
    saved = list((tmp_path / "data").rglob("scenes/*.json"))
    assert len(saved) == 1
    again = client.post("/api/method/scene", json=body)
    assert again.json() == first.json()


def test_the_relief_given_is_searched_below_and_its_absence_is_said(
    reference_case: Case, tmp_path: Path
) -> None:
    """One field for the relief: a geography folder (or the folder above it) gives WPS_GEOG, a
    calculation folder gives its geo_em file; a path that is not there is named, the view is flat
    and nothing is kept on disk."""
    from helpers import make_client

    write_geog(tmp_path / "geog" / "WPS_GEOG_LOW_RES")
    (tmp_path / "calculs" / "Test-WRF" / "wps").mkdir(parents=True)
    write_geo_em(tmp_path / "calculs" / "Test-WRF" / "wps" / "geo_em.d01.nc", reference_case)
    client = make_client(tmp_path)
    body = {"case": reference_case.model_dump(mode="json"), "domain": 1, "tiles": False}
    found = client.post("/api/method/scene", json={**body, "relief": str(tmp_path / "geog")}).json()
    assert found["source"] == "wps_geog" and found["source_detail"].endswith("topo_gmted2010_30s")
    calc = client.post(
        "/api/method/scene", json={**body, "relief": str(tmp_path / "calculs")}
    ).json()
    assert calc["source"] == "geo_em" and calc["source_detail"].endswith("geo_em.d01.nc")
    missing = client.post(
        "/api/method/scene", json={**body, "relief": str(tmp_path / "nowhere")}
    ).json()
    assert missing["source"] == "flat" and "nowhere" in missing["problems"][0]
    assert len(list((tmp_path / "data").rglob("scenes/*.json"))) == 2


def test_a_proxy_page_is_never_kept_as_a_tile(reference_case: Case, tmp_path: Path) -> None:
    """A proxy answering with an HTML page: the tiles fail with the reason and nothing is kept;
    a page kept by an earlier version is fetched again once the network answers."""

    def proxy(url: str) -> bytes:
        return b"<html>Proxy login</html>"

    def tile(url: str) -> bytes:
        buffer = BytesIO()
        Image.new("RGB", (256, 256), (128, 125, 0)).save(buffer, format="PNG")
        return buffer.getvalue()

    cache = tmp_path / "elevation"
    blocked = scene.scene(reference_case, 2, cache=cache, fetch=proxy)
    assert blocked["source"] == "flat" and any("proxy" in p for p in blocked["problems"])
    assert not list(cache.rglob("*.png"))
    assert scene.scene(reference_case, 2, cache=cache, fetch=tile)["source"] == "tiles"
    kept = sorted(cache.rglob("*.png"))
    kept[0].write_bytes(b"<html>kept by 0.6.6</html>")
    again = scene.scene(reference_case, 2, cache=cache, fetch=tile)
    assert again["source"] == "tiles" and again["problems"] == []
    assert kept[0].read_bytes()[:8] == scene.PNG_SIGNATURE


def test_tiles_are_not_asked_again_right_after_a_failure(monkeypatch) -> None:
    """Without network, each redraw would wait for the timeout: after a failure the tiles are
    paused for a few minutes."""
    from owstudio.core import web

    calls: list[str] = []

    def refused(url: str, timeout: float = 30) -> object:
        calls.append(url)
        raise OSError("unreachable")

    monkeypatch.setattr(web, "urlopen", refused)
    monkeypatch.setattr(scene, "_tiles_paused_until", 0.0)
    for _ in range(3):
        with pytest.raises(OSError):
            scene.download_tile("https://tiles/0/0/0.png")
    assert len(calls) == 1
    monkeypatch.setattr(scene, "_tiles_paused_until", 0.0)
