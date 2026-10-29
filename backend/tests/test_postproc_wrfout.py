import numpy as np
import pytest
import xarray as xr

from owstudio.core.postproc import wrfout

NZ, NY, NX = 5, 3, 4
# Heights of the staggered (w) levels above ground: mass levels sit at 25, 75, 125, 175, 225 m
Z_STAG = np.array([0.0, 50.0, 100.0, 150.0, 200.0, 250.0])
TERRAIN_M = 10.0


def make_dataset(u_profile: np.ndarray, v_value: float = 0.0) -> xr.Dataset:
    """A one-time wrfout-like dataset with flat terrain and the given U profile on mass levels."""
    geopotential = (Z_STAG + TERRAIN_M) * wrfout.GRAVITY
    ph = np.broadcast_to(geopotential[None, :, None, None], (1, NZ + 1, NY, NX))
    u = np.broadcast_to(u_profile[None, :, None, None], (1, NZ, NY, NX + 1))
    return xr.Dataset(
        {
            "Times": (("Time",), np.array([b"2025-10-01_00:00:00"])),
            "PH": (("Time", "bottom_top_stag", "south_north", "west_east"), ph.copy()),
            "PHB": (("Time", "bottom_top_stag", "south_north", "west_east"), np.zeros_like(ph)),
            "HGT": (("Time", "south_north", "west_east"), np.full((1, NY, NX), TERRAIN_M)),
            "U": (("Time", "bottom_top", "south_north", "west_east_stag"), u.copy()),
            "V": (
                ("Time", "bottom_top", "south_north_stag", "west_east"),
                np.full((1, NZ, NY + 1, NX), v_value),
            ),
            "POWER": (("Time", "south_north", "west_east"), np.full((1, NY, NX), 1.5e6)),
        }
    )


def test_times_are_decoded():
    ds = make_dataset(np.ones(NZ))
    assert str(wrfout.times(ds)[0]) == "2025-10-01 00:00:00"


def test_height_above_ground_is_mass_level_height():
    ds = make_dataset(np.ones(NZ))
    z = wrfout.height_above_ground(ds)
    np.testing.assert_allclose(z.isel(Time=0, south_north=0, west_east=0), [25, 75, 125, 175, 225])


def test_wind_speed_interpolates_linearly_between_levels():
    # U grows by 1 m/s every 50 m: 5, 6, 7, 8, 9 at 25, 75, ... m
    ds = make_dataset(np.array([5.0, 6.0, 7.0, 8.0, 9.0]))
    speed = wrfout.wind_speed_at_height(ds, 100.0)
    np.testing.assert_allclose(speed, 6.5)
    assert speed.dims == ("Time", "south_north", "west_east")


def test_wind_speed_combines_both_components():
    ds = make_dataset(np.full(NZ, 3.0), v_value=4.0)
    np.testing.assert_allclose(wrfout.wind_speed_at_height(ds, 80.0), 5.0)


def test_wind_speed_below_lowest_level_is_extrapolated():
    ds = make_dataset(np.array([5.0, 6.0, 7.0, 8.0, 9.0]))
    np.testing.assert_allclose(wrfout.wind_speed_at_height(ds, 0.0), 4.5)


def test_farm_power_sums_cells_in_megawatts():
    ds = make_dataset(np.ones(NZ))
    assert wrfout.farm_power(ds).item() == pytest.approx(1.5 * NY * NX)
