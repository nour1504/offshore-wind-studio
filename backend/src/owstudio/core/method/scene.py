"""The 3D scene of the vertical levels: the terrain under a domain, and the height of every model
level above each point, as real.exe computes them (core/method/vertical.py).

One source of relief, the first that can be read, in this order: the geo_em file of the domain
(HGT_M, the terrain WRF uses); a WPS_GEOG folder (its finest topography, recognised by its index
file whatever the names of the folders, read like geogrid); public elevation tiles (Terrarium,
Mapzen/AWS Open Data, cached in the data folder); flat. Each source that cannot be read says why.

Two grids:
- the model grid, at the domain's mass points (thinned beyond MAX_SIDE points a side): the levels
  are computed exactly over its terrain (the source averaged over each cell). Water is at 0 m.
- the display grid, finer (an integer number of points per model cell), only to draw a smooth
  terrain from the same source (with the depth of the sea for the tiles).
"""

import base64
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, Literal

import numpy as np

from owstudio.core import web
from owstudio.core.case.model import Case
from owstudio.core.domains import domain_extents, projection_for
from owstudio.core.energy.curves import turbine_types
from owstudio.core.i18n import tr
from owstudio.core.method import vertical
from owstudio.core.paths import folders_below

TERRARIUM_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
MAX_SIDE = 100
# Points of the display grid along the longer side, about
DISPLAY_SIDE = 240
MAX_TILES = 100

Source = Literal["geo_em", "wps_geog", "tiles", "flat"]


@dataclass(frozen=True)
class Samples:
    """Points of a domain where the scene is drawn, regular in the projection plane."""

    xs: np.ndarray  # metres, projection plane
    ys: np.ndarray
    lat: np.ndarray  # (ny, nx)
    lon: np.ndarray


def samples(case: Case, domain: int, max_side: int = MAX_SIDE) -> Samples:
    extent = domain_extents(case.grid)[domain - 1]
    spec = case.grid.domains[domain - 1]
    nx = min(spec.e_we - 1, max_side)
    ny = min(spec.e_sn - 1, max_side)
    xs = extent.west + (np.arange(nx) + 0.5) * (extent.east - extent.west) / nx
    ys = extent.south + (np.arange(ny) + 0.5) * (extent.north - extent.south) / ny
    proj = projection_for(case.grid.projection)
    lat = np.empty((ny, nx))
    lon = np.empty((ny, nx))
    for j, y in enumerate(ys):
        for i, x in enumerate(xs):
            lat[j, i], lon[j, i] = proj.inverse(float(x), float(y))
    return Samples(xs, ys, lat, lon)


def refined(case: Case, domain: int, model: Samples) -> tuple[Samples, int]:
    """The display grid: `factor` points a side inside every model cell, centred like it."""
    factor = max(1, DISPLAY_SIDE // max(len(model.xs), len(model.ys)))
    extent = domain_extents(case.grid)[domain - 1]
    nx, ny = len(model.xs) * factor, len(model.ys) * factor
    xs = extent.west + (np.arange(nx) + 0.5) * (extent.east - extent.west) / nx
    ys = extent.south + (np.arange(ny) + 0.5) * (extent.north - extent.south) / ny
    proj = projection_for(case.grid.projection)
    lat = np.empty((ny, nx))
    lon = np.empty((ny, nx))
    for j, y in enumerate(ys):
        for i, x in enumerate(xs):
            lat[j, i], lon[j, i] = proj.inverse(float(x), float(y))
    return Samples(xs, ys, lat, lon), factor


def cell_means(display: np.ndarray, factor: int) -> np.ndarray:
    """The mean over each model cell of a display field (water at 0 m, as in WRF's HGT_M)."""
    ny, nx = display.shape[0] // factor, display.shape[1] // factor
    land = np.maximum(display, 0.0)
    return np.asarray(land.reshape(ny, factor, nx, factor).mean(axis=(1, 3)))


def upsample(model: np.ndarray, factor: int) -> np.ndarray:
    """A model field on the display grid, bilinear between cell centres."""
    if factor == 1:
        return model.copy()
    ny, nx = model.shape
    yd = (np.arange(ny * factor) + 0.5) / factor - 0.5
    xd = (np.arange(nx * factor) + 0.5) / factor - 0.5
    y0 = np.clip(np.floor(yd).astype(int), 0, ny - 1)
    x0 = np.clip(np.floor(xd).astype(int), 0, nx - 1)
    y1 = np.clip(y0 + 1, 0, ny - 1)
    x1 = np.clip(x0 + 1, 0, nx - 1)
    fy = np.clip(yd - y0, 0, 1)[:, None]
    fx = np.clip(xd - x0, 0, 1)[None, :]
    top = model[np.ix_(y0, x0)] * (1 - fx) + model[np.ix_(y0, x1)] * fx
    bottom = model[np.ix_(y1, x0)] * (1 - fx) + model[np.ix_(y1, x1)] * fx
    return np.asarray(top * (1 - fy) + bottom * fy)


# ------------------------------------------------------------------ geo_em


def from_geo_em(path: Path, case: Case, domain: int, points: Samples) -> np.ndarray:
    """HGT_M of a geo_em file of the domain, at the nearest mass point of each sample."""
    import netCDF4

    extent = domain_extents(case.grid)[domain - 1]
    with netCDF4.Dataset(path) as data:
        heights = np.asarray(data.variables["HGT_M"][0], dtype=float)
        grid_id = getattr(data, "GRID_ID", domain)
        spacing = float(getattr(data, "DX", extent.dx))
        if (
            int(grid_id) != domain
            or not math.isfinite(spacing)
            or abs(spacing - extent.dx) > 0.01 * extent.dx
        ):
            raise ValueError(
                tr(
                    f"{path.name} is not domain {domain} of this project (grid or spacing)",
                    f"{path.name} n'est pas le domaine {domain} de ce projet (grille ou maille)",
                )
            )
        spec = case.grid.domains[domain - 1]
        if heights.shape != (spec.e_sn - 1, spec.e_we - 1):
            raise ValueError(
                tr(
                    f"{path.name} is not domain {domain} of this project (its size differs)",
                    f"{path.name} n'est pas le domaine {domain} de ce projet (sa taille diffère)",
                )
            )
        # Equal dimensions and GRID_ID do not identify a geographical grid. Check the mass
        # coordinates at its corners, edge centres and centre in this project's spherical
        # projection. The small tolerance accepts WPS float32 coordinate rounding, while a
        # displacement of even a small fraction of a cell is rejected.
        latitude = data.variables.get("XLAT_M")
        longitude = data.variables.get("XLONG_M")
        if latitude is None or longitude is None:
            raise ValueError(
                tr(
                    f"{path.name}: missing XLAT_M/XLONG_M; cannot verify its location",
                    f"{path.name} : XLAT_M/XLONG_M manquants ; sa position ne peut pas être vérifiée",
                )
            )
        ny, nx = heights.shape
        projection = projection_for(case.grid.projection)
        tolerance = max(2.0, extent.dx * 0.02)
        for variable in (latitude, longitude):
            if variable.ndim not in (2, 3) or variable.shape[-2:] != heights.shape:
                raise ValueError(
                    tr(
                        f"{path.name}: geographical coordinates do not match its grid",
                        f"{path.name} : les coordonnées géographiques ne correspondent pas à sa grille",
                    )
                )

        def coordinate(variable: Any, row: int, column: int) -> float:
            index = (0, row, column) if variable.ndim == 3 else (row, column)
            return float(np.ma.filled(variable[index], np.nan))

        for row in {0, ny // 2, ny - 1}:
            for column in {0, nx // 2, nx - 1}:
                lat = coordinate(latitude, row, column)
                lon = coordinate(longitude, row, column)
                if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90):
                    raise ValueError(
                        tr(
                            f"{path.name}: invalid geographical coordinates",
                            f"{path.name} : coordonnées géographiques invalides",
                        )
                    )
                try:
                    x, y = projection.forward(lat, lon)
                except (ValueError, OverflowError, ZeroDivisionError) as error:
                    raise ValueError(
                        tr(
                            f"{path.name}: invalid geographical coordinates",
                            f"{path.name} : coordonnées géographiques invalides",
                        )
                    ) from error
                expected_x = extent.west + (column + 0.5) * extent.dx
                expected_y = extent.south + (row + 0.5) * extent.dx
                # The rounding of float32 coordinates, as it moves the point on this projection
                # (about 10 m at 85 degrees in Mercator): never rejected for being stored in f4
                step_lat = float(np.spacing(np.float32(abs(lat))))
                step_lon = float(np.spacing(np.float32(abs(lon))))
                try:
                    xr, yr = projection.forward(
                        lat - math.copysign(step_lat, lat), lon - math.copysign(step_lon, lon)
                    )
                    rounding = math.hypot(xr - x, yr - y)
                except (ValueError, OverflowError, ZeroDivisionError):
                    rounding = 0.0
                allowed = max(tolerance, 2.0 * rounding)
                if (
                    not (math.isfinite(x) and math.isfinite(y))
                    or math.hypot(x - expected_x, y - expected_y) > allowed
                ):
                    raise ValueError(
                        tr(
                            f"{path.name} is not domain {domain} of this project "
                            "(its location or projection differs)",
                            f"{path.name} n'est pas le domaine {domain} de ce projet (sa position ou sa projection diffère)",
                        )
                    )
    i = np.clip(
        ((points.xs - extent.west) / extent.dx - 0.5).round().astype(int), 0, heights.shape[1] - 1
    )
    j = np.clip(
        ((points.ys - extent.south) / extent.dx - 0.5).round().astype(int), 0, heights.shape[0] - 1
    )
    return heights[np.ix_(j, i)]


# ------------------------------------------------------------------ WPS_GEOG


def read_index(folder: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in (folder / "index").read_text(encoding="ascii", errors="replace").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip().lower()] = value.strip().strip('"').strip("'")
    return values


def topography_step(folder: Path) -> float | None:
    """The pixel size in degrees when ``folder`` holds a WPS topography dataset, whatever its name:
    an index of continuous heights above sea level (units "meters MSL" or a description of the
    topography), regular_ll."""
    if not (folder / "index").is_file():
        return None
    try:
        index = read_index(folder)
        step = float(index["dx"])
    except (OSError, KeyError, ValueError):
        return None
    units, description = index.get("units", "").lower(), index.get("description", "").lower()
    if (
        index.get("type", "").lower() != "continuous"
        or index.get("projection", "regular_ll") != "regular_ll"
    ):
        return None
    return step if "msl" in units or "topograph" in description else None


def geog_topography(root: Path) -> Path | None:
    """The finest topography found in ``root`` or below it (a WPS_GEOG folder, the folder above
    it, or the topography itself), whatever the names of the folders."""
    found = [(step, folder) for folder in folders_below(root) if (step := topography_step(folder))]
    return min(found, key=lambda item: item[0])[1] if found else None


def find_geo_em(root: Path, domain: int) -> Path | None:
    """The geo_em file of the domain in ``root`` or below it (a wps/ folder, a calculation)."""
    name = f"geo_em.d{domain:02d}.nc"
    for folder in folders_below(root):
        if (folder / name).is_file():
            return folder / name
    return None


def from_wps_geog(folder: Path, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Heights from a WPS static dataset in the geogrid binary format (regular_ll), at the
    nearest pixel, as described by its index file (WPS user guide, binary format)."""
    index = read_index(folder)
    if index.get("projection", "regular_ll") != "regular_ll":
        raise ValueError(
            tr(
                f"{folder.name}: only regular_ll datasets are read",
                f"{folder.name} : seules les données regular_ll sont lues",
            )
        )
    dx, dy = float(index["dx"]), float(index["dy"])
    known_x, known_y = float(index.get("known_x", 1)), float(index.get("known_y", 1))
    known_lat, known_lon = float(index["known_lat"]), float(index["known_lon"])
    tile_x, tile_y = int(index["tile_x"]), int(index["tile_y"])
    border = int(index.get("tile_bdr", 0))
    size = int(index.get("wordsize", 2))
    signed = index.get("signed", "no").lower() == "yes"
    little = index.get("endian", "big").lower() == "little"
    scale = float(index.get("scale_factor", 1.0))
    top_bottom = index.get("row_order", "bottom_top").lower() == "top_bottom"
    columns = round(360.0 / dx)
    tiles: dict[tuple[int, int], np.ndarray] = {}

    def tile(tx: int, ty: int) -> np.ndarray:
        if (tx, ty) not in tiles:
            name = (
                f"{tx * tile_x + 1:05d}-{(tx + 1) * tile_x:05d}."
                f"{ty * tile_y + 1:05d}-{(ty + 1) * tile_y:05d}"
            )
            raw = np.frombuffer((folder / name).read_bytes(), dtype=np.uint8)
            raw = raw[: (tile_x + 2 * border) * (tile_y + 2 * border) * size]
            words = raw.reshape(-1, size).astype(np.int64)
            if little:
                words = words[:, ::-1]
            value = np.zeros(len(words), dtype=np.int64)
            for b in range(size):
                value = value * 256 + words[:, b]
            if signed:
                value = np.where(value >= 2 ** (8 * size - 1), value - 2 ** (8 * size), value)
            grid = value.reshape(tile_y + 2 * border, tile_x + 2 * border) * scale
            tiles[(tx, ty)] = grid[::-1] if top_bottom else grid
        return tiles[(tx, ty)]

    result = np.zeros(lat.shape)
    for index_ in np.ndindex(lat.shape):
        x = int(np.rint((lon[index_] - known_lon) / dx + known_x)) - 1
        y = int(np.rint((lat[index_] - known_lat) / dy + known_y)) - 1
        x %= columns
        tx, ty = x // tile_x, y // tile_y
        result[index_] = tile(tx, ty)[y % tile_y + border, x % tile_x + border]
    return result


# ------------------------------------------------------------------ public tiles


def tile_xy(lat: float, lon: float, zoom: int) -> tuple[float, float]:
    """Web Mercator tile coordinates (fractional) of a point."""
    n = 2**zoom
    x = (lon + 180.0) / 360.0 * n
    rad = math.radians(max(-85.0511, min(85.0511, lat)))
    y = (1.0 - math.log(math.tan(rad) + 1.0 / math.cos(rad)) / math.pi) / 2.0 * n
    return x, y


def tile_zoom(lat: np.ndarray, lon: np.ndarray, spacing_m: float) -> int:
    """The coarsest zoom whose pixels are at most half the sample spacing (up to zoom 13),
    reduced until at most MAX_TILES tiles cover the samples."""
    zoom = 13
    for candidate in range(1, 14):
        pixel = 40_075_016 * math.cos(math.radians(float(np.mean(lat)))) / (256 * 2**candidate)
        if pixel <= spacing_m / 2:
            zoom = candidate
            break
    while zoom > 1:
        x0, y0 = tile_xy(float(lat.max()), float(lon.min()), zoom)
        x1, y1 = tile_xy(float(lat.min()), float(lon.max()), zoom)
        if (int(x1) - int(x0) + 1) * (int(y1) - int(y0) + 1) <= MAX_TILES:
            break
        zoom -= 1
    return zoom


# After a failed download, the tiles are not asked again for a while: without network each
# redraw of the view would otherwise wait for the timeout
TILES_PAUSE_S = 300
_tiles_paused_until = 0.0
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def download_tile(url: str) -> bytes:
    global _tiles_paused_until
    if time.monotonic() < _tiles_paused_until:
        raise OSError(tr("no answer a few minutes ago", "pas de réponse il y a quelques minutes"))
    try:
        with web.urlopen(url, timeout=30) as response:
            data: bytes = response.read()
    except OSError:
        _tiles_paused_until = time.monotonic() + TILES_PAUSE_S
        raise
    return data


def from_tiles(
    lat: np.ndarray,
    lon: np.ndarray,
    spacing_m: float,
    cache: Path,
    fetch: Callable[[str], bytes] = download_tile,
) -> np.ndarray:
    """Heights from Terrarium tiles: (red x 256 + green + blue / 256) - 32768 metres."""
    from PIL import Image

    zoom = tile_zoom(lat, lon, spacing_m)
    images: dict[tuple[int, int], np.ndarray] = {}

    def image(tx: int, ty: int) -> np.ndarray:
        if (tx, ty) not in images:
            path = cache / str(zoom) / str(tx) / f"{ty}.png"
            # A file that is not a PNG (a proxy page kept by an earlier version) is fetched again
            if path.is_file() and path.read_bytes()[:8] != PNG_SIGNATURE:
                path.unlink()
            if not path.is_file():
                path.parent.mkdir(parents=True, exist_ok=True)
                data = fetch(TERRARIUM_URL.format(z=zoom, x=tx, y=ty))
                if data[:8] != PNG_SIGNATURE:
                    raise ValueError(
                        tr(
                            "the answer is not an image (proxy page?)",
                            "la réponse n'est pas une image (page de proxy ?)",
                        )
                    )
                temporary = path.with_suffix(".part")
                temporary.write_bytes(data)
                temporary.replace(path)
            rgb = np.asarray(Image.open(path).convert("RGB"), dtype=float)
            images[(tx, ty)] = rgb[..., 0] * 256 + rgb[..., 1] + rgb[..., 2] / 256 - 32768
        return images[(tx, ty)]

    # Bilinear between the pixel centres of the tiles around each point: no steps, no spikes
    n = 2**zoom
    result = np.zeros(lat.shape)

    def pixel(x: float, y: float) -> float:
        tx, ty = int(x // 256) % n, min(max(int(y // 256), 0), n - 1)
        return float(image(tx, ty)[min(max(int(y % 256), 0), 255), int(x % 256)])

    for index in np.ndindex(lat.shape):
        x, y = tile_xy(float(lat[index]), float(lon[index]), zoom)
        px, py = x * 256 - 0.5, y * 256 - 0.5
        x0, y0 = math.floor(px), math.floor(py)
        fx, fy = px - x0, py - y0
        top = pixel(x0, y0) * (1 - fx) + pixel(x0 + 1, y0) * fx
        bottom = pixel(x0, y0 + 1) * (1 - fx) + pixel(x0 + 1, y0 + 1) * fx
        result[index] = top * (1 - fy) + bottom * fy
    return result


# ------------------------------------------------------------------ levels over the terrain


def columns(
    s: vertical.VerticalSettings, znw: list[float], c: vertical.Coefficients, terrain: np.ndarray
) -> np.ndarray:
    """Heights above sea level of every full level over every terrain height, (levels, ...):
    the base state of real.exe (vertical.column), vectorised."""
    p00, t00, a, p_top = s.base_pres, s.base_temp, s.base_lapse, s.p_top
    g, r_d, cp = vertical.G, vertical.R_D, vertical.CP
    p_surf = p00 * np.exp(-t00 / a + ((t00 / a) ** 2 - 2.0 * g * terrain / a / r_d) ** 0.5)
    mub = p_surf - p_top
    kde = len(znw)
    phb = [terrain * g]
    for k in range(1, kde):
        pb = c.c3h[k - 1] * mub + c.c4h[k - 1] + p_top
        temp = np.maximum(s.iso_temp, t00 + a * np.log(pb / p00))
        if s.base_pres_strat > 0:
            temp = np.where(
                pb < s.base_pres_strat,
                s.iso_temp + s.base_lapse_strat * np.log(pb / s.base_pres_strat),
                temp,
            )
        t_init = temp * (p00 / pb) ** (r_d / cp) - vertical.T0
        alb = (
            (r_d / vertical.P1000MB)
            * (t_init + vertical.T0)
            * (pb / vertical.P1000MB) ** vertical.CVPM
        )
        if s.hypsometric_opt == 1:
            dnw = znw[k] - znw[k - 1]
            phb.append(phb[-1] - dnw * (c.c1h[k - 1] * mub + c.c2h[k - 1]) * alb)
        else:
            pfu = c.c3f[k] * mub + c.c4f[k] + p_top
            pfd = c.c3f[k - 1] * mub + c.c4f[k - 1] + p_top
            phb.append(phb[-1] + alb * pb * np.log(pfd / pfu))
    return np.stack(phb) / g


def _floats(values: np.ndarray) -> str:
    return base64.b64encode(np.ascontiguousarray(values, dtype="<f4").tobytes()).decode("ascii")


def scene(
    case: Case,
    domain: int = 1,
    geo_em: Path | None = None,
    geog: Path | list[Path] | None = None,
    cache: Path | None = None,
    fetch: Callable[[str], bytes] = download_tile,
    tiles_first: bool = False,
) -> dict[str, Any]:
    """The scene of a domain over the first relief that can be read: ``geo_em``, then each
    ``geog`` folder (searched below), then the tiles (with a ``cache`` folder), else flat;
    ``tiles_first``: the tiles before the others (chosen in the view)."""
    if not 1 <= domain <= case.max_dom:
        raise ValueError(tr(f"Domain {domain} does not exist", f"Le domaine {domain} n'existe pas"))
    points = samples(case, domain)
    fine, factor = refined(case, domain, points)
    extent = domain_extents(case.grid)[domain - 1]
    fine_spacing = float(fine.xs[1] - fine.xs[0]) if len(fine.xs) > 1 else extent.dx
    problems: list[str] = []
    geogs = [] if geog is None else [geog] if isinstance(geog, Path) else geog

    terrain: np.ndarray | None = None
    display: np.ndarray | None = None
    source: Source = "flat"
    detail = ""

    # Each source sets the terrain when it can be read, else says why
    def from_file() -> None:
        nonlocal terrain, source, detail
        try:
            terrain, source, detail = (
                from_geo_em(geo_em, case, domain, points),  # type: ignore[arg-type]
                "geo_em",
                str(geo_em),
            )
        except (OSError, KeyError, ValueError) as error:
            problems.append(
                tr(
                    f"Unreadable geo_em ({geo_em}): {error}",
                    f"geo_em illisible ({geo_em}) : {error}",
                )
            )

    def from_geography(root: Path) -> None:
        nonlocal terrain, display, source, detail
        folder = geog_topography(root)
        if folder is None:
            problems.append(tr(f"No geography in {root}", f"Pas de géographie dans {root}"))
            return
        try:
            display = from_wps_geog(folder, fine.lat, fine.lon)
            terrain, source, detail = cell_means(display, factor), "wps_geog", str(folder)
        except (OSError, KeyError, ValueError) as error:
            problems.append(
                tr(
                    f"Unreadable geography ({folder}): {error}",
                    f"Géographie illisible ({folder}) : {error}",
                )
            )

    def from_public_tiles() -> None:
        nonlocal terrain, display, source, detail
        try:
            display = from_tiles(fine.lat, fine.lon, fine_spacing, cache, fetch)  # type: ignore[arg-type]
            terrain, source, detail = (
                cell_means(display, factor),
                "tiles",
                "Terrarium (Mapzen, AWS Open Data)",
            )
        except (OSError, ValueError) as error:
            problems.append(
                tr(
                    f"Public tiles unavailable: {error}",
                    f"Tuiles publiques indisponibles : {error}",
                )
            )

    attempts: list[Callable[[], None]] = [from_file] if geo_em is not None else []
    attempts += [partial(from_geography, root) for root in geogs]
    if cache is not None:
        attempts = [from_public_tiles, *attempts] if tiles_first else [*attempts, from_public_tiles]
    for attempt in attempts:
        if terrain is not None:
            break
        attempt()
    if terrain is None:
        terrain = np.zeros(points.lat.shape)
    terrain = np.maximum(terrain, 0.0)  # water at 0 m, as HGT_M over the sea
    if display is None:
        display = upsample(terrain, factor)
    display_source = source

    settings = vertical.settings(case)
    znw = vertical.full_levels(settings)
    coefficients = vertical.coefficients(znw, settings.hybrid_opt, settings.etac, settings.p_top)
    heights = columns(settings, znw, coefficients, terrain)

    cx, cy = (extent.west + extent.east) / 2, (extent.south + extent.north) / 2
    proj = projection_for(case.grid.projection)

    def km(x: float, y: float) -> tuple[float, float]:
        return (x - cx) / 1000, (y - cy) / 1000

    domains = []
    for number, (e, spec) in enumerate(
        zip(domain_extents(case.grid), case.grid.domains, strict=True), 1
    ):
        x0, y0 = km(e.west, e.south)
        x1, y1 = km(e.east, e.north)
        # The real cells of each domain: their size and number (the view draws them)
        domains.append(
            {
                "number": number,
                "west": x0,
                "south": y0,
                "east": x1,
                "north": y1,
                "dx_km": e.dx / 1000,
                "cells_x": spec.e_we - 1,
                "cells_y": spec.e_sn - 1,
                "parent": spec.parent_id if number > 1 else 0,
            }
        )
    types = turbine_types(case)
    turbines = []
    for farm in case.farms:
        for turbine in farm.turbines:
            x, y = proj.forward(turbine.lat, turbine.lon)
            if not (extent.west <= x <= extent.east and extent.south <= y <= extent.north):
                continue
            model = types.get(turbine.type)
            kx, ky = km(x, y)
            turbines.append(
                {
                    "x": kx,
                    "y": ky,
                    "farm": farm.id,
                    "hub_m": model.hub_height_m if model else None,
                    "rotor_m": model.rotor_diameter_m if model else None,
                }
            )
    sea_levels = vertical.column(settings, znw, coefficients, 0.0)
    return {
        "domain": domain,
        "source": source,
        "source_detail": detail,
        "problems": problems,
        "nx": len(points.xs),
        "ny": len(points.ys),
        "xs_km": [(float(x) - cx) / 1000 for x in points.xs],
        "ys_km": [(float(y) - cy) / 1000 for y in points.ys],
        "terrain_m": _floats(terrain),
        # Finer terrain for the eye only (depths below 0 m kept for the colour of the sea)
        "display": {
            "source": display_source,
            "factor": factor,
            "nx": len(fine.xs),
            "ny": len(fine.ys),
            "terrain_m": _floats(display),
        },
        # B(eta) of every full level: how much of the terrain a level follows (1 at the
        # ground, 0 above etac), to lay the levels on the finer terrain in the view
        "b_full": list(coefficients.c3f),
        "levels": len(znw),
        "heights_m": _floats(heights),
        "sea_level_heights_m": sea_levels,
        "hybrid_opt": settings.hybrid_opt,
        "domains": domains,
        "turbines": turbines,
        "farms": [{"id": farm.id, "name": farm.name} for farm in case.farms],
    }
