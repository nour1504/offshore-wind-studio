"""Observation files: detection, suggestions, conversion with time zones and daylight saving,
quality codes, units, platform heights, datasets, alignment and comparison with a simulation."""

import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from helpers import make_client

from owstudio.core.observations import align as aligning
from owstudio.core.observations.convert import ConversionError, convert
from owstudio.core.observations.mapping import (
    ColumnSpec,
    FileOptions,
    Mapping,
    QualitySpec,
    Station,
    TimeSpec,
    readiness,
)
from owstudio.core.observations.reader import detect, read_delimited, suggest
from owstudio.core.series import (
    QUALITY_BAD,
    QUALITY_GOOD,
    QUALITY_SUSPECT,
    Series,
    SeriesMeta,
    sources,
)

# A logger in local Berlin time, 10-min averages stamped at the end, around the switch to summer
# time (2025-03-30 02:00 local -> 03:00), with a units line, decimal commas and semicolons
CSV = """Station FINO-like test file
Date;Time;WS_100m;WD_100m;T_30;QC_WS
;;[kn];[deg];[°C];
30.03.2025;01:50;19,4;270;8,0;0
30.03.2025;03:00;-999;275;8,1;0
30.03.2025;03:10;20,0;280;8,2;1
30.03.2025;03:20;21,0;285;8,3;2
"""


@pytest.fixture
def logger_file(tmp_path: Path) -> Path:
    path = tmp_path / "mast.csv"
    path.write_text(CSV, encoding="utf-8")
    return path


def mapping(**time: Any) -> Mapping:
    return Mapping(
        time=TimeSpec(
            **{
                "columns": ["Date", "Time"],
                "format": "%d.%m.%Y %H:%M",
                "timezone": "Europe/Berlin",
                "label": "end",
                "averaging_s": 600,
                **time,
            }
        ),
        station=Station(
            id="mast",
            name="Test mast",
            lat=54.0,
            lon=6.6,
            instrument="platform",
            height_reference="platform",
            platform_elevation_m=20.0,
        ),
        file={"missing": ["-999"]},  # type: ignore[arg-type]
        columns=[
            ColumnSpec(
                column="WS_100m",
                variable="wind_speed",
                height_m=100,
                unit="kn",
                quality=QualitySpec(column="QC_WS", good=["0"], suspect=["1"], bad=["2"]),
            ),
            ColumnSpec(
                column="WD_100m",
                variable="wind_direction",
                height_m=100,
                unit="deg",
                direction="from",
            ),
            ColumnSpec(column="T_30", variable="temperature", height_m=30, unit="°C"),
        ],
    )


def test_layout_is_detected(logger_file: Path) -> None:
    layout = detect(logger_file)
    assert layout.delimiter == ";" and layout.decimal == "," and layout.header and layout.units_row
    assert layout.columns == ["Date", "Time", "WS_100m", "WD_100m", "T_30", "QC_WS"]
    assert layout.units["WS_100m"] == "[kn]"
    frame = read_delimited(logger_file, layout)
    assert len(frame) == 4 and frame["WS_100m"][0] == "19,4"


def test_suggestions_and_ambiguity_flags(logger_file: Path) -> None:
    layout = detect(logger_file)
    frame = read_delimited(logger_file, layout)
    time_columns, suggestions, flags = suggest(layout.columns, layout.units, frame)
    assert time_columns == ["Date", "Time"]
    by_column = {s["column"]: s for s in suggestions}
    assert (
        by_column["WS_100m"]["variable"] == "wind_speed" and by_column["WS_100m"]["height_m"] == 100
    )
    assert by_column["WD_100m"]["variable"] == "wind_direction"
    assert by_column["T_30"]["variable"] == "temperature" and by_column["T_30"]["height_m"] == 30
    assert any(f.code == "direction_convention" for f in flags)


def test_mapping_must_say_time_zone_and_label() -> None:
    incomplete = Mapping(
        time=TimeSpec(columns=["Date"]),
        columns=[ColumnSpec(column="WS", variable="wind_speed", unit="m/s")],
    )
    codes = {f.code for f in readiness(incomplete)}
    assert {"no_timezone", "time_label_unknown", "height_not_found"} <= codes


def test_conversion_to_the_common_format(logger_file: Path) -> None:
    layout = detect(logger_file)
    frame = read_delimited(logger_file, layout)
    found, _flags = convert(frame, mapping(), "fino-test", layout.decimal, layout.units)
    speed, direction, temperature = found
    # 01:50 CET = 00:50 UTC; 03:00 CEST = 01:00 UTC: one hour later in local time is 10 min in UTC
    assert list(speed.times.strftime("%H:%M")) == ["00:50", "01:00", "01:10", "01:20"]
    assert speed.values.iloc[0] == pytest.approx(19.4 * 1852 / 3600)  # knots to m/s
    assert np.isnan(speed.values.iloc[1])  # -999 is missing
    assert speed.quality is not None and list(speed.quality) == [
        QUALITY_GOOD,
        9,
        QUALITY_SUSPECT,
        QUALITY_BAD,
    ]
    assert temperature.values.iloc[0] == pytest.approx(281.15) and temperature.meta.unit == "K"
    # Heights above the platform deck become heights above mean sea level
    assert speed.meta.height_m == 120 and speed.meta.height_ref == "asl"
    assert (
        speed.meta.time_label == "end"
        and speed.meta.averaging_s == 600
        and speed.meta.original_timezone == "Europe/Berlin"
    )
    assert direction.meta.variable == "wind_direction" and direction.values.iloc[0] == 270


def test_ambiguous_local_times_are_refused_unless_told(tmp_path: Path) -> None:
    # Switch back to winter time: 02:30 local happens twice on 2025-10-26
    path = tmp_path / "autumn.csv"
    path.write_text(
        "Date;Time;WS_100m\n26.10.2025;02:30;5,0\n26.10.2025;02:30;6,0\n", encoding="utf-8"
    )
    layout = detect(path)
    frame = read_delimited(path, layout)
    simple = Mapping(
        time=TimeSpec(
            columns=["Date", "Time"],
            format="%d.%m.%Y %H:%M",
            timezone="Europe/Berlin",
            label="instant",
        ),
        columns=[ColumnSpec(column="WS_100m", variable="wind_speed", height_m=100, unit="m/s")],
    )
    with pytest.raises(ConversionError, match="daylight saving"):
        convert(frame, simple, "x", layout.decimal)
    inferred = simple.model_copy(
        update={"time": simple.time.model_copy(update={"ambiguous": "infer"})}
    )
    found, _ = convert(frame, inferred, "x", layout.decimal)
    assert list(found[0].times.strftime("%H:%M")) == ["00:30", "01:30"]


def test_fixed_offset_and_direction_to_convention(tmp_path: Path) -> None:
    path = tmp_path / "buoy.csv"
    path.write_text("time,dir\n2025-06-01T12:00,90\n", encoding="utf-8")
    layout = detect(path)
    frame = read_delimited(path, layout)
    buoy = Mapping(
        time=TimeSpec(columns=["time"], format="ISO8601", timezone="UTC+02:00", label="instant"),
        columns=[
            ColumnSpec(
                column="dir",
                variable="wind_direction",
                height_m=4,
                unit="deg",
                direction="to",
                direction_offset_deg=5,
            )
        ],
    )
    found, _ = convert(frame, buoy, "buoy", layout.decimal)
    assert found[0].times[0] == pd.Timestamp("2025-06-01 10:00", tz="UTC")
    assert found[0].values.iloc[0] == pytest.approx(275.0)  # towards 90° is from 270°, plus 5°


# --------------------------------------------------------------- alignment


def hourly_sim(values: list[float]) -> Series:
    times = pd.date_range("2025-03-30 00:00", periods=len(values), freq="10min", tz="UTC")
    meta = SeriesMeta(
        variable="wind_speed",
        unit="m s-1",
        source="wrfout",
        dataset="case/run/main",
        location="mast",
        height_m=120,
        height_ref="asl",
        frequency_s=600,
        method="test; linear interpolation in height",
    )
    return Series(meta, pd.Series(values, index=times))


def test_lines_between_the_header_and_the_values_are_left_out_when_said(tmp_path: Path) -> None:
    """Regression: the option "lines after the header" was accepted and did nothing (the line
    before the values was taken as the header); a units line said, not detected, was taken as
    the header too, and the first values were lost."""
    path = tmp_path / "logger.dat"
    path.write_text(
        "TIMESTAMP,WS_100,WD_100\nTS,a,b\nAvg,Avg,Smp\n! a remark\n"
        "2025-03-30 00:10,8.1,270\n2025-03-30 00:20,8.4,272\n",
        encoding="utf-8",
    )
    options = FileOptions(skip_after_header=1, units_row=True, comment="!")
    layout = detect(path, options)
    assert layout.columns == ["TIMESTAMP", "WS_100", "WD_100"]
    assert layout.units == {"TIMESTAMP": "TS", "WS_100": "a", "WD_100": "b"}
    frame = read_delimited(path, layout)
    assert list(frame["WS_100"]) == ["8.1", "8.4"]
    # Nothing said: the file is read as before
    plain = tmp_path / "plain.csv"
    plain.write_text("time,ws\n# a remark\n2025-03-30 00:10,8.1\n", encoding="utf-8")
    assert list(read_delimited(plain, detect(plain))["ws"]) == ["8.1"]


def test_distortion_sectors_read_the_direction_as_it_is_converted() -> None:
    """Regression: the sectors were tested on the direction as written in the file, without its
    convention ("blowing to"), its offset or its own missing codes."""
    from owstudio.core.observations.mapping import DistortionSector

    frame = pd.DataFrame(
        {
            "Date": ["30.03.2025"] * 3,
            "Time": ["03:10", "03:20", "03:30"],
            "WS": ["8", "9", "10"],
            # Blowing to 180: from 0, in the first sector; to 90: from 270, in none; -280: missing
            "WD": ["180", "90", "-280"],
        }
    )
    chosen = mapping()
    chosen.station.distortion_sectors = [
        DistortionSector(start_deg=350, end_deg=10),
        DistortionSector(start_deg=80, end_deg=100),
    ]
    chosen.columns = [
        ColumnSpec(column="WS", variable="wind_speed", height_m=100, unit="m/s"),
        ColumnSpec(
            column="WD",
            variable="wind_direction",
            height_m=100,
            unit="deg",
            direction="to",
            missing=["-280"],
        ),
    ]
    found, _ = convert(frame, chosen, "sectors")
    speed = next(s for s in found if s.meta.variable == "wind_speed")
    assert speed.quality is not None
    assert list(speed.quality) == [QUALITY_SUSPECT, QUALITY_GOOD, QUALITY_GOOD]


def test_the_height_interpolation_is_said_in_french_too() -> None:
    """Regression: the remark was looked for in the English words of the method only, so a
    French window never had it."""
    from owstudio.core import i18n

    simulated = hourly_sim([10.0] * 12)
    assert any("interpolated in height" in c for c in aligning.caveats(simulated, simulated, None))
    with i18n.using("fr"):
        french = hourly_sim([10.0] * 12)
        french.meta.method = "essai ; interpolation linéaire en hauteur à 120 m"
        assert any("interpolée en hauteur" in c for c in aligning.caveats(french, french, None))


def test_alignment_averages_both_series_on_common_periods(logger_file: Path) -> None:
    layout = detect(logger_file)
    found, _ = convert(
        read_delimited(logger_file, layout), mapping(), "fino-test", layout.decimal, layout.units
    )
    observed = found[0]
    simulated = hourly_sim([10.0] * 12)
    obs, sim, notes = aligning.align(observed, simulated, 3600.0, min_availability=0.1)
    # The measured 00:50 value (period 00:40-00:50) falls in hour 00; only good values count
    assert obs.times[0] == pd.Timestamp("2025-03-30 00:00", tz="UTC")
    assert obs.values.iloc[0] == pytest.approx(19.4 * 1852 / 3600)
    assert sim.values.iloc[0] == pytest.approx(10.0) and sim.meta.time_label == "start"
    assert any("instantaneous" in n for n in notes)
    caveats = aligning.caveats(observed, simulated, 3000.0)
    assert any("grid cell of 3 km" in c for c in caveats) and any("disturb" in c for c in caveats)


# --------------------------------------------------------------------- API


def test_import_and_compare_through_the_api(tmp_path: Path, logger_file: Path) -> None:
    client = make_client(tmp_path)
    preview = client.post("/api/observations/preview", json={"path": str(logger_file)}).json()
    assert preview["time_columns"] == ["Date", "Time"] and len(preview["rows"]) == 4
    chosen = mapping().model_dump(mode="json")
    check = client.post(
        "/api/observations/check", json={"path": str(logger_file), "mapping": chosen}
    ).json()
    assert check["ready"] and len(check["series"]) == 3
    assert client.put("/api/observations/mappings/FINO logger", json=chosen).status_code == 200
    assert client.get("/api/observations/mappings").json()[0]["name"] == "FINO logger"
    job = client.post(
        "/api/observations/import",
        json={
            "path": str(logger_file),
            "mapping": chosen,
            "dataset_id": "fino-test",
            "name": "FINO test",
        },
    ).json()["job"]
    for _ in range(100):
        status = client.get(f"/api/jobs/{job}").json()
        if status["state"] != "running":
            break
        time.sleep(0.05)
    assert status["state"] == "succeeded", status
    datasets = client.get("/api/observations/datasets").json()
    assert datasets[0]["id"] == "fino-test" and datasets[0]["source"]["name"] == "mast.csv"
    assert (tmp_path / "data" / "observations" / "fino-test" / "source" / "mast.csv").exists()
    # A simulated series served by a test resolver, compared on 10-min periods
    sources.register(
        "sim-test",
        lambda _context, _ref: hourly_sim([10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0, 10.0]),
    )
    observation = {
        "kind": "observation",
        "dataset": "fino-test",
        "variable": "wind_speed",
        "height_m": 120,
        "height_ref": "asl",
    }
    result = client.post(
        "/api/observations/compare",
        json={
            "observation": observation,
            "simulation": {"kind": "sim-test", "variable": "wind_speed"},
            "period_s": 600,
            "min_availability": 1.0,
        },
    ).json()
    assert (
        result["overall"]["count"] == 1
    )  # only the good 00:50 value (the others are missing or not good)
    assert result["overall"]["bias"] == pytest.approx(10.0 - 19.4 * 1852 / 3600)
    assert result["alignment"] and result["caveats"]
    assert client.delete("/api/observations/datasets/fino-test").status_code == 204
    assert logger_file.exists()  # the original file is never touched


def test_year_first_dates_are_not_ambiguous(tmp_path: Path) -> None:
    # 2025-10-01 read day-first by pandas would be 10 January: ISO dates are always year-month-day
    path = tmp_path / "iso.csv"
    path.write_text(
        "Date (UTC),WS_100m\n2025-10-01T00:00,9.0\n2025-10-01T01:00,9.5\n", encoding="utf-8"
    )
    layout = detect(path)
    frame = read_delimited(path, layout)
    spec = Mapping(
        time=TimeSpec(columns=["Date (UTC)"], format="", timezone="UTC", label="instant"),
        columns=[ColumnSpec(column="WS_100m", variable="wind_speed", height_m=100, unit="m/s")],
    )
    found, _ = convert(frame, spec, "x", layout.decimal)
    assert found[0].times[0] == pd.Timestamp("2025-10-01 00:00", tz="UTC")
    # Day and month both possible: still refused until the format is given
    path.write_text("Date,WS_100m\n01/10/2025 00:00,9.0\n", encoding="utf-8")
    frame = read_delimited(path, detect(path))
    with pytest.raises(ConversionError, match="day-first or month-first"):
        convert(
            frame,
            spec.model_copy(update={"time": spec.time.model_copy(update={"columns": ["Date"]})}),
            "x",
            layout.decimal,
        )


def test_a_mast_in_the_cell_of_a_tslist_point_is_compared_with_its_series(tmp_path: Path) -> None:
    """A station in the grid cell of a tslist point: the model there is that point's series, every
    time step (WRF writes the column of the cell), so 10-min means can be compared; elsewhere the
    history files at the station, as before."""
    from helpers import REFERENCE
    from test_extract import wrfout
    from test_tslist import HEADER_FORMAT

    from owstudio.core.case.model import Case, TimeSeries, TimeSeriesPoint
    from owstudio.core.case.workspace import Workspace
    from owstudio.core.storage import Storage

    case = Case.from_yaml(REFERENCE)
    case.time_series = TimeSeries(
        turbines="none", points=[TimeSeriesPoint(name="Mast", prefix="MAST", lat=54.2, lon=7.2)]
    )
    case_id = Workspace(tmp_path / "data").create(case)
    main = Storage(tmp_path / "data").create_run(case_id).root / "outputs" / "main"
    (main / "tslist").mkdir(parents=True)
    case.to_yaml(main / "case.yaml")
    # History every hour on a 6 x 6 grid (test_extract.wrfout): 5, 7, 9 m/s at 25, 75, 125 m
    wrfout(["2025-10-01_00:00:00", "2025-10-01_01:00:00"]).to_netcdf(
        main / "wrfout_d02_2025-10-01_00-00-00"
    )
    # The point's cell, mass point (3, 3) counted from 1 (54.2 N, 7.2 E): 6, 8, 10 m/s every 15 s
    header = HEADER_FORMAT.format(
        name="Mast", domain=2, ts_id=1, prefix="MAST", lat=54.2, lon=7.2, i=3, j=3,
        glat=54.2, glon=7.2, elev=0.0, start="2025-10-01_00:00:00",
    )  # fmt: skip
    hours = np.arange(1, 241) * 15 / 3600
    zero = " ".join(["0.00000"] * 14)
    rows = [f"{2:2d}{h:13.6f}{1:5d}{3:5d}{3:5d} {zero}" for h in hours]
    (main / "tslist" / "MAST.d02.TS").write_text(header + "\n" + "\n".join(rows) + "\n")
    for kind, levels in (("PH", (25, 75, 125)), ("UU", (6, 8, 10)), ("VV", (0, 0, 0))):
        lines = [f"{h:13.6f} " + "".join(f"{v:13.5f} " for v in levels) for h in hours]
        (main / "tslist" / f"MAST.d02.{kind}").write_text(header + "\n" + "\n".join(lines) + "\n")
    client = make_client(tmp_path)

    def mast(name: str, lat: float, lon: float) -> None:
        path = tmp_path / f"{name}.csv"
        times = pd.date_range("2025-10-01 00:10", periods=6, freq="10min")
        path.write_text(
            "Date,WS\n" + "".join(f"{t:%Y-%m-%dT%H:%M},10.0\n" for t in times), encoding="utf-8"
        )
        mapping = Mapping(
            time=TimeSpec(columns=["Date"], timezone="UTC", label="end", averaging_s=600),
            station=Station(id=name, name=name, lat=lat, lon=lon),
            columns=[ColumnSpec(column="WS", variable="wind_speed", height_m=100, unit="m/s")],
        ).model_dump(mode="json")
        job = client.post(
            "/api/observations/import",
            json={"path": str(path), "mapping": mapping, "dataset_id": name, "name": name},
        ).json()["job"]
        while client.get(f"/api/jobs/{job}").json()["state"] == "running":
            time.sleep(0.05)

    def compare(name: str, period_s: int) -> Any:
        return client.post(
            "/api/observations/compare",
            json={
                "observation": {"kind": "observation", "dataset": name, "variable": "wind_speed", "height_m": 100},
                "simulation": {"kind": "run", "case_id": case_id, "variable": "wind_speed"},
                "period_s": period_s,
            },
        )  # fmt: skip

    mast("in-cell", 54.21, 7.19)
    answer = compare("in-cell", 600)
    assert answer.status_code == 200, answer.text
    result = answer.json()
    # 9 m/s at 100 m in the point's series (8 m/s in the history files at the station)
    assert result["overall"]["count"] == 6 and result["overall"]["bias"] == pytest.approx(-1.0)
    assert any(i["source"] == "tslist" and i["location"] == "MAST" for i in result["inputs"])
    mast("elsewhere", 54.41, 7.41)
    answer = compare("elsewhere", 3600)
    assert answer.status_code == 200, answer.text
    assert answer.json()["overall"]["bias"] == pytest.approx(-2.0)
