"""State shared by the API routes: settings, storage, projects, runs and background jobs."""

import contextvars
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from owstudio.api.runs import Runs
from owstudio.core import i18n
from owstudio.core.case.workspace import Workspace
from owstudio.core.settings import SETTINGS_FILE, Settings, load_settings, save_settings
from owstudio.core.storage import Storage


@dataclass
class Job:
    """A long operation running in the background: video rendering, report, large import..."""

    id: str
    title: str
    log: Path
    state: str = "running"
    progress: float = 0.0
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    error: str | None = None
    result: Any = None
    cancelled: threading.Event = field(default_factory=threading.Event)

    def write(self, line: str) -> None:
        with self.log.open("a", encoding="utf-8") as out:
            out.write(line.rstrip("\n") + "\n")


class JobManager:
    def __init__(self, log_dir: Callable[[], Path]) -> None:
        self.log_dir = log_dir
        self.jobs: dict[str, Job] = {}

    def start(self, title: str, work: Callable[[Job], Any]) -> Job:
        """Runs ``work(job)`` in a thread; its return value becomes the job result."""
        folder = self.log_dir()
        folder.mkdir(parents=True, exist_ok=True)
        job = Job(uuid.uuid4().hex[:12], title, folder / f"{uuid.uuid4().hex[:12]}.log")
        job.log.write_text(f"{title}\n", encoding="utf-8")
        self.jobs[job.id] = job

        def target() -> None:
            try:
                job.result = work(job)
                job.state = "cancelled" if job.cancelled.is_set() else "succeeded"
                job.progress = 1.0 if job.state == "succeeded" else job.progress
            except Exception as error:  # noqa: BLE001 - shown to the user
                job.state = "cancelled" if job.cancelled.is_set() else "failed"
                job.error = str(error) or repr(error)
                job.write(f"Error: {job.error}")
            job.finished_at = datetime.now(UTC)

        # The job speaks the language of the window that started it
        threading.Thread(target=contextvars.copy_context().run, args=(target,), daemon=True).start()
        return job


class AppState:
    def __init__(
        self,
        settings_path: Path = SETTINGS_FILE,
        static_dir: Path | None = None,
    ) -> None:
        self.settings_path = settings_path
        self._settings = load_settings(settings_path)
        i18n.set_default(self._settings.language)
        self.static_dir = static_dir
        self.storage.ensure()
        self.storage.migrate_legacy()
        self.runs = Runs(lambda: self.storage)
        self.runs.close_interrupted()
        self.jobs = JobManager(lambda: self.storage.jobs)
        # How the interface is shown: "window" (own window), "browser" (Linux without a
        # window toolkit: the default browser, closed by the user) or "server" (owstudio serve)
        self.mode = "server"
        # Browser mode: when a page last said it is open, and whether the user asked to quit
        self.last_seen: float | None = None
        self.quit_requested = threading.Event()

    def busy(self) -> bool:
        """A background job (import, video, report, installation) is running: the server stays."""
        return any(job.state == "running" for job in self.jobs.jobs.values())

    @property
    def settings(self) -> Settings:
        return self._settings

    def save_settings(self, settings: Settings) -> None:
        save_settings(settings, self.settings_path)
        self._settings = settings
        i18n.set_default(settings.language)
        self.storage.ensure()

    @property
    def storage(self) -> Storage:
        return Storage(self._settings.data_path, self._settings.folders)

    @property
    def workspace(self) -> Workspace:
        return Workspace(self._settings.data_path)
