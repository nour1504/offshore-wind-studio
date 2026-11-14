"""The tslist export of the Exporter tab (core/extract/tslist_export.py, api/routes_export.py)."""

from pathlib import Path

import numpy as np
import pytest
from helpers import REFERENCE
from test_tslist import patch_location, write_location

from owstudio.core import tslist
from owstudio.core.case.model import Case, TimeSeries, TimeSeriesPoint
from owstudio.core.extract import tslist_export


def run_folder(root: Path, patched: bool, step_s: int = 15) -> Case:
    """A run of the reference project with one tslist location per cell: the first cell of the
    farm (C0001, its turbines) and a mast, one hour of 15 s steps, with a run without turbines."""
    case = Case.from_yaml(REFERENCE)
    case.time_series = TimeSeries(
        turbines="cells", points=[TimeSeriesPoint(name="Mast", prefix="MAST", lat=55.56, lon=7.7)]
    )
    steps = 3600 // step_s
    hours = np.arange(1, steps + 1) * step_s / 3600
    for stage in ("main", "control"):
        folder = root / "outputs" / stage
        (folder / "tslist").mkdir(parents=True)
        case.to_yaml(folder / "case.yaml")
        write_location(folder / "tslist", "C0001", 0.0, hours)
        if patched:
            kw = np.full(steps, 3000.0 if stage == "main" else 0.0)
            patch_location(folder / "tslist", "C0001", np.full(steps, 0.002), kw, np.full((steps, 3), 0.6), "TK")  # fmt: skip
    return case


def test_long_and_wide_tables_of_a_patched_run(tmp_path: Path) -> None:
    case = run_folder(tmp_path, patched=True)
    places = tslist_export.places(tmp_path / "outputs" / "main", case)
    assert [p.prefix for p in places] == ["C0001"]
    place = places[0]
    members = tslist.turbines_at(case)["C0001"]
    assert len(place.turbines) == len(members) > 1
    keys = ["wind_speed", "turbulence_intensity", "tke", "power_cell", "power_turbine", "temperature_2m"]  # fmt: skip

    long = tslist_export.table(tmp_path, case, [place.key], keys, [75.0], 600, "long", True)
    frame = long.frame
    assert len(frame) == 6 and not long.missing
    assert frame["wind_speed_75m [m/s]"].iloc[0] == pytest.approx(8.0)
    # TKE 0.6 and U 8 m/s: TI = sqrt(0.6 / 0.945) / 8
    assert frame["tke_75m [m2/s2]"].iloc[0] == pytest.approx(0.6)
    assert frame["turbulence_intensity_75m [%]"].iloc[0] == pytest.approx(100 * np.sqrt(0.6 / 0.945) / 8, rel=1e-4)  # fmt: skip
    # WRF's POWER of the cell (3 MW) and one turbine's share of it
    assert frame["cell_power [MW]"].iloc[0] == pytest.approx(3.0)
    assert int(frame["turbines_in_cell"].iloc[0]) == len(members)
    # Without the wrfout of the parameterization, the turbine's power is not POWER / n: it is the
    # power curve; with them it is (test_energy.py). The cell's POWER is not given without turbines
    assert "turbine_power [MW]" in frame and "turbine_power_no_farm [MW]" in frame
    assert "cell_power_no_farm [MW]" not in frame
    # 285.15 K, but one value missing in the first interval (write_location): no mean there
    assert np.isnan(frame["temperature_2m [degC]"].iloc[0])
    assert frame["temperature_2m [degC]"].iloc[1] == pytest.approx(12.0, abs=0.01)

    wide = tslist_export.table(tmp_path, case, [place.key], keys, [75.0], 600, "wide", False)
    columns = list(wide.frame.columns)
    title = place.title()
    assert f"wind_speed_75m [m/s] {title}" in columns and all(lab in title for lab in place.labels)
    # One power column per turbine, named by its label
    assert sum(c.startswith("turbine_power [MW] ") for c in columns) == len(members)
    assert len(wide.frame) == 6


def test_shear_and_veer_between_the_lowest_and_the_highest_heights(tmp_path: Path) -> None:
    case = run_folder(tmp_path, patched=False)
    key = tslist_export.places(tmp_path / "outputs" / "main", case)[0].key
    keys = ["shear_exponent", "wind_veer"]
    frame = tslist_export.table(tmp_path, case, [key], keys, [125.0, 25.0, 75.0], 600, "long", False).frame  # fmt: skip
    # 6 m/s at 25 m, 10 m/s at 125 m, the same direction (test_tslist.write_location)
    assert frame["shear_exponent_25-125m [-]"].iloc[0] == pytest.approx(np.log(10 / 6) / np.log(5), rel=1e-4)  # fmt: skip
    assert frame["wind_veer_25-125m [deg]"].iloc[0] == pytest.approx(0.0, abs=1e-6)
    one = tslist_export.table(tmp_path, case, [key], keys, [100.0], 600, "long", False)
    assert set(one.missing) == {"shear_exponent [-]", "wind_veer [deg]"}


def test_without_wind_farm_parameterization_the_cell_power_is_not_given(tmp_path: Path) -> None:
    case = run_folder(tmp_path, patched=True)
    key = tslist_export.places(tmp_path / "outputs" / "main", case)[0].key
    keys = ["power_cell", "power_turbine"]
    with_farms = tslist_export.table(tmp_path, case, [key], keys, [], 600, "long", False)
    assert "cell_power [MW]" in with_farms.frame and not with_farms.missing
    # Without the wrfout of the parameterization: the power curve (see above)
    assert with_farms.power == {"turbine_power [MW]": ["curve"]}
    case.farm_scheme = None
    without = tslist_export.table(tmp_path, case, [key], keys, [], 600, "long", False)
    assert "cell_power [MW]" not in without.frame and "turbine_power [MW]" in without.frame
    assert "parameterization" in without.missing["cell_power [MW]"]


def test_a_stock_wrf_reports_what_it_lacks(tmp_path: Path) -> None:
    case = run_folder(tmp_path, patched=False)
    key = tslist_export.places(tmp_path / "outputs" / "main", case)[0].key
    result = tslist_export.table(
        tmp_path, case, [key], ["wind_speed", "tke", "friction_velocity"], [100.0], 0, "long", False
    )
    assert "wind_speed_100m [m/s]" in result.frame
    assert set(result.missing) == {"tke_100m [m2/s2]", "friction_velocity [m/s]"}
    with pytest.raises(tslist_export.ExportError):
        tslist_export.table(tmp_path, case, [key], ["nothing"], [], 0, "long", False)


def test_accumulated_rain_at_the_end_of_every_interval_whatever_the_step(tmp_path: Path) -> None:
    """18 s steps: no step ends at 10, 20, 40 or 50 min. The total there lies between the two steps
    around it, linear (each value stands for the step ending at it); at 30 and 60 min a step ends
    and gives it."""
    case = run_folder(tmp_path, patched=False, step_s=18)
    path = tmp_path / "outputs" / "main" / "tslist" / "C0001.d02.TS"
    header, *rows = path.read_text().splitlines()
    lines = []
    for k, row in enumerate(rows, start=1):
        tokens = row.split()
        tokens[5 + 11] = f"{0.01 * k:.5f}"  # RAINC: 0.01 mm more at each step
        lines.append(" ".join(tokens))
    path.write_text(header + "\n" + "\n".join(lines) + "\n")
    key = tslist_export.places(tmp_path / "outputs" / "main", case)[0].key
    frame = tslist_export.table(tmp_path, case, [key], ["rain_convective"], [], 600, "long", False).frame  # fmt: skip
    rain = frame["convective_rain_total [mm]"]
    assert len(rain) == 6
    assert rain.to_numpy() == pytest.approx(0.01 * np.arange(600, 3601, 600) / 18, abs=1e-9)
    # Each model step as it is
    each = tslist_export.table(tmp_path, case, [key], ["rain_convective"], [], 0, "long", False).frame  # fmt: skip
    assert len(each) == 200 and each["convective_rain_total [mm]"].iloc[-1] == pytest.approx(2.0)
