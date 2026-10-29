"""Read turbine or mast coordinates pasted from a spreadsheet, a CSV or a text file.

Accepted: tab, semicolon, comma or space separated columns; decimal points or commas (French
spreadsheets); an optional header naming the columns; latitude/longitude in either order, or
projected coordinates (UTM zone or any EPSG code). Without a header, the column order is the
one placing the points closest to the domain.
"""

import math
import re
from dataclasses import dataclass, field
from typing import Literal

from owstudio.core.i18n import tr

Crs = Literal["auto", "latlon", "lonlat", "projected"]

LAT_NAMES = {"lat", "latitude", "y_lat"}
LON_NAMES = {"lon", "long", "lng", "longitude", "x_lon"}
NORTHING_NAMES = {"northing", "north", "n", "y", "nord"}
EASTING_NAMES = {"easting", "east", "e", "x", "est"}
TYPE_NAMES = {"type", "turbine_type", "wtg_type", "model"}
NAME_NAMES = {"name", "id", "label", "wtg", "turbine", "station", "nom"}


@dataclass(frozen=True)
class ParsedPoint:
    lat: float
    lon: float
    type: int | None = None
    name: str | None = None


@dataclass
class ParsedPoints:
    points: list[ParsedPoint] = field(default_factory=list)
    skipped: list[int] = field(default_factory=list)  # 1-based line numbers
    detected: str = ""


class CoordinateError(ValueError):
    pass


def _split(line: str, delimiter: str | None) -> list[str]:
    parts = line.split(delimiter) if delimiter else line.split()
    return [p.strip().strip('"').strip("'") for p in parts]


def _number(text: str, decimal_comma: bool) -> float | None:
    text = text.replace(" ", "").replace(" ", "")
    if decimal_comma:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _detect_delimiter(lines: list[str]) -> tuple[str | None, bool]:
    """Delimiter (None for whitespace) and whether commas are decimal separators."""
    sample = lines[:20]
    if any("\t" in line for line in sample):
        return "\t", any(re.search(r"\d,\d", line) for line in sample)
    if any(";" in line for line in sample):
        return ";", any(re.search(r"\d,\d", line) for line in sample)
    if all(line.count(",") >= 1 for line in sample if re.search(r"\d", line)):
        # "55.48,7.84" separates with commas; "55,48 7,84" uses decimal commas
        if any(re.search(r"\d\.\d", line) for line in sample) or not any(
            " " in line.strip() for line in sample
        ):
            return ",", False
        return None, True
    return None, False


def _header_roles(tokens: list[str]) -> dict[str, int]:
    roles: dict[str, int] = {}
    for index, token in enumerate(tokens):
        key = re.sub(r"[^a-z_]", "", token.lower().replace(" ", "_"))
        for role, names in (
            ("lat", LAT_NAMES),
            ("lon", LON_NAMES),
            ("northing", NORTHING_NAMES),
            ("easting", EASTING_NAMES),
            ("type", TYPE_NAMES),
            ("name", NAME_NAMES),
        ):
            if key in names and role not in roles:
                roles[role] = index
    return roles


def _distance_deg(points: list[tuple[float, float]], near: tuple[float, float]) -> float:
    lat0, lon0 = near
    return sum(
        math.hypot(lat - lat0, (lon - lon0) * math.cos(math.radians(lat0))) for lat, lon in points
    )


def _to_geographic(xy: list[tuple[float, float]], epsg: int) -> list[tuple[float, float]]:
    from pyproj import Transformer

    try:
        transformer = Transformer.from_crs(epsg, 4326, always_xy=True)
    except Exception as error:
        raise CoordinateError(
            tr(
                f"Unknown coordinate system EPSG:{epsg}",
                f"Système de coordonnées inconnu EPSG:{epsg}",
            )
        ) from error
    return [(lat, lon) for lon, lat in (transformer.transform(x, y) for x, y in xy)]


def utm_epsg(zone: int, southern: bool) -> int:
    if not 1 <= zone <= 60:
        raise CoordinateError(tr("UTM zones go from 1 to 60", "Les zones UTM vont de 1 à 60"))
    return (32700 if southern else 32600) + zone


def parse_coordinates(
    text: str,
    crs: Crs = "auto",
    epsg: int | None = None,
    near: tuple[float, float] | None = None,
) -> ParsedPoints:
    raw_lines = text.splitlines()
    numbered = [
        (n + 1, line)
        for n, line in enumerate(raw_lines)
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not numbered:
        raise CoordinateError(tr("Nothing to read", "Rien à lire"))
    delimiter, decimal_comma = _detect_delimiter([line for _, line in numbered])

    first = _split(numbered[0][1], delimiter)
    has_header = all(_number(t, decimal_comma) is None for t in first[:2]) or (
        any(re.search(r"[a-zA-Z]{2,}", t) for t in first)
        and sum(_number(t, decimal_comma) is not None for t in first) < 2
    )
    roles = _header_roles(first) if has_header else {}
    rows = numbered[1:] if has_header else numbered

    result = ParsedPoints()
    pairs: list[tuple[float, float]] = []
    extras: list[tuple[int | None, str | None]] = []
    for line_number, line in rows:
        tokens = _split(line, delimiter)
        numbers = [(i, _number(t, decimal_comma)) for i, t in enumerate(tokens)]
        if roles and {"lat", "lon"} <= roles.keys():
            a_index, b_index = roles["lat"], roles["lon"]
        elif roles and {"northing", "easting"} <= roles.keys():
            a_index, b_index = roles["easting"], roles["northing"]
        else:
            numeric = [i for i, v in numbers if v is not None]
            if len(numeric) < 2:
                result.skipped.append(line_number)
                continue
            a_index, b_index = numeric[0], numeric[1]
        a = numbers[a_index][1] if a_index < len(numbers) else None
        b = numbers[b_index][1] if b_index < len(numbers) else None
        if a is None or b is None:
            result.skipped.append(line_number)
            continue
        type_value = None
        if "type" in roles and roles["type"] < len(numbers):
            value = numbers[roles["type"]][1]
            type_value = (
                int(value) if value is not None and value.is_integer() and value >= 1 else None
            )
        elif not roles:
            rest = [v for i, v in numbers if v is not None and i > b_index]
            if rest and rest[0].is_integer() and 1 <= rest[0] <= 99:
                type_value = int(rest[0])
        name = None
        if "name" in roles and roles["name"] < len(tokens):
            name = tokens[roles["name"]] or None
        elif not roles and numbers and numbers[0][1] is None:
            name = tokens[0] or None
        pairs.append((a, b))
        extras.append((type_value, name))

    if not pairs:
        raise CoordinateError(
            tr(
                "No coordinates found: expected two numeric columns",
                "Aucune coordonnée trouvée : deux colonnes de nombres sont attendues",
            )
        )

    projected = crs == "projected" or (
        crs == "auto" and any(abs(a) > 360 or abs(b) > 360 for a, b in pairs)
    )
    if projected:
        if epsg is None:
            raise CoordinateError(
                tr(
                    "These look like projected coordinates (UTM?): choose the UTM zone or EPSG code",
                    "Ces coordonnées semblent projetées (UTM ?) : choisissez la zone UTM ou le code EPSG",
                )
            )
        if roles and {"northing", "easting"} <= roles.keys():
            xy = pairs  # read as (easting, northing)
        else:
            # Northings are larger than eastings except near the equator
            xy = (
                pairs
                if sum(b > a for a, b in pairs) >= len(pairs) / 2
                else [(b, a) for a, b in pairs]
            )
        latlon = _to_geographic(xy, epsg)
        result.detected = tr(f"Projected, EPSG:{epsg}", f"Projetées, EPSG:{epsg}")
    else:
        if roles and {"lat", "lon"} <= roles.keys():
            order = "latlon"  # read by column name, whatever the column order
        elif crs in ("latlon", "lonlat"):
            order = crs
        elif any(abs(a) > 90 for a, _ in pairs):
            order = "lonlat"
        elif any(abs(b) > 90 for _, b in pairs):
            order = "latlon"
        elif near is not None:
            as_latlon = _distance_deg(pairs, near)
            as_lonlat = _distance_deg([(b, a) for a, b in pairs], near)
            order = "latlon" if as_latlon <= as_lonlat else "lonlat"
        else:
            order = "latlon"
        latlon = pairs if order == "latlon" else [(b, a) for a, b in pairs]
        result.detected = "Latitude, longitude" if order == "latlon" else "Longitude, latitude"
    if decimal_comma:
        result.detected += tr(" · decimal commas", " · virgules décimales")

    for (lat, lon), (type_value, name) in zip(latlon, extras, strict=True):
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise CoordinateError(
                tr(
                    f"Coordinate out of range: {lat:.4f}, {lon:.4f}",
                    f"Coordonnée hors limites : {lat:.4f}, {lon:.4f}",
                )
            )
        result.points.append(ParsedPoint(round(lat, 6), round(lon, 6), type_value, name))
    return result
