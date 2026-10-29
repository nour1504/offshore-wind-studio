"""Read-only geographic imports, metric layout previews and namelist-to-draft import.

Coordinates returned to the interface always use GeoJSON order (longitude, latitude), WGS84.
The source files are never edited. The layout is a geometric proposal, not a wake optimiser.

References:
https://www2.mmm.ucar.edu/wrf/users/wrf_users_guide/build/html/wps.html
https://www2.mmm.ucar.edu/wrf/users/wrf_users_guide/build/html/namelist_variables.html
https://f90nml.readthedocs.io/en/latest/usage.html
https://pyproj4.github.io/pyproj/stable/api/transformer.html
https://docs.ogc.org/is/12-007r2/12-007r2.html
"""

import codecs
import json
import math
import xml.etree.ElementTree as ET
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import f90nml
import numpy as np
import shapefile
from numpy.typing import NDArray
from pyproj import CRS, Transformer
from shapely import affinity, force_2d, transform
from shapely.geometry import Point, Polygon, mapping, shape
from shapely.geometry.base import BaseGeometry

from owstudio.core.case.model import Case, Domain, FarmScheme, Grid, Period, Projection
from owstudio.core.domains import EARTH_RADIUS_M
from owstudio.core.i18n import tr
from owstudio.core.namelist.generate import build_namelist_input, build_namelist_wps

MAX_FILE_BYTES = 50_000_000
MAX_FEATURES = 20_000
MAX_COORDINATES = 200_000
MAX_TURBINES = 10_000
MAX_CANDIDATES = 250_000
MAX_NAMELIST_CHARS = 2_000_000


def _project(geometry: BaseGeometry, transformer: Transformer) -> BaseGeometry:
    """The Shapely >=2.0 array API, avoiding the deprecated ops.transform function."""

    def coordinates(values: NDArray[np.float64]) -> NDArray[np.float64]:
        x, y = transformer.transform(values[:, 0], values[:, 1], errcheck=True)
        return np.column_stack((x, y))

    return cast(BaseGeometry, transform(geometry, coordinates))


def _bounded_read(path: Path) -> bytes:
    if not path.is_file():
        raise FileNotFoundError(tr(f"File not found: {path}", f"Fichier introuvable : {path}"))
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(
            tr(
                "Map import files are limited to 50 MB",
                "Les fichiers de carte importés sont limités à 50 Mo",
            )
        )
    data = path.read_bytes()
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(
            tr(
                "Map import files are limited to 50 MB",
                "Les fichiers de carte importés sont limités à 50 Mo",
            )
        )
    return data


def _json_value(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    return value


class _NoDtd(ET.TreeBuilder):
    def doctype(self, name: str, pubid: str | None, system: str | None) -> None:
        raise ValueError(
            tr(
                "KML DTDs and entity declarations are not supported",
                "Les DTD et déclarations d'entités KML ne sont pas acceptées",
            )
        )


def _tag(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _kml_coordinates(element: ET.Element) -> list[list[float]]:
    text = next((e.text for e in element.iter() if _tag(e) == "coordinates"), None)
    if not text:
        raise ValueError(
            tr("KML geometry has no coordinates", "La géométrie KML n'a pas de coordonnées")
        )
    result = []
    for token in text.split():
        parts = token.split(",")
        if len(parts) < 2:
            raise ValueError(
                tr(
                    "KML coordinates must use longitude,latitude[,altitude]",
                    "Les coordonnées KML doivent être longitude,latitude[,altitude]",
                )
            )
        result.append([float(part) for part in parts[:3]])
        if len(result) > MAX_COORDINATES:
            raise ValueError(tr("Too many map coordinates", "Trop de coordonnées de carte"))
    return result


def _kml_geometry(element: ET.Element) -> dict[str, Any] | None:
    kind = _tag(element)
    if kind == "Point":
        coordinates = _kml_coordinates(element)
        if len(coordinates) != 1:
            raise ValueError(
                tr(
                    "A KML Point must have exactly one coordinate",
                    "Un Point KML doit avoir exactement une coordonnée",
                )
            )
        return {"type": "Point", "coordinates": coordinates[0]}
    if kind in ("LineString", "LinearRing"):
        return {"type": "LineString", "coordinates": _kml_coordinates(element)}
    if kind == "Polygon":
        outer = [e for e in element if _tag(e) == "outerBoundaryIs"]
        inner = [e for e in element if _tag(e) == "innerBoundaryIs"]
        if len(outer) != 1:
            raise ValueError(
                tr(
                    "A KML polygon must have exactly one outer boundary",
                    "Un polygone KML doit avoir exactement un contour extérieur",
                )
            )
        return {"type": "Polygon", "coordinates": [_kml_coordinates(e) for e in outer + inner]}
    if kind == "MultiGeometry":
        geometries = [geometry for child in element if (geometry := _kml_geometry(child))]
        return {"type": "GeometryCollection", "geometries": geometries}
    return None


def _kml(data: bytes) -> list[dict[str, Any]]:
    root = ET.fromstring(data, parser=ET.XMLParser(target=_NoDtd()))
    if _tag(root) != "kml":
        raise ValueError(
            tr("The file is not a KML document", "Le fichier n'est pas un document KML")
        )
    features = []
    for placemark in root.iter():
        if _tag(placemark) != "Placemark":
            continue
        properties: dict[str, Any] = {}
        for child in placemark:
            if _tag(child) in ("name", "description"):
                properties[_tag(child)] = child.text or ""
        for field in placemark.iter():
            if _tag(field) in ("Data", "SimpleData") and field.get("name"):
                value = next((e.text for e in field if _tag(e) == "value"), field.text)
                properties[str(field.get("name"))] = value or ""
        geometries = [geometry for child in placemark if (geometry := _kml_geometry(child))]
        for geometry in geometries:
            features.append({"type": "Feature", "geometry": geometry, "properties": properties})
        if len(features) > MAX_FEATURES:
            raise ValueError(
                tr(
                    "Map imports are limited to 20 000 features",
                    "Les imports de carte sont limités à 20 000 objets",
                )
            )
    return features


def _geojson(data: bytes) -> tuple[list[dict[str, Any]], Any]:
    document = json.loads(data.decode("utf-8-sig"))
    if not isinstance(document, dict):
        raise TypeError(tr("GeoJSON must be an object", "Le GeoJSON doit être un objet"))
    kind = document.get("type")
    if kind == "FeatureCollection":
        features = document.get("features")
        if not isinstance(features, list):
            raise ValueError(
                tr(
                    "GeoJSON FeatureCollection needs a features array",
                    "Une FeatureCollection GeoJSON demande un tableau features",
                )
            )
    elif kind == "Feature":
        features = [document]
    elif kind in (
        "Point",
        "MultiPoint",
        "LineString",
        "MultiLineString",
        "Polygon",
        "MultiPolygon",
        "GeometryCollection",
    ):
        features = [{"type": "Feature", "geometry": document, "properties": {}}]
    else:
        raise ValueError(
            tr(f"Unsupported GeoJSON type: {kind}", f"Type GeoJSON non pris en charge : {kind}")
        )
    declared = document.get("crs")
    name = None
    if declared is not None:
        if not isinstance(declared, dict) or not isinstance(declared.get("properties"), dict):
            raise ValueError(
                tr(
                    "GeoJSON CRS must declare a named source CRS",
                    "Le CRS du GeoJSON doit déclarer un système de coordonnées nommé",
                )
            )
        name = declared["properties"].get("name")
        if not isinstance(name, str) or not name:
            raise ValueError(
                tr(
                    "GeoJSON CRS must declare a named source CRS",
                    "Le CRS du GeoJSON doit déclarer un système de coordonnées nommé",
                )
            )
    return features, name


def _coordinates(geometry: dict[str, Any], depth: int = 0) -> list[tuple[float, float]]:
    if depth > 5 or not isinstance(geometry, dict):
        raise ValueError(
            tr(
                "Invalid or excessively nested map geometry",
                "Géométrie de carte invalide ou trop imbriquée",
            )
        )
    if geometry.get("type") == "GeometryCollection":
        geometries = geometry.get("geometries", [])
        if not isinstance(geometries, list):
            raise ValueError(
                tr(
                    "GeometryCollection needs a geometries array",
                    "Une GeometryCollection demande un tableau geometries",
                )
            )
        collection_coordinates = []
        for child in geometries:
            collection_coordinates.extend(_coordinates(child, depth + 1))
            if len(collection_coordinates) > MAX_COORDINATES:
                raise ValueError(tr("Too many map coordinates", "Trop de coordonnées de carte"))
        return collection_coordinates
    result: list[tuple[float, float]] = []

    def walk(value: Any, depth: int = 0) -> None:
        if depth > 5 or not isinstance(value, (list, tuple)):
            raise ValueError(tr("Invalid map coordinates", "Coordonnées de carte invalides"))
        if len(value) >= 2 and all(
            isinstance(x, (int, float)) and not isinstance(x, bool) for x in value
        ):
            if not all(math.isfinite(x) for x in value):
                raise ValueError(
                    tr(
                        "Map coordinates must be finite",
                        "Les coordonnées de carte doivent être finies",
                    )
                )
            result.append((float(value[0]), float(value[1])))
            if len(result) > MAX_COORDINATES:
                raise ValueError(tr("Too many map coordinates", "Trop de coordonnées de carte"))
        else:
            for child in value:
                walk(child, depth + 1)

    walk(geometry.get("coordinates", []))
    return result


def import_map(path: Path, crs: str | None = None) -> dict[str, Any]:
    """Import a local map file and normalize all geometries to WGS84, always x/y order."""
    data = _bounded_read(path)
    suffix = path.suffix.lower()
    warnings: list[str] = []
    declared: Any = None
    if suffix in (".geojson", ".json"):
        features, declared = _geojson(data)
    elif suffix == ".kml":
        features = _kml(data)
        if crs and CRS.from_user_input(crs) != CRS.from_epsg(4326):
            raise ValueError(
                tr(
                    "KML coordinates are always WGS84 longitude/latitude",
                    "Les coordonnées KML sont toujours en longitude/latitude WGS84",
                )
            )
        warnings.append(
            tr(
                "KML styles, altitude modes and network links are not imported; no remote resources are loaded.",
                "Les styles, modes d'altitude et liens réseau du KML ne sont pas importés ; aucune ressource distante n'est chargée.",
            )
        )
    elif suffix == ".shp":
        # The .shp has already been checked; sidecars are local files, never ZIP/URL sources.
        for extension in (".shx", ".dbf"):
            if path.with_suffix(extension).exists():
                _bounded_read(path.with_suffix(extension))
        projection = path.with_suffix(".prj")
        if projection.exists():
            declared = _bounded_read(projection).decode("utf-8-sig").strip()
        if not crs and not declared:
            raise ValueError(
                tr(
                    "A shapefile needs its .prj file or an explicit source CRS (for example EPSG:32632)",
                    "Un shapefile demande son fichier .prj ou un système de coordonnées explicite (par exemple EPSG:32632)",
                )
            )
        features = []
        encoding = "utf-8"
        codepage = path.with_suffix(".cpg")
        if codepage.exists():
            encoding = _bounded_read(codepage).decode("ascii").strip()
            if encoding.isdigit():
                encoding = "utf-8" if encoding == "65001" else f"cp{encoding}"
            try:
                codecs.lookup(encoding)
            except LookupError as error:
                raise ValueError(
                    tr(
                        f"Unknown shapefile text encoding: {encoding}",
                        f"Encodage de texte du shapefile inconnu : {encoding}",
                    )
                ) from error
        with shapefile.Reader(str(path), encoding=encoding) as reader:
            if len(reader) > MAX_FEATURES:
                raise ValueError(
                    tr(
                        "Map imports are limited to 20 000 features",
                        "Les imports de carte sont limités à 20 000 objets",
                    )
                )
            for record in reader.iterShapeRecords():
                if record.shape.shapeType == shapefile.NULL:
                    warnings.append(
                        tr(
                            "A shapefile feature with no geometry was skipped.",
                            "Un objet du shapefile sans géométrie a été ignoré.",
                        )
                    )
                    continue
                features.append(
                    {
                        "type": "Feature",
                        "geometry": record.shape.__geo_interface__,
                        "properties": _json_value(record.record.as_dict()),
                    }
                )
    else:
        raise ValueError(
            tr(
                "Choose a GeoJSON (.geojson/.json), KML (.kml) or shapefile (.shp)",
                "Choisissez un GeoJSON (.geojson/.json), un KML (.kml) ou un shapefile (.shp)",
            )
        )
    if len(features) > MAX_FEATURES:
        raise ValueError(
            tr(
                "Map imports are limited to 20 000 features",
                "Les imports de carte sont limités à 20 000 objets",
            )
        )
    source = CRS.from_user_input(crs or declared or "EPSG:4326")
    transformer = Transformer.from_crs(source, "EPSG:4326", always_xy=True)
    converted = []
    count = 0
    for feature in features:
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ValueError(
                tr(
                    "Every GeoJSON item must be a Feature",
                    "Chaque élément du GeoJSON doit être une Feature",
                )
            )
        geometry = feature.get("geometry")
        if geometry is None:
            warnings.append(
                tr(
                    "A feature with no geometry was skipped.",
                    "Un objet sans géométrie a été ignoré.",
                )
            )
            continue
        if not isinstance(geometry, dict):
            raise TypeError(
                tr(
                    "Feature geometry must be an object",
                    "La géométrie d'une Feature doit être un objet",
                )
            )
        count += len(_coordinates(geometry))
        if count > MAX_COORDINATES:
            raise ValueError(
                tr(
                    "Map imports are limited to 200 000 coordinates",
                    "Les imports de carte sont limités à 200 000 coordonnées",
                )
            )
        native = shape(geometry)
        if native.has_z:
            warnings.append(
                tr(
                    "Map geometry is imported in two dimensions; altitude coordinates are omitted.",
                    "La géométrie est importée en deux dimensions ; les altitudes sont omises.",
                )
            )
        transformed = _project(force_2d(native), transformer)
        if transformed.is_empty:
            warnings.append(
                tr("An empty geometry was skipped.", "Une géométrie vide a été ignorée.")
            )
            continue
        normalized = _json_value(mapping(transformed))
        for lon, lat in _coordinates(normalized):
            if not (-180 <= lon <= 180 and -90 <= lat <= 90):
                raise ValueError(
                    tr(
                        "Transformed coordinates are outside WGS84 longitude/latitude bounds; check the source CRS",
                        "Les coordonnées transformées sortent des bornes de longitude/latitude WGS84 ; vérifiez le système de coordonnées de la source",
                    )
                )
        if not transformed.is_valid:
            warnings.append(
                tr(
                    "An invalid geometry was retained for display; repair it before generating a turbine layout.",
                    "Une géométrie invalide est gardée pour l'affichage ; réparez-la avant de générer une implantation d'éoliennes.",
                )
            )
        properties = feature.get("properties")
        if properties is None:
            properties = {}
        if not isinstance(properties, dict):
            raise TypeError(
                tr(
                    "Feature properties must be an object or null",
                    "Les propriétés d'une Feature doivent être un objet ou null",
                )
            )
        item = {"type": "Feature", "geometry": normalized, "properties": _json_value(properties)}
        if "id" in feature:
            item["id"] = feature["id"]
        converted.append(item)
    json.dumps(converted, allow_nan=False)
    points: list[dict[str, Any]] = []
    polygons: list[dict[str, Any]] = []

    def collect(geometry: dict[str, Any], properties: dict[str, Any], index: int) -> None:
        kind = geometry["type"]
        coords = geometry.get("coordinates", [])
        name = str(
            properties.get("name") or properties.get("label") or properties.get("id") or index
        )
        if kind == "Point":
            requested = properties.get("type", 1)
            turbine_type = int(requested) if str(requested).isdigit() and int(requested) >= 1 else 1
            points.append(
                {"lon": coords[0], "lat": coords[1], "type": turbine_type, "id": name[:32]}
            )
        elif kind == "MultiPoint":
            for coordinate in coords:
                collect({"type": "Point", "coordinates": coordinate}, properties, index)
        elif kind == "Polygon":
            polygons.append(
                {
                    "id": f"polygon-{len(polygons) + 1}",
                    "name": name,
                    "rings": [[coordinate[:2] for coordinate in ring] for ring in coords],
                }
            )
        elif kind == "MultiPolygon":
            for polygon in coords:
                collect({"type": "Polygon", "coordinates": polygon}, properties, index)
        elif kind == "GeometryCollection":
            for child in geometry.get("geometries", []):
                collect(child, properties, index)

    for index, feature in enumerate(converted, 1):
        collect(feature["geometry"], feature["properties"], index)
    return {
        "collection": {"type": "FeatureCollection", "features": converted},
        "points": points,
        "polygons": polygons,
        "warnings": list(dict.fromkeys(warnings)),
        "crs": "EPSG:4326",
    }


def turbine_layout(
    polygon: list[list[float]],
    spacing_m: float,
    rotation_deg: float,
    turbine_type: int,
    holes: list[list[list[float]]] | None = None,
    spacing_across_m: float | None = None,
    stagger: float = 0.0,
    setback_m: float = 0.0,
) -> dict[str, Any]:
    """Metric lattice rotated clockwise from east/north, strictly capped at 10 000: `spacing_m`
    along the rows, `spacing_across_m` between the rows (the same by default), every other row
    shifted by `stagger` x `spacing_m` (0 aligned, 0.5 staggered), and no turbine closer than
    `setback_m` to the edge of the zone."""
    if not math.isfinite(spacing_m) or spacing_m <= 0:
        raise ValueError(
            tr(
                "Turbine spacing must be positive and finite (metres)",
                "L'espacement des éoliennes doit être positif et fini (mètres)",
            )
        )
    across = spacing_m if spacing_across_m is None else spacing_across_m
    if not math.isfinite(across) or across <= 0 or not 0 <= stagger < 1 or not 0 <= setback_m < 1e6:
        raise ValueError(
            tr(
                "Spacing between rows must be positive, stagger from 0 to 1 and setback positive",
                "L'espacement entre rangées doit être positif, le décalage de 0 à 1 et la marge positive",
            )
        )
    if not math.isfinite(rotation_deg) or turbine_type < 1:
        raise ValueError(
            tr(
                "Rotation must be finite and turbine type must be positive",
                "La rotation doit être finie et le modèle d'éolienne positif",
            )
        )
    rings = [polygon, *(holes or [])]
    if sum(len(ring) for ring in rings) > MAX_COORDINATES:
        raise ValueError(tr("Too many polygon coordinates", "Trop de coordonnées dans le polygone"))
    for ring in rings:
        if len(ring) < 3 or any(
            len(pair) != 2
            or not all(math.isfinite(x) for x in pair)
            or not -180 <= pair[0] <= 180
            or not -90 <= pair[1] <= 90
            for pair in ring
        ):
            raise ValueError(
                tr(
                    "Polygon rings need at least three finite [longitude, latitude] pairs",
                    "Les contours d'un polygone demandent au moins trois paires [longitude, latitude] finies",
                )
            )
    lons = [pair[0] for pair in polygon]
    lats = [pair[1] for pair in polygon]
    if max(lons) - min(lons) > 180:
        raise ValueError(
            tr(
                "Split a polygon crossing the antimeridian before generating a layout",
                "Coupez un polygone qui traverse l'antiméridien avant de générer une implantation",
            )
        )
    lon0, lat0 = (max(lons) + min(lons)) / 2, (max(lats) + min(lats)) / 2
    projection = f"+proj=aeqd +lat_0={lat0} +lon_0={lon0} +datum=WGS84 +units=m +no_defs"
    forward = Transformer.from_crs("EPSG:4326", projection, always_xy=True)
    inverse = Transformer.from_crs(projection, "EPSG:4326", always_xy=True)
    geographic = Polygon(polygon, holes=holes)
    if not geographic.is_valid or geographic.is_empty or geographic.area <= 0:
        raise ValueError(
            tr(
                "The layout polygon is empty or invalid (self-intersection or invalid holes)",
                "Le polygone d'implantation est vide ou invalide (il se recoupe ou ses trous sont invalides)",
            )
        )
    metric = _project(geographic, forward)
    if metric.is_empty or not metric.is_valid or not all(math.isfinite(v) for v in metric.bounds):
        raise ValueError(
            tr(
                "The polygon cannot be projected to a valid local metric area",
                "Le polygone ne peut pas être projeté en une zone métrique locale valide",
            )
        )
    if max(metric.bounds[2] - metric.bounds[0], metric.bounds[3] - metric.bounds[1]) > 500_000:
        raise ValueError(
            tr(
                "Layout areas must be smaller than 500 km; split this zone into local areas",
                "Les zones d'implantation doivent faire moins de 500 km ; découpez cette zone en zones locales",
            )
        )
    angle = rotation_deg % 360
    aligned = affinity.rotate(metric, angle, origin=(0, 0))
    xmin, ymin, xmax, ymax = aligned.bounds
    # The setback: positions only inside the zone shrunk by that distance
    inside = aligned.buffer(-setback_m) if setback_m > 0 else aligned
    first_x, last_x = math.floor(xmin / spacing_m) - 1, math.ceil(xmax / spacing_m)
    first_y, last_y = math.ceil(ymin / across), math.floor(ymax / across)
    candidates = max(0, last_x - first_x + 1) * max(0, last_y - first_y + 1)
    if candidates > MAX_CANDIDATES:
        raise ValueError(
            tr(
                "The requested grid is too dense; increase the spacing (limit 10 000 turbines)",
                "La grille demandée est trop dense ; augmentez l'espacement (limite : 10 000 éoliennes)",
            )
        )
    points: list[dict[str, Any]] = []
    for j in range(first_y, last_y + 1):
        shift = (j % 2) * stagger * spacing_m
        for i in range(first_x, last_x + 1):
            point = Point(i * spacing_m + shift, j * across)
            if inside.is_empty or not inside.covers(point):
                continue
            unrotated = affinity.rotate(point, -angle, origin=(0, 0))
            lon, lat = inverse.transform(unrotated.x, unrotated.y, errcheck=True)
            points.append(
                {"lon": lon, "lat": lat, "type": turbine_type, "id": f"T{len(points) + 1:04d}"}
            )
            if len(points) > MAX_TURBINES:
                raise ValueError(
                    tr(
                        "Layout exceeds 10 000 turbines; increase the spacing",
                        "L'implantation dépasse 10 000 éoliennes ; augmentez l'espacement",
                    )
                )
    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [p["lon"], p["lat"]]},
            "properties": {"type": p["type"], "label": p["id"]},
        }
        for p in points
    ]
    warnings: list[str] = []
    if max(xmax - xmin, ymax - ymin) > 100_000:
        warnings.append(
            tr(
                "This large zone uses a local projection; ground spacing varies away from its centre.",
                "Cette grande zone utilise une projection locale ; l'espacement au sol varie en s'éloignant de son centre.",
            )
        )
    return {
        "points": points,
        "count": len(points),
        "collection": {"type": "FeatureCollection", "features": features},
        "spacing_m": spacing_m,
        "spacing_across_m": across,
        "area_km2": metric.area / 1e6,
        "rotation_deg": angle,
        "projection": projection,
        "warnings": warnings,
    }


def _read_namelist(text: str, label: str) -> dict[str, dict[str, Any]]:
    if not text.strip():
        return {}
    if len(text) > MAX_NAMELIST_CHARS:
        raise ValueError(
            tr(
                f"{label} is limited to 2 million characters",
                f"{label} est limité à 2 millions de caractères",
            )
        )
    try:
        parser = f90nml.Parser()
        parser.global_start_index = 1
        parsed = parser.reads(text)
        data = cast(dict[str, dict[str, Any]], parsed.todict(complex_tuple=True))
        if not data or any(not isinstance(group, dict) for group in data.values()):
            raise ValueError(
                tr("Expected named namelist groups", "Des groupes de namelist nommés sont attendus")
            )
        # The parser's one-based padding preserves partial indexed assignments through the
        # application's plain override dictionaries. Do not drop unknown WRF options.
        for group in data.values():
            indices = group.get("_start_index", {})
            if indices and all(all(i == 1 for i in start) for start in indices.values()):
                group.pop("_start_index", None)
        json.dumps(data, allow_nan=False)
        return data
    except (ValueError, TypeError, KeyError, IndexError, AssertionError) as error:
        raise ValueError(
            tr(f"Cannot parse {label}: {error}", f"Impossible de lire {label} : {error}")
        ) from error


def _value(options: dict[str, Any], key: str, default: Any = None, index: int = 0) -> Any:
    value = options.get(key, default)
    if isinstance(value, list):
        value = value[index] if index < len(value) else default
    return default if value is None else value


def _integer(value: Any, name: str) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or int(value) != value
    ):
        raise ValueError(tr(f"{name} must be an integer", f"{name} doit être un entier"))
    return int(value)


def _fill_sparse(parsed: dict[str, dict[str, Any]], generated: Any) -> bool:
    """Retain unassigned indices of a partial import from the existing generated project.

    Unknown sparse arrays keep explicit null/blank elements, so their Fortran indices survive.
    """
    sparse_unknown = False
    for group, options in parsed.items():
        for key, value in options.items():
            if key.startswith("_") or not isinstance(value, list) or None not in value:
                continue
            base = generated.get(group, {}).get(key)
            for index, item in enumerate(value):
                if item is not None:
                    continue
                original = (
                    base[index]
                    if isinstance(base, list) and index < len(base)
                    else base
                    if index == 0 and not isinstance(base, list)
                    else None
                )
                value[index] = original
                if original is None:
                    sparse_unknown = True
    return sparse_unknown


def _time(options: dict[str, Any], which: str, default: datetime, wps: bool = False) -> datetime:
    text = _value(options, f"{which}_date") if wps else None
    if text:
        parsed = datetime.fromisoformat(str(text).replace("_", "T"))
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    keys = [f"{which}_{part}" for part in ("year", "month", "day", "hour", "minute", "second")]
    if not any(key in options for key in keys):
        return default.replace(tzinfo=UTC) if default.tzinfo is None else default.astimezone(UTC)
    return datetime(
        int(_value(options, keys[0], default.year)),
        int(_value(options, keys[1], default.month)),
        int(_value(options, keys[2], default.day)),
        int(_value(options, keys[3], 0)),
        int(_value(options, keys[4], 0)),
        int(_value(options, keys[5], 0)),
        tzinfo=UTC,
    )


def import_namelists(case: Case, input_text: str = "", wps_text: str = "") -> dict[str, Any]:
    """Return a draft; preserve all imported overrides, and synchronize supported main fields.

    WPS owns horizontal geometry and WRF owns physics, vertical grid and simulation duration.
    Differences and settings beyond the single-period/square-grid Case model are explicit.
    """
    if not input_text.strip() and not wps_text.strip():
        raise ValueError(
            tr(
                "Provide namelist.input or namelist.wps text",
                "Donnez le texte de namelist.input ou de namelist.wps",
            )
        )
    wrf = _read_namelist(input_text, "namelist.input")
    wps = _read_namelist(wps_text, "namelist.wps")
    share, geogrid = wps.get("share", {}), wps.get("geogrid", {})
    control, domains = wrf.get("time_control", {}), wrf.get("domains", {})
    if wps and str(_value(share, "wrf_core", "ARW")).upper() != "ARW":
        raise ValueError(
            tr(
                "Only WRF-ARW namelists are supported",
                "Seules les namelists WRF-ARW sont acceptées",
            )
        )
    warnings = [
        "All imported namelist values remain overrides. Review machine-specific paths and clear an override when you want a graphical setting to control it."
    ]
    sparse_input = _fill_sparse(wrf, build_namelist_input(case))
    sparse_wps = _fill_sparse(wps, build_namelist_wps(case))
    if sparse_input or sparse_wps:
        warnings.append(
            tr(
                "Unknown partial indexed arrays retain blank elements (JSON null) to preserve their Fortran indices; review them in the generated namelist preview.",
                "Les tableaux indexés partiels inconnus gardent des éléments vides (null en JSON) pour conserver leurs indices Fortran ; vérifiez-les dans l'aperçu de la namelist générée.",
            )
        )
    data = case.model_dump()
    for field, parsed in (("namelist_input", wrf), ("namelist_wps", wps)):
        merged = deepcopy(data[field])
        for group, options in parsed.items():
            merged.setdefault(group, {}).update(options)
        data[field] = merged
    wps_count, wrf_count = _value(share, "max_dom"), _value(domains, "max_dom")
    if wps_count is not None and wrf_count is not None and wps_count != wrf_count:
        raise ValueError(
            tr(
                "namelist.wps and namelist.input specify different max_dom values",
                "namelist.wps et namelist.input donnent des max_dom différents",
            )
        )
    count = _integer(
        wps_count
        if wps_count is not None
        else wrf_count
        if wrf_count is not None
        else case.max_dom,
        "max_dom",
    )
    if not 1 <= count <= 99:
        raise ValueError(tr("max_dom must be between 1 and 99", "max_dom doit être entre 1 et 99"))
    horizontal = geogrid or domains
    model_domains = []
    for index in range(count):
        base = (
            case.grid.domains[index]
            if index < case.max_dom
            else Domain(e_we=31, e_sn=31, parent_grid_ratio=3)
        )
        values = base.model_dump()
        for key in (
            "e_we",
            "e_sn",
            "parent_id",
            "parent_grid_ratio",
            "i_parent_start",
            "j_parent_start",
            "geog_data_res",
        ):
            values[key] = _value(horizontal, key, values[key], index)
            if (
                geogrid
                and key in domains
                and key != "geog_data_res"
                and (key != "parent_id" or index > 0)
            ):
                other = _value(domains, key, values[key], index)
                if other != values[key]:
                    raise ValueError(
                        tr(
                            f"Horizontal setting {key} differs between WPS and WRF for domain {index + 1}",
                            f"Le réglage horizontal {key} diffère entre WPS et WRF pour le domaine {index + 1}",
                        )
                    )
        if index == 0:
            values.update(parent_id=1, parent_grid_ratio=1, i_parent_start=1, j_parent_start=1)
        model_domains.append(Domain.model_validate(values))
    projection = case.grid.projection.model_dump()
    for key in ("map_proj", "ref_lat", "ref_lon", "truelat1", "truelat2", "stand_lon"):
        if key in geogrid:
            projection[key] = _value(geogrid, key)
    # namelist.input alone does not define a WPS projection: keep the existing one explicitly.
    if domains and not geogrid:
        warnings.append(
            tr(
                "namelist.input does not define the WPS projection; the existing projection and reference location were kept.",
                "namelist.input ne définit pas la projection de WPS ; la projection et le point de référence existants sont gardés.",
            )
        )
    dx = float(_value(horizontal, "dx", case.grid.dx))
    dy = float(_value(horizontal, "dy", dx))
    if not math.isfinite(dx) or not math.isfinite(dy) or dx <= 0 or dy <= 0:
        raise ValueError(
            tr("dx and dy must be positive and finite", "dx et dy doivent être positifs et finis")
        )
    if not math.isclose(dx, dy, rel_tol=1e-6):
        warnings.append(
            tr(
                "dx and dy differ. Exact values are kept in overrides; the graphical Case grid and estimates represent the x spacing only.",
                "dx et dy diffèrent. Les valeurs exactes sont gardées dans les réglages bruts ; la grille affichée et les estimations ne représentent que la maille en x.",
            )
        )
    if (
        projection["map_proj"] == "lat-lon"
        and geogrid
        and ("dx" not in geogrid or "dy" not in geogrid)
    ):
        raise ValueError(
            tr(
                "A latitude-longitude namelist needs explicit angular dx/dy to migrate to this local-grid project model; global grids require manual configuration",
                "Une namelist en latitude-longitude demande des dx/dy angulaires explicites pour passer à la grille locale du projet ; les grilles globales se règlent à la main",
            )
        )
    if projection["map_proj"] == "lat-lon" and geogrid and "dx" in geogrid:
        dx *= math.pi * EARTH_RADIUS_M / 180
        warnings.append(
            tr(
                "Latitude-longitude WPS dx/dy are degrees: angular values stay in overrides; the Case uses their nominal spherical metre equivalent for estimates. Rotated/global grids need manual review.",
                "En latitude-longitude, dx/dy de WPS sont en degrés : ces valeurs angulaires restent dans les réglages bruts ; le projet utilise leur équivalent nominal en mètres pour les estimations. Les grilles tournées ou globales sont à vérifier à la main.",
            )
        )
    if any(key in geogrid for key in ("ref_x", "ref_y", "pole_lat", "pole_lon")):
        warnings.append(
            tr(
                "Non-default reference indices or a rotated pole remain namelist overrides; the map preview does not represent those extra projection options.",
                "Des indices de référence non standard ou un pôle tourné restent dans les réglages bruts de la namelist ; l'aperçu sur la carte ne représente pas ces options de projection.",
            )
        )
    grid = Grid(
        projection=Projection.model_validate(projection),
        dx=dx,
        domains=model_domains,
        e_vert=_integer(_value(domains, "e_vert", case.grid.e_vert), "e_vert"),
        p_top_requested=float(_value(domains, "p_top_requested", case.grid.p_top_requested)),
    )
    data["grid"] = grid.model_dump()
    if geogrid and "dx" in domains and projection["map_proj"] != "lat-lon":
        expected = grid.domain_dx()
        for index, spacing in enumerate(expected):
            supplied = float(_value(domains, "dx", spacing, index))
            if not math.isclose(supplied, spacing, rel_tol=1e-3):
                raise ValueError(
                    tr(
                        f"WRF dx is inconsistent with WPS nesting for domain {index + 1}",
                        f"dx de WRF ne correspond pas à l'imbrication de WPS pour le domaine {index + 1}",
                    )
                )
    start = _time(control, "start", _time(share, "start", case.period.start, wps=True))
    end = _time(control, "end", _time(share, "end", case.period.end, wps=True))
    duration = sum(
        float(_value(control, f"run_{unit}", 0)) * seconds
        for unit, seconds in (("days", 86400), ("hours", 3600), ("minutes", 60), ("seconds", 1))
    )
    if not math.isfinite(duration) or duration < 0:
        raise ValueError(
            tr(
                "run_* duration must be finite and non-negative",
                "La durée run_* doit être finie et positive ou nulle",
            )
        )
    if duration > 0:
        wrf_end = start + timedelta(seconds=duration)
        if control and any(key.startswith("end_") for key in control) and wrf_end != end:
            warnings.append(
                tr(
                    "WRF run_* duration and end_* dates differ: the Case period follows wrf.exe's run_* duration, while real.exe's longer/shorter boundary-data range stays in the overrides.",
                    "La durée run_* et les dates end_* de WRF diffèrent : la période du projet suit la durée run_* de wrf.exe, tandis que la plage des données aux frontières de real.exe reste dans les réglages bruts.",
                )
            )
        end = wrf_end
    interval = _integer(
        _value(
            control,
            "interval_seconds",
            _value(share, "interval_seconds", case.period.interval_seconds),
        ),
        "interval_seconds",
    )
    if (
        control
        and share
        and "interval_seconds" in control
        and "interval_seconds" in share
        and _value(control, "interval_seconds") != _value(share, "interval_seconds")
    ):
        raise ValueError(
            tr(
                "WPS and WRF interval_seconds must agree",
                "interval_seconds de WPS et de WRF doivent être égaux",
            )
        )
    data["period"] = Period(start=start, end=end, interval_seconds=interval).model_dump()
    if control and share:
        wps_start, wps_end = _time(share, "start", start, True), _time(share, "end", end, True)
        if wps_start > start or wps_end < end:
            warnings.append(
                tr(
                    "WPS dates do not cover the full WRF period. Review data coverage before launching.",
                    "Les dates de WPS ne couvrent pas toute la période de WRF. Vérifiez la couverture des données avant de lancer.",
                )
            )
    for field in ("physics", "dynamics"):
        data[field] = {
            **data[field],
            **{key: value for key, value in wrf.get(field, {}).items() if not key.startswith("_")},
        }
    history = _value(control, "history_interval")
    if history is not None and float(history) > 0:
        data["history_interval_minutes"] = _integer(history, "history_interval")
    elif "history_interval_s" in control or "history_interval_h" in control:
        warnings.append(
            tr(
                "Non-minute history output interval is kept exactly in namelist overrides; the graphical history interval was kept.",
                "Un intervalle de sortie qui n'est pas un nombre entier de minutes est gardé tel quel dans les réglages bruts ; l'intervalle affiché est conservé.",
            )
        )
    if _value(wrf.get("physics", {}), "sst_update") is not None:
        data["sea_surface"]["update"] = bool(_value(wrf["physics"], "sst_update"))
    options = wrf.get("physics", {})
    wind = options.get("windfarm_opt")
    if wind is not None:
        wind_values = wind if isinstance(wind, list) else [wind] * count
        enabled = [index + 1 for index, value in enumerate(wind_values[:count]) if value in (1, 2)]
        schemes = {value for value in wind_values[:count] if value in (1, 2)}
        if len(schemes) > 1:
            warnings.append(
                tr(
                    "Different farm schemes across domains remain in overrides; the graphical farm scheme cannot represent this combination.",
                    "Des schémas de parc différents selon les domaines restent dans les réglages bruts ; le réglage du schéma de parc ne peut pas représenter cette combinaison.",
                )
            )
        elif enabled:
            scheme = FarmScheme(
                scheme="mav" if 2 in schemes else "fitch",
                domains=enabled,
                tke_factor=float(_value(options, "windfarm_tke_factor", 0.25)),
                induction=bool(_value(options, "windfarm_induction", 1)),
                wake_model=_value(options, "windfarm_wake_model", 2),
                overlap_method=_value(options, "windfarm_overlap_method", 4),
            )
            data["farm_scheme"] = scheme.model_dump()
            warnings.append(
                tr(
                    "Wind-farm namelist settings were imported; turbine coordinates and turbine-table files must be supplied separately in Wind farms and Turbine models.",
                    "Les réglages de parc de la namelist sont importés ; les positions des éoliennes et leurs tables sont à donner à part dans Parcs éoliens et Modèles d'éoliennes.",
                )
            )
        else:
            data["farm_scheme"] = None
    elif data["farm_scheme"]:
        valid_domains = [number for number in data["farm_scheme"]["domains"] if number <= count]
        if valid_domains:
            data["farm_scheme"]["domains"] = valid_domains
        else:
            data["farm_scheme"] = None
            warnings.append(
                tr(
                    "The previous wind-farm domain no longer exists; the graphical farm scheme was disabled.",
                    "L'ancien domaine du parc n'existe plus ; le schéma de parc a été désactivé.",
                )
            )
    for per_domain_options, keys in (
        (
            control,
            (
                "start_year",
                "start_month",
                "start_day",
                "start_hour",
                "start_minute",
                "start_second",
                "end_year",
                "end_month",
                "end_day",
                "end_hour",
                "end_minute",
                "end_second",
                "history_interval",
            ),
        ),
        (share, ("start_date", "end_date")),
        (domains, ("e_vert",)),
    ):
        for key in keys:
            value = per_domain_options.get(key)
            if (
                isinstance(value, list)
                and len({str(item) for item in value if item is not None}) > 1
            ):
                warnings.append(
                    tr(
                        f"Per-domain {key} values differ: exact values stay in overrides; the graphical main setting follows domain 1.",
                        f"Les valeurs de {key} diffèrent selon les domaines : les valeurs exactes restent dans les réglages bruts ; le réglage principal affiché suit le domaine 1.",
                    )
                )
    imported = Case.model_validate(data)
    return {"case": imported.model_dump(mode="json"), "warnings": list(dict.fromkeys(warnings))}
