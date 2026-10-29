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
