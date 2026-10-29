"""Compute profiles: where the WRF/WPS engine of this computer is.

WRF and WPS are Linux programs. A profile points to an installation made by the application's
installation wizard (or an existing one):

- wsl:    a Linux distribution of Windows Subsystem for Linux on this computer
- local:  this computer, when the application itself runs on Linux

The application does not run WRF itself (the exported scripts do): a profile serves to install,
check and find the engine (the geography of the 3D view comes from it). SSH and Slurm profiles
of older versions, and their fields for launching runs, are left out when old settings load
(core/settings.py).
"""

import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from owstudio.core.i18n import tr

Kind = Literal["wsl", "local"]
KINDS = ("wsl", "local")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EngineInstall(Strict):
    """Linux paths on the machine of the engine."""

    # WRF directory: main/wrf.exe, main/real.exe and run/ with the physics tables
    wrf_dir: str = ""
    # WPS directory: geogrid.exe, ungrib.exe, metgrid.exe, link_grib.csh, geogrid/, metgrid/, ungrib/
    wps_dir: str = ""
    # Static geography (the folder usually named WPS_GEOG)
    geog_dir: str = ""
    # Commands run before the programs: module load, source of an environment script, exports
    env_setup: str = ""
    # Kept only so that saved settings still load: nothing uses it any more
    work_dir: str = ""
    # Shared folder of the downloaded input data (gfs/<year>/, era5/<year>/): the scripts
    # of every calculation download there and ungrib reads there (checked as writable)
    input_dir: str = ""


class Resources(Strict):
    # How MPI programs are launched; {ranks} is replaced by the number of processes
    mpi_command: str = "mpirun -np {ranks}"


class ComputeProfile(Strict):
    id: str = Field(pattern=r"^[a-z0-9-]{1,40}$")
    name: str = Field(min_length=1, max_length=80)
    kind: Kind
    install: EngineInstall = Field(default_factory=EngineInstall)
    resources: Resources = Field(default_factory=Resources)
    wsl_distro: str = ""
    # Managed WSL uses a dedicated unprivileged user, without changing another distro's default.
    wsl_user: str = Field("", pattern=r"^([a-z_][a-z0-9_-]{0,31})?$")
    notes: str = ""
    # Provenance of an engine actually built/verified on the target; empty for manual profiles.
    engine_manifest: dict[str, Any] = Field(default_factory=dict)

    def missing(self) -> list[str]:
        """What must still be filled in before the engine can be used."""
        problems = []
        for field, label in (
            ("wrf_dir", tr("WRF directory", "Dossier de WRF")),
            ("wps_dir", tr("WPS directory", "Dossier de WPS")),
            ("geog_dir", tr("geography directory", "Dossier de la géographie")),
            ("input_dir", tr("input data directory", "Dossier des données d'entrée")),
        ):
            value = getattr(self.install, field)
            # Written into namelist.wps, which Fortran reads without expanding ~ or $HOME
            absolute_only = field in ("wps_dir", "geog_dir")
            if not value:
                problems.append(tr(f"{label} not set", f"{label} non renseigné"))
            elif not value.startswith(("/",) if absolute_only else ("/", "~", "$")):
                problems.append(
                    tr(
                        f"{label} must be an absolute Linux path (starting with /), not {value!r}",
                        f"{label} doit être un chemin Linux absolu (commençant par /), pas {value!r}",
                    )
                )
        if self.kind == "wsl" and not self.wsl_distro:
            problems.append(tr("WSL distribution not set", "Distribution WSL non renseignée"))
        if "{ranks}" not in self.resources.mpi_command:
            problems.append(
                tr("the MPI command must contain {ranks}", "la commande MPI doit contenir {ranks}")
            )
        return problems


# Fields of older SSH/Slurm profiles and of launching runs, left out of old settings
REMOVED_PROFILE_FIELDS = ("docker", "ssh", "slurm", "max_concurrent_runs", "clean_work_files")
REMOVED_RESOURCE_FIELDS = ("mpi_ranks", "threads", "memory_gb", "walltime")


def without_removed_fields(profile: dict[str, Any]) -> dict[str, Any]:
    """A saved profile without the fields of what the application no longer does."""
    kept = {k: v for k, v in profile.items() if k not in REMOVED_PROFILE_FIELDS}
    if isinstance(kept.get("resources"), dict):
        kept["resources"] = {
            k: v for k, v in kept["resources"].items() if k not in REMOVED_RESOURCE_FIELDS
        }
    return kept


def seen_here(profile: ComputeProfile, folder: str) -> Path | None:
    """A Linux folder of an engine as this computer sees it: inside the WSL distribution of a
    WSL engine, or the folder itself for an engine on this Linux computer; None for another
    machine."""
    if not folder:
        return None
    if profile.kind == "wsl" and profile.wsl_distro:
        return Path("\\\\wsl.localhost\\" + profile.wsl_distro + folder.replace("/", "\\"))
    if profile.kind == "local":
        return Path(folder).expanduser()
    return None


def wsl_profile_template(distro: str, home: str) -> ComputeProfile:
    """Suggested paths for a WSL distribution where WRF and WPS were built in the home folder."""
    return ComputeProfile(
        id=re.sub(r"[^a-z0-9-]+", "-", f"wsl-{distro.lower()}")[:40].strip("-"),
        name=f"WSL {distro}",
        kind="wsl",
        wsl_distro=distro,
        install=EngineInstall(
            wrf_dir=f"{home}/WRF",
            wps_dir=f"{home}/WPS",
            geog_dir=f"{home}/WPS_GEOG",
            input_dir=f"{home}/donnees",
        ),
    )
