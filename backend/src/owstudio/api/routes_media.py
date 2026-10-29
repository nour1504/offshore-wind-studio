"""Animations (MP4) and PDF reports, produced as background jobs."""

import uuid
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from owstudio.api.routes_cases import state
from owstudio.api.routes_results import run_root
from owstudio.api.state import Job
from owstudio.core import media
from owstudio.core.case.model import Case
from owstudio.core.extract.history import HistoryFiles
from owstudio.core.extract.points import field_at
from owstudio.core.extract.quantities import Unavailable
from owstudio.core.i18n import tr
from owstudio.core.storage import stage_folder

router = APIRouter()


class VideoIn(BaseModel):
    run: str | None = None
    stage: Literal["main", "control"] = "main"
    domain: int = Field(1, ge=1, le=99)
    variable: str = "wind_speed"
    height_m: float | None = Field(100, ge=0)
    first: int = Field(0, ge=0)
    last: int | None = Field(None, ge=0)
    stride: int = Field(1, ge=1)
    fps: int = Field(12, ge=1, le=60)
    width: int = Field(1280, ge=320, le=2560, multiple_of=16)
    vectors: bool = True
    vmin: float | None = None
    vmax: float | None = None


class ReportIn(BaseModel):
    run: str | None = None
    lang: Literal["fr", "en"] = "fr"


def _artifact(
    request: Request, case_id: str, kind: str, path: Path, details: dict[str, Any]
) -> dict[str, Any]:
    return {
        "name": path.name,
        "path": str(path),
        "kind": kind,
        "size": path.stat().st_size,
        "url": f"/api/cases/{case_id}/media/{kind}/{path.name}",
        **details,
    }


@router.get("/api/cases/{case_id}/media")
def list_media(request: Request, case_id: str) -> list[dict[str, Any]]:
    app = state(request)
    app.workspace.load(case_id)
    return [
        _artifact(request, case_id, kind, path, {})
        for kind, folder, extension in (
            ("videos", app.storage.videos, "mp4"),
            ("reports", app.storage.reports, "pdf"),
        )
        for path in sorted(folder.glob(f"{case_id}-*.{extension}"), reverse=True)
        if path.is_file()
    ]


@router.get("/api/cases/{case_id}/media/{kind}/{name}")
def download_media(
    request: Request, case_id: str, kind: Literal["videos", "reports"], name: str
) -> FileResponse:
    app = state(request)
    app.workspace.load(case_id)
    folder = app.storage.videos if kind == "videos" else app.storage.reports
    extension = ".mp4" if kind == "videos" else ".pdf"
    path = folder / name
    if (
        Path(name).name != name
        or not name.startswith(f"{case_id}-")
        or path.suffix != extension
        or not path.is_file()
    ):
        raise HTTPException(404, tr("Unknown export", "Export inconnu"))
    if path.resolve().parent != folder.resolve():
        raise HTTPException(404, tr("Unknown export", "Export inconnu"))
    return FileResponse(
        path, filename=name, media_type="video/mp4" if kind == "videos" else "application/pdf"
    )


@router.post("/api/cases/{case_id}/media/video", status_code=202)
def create_video(request: Request, case_id: str, body: VideoIn) -> dict[str, Any]:
    app = state(request)
    root = run_root(request, case_id, body.run)
    outputs = stage_folder(root, body.stage)
    snapshot = outputs / "case.yaml"
    case = Case.from_yaml(snapshot if snapshot.exists() else root / "case.yaml")
    try:
        files = HistoryFiles(outputs, body.domain)
        last = body.last if body.last is not None else len(files.times) - 1
        if body.first > last or last >= len(files.times):
            raise ValueError(
                tr(
                    "Frame range is outside the available output times",
                    "La plage d'images sort des instants de sortie disponibles",
                )
            )
        field_at(files, body.first, body.variable, body.height_m)
    except (FileNotFoundError, ValueError, KeyError, Unavailable) as error:
        raise HTTPException(422, str(error)) from error
    if body.vmin is not None and body.vmax is not None and body.vmin >= body.vmax:
        raise HTTPException(
            422,
            tr(
                "Colour bounds must be increasing", "Les bornes de couleur doivent être croissantes"
            ),
        )
    frames = list(range(body.first, last + 1, body.stride))
    path = app.storage.videos / f"{case_id}-{uuid.uuid4().hex[:12]}.mp4"

    def work(job: Job) -> dict[str, Any]:
        job.write(f"{len(frames)} frames; run {root.name}; d{body.domain:02d}; {body.variable}")
        details = media.video(
            path,
            outputs,
            case,
            body.domain,
            body.variable,
            body.height_m,
            frames,
            body.fps,
            body.width,
            body.vectors,
            job.cancelled,
            lambda p: setattr(job, "progress", p),
            body.vmin,
            body.vmax,
        )
        return _artifact(request, case_id, "videos", path, details)

    return {
        "job_id": app.jobs.start("Render MP4", work).id,
        "frames": len(frames),
        "run_id": root.name,
    }


@router.post("/api/cases/{case_id}/media/report", status_code=202)
def create_report(request: Request, case_id: str, body: ReportIn) -> dict[str, Any]:
    app = state(request)
    case = app.workspace.load(case_id)
    root = None
    if body.run:
        try:
            root = app.storage.run(case_id, body.run).root
        except KeyError as error:
            raise HTTPException(404, tr("Unknown run", "Calcul inconnu")) from error
        if not (root / "case.yaml").exists():
            raise HTTPException(
                404, tr("No snapshot in this run", "Aucun instantané dans ce calcul")
            )
        case = Case.from_yaml(root / "case.yaml")
    path = app.storage.reports / f"{case_id}-{uuid.uuid4().hex[:12]}.pdf"

    def work(job: Job) -> dict[str, Any]:
        if job.cancelled.is_set():
            raise media.MediaCancelled(tr("Report cancelled", "Rapport annulé"))
        try:
            details = media.report(path, case, root, body.lang)
            if job.cancelled.is_set():
                raise media.MediaCancelled(tr("Report cancelled", "Rapport annulé"))
            return _artifact(request, case_id, "reports", path, details)
        except BaseException:
            path.unlink(missing_ok=True)
            raise

    return {"job_id": app.jobs.start("Create PDF report", work).id}
