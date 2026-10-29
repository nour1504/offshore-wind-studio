"""One retained-time contract for history, tslist, energy, maps and media.

Windows keep raw files in their own directories; windows.json controls what readers see.
Manifest version 2 (the window method, core/method/plan.py): each window keeps
]useful_start, useful_end]; the first one also keeps the history at D, end of its spin-up, so
history covers [D, F] and time series ]D, F]. Version 1 (runs of older versions) kept
[useful_start, useful_end), with the final end included. Original files are never edited or
removed by this module.
"""

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from owstudio.core.i18n import tr


@dataclass(frozen=True)
class OutputSource:
    folder: Path
    start: pd.Timestamp | None = None
    end: pd.Timestamp | None = None
    include_end: bool = True
    include_start: bool = True

    def mask(self, times: pd.DatetimeIndex) -> np.ndarray:
        utc = times.tz_localize("UTC") if times.tz is None else times.tz_convert("UTC")
        keep = np.ones(len(times), dtype=bool)
        if self.start is not None:
            keep &= np.asarray(utc >= self.start if self.include_start else utc > self.start)
        if self.end is not None:
            keep &= np.asarray(utc <= self.end if self.include_end else utc < self.end)
        return keep


def _utc(text: str) -> pd.Timestamp:
    time = pd.Timestamp(text)
    return time.tz_localize("UTC") if time.tzinfo is None else time.tz_convert("UTC")


def output_sources(folder: Path, history: bool = True) -> list[OutputSource]:
    """All source directories with retention bounds, or the ordinary single output folder.
    ``history`` False gives the bounds of time series: never D itself."""
    manifest = folder / "windows.json"
    if not manifest.is_file():
        return [OutputSource(folder)]
    body = json.loads(manifest.read_text(encoding="utf-8"))
    version = body.get("schema_version")
    if version not in (1, 2) or body.get("mode") != "independent_windows":
        raise ValueError(
            tr(
                "Unsupported independent-window output manifest",
                "Description des sorties par fenêtres non prise en charge",
            )
        )
    found = []
    for row in body["windows"]:
        target = (folder / row["output_dir"]).resolve()
        if not target.is_relative_to(folder.resolve()) or target == folder.resolve():
            raise ValueError(
                tr(
                    "Window output directory is outside the run",
                    "Le dossier des sorties d'une fenêtre est hors du calcul",
                )
            )
        start, end = _utc(row["useful_start"]), _utc(row["useful_end"])
        if end <= start:
            raise ValueError(
                tr("Invalid retained window interval", "Intervalle gardé d'une fenêtre invalide")
            )
        if version == 1:
            found.append(OutputSource(target, start, end, bool(row["include_end"]), True))
        else:
            include_start = history and bool(row.get("include_start", False))
            found.append(OutputSource(target, start, end, True, include_start))
    return found


def history_paths(folder: Path, domain: int | None = None) -> list[Path]:
    pattern = "wrfout_d*" if domain is None else f"wrfout_d{domain:02d}_*"
    return [
        p
        for source in output_sources(folder)
        for p in sorted(source.folder.glob(pattern))
        if p.is_file()
    ]


def time_series_sources(folder: Path) -> list[OutputSource]:
    """``folder`` is the tslist directory; a window manifest is on its parent stage."""
    if (folder.parent / "windows.json").is_file():
        return [
            OutputSource(s.folder / "tslist", s.start, s.end, s.include_end, s.include_start)
            for s in output_sources(folder.parent, history=False)
        ]
    return [OutputSource(folder)]
