"""Input data: GRIB inventories, Vtable compatibility, SST sources, NetCDF conversion and checks before a run."""

from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from owstudio.core.case.model import Case
from owstudio.core.data import examine, found, userfiles, vtables
from owstudio.core.i18n import tr

router = APIRouter()

# Files listed in a preview; the counts and the total size always cover every file
PREVIEW_LIMIT = 200


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(v) for v in value]
    return value


class ExamineIn(BaseModel):
    case: Case
    role: Literal["atmosphere", "sst"] = "atmosphere"


@router.post("/api/data/examine")
def examine_files(body: ExamineIn) -> dict[str, Any]:
    """What ungrib will find in the case's own files (fields, levels, times, area), the problems
    it, metgrid or real.exe would meet, and the standard Vtables that read the files best. Every
    file is read, however large (headers only)."""
    report = examine.examine_case(body.case, body.role, with_suggestions=True)
    if report is None:
        what = (
            tr("input files", "fichiers d'entrée")
            if body.role == "atmosphere"
            else tr("SST files", "fichiers SST")
        )
        raise HTTPException(
            422,
            tr(
                f"The case does not use its own {what}.",
                f"Le projet n'utilise pas ses propres fichiers ({what}).",
            ),
        )
    result: dict[str, Any] = _jsonable(asdict(report))
    result["errors"] = report.errors
    return result


@router.get("/api/data/files")
def input_files(folder: str, pattern: str = "*") -> dict[str, Any]:
    """Files of a folder on this computer and of its subfolders matching the pattern, with their
    detected format and the folders they are in."""
    try:
        files = userfiles.list_files(folder, pattern)
    except FileNotFoundError as error:
        raise HTTPException(404, str(error)) from error
    except OSError as error:
        raise HTTPException(
            422, tr(f"Cannot read {folder}: {error}", f"Impossible de lire {folder} : {error}")
        ) from error
    formats: dict[str, int] = {}
    for f in files:
        formats[f.format] = formats.get(f.format, 0) + 1
    return {
        "folder": folder,
        "count": len(files),
        "total_bytes": sum(f.size for f in files),
        "formats": formats,
        "problems": userfiles.problems(files, "Files"),
        "files": [
            {"name": f.name, "bytes": f.size, "format": f.format} for f in files[:PREVIEW_LIMIT]
        ],
        "truncated": len(files) > PREVIEW_LIMIT,
        "tree": found.tree(((f.path, f.size) for f in files), Path(folder).expanduser()),
    }


@router.get("/api/data/vtables")
def vtable_list() -> list[dict[str, Any]]:
    """WPS variable tables, recommended ones first, with the fields each produces."""
    return [asdict(info) for info in vtables.catalogue()]


@router.get("/api/data/vtables/{name}", response_class=PlainTextResponse)
def vtable_text(name: str) -> str:
    try:
        return vtables.read(name)
    except KeyError as error:
        raise HTTPException(404, str(error)) from error


class VtableText(BaseModel):
    text: str


@router.post("/api/data/vtables/validate")
def vtable_validate(body: VtableText) -> dict[str, Any]:
    """Whether ungrib can read a custom table, and the fields it produces."""
    return {"problems": vtables.validate(body.text), "fields": vtables.fields(body.text)}
