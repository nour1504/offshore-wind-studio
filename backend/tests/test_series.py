"""The common series format: index, quality flags, units, statistics and resolvers."""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from owstudio.core import series
from owstudio.core.series import Series, SeriesMeta, relabel
from owstudio.core.series.units import UnitError, convert


def to_components(speed: np.ndarray, direction: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Earth-relative u (eastward) and v (northward) of a wind blowing from ``direction``."""
    rad = np.deg2rad(np.asarray(direction, dtype=float))
    speed = np.asarray(speed, dtype=float)
    return -speed * np.sin(rad), -speed * np.cos(rad)


def meta(**changes: Any) -> SeriesMeta:
    base = {
        "variable": "wind_speed",
        "unit": "m s-1",
        "source": "observation",
        "dataset": "mast",
        "location": "M1",
        "height_m": 100.0,
        "height_ref": "agl",
    }
    return SeriesMeta.model_validate({**base, **changes})


def test_series_index_becomes_sorted_unique_utc() -> None:
    times = pd.to_datetime(["2025-10-01 01:00", "2025-10-01 00:00", "2025-10-01 00:00"])
    s = Series(meta(), pd.Series([2.0, 1.0, 5.0], index=times))
    assert str(s.times.tz) == "UTC" and list(s.values) == [1.0, 2.0]
    paris = pd.Series(
        [1.0], index=pd.DatetimeIndex(["2025-10-01 02:00"]).tz_localize("Europe/Paris")
    )
    assert Series(meta(), paris).times[0] == pd.Timestamp("2025-10-01 00:00", tz="UTC")


def test_quality_flags_mask_values() -> None:
    times = pd.date_range("2025-10-01", periods=3, freq="10min", tz="UTC")
    s = Series(meta(), pd.Series([1.0, 2.0, 3.0], index=times), pd.Series([0, 1, 2], index=times))
    assert s.good().isna().tolist() == [False, True, True]
    assert s.good(accept_suspect=True).isna().tolist() == [False, False, True]


def test_relabel_moves_period_stamps() -> None:
    times = pd.date_range("2025-10-01 00:10", periods=2, freq="10min", tz="UTC")
    end = Series(meta(averaging_s=600, time_label="end"), pd.Series([1.0, 2.0], index=times))
    start = relabel(end, "start")
    assert (
        start.times[0] == pd.Timestamp("2025-10-01 00:00", tz="UTC")
        and start.meta.time_label == "start"
    )
    assert relabel(start, "centre").times[0] == pd.Timestamp("2025-10-01 00:05", tz="UTC")


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    times = pd.date_range("2025-10-01", periods=4, freq="h", tz="UTC")
    a = Series(
        meta(),
        pd.Series([1.0, np.nan, 3.0, 4.0], index=times),
        pd.Series([0, 9, 0, 1], index=times),
    )
    b = Series(
        meta(
            variable="sst",
            unit="K",
            height_m=None,
            height_ref="surface",
            source="wrfout",
            dataset="run1",
        ),
        pd.Series([285.0] * 4, index=times),
    )
    series.save([a, b], tmp_path / "set")
    loaded = series.load(tmp_path / "set")
    assert [s.meta.key for s in loaded] == [a.meta.key, b.meta.key]
    pd.testing.assert_series_equal(loaded[0].values, a.values, check_names=False, check_freq=False)
    assert loaded[0].quality is not None and loaded[0].quality.tolist() == [0, 9, 0, 1]
    assert loaded[1].quality is None


def test_unit_conversions() -> None:
    assert convert(np.array([10.0]), "knots", "m/s")[0] == pytest.approx(5.1444, rel=1e-4)
    assert convert(np.array([15.0]), "°C", "K")[0] == pytest.approx(288.15)
    assert convert(np.array([1013.25]), "hPa", "Pa")[0] == pytest.approx(101325)
    assert convert(np.array([50.0]), "%", "1")[0] == pytest.approx(0.5)
    with pytest.raises(UnitError):
        convert(np.array([1.0]), "m/s", "K")


def test_circular_statistics() -> None:
    from owstudio.core.series import circular

    assert circular.mean(np.array([350.0, 10.0])) == pytest.approx(0.0, abs=1e-9)
    assert circular.difference(10.0, 350.0) == pytest.approx(20.0)
    assert circular.difference(350.0, 10.0) == pytest.approx(-20.0)
    assert circular.std_yamartino(np.array([90.0, 90.0, 90.0])) == pytest.approx(0.0, abs=1e-6)
    # Westerly wind: blows from 270, towards the east (u > 0)
    u, v = to_components(np.array([5.0]), np.array([270.0]))
    assert u[0] == pytest.approx(5.0) and v[0] == pytest.approx(0.0, abs=1e-12)
    assert circular.from_components(u, v)[0] == pytest.approx(270.0)
    assert circular.from_components(np.array([0.0]), np.array([-3.0]))[0] == pytest.approx(
        0.0
    )  # northerly
    assert circular.sector(np.array([0.0, 14.9, 15.1, 359.0, np.nan]), 12).tolist() == [
        0,
        0,
        1,
        0,
        -1,
    ]


def test_series_resolvers_are_registered_by_kind() -> None:
    from owstudio.core.series import sources

    ref = sources.SeriesRef(kind="test-kind", variable="wind_speed", dataset="d")
    with pytest.raises(sources.SeriesNotFound):
        sources.resolve(None, ref)  # type: ignore[arg-type]
    times = pd.date_range("2025-10-01", periods=2, freq="h", tz="UTC")
    sources.register(
        "test-kind",
        lambda _context, r: Series(meta(dataset=r.dataset), pd.Series([1.0, 2.0], index=times)),
    )
    assert sources.resolve(None, ref).meta.dataset == "d"  # type: ignore[arg-type]
