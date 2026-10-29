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
    assert any("1 location(s) outside every domain" in m for m in messages)


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
    from owstudio.core.postproc.tslist_reader import _numbers, interpolate_rows

    header = HEADER_FORMAT.format(
        name="Cell", domain=2, ts_id=1, prefix="C0009", lat=55.0, lon=7.0,
        i=1, j=1, glat=55.0, glon=7.0, elev=0.0, start="2025-10-01_00:00:00",
    )  # fmt: skip
    path = tmp_path / "C0009.d02.UU"
    rows = ["     0.004167      1.00000      2.00000      3.00000 "] * 3
    rows[1] = "     0.008333      1.00000 *************      3.00000 "
    path.write_text(header + "\n" + "\n".join(rows) + "\n     0.0125    1.0\n")
    _, values = _numbers(path)
    # The cut last line is left out; the asterisks are a missing value
    assert values.shape == (3, 4) and np.isnan(values[1, 2]) and values[2, 3] == 3.0
    # The file is read again when it changes
    path.write_text(header + "\n" + rows[0] + "\n")
    assert _numbers(path)[1].shape == (1, 4)

    z = np.array([[10.0, 50.0, 100.0], [10.0, 50.0, 100.0], [20.0, np.nan, 100.0]])
    v = np.array([[1.0, 5.0, 10.0], [1.0, 5.0, 10.0], [2.0, 9.0, 10.0]])
    assert interpolate_rows(z, v, 75.0) == pytest.approx([7.5, 7.5, 2.0 + 8.0 * 55 / 80])
    assert np.isnan(interpolate_rows(z, v, 5.0)).all() and np.isnan(interpolate_rows(z, v, 150.0)).all()
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

    csv = client.get(f"/api/cases/{case_id}/results/tslist/C0001/csv", params={"domain": 2}).text
    lines = csv.splitlines()
    # The conventions first, then the table stamped at the end of each interval
    assert lines[0].startswith("# WRF time series C0001") and "]t - 10 min, t]" in lines[1]
    assert lines[3].startswith("time_utc_end,wind_speed_10m")
    # Chosen columns over a chosen period: ]00:10, 00:40]
    chosen = client.get(
        f"/api/cases/{case_id}/results/tslist/C0001/csv",
        params={
            "domain": 2,
            "height": 75,
            "columns": ["wind_speed_hub", "wind_direction_hub"],
            "start": "2025-10-01T00:10:00Z",
            "end": "2025-10-01T00:40:00Z",
        },
    ).text.splitlines()
    rows = [line for line in chosen if not line.startswith("#")]
    assert rows[0] == "time_utc_end,wind_speed_hub,wind_direction_hub"
    assert [row.split(",")[0] for row in rows[1:]] == [
        "2025-10-01 00:20:00",
        "2025-10-01 00:30:00",
        "2025-10-01 00:40:00",
    ]
    assert any("]2025-10-01 00:10:00, 2025-10-01 00:40:00]" in line for line in chosen)
    unknown = client.get(
        f"/api/cases/{case_id}/results/tslist/C0001/csv", params={"domain": 2, "columns": "nope"}
    )
    assert unknown.status_code == 422
    assert (
        client.get(f"/api/cases/{case_id}/results/tslist/NOPE", params={"domain": 2}).status_code
        == 404
    )


def test_run_series_give_ten_minute_means_and_power(tmp_path: Path) -> None:
    """Analyses read the tslist locations as 10-minute means: speed, direction from the mean
    components, and the power of the cell's turbines."""
    from helpers import make_client

    from owstudio.core.case.workspace import Workspace
    from owstudio.core.energy.curves import turbine_types, wrf_power_w
    from owstudio.core.storage import Storage

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
