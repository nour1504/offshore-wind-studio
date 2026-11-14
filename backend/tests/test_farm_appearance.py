"""Marker choices must persist without changing anything WRF reads or computes."""

from pathlib import Path
from typing import Any

import pytest
from helpers import write_wind_farm_files
from pydantic import ValidationError

from owstudio.api.routes_cases import geometry
from owstudio.core.case.model import Case, FarmAppearance
from owstudio.core.namelist.generate import build_namelist_input, build_namelist_wps


def test_project_without_appearance_still_loads(reference: dict[str, Any]) -> None:
    for farm in reference["farms"]:
        farm.pop("appearance", None)
    case = Case.model_validate(reference)
    assert all(farm.appearance == FarmAppearance(color=None, symbol="auto") for farm in case.farms)


def test_marker_choices_survive_yaml_round_trip(reference_case: Case, tmp_path: Path) -> None:
    reference_case.farms[0].appearance = FarmAppearance(color="#2b8A66", symbol="diamond")
    target = tmp_path / "case.yaml"
    reference_case.to_yaml(target)
    restored = Case.from_yaml(target)
    assert restored == reference_case
    assert restored.farms[0].appearance.color == "#2b8A66"
    assert restored.farms[0].appearance.symbol == "diamond"


@pytest.mark.parametrize(
    "symbol", ["auto", "circle", "cross", "plus", "square", "diamond", "triangle"]
)
@pytest.mark.parametrize("color", [None, "#000000", "#ffffff", "#aBcD12"])
def test_supported_marker_choices_validate(symbol: str, color: str | None) -> None:
    appearance = FarmAppearance.model_validate({"color": color, "symbol": symbol})
    assert appearance.color == color
    assert appearance.symbol == symbol


@pytest.mark.parametrize(
    "appearance",
    [
        {"color": "red"},
        {"color": "#fff"},
        {"color": "#12345678"},
        {"color": "#00ffgg"},
        {"color": "url(https://example.org/image.svg)"},
        {"symbol": "star"},
        {"symbol": ""},
        {"symbol": None},
        {"unrecognised": True},
    ],
)
def test_invalid_marker_choices_are_rejected(appearance: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        FarmAppearance.model_validate(appearance)


@pytest.mark.parametrize("scheme", ["fitch", "mav"])
def test_marker_choices_do_not_change_engine_input_files(
    reference_case: Case, tmp_path: Path, scheme: str
) -> None:
    assert reference_case.farm_scheme is not None
    data = reference_case.model_dump(mode="json")
    data["farm_scheme"]["scheme"] = scheme
    original = Case.model_validate(data)
    styled = original.model_copy(deep=True)
    styled.farms[0].appearance = FarmAppearance(color="#8A6D42", symbol="triangle")

    assert str(build_namelist_input(styled)) == str(build_namelist_input(original))
    assert str(build_namelist_wps(styled)) == str(build_namelist_wps(original))
    files = []
    for name, case in [("before", original), ("after", styled)]:
        directory = tmp_path / name
        directory.mkdir()
        files.append({p.name: p.read_bytes() for p in write_wind_farm_files(case, directory)})
    assert files[0] == files[1]


def test_geometry_carries_appearance_without_moving_or_losing_turbines(
    reference_case: Case,
) -> None:
    before = geometry(reference_case)
    styled = reference_case.model_copy(deep=True)
    styled.farms[0].appearance = FarmAppearance(color="#28714F", symbol="plus")
    after = geometry(styled)
    original_points = [f for f in before["features"] if f["properties"]["kind"] == "turbine"]
    styled_points = [f for f in after["features"] if f["properties"]["kind"] == "turbine"]
    assert len(styled_points) == len(original_points) == 80
    assert [f["geometry"] for f in styled_points] == [f["geometry"] for f in original_points]
    assert all(f["properties"]["farm_color"] == "#28714F" for f in styled_points)
    assert all(f["properties"]["farm_symbol"] == "plus" for f in styled_points)
    assert reference_case.farms[0].appearance == FarmAppearance()
