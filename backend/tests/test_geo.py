"""Stateless imports and geometry contracts; every file/settings folder is synthetic and local."""

import hashlib
import io
import itertools
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import f90nml
import pytest
import shapefile
from helpers import make_client
from pyproj import CRS, Geod, Transformer
from shapely.geometry import Point, Polygon

from owstudio.core.case.model import Case
from owstudio.core.geo import import_map, import_namelists, turbine_layout
from owstudio.core.namelist.generate import build_namelist_input, build_namelist_wps


def text(namelist: Any) -> str:
    output = io.StringIO()
    namelist.write(output)
    return output.getvalue()


def test_geojson_points_holes_and_read_only_source(tmp_path: Path) -> None:
    path = tmp_path / "farm.geojson"
    outer = [[8, 55], [8.05, 55], [8.05, 55.05], [8, 55.05], [8, 55]]
    hole = [[8.01, 55.01], [8.01, 55.02], [8.02, 55.02], [8.02, 55.01], [8.01, 55.01]]
    path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [8.03, 55.03, 100]},
                        "properties": {"name": "A01", "type": 7},
                    },
                    {
                        "type": "Feature",
                        "geometry": {"type": "Polygon", "coordinates": [outer, hole]},
                        "properties": {"name": "Lease area"},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    before = hashlib.sha256(path.read_bytes()).digest()
    result = import_map(path)
    assert result["crs"] == "EPSG:4326"
    assert result["points"] == [{"lon": 8.03, "lat": 55.03, "type": 7, "id": "A01"}]
    assert len(result["polygons"][0]["rings"]) == 2
    assert result["polygons"][0]["name"] == "Lease area"
    assert len(result["collection"]["features"]) == 2
    assert hashlib.sha256(path.read_bytes()).digest() == before


def test_projected_geojson_axis_order(tmp_path: Path) -> None:
    path = tmp_path / "utm.json"
    path.write_text(json.dumps({"type": "Point", "coordinates": [500000, 0]}))
    result = import_map(path, "EPSG:32632")
    assert result["points"][0]["lon"] == pytest.approx(9, abs=1e-8)
    assert result["points"][0]["lat"] == pytest.approx(0, abs=1e-8)


def test_shapefile_prj_and_codepage(tmp_path: Path) -> None:
    path = tmp_path / "points.shp"
    with shapefile.Writer(str(path), shapeType=shapefile.POINT, encoding="cp1252") as writer:
        writer.field("name", "C")
        writer.point(500000, 0)
        writer.record("Éolienne")
    path.with_suffix(".prj").write_text(CRS.from_epsg(32632).to_wkt(), encoding="utf-8")
    path.with_suffix(".cpg").write_text("1252")
    result = import_map(path)
    assert result["points"][0]["lon"] == pytest.approx(9)
    assert result["points"][0]["id"] == "Éolienne"
    path.with_suffix(".prj").unlink()
    with pytest.raises(ValueError, match="explicit source CRS"):
        import_map(path)
    assert import_map(path, "EPSG:32632")["points"][0]["lat"] == pytest.approx(0)


def test_kml_multigeometry_and_no_external_fetch(tmp_path: Path) -> None:
    path = tmp_path / "layout.kml"
    path.write_text(
        """<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
      <NetworkLink><Link><href>https://example.invalid/remote.kml</href></Link></NetworkLink>
      <Placemark><name>Farm A</name><MultiGeometry>
        <Point><coordinates>8.2,55.2,0</coordinates></Point>
        <Polygon><outerBoundaryIs><LinearRing><coordinates>8,55 8.1,55 8.1,55.1 8,55.1 8,55</coordinates></LinearRing></outerBoundaryIs></Polygon>
      </MultiGeometry></Placemark></Document></kml>""",
        encoding="utf-8",
    )
    result = import_map(path)
    assert len(result["points"]) == len(result["polygons"]) == 1
    assert result["points"][0]["lon"] == 8.2
    assert any("network links" in warning for warning in result["warnings"])


@pytest.mark.parametrize("encoding", ["utf-8", "utf-16"])
def test_kml_dtd_rejected_even_with_utf16(tmp_path: Path, encoding: str) -> None:
    path = tmp_path / "entity.kml"
    path.write_bytes(
        (
            '<?xml version="1.0"?><!DOCTYPE kml [<!ENTITY x SYSTEM "file:///not-readable">]>'
            "<kml><Placemark><name>&x;</name></Placemark></kml>"
        ).encode(encoding)
    )
    with pytest.raises(ValueError, match="DTDs"):
        import_map(path)


@pytest.mark.parametrize(
    "geometry",
    [
        {"type": "Point", "coordinates": [8, 91]},
        {"type": "Point", "coordinates": [math.nan, 55]},
        {"type": "Point", "coordinates": [True, 55]},
        {"type": "GeometryCollection", "geometries": ["bad"]},
    ],
)
def test_invalid_geometry_refused(tmp_path: Path, geometry: dict[str, Any]) -> None:
    path = tmp_path / "bad.geojson"
    path.write_text(json.dumps(geometry))
    with pytest.raises((ValueError, TypeError)):
        import_map(path)


def test_layout_holes_metric_spacing_and_rotation() -> None:
    ring = [[8, 55], [8.05, 55], [8.05, 55.04], [8, 55.04]]
    hole = [[8.01, 55.01], [8.01, 55.02], [8.02, 55.02], [8.02, 55.01]]
    result = turbine_layout(ring, 500, 27, 4, [hole])
    assert 10 < result["count"] < 100
    area = Polygon(ring, holes=[hole])
    assert all(area.covers(Point(p["lon"], p["lat"])) for p in result["points"])
    assert all(p["type"] == 4 for p in result["points"])
    points = result["points"]
    distances = [
        Geod(ellps="WGS84").inv(p["lon"], p["lat"], q["lon"], q["lat"])[2]
        for p in points
        for q in points
        if p["id"] != q["id"]
    ]
    assert min(distances) == pytest.approx(500, abs=0.1)
    local = Transformer.from_crs("EPSG:4326", result["projection"], always_xy=True)
    first = local.transform(points[0]["lon"], points[0]["lat"])
    second = local.transform(points[1]["lon"], points[1]["lat"])
    direction = math.degrees(math.atan2(second[1] - first[1], second[0] - first[0]))
    # A square lattice has two perpendicular axes: -27 degrees and +63 degrees.
    assert direction % 90 == pytest.approx(63, abs=1e-6)


def test_layout_rows_stagger_and_setback() -> None:
    """Two spacings (along and between the rows), every other row shifted by half a spacing, and
    no turbine closer than the setback to the edge; the area of the zone comes back."""
    ring = [[8, 55], [8.08, 55], [8.08, 55.05], [8, 55.05]]
    plain = turbine_layout(ring, 800, 0, 1)
    result = turbine_layout(ring, 800, 0, 1, None, 1200, 0.5, 300)
    assert result["spacing_across_m"] == 1200 and 25 < result["area_km2"] < 30
    assert 0 < result["count"] < plain["count"]
    local = Transformer.from_crs("EPSG:4326", result["projection"], always_xy=True)
    xy = [local.transform(p["lon"], p["lat"]) for p in result["points"]]
    rows = sorted({round(y) for _, y in xy})
    assert all(b - a == pytest.approx(1200, abs=1) for a, b in itertools.pairwise(rows))
    first = sorted(x for x, y in xy if round(y) == rows[0])
    second = sorted(x for x, y in xy if round(y) == rows[1])
    assert abs((second[0] - first[0]) % 800 - 400) < 1
    # The zone shrunk by 300 m holds every turbine
    zone = _metric(ring, local)
    assert all(zone.exterior.distance(Point(x, y)) >= 300 - 1 for x, y in xy)


def _metric(ring: list[list[float]], local: Any) -> Polygon:
    return Polygon([local.transform(lon, lat) for lon, lat in ring])


def test_layout_dense_invalid_and_antimeridian() -> None:
    square = [[8, 55], [8.1, 55], [8.1, 55.1], [8, 55.1]]
    with pytest.raises(ValueError, match="dense|10 000"):
        turbine_layout(square, 1, 0, 1)
    with pytest.raises(ValueError, match="invalid"):
        turbine_layout([[0, 0], [1, 1], [1, 0], [0, 1]], 500, 0, 1)
    with pytest.raises(ValueError, match="antimeridian"):
        turbine_layout([[179.9, 10], [-179.9, 10], [-179.9, 10.1], [179.9, 10.1]], 500, 0, 1)
    with pytest.raises(ValueError, match="spacing"):
        turbine_layout(square, float("nan"), 0, 1)


def test_namelist_roundtrip_and_no_original_mutation(reference_case: Case) -> None:
    before = reference_case.model_dump_json()
    result = import_namelists(
        reference_case,
        text(build_namelist_input(reference_case)),
        text(build_namelist_wps(reference_case)),
    )
    imported = Case.model_validate(result["case"])
    assert imported.grid == reference_case.grid
    assert imported.period.start == reference_case.period.start.replace(tzinfo=UTC)
    assert imported.period.end == reference_case.period.end.replace(tzinfo=UTC)
    assert imported.physics == reference_case.physics | dict(
        build_namelist_input(reference_case)["physics"]
    )
    assert imported.farms == reference_case.farms
    assert (
        imported.namelist_input["domains"]["time_step"]
        == build_namelist_input(reference_case)["domains"]["time_step"]
    )
    assert reference_case.model_dump_json() == before


def test_namelist_minutes_run_duration_and_unknown_overrides(reference_case: Case) -> None:
    imported = import_namelists(
        reference_case,
        """&time_control
      start_year=2024, start_month=2, start_day=28, start_hour=23, start_minute=30,
      end_year=2024,end_month=2,end_day=29,end_hour=4, run_hours=2,
      history_interval=30, interval_seconds=3600 /
      &custom_group unknown_flag=.true., unknown_list=1,2,3 /""",
    )
    case = Case.model_validate(imported["case"])
    assert case.period.start == datetime(2024, 2, 28, 23, 30, tzinfo=UTC)
    assert case.period.end == datetime(2024, 2, 29, 1, 30, tzinfo=UTC)
    assert case.history_interval_minutes == 30
    assert case.namelist_input["custom_group"] == {"unknown_flag": True, "unknown_list": [1, 2, 3]}
    assert any("run_* duration" in warning for warning in imported["warnings"])


def test_indexed_namelist_keeps_assigned_domain(reference_case: Case) -> None:
    reference_case.physics["mp_physics"] = [3, 6]
    result = import_namelists(reference_case, "&physics mp_physics(2)=8 /")
    imported = Case.model_validate(result["case"])
    rendered = text(build_namelist_input(imported))
    reparsed = f90nml.reads(rendered)
    assert reparsed["physics"]["mp_physics"][1] == 8
    assert reparsed["physics"]["mp_physics"][0] == 3
    assert imported.physics["mp_physics"] == [3, 8]
    assert len(imported.namelist_input["physics"]["mp_physics"]) == 2


def test_partial_time_control_uses_wps_dates(reference_case: Case) -> None:
    result = import_namelists(
        reference_case,
        "&time_control history_interval=30 /",
        "&share start_date='2024-01-01_00:00:00',end_date='2024-01-02_00:00:00' /",
    )
    imported = Case.model_validate(result["case"])
    assert imported.period.start == datetime(2024, 1, 1, tzinfo=UTC)
    assert imported.period.end == datetime(2024, 1, 2, tzinfo=UTC)


def test_unknown_indexed_array_keeps_fortran_indices(reference_case: Case) -> None:
    result = import_namelists(reference_case, "&custom_array unlisted(3)=99 /")
    imported = Case.model_validate(result["case"])
    assert imported.namelist_input["custom_array"]["unlisted"] == [None, None, 99]
    assert f90nml.reads(text(build_namelist_input(imported)))["custom_array"]["unlisted"][2] == 99
    assert any("partial indexed" in warning for warning in result["warnings"])


def test_wps_domain_migration_keeps_overrides_and_disables_removed_farm_domain(
    reference_case: Case,
) -> None:
    wps = """&share max_dom=1, start_date='2024-01-01_00:00:00',end_date='2024-01-02_00:00:00',interval_seconds=10800 /
      &geogrid e_we=101,e_sn=91,dx=6000,dy=6000,map_proj='mercator',ref_lat=55,ref_lon=8,truelat1=55,geog_data_res='default' /
      &ungrib prefix='MYDATA',out_format='WPS' /"""
    result = import_namelists(reference_case, wps_text=wps)
    case = Case.model_validate(result["case"])
    assert case.grid.dx == 6000 and case.max_dom == 1
    assert case.grid.domains[0].e_we == 101
    assert case.grid.projection.map_proj == "mercator"
    assert case.farm_scheme is None
    assert case.namelist_wps["ungrib"]["prefix"] == "MYDATA"
    assert case.period.interval_seconds == 10800


def test_conflicting_essential_namelists_refused(reference_case: Case) -> None:
    with pytest.raises(ValueError, match="max_dom"):
        import_namelists(reference_case, "&domains max_dom=2 /", "&share max_dom=1 /")
    with pytest.raises(ValueError, match="e_we"):
        import_namelists(
            reference_case,
            "&domains max_dom=1,e_we=111 /",
            "&share max_dom=1 / &geogrid e_we=101,e_sn=91,dx=6000 /",
        )
    with pytest.raises(ValueError, match="interval_seconds"):
        import_namelists(
            reference_case,
            "&time_control interval_seconds=3600 /",
            "&share interval_seconds=10800 /",
        )
    with pytest.raises(ValueError, match="integer"):
        import_namelists(reference_case, "&domains max_dom=1.5 /")


def test_latlon_import_keeps_degrees_override_and_warns(reference_case: Case) -> None:
    result = import_namelists(
        reference_case, wps_text="&geogrid map_proj='lat-lon', dx=0.1,dy=0.1 /"
    )
    case = Case.model_validate(result["case"])
    assert 11000 < case.grid.dx < 11200
    assert case.namelist_wps["geogrid"]["dx"] == 0.1
    assert any("degrees" in warning for warning in result["warnings"])


def test_routes_are_stateless_and_errors_are_user_visible(
    tmp_path: Path, reference: dict[str, Any]
) -> None:
    client = make_client(tmp_path / "application")
    path = tmp_path / "points.geojson"
    path.write_text('{"type":"Point","coordinates":[8,55]}')
    assert client.post("/api/geo/import", json={"path": str(path)}).status_code == 200
    assert (
        client.post("/api/geo/import", json={"path": str(tmp_path / "missing.kml")}).status_code
        == 404
    )
    assert (
        client.post(
            "/api/geo/layout",
            json={
                "polygon": [[8, 55], [8.05, 55], [8.05, 55.05], [8, 55.05]],
                "spacing_m": 500,
                "rotation_deg": 0,
                "turbine_type": 1,
            },
        ).status_code
        == 200
    )
    response = client.post(
        "/api/geo/namelist-import",
        json={"case": reference, "input": "&physics mp_physics=8,8 /", "wps": ""},
    )
    assert response.status_code == 200 and response.json()["case"]["physics"]["mp_physics"] == [
        8,
        8,
    ]
    assert client.get("/api/cases").json() == []
    assert client.get("/api/profiles").json()["profiles"] == []
    assert client.post("/api/geo/namelist-import", json={"case": reference}).status_code == 422
    assert (
        client.post(
            "/api/geo/layout", json={"polygon": [[8, 55], [8.1, 55], [8.1, 55.1]], "spacing_m": -1}
        ).status_code
        == 422
    )
