"""Energy over the computed period, wake losses and the Fitch reconstruction, on synthetic runs
with known values."""

from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from helpers import REFERENCE
from test_extract import wrfout

from owstudio.core import tslist
from owstudio.core.case.model import Case, Farm, FarmScheme, TimeSeries, Turbine
from owstudio.core.energy import fitch, integrate
from owstudio.core.energy.curves import turbine_types, wrf_power_w
from owstudio.core.energy.production import RunPower, sites
from owstudio.core.energy.summary import run_energy

T0 = "2025-10-01_00:00:00"
TIMES = [T0, "2025-10-01_01:00:00", "2025-10-01_02:00:00"]


def hourly(values: list[float], gaps_after: int | None = None) -> pd.Series:
    times = pd.date_range("2025-10-01", periods=len(values), freq="h", tz="UTC")
    if gaps_after is not None:
        times = times[: gaps_after + 1].append(times[gaps_after + 1 :] + pd.Timedelta(hours=3))
    return pd.Series(values, index=times)


# ------------------------------------------------------------- integration


def test_trapezoid_with_gaps_and_spin_up() -> None:
    power = hourly([0.0, 10.0, 10.0, 10.0, 10.0], gaps_after=2)  # 3 h gap between 02:00 and 06:00
    energy = integrate.integrate(power)
    assert energy.energy_wh == pytest.approx(5 + 10 + 10) and energy.covered_h == pytest.approx(3)
    assert len(energy.gaps) == 1
    after_spin_up = integrate.integrate(power, datetime(2025, 10, 1, 1))
    assert after_spin_up.energy_wh == pytest.approx(20)


def test_energy_by_day_and_capacity_factor() -> None:
    power = pd.Series(1e6, index=pd.date_range("2025-10-01", periods=49, freq="h", tz="UTC"))
    days = integrate.by_period(power, "day")
    assert days["energy_wh"].tolist() == pytest.approx([24e6, 24e6])
    energy = integrate.integrate(power)
    assert integrate.capacity_factor(energy, 2e6) == pytest.approx(0.5)
    value, reason = integrate.aep(energy)
    assert value is None and "less than a year" in reason


def test_aep_from_a_full_year() -> None:
    power = pd.Series(1e6, index=pd.date_range("2025-01-01", periods=8761, freq="h", tz="UTC"))
    value, _ = integrate.aep(integrate.integrate(power))
    assert value == pytest.approx(1e6 * integrate.HOURS_PER_YEAR)


# ------------------------------------------------------- Fitch formula


def test_fitch_reconstruction_without_induction_is_the_table() -> None:
    turbine = turbine_types(Case.from_yaml(REFERENCE))[1]
    z = np.array([[25.0, 75.0, 125.0]])
    u = np.array([[5.0, 7.0, 9.0]])
    power = fitch.turbine_power(z, u, np.zeros_like(u), turbine, 1, 3000.0, induction=False)
    assert power[0] == pytest.approx(
        wrf_power_w(np.array([np.interp(turbine.hub_height_m, z[0], u[0])]), turbine)[0]
    )


def test_fitch_induction_raises_the_hub_speed() -> None:
    turbine = turbine_types(Case.from_yaml(REFERENCE))[1]
    z, u = np.array([[25.0, 75.0, 125.0]]), np.array([[5.0, 7.0, 9.0]])
    plain = fitch.turbine_power(z, u, np.zeros_like(u), turbine, 1, 3000.0, induction=False)
    corrected = fitch.turbine_power(z, u, np.zeros_like(u), turbine, 2, 3000.0, induction=True)
    assert corrected[0] > plain[0]


# ----------------------------------------------------------- run energy


def farms_case(farms: dict[str, tuple[float, float]]) -> Case:
    case = Case.from_yaml(REFERENCE)
    case.farms = [
        Farm(id=f, name=f"Farm {f}", turbines=[Turbine(lat=lat, lon=lon, id=f"{f}1")])
        for f, (lat, lon) in farms.items()
    ]
    case.farm_scheme = FarmScheme(scheme="fitch", domains=[2])
    case.period.start = datetime(2025, 10, 1)
    return case


SITES = {"A": (54.1, 7.1), "B": (54.1, 7.3), "C": (54.3, 7.1)}
CELLS = {"A": (1, 1), "B": (1, 3), "C": (3, 1)}


def write_run(root: Path, case: Case, power_mw: dict[str, float], control: bool = False) -> None:
    """A run folder with POWER (MW) in the cells of the given farms, constant after t0."""
    power = np.zeros((len(TIMES), 6, 6))
    for farm, value in power_mw.items():
        j, i = CELLS[farm]
        power[1:, j, i] = value * 1e6
    main = root / "outputs" / "main"
    main.mkdir(parents=True, exist_ok=True)
    wrfout(TIMES, {"POWER": (("Time", "south_north", "west_east"), power)}).to_netcdf(
        main / "wrfout_d02_2025-10-01_00-00-00"
    )
    case.to_yaml(main / "case.yaml")
    if control:
        out = root / "outputs" / "control"
        out.mkdir(parents=True)
        wrfout(TIMES).to_netcdf(out / "wrfout_d02_2025-10-01_00-00-00")


def free_power_w(case: Case) -> float:
    turbine = turbine_types(case)[1]
    hub = float(np.interp(turbine.hub_height_m, [25, 75, 125], [5, 7, 9]))
    return float(wrf_power_w(np.array([hub]), turbine)[0])


def test_run_energy_with_control_run(tmp_path: Path) -> None:
    case = farms_case({"A": SITES["A"]})
    write_run(tmp_path, case, {"A": 0.5}, control=True)
    result = run_energy(tmp_path, case, "wrf")
    farm = result["farms"][0]
    # POWER from 01:00 (the initial time is left out): 0.5 MW during 1 h
    assert farm["energy_mwh"] == pytest.approx(0.5) and farm["covered_h"] == pytest.approx(1)
    free = free_power_w(case) / 1e6  # reference: same conversion on the control run's cell wind
    assert farm["reference_energy_mwh"] == pytest.approx(free)
    assert farm["loss_mwh"] == pytest.approx(free - 0.5) and result["aep_mwh"] is None
    assert any("initial time left out" in n for n in result["notes"])


def test_repeated_labels_across_farms_keep_separate_power(tmp_path: Path) -> None:
    case = farms_case({"A": SITES["A"], "B": SITES["B"]})
    for farm in case.farms:
        farm.turbines[0].id = "A01"
    write_run(tmp_path, case, {"A": 0.5, "B": 1.0})
    result = run_energy(tmp_path, case, "wrf")
    assert {row["label"] for row in result["turbines"]} == {"A/A01", "B/A01"}
    assert {row["farm"]: row["energy_mwh"] for row in result["turbines"]} == pytest.approx(
        {"A": 0.5, "B": 1.0}
    )
    assert result["total"]["energy_mwh"] == pytest.approx(1.5)


@pytest.mark.parametrize("scheme", ["fitch", "mav"])
def test_repeated_labels_in_shared_cell_conserve_wrf_power(tmp_path: Path, scheme: str) -> None:
    case = farms_case({"A": SITES["A"], "B": SITES["A"]})
    assert case.farm_scheme is not None
    case.farm_scheme.scheme = scheme  # type: ignore[assignment]
    for farm in case.farms:
        farm.turbines[0].id = "A01"
    main = tmp_path / "outputs" / "main"
    main.mkdir(parents=True)
    power = np.zeros((len(TIMES), 6, 6))
    power[1:, 1, 1] = 1.2e6
    dataset = wrfout(TIMES, {"POWER": (("Time", "south_north", "west_east"), power)})
    dataset.attrs["DX"] = 3000.0  # exercise the recomputed Fitch shares as well as MAV equal shares
    dataset.to_netcdf(main / "wrfout_d02_2025-10-01_00-00-00")
    case.to_yaml(main / "case.yaml")
    result = run_energy(tmp_path, case, "wrf")
    assert len(result["turbines"]) == 2
    assert {row["farm"]: row["energy_mwh"] for row in result["turbines"]} == pytest.approx(
        {"A": 0.6, "B": 0.6}
    )
    assert result["total"]["energy_mwh"] == pytest.approx(1.2)


def test_explicit_labels_colliding_with_automatic_and_qualified_labels() -> None:
    case = farms_case({"A": SITES["A"], "B": SITES["B"], "C": SITES["C"]})
    case.farms[0].turbines[0].id = None  # automatic A-1
    case.farms[1].turbines[0].id = "A-1"
    case.farms[2].turbines[0].id = "A/A-1"  # must retain this globally unique legacy label
    labels = [site.label for site in sites(case)]
    assert len(set(labels)) == 3
    assert labels[2] == "A/A-1"
    assert labels[0] == "A/A-1#2" and labels[1] == "B/A-1"


def test_tslist_lookup_uses_unique_prefixes_even_when_names_truncate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = farms_case({"A": SITES["A"], "B": SITES["B"]})
    case.time_series = TimeSeries(turbines="each")
    for index, farm in enumerate(case.farms):
        farm.id = f"long-common-farm-prefix-{index}"
        farm.turbines[0].id = "abcdefghijklmnopqrstuvwx12345678"  # names exceed WRF's A25 field
    write_run(tmp_path, case, {"A": 0.5, "B": 1.0})
    generated = tslist.locations(case)
    assert len({point.name for point in generated}) == 1  # identical truncated display fields
    assert [point.prefix for point in generated] == ["T0001", "T0002"]
    called = []

    class Series:
        def __init__(self, value: float) -> None:
            self.values = hourly([value, value, value])

    class FakeSeriesFiles:
        def __init__(self, folder: Path) -> None:
            pass

        def has(self, prefix: str, domain: int) -> bool:
            return True

        def series(self, prefix: str, domain: int, name: str, height: float) -> tuple[None, Series]:
            called.append(prefix)
            return None, Series(5.0 if prefix == "T0001" else 9.0)

    monkeypatch.setattr("owstudio.core.energy.production.TimeSeriesFiles", FakeSeriesFiles)
    source = RunPower(tmp_path / "outputs" / "main", case)
    chosen = sites(case)
    assert source.hub_wind(chosen[0], "point").iloc[0] == 5.0
    assert source.hub_wind(chosen[1], "point").iloc[0] == 9.0
    assert called == ["T0001", "T0002"]
