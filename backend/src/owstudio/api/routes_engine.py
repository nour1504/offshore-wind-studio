"""Engine installation: catalogue, kit, local WSL preparation, checks, installation, follow-up,
resumption, cancellation and verification. Every action is an explicit request."""

import sys
import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from owstudio.api.routes_cases import state
from owstudio.api.routes_system import profiles
from owstudio.api.state import AppState, Job
from owstudio.core.engine import install, local_setup
from owstudio.core.engine.profiles import ComputeProfile, without_removed_fields
from owstudio.core.engine.shells import LocalShell, WslShell
from owstudio.core.i18n import tr

router = APIRouter()


@router.get("/api/engine/catalog")
def engine_catalog(request: Request) -> dict[str, Any]:
    """The engine the application installs: versions, dependencies, geography and complements."""
    value = install.catalog()
    value["local_folder"] = str(Path(state(request).settings.data_root).expanduser() / "engine-wsl")
    value["host_platform"] = sys.platform
    value["native_root"] = str(Path.home() / "OffshoreWindStudioEngine" / value["id"])
    return value


@router.get("/api/engine/kit")
def engine_kit(request: Request) -> FileResponse:
    """The small kit for a manual installation (recipe and helpers, no binary, no data)."""
    app = state(request)
    path = app.storage.exports / f"OffshoreWindStudio-engine-{install.spec()['id']}.zip"
    install.export_kit(path)
    return FileResponse(path, media_type="application/zip", filename=path.name)


@router.get("/api/engine/wsl")
def wsl_status() -> dict[str, Any]:
    return local_setup.status()


class WslSetup(BaseModel):
    folder: str


def _running(app: AppState, title: str) -> Job | None:
    return next(
        (j for j in app.jobs.jobs.values() if j.state == "running" and j.title == title), None
    )


@router.post("/api/engine/wsl/prepare", status_code=202)
def prepare_wsl(request: Request, body: WslSetup) -> dict[str, str]:
    """Creates the dedicated local Linux (WSL) for the engine; may ask for administrator approval."""
    app = state(request)
    if _running(app, "Prepare local Linux"):
        raise HTTPException(
            409,
            tr(
                "The local Linux is already being prepared",
                "Le Linux local est déjà en préparation",
            ),
        )
    scratch = install.receipt_folder(app.settings_path) / f"wsl-{uuid.uuid4().hex[:12]}"
    job = app.jobs.start(
        "Prepare local Linux", lambda job: local_setup.prepare(Path(body.folder), scratch, job)
    )
    return {"job_id": job.id}


@router.post("/api/engine/preflight")
def engine_preflight(request: Request, body: install.InstallRequest) -> dict[str, Any]:
    """What the target offers: system, tools, space, network and the state of the folder."""
    try:
        return install.preflight(body, uploaded=install.uploaded(state(request).settings_path))
    except (RuntimeError, ValueError, OSError) as error:
        raise HTTPException(
            422,
            tr(
                f"The target could not be checked: {error}",
                f"La cible n'a pas pu être vérifiée : {error}",
            ),
        ) from error


# ----------------------------------------------------------------------------- geography


@router.get("/api/engine/geography/uploads")
def geography_uploads(request: Request) -> dict[str, int]:
    """The geography choices whose NCAR archive was sent from this computer, with its size."""
    return install.uploaded(state(request).settings_path)


@router.put("/api/engine/geography/{geography}")
async def upload_geography(request: Request, geography: str) -> dict[str, int]:
    """The NCAR archive of a geography, sent from the browser when the target cannot download it
    (a proxy answering 403). Kept until an installation sends it to its target."""
    try:
        name = install.archive_name(geography)
    except ValueError as error:
        raise HTTPException(404, str(error)) from error
    expected = next(
        int(c["download_bytes"]) for c in install.spec()["geography"] if c["id"] == geography
    )
    folder = install.uploads_folder(state(request).settings_path)
    folder.mkdir(parents=True, exist_ok=True)
    partial = folder / f"{name}.part"
    size = 0
    with partial.open("wb") as stream:
        async for chunk in request.stream():
            size += len(chunk)
            if size > expected:
                break
            stream.write(chunk)
    if size != expected:
        partial.unlink(missing_ok=True)
        raise HTTPException(
            422,
            tr(
                f"Not the NCAR archive {name}: {size} bytes instead of {expected}",
                f"Pas l'archive NCAR {name} : {size} octets au lieu de {expected}",
            ),
        )
    partial.replace(folder / name)
    return install.uploaded(state(request).settings_path)


class GeographySearch(BaseModel):
    target: Literal["wsl", "local"]


@router.post("/api/engine/geography/find")
def find_geography(body: GeographySearch) -> list[dict[str, Any]]:
    """WPS_GEOG folders already on the target (the dedicated WSL Linux, or this Linux computer):
    nothing to download when one is there."""
    if body.target == "wsl":
        status = local_setup.status()
        if not status.get("managed_exists"):
            return []
        shell = WslShell(status["managed_distro"], status["managed_user"])
    else:
        if sys.platform == "win32":
            return []
        shell = LocalShell()
    try:
        return install.find_geography(shell)
    except (OSError, RuntimeError):
        return []


@router.get("/api/engine/installations")
def installations(request: Request) -> list[dict[str, Any]]:
    app = state(request)
    receipts = install.list_receipts(install.receipt_folder(app.settings_path))
    for receipt in receipts:
        job = app.jobs.jobs.get(receipt.get("job_id") or "")
        receipt["followed"] = bool(job and job.state == "running")
    return receipts


def _register(app: AppState, profile: ComputeProfile) -> None:
    settings = app.settings.model_copy(deep=True)
    settings.profiles = [p for p in settings.profiles if p.id != profile.id] + [profile]
    settings.default_profile = settings.default_profile or profile.id
    app.save_settings(settings)


def _machine(profile: ComputeProfile) -> tuple[str, ...]:
    """The machine a profile reaches (two profiles may name the same one)."""
    if profile.kind == "wsl":
        return ("wsl", profile.wsl_distro.lower())
    return (profile.kind,)


def _start(app: AppState, body: install.InstallRequest) -> dict[str, str]:
    folder = install.receipt_folder(app.settings_path)
    machine = _machine(body.profile)
    for receipt in install.list_receipts(folder):
        same = (
            _machine(ComputeProfile.model_validate(without_removed_fields(receipt["profile"])))
            == machine
        )
        if same and receipt["state"] in install.ACTIVE_STATES:
            raise HTTPException(
                409,
                tr(
                    f"Installation {receipt['id']} is not finished on this machine: follow, resume or cancel it first",
                    f"L'installation {receipt['id']} n'est pas terminée sur cette machine : suivez-la, reprenez-la ou annulez-la d'abord",
                ),
            )
    for receipt in install.list_receipts(folder):
        if (
            receipt["profile"]["id"] == body.profile.id
            and receipt["state"] in install.ACTIVE_STATES
        ):
            raise HTTPException(
                409,
                tr(
                    f"Installation {receipt['id']} of this profile is not finished: follow, resume or cancel it first",
                    f"L'installation {receipt['id']} de ce profil n'est pas terminée : suivez-la, reprenez-la ou annulez-la d'abord",
                ),
            )
    try:
        old = app.settings.profile(body.profile.id)
    except KeyError:
        old = None
    if old and (old.kind != body.profile.kind or old.wsl_distro != body.profile.wsl_distro):
        raise HTTPException(
            409,
            tr(
                "This profile name already designates another machine: choose another name",
                "Ce nom de profil désigne déjà une autre machine : choisissez un autre nom",
            ),
        )

    # A geography archive sent from the browser goes with the installation that uses it
    archive = None
    if body.geography in install.uploaded(app.settings_path):
        archive = install.uploads_folder(app.settings_path) / install.archive_name(body.geography)

    def work(job: Job) -> dict[str, Any]:
        receipt = install.begin(body, folder, folder / "kits", job, archive=archive)
        return install.follow(receipt, folder, job, lambda profile: _register(app, profile))

    job = app.jobs.start("Install WRF/WPS engine", work)
    return {"job_id": job.id}


@router.post("/api/engine/install", status_code=202)
def install_engine(request: Request, body: install.InstallRequest) -> dict[str, str]:
    """Installs the engine on the target and configures the profile once it is verified."""
    return _start(state(request), body)


def _receipt(app: AppState, installation_id: str) -> dict[str, Any]:
    try:
        return install.read_receipt(install.receipt_folder(app.settings_path), installation_id)
    except (ValueError, FileNotFoundError) as error:
        raise HTTPException(404, str(error)) from error


@router.post("/api/engine/installations/{installation_id}/follow", status_code=202)
def follow_engine(request: Request, installation_id: str) -> dict[str, str]:
    """Reconnects to an installation still working on its target (after a restart, for example)."""
    app = state(request)
    folder = install.receipt_folder(app.settings_path)
    receipt = _receipt(app, installation_id)
    previous = app.jobs.jobs.get(receipt.get("job_id") or "")
    if previous and previous.state == "running":
        return {"job_id": previous.id}
    if receipt["state"] in ("succeeded", "cancelled", "resumed"):
        raise HTTPException(
            409,
            tr(
                f"This installation is {receipt['state']}",
                f"Cette installation est à l'état « {receipt['state']} »",
            ),
        )
    job = app.jobs.start(
        "Follow WRF/WPS installation",
        lambda job: install.follow(receipt, folder, job, lambda profile: _register(app, profile)),
    )
    receipt["job_id"] = job.id
    install.save_receipt(folder, receipt)
    return {"job_id": job.id}


class ResumeChanges(BaseModel):
    """Another geography for the resumption (the choice of the start is no longer imposed)."""

    geography: Literal["mandatory-high", "mandatory-low", "existing"] | None = None
    geog_path: str | None = None
    extras: list[str] | None = None


@router.post("/api/engine/installations/{installation_id}/resume", status_code=202)
def resume_engine(
    request: Request, installation_id: str, changes: ResumeChanges | None = None
) -> dict[str, str]:
    """Starts the same installation again; what was completed on the target is kept."""
    app = state(request)
    folder = install.receipt_folder(app.settings_path)
    receipt = _receipt(app, installation_id)
    job = app.jobs.jobs.get(receipt.get("job_id") or "")
    if job and job.state == "running":
        raise HTTPException(
            409,
            tr("This installation is still being followed", "Cette installation est encore suivie"),
        )
    if receipt["state"] not in ("failed", "cancelled", "monitor-interrupted"):
        raise HTTPException(
            409,
            tr(
                f"This installation is {receipt['state']}: nothing to resume",
                f"Cette installation est à l'état « {receipt['state']} » : rien à reprendre",
            ),
        )
    try:
        body = install.resume_request(receipt, changes.model_dump() if changes else None)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    receipt.update(state="resumed")
    install.save_receipt(folder, receipt)
    return _start(app, body)


@router.post("/api/engine/installations/{installation_id}/cancel")
def cancel_installation(request: Request, installation_id: str) -> dict[str, bool]:
    """Stops this installation's own processes; completed stages stay on the target."""
    app = state(request)
    folder = install.receipt_folder(app.settings_path)
    receipt = _receipt(app, installation_id)
    try:
        job = app.jobs.jobs.get(receipt.get("job_id") or "")
        if job and job.state == "running":
            job.cancelled.set()
        else:
            install.cancel_receipt(receipt)
            receipt["state"] = "cancelled"
            install.save_receipt(folder, receipt)
    except (ValueError, RuntimeError, OSError) as error:
        raise HTTPException(400, str(error)) from error
    return {"cancelled": True}


class VerifyEngine(BaseModel):
    profile_id: str


@router.post("/api/engine/verify")
def verify_engine(request: Request, body: VerifyEngine) -> dict[str, Any]:
    """Checks again the engine of a profile installed by the application, on its target."""
    app = state(request)
    try:
        profile = app.settings.profile(body.profile_id)
    except KeyError as error:
        raise HTTPException(
            404, tr(f"Unknown profile {body.profile_id!r}", f"Profil inconnu : {body.profile_id!r}")
        ) from error
    manifest = profile.engine_manifest
    if not manifest.get("root") or not manifest.get("kit"):
        raise HTTPException(
            422,
            tr(
                "This profile points to an engine that was not installed by the application",
                "Ce profil désigne un moteur qui n'a pas été installé par le logiciel",
            ),
        )
    try:
        verified = install.verify_engine(
            profile, install.validate_root(manifest["root"]), install.validate_root(manifest["kit"])
        )
    except (RuntimeError, ValueError, OSError) as error:
        return {"ok": False, "error": str(error)}
    return {
        "ok": True,
        "manifest": install.manifest_summary(
            verified, manifest["root"], manifest["kit"], manifest.get("installation_id", "")
        ),
    }


@router.post("/api/engine/data-folder")
def update_data_folder(request: Request, body: VerifyEngine) -> dict[str, Any]:
    """Brings an engine installed before version 0.6.2 to the shared data folder next to it:
    moves what was downloaded and saves the profile."""
    app = state(request)
    try:
        profile = app.settings.profile(body.profile_id)
    except KeyError as error:
        raise HTTPException(
            404, tr(f"Unknown profile {body.profile_id!r}", f"Profil inconnu : {body.profile_id!r}")
        ) from error
    try:
        updated = install.move_data_folder(profile)
    except (RuntimeError, ValueError, OSError) as error:
        raise HTTPException(
            502,
            tr(
                f"The data could not be moved: {error}",
                f"Les données n'ont pas pu être déplacées : {error}",
            ),
        ) from error
    settings = app.settings.model_copy(deep=True)
    settings.profiles = [updated if p.id == profile.id else p for p in settings.profiles]
    app.save_settings(settings)
    return profiles(request)


class PhysicsOptions(BaseModel):
    physics: dict[str, Any]


@router.post("/api/engine/complements")
def needed_complements(body: PhysicsOptions) -> dict[str, list[str]]:
    """Geography complements the physics options of a project need."""
    return {"complements": install.complements_for(body.physics)}
