"""Wind analyses on synthetic series with known statistics."""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from helpers import make_client

from owstudio.core.analysis import distribution, profile, rose, stability, weibull
from owstudio.core.analysis.common import AnalysisError, Selection, by_sector, by_time
from owstudio.core.analysis.compare import compare
from owstudio.core.analysis.wind import Wind
from owstudio.core.series import Series, SeriesMeta, sources


def series(
    values: Any,
    variable: str = "wind_speed",
    unit: str = "m s-1",
    height: float | None = 100.0,
    freq: str = "10min",
    **meta: Any,
) -> Series:
    values = np.asarray(values, dtype=float)
    times = pd.date_range("2025-01-01", periods=values.size, freq=freq, tz="UTC")
    fields: dict[str, Any] = {
        "variable": variable, "unit": unit, "source": "observation", "dataset": "test", "location": "M1",
        "height_m": height, "height_ref": "agl" if height is not None else "surface",
    }  # fmt: skip
    fields.update(meta)
    return Series(SeriesMeta.model_validate(fields), pd.Series(values, index=times))


def direction(values: Any, **meta: Any) -> Series:
    return series(values, "wind_direction", "deg", **meta)


# ------------------------------------------------------------------ roses


def test_rose_frequencies_and_energy() -> None:
    # 3 samples from north (one at 355°, still sector 0), 1 from east; speeds 4, 4, 8, 2
    wind = Wind(series([4, 4, 8, 2]), direction([355, 5, 0, 90]))
    result = rose.wind_rose([wind], sectors=4, speed_bins=[0, 5]).to_json()
    north, east = result["sectors"][0], result["sectors"][1]
    assert north["frequency_pct"] == pytest.approx(75) and east["frequency_pct"] == pytest.approx(
        25
    )
    # Energy share of U³: (64 + 64 + 512) / (640 + 8)
    assert north["energy_pct"] == pytest.approx(100 * 640 / 648)
    assert result["frequency"][0] == pytest.approx([50, 25])  # 2 samples below 5 m/s, 1 above


def test_rose_refuses_speeds_with_negative_values() -> None:
    with pytest.raises(AnalysisError, match="negative wind speeds"):
        rose.wind_rose([Wind(series([4, -999, 3]), direction([0, 0, 0]))])


# ---------------------------------------------------------------- Weibull


def test_weibull_recovers_known_parameters() -> None:
    rng = np.random.default_rng(1)
    k, a = 2.2, 9.0
    speeds = a * rng.weibull(k, 20000)
    result = weibull.weibull_analysis(Wind(series(speeds)), sectors=0).to_json()
    for method in ("mle", "moments", "wasp"):
        fit = result["all"]["fits"][method]
        assert fit["k"] == pytest.approx(k, rel=0.04) and fit["A"] == pytest.approx(a, rel=0.02)
        assert fit["ks"] < 0.02
    # The WAsP fit preserves the mean cube by construction
    assert result["all"]["fits"]["wasp"]["mean_cube_ratio"] == pytest.approx(1.0, abs=1e-6)


def test_weibull_counts_calms_in_the_share_of_time_not_in_the_fit() -> None:
    rng = np.random.default_rng(2)
    speeds = np.concatenate([9.0 * rng.weibull(2.2, 900), np.zeros(100)])
    result = weibull.weibull_analysis(Wind(series(speeds)), sectors=0, methods=["mle"]).to_json()
    histogram = result["histogram"]
    # Every valid speed in the shares of time, calms in the first class; the fit without them
    assert sum(histogram["counts_all"]) == 1000 and sum(histogram["counts"]) == 900
    assert histogram["counts_all"][0] - histogram["counts"][0] == 100
    assert result["observed_all"]["mean"] == pytest.approx(speeds.mean())
    assert result["all"]["observed"]["mean"] == pytest.approx(speeds[speeds > 0].mean())


def test_weibull_refuses_too_few_samples() -> None:
    with pytest.raises(AnalysisError, match="fewer than the minimum"):
        weibull.weibull_analysis(Wind(series([5.0] * 30)))


# -------------------------------------------------------- distributions


def test_histogram_and_circular_statistics() -> None:
    result = distribution.histogram(series([1, 2, 2, 3]), edges=[0, 2, 4]).to_json()
    assert result["counts"] == [1, 3] and result["statistics"]["mean"] == pytest.approx(2.0)
    directions = distribution.histogram(direction([350, 10]), bins=4).to_json()
    assert directions["statistics"]["mean"] == pytest.approx(0.0, abs=1e-9)  # not 180


def test_aggregation_drops_periods_with_low_availability() -> None:
    values = np.arange(12, dtype=float)  # two hours of 10-min values
    values[7:11] = np.nan  # second hour: 2 of 6 values
    result = distribution.aggregate(series(values), "hour", min_availability=0.7).to_json()
    assert result["mean"][0] == pytest.approx(np.mean(np.arange(6)))
    assert result["mean"][1] is None and result["availability"][1] == pytest.approx(2 / 6)


def test_daily_cycle_by_hour() -> None:
    hours = np.tile(np.arange(24, dtype=float), 3)  # value = hour of day
    data = series(hours, freq="h")
    result = distribution.grouped(data, by_time("hour", data.meta)).to_json()
    assert [g["mean"] for g in result["groups"]] == pytest.approx(list(range(24)))


def test_grouping_by_sector() -> None:
    speed, dirs = series([2, 4, 6, 8]), direction([0, 0, 180, 180])
    result = distribution.grouped(speed, by_sector(dirs, 4, Selection())).to_json()
    assert result["groups"][0]["mean"] == pytest.approx(3) and result["groups"][2][
        "mean"
    ] == pytest.approx(7)


# ------------------------------------------------------- profiles, shear


def test_shear_of_a_power_law_profile() -> None:
    alpha = 0.14
    base = np.array([6.0, 8.0, 10.0])
    heights = [40.0, 100.0, 160.0]
    winds = [series(base * (z / 100.0) ** alpha, height=z) for z in heights]
    result = profile.shear(winds).to_json()
    assert result["groups"][0]["pairwise"]["mean"] == pytest.approx(alpha, abs=1e-9)
    assert result["groups"][0]["fit"]["mean"] == pytest.approx(alpha, abs=1e-9)


def test_profile_refuses_mixed_height_references() -> None:
    with pytest.raises(AnalysisError, match="mix references"):
        profile.profile([series([5], height=50), series([6], height=100, height_ref="asl")])


def test_veer_across_north() -> None:
    result = profile.veer(direction([350.0], height=50), direction([10.0], height=150)).to_json()
    assert result["groups"][0]["mean"] == pytest.approx(20.0)
    assert result["groups"][0]["mean_deg_per_m"] == pytest.approx(0.2)


# -------------------------------------------------------------- stability


def test_stability_classes_of_gryning_2007() -> None:
    lengths = series([-75, -150, -300, 1000, 300, 100, 30, 5], "obukhov_length", "m", height=None)
    result = stability.stability_analysis(lengths).to_json()
    counts = {c["key"]: c["count"] for c in result["classes"]}
    assert counts == {
        "very_unstable": 1, "unstable": 1, "near_neutral_unstable": 1, "neutral": 1,
        "near_neutral_stable": 1, "stable": 1, "very_stable": 1,
    }  # fmt: skip
    assert result["counts"]["outside_scheme"] == 1  # L = 5 m is outside the published limits


# ------------------------------------------------------------- comparison


def test_comparison_metrics() -> None:
    reference = series([1.0, 2.0, 3.0, 4.0])
    evaluated = series([2.0, 3.0, 4.0, 5.0])  # +1 everywhere
    result = compare(reference, evaluated).to_json()["overall"]
    assert result["bias"] == pytest.approx(1.0) and result["rmse"] == pytest.approx(1.0)
    assert result["crmse"] == pytest.approx(0.0) and result["correlation"] == pytest.approx(1.0)
    assert result["ols_slope"] == pytest.approx(1.0) and result[
        "orthogonal_slope"
    ] == pytest.approx(1.0)


def test_comparison_of_directions_is_circular() -> None:
    result = compare(direction([355.0, 5.0]), direction([5.0, 355.0])).to_json()["overall"]
    assert result["mae"] == pytest.approx(10.0) and result["bias"] == pytest.approx(0.0, abs=1e-9)


def test_comparison_refuses_different_averaging() -> None:
    with pytest.raises(AnalysisError, match="same averaging"):
        compare(series([1.0, 2.0]), series([1.0, 2.0], averaging_s=600, time_label="end"))


# -------------------------------------------------------------------- API


def test_analysis_api_resolves_references(tmp_path: Path) -> None:
    rng = np.random.default_rng(3)
    data = {
        "ws": series(9 * rng.weibull(2.0, 2000)),
        "wd": direction(rng.uniform(0, 360, 2000)),
    }
    sources.register("analysis-test", lambda _context, ref: data[ref.location])
    client = make_client(tmp_path)
    ref = {"kind": "analysis-test", "variable": "wind_speed", "location": "ws"}
    direction_ref = {"kind": "analysis-test", "variable": "wind_direction", "location": "wd"}
    rose_result = client.post(
        "/api/analysis/rose", json={"winds": [{"speed": ref, "direction": direction_ref}]}
    ).json()
    assert len(rose_result["sectors"]) == 12 and rose_result["samples"]["valid"] == 2000
    csv = client.post(
        "/api/analysis/weibull",
        params={"format": "csv", "table": "fits"},
        json={"wind": {"speed": ref}},
    )
    assert csv.headers["content-type"].startswith("text/csv") and "mle" in csv.text
    refused = client.post("/api/analysis/veer", json={"series": [ref, ref, ref]})
    assert refused.status_code == 422 and "two heights" in refused.text
    missing = client.post(
        "/api/analysis/histogram", json={"series": {"kind": "nope", "variable": "x"}}
    )
    assert missing.status_code == 404
    assert client.get("/api/analysis/schemes").json()[0]["key"] == "gryning2007"


def test_bulk_richardson_api_uses_two_levels_and_preserves_undefined(tmp_path: Path) -> None:
    data = {}
    for height, theta, u in ((25, [300, 300], [3, 3]), (125, [301, 301], [5, 3])):
        for variable, values, unit in (
            ("virtual_potential_temperature", theta, "K"),
            ("u", u, "m s-1"),
            ("v", [0, 0], "m s-1"),
        ):
            data[f"{height}-{variable}"] = series(values, variable, unit, height=height)
    sources.register("ri-test", lambda _context, ref: data[ref.location])

    def level(height: int) -> dict[str, Any]:
        return {
            key: {
                "kind": "ri-test",
                "variable": variable,
                "location": f"{height}-{variable}",
                "height_m": height,
            }
            for key, variable in (
                ("theta_v", "virtual_potential_temperature"),
                ("u", "u"),
                ("v", "v"),
            )
        }

    client = make_client(tmp_path)
    response = client.post(
        "/api/analysis/bulk-richardson", json={"lower": level(25), "upper": level(125)}
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["samples"] == {"paired": 2, "valid": 1, "undefined": 1}
    assert result["statistics"]["mean"] == pytest.approx(9.81 / 300.5 * 100 / 4)
