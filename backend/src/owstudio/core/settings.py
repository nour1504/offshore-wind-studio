"""Application settings: data folder, compute profiles, preferences, users.

Stored in the user's settings folder (outside the data folder, since the data folder itself is a
setting). Every field has a default so that an empty or older file still loads. No compute
profile is needed to open the application, prepare cases, read the documentation or analyse
results; only running WRF needs one.
"""

import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from owstudio.core.engine.profiles import KINDS, ComputeProfile, without_removed_fields
from owstudio.core.i18n import tr


def _settings_dir(
    platform: str = sys.platform,
    environ: Mapping[str, str] = os.environ,
    home: Path | None = None,
) -> Path:
    """Windows: %APPDATA%\\OffshoreWindStudio. Linux: $XDG_CONFIG_HOME (~/.config) /
    OffshoreWindStudio, after copying the settings of the former ~/.owstudio folder once (never
    moved nor deleted). Other systems keep ~/.owstudio."""
    home = home or Path.home()
    if platform == "win32" and environ.get("APPDATA"):
        return Path(environ["APPDATA"]) / "OffshoreWindStudio"
    former = home / ".owstudio"
    if platform.startswith("linux"):
        folder = Path(environ.get("XDG_CONFIG_HOME") or home / ".config") / "OffshoreWindStudio"
        if not folder.exists() and (former / "settings.json").is_file():
            import shutil

            try:
                shutil.copytree(former, folder)
            except OSError:
                return former
        return folder
    return former


SETTINGS_DIR = _settings_dir()
SETTINGS_FILE = SETTINGS_DIR / "settings.json"
DEFAULT_DATA_ROOT = Path.home() / "OffshoreWindStudio"


def physical_cores() -> int:
    """Physical cores of this machine; WRF gains little from hyper-threads."""
    try:
        import psutil

        return int(psutil.cpu_count(logical=False) or os.cpu_count() or 2)
    except ImportError:
        return max(1, (os.cpu_count() or 2) // 2)


class Folders(BaseModel):
    """Optional overrides of the folders below the data folder; empty means the default place."""

    input: str = ""
    observations: str = ""
    videos: str = ""
    reports: str = ""
    exports: str = ""


class Settings(BaseModel):
    data_root: str = str(DEFAULT_DATA_ROOT)
    folders: Folders = Field(default_factory=Folders)
    profiles: list[ComputeProfile] = Field(default_factory=list)
    default_profile: str | None = None
    language: Literal["en", "fr"] = "fr"

    @model_validator(mode="before")
    @classmethod
    def _without_removed_kinds(cls, data: object) -> object:
        """Profiles of a kind no longer supported (container engine, SSH servers and Slurm
        clusters) are left out, and so are the fields older versions used to launch runs."""
        if isinstance(data, dict) and isinstance(data.get("profiles"), list):
            kept = [
                p
                for p in data["profiles"]
                if not (isinstance(p, dict) and p.get("kind") not in KINDS)
            ]
            kept = [without_removed_fields(p) if isinstance(p, dict) else p for p in kept]
            data = {**data, "profiles": kept}
            if data.get("default_profile") not in {
                p.get("id") for p in kept if isinstance(p, dict)
            }:
                data["default_profile"] = None
        return data

    @model_validator(mode="after")
    def _default_profile_exists(self) -> "Settings":
        ids = [p.id for p in self.profiles]
        if len(ids) != len(set(ids)):
            raise ValueError(
                tr(
                    "compute profile identifiers must be unique",
                    "les identifiants des profils de calcul doivent être uniques",
                )
            )
        if self.default_profile not in ids:
            self.default_profile = ids[0] if ids else None
        return self

    def profile(self, profile_id: str | None) -> ComputeProfile:
        wanted = profile_id or self.default_profile
        for profile in self.profiles:
            if profile.id == wanted:
                return profile
        raise KeyError(
            tr(
                f"No compute profile {wanted!r}: create one in Compute",
                f"Aucun profil de calcul {wanted!r} : créez-en un dans Calcul",
            )
        )

    @property
    def data_path(self) -> Path:
        return Path(self.data_root).expanduser()


def load_settings(path: Path = SETTINGS_FILE) -> Settings:
    if path.exists():
        # utf-8-sig: a file saved with a byte order mark (Notepad, PowerShell) still loads
        return Settings.model_validate_json(path.read_text(encoding="utf-8-sig"))
    return Settings()


def save_settings(settings: Settings, path: Path = SETTINGS_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
    temporary.replace(path)
