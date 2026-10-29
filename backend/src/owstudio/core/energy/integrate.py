"""Energy from power time series: trapezoidal integration over the output times, with gaps not
bridged, spin-up excluded, aggregation by hour, day or month, capacity factor and AEP.

WRF's power outputs are instantaneous values at the output times: between two of them the power
is unknown, and the trapezoidal rule (the mean of the two values over the interval) is the
consistent estimate of the energy. Intervals longer than the gap tolerance are not bridged: they
count neither in the energy nor in the covered duration.
"""

from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd

from owstudio.core.i18n import tr

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
    p.index = (
        pd.DatetimeIndex(p.index).tz_localize("UTC")
        if pd.DatetimeIndex(p.index).tz is None
        else pd.DatetimeIndex(p.index).tz_convert("UTC")
    )
    if start is not None:
        stamp = pd.Timestamp(start)
        stamp = stamp.tz_localize("UTC") if stamp.tz is None else stamp.tz_convert("UTC")
        p = p[p.index >= stamp]
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


def integrate(
    power: pd.Series, start: datetime | pd.Timestamp | None = None, max_gap_s: float | None = None
) -> Energy:
    """Energy (Wh) of a power series (W) from ``start`` on, and the covered duration."""
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
) -> pd.DataFrame:
    """Energy (Wh) and covered hours per UTC hour, day or month; each interval counts in the
    period holding its middle."""
    if period not in PERIODS:
        raise ValueError(
            tr(
                f"Unknown period {period!r} (hour, day or month)",
                f"Période inconnue {period!r} (heure, jour ou mois)",
            )
        )
    p = clean(power, start)
    gap = tolerance(pd.DatetimeIndex(p.index)) if max_gap_s is None else max_gap_s
    parts = segments(p, gap)
    if parts.empty:
        return pd.DataFrame(columns=["period_start", "energy_wh", "covered_h"])
    middle = pd.DatetimeIndex(parts["start"]) + pd.to_timedelta(
        parts["seconds"].to_numpy() / 2, unit="s"
    )
    grouped = parts.assign(
        period=middle.to_period(PERIODS[period].replace("MS", "M")).start_time.tz_localize("UTC")
    ).groupby("period")
    result = pd.DataFrame(
        {"energy_wh": grouped["energy_wh"].sum(), "covered_h": grouped["seconds"].sum() / 3600.0}
    )
    return result.reset_index(names="period_start")


def common_start(period_start: datetime, spin_up_hours: float, method: str) -> pd.Timestamp:
    """Start of the energy integration, the same for a run and its reference: after the spin-up,
    and after the initial time for WRF's POWER (written before the first step, always zero)."""
    start = pd.Timestamp(period_start) + pd.Timedelta(hours=spin_up_hours)
    if method == "wrf":
        start = max(start, pd.Timestamp(period_start) + pd.Timedelta(seconds=1))
    return start


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
        f"Énergie sur {energy.covered_h / HOURS_PER_YEAR:.2f} années couvertes, ramenée à "
        f"{HOURS_PER_YEAR:g} h par an ; la variabilité d'une année à l'autre n'est pas représentée.",
    )
