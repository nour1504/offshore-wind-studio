"""Local engine on Windows: a dedicated WSL distribution, prepared only when the engine wizard
asks for it (never at application start). On Linux, this computer is the Linux itself: the engine
installs natively in a chosen Linux folder (profile kind "local"), with nothing to prepare.

The distribution, OffshoreWindStudio-WRF (Ubuntu 24.04 from Microsoft's official WSL catalogue),
lives in a folder the user chooses, with a non-root Linux user, owstudio. Other distributions are
never touched. When WSL itself is missing, Windows asks for
administrator approval to enable it and may need a restart.
"""

import base64
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from owstudio.core.engine.install import InstallJob, kit_files
from owstudio.core.engine.shells import CREATE_NO_WINDOW, WslShell, usable_distribution
from owstudio.core.i18n import tr

MANAGED_DISTRO = "OffshoreWindStudio-WRF"
MANAGED_USER = "owstudio"
UBUNTU = "Ubuntu-24.04"
MARKER = ".ows-wsl-managed.json"
# --name and --location of wsl --install exist from WSL 2.4.4
MINIMUM_WSL = (2, 4, 4)
BOOTSTRAP = f"""set -e
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl bzip2 gzip tar xz-utils util-linux procps python3
id -u {MANAGED_USER} >/dev/null 2>&1 || useradd --create-home --shell /bin/bash {MANAGED_USER}
printf '[user]\\ndefault={MANAGED_USER}\\n' > /etc/wsl.conf
"""


def _decode(content: bytes) -> str:
    if content.startswith((b"\xff\xfe", b"\xfe\xff")) or b"\x00" in content[:200]:
        return content.decode("utf-16-le", errors="replace").replace("﻿", "")
    return content.decode("utf-8", errors="replace")


def wsl_command(arguments: list[str], timeout: float = 30) -> tuple[int, str]:
    result = subprocess.run(
        ["wsl.exe", *arguments], capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL,
        check=False, creationflags=CREATE_NO_WINDOW,
    )  # fmt: skip
    text = "\n".join(
        part for part in (_decode(result.stdout).strip(), _decode(result.stderr).strip()) if part
    )
    return result.returncode, text


def wsl_version(text: str) -> tuple[int, ...] | None:
    """The WSL version from 'wsl --version' (localised labels, first dotted number)."""
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", text)
    return tuple(int(part) for part in match.groups()) if match else None


def status() -> dict[str, Any]:
    result: dict[str, Any] = {
        "platform": sys.platform, "available": False, "ready": False, "version": None,
        "version_ok": False, "distributions": [], "managed_distro": MANAGED_DISTRO,
        "managed_user": MANAGED_USER, "managed_exists": False, "managed_folder": None, "error": None,
        "native": sys.platform.startswith("linux"),
    }  # fmt: skip
    if result["native"]:
        # Nothing to enable or create: the installer uses the chosen native Linux folder.
        result["available"] = result["ready"] = result["version_ok"] = True
        return result
    if sys.platform != "win32" or shutil.which("wsl.exe") is None:
        return result
    result["available"] = True
    try:
        code, output = wsl_command(["--version"], 15)
        version = wsl_version(output) if code == 0 else None
        result["version"] = ".".join(map(str, version)) if version else None
        result["version_ok"] = bool(version and version >= MINIMUM_WSL)
        code, output = wsl_command(["--list", "--quiet"], 15)
        if code == 0:
            names = [line.strip() for line in output.splitlines() if line.strip()]
            result["distributions"] = [n for n in names if usable_distribution(n)]
            result["managed_exists"] = MANAGED_DISTRO in names
            result["managed_folder"] = distribution_folder(MANAGED_DISTRO)
        code, output = wsl_command(["--status"], 15)
        result["ready"] = code == 0 and result["version_ok"]
        if code != 0:
            result["error"] = output[-2000:]
    except (OSError, subprocess.TimeoutExpired) as error:
        result["error"] = str(error)
    return result


def owning_folder(distribution: str | None) -> Path | None:
    """The folder the application chose for its distribution, whose virtual disk is in
    ``<folder>/distro``: known by the application's marker there, else None."""
    if not distribution:
        return None
    home = Path(distribution).parent
    try:
        marker = json.loads((home / MARKER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return home if isinstance(marker, dict) and marker.get("distro") == MANAGED_DISTRO else None


def distribution_folder(name: str) -> str | None:
    """Where WSL keeps a distribution's virtual disk (HKCU Lxss registry key BasePath)."""
    if sys.platform != "win32":
        return None
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Lxss"
        ) as lxss:
            for index in range(winreg.QueryInfoKey(lxss)[0]):
                with winreg.OpenKey(lxss, winreg.EnumKey(lxss, index)) as key:
                    if winreg.QueryValueEx(key, "DistributionName")[0] == name:
                        base = str(winreg.QueryValueEx(key, "BasePath")[0])
                        return base.removeprefix("\\\\?\\")
    except OSError:
        return None
    return None


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _enable_wsl(scratch: Path, job: InstallJob) -> str:
    """Runs the Windows part with administrator approval; returns ready or needs_restart."""
    job.write("Enabling WSL: Windows asks for administrator approval and may need a restart.")
    scratch.mkdir(parents=True, exist_ok=True)
    helper = scratch / "enable-wsl.ps1"
    helper.write_bytes(kit_files("windows")["enable-wsl.ps1"])
    result_path = scratch / "wsl-result.json"
    result_path.unlink(missing_ok=True)
    invocation = f"& {_ps_quote(str(helper))} -ResultFile {_ps_quote(str(result_path))}"
    encoded = base64.b64encode(invocation.encode("utf-16-le")).decode("ascii")
    # EncodedCommand keeps the literal paths intact through the elevation prompt
    script = (
        "$ErrorActionPreference='Stop'; Start-Process -FilePath 'powershell.exe' -Verb RunAs -WindowStyle Hidden "
        "-ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-EncodedCommand',"
        + _ps_quote(encoded)
        + ")"
    )
    launched = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script], capture_output=True, text=True,
        timeout=180, check=False, creationflags=CREATE_NO_WINDOW,
    )  # fmt: skip
    if launched.returncode:
        raise RuntimeError(launched.stderr.strip() or "Administrator approval was not given")
    deadline = time.monotonic() + 1800
    while not result_path.is_file():
        if job.cancelled.is_set():
            raise RuntimeError("Cancelled")
        if time.monotonic() > deadline:
            raise RuntimeError(
                tr(
                    "Windows did not report the end of the WSL setup",
                    "Windows n'a pas signalé la fin de l'installation de WSL",
                )
            )
        time.sleep(2)
    result = json.loads(result_path.read_text(encoding="utf-8-sig"))
    if result["state"] == "failed":
        raise RuntimeError(result.get("error") or "WSL setup failed")
    return str(result["state"])


def prepare(folder: Path, scratch: Path, job: InstallJob) -> dict[str, Any]:
    """Creates (or reuses) the managed distribution in ``folder``."""
    if sys.platform != "win32":
        raise ValueError(
            tr(
                "The local WSL engine is prepared on Windows only",
                "Le moteur WSL local ne se prépare que sous Windows",
            )
        )
    folder = folder.expanduser()
    if not folder.is_absolute():
        raise ValueError(
            tr(
                "Choose an absolute Windows folder for the local engine",
                "Choisissez un dossier Windows absolu pour le moteur local",
            )
        )
    folder = folder.resolve()
    if folder == Path(folder.anchor) or folder.is_symlink():
        raise ValueError(
            tr(
                "Choose a dedicated folder for the local engine, not a drive root",
                "Choisissez un dossier dédié au moteur local, pas la racine d'un disque",
            )
        )
    marker = folder / MARKER
    current = status()
    if not current["available"] or not current["ready"]:
        if current["available"] and current["version"] and not current["version_ok"]:
            job.write(
                f"WSL {current['version']} is too old for a named distribution; updating WSL."
            )
            code, text = wsl_command(["--update", "--web-download"], 1800)
            job.write(text)
            if code:
                raise RuntimeError(
                    tr(
                        "WSL could not be updated: " + text[-1500:],
                        "WSL n'a pas pu être mis à jour : " + text[-1500:],
                    )
                )
        else:
            state = _enable_wsl(scratch, job)
            if state == "needs_restart":
                return {"kind": "wsl", "state": "needs_restart", "folder": str(folder)}
        current = status()
        if not current["ready"]:
            raise RuntimeError(
                tr(
                    "WSL is still not ready: "
                    + str(current.get("error") or "restart Windows and try again"),
                    "WSL n'est toujours pas prêt : "
                    + str(current.get("error") or "redémarrez Windows et réessayez"),
                )
            )
    if current["managed_exists"]:
        # Reused where it was created, whatever folder the request names (the wizard hides
        # the folder once the distribution exists)
        owner = owning_folder(current.get("managed_folder"))
        if owner is None:
            raise ValueError(
                tr(
                    f"A WSL distribution named {MANAGED_DISTRO} exists but was not created by "
                    "Offshore Wind Studio: it is left untouched",
                    f"Une distribution WSL nommée {MANAGED_DISTRO} existe mais n'a pas été créée par Offshore Wind Studio : elle n'est pas modifiée",
                )
            )
        folder = owner
    else:
        owned = owning_folder(str(folder / "distro")) is not None
        if folder.is_dir() and any(folder.iterdir()) and not owned:
            raise ValueError(
                tr(
                    "This folder is not empty: choose an empty folder for the local engine",
                    "Ce dossier n'est pas vide : choisissez un dossier vide pour le moteur local",
                )
            )
        folder.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            json.dumps({"distro": MANAGED_DISTRO, "user": MANAGED_USER}), encoding="utf-8"
        )
        job.progress = 0.1
        job.write(f"Downloading {UBUNTU} from Microsoft's WSL catalogue into {folder / 'distro'}")
        code, text = wsl_command(
            ["--install", "--distribution", UBUNTU, "--name", MANAGED_DISTRO,
             "--location", str(folder / "distro"), "--no-launch", "--web-download"], 3600,
        )  # fmt: skip
        job.write(text)
        if code == 3010:
            return {"kind": "wsl", "state": "needs_restart", "folder": str(folder)}
        if code:
            raise RuntimeError(
                tr(
                    "The Linux distribution could not be installed: " + text[-2000:],
                    "La distribution Linux n'a pas pu être installée : " + text[-2000:],
                )
            )
    job.progress = 0.6
    job.write("Installing the basic tools and the non-administrator Linux user owstudio.")
    root_shell = WslShell(MANAGED_DISTRO, "root")
    bootstrap = root_shell.run(BOOTSTRAP, timeout=1800)
    job.write((bootstrap.stdout + bootstrap.stderr)[-6000:])
    if not bootstrap.ok:
        raise RuntimeError(
            tr(
                "Linux preparation failed: " + bootstrap.stderr[-2000:],
                "La préparation de Linux a échoué : " + bootstrap.stderr[-2000:],
            )
        )
    home = WslShell(MANAGED_DISTRO, MANAGED_USER).run('printf "%s" "$HOME"', timeout=60)
    if not home.ok or not home.stdout.strip().startswith("/"):
        raise RuntimeError(
            tr(
                "The Linux user owstudio is not available",
                "L'utilisateur Linux owstudio n'est pas disponible",
            )
        )
    job.progress = 1.0
    return {"kind": "wsl", "state": "ready", "folder": str(folder), "distro": MANAGED_DISTRO,
            "user": MANAGED_USER, "linux_home": home.stdout.strip()}  # fmt: skip
