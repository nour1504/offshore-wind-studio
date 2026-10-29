"""Layout of the data folder, so that projects and runs never overwrite each other.

    <data folder>/
      cases/<case>/case.yaml              the project's case
      cases/<case>/runs/<run>/            one folder per run, named by its start time (UTC)
          run.json                        status, progress and engine details
          case.yaml                       the case exactly as it ran
          generated/                      files sent to WPS and WRF
          logs/                           WPS and WRF logs
          outputs/main/, outputs/control/ history files and time series
          outputs/reference.json          the run without turbines chosen for this one
      cases/<case>/imports/<name>/        results imported from elsewhere
      input/<source>/                     input data shared by every case (GFS, ERA5, SST...)
      observations/                       measured data and saved import mappings
      exports/                            extracted series and tables
      videos/                             rendered animations
      reports/                            PDF reports
      jobs/                               logs of background tasks

Input, observation, export, video and report folders can be moved elsewhere in the settings.
Sources such as imported files are copied, never modified.
"""

import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RUN_ID = re.compile(r"^\d{8}-\d{6}(-\d+)?$")
# The run without turbines compared with a run: another run of any project, chosen on the pages
# of results, or none; without this file, the one imported with the run (outputs/control)
REFERENCE_FILE = "reference.json"


def stage_folder(root: Path, stage: str) -> Path:
    """Outputs of a run folder: "main", or "control", the run without turbines it is compared
    with."""
    if stage == "control":
        chosen = reference_choice(root)
        if chosen is not None:
            path = chosen.get("path")
            if chosen.get("none") or not isinstance(path, str):
                return root / "outputs" / "none"
            return (root / path).resolve()
    return root / "outputs" / stage


def outputs_stamp(root: Path) -> tuple[str, float, float]:
    """The run folder, the date its outputs were imported and the date of its reference choice:
    a new import or another run without turbines is a new key for what is computed from them."""
    chosen = root / "outputs" / REFERENCE_FILE
    return (
        str(root),
        (root / "outputs" / "main" / "case.yaml").stat().st_mtime,
        chosen.stat().st_mtime if chosen.exists() else 0.0,
    )


def reference_choice(root: Path) -> dict[str, Any] | None:
    """The choice saved in outputs/reference.json, or None when nothing was chosen."""
    chosen = root / "outputs" / REFERENCE_FILE
    if not chosen.is_file():
        return None
    try:
        data = json.loads(chosen.read_text(encoding="utf-8"))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def new_run_id(existing: set[str], now: datetime | None = None) -> str:
    """Start time in UTC, with a suffix if two runs start in the same second."""
    base = (now or datetime.now(UTC)).strftime("%Y%m%d-%H%M%S")
    run_id, n = base, 2
    while run_id in existing:
        run_id, n = f"{base}-{n}", n + 1
    return run_id


@dataclass(frozen=True)
class RunPaths:
    root: Path

    @property
    def id(self) -> str:
        return self.root.name

    @property
    def status(self) -> Path:
        return self.root / "run.json"

    @property
    def case_snapshot(self) -> Path:
        return self.root / "case.yaml"

    def generated(self, control: bool = False) -> Path:
        return self.root / ("generated-control" if control else "generated")

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    def outputs(self, run: str = "main") -> Path:
        return stage_folder(self.root, run)


@dataclass(frozen=True)
class Storage:
    root: Path
    folders: Any = field(default=None)

    def _folder(self, name: str) -> Path:
        override = getattr(self.folders, name, "") if self.folders is not None else ""
        return Path(override).expanduser() if override else self.root / name

    @property
    def cases(self) -> Path:
        return self.root / "cases"

    @property
    def input_root(self) -> Path:
        # The map cache (base maps, relief, 3D scenes); the setting keeps its name "input"
        override = getattr(self.folders, "input", "") if self.folders is not None else ""
        return Path(override).expanduser() if override else self.root / "cache"

    def input(self, source: str) -> Path:
        return self.input_root / source

    @property
    def observations(self) -> Path:
        return self._folder("observations")

    @property
    def exports(self) -> Path:
        return self._folder("exports")

    @property
    def videos(self) -> Path:
        return self._folder("videos")

    @property
    def reports(self) -> Path:
        return self._folder("reports")

    @property
    def jobs(self) -> Path:
        return self.root / "jobs"

    def case(self, case_id: str) -> Path:
        return self.cases / case_id

    def runs(self, case_id: str) -> Path:
        return self.case(case_id) / "runs"

    def run(self, case_id: str, run_id: str) -> RunPaths:
        if not RUN_ID.match(run_id):
            raise KeyError(run_id)
        return RunPaths(self.runs(case_id) / run_id)

    def run_ids(self, case_id: str) -> list[str]:
        folder = self.runs(case_id)
        if not folder.exists():
            return []
        return sorted(p.name for p in folder.iterdir() if p.is_dir() and RUN_ID.match(p.name))

    def create_run(self, case_id: str) -> RunPaths:
        run_id = new_run_id(set(self.run_ids(case_id)))
        paths = RunPaths(self.runs(case_id) / run_id)
        paths.root.mkdir(parents=True)
        return paths

    def ensure(self) -> None:
        # The map cache was the "input" folder: renamed once, its content kept
        old = self.root / "input"
        if self.input_root == self.root / "cache" and old.is_dir() and not self.input_root.exists():
            old.rename(self.input_root)
        for folder in (
            self.cases,
            self.input_root,
            self.observations,
            self.exports,
            self.videos,
            self.reports,
            self.jobs,
        ):
            folder.mkdir(parents=True, exist_ok=True)

    def locations(self) -> list[dict[str, str]]:
        """Every folder the application writes to, for the Storage page."""
        return [
            {"key": "cases", "label": "Projects, runs and results", "path": str(self.cases)},
            {
                "key": "input",
                "label": "Map cache (base maps, relief, 3D scenes)",
                "path": str(self.input_root),
            },
            {
                "key": "observations",
                "label": "Observations and import mappings",
                "path": str(self.observations),
            },
            {"key": "exports", "label": "Extracted data", "path": str(self.exports)},
            {"key": "videos", "label": "Animations", "path": str(self.videos)},
            {"key": "reports", "label": "Reports", "path": str(self.reports)},
            {"key": "jobs", "label": "Background task logs", "path": str(self.jobs)},
        ]

    def migrate_legacy(self) -> list[str]:
        """Moves results of the first layout (cases/<case>/outputs and run.json) into a run."""
        moved = []
        for case_dir in sorted(self.cases.glob("*")) if self.cases.exists() else []:
            outputs, status = case_dir / "outputs", case_dir / "run.json"
            if not outputs.exists() and not status.exists():
                continue
            stamp = datetime.fromtimestamp(
                (outputs if outputs.exists() else status).stat().st_mtime, UTC
            )
            target = RunPaths(
                case_dir / "runs" / new_run_id(set(self.run_ids(case_dir.name)), stamp)
            )
            target.root.mkdir(parents=True)
            if outputs.exists():
                shutil.move(str(outputs), str(target.root / "outputs"))
                snapshot = target.outputs("main") / "case.yaml"
                if snapshot.exists():
                    shutil.copy2(snapshot, target.case_snapshot)
            if status.exists():
                shutil.move(str(status), str(target.status))
            for leftover in ("generated", "generated-control"):
                if (case_dir / leftover).exists():
                    shutil.move(str(case_dir / leftover), str(target.root / leftover))
            moved.append(f"{case_dir.name}/{target.id}")
        return moved


def folder_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def free_space(path: Path) -> int:
    existing = path
    while not existing.exists() and existing.parent != existing:
        existing = existing.parent
    return shutil.disk_usage(existing).free
