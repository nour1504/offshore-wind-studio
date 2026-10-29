"""Time-weighted means of model time series over fixed intervals (10 minutes by default).

Convention of the window method:
- intervals ]t - P, t], aligned on multiples of P in UTC, stamped at their end t;
- each WRF value counts for the time step that ends at it: the value written at t_k stands for
  ]t_(k-1), t_k] (WRF writes its time series after each step, share/wrf_timeseries.F). The
  weight of a value in an interval is the length of the overlap, divided by P. With a step
  dividing P, every complete interval holds exactly P / dt values of equal weight: the mean is
  their simple mean. Any step works, also a variable (adaptive) one;
- an interval is kept only when its whole length is covered by values; otherwise it is left out
  and counted. A value is taken to cover at most 1.5 typical steps before it (3 with a variable
  step), so that a missing value leaves a hole instead of being stretched over it;
- speed: mean of the instantaneous speed; direction: from the means of u and v.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from owstudio.core.i18n import tr

DEFAULT_PERIOD_S = 600


@dataclass(frozen=True)
class Means:
    frame: pd.DataFrame
    period_s: int
    # Intervals touched by the data but not entirely covered: left out
    excluded: int
    kept: int

    @property
    def note(self) -> str:
        return tr(
            f"time-weighted means over ]t - {self.period_s // 60} min, t] (UTC), stamped at the "
            "end t; each model value counts for the time step ending at it; "
            f"{self.excluded} incomplete interval(s) left out",
            f"moyennes pondérées par le temps sur ]t - {self.period_s // 60} min, t] (UTC), "
            "horodatées à la fin t ; chaque valeur du modèle compte pour le pas de temps qui se "
            f"termine à elle ; {self.excluded} intervalle(s) incomplet(s) écarté(s)",
        )


def _seconds(index: pd.DatetimeIndex) -> np.ndarray:
    utc = index.tz_convert("UTC") if index.tz is not None else index
    return utc.to_numpy(dtype="datetime64[ns]").astype("int64") / 1e9


def coverage(times: np.ndarray, start: float | None = None) -> np.ndarray:
    """Start of the step each value stands for: ]start_k, t_k]."""
    if len(times) == 0:
        return times
    steps = np.diff(times)
    typical = float(np.median(steps)) if len(steps) else 0.0
    if typical <= 0:
        return times.copy()
    variable = len(steps) > 1 and np.mean(np.abs(steps - typical) > 0.01 * typical) > 0.02
    cap = (3.0 if variable else 1.5) * typical
    previous = np.empty_like(times)
    previous[0] = times[0] - typical if start is None else max(start, times[0] - cap)
    previous[1:] = times[:-1]
    limited: np.ndarray = np.maximum(previous, times - cap)
    return limited


def weighted_means(
    frame: pd.DataFrame,
    period_s: int = DEFAULT_PERIOD_S,
    start: pd.Timestamp | None = None,
    vectors: dict[str, tuple[str, str]] | None = None,
) -> Means:
    """Means of every column over ]t - period, t]. ``vectors`` maps a direction column to its
    (u, v) columns, recomputed from their means. ``start`` is the time before the first value
    (D for the series of the window method)."""
    if frame.empty:
        return Means(frame.copy(), period_s, 0, 0)
    times = _seconds(pd.DatetimeIndex(frame.index))
    begins = coverage(
        times, None if start is None else float(_seconds(pd.DatetimeIndex([start]))[0])
    )
    first = np.floor(begins.min() / period_s) * period_s
    last = np.ceil(times.max() / period_s) * period_s
    ends = np.arange(first + period_s, last + period_s / 2, period_s)
    count = len(ends)
    covered = np.zeros(count)
    columns = [c for c in frame.columns if pd.api.types.is_numeric_dtype(frame[c])]
    values = frame[columns].to_numpy(dtype=float)
    sums = np.zeros((count, len(columns)))
    weights = np.zeros((count, len(columns)))
    valid = times > begins
    lo_index = np.floor((begins - first) / period_s).astype(int)
    hi_index = np.ceil((times - first) / period_s).astype(int) - 1

    def add(rows: np.ndarray, interval: np.ndarray, overlap: np.ndarray) -> None:
        np.add.at(covered, interval, overlap)
        block = values[rows]
        finite = np.isfinite(block)
        np.add.at(sums, interval, np.where(finite, block, 0.0) * overlap[:, None])
        np.add.at(weights, interval, finite * overlap[:, None])

    # Values inside one interval
    inside = np.nonzero(valid & (lo_index == hi_index))[0]
    add(inside, lo_index[inside], times[inside] - begins[inside])
    # Values across a limit: split
    for k in np.nonzero(valid & (lo_index != hi_index))[0]:
        for n in range(max(lo_index[k], 0), min(hi_index[k], count - 1) + 1):
            a = first + n * period_s
            overlap = min(times[k], a + period_s) - max(begins[k], a)
            if overlap > 0:
                add(np.array([k]), np.array([n]), np.array([overlap]))
    complete = np.isclose(covered, period_s, rtol=0, atol=1e-6 * period_s) & (covered > 0)
    touched = covered > 0
    # A variable missing at some step of an interval has a hole there: no mean for it
    full = np.isclose(weights, period_s, rtol=0, atol=1e-6 * period_s)
    with np.errstate(invalid="ignore", divide="ignore"):
        means = np.where(full, sums / np.where(weights > 0, weights, 1.0), np.nan)
    result = pd.DataFrame(means, columns=columns, index=pd.to_datetime(ends, unit="s", utc=True))
    for direction, (u, v) in (vectors or {}).items():
        if u in result and v in result:
            result[direction] = (270.0 - np.degrees(np.arctan2(result[v], result[u]))) % 360.0
    if pd.DatetimeIndex(frame.index).tz is None:
        result.index = pd.DatetimeIndex(result.index).tz_localize(None)
    kept = result[complete]
    return Means(kept, period_s, int((touched & ~complete).sum()), int(complete.sum()))
