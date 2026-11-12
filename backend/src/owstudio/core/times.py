"""Times in UTC, as everywhere in the application. WRF and WPS write UTC times without zone
(2025-10-01_00:00:00); a time without zone is taken as UTC."""

from datetime import UTC, datetime
from typing import Any

import pandas as pd

WRF_DATE = "%Y-%m-%d_%H:%M:%S"


def wrf_date(moment: datetime) -> str:
    """A time as WRF and WPS write it."""
    return moment.strftime(WRF_DATE)


def naive_utc(moment: datetime) -> datetime:
    """UTC wall time without zone, as in WRF and WPS dates."""
    return moment.astimezone(UTC).replace(tzinfo=None) if moment.tzinfo else moment


def utc_stamp(moment: Any) -> pd.Timestamp:
    """A UTC timestamp."""
    stamp = pd.Timestamp(moment)
    return stamp.tz_localize("UTC") if stamp.tz is None else stamp.tz_convert("UTC")


def naive_stamp(moment: Any) -> pd.Timestamp:
    """A UTC timestamp without zone, as in the tables of the tslist files."""
    stamp = pd.Timestamp(moment)
    return stamp.tz_convert("UTC").tz_localize(None) if stamp.tz is not None else stamp


def utc_index(times: Any) -> pd.DatetimeIndex:
    """UTC times."""
    index = pd.DatetimeIndex(times)
    return index.tz_localize("UTC") if index.tz is None else index.tz_convert("UTC")


def naive_index(times: Any) -> pd.DatetimeIndex:
    """UTC times without zone."""
    index = pd.DatetimeIndex(times)
    return index.tz_convert("UTC").tz_localize(None) if index.tz is not None else index
