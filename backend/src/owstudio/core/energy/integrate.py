"""Energy from power series: mean power x interval for fixed-interval means (tslist), trapezoids
between output times for instantaneous values (wrfout), spin-up excluded; sums by hour, day or
month, capacity factor and AEP.

Between two instantaneous values the power is unknown and the trapezoid is the consistent estimate.
Gaps longer than the tolerance are not bridged: they count neither in the energy nor in the covered
time.
"""

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd

from owstudio.core.i18n import num, tr
from owstudio.core.times import naive_index, utc_index, utc_stamp

HOURS_PER_YEAR = 8766.0  # 365.25 days
# AEP only from at least a full year of covered time
MIN_HOURS_FOR_AEP = 8760.0
PERIODS = {"hour": "h", "day": "D", "month": "MS"}


@dataclass
class Energy:
    energy_wh: float
    covered_h: float
    gaps: list[tuple[str, str]] = field(default_factory=list)
    samples: int = 0
    first: datetime | None = None
    last: datetime | None = None

    @property
    def mean_power_w(self) -> float | None:
        return self.energy_wh / self.covered_h if self.covered_h > 0 else None


def clean(power: pd.Series, start: datetime | pd.Timestamp | None = None) -> pd.Series:
    """Sorted UTC power without missing values, from ``start`` (end of spin-up) on."""
    p = power.dropna().sort_index()
    p.index = utc_index(p.index)
    if start is not None:
        p = p[p.index >= utc_stamp(start)]
    return p


def tolerance(index: pd.DatetimeIndex, factor: float = 1.5) -> float:
    """Longest interval bridged, seconds: 1.5 times the usual (median) step."""
    if len(index) < 2:
        return 0.0
    steps = np.diff(index.to_numpy(dtype="datetime64[ns]").astype("int64")) / 1e9
    return float(np.median(steps) * factor)


def segments(power: pd.Series, max_gap_s: float) -> pd.DataFrame:
    """Each bridged interval: its start, end, duration (s) and trapezoidal energy (Wh)."""
    if len(power) < 2:
        return pd.DataFrame(columns=["start", "end", "seconds", "energy_wh"])
    t = pd.DatetimeIndex(power.index)
    seconds = np.diff(t.to_numpy(dtype="datetime64[ns]").astype("int64")) / 1e9
    v = power.to_numpy(dtype=float)
    energy = 0.5 * (v[:-1] + v[1:]) * seconds / 3600.0
    frame = pd.DataFrame({"start": t[:-1], "end": t[1:], "seconds": seconds, "energy_wh": energy})
    return frame[frame["seconds"] <= max_gap_s + 1e-6]


def means(
    power: pd.Series, averaging_s: float, start: datetime | pd.Timestamp | None = None
) -> pd.DataFrame:
    """Each interval ]t - averaging_s, t] of a series of mean powers (W) stamped at their end t,
    from ``start`` on: its start, end, duration (s) and energy (Wh), mean power x duration."""
    p = clean(power)
    t = pd.DatetimeIndex(p.index)
    begins = t - pd.Timedelta(seconds=averaging_s)
    frame = pd.DataFrame(
        {
            "start": begins,
            "end": t,
            "seconds": float(averaging_s),
            "energy_wh": p.to_numpy(dtype=float) * averaging_s / 3600.0,
        }
    )
    if start is not None:
        frame = frame[frame["start"] >= utc_stamp(start)]
    return frame.reset_index(drop=True)


def integrate(
    power: pd.Series,
    start: datetime | pd.Timestamp | None = None,
    max_gap_s: float | None = None,
    averaging_s: float = 0.0,
) -> Energy:
    """Energy (Wh) of a power series (W) from ``start`` on, and the covered duration. With
    ``averaging_s``, the values are means over the interval ending at each time: energy = mean
    power x interval; otherwise instantaneous values, integrated by trapezoids."""
    if averaging_s:
        parts = means(power, averaging_s, start)
        ends = pd.DatetimeIndex(parts["end"])
        begins = pd.DatetimeIndex(parts["start"])
        gaps = [
            (ends[int(k) - 1].isoformat(), begins[int(k)].isoformat())
            for k in np.flatnonzero(begins[1:] > ends[:-1]) + 1
        ]
        return Energy(
            float(parts["energy_wh"].sum()),
            float(parts["seconds"].sum()) / 3600.0,
            gaps,
            len(parts),
            parts["start"].iloc[0].to_pydatetime() if len(parts) else None,
            ends[-1].to_pydatetime() if len(parts) else None,
        )
    p = clean(power, start)
    gap = tolerance(pd.DatetimeIndex(p.index)) if max_gap_s is None else max_gap_s
    parts = segments(p, gap)
    t = pd.DatetimeIndex(p.index)
    gaps = []
    if len(t) > 1:
        seconds = np.diff(t.to_numpy(dtype="datetime64[ns]").astype("int64")) / 1e9
        gaps = [
            (t[int(k)].isoformat(), t[int(k) + 1].isoformat())
            for k in np.flatnonzero(seconds > gap + 1e-6)
        ]
    return Energy(
        float(parts["energy_wh"].sum()),
        float(parts["seconds"].sum()) / 3600.0,
        gaps,
        len(p),
        t[0].to_pydatetime() if len(t) else None,
        t[-1].to_pydatetime() if len(t) else None,
    )


def by_period(
    power: pd.Series,
    period: str,
    start: datetime | pd.Timestamp | None = None,
    max_gap_s: float | None = None,
    averaging_s: float = 0.0,
) -> pd.DataFrame:
    """Energy (Wh) and covered hours per UTC hour, day or month; each interval counts in the
    period holding its middle (``averaging_s``: see integrate)."""
    if period not in PERIODS:
        raise ValueError(
            tr(
                f"Unknown period {period!r} (hour, day or month)",
                f"Période inconnue {period!r} (heure, jour ou mois)",
            )
        )
    if averaging_s:
        parts = means(power, averaging_s, start)
    else:
        p = clean(power, start)
        parts = segments(
            p, tolerance(pd.DatetimeIndex(p.index)) if max_gap_s is None else max_gap_s
        )
    if parts.empty:
        return pd.DataFrame(columns=["period_start", "energy_wh", "covered_h"])
    middle = pd.DatetimeIndex(parts["start"]) + pd.to_timedelta(
        parts["seconds"].to_numpy() / 2, unit="s"
    )
    # Periods are read on UTC clock times (pandas periods hold no time zone)
    periods = naive_index(middle).to_period(PERIODS[period].replace("MS", "M"))
    grouped = parts.assign(period=periods.start_time.tz_localize("UTC")).groupby("period")
    result = pd.DataFrame(
        {"energy_wh": grouped["energy_wh"].sum(), "covered_h": grouped["seconds"].sum() / 3600.0}
    )
    return result.reset_index(names="period_start")


def common_start(period_start: datetime, initial_left_out: bool) -> pd.Timestamp:
    """Start of the energy integration, the same for a run and its reference: the start of the
    period, or just after it when the run's power leaves out the initial time of the simulation
    (WRF's POWER, written before the first step, is zero there)."""
    start = pd.Timestamp(period_start)
    return start + pd.Timedelta(seconds=1) if initial_left_out else start


def capacity_factor(energy: Energy, installed_w: float) -> float | None:
    """Energy divided by installed power times the covered duration."""
    if installed_w <= 0 or energy.covered_h <= 0:
        return None
    return energy.energy_wh / (installed_w * energy.covered_h)


def aep(energy: Energy) -> tuple[float | None, str]:
    """Annual energy (Wh per year) when at least a full year is covered, otherwise None and why."""
    if energy.covered_h < MIN_HOURS_FOR_AEP:
        return None, tr(
            f"Not given: the run covers {energy.covered_h:.0f} h, less than a year. An annual energy "
            "needs a full year of simulation (or a long-term correction, not done here): the "
            "energy over the computed period is given instead.",
            f"Non donnée : le calcul couvre {energy.covered_h:.0f} h, moins d'un an. Une énergie "
            "annuelle demande une année entière de simulation (ou une correction long terme, non "
            "faite ici) : l'énergie sur la période calculée est donnée à la place.",
        )
    return energy.energy_wh / energy.covered_h * HOURS_PER_YEAR, tr(
        f"Energy over {energy.covered_h / HOURS_PER_YEAR:.2f} years of covered time, scaled to "
        f"{HOURS_PER_YEAR:g} h per year; inter-annual variability is not represented.",
        f"Énergie sur {num(energy.covered_h / HOURS_PER_YEAR, '.2f')} années couvertes, ramenée à "
        f"{num(HOURS_PER_YEAR)} h par an ; la variabilité d'une année à l'autre n'est pas représentée.",
    )
