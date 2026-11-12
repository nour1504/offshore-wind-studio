"""Starting points for the physics and dynamics options. Users can change every value."""

from owstudio.core.case.model import NamelistValue

# Cumulus parameterization is switched off below this grid spacing
CONVECTION_PERMITTING_DX_M = 5000.0


def offshore_wind_physics(domain_dx: list[float]) -> dict[str, NamelistValue]:
    """Thompson, RRTMG, MYNN PBL and surface layer, Noah; cumulus only on coarse domains.

    MYNN is required by the Fitch scheme, and advecting its TKE lets turbine
    turbulence travel downstream.
    """
    n = len(domain_dx)
    return {
        "mp_physics": [8] * n,
        "ra_lw_physics": [4] * n,
        "ra_sw_physics": [4] * n,
        "radt": [round(domain_dx[0] / 1000)] * n,
        "sf_sfclay_physics": [5] * n,
        "sf_surface_physics": [2] * n,
        "bl_pbl_physics": [5] * n,
        "bldt": [0] * n,
        "bl_mynn_tkeadvect": [True] * n,
        "cu_physics": [1 if dx > CONVECTION_PERMITTING_DX_M else 0 for dx in domain_dx],
        "cudt": [5] * n,
        "num_soil_layers": 4,
        "sf_urban_physics": [0] * n,
    }


def default_dynamics(n: int) -> dict[str, NamelistValue]:
    """Usual real-data settings recommended by the WRF documentation."""
    return {
        "hybrid_opt": 2,
        "w_damping": 1,
        "diff_opt": [1] * n,
        "km_opt": [4] * n,
        "diff_6th_opt": [2] * n,
        "diff_6th_factor": [0.12] * n,
        "base_temp": 290.0,
        "damp_opt": 3,
        "zdamp": [5000.0] * n,
        "dampcoef": [0.2] * n,
        "khdif": [0] * n,
        "kvdif": [0] * n,
        "non_hydrostatic": [True] * n,
        "moist_adv_opt": [1] * n,
        "scalar_adv_opt": [1] * n,
    }
