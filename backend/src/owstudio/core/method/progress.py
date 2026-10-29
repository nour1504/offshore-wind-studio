"""Where a calculation of an extracted folder stands, read from the files its scripts write.

Nothing is launched nor written: the folder is read as the scripts left it.

- the input data: the files its download script lists, in the shared folder it names
  (DOSSIER_DONNEES, DATA_DIR) or else in donnees/ (data/); the part being downloaded ends in .part;
- the run journal (calcul.log, run.log), written by the command of the README: one line per step,
  "[2026-10-26 18:18:00 UTC]   > wrf.exe...", and "ERREUR :" / "ERROR:" when a script stops;
- the windows done (wrf/journaux/fenetres_faites.txt, wrf/logs/windows_done.txt): "fenetre 001
  <real seconds> <simulated seconds>";
- rsl.error.0000 of wrf/: "Timing for main: time 2025-10-01_03:00:00 on domain 1: ..." gives the
  instant reached by the window being computed;
- plan_fenetres.csv (window_plan.csv): the windows in their order of computation.

The time left is the simulated time left times the pace measured: real time per simulated second
of the windows done, or of the window being computed since its wrf.exe started.
"""

import csv
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from owstudio.core.method.scripts import FILE_NAMES

# Without a change in the journal or in rsl.error.0000 for this long, the calculation has stopped
ACTIVE_S = 15 * 60

_STAMP = re.compile(r"^\[(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d) UTC\]\s*(.*)$")
_PROGRAM = re.compile(r"^>\s+(\S+?)(?:\.exe)?\.\.\.$")
_TIMING = re.compile(r"Timing for main: time (\d{4}-\d\d-\d\d_\d\d:\d\d:\d\d) on domain\s+1:")
_DATA_LINE = re.compile(r'^"(\d{4}) \S+ (\S+)"$')
_DATA_DIR = re.compile(r"^(?:DOSSIER_DONNEES|DATA_DIR)\s*=\s*['\"]?([^'\"\s#]+)")
_ERA5_TARGET = re.compile(r'"target": "(era5/[^"]+)"')


def _names(key: str) -> list[str]:
    return sorted({names[key] for names in FILE_NAMES.values()})


def _first(folder: Path, *parts: list[str]) -> Path | None:
    """The first existing path among the names of both languages."""
    candidates = [folder]
    for names in parts:
        candidates = [c / n for c in candidates for n in names]
    return next((c for c in candidates if c.exists()), None)


def _instant(text: str) -> datetime:
    return datetime.strptime(text.replace("_", " "), "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)


def _tail(path: Path, size: int = 64_000) -> list[str]:
    with path.open("rb") as stream:
        stream.seek(max(0, path.stat().st_size - size))
        return stream.read().decode("utf-8", errors="replace").splitlines()


def _windows(folder: Path) -> list[dict[str, Any]]:
    """The windows of the plan in their order of computation."""
    plan = _first(folder, _names("plan"))
    if plan is None:
        return []
    with plan.open(encoding="utf-8") as stream:
        rows = list(csv.reader(stream))[1:]
    windows = [
        {
            "id": r[0],
            "order": int(r[1]),
            "start": _instant(r[3]),
            "end": _instant(r[4]),
            "seconds": int(r[9]),
        }
        for r in rows
        if len(r) > 9
    ]
    return sorted(windows, key=lambda w: w["order"])


def _download(folder: Path) -> dict[str, Any] | None:
    """Files of the input data present and expected: those its download script lists (GFS) or
    requests (ERA5), in the shared folder it names, or else in the package's data folder."""
    data = _first(folder, _names("data"))
    if data is None:
        return None
    script = _first(data, _names("download_gfs")) or _first(data, _names("download_era5"))
    if script is None:
        return {"done": 0, "expected": 0, "partial": False, "changed": 0.0}
    text = script.read_text(encoding="utf-8")
    base = data
    expected: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if match := _DATA_DIR.match(line):
            base = (
                data / match.group(1)
                if not match.group(1).startswith("/")
                else Path(match.group(1))
            )
        elif match := _DATA_LINE.match(line):
            expected.append(f"gfs/{match.group(1)}/{match.group(2)}")
    expected += _ERA5_TARGET.findall(text)
    done, partial, latest = 0, False, 0.0
    for name in expected:
        whole, part = base / name, base / f"{name}.part"
        if whole.is_file():
            done += 1
            latest = max(latest, whole.stat().st_mtime)
        elif part.is_file():
            partial = True
            latest = max(latest, part.stat().st_mtime)
    return {"done": done, "expected": len(expected), "partial": partial, "changed": latest}


def progress(folder: Path, now: float | None = None) -> dict[str, Any]:
    """State of the calculation of an extracted folder: step, window n/N, instant reached in the
    window, time left; "none" when nothing was run yet."""
    now = time.time() if now is None else now
    windows = _windows(folder)
    wrf = folder / "wrf"
    state_file = _first(wrf, _names("logs"), _names("state"))
    done_lines = state_file.read_text(encoding="utf-8").split("\n") if state_file else []
    done = {}
    for line in done_lines:
        parts = line.split()
        if len(parts) == 4 and parts[0] in ("fenetre", "window"):
            done[parts[1]] = (int(parts[2]), int(parts[3]))
    journal = _first(folder, _names("run_log"))
    lines = _tail(journal) if journal else []
    rsl = wrf / "rsl.error.0000"
    download = _download(folder)

    changes = [
        p.stat().st_mtime for p in (journal, rsl, state_file) if p is not None and p.exists()
    ]
    if download:
        changes.append(download["changed"])
    last_change = max(changes, default=0.0)
    active = now - last_change < ACTIVE_S

    # The last step of the journal, and when the current wrf.exe started
    step = ""
    error = ""
    wrf_started: datetime | None = None
    for line in lines:
        found = _STAMP.match(line)
        if not found:
            continue
        stamp, text = found.groups()
        text = text.strip()
        if text.startswith(("ERREUR :", "ERROR:")):
            error = text.split(":", 1)[1].strip()
            continue
        program = _PROGRAM.match(text)
        if program:
            step = program.group(1)
            error = ""
            if step == "wrf":
                wrf_started = _instant(stamp)

    total = len(windows)
    finished = total > 0 and all(w["id"] in done for w in windows)
    current = next((w for w in windows if w["id"] not in done), None)
    reached: datetime | None = None
    if current and rsl.exists() and step in ("", "wrf"):
        for line in reversed(_tail(rsl)):
            timing = _TIMING.search(line)
            if timing:
                reached = _instant(timing.group(1))
                break
        if reached and not current["start"] <= reached <= current["end"]:
            reached = None
        if reached:
            step = "wrf"

    if step == "" and download and (download["partial"] or download["done"] < download["expected"]):
        step = "download"
    elif step == "" and done:
        step = "wrf"

    # Pace: real seconds per simulated second, of the windows done, else of this window
    pace = None
    if done:
        pace = sum(r for r, _ in done.values()) / max(1, sum(s for _, s in done.values()))
    elif current and reached and wrf_started:
        simulated = (reached - current["start"]).total_seconds()
        if simulated > 0:
            pace = (last_change - wrf_started.timestamp()) / simulated
    left = None
    if pace is not None and current:
        remaining = sum(w["seconds"] for w in windows if w["id"] not in done)
        if reached:
            remaining -= (reached - current["start"]).total_seconds()
        left = max(0.0, remaining * pace)

    if finished:
        state = "done"
    elif error:
        state = "error"
    elif not (lines or done or reached or (download and download["done"])):
        state = "none"
    else:
        state = "running" if active else "stopped"
    return {
        "state": state,
        "step": step,
        "error": error,
        "window": (windows.index(current) + 1) if current else total,
        "windows": total,
        "done": len(done),
        "start": current["start"].isoformat() if current else None,
        "end": current["end"].isoformat() if current else None,
        "reached": reached.isoformat() if reached else None,
        "left_s": None if finished or error or left is None else round(left),
        "download": download and {"done": download["done"], "expected": download["expected"]},
        "changed": last_change or None,
    }
