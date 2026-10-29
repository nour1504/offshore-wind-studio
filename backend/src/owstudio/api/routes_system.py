"""Settings, compute profiles, storage, background jobs and the help pages."""

import shutil
import subprocess
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from owstudio import __version__
from owstudio.api.routes_cases import state
from owstudio.core import docs
from owstudio.core.data import era5
from owstudio.core.engine import commands
from owstudio.core.engine.profiles import ComputeProfile, seen_here, wsl_profile_template
from owstudio.core.engine.shells import list_wsl_distributions, shell_for
from owstudio.core.i18n import tr
from owstudio.core.settings import Folders, physical_cores
from owstudio.core.storage import Storage, folder_size, free_space

router = APIRouter()


def platform_name() -> str:
    """windows, linux, or Python's own name for other systems."""
    if sys.platform == "win32":
        return "windows"
    return "linux" if sys.platform.startswith("linux") else sys.platform


@router.get("/api/health")
def health(request: Request) -> dict[str, Any]:
    settings = state(request).settings
    return {
        "status": "ok",
        "version": __version__,
        "profiles": len(settings.profiles),
        "default_profile": settings.default_profile,
        "engine_ready": bool(settings.profiles),
        "platform": platform_name(),
        "mode": state(request).mode,
    }


@router.post("/api/system/heartbeat")
def heartbeat(request: Request) -> dict[str, bool]:
    """A page of the interface is open (browser mode stops the server once none is left)."""
    app = state(request)
    app.last_seen = time.monotonic()
    return {"busy": app.busy()}


@router.post("/api/system/quit")
def quit_application(request: Request) -> dict[str, bool]:
    """Browser mode only: stops the local server, unless a background job is running."""
    app = state(request)
    if app.mode != "browser":
        raise HTTPException(
            409,
            tr(
                "Only the browser mode is closed from the interface",
                "Seul le mode navigateur se ferme depuis l'interface",
            ),
        )
    if app.busy():
        raise HTTPException(
            409,
            tr(
                "A background job is still running",
                "Une tâche est encore en cours",
            ),
        )
    app.quit_requested.set()
    return {"quitting": True}


# ---------------------------------------------------------------- settings


class SettingsPatch(BaseModel):
    language: Literal["en", "fr"] | None = None
    default_profile: str | None = None


@router.get("/api/settings")
def get_settings(request: Request) -> dict[str, Any]:
    settings = state(request).settings
    return {
        **settings.model_dump(exclude={"profiles"}),
        "cds_key_configured": era5.has_api_key(),
        "cds_url": era5.CDS_URL,
        "physical_cores": physical_cores(),
    }


@router.patch("/api/settings")
def patch_settings(request: Request, patch: SettingsPatch) -> dict[str, Any]:
    app = state(request)
    settings = app.settings.model_copy(update=patch.model_dump(exclude_none=True))
    if patch.default_profile:
        try:
            settings.profile(patch.default_profile)
        except KeyError as error:
            raise HTTPException(422, str(error)) from error
    app.save_settings(settings)
    return get_settings(request)


class CdsKey(BaseModel):
    key: str


@router.put("/api/settings/cds-key", status_code=204)
def set_cds_key(body: CdsKey) -> None:
    # The key is typed by the user in the interface and stored where the CDS client reads it
    try:
        era5.save_api_key(body.key)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


# --------------------------------------------------------- compute profiles


@router.get("/api/profiles")
def profiles(request: Request) -> dict[str, Any]:
    settings = state(request).settings
    return {
        "profiles": [
            {**p.model_dump(), "missing": p.missing(), "default": p.id == settings.default_profile}
            for p in settings.profiles
        ],
        "physical_cores": physical_cores(),
    }


@router.get("/api/profiles/suggestions")
def profile_suggestions() -> dict[str, Any]:
    """Starting points: the installed WSL distributions."""
    suggestions = []
    for distro in list_wsl_distributions() if sys.platform == "win32" else []:
        home = (
            subprocess.run(
                ["wsl.exe", "-d", distro, "--exec", "bash", "-lc", "echo $HOME"],
                capture_output=True,
                text=True,
                check=False,
            ).stdout.strip()
            or "/root"
        )
        suggestions.append(wsl_profile_template(distro, home).model_dump())
    return {"suggestions": suggestions}


@router.put("/api/profiles/{profile_id}")
def save_profile(request: Request, profile_id: str, profile: ComputeProfile) -> dict[str, Any]:
    """Saves a profile; it does not need to be reachable yet."""
    app = state(request)
    if profile.id != profile_id:
        raise HTTPException(
            422,
            tr(
                "The profile identifier cannot change",
                "L'identifiant du profil ne peut pas changer",
            ),
        )
    settings = app.settings.model_copy(deep=True)
    settings.profiles = [p for p in settings.profiles if p.id != profile_id] + [profile]
    settings.profiles.sort(key=lambda p: p.name.lower())
    settings.default_profile = settings.default_profile or profile.id
    app.save_settings(settings)
    return profiles(request)


@router.delete("/api/profiles/{profile_id}")
def delete_profile(request: Request, profile_id: str) -> dict[str, Any]:
    app = state(request)
    settings = app.settings.model_copy(deep=True)
    settings.profiles = [p for p in settings.profiles if p.id != profile_id]
    if settings.default_profile == profile_id:
        settings.default_profile = settings.profiles[0].id if settings.profiles else None
    app.save_settings(settings)
    return profiles(request)


@router.post("/api/profiles/verify")
def verify_profile(profile: ComputeProfile) -> dict[str, Any]:
    """Connects to the engine and checks the installation, without saving the profile."""
    label = tr("Profile", "Profil")
    missing = profile.missing()
    if missing:
        return {
            "reachable": False,
            "checks": [{"status": "fail", "label": label, "detail": m} for m in missing],
        }
    try:
        shell = shell_for(profile)
    except ValueError as error:
        return {
            "reachable": False,
            "checks": [{"status": "fail", "label": label, "detail": str(error)}],
        }
    result = shell.run(commands.verify_script(profile), timeout=180)
    checks = commands.parse_verify(result.stdout)
    if not checks:
        detail = (result.stderr or result.stdout or tr("no answer", "pas de réponse")).strip()
        return {
            "reachable": False,
            "checks": [
                {"status": "fail", "label": tr("Connection", "Connexion"), "detail": detail[-1500:]}
            ],
        }
    return {"reachable": True, "checks": checks}


# ----------------------------------------------------------------- storage


@router.get("/api/storage")
def storage_usage(request: Request) -> dict[str, Any]:
    app = state(request)
    storage = app.storage
    locations = [{**loc, "bytes": folder_size(Path(loc["path"]))} for loc in storage.locations()]
    runs = []
    for case_dir in sorted(storage.cases.glob("*")) if storage.cases.exists() else []:
        for run_id in storage.run_ids(case_dir.name):
            paths = storage.run(case_dir.name, run_id)
            runs.append(
                {
                    "case": case_dir.name,
                    "run": run_id,
                    "path": str(paths.root),
                    "bytes": folder_size(paths.root),
                    "outputs_bytes": folder_size(paths.root / "outputs"),
                    "state": app.runs.status(case_dir.name, run_id).state,
                }
            )
    return {
        "data_root": str(storage.root),
        "downloads_root": str(downloads_root(app)),
        "free_bytes": free_space(storage.root),
        "folders": app.settings.folders.model_dump(),
        "locations": locations,
        "runs": runs,
        "settings_file": str(app.settings_path),
    }


def downloads_root(app: Any) -> Path:
    """Where the downloaded input data are (gfs/, era5/, sst/): the shared data folder of the
    default engine when this computer sees it (the one its scripts download into), else the
    application's own input folder."""
    own: Path = app.storage.input_root
    try:
        profile = app.settings.profile(None)
    except KeyError:
        return own
    folder = seen_here(profile, profile.install.input_dir)
    return folder if folder is not None else own


class DataRoot(BaseModel):
    path: str
    # Move the existing projects and data to the new folder
    move: bool = True


@router.put("/api/storage/data-root")
def set_data_root(request: Request, body: DataRoot) -> dict[str, Any]:
    app = state(request)
    if app.busy():
        raise HTTPException(
            409,
            tr(
                "Wait for the background jobs to finish before moving the data",
                "Attendez la fin des tâches en cours avant de déplacer les données",
            ),
        )
    target = Path(body.path).expanduser()
    if not target.is_absolute():
        raise HTTPException(
            422,
            tr(
                "Give a full path, for example D:\\WRF-data",
                "Indiquez un chemin complet, par exemple D:\\Donnees-WRF",
            ),
        )
    _writable(target)
    old = app.storage
    if body.move and old.root.resolve() != target.resolve():
        new = Storage(target)
        for name in ("cases", "cache", "input", "observations", "exports", "videos", "reports"):
            source = old.root / name
            if source.exists():
                destination = new.root / name
                if destination.exists() and any(destination.iterdir()):
                    raise HTTPException(
                        409,
                        tr(
                            f"{destination} already contains data: choose an empty folder or do not move",
                            f"{destination} contient déjà des données : choisissez un dossier vide ou ne déplacez pas",
                        ),
                    )
                shutil.move(str(source), str(destination))
    app.save_settings(app.settings.model_copy(update={"data_root": str(target)}))
    return storage_usage(request)


@router.put("/api/storage/folders")
def set_folders(request: Request, folders: Folders) -> dict[str, Any]:
    app = state(request)
    for value in folders.model_dump().values():
        if value:
            _writable(Path(value).expanduser())
    app.save_settings(app.settings.model_copy(update={"folders": folders}))
    return storage_usage(request)


def _writable(folder: Path) -> None:
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / ".owstudio-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as error:
        raise HTTPException(
            422,
            tr(
                f"Cannot write in {folder}: {error}", f"Impossible d'écrire dans {folder} : {error}"
            ),
        ) from error


class Cleanup(BaseModel):
    # Runs to delete entirely ("case/run"), runs whose generated and log files are deleted but
    # results kept, and input folders to empty
    runs: list[str] = []
    intermediates: list[str] = []
    inputs: list[Literal["gfs", "era5", "sst"]] = []


@router.post("/api/storage/cleanup")
def cleanup(request: Request, body: Cleanup) -> dict[str, Any]:
    """Deletes what the user selected after confirming it; never touches the engines."""
    app = state(request)
    done: list[str] = []
    if any(job.state == "running" for job in app.jobs.jobs.values()):
        raise HTTPException(
            409,
            tr(
                "Wait for background imports and exports before cleaning storage",
                "Attendez la fin des imports et exports en cours avant de libérer de la place",
            ),
        )

    def run_root(item: str) -> Path:
        case_id, _, run_id = item.partition("/")
        app.workspace.load(case_id)
        if app.runs.is_running(case_id, run_id):
            raise HTTPException(
                409, tr(f"{item} is being imported", f"{item} est en cours d'import")
            )
        try:
            return app.storage.run(case_id, run_id).root
        except KeyError as error:
            raise HTTPException(
                422, tr(f"Unknown run {item}", f"Calcul inconnu : {item}")
            ) from error

    # Validate every selection before the first deletion; a later invalid selection must not
    # leave the earlier selections deleted despite the request reporting a failure.
    selected = {item: run_root(item) for item in set(body.runs + body.intermediates)}
    for item in body.runs:
        root = selected[item]
        if root.exists():
            shutil.rmtree(root)
            done.append(item)
    for item in body.intermediates:
        root = selected[item]
        for name in ("generated", "generated-control"):
            if (root / name).exists():
                shutil.rmtree(root / name)
        done.append(f"{item} (intermediate files)")
    for source in body.inputs:
        folder = downloads_root(app) / source
        if folder.exists():
            shutil.rmtree(folder)
            folder.mkdir(parents=True)
            done.append(str(folder))
    return {"done": done, **storage_usage(request)}


# -------------------------------------------------------------------- jobs


@router.get("/api/jobs/{job_id}")
def job_status(request: Request, job_id: str) -> dict[str, Any]:
    job = state(request).jobs.jobs.get(job_id)
    if job is None:
        raise HTTPException(404, tr("Unknown job", "Tâche inconnue"))
    text = job.log.read_text(encoding="utf-8", errors="replace") if job.log.exists() else ""
    return {
        "id": job.id, "title": job.title, "state": job.state, "error": job.error, "progress": job.progress,
        "started_at": job.started_at, "finished_at": job.finished_at, "log": text[-20000:], "result": job.result,
    }  # fmt: skip


@router.post("/api/jobs/{job_id}/cancel")
def cancel_job(request: Request, job_id: str) -> dict[str, bool]:
    job = state(request).jobs.jobs.get(job_id)
    if job is None:
        raise HTTPException(404, tr("Unknown job", "Tâche inconnue"))
    job.cancelled.set()
    return {"cancelled": True}


# -------------------------------------------------------------------- help

Lang = Literal["en", "fr"]


def _summary(topic: docs.Topic) -> dict[str, Any]:
    return {
        "id": topic.id,
        "title": topic.title,
        "section": topic.section,
        "summary": topic.summary,
    }


@router.get("/api/docs")
def docs_index(lang: Lang = "en") -> dict[str, Any]:
    return {"topics": [_summary(t) for t in docs.index(lang)]}


@router.get("/api/docs/search")
def docs_search(q: str, lang: Lang = "en") -> dict[str, Any]:
    return {"results": [asdict(hit) for hit in docs.search(q, lang)]}


@router.get("/api/docs/{topic_id}")
def docs_page(topic_id: str, lang: Lang = "en") -> dict[str, Any]:
    try:
        topic = docs.get(topic_id, lang)
    except KeyError as error:
        raise HTTPException(
            404, tr(f"No help topic {topic_id!r}", f"Aucune page d'aide {topic_id!r}")
        ) from error
    known = docs.topics(lang)
    return {
        **_summary(topic),
        "lang": topic.lang,
        "markdown": topic.markdown,
        "related": [{"id": r, "title": known[r].title} for r in topic.related if r in known],
    }
