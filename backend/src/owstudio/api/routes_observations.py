"""Observations: import with saved mappings, conversion to the common format, alignment and comparison."""

from pathlib import Path
from typing import Any

import numpy as np
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from owstudio.api.routes_analysis import GroupingIn, SelectionIn, _grouping
from owstudio.api.routes_cases import state
from owstudio.core.analysis.common import AnalysisError
from owstudio.core.analysis.compare import compare
from owstudio.core.case.model import Case
from owstudio.core.i18n import tr
from owstudio.core.observations import align as aligning
from owstudio.core.observations import mapping as mappings
from owstudio.core.observations import store
from owstudio.core.observations.convert import ConversionError, convert
from owstudio.core.observations.mapping import FileOptions, Mapping
from owstudio.core.observations.reader import detect, read_delimited, read_netcdf, suggest
from owstudio.core.series.sources import SeriesNotFound, SeriesRef, resolve

router = APIRouter()
PREVIEW_ROWS = 30


def _path(text: str) -> Path:
    path = Path(text).expanduser()
    if not path.is_file():
        raise HTTPException(
            404,
            tr(
                f"File not found on this computer: {path}",
                f"Fichier introuvable sur cet ordinateur : {path}",
            ),
        )
    return path


def _table(
    path: Path, options: FileOptions, nrows: int | None = None
) -> tuple[Any, dict[str, Any], dict[str, str], str]:
    """The file as a table of text cells, its layout and its units."""
    is_netcdf = options.format == "netcdf" or (
        options.format == "auto" and path.suffix.lower() in (".nc", ".nc4", ".cdf")
    )
    if is_netcdf:
        frame, units = read_netcdf(path)
        layout: dict[str, Any] = {"format": "netcdf", "columns": list(frame.columns), "flags": []}
        return (frame.head(nrows) if nrows else frame), layout, units, "."
    try:
        found = detect(path, options)
    except (ValueError, UnicodeDecodeError) as error:
        raise HTTPException(
            422,
            tr(f"Cannot read {path.name}: {error}", f"Impossible de lire {path.name} : {error}"),
        ) from error
    frame = read_delimited(path, found, nrows)
    layout = {k: v for k, v in found.__dict__.items() if k != "flags"}
    layout["flags"] = [f.model_dump() for f in found.flags]
    return frame, layout, found.units, found.decimal


class PreviewIn(BaseModel):
    path: str
    file: FileOptions = Field(default_factory=FileOptions)


@router.post("/api/observations/preview")
def preview(body: PreviewIn) -> dict[str, Any]:
    """The detected layout, the first rows, and a suggestion for every column (time columns,
    variable, height, unit, statistic), with flags for every ambiguity."""
    path = _path(body.path)
    frame, layout, units, _ = _table(path, body.file, PREVIEW_ROWS)
    time_columns, suggestions, flags = suggest(list(frame.columns), units, frame)
    return {
        "layout": layout,
        "columns": list(frame.columns),
        "rows": frame.head(PREVIEW_ROWS).to_dict("records"),
        "time_columns": time_columns,
        "suggestions": suggestions,
        "flags": [*layout["flags"], *[f.model_dump() for f in flags]],
    }


class CheckIn(BaseModel):
    path: str
    mapping: Mapping


@router.post("/api/observations/check")
def check_mapping(body: CheckIn) -> dict[str, Any]:
    """Whether the mapping can be applied, and the series it would give on the first rows."""
    errors = mappings.readiness(body.mapping)
    if errors:
        return {"ready": False, "flags": [e.model_dump() for e in errors], "series": []}
    frame, _, units, decimal = _table(_path(body.path), body.mapping.file, 500)
    try:
        found, flags = convert(
            frame, body.mapping, "preview", body.mapping.file.decimal or decimal, units
        )
    except ConversionError as error:
        return {"ready": False, "flags": [f.model_dump() for f in error.flags], "series": []}
    return {
        "ready": True,
        "flags": [f.model_dump() for f in flags],
        "series": [
            {
                "meta": s.meta.model_dump(mode="json"),
                "times": [t.isoformat() for t in s.times[:20]],
                "values": [None if np.isnan(v) else float(v) for v in s.values.to_numpy()[:20]],
            }
            for s in found
        ],
    }


@router.get("/api/observations/mappings")
def list_mappings(request: Request) -> list[dict[str, Any]]:
    return mappings.list_mappings(state(request).storage.observations)


@router.get("/api/observations/mappings/{name}")
def get_mapping(request: Request, name: str) -> dict[str, Any]:
    try:
        return mappings.load_mapping(state(request).storage.observations, name).model_dump(
            mode="json"
        )
    except (KeyError, ValueError) as error:
        raise HTTPException(
            404, tr(f"Unknown mapping {name!r}", f"Correspondance inconnue : {name!r}")
        ) from error


@router.put("/api/observations/mappings/{name}")
def save_mapping(request: Request, name: str, mapping: Mapping) -> dict[str, Any]:
    try:
        mappings.save_mapping(state(request).storage.observations, name, mapping)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    return {"name": name}


@router.delete("/api/observations/mappings/{name}", status_code=204)
def delete_mapping(request: Request, name: str) -> None:
    try:
        mappings.delete_mapping(state(request).storage.observations, name)
    except (KeyError, ValueError) as error:
        raise HTTPException(
            404, tr(f"Unknown mapping {name!r}", f"Correspondance inconnue : {name!r}")
        ) from error


class ImportIn(BaseModel):
    path: str
    mapping: Mapping
    dataset_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{0,63}$")
    name: str = Field(min_length=1, max_length=120)


@router.post("/api/observations/import")
def import_dataset(request: Request, body: ImportIn) -> dict[str, Any]:
    """Imports the whole file as a dataset, in the background; follow the job for the result."""
    app = state(request)
    path = _path(body.path)
    if (
        body.dataset_id in store.RESERVED
        or (app.storage.observations / body.dataset_id / "dataset.json").exists()
    ):
        raise HTTPException(
            409,
            tr(
                f"A dataset {body.dataset_id!r} already exists: choose another identifier or delete it",
                f"Un jeu de données {body.dataset_id!r} existe déjà : choisissez un autre identifiant ou supprimez-le",
            ),
        )
    errors = mappings.readiness(body.mapping)
    if errors:
        raise HTTPException(422, {"errors": [e.message for e in errors]})

    def work(job: Any) -> dict[str, Any]:
        job.write(f"Reading {path}")
        frame, _, units, decimal = _table(path, body.mapping.file)
        job.progress = 0.4
        found, flags = convert(
            frame, body.mapping, body.dataset_id, body.mapping.file.decimal or decimal, units
        )
        job.progress = 0.8
        job.write(f"{len(found)} series, {len(frame)} rows")
        return store.save(
            app.storage.observations, body.dataset_id, body.name, path, body.mapping, found, flags
        )

    job = app.jobs.start(f"Import {path.name}", work)
    return {"job": job.id}


@router.get("/api/observations/datasets")
def list_datasets(request: Request) -> list[dict[str, Any]]:
    return store.datasets(state(request).storage.observations)


@router.get("/api/observations/datasets/{dataset_id}")
def get_dataset(request: Request, dataset_id: str) -> dict[str, Any]:
    try:
        return store.describe(state(request).storage.observations, dataset_id)
    except KeyError as error:
        raise HTTPException(
            404, tr(f"Unknown dataset {dataset_id!r}", f"Jeu de données inconnu : {dataset_id!r}")
        ) from error


@router.delete("/api/observations/datasets/{dataset_id}", status_code=204)
def delete_dataset(request: Request, dataset_id: str) -> None:
    """Deletes the imported dataset (series and copy of the source); the original file is untouched."""
    try:
        store.delete(state(request).storage.observations, dataset_id)
    except KeyError as error:
        raise HTTPException(
            404, tr(f"Unknown dataset {dataset_id!r}", f"Jeu de données inconnu : {dataset_id!r}")
        ) from error


class CompareIn(BaseModel):
    observation: SeriesRef
    simulation: SeriesRef
    # Common averaging period in seconds (e.g. 600 or 3600); None: the series already match
    period_s: float | None = 3600.0
    min_availability: float = 0.7
    tolerance_s: float = 0.0
    grouping: GroupingIn = Field(default_factory=GroupingIn)
    selection: SelectionIn = Field(default_factory=SelectionIn)


@router.post("/api/observations/compare")
def compare_with_simulation(request: Request, body: CompareIn) -> dict[str, Any]:
    """A measured series against a simulated one, aligned explicitly, with metrics, plot data and
    the representativeness caveats."""
    app = state(request)
    simulation_ref = body.simulation
    try:
        observed = resolve(app, body.observation)
        if (
            simulation_ref.lat is None
            and simulation_ref.location == ""
            and observed.meta.lat is not None
        ):
            # The model at the station, at the measurement's height, unless said otherwise
            simulation_ref = simulation_ref.model_copy(
                update={
                    "lat": observed.meta.lat,
                    "lon": observed.meta.lon,
                    "height_m": simulation_ref.height_m
                    if simulation_ref.height_m is not None
                    else observed.meta.height_m,
                    "height_ref": observed.meta.height_ref
                    if observed.meta.height_ref != "surface"
                    else "agl",
                }
            )
        simulated = resolve(app, simulation_ref)
    except SeriesNotFound as error:
        raise HTTPException(404, str(error)) from error
    try:
        obs, sim, notes = aligning.align(observed, simulated, body.period_s, body.min_availability)
        selection = body.selection.build()
        grouping = _grouping(request, body.grouping, obs, selection)
        result = compare(obs, sim, grouping, body.tolerance_s, selection).to_json()
    except (aligning.AlignmentError, AnalysisError) as error:
        raise HTTPException(422, str(error)) from error
    spacing = None
    if simulated.meta.extra.get("domain") and simulation_ref.case_id:
        try:
            case: Case = app.workspace.load(simulation_ref.case_id)
            spacing = case.grid.domain_dx()[int(simulated.meta.extra["domain"]) - 1]
        except (KeyError, IndexError):
            spacing = None
    result["alignment"] = notes
    result["caveats"] = aligning.caveats(observed, simulated, spacing)
    return result
