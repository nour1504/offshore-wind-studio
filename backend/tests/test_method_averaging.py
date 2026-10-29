"""10-minute means of model time series (core/method/averaging.py)."""

import numpy as np
import pandas as pd
import pytest

from owstudio.core.method.averaging import weighted_means

D = pd.Timestamp("2024-02-27 00:00")


def series(step_s: float, hours: float, values) -> pd.DataFrame:  # type: ignore[no-untyped-def]
    """Values at D + n x step, n = 1.. (WRF writes after each step)."""
    n = np.arange(1, int(hours * 3600 / step_s) + 1)
    seconds = n * step_s
    index = D + pd.to_timedelta(seconds, unit="s")
    return pd.DataFrame({"x": values(seconds)}, index=index)


@pytest.mark.parametrize("step", [10.0, 15.0])
def test_a_dividing_step_gives_the_simple_mean(step: float) -> None:
    rng = np.random.default_rng(1)
    frame = series(step, 2, lambda s: rng.normal(8, 2, len(s)))
    means = weighted_means(frame, start=D)
    per_interval = int(600 / step)
    assert means.kept == 12 and means.excluded == 0
    expected = frame["x"].to_numpy().reshape(12, per_interval).mean(axis=1)
    assert means.frame["x"].to_numpy() == pytest.approx(expected, abs=1e-9)
    # Stamped at the end of ]t - 10 min, t]
    assert means.frame.index[0] == D + pd.Timedelta(minutes=10)


def test_a_constant_with_a_step_not_dividing_600() -> None:
    frame = series(35.0, 3, lambda s: np.full(len(s), 7.25))
    means = weighted_means(frame, start=D)
    assert means.kept >= 17
    assert means.frame["x"].to_numpy() == pytest.approx(7.25, abs=1e-12)


def test_a_linear_signal_with_a_step_not_dividing_600() -> None:
    step = 35.0
    frame = series(step, 3, lambda s: 0.01 * s)
    means = weighted_means(frame, start=D)
    for end, value in means.frame["x"].items():
        t1 = (end - D).total_seconds()
        # Independent integration of the step function: the value at n x dt holds on
        # ](n - 1) x dt, n x dt], sampled every 1/100 s
        fine = np.arange(t1 - 600, t1, 0.01) + 0.005
        step_value = 0.01 * np.ceil(fine / step) * step
        assert value == pytest.approx(step_value.mean(), abs=1e-4)
        # Hence the middle of the interval plus about half a step
        assert value == pytest.approx(0.01 * (t1 - 300) + 0.01 * step / 2, abs=0.01 * step / 2)


def test_an_interval_with_a_hole_is_left_out() -> None:
    frame = series(15.0, 1, lambda s: np.ones(len(s)))
    # Drop one value inside the third interval ]20 min, 30 min]
    frame = frame.drop(D + pd.Timedelta(minutes=25))
    means = weighted_means(frame, start=D)
    assert means.excluded == 1 and means.kept == 5
    assert D + pd.Timedelta(minutes=30) not in means.frame.index
    assert "1 incomplete interval" in means.note


def test_directions_from_mean_components() -> None:
    index = D + pd.to_timedelta(np.arange(1, 41) * 15, unit="s")
    # Wind alternating between north-west and north-east at 10 m/s
    u = np.where(np.arange(40) % 2, 1.0, -1.0) * 10 / np.sqrt(2)
    v = -np.full(40, 10 / np.sqrt(2))
    speed = np.hypot(u, v)
    frame = pd.DataFrame({"u": u, "v": v, "speed": speed, "direction": 0.0}, index=index)
    means = weighted_means(frame, start=D, vectors={"direction": ("u", "v")})
    row = means.frame.iloc[0]
    assert row["direction"] == pytest.approx(0.0, abs=1e-9) or row["direction"] == pytest.approx(
        360.0
    )
    assert row["speed"] == pytest.approx(10.0)  # mean of the instantaneous speed


def test_variable_step() -> None:
    steps = np.tile([10.0, 20.0, 30.0], 40)
    seconds = np.cumsum(steps)
    frame = pd.DataFrame(
        {"x": np.full(len(seconds), 3.0)}, index=D + pd.to_timedelta(seconds, unit="s")
    )
    means = weighted_means(frame, start=D)
    assert means.excluded == 0 and means.kept == int(seconds[-1] // 600)
    assert means.frame["x"].to_numpy() == pytest.approx(3.0)
