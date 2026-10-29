"""The runs of a project: each one a folder with its record (run.json) and its outputs.

The application does not launch WRF itself: the exported scripts run on a cluster or a
Linux computer, and their outputs come back through the import (api/routes_import.py), which
stores them as a run. This module reads and writes those records; the results, energy, explorer,
videos and comparisons read the runs it lists.
"""

import threading
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from owstudio.core.i18n import tr
from owstudio.core.storage import RunPaths, Storage

State = Literal["idle", "queued", "running", "succeeded", "failed", "cancelled"]


class RunStatus(BaseModel):
    """The record of a run (run.json). Runs launched by older versions, which ran WRF
    themselves, have more fields filled in (profile, engine...): their records still load."""

    run_id: str | None = None
    state: State = "idle"
    # "main" for the case itself, "control" for the same case without turbines
    stage: Literal["main", "control"] = "main"
    with_control: bool = False
    profile: str | None = None
    profile_name: str | None = None
    mpi_ranks: int | None = None
    step: str | None = None
    fraction: float = 0.0
    model_time: datetime | None = None
    seconds_per_step: float | None = None
    queued_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None
    engine: dict[str, Any] = Field(default_factory=dict)
    label: str = ""
    tags: dict[str, str] = Field(default_factory=dict)
    farms: list[str] = Field(default_factory=list)
    fingerprint: str = ""


class Runs:
    """The records of the runs, in the data folder."""

    def __init__(self, storage: Any) -> None:
        # A callable giving the current Storage (the data folder can move)
        self._storage = storage
        self._lock = threading.Lock()
        # Imports being written now, as (project, run)
        self._writing: set[tuple[str, str]] = set()

    @property
    def storage(self) -> Storage:
        found: Storage = self._storage()
        return found

    def runs(self, case_id: str) -> list[RunStatus]:
        """The runs of a project, the latest first."""
        return [self.status(case_id, run_id) for run_id in reversed(self.storage.run_ids(case_id))]

    def latest(self, case_id: str) -> RunStatus:
        ids = self.storage.run_ids(case_id)
        return self.status(case_id, ids[-1]) if ids else RunStatus()

    def status(self, case_id: str, run_id: str) -> RunStatus:
        paths = self.storage.run(case_id, run_id)
        with self._lock:
            if not paths.status.exists():
                return RunStatus(run_id=run_id)
            return RunStatus.model_validate_json(paths.status.read_text(encoding="utf-8"))

    def save(self, paths: RunPaths, status: RunStatus) -> None:
        temporary = paths.status.with_suffix(".tmp")
        with self._lock:
            # Replace in one step so a crash never leaves a half-written file
            temporary.write_text(status.model_dump_json(indent=2), encoding="utf-8")
            temporary.replace(paths.status)

    def writing(self, case_id: str, run_id: str, active: bool) -> None:
        """Marks an import of outputs as being written into this run, or as finished."""
        with self._lock:
            (self._writing.add if active else self._writing.discard)((case_id, run_id))

    def is_running(self, case_id: str, run_id: str | None = None) -> bool:
        """Outputs are being imported into this project (or this run) right now."""
        with self._lock:
            return any(case == case_id and run_id in (None, run) for case, run in self._writing)

    def close_interrupted(self) -> list[str]:
        """Records left running when the application stopped become failed, so that nothing waits
        for them: an import cut short, or a run launched by an older version, which nothing
        follows any more."""
        closed = []
        for case_dir in sorted(self.storage.cases.glob("*")) if self.storage.cases.is_dir() else []:
            for run_id in self.storage.run_ids(case_dir.name):
                status = self.status(case_dir.name, run_id)
                if status.state in ("queued", "running"):
                    status.state = "failed"
                    status.finished_at = status.finished_at or datetime.now(UTC)
                    status.error = (
                        tr(
                            "The import was interrupted: import the files again",
                            "L'import a été interrompu : importez à nouveau les fichiers",
                        )
                        if status.step == "import"
                        else tr(
                            "No longer followed: the application no longer runs simulations",
                            "Plus suivi : le logiciel ne lance plus de simulations",
                        )
                    )
                    self.save(self.storage.run(case_dir.name, run_id), status)
                    closed.append(f"{case_dir.name}/{run_id}")
        return closed
