from datetime import datetime
from pathlib import Path

import f90nml
import pytest
from helpers import write_namelist, write_wind_farm_files
from pydantic import ValidationError

from owstudio.core.case.checks import check_case
from owstudio.core.case.model import Case, CurvePoint, Domain, TurbineType
from owstudio.core.namelist.generate import build_namelist_input, build_namelist_wps
from owstudio.core.windfarm.files import turbine_table

# The reference case was run end to end with the engine image
REFERENCE = Path(__file__).parent / "fixtures" / "horns-rev"


@pytest.fixture
def case() -> Case:
    return Case.from_yaml(REFERENCE / "case.yaml")


def assert_same_namelist(generated: f90nml.Namelist, reference: f90nml.Namelist) -> None:
    # Order matters: WPS reads its groups in sequence without rewinding the file
    assert list(generated) == list(reference)
    for group in reference:
        assert dict(generated[group]) == dict(reference[group]), group


def test_generated_namelist_input_matches_reference_run(case: Case, tmp_path: Path) -> None:
    generated = build_namelist_input(case)
    assert_same_namelist(generated, f90nml.read(REFERENCE / "namelist.input"))
    # What WRF reads back from the written file is what was generated
    write_namelist(generated, tmp_path / "namelist.input")
    assert_same_namelist(f90nml.read(tmp_path / "namelist.input"), generated)


def test_generated_namelist_wps_matches_reference_run(case: Case, tmp_path: Path) -> None:
    generated = build_namelist_wps(case)
    assert_same_namelist(generated, f90nml.read(REFERENCE / "namelist.wps"))
    write_namelist(generated, tmp_path / "namelist.wps")
    assert_same_namelist(f90nml.read(tmp_path / "namelist.wps"), generated)


def test_turbine_layout_matches_reference_run(case: Case, tmp_path: Path) -> None:
    assert case.farm_scheme is not None
    written = write_wind_farm_files(case, tmp_path)
    assert [p.name for p in written] == ["windturbines.txt", "turbines.csv"]
    assert written[0].read_text() == (REFERENCE / "windturbines.txt").read_text()


def test_yaml_round_trip(case: Case, tmp_path: Path) -> None:
    case.to_yaml(tmp_path / "case.yaml")
    assert Case.from_yaml(tmp_path / "case.yaml") == case


def test_written_files_use_unix_line_endings(case: Case, tmp_path: Path) -> None:
    assert case.farm_scheme is not None
    case.to_yaml(tmp_path / "case.yaml")
    write_namelist(build_namelist_input(case), tmp_path / "namelist.input")
    write_namelist(build_namelist_wps(case), tmp_path / "namelist.wps")
    write_wind_farm_files(case, tmp_path)
    for path in tmp_path.iterdir():
        assert b"\r" not in path.read_bytes(), path.name


def test_overrides_reach_any_namelist_option(case: Case) -> None:
    case.namelist_input = {"physics": {"windfarm_tke_factor": 0.25}, "stoch": {"skebs": [1, 1]}}
    nml = build_namelist_input(case)
    assert nml["physics"]["windfarm_tke_factor"] == 0.25
    assert nml["stoch"]["skebs"] == [1, 1]


def test_mav_scheme_sets_windfarm_opt_2(case: Case) -> None:
    assert case.farm_scheme is not None
    case.farm_scheme.scheme = "mav"
    assert build_namelist_input(case)["physics"]["windfarm_opt"] == [0, 2]


def test_custom_turbine_table_follows_wrf_format() -> None:
    turbine = TurbineType(
        hub_height_m=150,
        rotor_diameter_m=240,
        standing_thrust_coefficient=0.1,
        rated_power_mw=15,
        curve=[
            CurvePoint(wind_speed=3, thrust_coefficient=0.8, power_kw=50),
            CurvePoint(wind_speed=11, thrust_coefficient=0.7, power_kw=15000),
        ],
    )
    assert turbine_table(turbine) == "2\n150 240 0.1 15\n3 0.8 50\n11 0.7 15000\n"


def test_nest_outside_parent_is_rejected(case: Case) -> None:
    data = case.model_dump()
    data["grid"]["domains"][1]["i_parent_start"] = 80
    with pytest.raises(ValidationError, match="extends beyond its parent"):
        Case.model_validate(data)


def test_nest_size_must_match_ratio(case: Case) -> None:
    data = case.model_dump()
    data["grid"]["domains"][1]["e_we"] = 101
    with pytest.raises(ValidationError, match="multiple of the ratio"):
        Case.model_validate(data)


def test_period_must_be_increasing(case: Case) -> None:
    data = case.model_dump()
    data["period"]["end"] = datetime(2025, 9, 30)
    with pytest.raises(ValidationError, match="end must be after start"):
        Case.model_validate(data)


def test_reference_case_has_no_issues(case: Case) -> None:
    assert check_case(case) == []


def test_fitch_without_mynn_is_an_error(case: Case) -> None:
    case.physics["bl_pbl_physics"] = [1, 1]
    issues = check_case(case)
    assert [i.severity for i in issues] == ["error"]
    assert "MYNN" in issues[0].message


def test_tke_advection_off_is_a_warning(case: Case) -> None:
    case.physics["bl_mynn_tkeadvect"] = [False, False]
    assert [i.severity for i in check_case(case)] == ["warning"]


def test_grid_finer_than_five_rotor_diameters_is_a_warning(case: Case) -> None:
    assert case.farm_scheme is not None
    case.turbine_types[1] = TurbineType(
        hub_height_m=150,
        rotor_diameter_m=240,
        standing_thrust_coefficient=0.1,
        rated_power_mw=15,
        curve=[
            CurvePoint(wind_speed=3, thrust_coefficient=0.8, power_kw=50),
            CurvePoint(wind_speed=12, thrust_coefficient=0.7, power_kw=15000),
        ],
    )
    case.grid.domains.append(
        Domain(
            e_we=100,
            e_sn=100,
            parent_id=2,
            parent_grid_ratio=3,
            i_parent_start=34,
            j_parent_start=34,
        )
    )
    case.farm_scheme.domains = [3]
    case.physics = {k: (v + [v[-1]] if isinstance(v, list) else v) for k, v in case.physics.items()}
    resolution = [i.message for i in check_case(case) if "grid spacing" in i.message]
    assert len(resolution) == 1
    assert "5 rotor diameters (1200 m)" in resolution[0]


def test_large_time_step_is_a_warning(case: Case) -> None:
    case.namelist_input = {"domains": {"time_step": 60}}
    assert [i.severity for i in check_case(case)] == ["warning"]


def test_undefined_turbine_type_is_an_error(case: Case) -> None:
    assert case.farm_scheme is not None
    case.farms[0].turbines[0].type = 2
    issues = check_case(case)
    assert [i.severity for i in issues] == ["error"]
    assert "Turbine type 2" in issues[0].message


def test_power_curve_above_betz_is_a_warning(case: Case) -> None:
    from owstudio.core.windfarm.catalog import load_catalog

    assert case.farm_scheme is not None
    turbine = next(e for e in load_catalog() if e.id == "wrf-generic-2mw").turbine.model_copy()
    turbine.rotor_diameter_m = 40  # power curve now implies an impossible efficiency
    case.turbine_types[1] = turbine
    messages = [i.message for i in check_case(case)]
    assert any("Betz" in m for m in messages)


def test_curve_wind_speeds_must_increase() -> None:
    with pytest.raises(ValidationError, match="strictly increase"):
        TurbineType(
            hub_height_m=90,
            rotor_diameter_m=126,
            standing_thrust_coefficient=0.1,
            rated_power_mw=5,
            curve=[
                CurvePoint(wind_speed=5, thrust_coefficient=0.8, power_kw=400),
                CurvePoint(wind_speed=4, thrust_coefficient=0.8, power_kw=180),
            ],
        )


def test_turbines_closer_than_three_diameters_are_flagged(case: Case) -> None:
    from owstudio.core.windfarm.catalog import load_catalog

    assert case.farm_scheme is not None
    # 240 m rotors on the 560 m Horns Rev grid: 2.3 rotor diameters apart
    iea = next(e for e in load_catalog() if e.id == "iea-reference-15mw-240").turbine
    case.turbine_types[1] = iea
    messages = [i.message for i in check_case(case)]
    assert len(messages) == 1
    assert "80 turbine(s) are closer than 3 rotor diameters" in messages[0]
    assert "closest 2.3 D" in messages[0]


def test_turbines_outside_the_farm_domain_are_an_error(case: Case) -> None:
    assert case.farm_scheme is not None
    case.farms[0].turbines[0].lat = 60.0
    issues = check_case(case)
    assert [i.severity for i in issues] == ["error"]
    assert "1 turbine(s) lie outside d02" in issues[0].message


def test_static_data_resolution_is_required_and_checked_against_wps(case: Case) -> None:
    case.grid.domains[1].geog_data_res = ""
    case.grid.domains[0].geog_data_res = "lowres+nlcd2011_30m"
    issues = {i.field: i for i in check_case(case) if i.field and "geog_data_res" in i.field}
    assert issues["grid.domains.1.geog_data_res"].severity == "error"
    assert issues["grid.domains.0.geog_data_res"].severity == "warning"
    assert "nlcd2011_30m" in issues["grid.domains.0.geog_data_res"].message
    case.grid.domains[0].geog_data_res = "lowres"
    case.grid.domains[1].geog_data_res = "modis_15s+default"
    assert not [i for i in check_case(case) if i.field and "geog_data_res" in i.field]
