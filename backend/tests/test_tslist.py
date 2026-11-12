"""tslist generation and reading of WRF time series files written in WRF's exact formats."""

from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

from owstudio.core import tslist
from owstudio.core.case.checks import check_case
from owstudio.core.case.model import Case, TimeSeries, TimeSeriesPoint
from owstudio.core.namelist.generate import build_namelist_input
from owstudio.core.postproc.tslist_reader import TimeSeriesSet, average, read_header

REFERENCE = Path(__file__).parent / "fixtures" / "horns-rev" / "case.yaml"


@pytest.fixture
def case() -> Case:
    case = Case.from_yaml(REFERENCE)
    case.time_series = TimeSeries(
        turbines="cells",
        points=[TimeSeriesPoint(name="FINO3 mast", prefix="FINO3", lat=55.195, lon=7.158)],
    )
    return case


def fortran_read(line: str) -> tuple[str, str, float, float]:
    """What WRF reads with FMT='(A25,1X,A5,1X,F7.3,1X,F8.3)'."""
    return line[0:25], line[26:31], float(line[32:39]), float(line[40:48])


def test_tslist_file_follows_wrf_columns(case: Case) -> None:
    text = tslist.tslist_text(tslist.locations(case))
    lines = text.splitlines()
    # The header tells WRF whether coordinates are LAT/LON or I/J: it reads columns 33-39, 42-48
    assert lines[1][32:39].strip() == "LAT" and lines[1][41:48].strip() == "LON"
    name, prefix, lat, lon = fortran_read(lines[-1])
    assert (name.strip(), prefix.strip(), lat, lon) == ("FINO3 mast", "FINO3", 55.195, 7.158)


def test_one_location_per_turbine_cell(case: Case) -> None:
    points = tslist.locations(case)
    cells = [p for p in points if p.prefix.startswith("C")]
    # The 80 turbines (4.5 x 5 km) spread over a few 3 km cells of d02
    assert 2 <= len(cells) <= 9
    assert sum(int(p.name.split("(")[1].split()[0]) for p in cells) == 80
    assert points[-1].prefix == "FINO3"


def test_one_location_per_turbine(case: Case) -> None:
    assert case.time_series is not None
    case.time_series.turbines = "each"
    points = tslist.locations(case)
    assert [p.prefix for p in points[:2]] == ["T0001", "T0002"] and len(points) == 81
    line = tslist.tslist_text(points).splitlines()[3]
    # As many decimals as the F7.3 and F8.3 fields hold: about 10 m and 1 m here
    assert fortran_read(line)[2:] == (55.5063, 7.80425)


def test_namelist_enables_time_series(case: Case) -> None:
    domains = build_namelist_input(case)["domains"]
    assert domains["max_ts_locs"] == len(tslist.locations(case))
    assert domains["max_ts_level"] == 15
    assert domains["tslist_unstagger_winds"] is True


def test_checks_flag_duplicate_prefixes_and_outside_points(case: Case) -> None:
    assert case.time_series is not None
    case.time_series.points.append(TimeSeriesPoint(name="Copy", prefix="fino3", lat=55.2, lon=7.2))
    case.time_series.points.append(
        TimeSeriesPoint(name="Far away", prefix="FAR", lat=40.0, lon=0.0)
    )
    messages = [i.message for i in check_case(case)]
    assert any("prefixes must be unique" in m for m in messages)
    assert any("1 point outside every domain" in m for m in messages)


HEADER_FORMAT = "{name:<25} {domain:2d}{ts_id:3d} {prefix:<5} ({lat:7.3f},{lon:8.3f}) ({i:4d},{j:4d}) ({glat:7.3f},{glon:8.3f}) {elev:6.1f} meters  {start}"


def write_location(directory: Path, prefix: str, elevation: float, hours: np.ndarray) -> None:
    header = HEADER_FORMAT.format(
        name="Cell 50,50 (9 turb.)", domain=2, ts_id=1, prefix=prefix, lat=55.486, lon=7.84,
        i=50, j=50, glat=55.487, glon=7.838, elev=elevation, start="2025-10-01_00:00:00",
    )  # fmt: skip
    rows = []
    for k, hour in enumerate(hours):
        values = [285.15, 0.008, 3.0, 4.0, 101325.0] + [0.0] * 9
        if k == 1:
            values[0] = 1e30  # missing: printed as asterisks by the f13.5 format
        fields = "".join(f"{v:13.5f} " if v < 1e8 else "*" * 13 + " " for v in values)
        rows.append(f"{2:2d}{hour:13.6f}{1:5d}{50:5d}{50:5d} {fields}")
    (directory / f"{prefix}.d02.TS").write_text(header + "\n" + "\n".join(rows) + "\n")
    # Three levels at 25, 75 and 125 m above ground; wind 6, 8, 10 m/s from the south-west
    for kind, level_values in (
        ("PH", [elevation + 25, elevation + 75, elevation + 125]),
        ("UU", [6 / np.sqrt(2), 8 / np.sqrt(2), 10 / np.sqrt(2)]),
        ("VV", [6 / np.sqrt(2), 8 / np.sqrt(2), 10 / np.sqrt(2)]),
        ("TH", [290.0, 291.0, 292.0]),
        ("PR", [100000.0, 99400.0, 98800.0]),
    ):
        lines = [f"{hour:13.6f} " + "".join(f"{v:13.5f} " for v in level_values) for hour in hours]
        (directory / f"{prefix}.d02.{kind}").write_text(header + "\n" + "\n".join(lines) + "\n")


def test_profiles_read_asterisks_cut_lines_and_interpolate_per_row(tmp_path: Path) -> None:
    from owstudio.core.postproc.tslist_reader import interpolate_rows, read_profile

    header = HEADER_FORMAT.format(
        name="Cell", domain=2, ts_id=1, prefix="C0009", lat=55.0, lon=7.0,
        i=1, j=1, glat=55.0, glon=7.0, elev=0.0, start="2025-10-01_00:00:00",
    )  # fmt: skip
    path = tmp_path / "C0009.d02.UU"
    rows = ["     0.004167      1.00000      2.00000      3.00000 "] * 3
    rows[1] = "     0.008333      1.00000 *************      3.00000 "
    path.write_text(header + "\n" + "\n".join(rows) + "\n     0.0125    1.0\n")
    values = read_profile(path).to_numpy()
    # The cut last line is left out; the asterisks are a missing value
    assert values.shape == (3, 3) and np.isnan(values[1, 1]) and values[2, 2] == 3.0
    # The file is read again when it changes
    path.write_text(header + "\n" + rows[0] + "\n")
    assert read_profile(path).shape == (1, 3)

    z = np.array([[10.0, 50.0, 100.0], [10.0, 50.0, 100.0], [20.0, np.nan, 100.0]])
    v = np.array([[1.0, 5.0, 10.0], [1.0, 5.0, 10.0], [2.0, 9.0, 10.0]])
    assert interpolate_rows(z, v, 75.0) == pytest.approx([7.5, 7.5, 2.0 + 8.0 * 55 / 80])
    assert (
        np.isnan(interpolate_rows(z, v, 5.0)).all()
        and np.isnan(interpolate_rows(z, v, 150.0)).all()
    )
    assert interpolate_rows(z, v, 100.0) == pytest.approx([10.0, 10.0, 10.0])


def test_header_is_parsed() -> None:
    line = HEADER_FORMAT.format(
        name="NZCM McMurdo", domain=2, ts_id=7, prefix="mcm", lat=-77.85, lon=166.71,
        i=153, j=207, glat=-77.768, glon=166.5, elev=81.8, start="2025-10-01_00:00:00",
    )  # fmt: skip
    location = read_header(line)
    assert (location.name, location.prefix, location.domain) == ("NZCM McMurdo", "mcm", 2)
    assert (location.i, location.j, location.elevation) == (153, 207, 81.8)
    assert location.start == datetime(2025, 10, 1)


def test_series_give_hub_height_wind_and_surface_variables(tmp_path: Path) -> None:
    hours = np.arange(1, 121) * 15 / 3600  # 15 s time step over half an hour, as WRF writes
    write_location(tmp_path, "C0001", elevation=-20.0, hours=hours)
    data = TimeSeriesSet(tmp_path)
    assert [loc.prefix for loc in data.locations()] == ["C0001"]

    series = data.series("C0001", 2, hub_height_m=100.0)
    assert series.index[1] == datetime(2025, 10, 1, 0, 0, 30)
    assert series["wind_speed_hub"].iloc[0] == pytest.approx(9.0)  # halfway between 75 and 125 m
    assert series["wind_direction_hub"].iloc[0] == pytest.approx(225.0)
    assert series["wind_speed_10m"].iloc[0] == pytest.approx(5.0)
    assert np.isnan(series["temperature_2m"].iloc[1])  # the asterisks
    assert series["temperature_2m"].iloc[0] == pytest.approx(12.0)
    # Temperature at the height from the profiles of θ and pressure: θ (p / p0)^(Rd/cp)
    assert series["temperature_hub"].iloc[0] == pytest.approx(
        291.5 * (99100.0 / 1e5) ** (1 / 3.5) - 273.15
    )

    # Means over ]t - 10 min, t], stamped at t; the missing temperature leaves a hole
    ten_minutes = average(series, 600)
    assert len(ten_minutes) == 3 and ten_minutes.index[0] == datetime(2025, 10, 1, 0, 10)
    assert ten_minutes["wind_direction_hub"].iloc[0] == pytest.approx(225.0)
    assert np.isnan(ten_minutes["temperature_2m"].iloc[0])
    assert ten_minutes["temperature_2m"].iloc[1] == pytest.approx(12.0)


def test_api_serves_time_series_with_and_without_farm(tmp_path: Path) -> None:
    from helpers import make_client

    from owstudio.core.case.workspace import Workspace
    from owstudio.core.storage import Storage

    case_id = Workspace(tmp_path / "data").create(Case.from_yaml(REFERENCE))
    outputs = Storage(tmp_path / "data").create_run(case_id).root / "outputs"
    hours = np.arange(1, 241) * 15 / 3600
    for run in ("main", "control"):
        (outputs / run / "tslist").mkdir(parents=True)
        write_location(outputs / run / "tslist", "C0001", elevation=0.0, hours=hours)
    Case.from_yaml(REFERENCE).to_yaml(outputs / "main" / "case.yaml")
    client = make_client(tmp_path)

    index = client.get(f"/api/cases/{case_id}/results/tslist").json()
    assert index["locations"][0]["prefix"] == "C0001" and index["locations"][0]["has_control"]

    series = client.get(
        f"/api/cases/{case_id}/results/tslist/C0001",
        params={"domain": 2, "height": 75, "average_s": 600},
    ).json()
    assert len(series) == 6
    assert series[0]["wind_speed_hub"] == pytest.approx(8.0)
    assert series[0]["wind_speed_hub_no_farm"] == pytest.approx(8.0)

    assert (
        client.get(f"/api/cases/{case_id}/results/tslist/NOPE", params={"domain": 2}).status_code
        == 404
    )

    # The Exporter tab: the cells offered, a preview read at the first cell, then the file
    offer = client.get(f"/api/cases/{case_id}/export/tslist").json()
    assert offer["reference"] and [p["prefixes"] for p in offer["places"]] == [["C0001"]]
    key = offer["places"][0]["key"]
    chosen = {"points": [key], "quantities": ["wind_speed", "wind_direction"], "heights": [75]}
    preview = client.get(f"/api/cases/{case_id}/export/tslist/preview", params=chosen).json()
    assert preview["times"] == 6 and preview["first"].startswith("2025-10-01T00:10:00")
    assert preview["columns"][:3] == ["time_utc_end", "point", "turbines_in_cell"]
    lines = client.get(f"/api/cases/{case_id}/export/tslist.csv", params=chosen).text.splitlines()
    # The source, the averaging and the heights first, then the table stamped at the end of
    # each interval, the run without turbines beside
    assert lines[0].startswith("# Source: tslist") and "]t - 600 s, t]" in lines[1]
    rows = [line for line in lines if not line.startswith("#")]
    assert rows[0].startswith("time_utc_end,point,turbines_in_cell,turbines,wind_speed_75m [m/s]")
    assert "wind_speed_75m_no_farm [m/s]" in rows[0] and len(rows) == 7
    # Over a chosen period: ]00:10, 00:40]
    period = {**chosen, "start": "2025-10-01T00:10:00Z", "end": "2025-10-01T00:40:00Z"}
    kept = client.get(f"/api/cases/{case_id}/export/tslist.csv", params=period).text.splitlines()
    assert [row.split(",")[0] for row in kept if not row.startswith("#")][1:] == [
        "2025-10-01 00:20:00",
        "2025-10-01 00:30:00",
        "2025-10-01 00:40:00",
    ]
    assert any("]2025-10-01 00:10:00, 2025-10-01 00:40:00]" in line for line in kept)
    unknown = client.get(
        f"/api/cases/{case_id}/export/tslist.csv", params={**chosen, "quantities": ["nope"]}
    )
    assert unknown.status_code == 422

    # The heights offered first: the hub heights of the run's turbines, also in a run without
    # the wind farm parameterization (their power is then the curve at that height)
    from owstudio.core.windfarm.catalog import turbine_types

    reference = Case.from_yaml(REFERENCE)
    types = turbine_types(reference)
    hubs = sorted(
        {types[t.type].hub_height_m for farm in reference.enabled_farms for t in farm.turbines}
    )
    assert offer["hub_heights_m"] == hubs
    reference.farm_scheme = None
    reference.to_yaml(outputs / "main" / "case.yaml")
    assert client.get(f"/api/cases/{case_id}/export/tslist").json()["hub_heights_m"] == hubs


def test_run_series_give_ten_minute_means_and_power(tmp_path: Path) -> None:
    """Analyses read the tslist locations as 10-minute means: speed, direction from the mean
    components, and the power of the cell's turbines."""
    from helpers import make_client

    from owstudio.core.case.workspace import Workspace
    from owstudio.core.energy.curves import wrf_power_w
    from owstudio.core.storage import Storage
    from owstudio.core.windfarm.catalog import turbine_types

    case = Case.from_yaml(REFERENCE)
    case.time_series = TimeSeries(turbines="cells")
    case_id = Workspace(tmp_path / "data").create(case)
    run = Storage(tmp_path / "data").create_run(case_id)
    folder = run.root / "outputs" / "main" / "tslist"
    folder.mkdir(parents=True)
    hours = np.arange(1, 241) * 15 / 3600  # one hour of 15 s steps
    write_location(folder, "C0001", elevation=0.0, hours=hours)
    # At 75 m the speed alternates 7 and 9 m/s from the south-west: mean 8, deviation 1
    header = (folder / "C0001.d02.UU").read_text().splitlines()[0]
    for kind in ("UU", "VV"):
        lines = [
            f"{hour:13.6f} "
            + "".join(f"{v / np.sqrt(2):13.5f} " for v in (6, 7 if k % 2 else 9, 10))
            for k, hour in enumerate(hours)
        ]
        (folder / f"C0001.d02.{kind}").write_text(header + "\n" + "\n".join(lines) + "\n")
    case.to_yaml(run.root / "outputs" / "main" / "case.yaml")
    client = make_client(tmp_path)

    def series(variable: str, height: float | None = 75) -> dict:
        ref = {
            "kind": "run",
            "case_id": case_id,
            "variable": variable,
            "location": "C0001",
            "height_m": height,
            "options": {"averaging_s": 600},
        }
        answer = client.post("/api/explore/series", json={"refs": [ref]})
        assert answer.status_code == 200, answer.text
        return answer.json()["series"][0]

    speed = series("wind_speed")
    assert len(speed["values"]) == 6 and speed["values"][0] == pytest.approx(8.0)
    assert speed["meta"]["averaging_s"] == 600 and speed["meta"]["time_label"] == "end"
    assert series("wind_direction")["values"][0] == pytest.approx(225.0)

    # The cell's turbines at their hub height, with WRF's conversion of their curve
    members = tslist.turbines_at(case)["C0001"]
    farm = next(f for f in case.farms if f.id == members[0][0])
    model = turbine_types(case)[farm.turbines[0].type]
    z = model.hub_height_m
    low, high = (np.interp(z, [25, 75, 125], [6, s, 10]) for s in (7, 9))
    expected = len(members) * (wrf_power_w(np.array([low, high]), model).mean()) / 1e6
    assert series("power", None)["values"][0] == pytest.approx(expected, rel=1e-3)

    # One turbine of the cell: its own power from the cell's wind
    labels = tslist.turbine_labels(case)

    def at(location: str, variable: str, height: float | None = 75) -> dict:
        ref = {
            "kind": "run",
            "case_id": case_id,
            "variable": variable,
            "location": location,
            "height_m": height,
            "options": {"averaging_s": 600},
        }
        answer = client.post("/api/explore/series", json={"refs": [ref]})
        assert answer.status_code == 200, answer.text
        return answer.json()["series"][0]

    one = at(labels[members[0]], "power", None)["values"][0]
    assert one == pytest.approx(expected / len(members), rel=1e-3)

    # The analyses of the page: power per direction sector
    def ref(variable: str, height: float | None = 75) -> dict:
        return {
            "kind": "run",
            "case_id": case_id,
            "variable": variable,
            "location": "C0001",
            "height_m": height,
            "options": {"averaging_s": 600},
        }

    by_sector = client.post(
        "/api/analysis/grouped",
        json={
            "series": ref("power", None),
            "grouping": {"kind": "sector", "sectors": 8, "series": ref("wind_direction")},
        },
    ).json()
    south_west = next(g for g in by_sector["groups"] if g["centre_deg"] == 225)
    assert south_west["count"] == 6 and south_west["mean"] == pytest.approx(expected, rel=1e-3)


# ------------------------------------- files of a WRF compiled with the installer's tslist outputs


def patch_location(
    directory: Path,
    prefix: str,
    rmol: np.ndarray,
    power_kw: np.ndarray,
    qke: np.ndarray,
    kind: str = "QK",
) -> None:
    """Turns the files of write_location into those of a WRF compiled with the installer's
    patch: five more values at the end of each TS line, FMT='(...,18(f13.5,1x),f13.2)' (RMOL,
    BR, UST, PBLH, and the cell's POWER in kW), and the profile file ``kind`` (``qke``: time,
    level): QK, the QKE of the patch of 0.7.4, or TK, the TKE of the patch of 0.7.5 (NaN written
    as WRF prints its missing 1.E30, asterisks)."""
    path = directory / f"{prefix}.d02.TS"
    header, *rows = path.read_text().splitlines()
    longer = [
        f"{row}{rmol[k]:13.5f} {0.012:13.5f} {0.31:13.5f} {480.0:13.5f} {power_kw[k]:13.2f}"
        for k, row in enumerate(rows)
    ]
    path.write_text(header + "\n" + "\n".join(longer) + "\n")
    lines = [
        f"{float(row.split()[1]):13.6f} "
        + "".join("*" * 13 + " " if np.isnan(v) else f"{v:13.5f} " for v in qke[k])
        for k, row in enumerate(rows)
    ]
    (directory / f"{prefix}.d02.{kind}").write_text(header + "\n" + "\n".join(lines) + "\n")


def test_with_the_solar_diagnostics_the_message_names_them(tmp_path: Path) -> None:
    """With solar_diagnostics = 1 (process_time_series = 2) WRF writes its WRF-Solar TS line (50
    values) instead of the one the installer's patch lengthens: RMOL, BR, UST, PBLH and POWER are
    missing although the TK file is there. The message says so instead of naming the build."""
    from owstudio.core.extract.points import TimeSeriesFiles
    from owstudio.core.extract.quantities import Unavailable

    hours = np.arange(1, 41) * 15 / 3600
    write_location(tmp_path, "C0001", elevation=0.0, hours=hours)
    patch_location(tmp_path, "C0001", np.zeros(40), np.zeros(40), np.full((40, 3), 0.6), "TK")
    path = tmp_path / "C0001.d02.TS"
    header, *rows = path.read_text().splitlines()
    # The usual 14 values, then 36 solar diagnostics
    solar = [" ".join(row.split()[:19]) + " " + " ".join(["0.00000"] * 36) for row in rows]
    path.write_text(header + "\n" + "\n".join(solar) + "\n")
    files = TimeSeriesFiles(tmp_path)
    for name in ("inverse_obukhov_length", "cell_power"):
        with pytest.raises(Unavailable, match="WRF-Solar") as refused:
            files.series("C0001", 2, name, None)
        assert "compiled" not in str(refused.value), name
    # The TKE of the TK file is there
    assert files.series("C0001", 2, "tke", 75.0)[1].values.iloc[0] == pytest.approx(0.6)


def alternate_speed(directory: Path, prefix: str, hours: np.ndarray) -> None:
    """At 75 m the speed alternates 9 and 7 m/s from the south-west: mean 8."""
    header = (directory / f"{prefix}.d02.UU").read_text().splitlines()[0]
    for kind in ("UU", "VV"):
        lines = [
            f"{hour:13.6f} "
            + "".join(f"{v / np.sqrt(2):13.5f} " for v in (6, 7 if k % 2 else 9, 10))
            for k, hour in enumerate(hours)
        ]
        (directory / f"{prefix}.d02.{kind}").write_text(header + "\n" + "\n".join(lines) + "\n")


def test_a_patched_wrf_gives_stability_and_turbulence_at_the_tslist_points(tmp_path: Path) -> None:
    """1/L in the TS file and the TKE in the QK file, read at every model time step; over 10
    minutes the Obukhov length comes from the mean of 1/L, and σu and TI from the mean TKE and
    the mean speed (not from the means of L or of TI)."""
    from helpers import make_client

    from owstudio.core.case.workspace import Workspace
    from owstudio.core.extract.points import TimeSeriesFiles
    from owstudio.core.extract.quantities import Unavailable
    from owstudio.core.postproc.tslist_reader import TS_COLUMNS, TS_PATCHED, read_surface
    from owstudio.core.storage import Storage

    case = Case.from_yaml(REFERENCE)
    case.time_series = TimeSeries(turbines="cells")
    case_id = Workspace(tmp_path / "data").create(case)
    run = Storage(tmp_path / "data").create_run(case_id)
    folder = run.root / "outputs" / "main" / "tslist"
    folder.mkdir(parents=True)
    hours = np.arange(1, 241) * 15 / 3600  # one hour of 15 s steps: six 10-minute intervals
    step = np.arange(240)
    write_location(folder, "C0001", elevation=0.0, hours=hours)
    files = TimeSeriesFiles(folder)

    # A WRF without the patch: the usual 14 values, no QK file
    assert not files.patched()
    with pytest.raises(Unavailable, match="no RMOL in these tslist files"):
        files.series("C0001", 2, "inverse_obukhov_length", None)
    with pytest.raises(Unavailable, match="TK file"):
        files.series("C0001", 2, "turbulence_intensity", 75.0)

    # 1/L of each 10-minute interval: 0.001 and 0.007 alternating (mean 0.004), then constant
    inverse = np.select(
        [step < 40, step < 80, step < 120, step < 160, step < 200],
        [np.where(step % 2, 0.007, 0.001), 0.03, -0.004, -0.015, 0.0005],
        0.0,
    )
    # QKE at 75 m alternates 3 and 1 m²/s² (TKE 1.5 and 0.5, mean 1) with the speed 9 and 7 m/s
    qke = np.column_stack([np.full(240, 0.8), np.where(step % 2, 1.0, 3.0), np.full(240, 0.4)])
    patch_location(folder, "C0001", inverse, np.full(240, 1234.56), qke)
    alternate_speed(folder, "C0001", hours)
    assert files.patched()
    _, surface = read_surface(folder / "C0001.d02.TS")
    assert list(surface.columns) == (TS_COLUMNS + TS_PATCHED)[5:]
    assert surface["power"].iloc[0] == 1234.56 and surface["pblh"].iloc[0] == 480.0

    # Every model time step
    _, written = files.series("C0001", 2, "inverse_obukhov_length", None)
    assert written.unit == "m-1" and written.values.to_numpy() == pytest.approx(inverse)
    # A surface quantity: a height given with it is ignored
    assert files.series("C0001", 2, "inverse_obukhov_length", 75.0)[1].values.equals(written.values)
    _, length = files.series("C0001", 2, "obukhov_length", None)
    assert length.values.iloc[0] == pytest.approx(1000.0) and np.isnan(length.values.iloc[-1])
    _, cell = files.series("C0001", 2, "cell_power", None)
    assert cell.unit == "W" and cell.values.iloc[0] == pytest.approx(1234560.0)
    _, tke = files.series("C0001", 2, "tke", 75.0)
    assert tke.values.to_numpy()[:2] == pytest.approx([1.5, 0.5]) and "QKE / 2" in tke.method
    assert files.series("C0001", 2, "tke", 50.0)[1].values.iloc[0] == pytest.approx(0.95)
    _, sigma = files.series("C0001", 2, "wind_speed_std", 75.0)
    assert sigma.values.to_numpy()[:2] == pytest.approx(np.sqrt(np.array([1.5, 0.5]) / 0.945))
    _, ti = files.series("C0001", 2, "turbulence_intensity", 75.0)
    each = np.sqrt(np.array([1.5, 0.5]) / 0.945) / np.array([9.0, 7.0])
    assert ti.values.to_numpy()[:2] == pytest.approx(each) and ti.unit == "1"
    assert any("0.945" in flag for flag in ti.flags)
    # Above the written levels: no value, and it is said
    high = files.series("C0001", 2, "tke", 200.0)[1]
    assert np.isnan(high.values.to_numpy()).all() and "outside the written levels" in high.flags[0]

    # As the analyses read them: 10-minute values
    case.to_yaml(run.root / "outputs" / "main" / "case.yaml")
    client = make_client(tmp_path)

    def ref(variable: str, height: float | None = 75, seconds: int = 600) -> dict:
        return {
            "kind": "run",
            "case_id": case_id,
            "variable": variable,
            "location": "C0001",
            "height_m": height,
            "options": {"averaging_s": seconds},
        }

    def series(variable: str, height: float | None = 75, seconds: int = 600) -> dict:
        answer = client.post("/api/explore/series", json={"refs": [ref(variable, height, seconds)]})
        assert answer.status_code == 200, answer.text
        return answer.json()["series"][0]

    ten = series("turbulence_intensity")
    assert ten["meta"]["source"] == "tslist" and ten["meta"]["averaging_s"] == 600
    assert len(ten["values"]) == 6
    # √(mean TKE / 0.945) / mean U, not the mean of the TI of each step
    assert ten["values"][0] == pytest.approx(np.sqrt(1.0 / 0.945) / 8.0)
    assert abs(ten["values"][0] - each.mean()) > 0.005
    assert "from the means of the TKE and of U" in ten["meta"]["method"]
    assert series("wind_speed_std")["values"][0] == pytest.approx(np.sqrt(1.0 / 0.945))
    assert series("tke")["values"][0] == pytest.approx(1.0)
    assert len(series("turbulence_intensity", seconds=0)["values"]) == 240
    lengths = series("obukhov_length", None)
    assert lengths["values"][:5] == pytest.approx([250.0, 1 / 0.03, -250.0, -1 / 0.015, 2000.0])
    assert lengths["values"][5] is None and "from the mean of 1/L" in lengths["meta"]["method"]

    # The Stability tab: classes of the 10-minute values (the height it sends is ignored)
    answer = client.post(
        "/api/analysis/stability",
        json={"series": ref("obukhov_length", 105.0), "scheme": "gryning2007"},
    )
    assert answer.status_code == 200, answer.text
    result = answer.json()
    assert result["inputs"][0]["source"] == "tslist" and result["inputs"][0]["averaging_s"] == 600
    counts = {row["key"]: row["count"] for row in result["classes"]}
    assert counts == {
        "very_unstable": 1,
        "unstable": 0,
        "near_neutral_unstable": 1,
        "neutral": 1,
        "near_neutral_stable": 1,  # 0.001 and 0.007 alternating: L = 1 / 0.004 = 250 m
        "stable": 0,
        "very_stable": 1,
    }
    assert result["counts"]["valid"] == 5 and result["counts"]["values"] == 6

    # What the run can give, as the Explorer lists it
    listed = client.get(f"/api/cases/{case_id}/runs/{run.id}/diagnostics").json()["diagnostics"]
    status = {d["key"]: d["status"] for d in listed}
    assert status["turbulence_intensity"] == status["obukhov_length"] == "derivable"


def test_qke_of_another_boundary_layer_scheme_gives_no_turbulence(tmp_path: Path) -> None:
    """QKE is computed by MYNN only: with another scheme WRF writes zeros, which are not a TKE."""
    from owstudio.core.extract.points import TimeSeriesFiles
    from owstudio.core.extract.quantities import Unavailable

    hours = np.arange(1, 41) * 15 / 3600
    write_location(tmp_path, "C0001", elevation=0.0, hours=hours)
    patch_location(tmp_path, "C0001", np.zeros(40), np.zeros(40), np.zeros((40, 3)))
    with pytest.raises(Unavailable, match="MYNN"):
        TimeSeriesFiles(tmp_path).series("C0001", 2, "turbulence_intensity", 75.0)
    # 1/L of the surface layer scheme is there whatever the boundary layer scheme
    values = TimeSeriesFiles(tmp_path).series("C0001", 2, "inverse_obukhov_length", None)[1].values
    assert len(values) == 40 and (values == 0).all()


def test_tke_profile_of_the_patch_of_075(tmp_path: Path) -> None:
    """The TK file holds the TKE itself (QKE / 2 with MYNN, TKE_PBL with MYJ, QNSE and BouLac):
    read as it is; with a scheme that has none, WRF writes its missing value, and the TKE and
    the turbulence intensity are unavailable, never zero."""
    from owstudio.core.extract.points import TimeSeriesFiles
    from owstudio.core.extract.quantities import Unavailable

    hours = np.arange(1, 41) * 15 / 3600
    write_location(tmp_path, "C0001", elevation=0.0, hours=hours)
    patch_location(tmp_path, "C0001", np.zeros(40), np.zeros(40), np.full((40, 3), 0.8), "TK")
    files = TimeSeriesFiles(tmp_path)
    assert files.patched()
    _, tke = files.series("C0001", 2, "tke", 75.0)
    assert tke.values.to_numpy() == pytest.approx(np.full(40, 0.8)) and "TK profile" in tke.method
    other = tmp_path / "other"
    other.mkdir()
    write_location(other, "C0001", elevation=0.0, hours=hours)
    patch_location(other, "C0001", np.zeros(40), np.zeros(40), np.full((40, 3), np.nan), "TK")
    for name in ("tke", "turbulence_intensity"):
        with pytest.raises(Unavailable, match="computes none"):
            TimeSeriesFiles(other).series("C0001", 2, name, 75.0)
