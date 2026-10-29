"""Checks concern the final Fortran values, including imported and indexed overrides."""

import pytest

from owstudio.core.case.model import Case
from owstudio.core.namelist.validate import check_namelists, check_time_steps, domain_option


@pytest.mark.parametrize(
    "override,word",
    [
        ({"time_step": "fast"}, "integer"),
        ({"time_step": 0}, "positive"),
        ({"time_step_fract_den": 0}, "den"),
        (
            {
                "use_adaptive_time_step": True,
                "min_time_step": [100, 100],
                "max_time_step": [50, 50],
            },
            "min_time_step",
        ),
        ({"use_adaptive_time_step": True, "adaptation_domain": 99}, "adaptation_domain"),
    ],
)
def test_invalid_final_time_options_are_detected(
    reference_case: Case, override: dict, word: str
) -> None:
    reference_case.namelist_input = {"domains": override}
    findings = check_namelists(reference_case)
    assert any(f.severity == "error" and word in f.message for f in findings)


def test_adaptive_step_does_not_apply_static_six_dx_limit(reference_case: Case) -> None:
    reference_case.namelist_input = {"domains": {"time_step": 1000, "use_adaptive_time_step": True}}
    assert not any("6 s/km" in f.message for f in check_time_steps(reference_case))
    reference_case.namelist_input["domains"]["use_adaptive_time_step"] = False
    assert any(
        f.severity == "warning" and "6 s/km" in f.message for f in check_time_steps(reference_case)
    )


def test_unrecognised_options_remain_available_and_report_coverage(reference_case: Case) -> None:
    reference_case.namelist_input = {"physics": {"custom_build_option": 1}}
    findings = [f for f in check_namelists(reference_case) if "custom_build_option" in f.message]
    assert len(findings) == 1 and findings[0].severity == "warning"


def test_incompatible_physics_and_raw_turbine_override(reference_case: Case) -> None:
    reference_case.namelist_input = {
        "physics": {"bl_pbl_physics": [10, 10], "sf_sfclay_physics": [1, 1]}
    }
    assert any(
        f.severity == "error" and "TEMF" in f.message for f in check_namelists(reference_case)
    )
    reference_case.namelist_input = {"physics": {"windfarm_opt": [0, 0]}}
    assert any(
        f.severity == "error" and "windfarm_opt" in f.message
        for f in check_namelists(reference_case)
    )


def test_indexed_arrays_keep_fortran_domain_position(reference_case: Case) -> None:
    reference_case.namelist_input = {
        "physics": {"sf_sfclay_physics": [2], "_start_index": {"sf_sfclay_physics": [2]}}
    }
    assert domain_option(reference_case, "physics", "sf_sfclay_physics", 2) == 2
    assert domain_option(reference_case, "physics", "sf_sfclay_physics", 1) != 2
    assert not any(
        f.severity == "error" and "metadata" in f.message for f in check_namelists(reference_case)
    )
