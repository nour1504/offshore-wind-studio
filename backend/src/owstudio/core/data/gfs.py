"""GFS 0.25 degree analyses from the NOAA Open Data archive on AWS (no account needed)."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from owstudio.core.case.model import Period
from owstudio.core.i18n import tr

ARCHIVE_URL = "https://noaa-gfs-bdp-pds.s3.amazonaws.com"
# First cycle of the archive on AWS
ARCHIVE_START = datetime(2021, 1, 1)
# Since GFS v16, files sit in an "atmos" subdirectory of each cycle
GFS_V16_START = datetime(2021, 3, 22, 12)
CYCLE_HOURS = 6


@dataclass(frozen=True)
class GribFile:
    url: str
    name: str


def analysis_times(period: Period) -> list[datetime]:
    """Analysis times covering the period, one per boundary interval."""
    if period.interval_seconds % (CYCLE_HOURS * 3600):
        raise ValueError(
            tr(
                "GFS analyses are 6-hourly: interval_seconds must be a multiple of 21600",
                "Les analyses GFS sont toutes les 6 heures : interval_seconds doit être un multiple de 21600",
            )
        )
    if period.start.hour % CYCLE_HOURS or period.start.minute or period.start.second:
        raise ValueError(
            tr(
                "GFS analyses start at 00, 06, 12 or 18 UTC",
                "Les analyses GFS commencent à 00, 06, 12 ou 18 UTC",
            )
        )
    step = timedelta(seconds=period.interval_seconds)
    times, t = [], period.start
    while t < period.end:
        times.append(t)
        t += step
    times.append(t)
    return times


def files_for(period: Period) -> list[GribFile]:
    if period.start < ARCHIVE_START:
        raise ValueError(
            tr(
                f"GFS from {ARCHIVE_START:%Y-%m-%d} only: ERA5 or own files before",
                f"GFS à partir du {ARCHIVE_START:%d/%m/%Y} seulement : ERA5 ou vos fichiers avant",
            )
        )
    return [
        GribFile(
            url=f"{ARCHIVE_URL}/gfs.{t:%Y%m%d}/{t:%H}/"
            + ("atmos/" if t >= GFS_V16_START else "")
            + f"gfs.t{t:%H}z.pgrb2.0p25.f000",
            name=f"gfs.{t:%Y%m%d%H}.f000.grib2",
        )
        for t in analysis_times(period)
    ]
