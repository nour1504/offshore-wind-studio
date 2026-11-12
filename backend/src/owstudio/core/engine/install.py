"""Explicit engine installation (WRF 4.8.0 + WPS 4.7.0) on a Linux target: WSL or this Linux.

Only the kit (data/engine-kit) is sent; the target downloads and compiles the official sources and
the NCAR geography itself, WRF with wrf-tslist.patch (whether a wrf.exe has its outputs is read in
the program: TSLIST_TRACES). Nothing runs at application start. The worker runs detached and writes
its status on the target, so an install outlives the application; a receipt here lets it be followed
again instead of building twice. Cancelling stops only its own processes; the profile is set once
the engine is verified; older receipts still load.
"""

import json
import posixpath
import re
import shlex
import subprocess
import sys
import time
import uuid
import zipfile
from collections.abc import Callable, Collection
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field, model_validator

from owstudio.core.engine import commands
from owstudio.core.engine.commands import detach
from owstudio.core.engine.profiles import ComputeProfile, without_removed_fields
from owstudio.core.engine.shells import CREATE_NO_WINDOW, Shell, shell_for, usable_distribution
from owstudio.core.i18n import tr

ROOT_PATTERN = re.compile(r"^/[A-Za-z0-9_./-]+$")
ID_PATTERN = re.compile(r"^[a-f0-9]{12}$")
PROTECTED_ROOTS = {"/", "/usr", "/usr/local", "/opt", "/home", "/tmp", "/var", "/root", "/etc"}
# Peak disk use of each part, as install.sh checks it (bytes)
NEED_BUILD = 6_000_000_000
# Compiling WRF and WPS again in the folder of an engine: what the two trees take once compiled
# (1.1 GB measured) less what they hold already, and at least the room a compilation needs
NEED_TREES = 1_500_000_000
NEED_REBUILD = 500_000_000
NEED_LIBRARIES = 3_000_000_000
NEED_GEOGRAPHY = {"mandatory-high": 33_000_000_000, "mandatory-low": 1_000_000_000, "existing": 0}
NEED_COMPLEMENT = 6_000_000_000
FINAL_STATES = ("succeeded", "failed", "cancelled", "resumed")
ACTIVE_STATES = ("preparing", "queued", "running", "fetched", "monitor-interrupted")
# Consecutive observations of a missing worker before an installation is declared stopped
DEAD_CHECKS = 3
# Seconds between two looks at the target while following an installation
POLL_SECONDS = 5.0


def kit_files(target: Literal["linux", "windows"] = "linux") -> dict[str, bytes]:
    """The kit's files: the Linux kit (sent to targets, exported) leaves the Windows helper out."""
    folder = resources.files("owstudio.data").joinpath("engine-kit")
    files: dict[str, bytes] = {}
    for item in sorted(folder.iterdir(), key=lambda entry: entry.name):
        if not item.is_file():
            continue
        name = item.name.removesuffix(".txt") if item.name.endswith(".py.txt") else item.name
        if (target == "linux") == name.endswith(".ps1"):
            continue
        files[name] = item.read_bytes().replace(b"\r\n", b"\n")
    return files


def spec() -> dict[str, Any]:
    value: dict[str, Any] = json.loads(kit_files()["spec.json"])
    return value


def family() -> str:
    """The engine without its recipe number (wrf4.8.0-wps4.7.0-gnu13): a folder or an engine of
    another recipe of the same versions is brought to this one, in place."""
    return str(spec()["id"]).rsplit("-v", 1)[0]


def same_family(engine_id: object) -> bool:
    return re.fullmatch(re.escape(family()) + r"-v\d+", str(engine_id or "")) is not None


def catalog() -> dict[str, Any]:
    value = spec()
    value["kit_bytes"] = sum(len(content) for content in kit_files().values())
    return value


def complements_for(physics: dict[str, Any]) -> list[str]:
    """Geography complements the physics options need (official NCAR list of special datasets).
    ``physics`` maps option names to values (scalars or per-domain lists)."""
    needed = []
    for complement in spec()["complements"]:
        for option, value in complement["when"]:
            current = physics.get(option)
            values = current if isinstance(current, list) else [current]
            if any(str(v).strip().lower() == value for v in values if v is not None):
                needed.append(complement["id"])
                break
    return needed


def export_kit(path: Path) -> Path:
    """The kit as a ZIP for a manual installation: recipe and helpers only, no binary."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in kit_files().items():
            info = zipfile.ZipInfo(f"OffshoreWindStudio-engine/{name}")
            info.external_attr = (0o100755 if name.endswith((".sh", ".py")) else 0o100644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content)
        # In the language of the window that asks for it
        archive.writestr(
            f"OffshoreWindStudio-engine/{tr('README.txt', 'LISEZ-MOI.txt')}",
            tr(KIT_README, KIT_LISEZ_MOI),
        )
    temporary.replace(path)
    return path


KIT_README = """Offshore Wind Studio engine kit: WRF 4.8.0 + WPS 4.7.0 (GNU, dmpar) for Linux x86_64.

This folder holds only the recipe: the installer downloads the official sources, the
libraries (conda-forge) and the NCAR static geography on the target machine itself.

WRF is compiled with wrf-tslist.patch, applied to the official sources: its time series
(tslist) write five more values at the end of each .TS line (RMOL, BR, UST, PBLH and the
POWER of the grid cell in kW, 0 without a wind farm parameterization) and one more profile
file, .TK (the TKE at each level: QKE/2 with MYNN, TKE_PBL with MYJ, QNSE and BouLac).
Nothing else changes.

The application installs it itself (Compute page, Install). By hand, on the target:

  bash install.sh --root $HOME/OffshoreWindStudioEngine --jobs 8 --geography mandatory-high

Options: --mode system (use the cluster's compilers, MPI and NetCDF modules instead of the
managed libraries), --geography mandatory-low (tests and teaching only) or existing with
--geog-path /path/to/WPS_GEOG, --extra ID for a complement of special physics options
(see spec.json). Needs about 45 GB with the high-resolution geography. Re-running the same
command resumes an interrupted installation; with --fresh it compiles WRF and WPS again from
their official sources. Then point a compute profile at the folder.
"""

KIT_LISEZ_MOI = """Kit du moteur d'Offshore Wind Studio : WRF 4.8.0 + WPS 4.7.0 (GNU, dmpar) pour Linux x86_64.

Ce dossier ne contient que la recette : l'installateur télécharge les sources officielles, les
bibliothèques (conda-forge) et la géographie statique du NCAR sur la machine cible elle-même.

WRF est compilé avec wrf-tslist.patch, appliqué aux sources officielles : ses séries
temporelles (tslist) écrivent cinq valeurs de plus à la fin de chaque ligne .TS (RMOL, BR, UST,
PBLH et le POWER de la maille en kW, 0 sans paramétrisation des parcs) et un fichier de profil
de plus, .TK (la TKE à chaque niveau : QKE/2 avec MYNN, TKE_PBL avec MYJ, QNSE et BouLac).
Rien d'autre ne change.

Le logiciel l'installe lui-même (page Calcul, Installer). À la main, sur la cible :

  bash install.sh --root $HOME/OffshoreWindStudioEngine --jobs 8 --geography mandatory-high

Options : --mode system (compilateurs, MPI et NetCDF des modules du cluster au lieu des
bibliothèques gérées), --geography mandatory-low (essais et enseignement seulement) ou existing
avec --geog-path /chemin/vers/WPS_GEOG, --extra ID pour un complément d'options de physique
particulières (voir spec.json). Environ 45 Go avec la géographie haute résolution. Relancer la
même commande reprend une installation interrompue ; avec --fresh, WRF et WPS sont compilés de
nouveau depuis leurs sources officielles. Reste à désigner ce dossier dans un profil de calcul.
"""

# What wrf-tslist.patch leaves in a compiled wrf.exe: the format of the longer .TS line, and
# the name of the TKE profile array (in the message of a failed allocation). A wrf.exe of the
# 0.7.4 patch (ts_qke_profile, .QK files) lacks the second: it is compiled again
TSLIST_TRACES = ("18(f13.5,1x),f13.2", "ts_tke_profile")


def has_tslist_outputs(exe: str) -> str:
    """Shell test, true when the wrf.exe at ``exe`` (a shell word) writes the outputs of
    wrf-tslist.patch."""
    return " && ".join(f"grep -a -q -F -e {shlex.quote(t)} {exe}" for t in TSLIST_TRACES)


def validate_root(root: str) -> str:
    root = root.rstrip("/") or "/"
    if not ROOT_PATTERN.fullmatch(root) or root in PROTECTED_ROOTS or ".." in root.split("/"):
        raise ValueError(
            tr(
                "Use a dedicated absolute Linux folder without spaces or '..'.",
                "Utiliser un dossier Linux absolu dédié, sans espace ni '..'.",
            )
        )
    return root


class InstallRequest(BaseModel):
    profile: ComputeProfile
    # Linux folder of the engine; empty: ~/OffshoreWindStudioEngine/<engine id> on the target
    root: str = ""
    jobs: int = Field(4, ge=1, le=128)
    dependency_mode: Literal["managed", "system"] = "managed"
    geography: Literal["mandatory-high", "mandatory-low", "existing"] = "mandatory-high"
    geog_path: str = ""
    extras: list[str] = Field(default_factory=list)
    # Reinstallation of the engine of a profile: WRF and WPS are compiled again from their
    # official sources, and the profile keeps its own data folder and MPI command
    fresh: bool = False

    @model_validator(mode="after")
    def valid_target(self) -> "InstallRequest":
        if self.root:
            self.root = validate_root(self.root)
        if self.profile.kind == "wsl" and (not usable_distribution(self.profile.wsl_distro)):
            raise ValueError(
                tr(
                    "Choose a WSL distribution of your own, or prepare local Linux first.",
                    "Choisir une distribution WSL, ou préparer d'abord le Linux local.",
                )
            )
        if self.geography == "existing":
            if not self.geog_path.startswith("/") or any(
                c in self.geog_path for c in "\x00\n\r'\""
            ):
                raise ValueError(
                    tr(
                        "Give the absolute Linux path of the existing geography folder.",
                        "Indiquer le chemin Linux absolu du dossier de géographie existant.",
                    )
                )
            if self.extras:
                raise ValueError(
                    tr(
                        "Complements are added only to a geography folder installed by the application.",
                        "Les compléments ne s'ajoutent qu'à un dossier de géographie installé par le logiciel.",
                    )
                )
        known = {c["id"] for c in spec()["complements"]}
        unknown = [e for e in self.extras if e not in known]
        if unknown:
            raise ValueError(
                tr(
                    f"Unknown geography complement: {', '.join(unknown)}",
                    f"Complément de géographie inconnu : {', '.join(unknown)}",
                )
            )
        self.extras = sorted(set(self.extras))
        return self

    def options(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"profile"})


class InstallJob(Protocol):
    progress: float

    def write(self, line: str) -> None: ...

    @property
    def cancelled(self) -> Any: ...


def environment(profile: ComputeProfile) -> str:
    """Commands run before anything on the target: the profile's own setup."""
    lines = ["set -e", "export LC_ALL=C"]
    if profile.install.env_setup.strip():
        lines.append(profile.install.env_setup.strip())
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- receipts


def receipt_folder(settings_path: Path) -> Path:
    return settings_path.parent / "engine-installations"


def save_receipt(folder: Path, receipt: dict[str, Any]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{receipt['id']}.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    temporary.replace(path)


def read_receipt(folder: Path, installation_id: str) -> dict[str, Any]:
    if not ID_PATTERN.fullmatch(installation_id):
        raise ValueError(
            tr("Invalid installation identifier", "Identifiant d'installation invalide")
        )
    path = folder / f"{installation_id}.json"
    if not path.is_file():
        raise FileNotFoundError(
            tr("Unknown engine installation", "Installation du moteur inconnue")
        )
    value: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return value


def list_receipts(folder: Path) -> list[dict[str, Any]]:
    if not folder.is_dir():
        return []
    receipts = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in folder.glob("*.json")
        if ID_PATTERN.fullmatch(path.stem)
    ]
    return sorted(receipts, key=lambda r: str(r.get("started_at", "")), reverse=True)


# ------------------------------------------------------------- the target


def _checked(shell: Shell, script: str, timeout: float = 120) -> str:
    result = shell.run(script, timeout=timeout)
    if not result.ok:
        raise RuntimeError(
            (
                result.stderr
                or result.stdout
                or tr("The target did not answer", "La cible n'a pas répondu")
            )[-5000:]
        )
    return result.stdout


def _values(output: str) -> dict[str, str]:
    found = {}
    for line in output.splitlines():
        key, sep, value = line.partition("=")
        if sep and re.fullmatch(r"OWS_[A-Z_]+", key):
            found[key.removeprefix("OWS_")] = value.strip()
    return found


def native_root() -> str:
    """The default engine folder on this Linux computer: the one an engine of this family
    already has there (it is brought to this recipe in place), else a new one."""
    base = Path.home() / "OffshoreWindStudioEngine"
    found = sorted(p for p in base.glob(f"{family()}-v*") if (p / ".ows-engine-owner").is_file())
    return str(found[-1] if found else base / spec()["id"])


def resolve_root(shell: Shell, body: InstallRequest) -> str:
    """The engine folder of a request; none given: the default one in the home folder of the
    target, where an engine of this family already there is found again."""
    if body.root:
        return validate_root(body.root)
    script = environment(body.profile) + (
        'printf "\\nOWS_HOME=%s\\n" "$HOME"\n'
        f'for d in "$HOME"/OffshoreWindStudioEngine/{shlex.quote(family())}-v*; do\n'
        '  if [ -f "$d/.ows-engine-owner" ]; then printf "OWS_ENGINE=%s\\n" "$d"; fi\n'
        "done\n"
    )
    found = _values(_checked(shell, script, 30))
    home = found.get("HOME", "")
    if not home.startswith("/"):
        raise RuntimeError(
            tr(
                "Could not find the Linux home folder on the target",
                "Dossier personnel Linux introuvable sur la cible",
            )
        )
    return validate_root(found.get("ENGINE") or f"{home}/OffshoreWindStudioEngine/{spec()['id']}")


PROBE = r"""
r={root}
printf '\nOWS_SYSTEM=%s %s\n' "$(uname -s)" "$(uname -m)"
printf 'OWS_GLIBC=%s\n' "$(ldd --version 2>/dev/null | head -n 1 | awk '{{print $NF}}')"
printf 'OWS_CPUS=%s\n' "$(env -u OMP_NUM_THREADS -u OMP_THREAD_LIMIT nproc 2>/dev/null || echo 1)"
printf 'OWS_MEMORY_KB=%s\n' "$(awk '/MemTotal/ {{print $2}}' /proc/meminfo 2>/dev/null)"
missing=""
for t in curl tar gzip sha256sum flock df stat python3; do command -v "$t" >/dev/null || missing="$missing $t"; done
printf 'OWS_MISSING=%s\n' "$missing"
site=""
for t in gcc gfortran cpp mpicc mpif90 mpirun nc-config nf-config git make perl m4 csh; do command -v "$t" >/dev/null || site="$site $t"; done
printf 'OWS_SITE_MISSING=%s\n' "$site"
printf 'OWS_PYTHON=%s\n' "$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)"
if [ -e "$r" ]; then
  if [ -z "$(ls -A "$r" 2>/dev/null)" ]; then s=empty
  else
    # A folder of another recipe of the same engine is ours too: its WRF is brought to this one
    case "$(cat "$r/.ows-engine-owner" 2>/dev/null)" in
      {family}-v[0-9]*)
        s=ours
        # An installation working in the folder holds its lock
        if [ -e "$r/.install.lock" ] && command -v flock >/dev/null && ! flock -n "$r/.install.lock" true; then s=busy; fi;;
      *) s=foreign;;
    esac
  fi
else s=absent; fi
printf 'OWS_ROOT_STATE=%s\n' "$s"
for m in runtime/.ows-ready WRF/.ows-cloned WPS/.ows-cloned WRF/.ows-built WPS/.ows-built geography/mandatory-high/.ows-geog-ready geography/mandatory-low/.ows-geog-ready engine-manifest.json; do
  [ -e "$r/$m" ] && printf 'OWS_HAS=%s\n' "$m"
done
for m in "$r"/geography/.extra-*; do
  [ -e "$m" ] && printf 'OWS_HAS=geography/%s\n' "${{m##*/}}"
done
# The time series outputs, read in the compiled program itself
if [ -f "$r/WRF/main/wrf.exe" ] && {tslist}; then printf 'OWS_HAS=%s\n' WRF/tslist-outputs; fi
# The geography next to the engine (geog/, NCAR's folder names) counts as the engine's own
g="$(dirname "$r")/geog"
[ -e "$g/WPS_GEOG/.ows-geog-ready" ] && printf 'OWS_HAS=%s\n' geography/mandatory-high/.ows-geog-ready
[ -e "$g/WPS_GEOG_LOW_RES/.ows-geog-ready" ] && printf 'OWS_HAS=%s\n' geography/mandatory-low/.ows-geog-ready
p="$r"; while [ ! -d "$p" ]; do p=$(dirname "$p"); done
printf 'OWS_FREE=%s\n' "$(df -Pk "$p" | awk 'NR==2 {{printf "%.0f", $4 * 1024}}')"
# What the WRF and WPS folders take today: compiled again in place, they need little more
printf 'OWS_HELD=%s\n' "$({{ du -sk "$r/WRF" "$r/WPS" 2>/dev/null || true; }} | awk '{{n += $1}} END {{printf "%.0f", n * 1024}}')"
for u in https://github.com https://api.anaconda.org https://www2.mmm.ucar.edu; do
  c=$(curl -s -o /dev/null -I --max-time 15 -w '%{{http_code}}' "$u" 2>/dev/null)
  case "$c" in 2*|3*) printf 'OWS_NET=%s ok\n' "$u";; *) printf 'OWS_NET=%s %s\n' "$u" "${{c:-000}}";; esac
done
"""


def needed_bytes(body: InstallRequest, present: set[str], held: int = 0) -> int:
    """The free space an installation needs; ``held`` is what the WRF and WPS folders of the
    engine take today."""
    need = 0
    if body.fresh:
        # Compiled again where they are: the two trees take about the room they hold already
        need += max(NEED_TREES - held, NEED_REBUILD)
    elif "WRF/.ows-built" not in present or "WPS/.ows-built" not in present:
        need += NEED_BUILD
    if body.dependency_mode == "managed" and "runtime/.ows-ready" not in present:
        need += NEED_LIBRARIES
    if f"geography/{body.geography}/.ows-geog-ready" not in present:
        need += NEED_GEOGRAPHY[body.geography]
    return need + NEED_COMPLEMENT * sum(f"geography/.extra-{e}" not in present for e in body.extras)


def preflight(
    body: InstallRequest, shell: Shell | None = None, uploaded: Collection[str] = ()
) -> dict[str, Any]:
    """What the target offers before an installation: system, tools, space, network, folder.
    A geography sent from this computer (``uploaded``) needs no access to NCAR."""
    shell = shell or shell_for(body.profile)
    root = resolve_root(shell, body)
    script = environment(body.profile).replace("set -e\n", "") + PROBE.format(
        root=shlex.quote(root),
        family=shlex.quote(family()),
        tslist=has_tslist_outputs('"$r/WRF/main/wrf.exe"'),
    )
    output = _checked(shell, script, 90)
    values: dict[str, Any] = {}
    present: set[str] = set()
    # "ok", or the HTTP code of the answer ("403" behind a proxy, "000" without any answer)
    network: dict[str, str] = {}
    for line in output.splitlines():
        key, sep, value = line.partition("=")
        if not sep:
            continue
        if key == "OWS_HAS":
            present.add(value.strip())
        elif key == "OWS_NET":
            url, _, state = value.strip().rpartition(" ")
            network[url] = state
        elif re.fullmatch(r"OWS_[A-Z_]+", key):
            values[key.removeprefix("OWS_")] = value.strip()
    checks: list[dict[str, str]] = []

    def check(status: str, key: str, detail: str) -> None:
        checks.append({"status": status, "key": key, "detail": detail})

    system = values.get("SYSTEM", "")
    check("ok" if system == "Linux x86_64" else "fail", "system", system or "unknown")
    missing = values.get("MISSING", "").split()
    check("fail" if missing else "ok", "tools", " ".join(missing))
    python = values.get("PYTHON", "")
    major_minor = (
        tuple(int(p) for p in python.split(".")) if re.fullmatch(r"\d+\.\d+", python) else (0, 0)
    )
    check("ok" if major_minor >= (3, 6) else "fail", "python", python or "absent")
    if body.dependency_mode == "system":
        site = values.get("SITE_MISSING", "").split()
        check("fail" if site else "ok", "site_libraries", " ".join(site))
    state = values.get("ROOT_STATE", "")
    check("fail" if state in ("foreign", "busy") else "ok", "folder", state)
    need = needed_bytes(body, present, int(values.get("HELD") or 0))
    free = int(values.get("FREE") or 0)
    check("ok" if free >= need else "fail", "space", f"{free}/{need}")
    downloads = [f"{u.split('//')[-1]} {code}" for u, code in network.items() if code != "ok"]
    # A server is needed only for what is still to download from it
    geography_there = (
        body.geography == "existing"
        or body.geography in uploaded
        or f"geography/{body.geography}/.ows-geog-ready" in present
    )
    if geography_there and all(f"geography/.extra-{e}" in present for e in body.extras):
        downloads = [u for u in downloads if "ucar" not in u]
    if body.dependency_mode == "system" or "runtime/.ows-ready" in present:
        downloads = [u for u in downloads if "anaconda" not in u]
    if {"WRF/.ows-cloned", "WPS/.ows-cloned"} <= present:
        downloads = [u for u in downloads if "github" not in u]
    check("fail" if downloads else "ok", "network", " ".join(downloads))
    cpus = int(values.get("CPUS") or 1)
    return {
        "root": root,
        "checks": checks,
        "ready": not any(c["status"] == "fail" for c in checks),
        "free_bytes": free,
        "needed_bytes": need,
        "cpus": cpus,
        "memory_bytes": int(values.get("MEMORY_KB") or 0) * 1024,
        "glibc": values.get("GLIBC", ""),
        "present": sorted(present),
        "suggested_jobs": max(1, min(cpus, 32)),
        "blocked": [u for u, code in network.items() if code != "ok"],
    }


# --------------------------------------------------------- geography sent from this computer


def uploads_folder(settings_path: Path) -> Path:
    """Geography archives sent from the browser, kept until an installation takes them."""
    return settings_path.parent / "engine-uploads"


def archive_name(geography: str) -> str:
    """The NCAR archive of a geography choice (geog_low_res_mandatory.tar.gz...)."""
    for choice in spec()["geography"]:
        if choice["id"] == geography and choice.get("url"):
            return str(choice["url"]).rsplit("/", 1)[-1]
    raise ValueError(tr(f"No archive for {geography}", f"Pas d'archive pour {geography}"))


def uploaded(settings_path: Path) -> dict[str, int]:
    """The geography choices whose whole archive was sent (its size is the NCAR one)."""
    found = {}
    for choice in spec()["geography"]:
        if not choice.get("url"):
            continue
        path = uploads_folder(settings_path) / archive_name(choice["id"])
        if path.is_file() and path.stat().st_size == int(choice["download_bytes"]):
            found[choice["id"]] = path.stat().st_size
    return found


FIND_GEOGRAPHY = r"""
for base in "$HOME" /app /data /opt /srv /scratch /mnt/data; do
  [ -d "$base" ] || continue
  timeout 20 find "$base" -maxdepth 6 -type f -path '*/topo_gmted2010_*/index' 2>/dev/null
done | sed -E 's#/topo_gmted2010_(30s|5m)/index$# \1#' | sort -u
"""


def find_geography(shell: Shell) -> list[dict[str, Any]]:
    """WPS_GEOG folders already on a machine (home, /app, /data...), with their resolutions:
    "default" (30 s topography) and "lowres" (5 min)."""
    done = shell.run(FIND_GEOGRAPHY, timeout=90)
    folders: dict[str, set[str]] = {}
    for line in done.stdout.splitlines():
        folder, _, size = line.strip().rpartition(" ")
        if folder.startswith("/"):
            folders.setdefault(folder, set()).add("default" if size == "30s" else "lowres")
    return [{"path": f, "resolutions": sorted(r)} for f, r in sorted(folders.items())]


def install_command(root: str, installation_id: str, options: dict[str, Any], stage: str) -> str:
    args = [
        "bash", f"{root}/installer/{installation_id}/install.sh", "--root", root,
        "--jobs", str(options["jobs"]), "--mode", options["dependency_mode"],
        "--geography", options["geography"], "--task-id", installation_id, "--stage", stage,
    ]  # fmt: skip
    if options.get("geog_path"):
        args += ["--geog-path", options["geog_path"]]
    for extra in options.get("extras", []):
        args += ["--extra", extra]
    if options.get("fresh"):
        args.append("--fresh")
    return shlex.join(args)


def _launch_detached(
    shell: Shell,
    profile: ComputeProfile,
    root: str,
    installation_id: str,
    options: dict[str, Any],
    stage: str,
) -> None:
    task = f"{root}/.install-runs/{installation_id}"
    q = shlex.quote
    # setsid makes the worker a session leader: its process group is exactly this installation
    launched = q(task + "/launcher.pid")
    command = f"echo $$ > {launched}; exec {install_command(root, installation_id, options, stage)}"
    script = environment(profile) + (
        f"command -v setsid >/dev/null\ncd {q(root)}\nrm -f {launched}\n"
        + detach(command, q(task + "/install.log"), launched)
    )
    _checked(shell, script, 60)


def keep_wsl_alive(profile: ComputeProfile, root: str, installation_id: str) -> None:
    """WSL may stop a distribution once no Windows program uses it: a small companion keeps it
    running while the installation's worker lives, even if the application closes."""
    if profile.kind != "wsl" or sys.platform != "win32":
        return
    task = f"{root}/.install-runs/{installation_id}"
    watch = (
        f"sleep 20; while pid=$(cat {shlex.quote(task + '/worker.pid')} 2>/dev/null) "
        f'&& kill -0 "$pid" 2>/dev/null; do sleep 30; done'
    )
    command = ["wsl.exe", "-d", profile.wsl_distro]
    if profile.wsl_user:
        command += ["-u", profile.wsl_user]
    detached = 0x00000008  # DETACHED_PROCESS: survives the application
    subprocess.Popen(
        [*command, "--exec", "bash", "-c", watch],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=CREATE_NO_WINDOW | detached,
    )


def begin(
    body: InstallRequest,
    folder: Path,
    scratch: Path,
    job: InstallJob,
    shell: Shell | None = None,
    archive: Path | None = None,
    listed: Callable[[], None] | None = None,
) -> dict[str, Any]:
    """Prepares the folder, sends the kit (and the geography ``archive`` sent from this
    computer, which the worker then does not download) and starts the worker; returns the
    receipt. ``listed`` is called once the receipt is written: the installation is listed."""
    if body.profile.kind == "local" and sys.platform == "win32":
        raise ValueError(
            tr(
                "On Windows, a local engine runs in WSL",
                "Sous Windows, un moteur local tourne dans WSL",
            )
        )
    shell = shell or shell_for(body.profile)
    root = resolve_root(shell, body)
    installation_id = uuid.uuid4().hex[:12]
    engine = spec()["id"]
    options = body.options()
    stage = "all"
    receipt: dict[str, Any] = {
        "id": installation_id, "engine": engine, "root": root, "profile": body.profile.model_dump(mode="json"),
        "options": options, "state": "preparing", "progress": 0.0, "stage": "transfer", "detail": "",
        "phase": stage, "error": None, "started_at": datetime.now(UTC).isoformat(),
        "kit": f"{root}/installer/{installation_id}", "job_id": getattr(job, "id", None),
    }  # fmt: skip
    save_receipt(folder, receipt)
    if listed is not None:
        listed()
    q = shlex.quote
    try:
        job.write(f"Engine {engine} into {root} on {describe_target(body.profile)}")
        # Ownership is checked before anything is created or sent into the folder
        guard = (
            environment(body.profile)
            + f"""
r={q(root)}
test ! -L "$r" || {{ echo {q(tr("The installation folder is a symbolic link", "Le dossier d'installation est un lien symbolique"))} >&2; exit 2; }}
if test -d "$r" && test -n "$(ls -A "$r")"; then
  case "$(cat "$r/.ows-engine-owner" 2>/dev/null)" in
    {q(family())}-v[0-9]*) ;;
    *) echo {q(tr("This folder is not empty and belongs to something else: choose an empty folder", "Ce dossier n'est pas vide et sert à autre chose : choisir un dossier vide"))} >&2; exit 2;;
  esac
fi
mkdir -p "$r/installer/{installation_id}" "$r/.install-runs/{installation_id}"
printf '%s\\n' {q(engine)} > "$r/.ows-engine-owner"
printf '%s\\n' '{{"state":"queued","progress":0,"stage":"queued","detail":"","phase":"{stage}"}}' > "$r/.install-runs/{installation_id}/status.json"
"""
        )
        _checked(shell, guard)
        local = scratch / installation_id
        local.mkdir(parents=True, exist_ok=False)
        for name, content in kit_files().items():
            (local / name).write_bytes(content)
        sent = shell.upload(local, f"{root}/installer/{installation_id}")
        if not sent.ok:
            raise RuntimeError(
                sent.stderr
                or sent.stdout
                or tr("Could not send the kit", "Envoi du kit impossible")
            )
        if archive is not None and archive.is_file():
            job.write(f"Geography archive {archive.name} sent from this computer")
            sent = shell.upload(archive, f"{root}/downloads")
            if not sent.ok:
                raise RuntimeError(
                    sent.stderr
                    or sent.stdout
                    or tr("Could not send the geography", "Envoi de la géographie impossible")
                )
            archive.unlink()
        _launch_detached(shell, body.profile, root, installation_id, options, stage)
        keep_wsl_alive(body.profile, root, installation_id)
        receipt.update(state="running", stage="queued")
        save_receipt(folder, receipt)
        return receipt
    except Exception as error:
        receipt.update(state="failed", error=str(error))
        save_receipt(folder, receipt)
        raise


def describe_target(profile: ComputeProfile) -> str:
    if profile.kind == "wsl":
        return f"WSL {profile.wsl_distro}" + (
            f" (user {profile.wsl_user})" if profile.wsl_user else ""
        )
    return profile.kind


def _task(receipt: dict[str, Any]) -> str:
    root = validate_root(receipt["root"])
    if not ID_PATTERN.fullmatch(str(receipt["id"])):
        raise ValueError(
            tr("Invalid installation identifier", "Identifiant d'installation invalide")
        )
    return f"{root}/.install-runs/{receipt['id']}"


def _worker_check(receipt: dict[str, Any]) -> str:
    """Prints yes when this installation's worker is alive (pid checked against its command line)."""
    task = shlex.quote(_task(receipt))
    marker = shlex.quote(f"--task-id {receipt['id']}")
    return (
        f"pid=$(cat {task}/worker.pid 2>/dev/null || cat {task}/launcher.pid 2>/dev/null || true)\n"
        f'if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null && tr "\\0" " " < /proc/$pid/cmdline 2>/dev/null | grep -q -- {marker}; '
        f"then echo yes; else echo no; fi\n"
    )


def cancel_receipt(receipt: dict[str, Any], shell: Shell | None = None) -> None:
    """Stops this installation only: its own worker process group."""
    profile = ComputeProfile.model_validate(without_removed_fields(receipt["profile"]))
    shell = shell or shell_for(profile)
    task = _task(receipt)
    q = shlex.quote
    script = environment(profile).replace("set -e\n", "") + f"touch {q(task + '/cancel')}\n"
    script += f"""
pid=$(cat {q(task + "/worker.pid")} 2>/dev/null || cat {q(task + "/launcher.pid")} 2>/dev/null || true)
case "$pid" in ''|*[!0-9]*) exit 0;; esac
if [ "$pid" -gt 1 ] && tr '\\0' ' ' < /proc/$pid/cmdline 2>/dev/null | grep -q -- {q("--task-id " + str(receipt["id"]))}; then
  kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
fi
"""
    _checked(shell, script, 60)


def verified_manifest(receipt: dict[str, Any], shell: Shell | None = None) -> dict[str, Any]:
    profile = ComputeProfile.model_validate(without_removed_fields(receipt["profile"]))
    shell = shell or shell_for(profile)
    root = validate_root(receipt["root"])
    kit = validate_root(receipt.get("kit", f"{root}/installer/{receipt['id']}"))
    if not kit.startswith(root + "/installer/"):
        raise ValueError(tr("Unexpected kit folder", "Dossier du kit inattendu"))
    return verify_engine(profile, root, kit, shell)


def verify_engine(
    profile: ComputeProfile, root: str, kit: str, shell: Shell | None = None
) -> dict[str, Any]:
    """Checks an installed engine on its target: official commits, unchanged executables, linked
    libraries and geography; returns its manifest."""
    shell = shell or shell_for(profile)
    q = shlex.quote
    script = (
        # A folder whose engine was removed, or is being compiled again, holds no manifest
        f"[ -f {q(root + '/env.sh')} ] && [ -f {q(root + '/engine-manifest.json')} ]"
        " || { echo OWS_ENGINE=absent; exit 0; }\n"
        + environment(profile)
        + f"source {q(root + '/env.sh')}\npython3 {q(kit + '/manifest.py')} verify {q(root)} {q(kit)}\n"
    )
    output = _checked(shell, script, 300)
    if _values(output).get("ENGINE") == "absent":
        raise RuntimeError(
            tr("No complete engine in this folder", "Pas de moteur complet dans ce dossier")
        )
    manifest: dict[str, Any] = json.loads(output.strip().splitlines()[-1])
    # An engine built by another recipe of the same versions is checked as what it is: what its
    # WRF writes is read in wrf.exe (tslist_outputs)
    if (
        not same_family(manifest.get("id"))
        or manifest.get("prefix") != root
        or manifest.get("state") != "ready"
    ):
        raise RuntimeError(
            tr(
                "The engine manifest does not match this installation",
                "Le manifeste du moteur ne correspond pas à cette installation",
            )
        )
    return manifest


def manifest_summary(
    manifest: dict[str, Any], root: str, kit: str, installation_id: str
) -> dict[str, Any]:
    """What the profile keeps: versions and provenance, without the full package list (which
    stays on the target in engine-manifest.json and environment.lock)."""
    packages = {
        p.get("name"): p.get("version") for p in manifest.get("packages", []) if p.get("name")
    }
    keep = (
        "gfortran_linux-64",
        "gcc_linux-64",
        "openmpi",
        "libnetcdf",
        "netcdf-fortran",
        "hdf5",
        "python",
    )
    return {
        **{k: v for k, v in manifest.items() if k not in ("packages", "executables")},
        "packages": {name: packages[name] for name in keep if name in packages},
        "package_count": len(packages),
        "executables": sorted(manifest.get("executables", {})),
        "root": root,
        "kit": kit,
        "installation_id": installation_id,
    }


def configured_profile(receipt: dict[str, Any], manifest: dict[str, Any]) -> ComputeProfile:
    profile = ComputeProfile.model_validate(without_removed_fields(receipt["profile"])).model_copy(
        deep=True
    )
    root = validate_root(receipt["root"])
    kit = receipt.get("kit", f"{root}/installer/{receipt['id']}")
    # A reinstallation keeps what the profile had: its data folder and its MPI command
    again = bool((receipt.get("options") or {}).get("fresh"))
    profile.install.wrf_dir = f"{root}/WRF"
    profile.install.wps_dir = f"{root}/WPS"
    profile.install.geog_dir = manifest["geography"]["path"]
    # The shared folder of the input data sits next to the engine, like the geography
    profile.install.work_dir = ""
    if not (again and profile.install.input_dir):
        profile.install.input_dir = f"{posixpath.dirname(root)}/donnees"
    source = f"source {shlex.quote(root + '/env.sh')}"
    kept = [
        line
        for line in profile.install.env_setup.splitlines()
        if line.strip() and line.strip() != source
    ]
    # Site modules and the user's own lines first, then the engine's environment
    profile.install.env_setup = "\n".join([*kept, source])
    if manifest.get("dependency_mode") == "managed" and not again:
        profile.resources.mpi_command = "mpirun -np {ranks}"
    profile.engine_manifest = manifest_summary(manifest, root, kit, str(receipt["id"]))
    return profile


# ------------------------------------------- the engine of a profile: outputs, reinstall, remove

# What the installer builds in an engine folder. The geography, the input data, the calculations
# and anything else there are never removed
ENGINE_PARTS = (
    "WRF", "WPS", "runtime", "mamba", "bootstrap", "toolchain", "downloads", "installer",
    ".install-runs", "env.sh", "engine-manifest.json", "environment.lock",
)  # fmt: skip


def engine_root(profile: ComputeProfile) -> str:
    """The folder of the engine the application installed for this profile."""
    root = str(profile.engine_manifest.get("root") or "")
    if not root:
        raise ValueError(
            tr(
                "This profile points to an engine that was not installed by the application",
                "Ce profil désigne un moteur qui n'a pas été installé par le logiciel",
            )
        )
    return validate_root(root)


def tslist_outputs(profile: ComputeProfile, shell: Shell | None = None) -> str:
    """Whether the WRF of a profile writes the time series outputs of wrf-tslist.patch: "yes",
    "no", or "absent" without a wrf.exe. Read in the compiled program, whoever built it."""
    shell = shell or shell_for(profile)
    written = has_tslist_outputs('"$exe"')
    script = commands.environment(profile) + (
        'for exe in "$OWS_WRF/main/wrf.exe" "$OWS_WRF/run/wrf.exe"; do\n'
        '  [ -f "$exe" ] || continue\n'
        f"  if {written}; then echo OWS_TSLIST=yes; else echo OWS_TSLIST=no; fi\n"
        "  exit 0\n"
        "done\n"
        "echo OWS_TSLIST=absent\n"
    )
    found = _values(shell.run(script, timeout=60).stdout).get("TSLIST", "")
    if found not in ("yes", "no", "absent"):
        raise RuntimeError(tr("The engine did not answer", "Le moteur n'a pas répondu"))
    return found


def running_programs(profile: ComputeProfile, root: str, shell: Shell | None = None) -> list[str]:
    """The programs of the engine in ``root`` that are running on its machine (wrf.exe,
    real.exe, the managed mpirun...): a calculation uses the engine."""
    shell = shell or shell_for(profile)
    script = f"""export LC_ALL=C
r=$(cd -- {shlex.quote(validate_root(root))} 2>/dev/null && pwd -P) || exit 0
for p in /proc/[0-9]*; do
  exe=$(readlink "$p/exe" 2>/dev/null) || continue
  case "$exe" in "$r"/*) printf 'OWS_RUNNING=%s\\n' "${{exe##*/}}";; esac
done
exit 0
"""
    lines = _checked(shell, script, 60).splitlines()
    return sorted(
        {line.partition("=")[2].strip() for line in lines if line.startswith("OWS_RUNNING=")}
    )


class EngineBusy(RuntimeError):
    """The engine cannot be compiled again or removed now: a calculation uses it."""


def stop_if_running(profile: ComputeProfile, root: str, shell: Shell | None = None) -> None:
    running = running_programs(profile, root, shell)
    if running:
        names = ", ".join(running)
        raise EngineBusy(
            tr(
                f"The engine is running ({names}): wait for the end of the calculation",
                f"Le moteur tourne ({names}) : attendre la fin du calcul",
            )
        )


def remove_engine(profile: ComputeProfile, shell: Shell | None = None) -> None:
    """Removes what the installer built in the engine folder of a profile: WRF, WPS and the
    libraries. The geography, the input data, the calculations and anything else in the folder
    stay, and the folder keeps its owner mark for a reinstallation."""
    shell = shell or shell_for(profile)
    root = engine_root(profile)
    stop_if_running(profile, root, shell)
    q = shlex.quote
    parts = " ".join(q(part) for part in ENGINE_PARTS)
    script = f"""export LC_ALL=C
r={q(root)}
[ -d "$r" ] || exit 0
[ ! -L "$r" ] || {{ echo {q(tr("The engine folder is a symbolic link", "Le dossier du moteur est un lien symbolique"))} >&2; exit 2; }}
case "$(cat "$r/.ows-engine-owner" 2>/dev/null)" in
  {q(family())}-v[0-9]*) ;;
  *) echo {q(tr("This folder was not created by the engine installer", "Ce dossier n'a pas été créé par l'installateur du moteur"))} >&2; exit 2;;
esac
exec 9>"$r/.install.lock"
flock -n 9 || {{ echo {q(tr("An installation is working in this folder", "Une installation est en cours dans ce dossier"))} >&2; exit 3; }}
cd -- "$r" || exit 2
rm -rf -- {parts} 2>/dev/null || {{ chmod -R u+w -- {parts} 2>/dev/null; rm -rf -- {parts}; }}
"""
    _checked(shell, script, 1800)


def installed_jobs(profile: ComputeProfile, receipts: list[dict[str, Any]]) -> int | None:
    """The number of build jobs the engine of a profile was installed with, when its receipt is
    still there."""
    wanted = str(profile.engine_manifest.get("installation_id") or "")
    for receipt in receipts:
        if wanted and receipt.get("id") == wanted:
            jobs = (receipt.get("options") or {}).get("jobs")
            return int(jobs) if isinstance(jobs, int) and 1 <= jobs <= 128 else None
    return None


def reinstall_request(profile: ComputeProfile, jobs: int) -> InstallRequest:
    """The engine of a profile installed again in its folder, with what it was installed with
    (libraries, geography, complements): nothing to choose."""
    manifest = profile.engine_manifest
    root = engine_root(profile)
    geography = manifest.get("geography") or {}
    choice: Literal["mandatory-high", "mandatory-low", "existing"] = "existing"
    if geography.get("id") == "mandatory-high":
        choice = "mandatory-high"
    elif geography.get("id") == "mandatory-low":
        choice = "mandatory-low"
    again = profile.model_copy(deep=True)
    # The engine's own environment line comes back once the engine is there again
    source = f"source {shlex.quote(root + '/env.sh')}"
    again.install.env_setup = "\n".join(
        line for line in profile.install.env_setup.splitlines() if line.strip() != source
    )
    return InstallRequest(
        profile=again,
        root=root,
        jobs=jobs,
        dependency_mode="system" if manifest.get("dependency_mode") == "system" else "managed",
        geography=choice,
        geog_path=str(geography.get("path") or "") if choice == "existing" else "",
        extras=[] if choice == "existing" else list(geography.get("complements") or []),
        fresh=True,
    )


def old_data_folder(profile: ComputeProfile) -> tuple[str, str] | None:
    """For an engine installed before version 0.6.2: its data folder inside the engine
    (<engine>/input) and the shared one next to it (<parent>/donnees); None when up to date."""
    root = str(profile.engine_manifest.get("root") or "")
    if not root.startswith("/"):
        return None
    old = profile.install.input_dir.rstrip("/")
    if old not in ("", f"{root}/input", f"{root}/work"):
        return None
    return old or f"{root}/input", f"{posixpath.dirname(root)}/donnees"


def move_data_folder(profile: ComputeProfile, shell: Shell | None = None) -> ComputeProfile:
    """Moves the downloaded data of an engine from before 0.6.2 into the shared folder next to
    it, and points the profile there. A file already there is kept; the old folders go when
    empty."""
    found = old_data_folder(profile)
    if found is None:
        return profile
    old, new = found
    root = str(profile.engine_manifest["root"])
    q = shlex.quote
    # The input folder moves whole; the work folder holds old calculations too: only its
    # downloaded data (gfs, era5, sst) move
    work = root + "/work"
    data = [old] if old != work else []
    data += [root + "/input"]
    script = f"""set -e
new={q(new)}
mkdir -p "$new"
move() {{
  [ -d "$1" ] || return 0
  (cd "$1" && find . -type f) | while IFS= read -r file; do
    [ -e "$2/$file" ] && continue
    mkdir -p "$(dirname -- "$2/$file")"
    mv -- "$1/$file" "$2/$file"
  done
  find "$1" -depth -type d -empty -delete
}}
for old in {" ".join(q(folder) for folder in dict.fromkeys(data))}; do
  move "$old" "$new"
done
for source in gfs era5 sst; do
  move {q(work)}/"$source" "$new/$source"
done
test -w "$new"
"""
    _checked(shell or shell_for(profile), script, 600)
    updated = profile.model_copy(deep=True)
    updated.install.input_dir = new
    updated.install.work_dir = ""
    return updated


def _status_script(receipt: dict[str, Any], profile: ComputeProfile) -> str:
    task = shlex.quote(_task(receipt))
    script = environment(profile).replace("set -e\n", "")
    script += (
        f"cat {task}/status.json 2>/dev/null || true\nprintf '\\nOWS_ALIVE='\n"
        + _worker_check(receipt)
    )
    script += f"printf 'OWS_INSTALL_LOG\\n'\ntail -n 60 {task}/install.log 2>/dev/null || true\n"
    return script


def follow(
    receipt: dict[str, Any],
    folder: Path,
    job: InstallJob,
    on_ready: Callable[[ComputeProfile], None],
    shell: Shell | None = None,
) -> dict[str, Any]:
    """Follows the worker until the engine is verified and the profile configured."""
    profile = ComputeProfile.model_validate(without_removed_fields(receipt["profile"]))
    shell = shell or shell_for(profile)
    root = validate_root(receipt["root"])
    last_log = ""
    dead = 0
    try:
        while True:
            if job.cancelled.is_set():
                cancel_receipt(receipt, shell)
                receipt.update(state="cancelled", stage="cancelled")
                save_receipt(folder, receipt)
                raise RuntimeError(
                    tr("Engine installation cancelled", "Installation du moteur annulée")
                )
            output = _checked(shell, _status_script(receipt, profile), 60)
            head, _, log = output.partition("OWS_INSTALL_LOG\n")
            statuses = [line for line in head.splitlines() if line.startswith('{"state"')]
            facts = _values(head)
            if not statuses:
                raise RuntimeError(
                    tr(
                        "No installation status on the target: the folder may have been removed",
                        "Aucun état d'installation sur la cible : le dossier a peut-être été supprimé",
                    )
                )
            status = json.loads(statuses[-1])
            receipt.update(state=status["state"], progress=status.get("progress", 0), stage=status.get("stage", ""),
                           detail=status.get("detail", ""))  # fmt: skip
            job.progress = float(status.get("progress", 0))
            if log != last_log:
                new = log.removeprefix(last_log)
                if new.strip():
                    job.write(new.rstrip()[-8000:])
                last_log = log
            save_receipt(folder, receipt)
            state = status["state"]
            if state == "succeeded":
                manifest = verified_manifest(receipt, shell)
                configured = configured_profile(receipt, manifest)
                on_ready(configured)
                receipt.update(
                    manifest=configured.engine_manifest, finished_at=datetime.now(UTC).isoformat()
                )
                save_receipt(folder, receipt)
                return {"kind": "engine", "installation_id": receipt["id"], "profile_id": profile.id,
                        "manifest": configured.engine_manifest, "root": root}  # fmt: skip
            elif state in ("failed", "cancelled"):
                receipt["error"] = log[-5000:] or (
                    tr("The engine installation failed", "L'installation du moteur a échoué")
                    if state == "failed"
                    else tr(
                        "The engine installation was cancelled",
                        "L'installation du moteur a été annulée",
                    )
                )
                save_receipt(folder, receipt)
                raise RuntimeError(receipt["error"])
            else:
                if facts.get("ALIVE") == "yes":
                    dead = 0
                else:
                    dead += 1
                if dead >= DEAD_CHECKS:
                    tail = log.strip()[-3000:]
                    reason = tr(
                        "The installation stopped on the target (computer restarted, WSL or "
                        "connection closed, job ended). Resume it: it continues where it stopped.",
                        "L'installation s'est arrêtée sur la cible (ordinateur redémarré, WSL ou "
                        "connexion fermés, calcul terminé). La reprendre : elle repart où elle s'est arrêtée.",
                    )
                    receipt.update(state="failed", error=reason + (f"\n{tail}" if tail else ""))
                    save_receipt(folder, receipt)
                    raise RuntimeError(receipt["error"])
            time.sleep(POLL_SECONDS)
    except Exception as error:
        if receipt.get("state") not in FINAL_STATES:
            receipt["state"] = "monitor-interrupted"
        receipt["error"] = receipt.get("error") or str(error)
        save_receipt(folder, receipt)
        raise


def resume_request(
    receipt: dict[str, Any], changes: dict[str, Any] | None = None
) -> InstallRequest:
    """The same installation again: completed stages are kept on the target and skipped. The
    geography may be chosen again (``changes``: geography, geog_path, extras)."""
    options = dict(receipt.get("options") or {})
    options.update({k: v for k, v in (changes or {}).items() if v is not None})
    options["root"] = receipt["root"]
    return InstallRequest.model_validate({"profile": receipt["profile"], **options})
