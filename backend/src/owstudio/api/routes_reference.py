"""The run without turbines compared with a run, for the wake losses.

Each import holds one set of outputs. A run with turbines is compared with another run, of this
project or of any other, that has no turbine power (no POWER in its history files) and the same
grid. The choice is saved in the run folder (outputs/reference.json) and can be changed at any
time: no file is copied or moved. Runs imported with their run without turbines (outputs/control)
keep it unless another one is chosen.
"""

import json
import os
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from owstudio.api.routes_cases import state
from owstudio.api.state import AppState
from owstudio.core.case.model import Case
from owstudio.core.extract.history import HistoryFiles, domains
from owstudio.core.i18n import tr
from owstudio.core.postproc.results import Results
from owstudio.core.postproc.windowed import history_paths
from owstudio.core.storage import REFERENCE_FILE, reference_choice

router = APIRouter()


class ReferenceIn(BaseModel):
    # "run": another run, given by its project and run; "included": the one imported with the
    # run; "none": no comparison
    kind: Literal["run", "included", "none"]
    case_id: str = ""
    run_id: str = ""


def _run_root(app: AppState, case_id: str, run_id: str) -> Path:
    app.workspace.load(case_id)
    try:
        root = app.storage.run(case_id, run_id).root
    except KeyError as error:
        raise HTTPException(404, tr("Unknown run", "Calcul inconnu")) from error
    if not Results.exist(root):
        raise HTTPException(404, tr("This run has no results", "Ce calcul n'a pas de résultats"))
    return root


def without_turbines(main: Path) -> bool:
    """True when no domain of these outputs has turbine power."""
    try:
        return not any(HistoryFiles(main, number).has("POWER") for number in domains(main))
    except (FileNotFoundError, OSError):
        return False


def _candidates(app: AppState, root: Path) -> list[dict[str, Any]]:
    """Runs without turbines on the same grid, of every project, the latest first."""
    grid = Case.from_yaml(root / "outputs" / "main" / "case.yaml").grid
    found = []
    for summary in app.workspace.list():
        for run_id in reversed(app.storage.run_ids(summary.id)):
            other = app.storage.run(summary.id, run_id).root
            main = other / "outputs" / "main"
            if other == root or not Results.exist(other) or not without_turbines(main):
                continue
            try:
                if Case.from_yaml(main / "case.yaml").grid != grid:
                    continue
            except (OSError, ValueError):
                continue
            status = app.runs.status(summary.id, run_id)
            found.append(
                {
                    "case_id": summary.id,
                    "case_name": summary.name,
                    "run_id": run_id,
                    "finished_at": status.finished_at or status.started_at,
                }
            )
    return found


def _current(root: Path, included: bool) -> dict[str, str]:
    chosen = reference_choice(root)
    if chosen is None:
        return {"kind": "included" if included else "none"}
    if chosen.get("none"):
        return {"kind": "none"}
    return {
        "kind": "run",
        "case_id": str(chosen.get("case_id", "")),
        "run_id": str(chosen.get("run_id", "")),
    }


@router.get("/api/cases/{case_id}/runs/{run_id}/reference")
def reference_options(request: Request, case_id: str, run_id: str) -> dict[str, Any]:
    """The run without turbines compared with this run, and the ones that can be chosen."""
    app = state(request)
    root = _run_root(app, case_id, run_id)
    included = bool(history_paths(root / "outputs" / "control"))
    return {
        "current": _current(root, included),
        "included": included,
        "options": _candidates(app, root),
    }


@router.put("/api/cases/{case_id}/runs/{run_id}/reference")
def choose_reference(
    request: Request, case_id: str, run_id: str, body: ReferenceIn
) -> dict[str, Any]:
    app = state(request)
    root = _run_root(app, case_id, run_id)
    saved = root / "outputs" / REFERENCE_FILE
    if body.kind == "run":
        other = _run_root(app, body.case_id, body.run_id)
        if not any(
            c["case_id"] == body.case_id and c["run_id"] == body.run_id
            for c in _candidates(app, root)
        ):
            raise HTTPException(
                422,
                tr(
                    "This run cannot be the reference: it has turbines or another grid",
                    "Ce calcul ne peut pas servir de référence : il a des éoliennes ou une autre grille",
                ),
            )
        main = other / "outputs" / "main"
        try:
            path = Path(os.path.relpath(main, root)).as_posix()
        except ValueError:  # another drive
            path = main.as_posix()
        choice: dict[str, Any] = {"case_id": body.case_id, "run_id": body.run_id, "path": path}
    elif body.kind == "none":
        choice = {"none": True}
    else:
        saved.unlink(missing_ok=True)
        return reference_options(request, case_id, run_id)
    temporary = saved.with_suffix(".tmp")
    temporary.write_text(json.dumps(choice, indent=2), encoding="utf-8")
    temporary.replace(saved)
    return reference_options(request, case_id, run_id)
