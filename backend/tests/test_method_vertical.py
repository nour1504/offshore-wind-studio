"""Vertical levels (core/method/vertical.py), checked against real.exe's own output.

Known values: real.exe logs posted on the WRF forum, with WRF 4.5 whose levels and compute_eta
routines are identical to 4.8's:
- https://forum.mmm.ucar.edu/threads/real-how-to-split-the-lowest-eta-level-in-two-layers.15160/
  e_vert 40 (dzbot 50) and 41 (dzbot 30), p_top_requested 5000, other options by default;
- https://forum.mmm.ucar.edu/threads/does-the-real-program-generate-the-full-level-height-based-on-the-international-standard-atmosphere.16833/
  eta 1.0000 0.9941 0.9876 0.9805 0.9727 and heights 0.0 50.0 104.9 165.2 231.5 m, which are
  those of dzbot 50, dzstretch_s 1.1 and p_top 1000 Pa.
"""

import math
from dataclasses import replace

import pytest

from owstudio.core.case.model import Case
from owstudio.core.method import vertical
from owstudio.core.method.vertical import VerticalError, VerticalSettings

DEFAULT = VerticalSettings(
    e_vert=40,
    p_top=5000.0,
    auto_levels_opt=2,
    dzbot=50.0,
    dzstretch_s=1.3,
    dzstretch_u=1.1,
    max_dz=1000.0,
    eta_levels=None,
    hybrid_opt=2,
    etac=0.2,
    base_temp=290.0,
    base_lapse=50.0,
    iso_temp=200.0,
    base_pres=100000.0,
    base_pres_strat=0.0,
    base_lapse_strat=-11.0,
    hypsometric_opt=2,
)


def logged_heights(s: vertical.VerticalSettings, znw: list[float]) -> list[float]:
    """Heights real.exe prints in its log ("Full level index = ... Height = ..."): compute_eta
    integrates the sea-level base state linearly in eta. The model's own base state follows
    hypsometric_opt (profile); both agree near the ground, within 0.1 % at the top."""
    from dataclasses import replace

    linear = replace(s, hypsometric_opt=1)
    return vertical.column(
        linear, znw, vertical.coefficients(znw, s.hybrid_opt, s.etac, s.p_top), 0.0
    )


def logged(settings: VerticalSettings) -> list[float]:
    return logged_heights(settings, vertical.full_levels(settings))


@pytest.mark.parametrize(
    ("e_vert", "dzbot", "expected"),
    [
        (
            40,
            50.0,
            {
                2: 50.0,
                3: 113.9,
                4: 195.2,
                5: 298.0,
                10: 1312.6,
                20: 6841.5,
                30: 13678.6,
                39: 19264.7,
                40: 19885.3,
            },
        ),
        (
            41,
            30.0,
            {
                2: 30.0,
                3: 68.6,
                4: 118.1,
                5: 181.5,
                10: 847.9,
                20: 5385.9,
                30: 12717.6,
                40: 19232.6,
                41: 19884.1,
            },
        ),
    ],
)
def test_heights_of_real_exe_logs(e_vert: int, dzbot: float, expected: dict[int, float]) -> None:
    heights = logged(replace(DEFAULT, e_vert=e_vert, dzbot=dzbot))
    assert len(heights) == e_vert and heights[0] == 0
    for level, height in expected.items():
        assert heights[level - 1] == pytest.approx(height, abs=0.11), level


def test_eta_and_heights_of_a_second_log() -> None:
    settings = replace(DEFAULT, e_vert=60, p_top=1000.0, dzstretch_s=1.1)
    eta = vertical.full_levels(settings)
    assert [round(v, 4) for v in eta[:5]] == [1.0, 0.9941, 0.9876, 0.9805, 0.9727]
    assert [round(v, 1) for v in logged(settings)[:5]] == [0.0, 50.0, 104.9, 165.2, 231.5]


def test_model_base_state_agrees_near_the_ground() -> None:
    eta = vertical.full_levels(DEFAULT)
    coefficients = vertical.coefficients(eta, 2, 0.2, DEFAULT.p_top)
    model = vertical.column(DEFAULT, eta, coefficients)
    printed = logged(DEFAULT)
    assert model[:6] == pytest.approx(printed[:6], abs=0.2)
    assert model[-1] == pytest.approx(printed[-1], rel=2e-3)


def test_errors_of_real_exe() -> None:
    with pytest.raises(VerticalError, match="not enough eta levels"):
        vertical.full_levels(replace(DEFAULT, e_vert=20))
    with pytest.raises(VerticalError, match="too thick"):
        vertical.full_levels(replace(DEFAULT, e_vert=40, max_dz=300.0))


def test_explicit_eta_levels() -> None:
    levels = (1.0, 0.99, 0.97, 0.9, 0.7, 0.4, 0.1, 0.0)
    settings = replace(DEFAULT, e_vert=8, eta_levels=levels)
    assert vertical.full_levels(settings) == list(levels)
    assert vertical.full_levels(replace(settings, eta_levels=levels[::-1])) == list(levels)
    with pytest.raises(VerticalError, match="exactly e_vert"):
        vertical.full_levels(replace(settings, e_vert=9))
    with pytest.raises(VerticalError, match="decrease"):
        vertical.full_levels(
            replace(settings, eta_levels=(1.0, 0.99, 0.995, 0.5, 0.3, 0.2, 0.1, 0.0))
        )
    with pytest.raises(VerticalError, match="first eta level"):
        vertical.full_levels(
            replace(settings, eta_levels=(0.98, 0.9, 0.8, 0.5, 0.3, 0.2, 0.1, 0.0))
        )


def test_hybrid_coordinate_follows_terrain_then_flattens() -> None:
    eta = vertical.full_levels(DEFAULT)
    coefficients = vertical.coefficients(eta, 2, 0.2, DEFAULT.p_top)
    assert coefficients.c3f[0] == 1 and coefficients.c3f[-1] == 0
    assert all(b == 0 for e, b in zip(eta, coefficients.c3f, strict=True) if e < 0.2)
    sea = vertical.column(DEFAULT, eta, coefficients, 0.0)
    hill = vertical.column(DEFAULT, eta, coefficients, 800.0)
    # Near the ground the levels keep their height above the terrain
    assert hill[1] - 800 == pytest.approx(sea[1], rel=0.05)
    # Above etac the levels are pressure levels: the same height whatever the terrain
    top = next(k for k, e in enumerate(eta) if e < 0.2)
    assert hill[top + 1] == pytest.approx(sea[top + 1], abs=1.0)
    sigma = vertical.coefficients(eta, 0, 0.2, DEFAULT.p_top)
    flat = vertical.column(replace(DEFAULT, hybrid_opt=0), eta, sigma, 800.0)
    assert flat[top + 1] - sea[top + 1] > 50  # terrain-following up to the top


def test_profile_of_a_case(reference_case: Case) -> None:
    profile = vertical.profile(reference_case)
    assert len(profile.full) == reference_case.grid.e_vert
    assert profile.full[0].height_m == 0 and profile.full[1].height_m == pytest.approx(50, abs=0.2)
    assert len(profile.mass_heights_m) == reference_case.grid.e_vert - 1
    assert all(
        b > a for a, b in zip(profile.mass_heights_m, profile.mass_heights_m[1:], strict=False)
    )


def test_levels_typed_by_hand_go_to_the_namelist_and_are_used(reference_case: Case) -> None:
    """The user may type the full eta levels instead of the automatic ones: they are written as
    eta_levels (no automatic settings) and the levels shown are exactly those."""
    from owstudio.core.method import vertical_advice
    from owstudio.core.namelist.generate import build_namelist_input

    case = reference_case.model_copy(deep=True)
    typed = [
        1.0,
        0.993,
        0.983,
        0.97,
        0.954,
        0.934,
        0.909,
        0.88,
        0.8,
        0.7,
        0.6,
        0.5,
        0.4,
        0.3,
        0.2,
        0.1,
        0.0,
    ]
    case.grid.eta_levels = typed
    case.grid.e_vert = len(typed)
    domains = build_namelist_input(case)["domains"]
    assert domains["eta_levels"] == typed and "auto_levels_opt" not in domains
    profile = vertical.profile(case)
    assert [level.eta for level in profile.full] == typed
    assert vertical_advice.checks(case)[0].ok
    # Typed upside down in the wrong way: real.exe would stop, with its reason and no correction
    case.grid.eta_levels = [1.0, 0.9, 0.95, *typed[3:]]
    [real] = vertical_advice.checks(case)
    assert not real.ok and real.changes is None and "module_initialize_real" in real.source


# ------------------------------------------------------------------ hybrid coordinate, exactly WRF's


def _wrf_b(eta: float, etac: float) -> float:
    """B(eta) of WRF 4.8 (compute_vcoord_1d_coeffs, hybrid_opt = 2), written out independently."""
    b1 = 2.0 * etac**2 * (1.0 - etac)
    b2 = -etac * (4.0 - 3.0 * etac - etac**3)
    b3 = 2.0 * (1.0 - etac**3)
    b4 = -(1.0 - etac**2)
    b5 = (1.0 - etac) ** 4
    return 0.0 if eta < etac else (b1 + b2 * eta + b3 * eta**2 + b4 * eta**3) / b5


def _base_height(p: float, s: VerticalSettings) -> float:
    """Height of the pressure p in WRF's base state (T = T0 + A ln(p/p00), above the isothermal
    layer excluded): the inverse of the surface pressure formula of real.exe."""
    a, t00, p00 = s.base_lapse, s.base_temp, s.base_pres
    return -(a * vertical.R_D / (2 * vertical.G)) * (
        (math.log(p / p00) + t00 / a) ** 2 - (t00 / a) ** 2
    )


@pytest.mark.parametrize("etac", [0.2, 0.3])
@pytest.mark.parametrize("terrain", [0.0, 800.0])
def test_levels_follow_the_hybrid_formula(etac: float, terrain: float) -> None:
    """p_d = B(eta)(p_s - p_t) + [eta - B(eta)](p_0 - p_t) + p_t, and each level at the height of
    that pressure in the base state, over the sea and over relief."""
    s = replace(DEFAULT, etac=etac)
    eta = vertical.full_levels(s)
    c = vertical.coefficients(eta, 2, etac, s.p_top)
    for k, e in enumerate(eta):
        expected = 1.0 if k == 0 else 0.0 if k == len(eta) - 1 else _wrf_b(e, etac)
        assert c.c3f[k] == pytest.approx(expected, abs=1e-12)
    heights = vertical.column(s, eta, c, terrain)
    p_s = s.base_pres * math.exp(
        -s.base_temp / s.base_lapse
        + (
            (s.base_temp / s.base_lapse) ** 2
            - 2 * vertical.G * terrain / s.base_lapse / vertical.R_D
        )
        ** 0.5
    )
    for k, e in enumerate(eta):
        b = c.c3f[k]
        p_d = b * (p_s - s.p_top) + (e - b) * (vertical.P1000MB - s.p_top) + s.p_top
        assert c.c3f[k] * (p_s - s.p_top) + c.c4f[k] + s.p_top == pytest.approx(p_d, rel=1e-12)
        # Below the isothermal layer the base state is analytic: the level is where p_d is
        temperature = s.base_temp + s.base_lapse * math.log(p_d / s.base_pres)
        if temperature > s.iso_temp + 15:
            assert heights[k] == pytest.approx(
                _base_height(p_d, s), abs=max(0.5, 3e-4 * heights[k])
            )


def test_above_etac_levels_are_flat_and_sigma_follows_the_terrain() -> None:
    eta = vertical.full_levels(DEFAULT)
    hybrid = vertical.coefficients(eta, 2, 0.2, DEFAULT.p_top)
    sigma = vertical.coefficients(eta, 0, 0.2, DEFAULT.p_top)
    assert sigma.c3f == pytest.approx(eta)  # hybrid_opt = 0: B(eta) = eta, pure sigma
    p_sea = DEFAULT.base_pres
    p_hill = DEFAULT.base_pres * 0.84  # any surface pressure: above etac the pressure is the same
    sea = vertical.column(DEFAULT, eta, hybrid, 0.0)
    hill = vertical.column(DEFAULT, eta, hybrid, 1500.0)
    for k, e in enumerate(eta):
        if e < 0.2:
            mu = [p - DEFAULT.p_top for p in (p_sea, p_hill)]
            pressures = [hybrid.c3f[k] * m + hybrid.c4f[k] + DEFAULT.p_top for m in mu]
            assert pressures[0] == pressures[1]
            # Heights: flat up to real.exe's own integration from each ground (under 0.01 %)
            assert hill[k] == pytest.approx(sea[k], rel=1e-4)
    flat_sea = vertical.column(replace(DEFAULT, hybrid_opt=0), eta, sigma, 0.0)
    flat_hill = vertical.column(replace(DEFAULT, hybrid_opt=0), eta, sigma, 1500.0)
    assert flat_hill[-2] - flat_sea[-2] > 100


def test_the_project_hybrid_option_is_followed(reference_case: Case) -> None:
    case = reference_case.model_copy(deep=True)
    case.namelist_input.setdefault("dynamics", {})["hybrid_opt"] = 0
    assert vertical.settings(case).hybrid_opt == 0
    assert vertical.settings(reference_case).hybrid_opt == 2
