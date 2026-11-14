import pytest

from owstudio.core.windfarm.coordinates import CoordinateError, parse_coordinates, utm_epsg

HORNS_REV = (55.5, 7.8)


def latlons(text: str, **kwargs: object) -> list[tuple[float, float]]:
    return [(p.lat, p.lon) for p in parse_coordinates(text, **kwargs).points]  # type: ignore[arg-type]


def test_tab_separated_from_a_spreadsheet() -> None:
    assert latlons("55.4863\t7.8401\n55.4912\t7.8488\n") == [(55.4863, 7.8401), (55.4912, 7.8488)]


def test_french_spreadsheet_with_semicolons_and_decimal_commas() -> None:
    result = parse_coordinates("Latitude;Longitude;Type\n55,4863;7,8401;2\n55,4912;7,8488;2\n")
    assert [(p.lat, p.lon, p.type) for p in result.points] == [
        (55.4863, 7.8401, 2),
        (55.4912, 7.8488, 2),
    ]
    assert "decimal commas" in result.detected


def test_tab_separated_with_decimal_commas() -> None:
    assert latlons("55,4863\t7,8401") == [(55.4863, 7.8401)]


def test_header_names_decide_the_order() -> None:
    assert latlons("lon,lat\n7.8401,55.4863") == [(55.4863, 7.8401)]
    assert latlons("ID;Longitude;Latitude\nWTG01;7,84;55,48") == [(55.48, 7.84)]


def test_order_without_header_is_the_one_closest_to_the_domain() -> None:
    assert latlons("7.8401 55.4863", near=HORNS_REV) == [(55.4863, 7.8401)]
    assert latlons("55.4863 7.8401", near=HORNS_REV) == [(55.4863, 7.8401)]


def test_order_can_be_forced() -> None:
    assert latlons("7.8401 55.4863", crs="lonlat") == [(55.4863, 7.8401)]


def test_names_and_types_without_header() -> None:
    points = parse_coordinates("WTG01 55.4863 7.8401 3\nWTG02 55.4912 7.8488 3").points
    assert [(p.name, p.type) for p in points] == [("WTG01", 3), ("WTG02", 3)]


def test_utm_coordinates_need_a_zone_then_convert() -> None:
    text = "Easting;Northing\n423000;6150000\n"
    with pytest.raises(CoordinateError, match="UTM"):
        parse_coordinates(text)
    lat, lon = latlons(text, epsg=utm_epsg(32, southern=False))[0]
    assert lat == pytest.approx(55.49004, abs=1e-4) and lon == pytest.approx(7.78135, abs=1e-4)


def test_utm_without_header_in_either_order() -> None:
    epsg = utm_epsg(32, southern=False)
    assert latlons("423000 6150000", epsg=epsg) == latlons("6150000 423000", epsg=epsg)


def test_bad_lines_are_reported() -> None:
    result = parse_coordinates("55.48 7.84\nnot a point\n55.49 7.85")
    assert len(result.points) == 2 and result.skipped == [2]


def test_out_of_range_is_an_error() -> None:
    with pytest.raises(CoordinateError, match="out of range"):
        parse_coordinates("95.0 200.0\n", crs="latlon")
