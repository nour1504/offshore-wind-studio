"""Folders of the engine machine and of this computer, for the folder explorer (core/engine/browse.py)."""

from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from owstudio.api.routes_cases import state
from owstudio.core.engine import browse
from owstudio.core.engine.profiles import ComputeProfile

router = APIRouter()


def _engine(request: Request, profile_id: str | None = None) -> ComputeProfile | None:
    try:
        profile: ComputeProfile = state(request).settings.profile(profile_id)
    except KeyError:
        return None
    return profile


@router.get("/api/fs/list")
def list_folder(
    request: Request,
    machine: Literal["engine", "here"] = "here",
    path: str = "",
    offset: int = 0,
    profile: str | None = None,
) -> dict[str, Any]:
    """One folder; `profile` names the engine machine, the default profile otherwise."""
    return browse.listing(machine, _engine(request, profile), path, offset)


class CheckBody(BaseModel):
    folders: dict[str, str]
    geog_data_res: list[str] = []
    # Where the files are extracted: on the engine machine, a wrong folder stops the extraction
    destination: str = ""


@router.post("/api/fs/check")
def check_folders(request: Request, body: CheckBody) -> dict[str, Any]:
    """Few words for each wrong folder of the engine machine, and whether they block."""
    engine = _engine(request)
    needed = browse.needed_resolutions(body.geog_data_res)
    found: dict[str, str] = {}
    issues = browse.check(engine, body.folders, needed, found)
    return {
        "issues": issues,
        # The right folder below one given, which the scripts will take
        "found": found,
        "blocking": bool(issues) and browse.same_machine(engine, body.destination),
    }
