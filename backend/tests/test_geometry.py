from pathlib import Path

import pytest

from owstudio.core.case.model import Case, Projection
from owstudio.core.domains import cell_of, domain_outlines, projection_for

REFERENCE = Path(__file__).parent / "fixtures" / "horns-rev"

# Outer corners (lower-left, upper-left, upper-right, lower-right) written by geogrid in the
# corner_lats / corner_lons attributes of geo_em.d0N.nc for the Horns Rev case
GEOGRID_CORNERS = {
    1: [(51.31039, 1.39505), (59.27924, -0.04571533), (59.27924, 15.64569), (51.31039, 14.20496)],
    2: [(54.14204, 5.519226), (56.81258, 5.3591), (56.81258, 10.24088), (54.14204, 10.08075)],
}


@pytest.fixture
def case() -> Case:
    return Case.from_yaml(REFERENCE / "case.yaml")


@pytest.mark.parametrize("number", [1, 2])
def test_outline_corners_match_geogrid(case: Case, number: int) -> None:
    points = 10
    ring = domain_outlines(case.grid, points_per_edge=points)[number - 1]
    # The ring walks lower-left, lower-right, upper-right, upper-left
    lower_left, lower_right, upper_right, upper_left = (ring[k * points] for k in range(4))
    ours = [lower_left, upper_left, upper_right, lower_right]
    for (lon, lat), (ref_lat, ref_lon) in zip(ours, GEOGRID_CORNERS[number], strict=True):
        assert lat == pytest.approx(ref_lat, abs=2e-3)
        assert lon == pytest.approx(ref_lon, abs=2e-3)


@pytest.mark.parametrize(
    "projection",
    [
        Projection(
            map_proj="lambert", ref_lat=55.5, ref_lon=7.8, truelat1=54, truelat2=57, stand_lon=7.8
        ),
        Projection(
            map_proj="lambert", ref_lat=-38, ref_lon=145, truelat1=-35, truelat2=-41, stand_lon=145
        ),
        Projection(map_proj="mercator", ref_lat=20, ref_lon=-160, truelat1=20),
    ],
)
def test_projection_round_trip(projection: Projection) -> None:
    proj = projection_for(projection)
    for lat, lon in [
        (projection.ref_lat, projection.ref_lon),
        (projection.ref_lat + 3, projection.ref_lon - 4),
    ]:
        back = proj.inverse(*proj.forward(lat, lon))
        assert back == pytest.approx((lat, lon), abs=1e-9)


def test_farm_lies_in_the_middle_of_the_nest(case: Case) -> None:
    first = case.farms[0].turbines[0]
    assert cell_of(case.grid, 2, first.lat, first.lon) == (50, 50)


def test_point_outside_domain_has_no_cell(case: Case) -> None:
    assert cell_of(case.grid, 2, 40.0, 0.0) is None
