"""Observation datasets in the data folder: <observations>/<dataset>/ with the series (common
format), dataset.json (station, mapping, source file and its hash, import time, flags) and a copy
of the source file, which is never modified. Registers the resolver of SeriesRef(kind="observation")."""

import hashlib
import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from owstudio.core import series as series_format
from owstudio.core.i18n import tr
from owstudio.core.observations.mapping import Flag, Mapping
from owstudio.core.series import Series
from owstudio.core.series.sources import Context, SeriesNotFound, SeriesRef, register

DATASET_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
RESERVED = {"mappings", "uploads"}


def folder(observations: Path, dataset_id: str) -> Path:
    if not DATASET_ID.match(dataset_id) or dataset_id in RESERVED:
        raise KeyError(dataset_id)
    return observations / dataset_id


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def save(
    observations: Path,
    dataset_id: str,
    name: str,
    source: Path,
    mapping: Mapping,
    found: list[Series],
    flags: list[Flag],
) -> dict[str, Any]:
    target = folder(observations, dataset_id)
    target.mkdir(parents=True, exist_ok=True)
    (target / "source").mkdir(exist_ok=True)
    shutil.copy2(source, target / "source" / source.name)
    series_format.save(found, target / "series")
    document = {
        "id": dataset_id,
        "name": name,
        "station": mapping.station.model_dump(mode="json"),
        "mapping": mapping.model_dump(mode="json"),
        "source": {"name": source.name, "sha256": sha256(source), "bytes": source.stat().st_size},
        "imported_at": datetime.now(UTC).isoformat(),
        "flags": [f.model_dump() for f in flags],
        "series": [
            {
                "key": s.meta.key,
                "variable": s.meta.variable,
                "unit": s.meta.unit,
                "height_m": s.meta.height_m,
                "height_ref": s.meta.height_ref,
                "count": int(s.values.notna().sum()),
                "start": s.times[0].isoformat() if len(s.times) else None,
                "end": s.times[-1].isoformat() if len(s.times) else None,
            }
            for s in found
        ],
    }
    (target / "dataset.json").write_text(json.dumps(document, indent=1), encoding="utf-8")
    return document


def describe(observations: Path, dataset_id: str) -> dict[str, Any]:
    path = folder(observations, dataset_id) / "dataset.json"
    if not path.exists():
        raise KeyError(dataset_id)
    document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return document


def datasets(observations: Path) -> list[dict[str, Any]]:
    found = []
    for path in sorted(observations.glob("*/dataset.json")) if observations.exists() else []:
        document = json.loads(path.read_text(encoding="utf-8"))
        found.append(
            {k: document[k] for k in ("id", "name", "station", "imported_at", "series", "source")}
        )
    return found


def delete(observations: Path, dataset_id: str) -> None:
    target = folder(observations, dataset_id)
    if not (target / "dataset.json").exists():
        raise KeyError(dataset_id)
    shutil.rmtree(target)


def load(observations: Path, dataset_id: str) -> list[Series]:
    target = folder(observations, dataset_id)
    if not (target / "series.json").exists():
        raise KeyError(dataset_id)
    return series_format.load(target / "series")


def resolve_observation(context: Context, ref: SeriesRef) -> Series:
    try:
        found = load(context.storage.observations, ref.dataset)
    except KeyError as error:
        raise SeriesNotFound(
            tr(
                f"Unknown observation dataset {ref.dataset!r}",
                f"Jeu de données d'observation inconnu : {ref.dataset!r}",
            )
        ) from error
    for s in found:
        meta = s.meta
        if meta.variable != ref.variable or (ref.location and meta.location != ref.location):
            continue
        if ref.height_m is None and meta.height_m is None:
            return s
        if (
            ref.height_m is not None
            and meta.height_m is not None
            and abs(meta.height_m - ref.height_m) < 0.01
            and meta.height_ref == ref.height_ref
        ):
            return s
    heights = sorted(
        {(s.meta.height_m, s.meta.height_ref) for s in found if s.meta.variable == ref.variable},
        key=lambda h: (h[0] is None, h[0] or 0),
    )
    raise SeriesNotFound(
        tr(
            f"No {ref.variable} at {ref.height_m} m {ref.height_ref} in dataset {ref.dataset}",
            f"Pas de {ref.variable} à {ref.height_m} m {ref.height_ref} dans le jeu de données {ref.dataset}",
        )
        + (
            f" (heights available: {', '.join(f'{h} m {r}' for h, r in heights)})"
            if heights
            else ""
        )
    )


register("observation", resolve_observation)
