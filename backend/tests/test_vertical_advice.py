"""Checks of the vertical grid (core/method/vertical_advice.py): only real.exe's refusals, each with
its source, and every correction offered passes the same computation as real.exe."""

from owstudio.core.case.model import Case
from owstudio.core.method import vertical, vertical_advice


def apply(case: Case, changes: dict[str, float]) -> Case:
    changed = case.model_copy(deep=True)
    for key, value in changes.items():
        setattr(changed.grid, key, int(value) if key == "e_vert" else value)
    return changed


def test_too_few_levels_gives_the_fewest_that_reach_the_top(reference_case: Case) -> None:
    case = reference_case.model_copy(deep=True)
    case.grid.e_vert = 20
    [real] = vertical_advice.checks(case)
    assert not real.ok and real.changes is not None and set(real.changes) == {"e_vert"}
    assert "module_initialize_real" in real.source
    levels = int(real.changes["e_vert"])
    vertical.profile(apply(case, real.changes))
    assert vertical_advice.checks(apply(case, {"e_vert": levels}))[0].ok
    assert not vertical_advice.checks(apply(case, {"e_vert": levels - 1}))[0].ok


def test_nothing_but_real_exe_is_checked(reference_case: Case) -> None:
    """Advice (layers in the rotor...) is in the help, not on the screen: a project real.exe
    accepts gives a single passing check."""
    [real] = vertical_advice.checks(reference_case)
    assert real.ok and real.changes is None
