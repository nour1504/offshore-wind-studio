"""Import existing WRF outputs as a separate run, without modifying their original files.

The outputs of the exported scripts (core/method/export.py), brought back from a cluster, are
recognised by their manifest.json: the history files of [D, F] in wrf/ and the time series of
]D, F] in wrf/tslist_periode/ (wrf/tslist_period/ in English; time in hours since D). They are stored as one window of the
window method (windows.json), so that every reader keeps the method's conventions.
"""

import json
import os
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from owstudio.api.routes_cases import geometry, state
from owstudio.api.runs import RunStatus
from owstudio.api.state import Job
from owstudio.core.case.model import Case
from owstudio.core.data import found as found_files
from owstudio.core.extract.history import HistoryFiles, domains, record_times
from owstudio.core.i18n import tr
from owstudio.core.method.scripts import FILE_NAMES
from owstudio.core.paths import folders_below
from owstudio.core.postproc.windowed import history_paths, output_sources
from owstudio.core.storage import free_space

router = APIRouter()


class ImportIn(BaseModel):
    folder: str
    control_folder: str | None = None
    mode: Literal["link", "copy"] = "link"


EXPORT_FORMAT = "offshore-wind-studio-export"
EXPORT_DIR = "windows/export"


def exported(folder: Path) -> tuple[Path, dict[str, Any]] | None:
    """(wrf folder, manifest) when ``folder`` is an export of the application (its root or its
    wrf/ folder), else None."""
    for root in (folder, folder.parent):
        manifest = root / "manifest.json"
        if manifest.is_file():
            try:
                body = json.loads(manifest.read_text(encoding="utf-8"))
            except ValueError:
                continue
            if isinstance(body, dict) and body.get("format") == EXPORT_FORMAT:
                return root / "wrf", body
    return None


def export_manifest(body: dict[str, Any]) -> dict[str, Any]:
    """windows.json of an imported export: one window over the study period, history at D
    included (end of the first spin-up), time series ]D, F]."""
    return {
        "schema_version": 2,
        "mode": "independent_windows",
        "timezone": "UTC",
        "requested_start": body["period"]["start"],
        "requested_end": body["period"]["end"],
        "useful_hours": body.get("useful_hours"),
        "spin_up_hours": body.get("spin_up_hours"),
        "retention": "]useful_start,useful_end]; history also keeps D (first window)",
        "raw_outputs_retained": True,
        "source": "export",
        "windows": [
            {
                "id": "export",
                "number": 1,
                "useful_start": body["period"]["start"],
                "useful_end": body["period"]["end"],
                "include_start": True,
                "output_dir": EXPORT_DIR,
                "state": "succeeded",
            }
        ],
    }


def stored_name(name: str) -> str:
    """The name a file is imported under. WSL shows Windows the ":" of a Linux file name as
    U+F03A, which the netCDF library cannot open: the time takes its dashed form instead."""
    return name.replace("", "-")


def check_history(folder: Path, domain: int) -> None:
    """Reads the times of a domain's history files, unless their names hold U+F03A: the netCDF
    library cannot open those from here, they are read once imported under their stored name."""
    files = HistoryFiles(folder, domain)
    if not any("" in path.name for path in files.paths):
        _ = files.times


def _holds_outputs(folder: Path) -> bool:
    """An export of the application, or a folder of WRF history files."""
    return (
        exported(folder) is not None
        or (folder / "windows.json").is_file()
        or any(p.is_file() for p in folder.glob("wrfout_d*"))
    )


# How far below the chosen folder the outputs are searched
OUTPUTS_DEPTH = 4


def outputs_below(folder: Path) -> Path:
    """The folder holding the outputs: the chosen one, or the only one found below it (an export
    of the application or a folder of history files, the highest one of each branch)."""
    if _holds_outputs(folder):
        return folder
    holds: dict[Path, bool] = {}

    def stop(below: Path) -> bool:
        holds[below] = _holds_outputs(below)
        return holds[below]

    found = [p for p in folders_below(folder, OUTPUTS_DEPTH, stop) if holds.get(p)]
    if len(found) > 1:
        shown = ", ".join(str(p.relative_to(folder)) for p in found[:6])
        more = ", …" if len(found) > 6 else ""
        raise HTTPException(
            422,
            tr(
                f"Several calculations in {folder}: {shown}{more}. Choose one.",
                f"Plusieurs calculs dans {folder} : {shown}{more}. Choisissez-en un.",
            ),
        )
    return found[0] if found else folder


def sources(body: ImportIn) -> dict[str, tuple[Path, list[Path]]]:
    if not body.folder.strip():
        raise HTTPException(
            422,
            tr(
                "Choose a folder containing the main WRF outputs",
                "Choisissez un dossier contenant les sorties WRF principales",
            ),
        )
    result = {}
    for stage, text in (("main", body.folder), ("control", body.control_folder)):
        if not text:
            continue
        folder = Path(text).expanduser().resolve()
        if not folder.is_dir():
            raise HTTPException(
                422, tr(f"No input folder: {folder}", f"Dossier introuvable : {folder}")
            )
        folder = outputs_below(folder)
        export = exported(folder)
        if export is not None:
            result[stage] = _export_files(*export)
            continue
        try:
            available = domains(folder)
            if not available:
                raise HTTPException(
                    422,
                    tr(
                        f"No WRF history file in {folder}",
                        f"Aucun fichier d'historique WRF dans {folder}",
                    ),
                )
            for domain in available:
                check_history(folder, domain)
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise HTTPException(
                422,
                tr(
                    f"Invalid WRF history file: {error}",
                    f"Fichier d'historique WRF invalide : {error}",
                ),
            ) from error
        files = history_paths(folder)
        windowed = (folder / "windows.json").is_file()
        for source in output_sources(folder):
            for candidate in (source.folder, source.folder / "tslist"):
                files.extend(p for p in candidate.glob("*.d[0-9][0-9].*") if p.is_file())
        names = [str(p.relative_to(folder)) if windowed else p.name for p in files]
        if len(names) != len(set(names)):
            raise HTTPException(
                422,
                tr(
                    "Duplicate time-series file names in the source and its tslist folder; choose an unambiguous source folder",
                    "Des séries temporelles portent le même nom dans la source et dans son dossier tslist ; choisissez un dossier source sans ambiguïté",
                ),
            )
        if windowed:
            files.append(folder / "windows.json")
        result[stage] = (folder, list(dict.fromkeys(files)))
    return result


def _export_files(wrf: Path, body: dict[str, Any]) -> tuple[Path, list[Path]]:
    if not wrf.is_dir():
        raise HTTPException(
            422,
            tr(
                f"No wrf folder next to the manifest: {wrf}",
                f"Aucun dossier wrf à côté du manifest : {wrf}",
            ),
        )
    history = sorted(p for p in wrf.glob("wrfout_d*") if p.is_file())
    if not history:
        raise HTTPException(
            422,
            tr(
                f"No WRF history file in {wrf}: run the scripts first",
                f"Aucun fichier d'historique WRF dans {wrf} : lancez d'abord les scripts",
            ),
        )
    try:
        for domain in domains(wrf):
            check_history(wrf, domain)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise HTTPException(
            422,
            tr(
                f"Invalid WRF history file: {error}", f"Fichier d'historique WRF invalide : {error}"
            ),
        ) from error
    # The folder of the assembled series is named in the language of the export
    series = sorted(
        p
        for name in {names["tslist_period"] for names in FILE_NAMES.values()}
        for p in (wrf / name).glob("*.d[0-9][0-9].*")
        if p.is_file()
    )
    return wrf, [*history, *series, wrf.parent / "manifest.json"]


@router.post("/api/cases/{case_id}/results/import/preview")
def preview_import(request: Request, case_id: str, body: ImportIn) -> dict[str, Any]:
    app = state(request)
    case = app.workspace.load(case_id)
    found = sources(body)
    # Each file is measured once: the total and the tree of the preview
    sizes = {p: p.stat().st_size for _, files in found.values() for p in files}
    count = sum(len(files) for _, files in found.values())
    size = sum(sizes.values())
    notes = []
    export = exported(found["main"][0])
    if export is not None:
        # An export of the application names its project and period: said only when they differ
        manifest = export[1]
        period = manifest.get("period") or {}
        same_period = str(period.get("start", "")).startswith(
            case.period.start.isoformat()
        ) and str(period.get("end", "")).startswith(case.period.end.isoformat())
        if manifest.get("project") != case.name or not same_period:
            notes.append(
                tr(
                    f'These outputs were exported from the project "{manifest.get("project")}" ({period.get("start")} → {period.get("end")}): check that they match this project',
                    f"Ces sorties viennent du projet « {manifest.get('project')} » ({period.get('start')} → {period.get('end')}) : vérifiez qu'elles correspondent à ce projet",
                )
            )
    elif not (found["main"][0] / "case.yaml").is_file():
        notes.append(
            tr(
                "No case.yaml in the source: the saved project's configuration will be used; check that it matches these outputs",
                "Pas de case.yaml dans la source : la configuration du projet enregistré sera utilisée ; vérifiez qu'elle correspond à ces sorties",
            )
        )
    if body.mode == "link":
        if any(
            os.stat(p).st_dev != os.stat(app.storage.cases).st_dev
            for _, files in found.values()
            for p in files
        ):
            raise HTTPException(
                422,
                tr(
                    "Linked import needs inputs and project data on the same disk; choose Copy for another disk",
                    "L'import par liens demande que les sorties et les données du projet soient sur le même disque ; choisissez Copier pour un autre disque",
                ),
            )
        notes.append(
            tr(
                "Hard links share file contents without a second data copy. Keep these outputs immutable: editing either name changes the same file",
                "Les liens physiques partagent le contenu des fichiers sans seconde copie. Ne modifiez pas ces sorties : changer l'un des deux noms change le même fichier",
            )
        )
    return {
        "files": count,
        "bytes": size,
        "mode": body.mode,
        "warnings": notes,
        "domains": {stage: domains(folder) for stage, (folder, _) in found.items()},
        # What will be imported, folder by folder, to check it before importing
        "folder": str(found["main"][0]),
        "tree": found_files.tree(sizes.items()),
    }


@router.post("/api/cases/{case_id}/results/import", status_code=202)
def import_outputs(request: Request, case_id: str, body: ImportIn) -> dict[str, str]:
    app = state(request)
    preview = preview_import(request, case_id, body)
    found = sources(body)
    from_export = {stage: exported(folder) for stage, (folder, _) in found.items()}
    snapshot = found["main"][0] / "case.yaml"
    try:
        case = Case.from_yaml(snapshot) if snapshot.is_file() else app.workspace.load(case_id)
    except ValueError as error:
        raise HTTPException(
            422,
            tr(f"Invalid source case.yaml: {error}", f"case.yaml de la source invalide : {error}"),
        ) from error
    if body.mode == "copy" and preview["bytes"] > free_space(app.storage.cases):
        raise HTTPException(
            422,
            tr(
                "Not enough free disk space for this copy",
                "Pas assez d'espace libre sur le disque pour cette copie",
            ),
        )
    paths = app.storage.create_run(case_id)
    case.to_yaml(paths.case_snapshot)
    now = datetime.now(UTC)
    status = RunStatus(
        run_id=paths.id,
        state="running",
        started_at=now,
        label=tr("Imported WRF outputs", "Sorties WRF importées"),
        with_control="control" in found,
        farms=[f.id for f in case.enabled_farms],
        step="import",
        tags={"source": "import", "mode": body.mode},
    )
    app.runs.save(paths, status)
    app.runs.writing(case_id, paths.id, True)

    def work(job: Job) -> dict[str, Any]:
        completed = 0
        try:
            for note in preview["warnings"]:
                job.write(note)
            for stage, (source_root, files) in found.items():
                target = paths.root / "outputs" / stage
                target.mkdir(parents=True, exist_ok=True)
                case.to_yaml(target / "case.yaml")
                export = from_export.get(stage)
                if export is not None:
                    (target / "windows.json").write_text(
                        json.dumps(export_manifest(export[1]), indent=2) + "\n", encoding="utf-8"
                    )
                copies: list[tuple[Path, Path]] = []
                for source in files:
                    if job.cancelled.is_set():
                        raise RuntimeError(tr("Import cancelled", "Import annulé"))
                    if export is not None:
                        if source.name == "manifest.json":
                            destination = target / "export-manifest.json"
                        elif source.name.startswith("wrfout_"):
                            destination = target / EXPORT_DIR / stored_name(source.name)
                        else:
                            destination = target / EXPORT_DIR / "tslist" / source.name
                    elif (source_root / "windows.json").is_file():
                        relative = source.relative_to(source_root)
                        destination = target / relative.parent / stored_name(relative.name)
                    else:
                        destination = (
                            target if source.name.startswith("wrfout_") else target / "tslist"
                        ) / stored_name(source.name)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    # Metadata is copied even in linked mode, keeping bounds a stable snapshot.
                    if body.mode == "link" and source.name not in ("windows.json", "manifest.json"):
                        os.link(source, destination)
                    else:
                        shutil.copy2(source, destination)
                    copies.append((source, destination))
                    completed += 1
                    job.progress = completed / preview["files"]
                # The times read to check the import, kept: a long run opens without reading
                # every file again
                record_times(target, copies)
            status.state, status.fraction = "succeeded", 1.0
            return {"run_id": paths.id, "files": completed, "warnings": preview["warnings"]}
        except Exception as error:
            status.state = "cancelled" if job.cancelled.is_set() else "failed"
            status.error = str(error)
            raise
        finally:
            status.finished_at = datetime.now(UTC)
            app.runs.save(paths, status)
            app.runs.writing(case_id, paths.id, False)

    job = app.jobs.start("Import WRF outputs", work)
    return {"job_id": job.id, "run_id": paths.id}


@router.get("/api/cases/{case_id}/runs/{run_id}/geometry")
def run_geometry(request: Request, case_id: str, run_id: str) -> dict[str, Any]:
    app = state(request)
    app.workspace.load(case_id)
    try:
        root = app.storage.run(case_id, run_id).root
    except KeyError as error:
        raise HTTPException(404, tr("Unknown run", "Calcul inconnu")) from error
    snapshot = root / "case.yaml"
    if not snapshot.is_file():
        snapshot = root / "outputs" / "main" / "case.yaml"
    if not snapshot.is_file():
        raise HTTPException(
            404,
            tr(
                "No configuration snapshot in this run",
                "Pas de copie de la configuration dans ce calcul",
            ),
        )
    return geometry(Case.from_yaml(snapshot))
