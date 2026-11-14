"""A repeated display label must never extract a turbine of another wind farm."""

from owstudio.core.case.model import Case, Farm, Turbine
from owstudio.core.extract.runs import turbine_position
from owstudio.core.tslist import turbine_labels


def test_qualified_turbine_positions_preserve_both_farms(reference_case: Case) -> None:
    case = reference_case.model_copy(deep=True)
    case.farms = [
        Farm(id="farm-a", name="A", turbines=[Turbine(id="A01", lat=54.1, lon=7.1)]),
        Farm(id="farm-b", name="B", turbines=[Turbine(id="A01", lat=54.2, lon=7.2)]),
    ]
    labels = turbine_labels(case)
    assert labels[("farm-a", 1)] == "farm-a/A01"
    assert labels[("farm-b", 1)] == "farm-b/A01"
    assert turbine_position(case, labels[("farm-a", 1)]) == (54.1, 7.1)
    assert turbine_position(case, labels[("farm-b", 1)]) == (54.2, 7.2)
    # An ambiguous old raw label resolves to neither farm instead of silently choosing A.
    assert turbine_position(case, "A01") is None


def test_positions_reserve_unique_labels_and_generated_name_collisions(
    reference_case: Case,
) -> None:
    case = reference_case.model_copy(deep=True)
    case.farms = [
        Farm(
            id="farm-a",
            name="A",
            turbines=[
                Turbine(id="A01", lat=54.1, lon=7.1),
                Turbine(lat=54.3, lon=7.3),
            ],
        ),
        Farm(
            id="farm-b",
            name="B",
            turbines=[
                Turbine(id="A01", lat=54.2, lon=7.2),
                Turbine(id="farm-a-2", lat=54.4, lon=7.4),
            ],
        ),
        Farm(
            id="farm-c",
            name="C",
            turbines=[
                Turbine(id="farm-a/A01", lat=54.5, lon=7.5),
                Turbine(id="unique", lat=54.6, lon=7.6),
            ],
        ),
    ]
    labels = turbine_labels(case)
    assert labels[("farm-a", 1)] == "farm-a/A01#2"
    assert labels[("farm-c", 1)] == "farm-a/A01"
    assert labels[("farm-a", 2)] == "farm-a/farm-a-2"
    assert labels[("farm-b", 2)] == "farm-b/farm-a-2"
    for farm in case.farms:
        for index, turbine in enumerate(farm.turbines, 1):
            assert turbine_position(case, labels[(farm.id, index)]) == (turbine.lat, turbine.lon)
    assert turbine_position(case, "unique") == (54.6, 7.6)
    assert turbine_position(case, "farm-a-2") is None
    assert turbine_position(case, "unknown") is None
