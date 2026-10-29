"""Projects exported to a file and imported back, to share them between computers.

An exported project is a ZIP holding the project's case.yaml (period, domains, turbine models,
farms, physics, outputs: everything set in the application) and project.json (what wrote it).
Runs and results are not included: they are large and are computed again. Paths to the user's
own weather or SST files are kept as they are; on another computer they are reported so that
they can be chosen again.

Import reads only case.yaml from the archive, in memory (nothing is unpacked to disk), and
validates it like any project before it is stored under a new identifier.
"""

import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from owstudio import __version__
from owstudio.core.case.model import Case
from owstudio.core.case.workspace import CASE_FILE
from owstudio.core.i18n import tr

FORMAT = "offshore-wind-studio-project"
# An exported project is a few hundred kilobytes; this bound rejects anything else early
MAX_BYTES = 50_000_000


def export_project(case: Case, case_dir: Path) -> bytes:
    """The project as a ZIP: case.yaml exactly as saved, and project.json."""
    about = {
        "format": FORMAT,
        "format_version": 1,
        "application_version": __version__,
        "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "name": case.name,
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(CASE_FILE, (case_dir / CASE_FILE).read_bytes())
        archive.writestr("project.json", json.dumps(about, indent=2, ensure_ascii=False))
    return buffer.getvalue()


def export_name(case: Case) -> str:
    """A file name readable on every system: the project's name, without forbidden characters."""
    safe = "".join(c if c.isalnum() or c in " -_()" else "-" for c in case.name).strip(" .-")
    return f"{safe or 'projet'}.owstudio.zip"


def read_project(data: bytes, filename: str) -> Case:
    """The project in an exported ZIP or in a case.yaml; ValueError with a plain reason."""
    if len(data) > MAX_BYTES:
        raise ValueError(
            tr(
                "This file is too large to be a project (50 MB at most).",
                "Ce fichier est trop gros pour être un projet (50 Mo au plus).",
            )
        )
    text: str
    if zipfile.is_zipfile(io.BytesIO(data)):
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = [name for name in archive.namelist() if Path(name).name == CASE_FILE]
            if not names:
                raise ValueError(
                    tr(
                        "This archive holds no case.yaml: it is not a project.",
                        "Cette archive ne contient pas de case.yaml : ce n'est pas un projet.",
                    )
                )
            info = archive.getinfo(min(names, key=lambda name: name.count("/")))
            if info.file_size > MAX_BYTES:
                raise ValueError(
                    tr(
                        "The case.yaml of this archive is too large.",
                        "Le case.yaml de cette archive est trop gros.",
                    )
                )
            text = archive.read(info).decode("utf-8")
    elif filename.lower().endswith((".yaml", ".yml")):
        text = data.decode("utf-8")
    else:
        raise ValueError(
            tr(
                "Choose a project exported by Offshore Wind Studio (.zip) or a case.yaml.",
                "Choisissez un projet exporté par Offshore Wind Studio (.zip) ou un case.yaml.",
            )
        )
    try:
        content: Any = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise ValueError(
            tr(
                f"The case.yaml cannot be read: {error}",
                f"Le case.yaml ne peut pas être lu : {error}",
            )
        ) from error
    if not isinstance(content, dict):
        raise ValueError(  # noqa: TRY004 - the callers report ValueError to the user
            tr(
                "The case.yaml does not describe a project.",
                "Le case.yaml ne décrit pas un projet.",
            )
        )
    return Case.model_validate(content)


def missing_folders(case: Case) -> list[str]:
    """The user's own weather and SST folders the project names but this computer lacks."""
    folders = [
        case.grib.folder if case.grib else "",
        case.sea_surface.grib.folder if case.sea_surface.grib else "",
    ]
    return [folder for folder in folders if folder and not Path(folder).expanduser().is_dir()]
