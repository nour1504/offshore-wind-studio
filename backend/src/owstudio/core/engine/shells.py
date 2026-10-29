"""Run bash scripts and move files on the machine of the engine (WSL or this Linux computer).

Both kinds give the same small interface:

- run(script):       run a bash script to completion and capture its output
- upload(local, to): copy a local file or folder's content to an engine path
- download(from, local): copy an engine path (file or folder content) to this computer

The engine installation runs detached (commands.detach), so a closed application does not stop
it; its state is polled with run().
"""

import shlex
import subprocess
import sys
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from owstudio.core.engine.profiles import ComputeProfile
from owstudio.core.i18n import tr

# Windows: do not flash a console window for every command
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


@dataclass(frozen=True)
class Completed:
    code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.code == 0


def execute(
    command: list[str], timeout: float | None = None, input_text: str | None = None
) -> Completed:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            input=input_text,
            check=False,
            creationflags=CREATE_NO_WINDOW,
        )
    except FileNotFoundError as error:
        return Completed(127, "", f"{command[0]} not found: {error}")
    except subprocess.TimeoutExpired:
        return Completed(124, "", f"timed out after {timeout} s")
    return Completed(result.returncode, result.stdout, result.stderr)


class Shell(ABC):
    @abstractmethod
    def command(self, script: str) -> list[str]:
        """The command line running ``script`` with bash on the engine (for previews too)."""

    def run(self, script: str, timeout: float | None = 600) -> Completed:
        return execute(self.command(script), timeout)

    @abstractmethod
    def upload(self, local: Path, remote: str) -> Completed: ...

    @abstractmethod
    def download(self, remote: str, local: Path) -> Completed: ...


class LocalShell(Shell):
    """This computer, when the application runs on Linux."""

    def command(self, script: str) -> list[str]:
        return ["bash", "-lc", script]

    def upload(self, local: Path, remote: str) -> Completed:
        source = f"{shlex.quote(str(local))}/." if local.is_dir() else shlex.quote(str(local))
        return self.run(f"mkdir -p {shlex.quote(remote)} && cp -r {source} {shlex.quote(remote)}/")

    def download(self, remote: str, local: Path) -> Completed:
        local.mkdir(parents=True, exist_ok=True)
        return self.run(f"cp -r {shlex.quote(remote)}/. {shlex.quote(str(local))}/")


def windows_to_wsl(path: Path) -> str:
    """C:\\Users\\me\\data -> /mnt/c/Users/me/data (WSL's default automount)."""
    # A relative path is taken from this process's folder: WSL would read it from its own
    windows = PureWindowsPath(str(path.resolve() if path.is_absolute() else Path.cwd() / path))
    drive = windows.drive.rstrip(":").lower()
    rest = "/".join(windows.parts[1:])
    return f"/mnt/{drive}/{rest}" if drive else rest


class WslShell(Shell):
    """A Linux distribution of Windows Subsystem for Linux on this computer."""

    def __init__(self, distro: str, user: str = "") -> None:
        self.distro = distro
        self.user = user

    def command(self, script: str) -> list[str]:
        # --exec hands the arguments to bash as they are: with "--", wsl.exe first passes them
        # through the distribution's default shell, which expands $variables of the script
        return [
            "wsl.exe",
            "-d",
            self.distro,
            *(["-u", self.user] if self.user else []),
            "--exec",
            "bash",
            "-lc",
            script,
        ]

    def upload(self, local: Path, remote: str) -> Completed:
        source = windows_to_wsl(local)
        source = f"{shlex.quote(source)}/." if local.is_dir() else shlex.quote(source)
        return self.run(f"mkdir -p {shlex.quote(remote)} && cp -r {source} {shlex.quote(remote)}/")

    def download(self, remote: str, local: Path) -> Completed:
        local.mkdir(parents=True, exist_ok=True)
        target = shlex.quote(windows_to_wsl(local))
        return self.run(f"cp -r {shlex.quote(remote)}/. {target}/")


def shell_for(profile: ComputeProfile) -> Shell:
    if profile.kind == "wsl":
        return WslShell(profile.wsl_distro, profile.wsl_user)
    if profile.kind == "local":
        # On Windows, "bash" is WSL's launcher: the commands would land in the default distribution
        if sys.platform == "win32":
            raise ValueError(
                tr(
                    "A Linux-computer engine is reached only from that Linux computer",
                    "Un moteur « ordinateur Linux » ne s'atteint que depuis cet ordinateur Linux",
                )
            )
        return LocalShell()
    raise ValueError(
        tr(
            f"Unknown kind of compute profile: {profile.kind}",
            f"Type de profil de calcul inconnu : {profile.kind}",
        )
    )


# WSL distributions other programs create for their own use: never offered for the engine
INTERNAL_DISTRIBUTIONS = ("docker-desktop",)


def usable_distribution(name: str) -> bool:
    return bool(name.strip()) and not name.strip().lower().startswith(INTERNAL_DISTRIBUTIONS)


def list_wsl_distributions() -> list[str]:
    """Installed WSL distributions, without other programs' internal ones."""
    result = execute(["wsl.exe", "--list", "--quiet"], timeout=30)
    if not result.ok:
        return []
    # wsl.exe writes its own messages in UTF-16
    text = result.stdout.replace("\x00", "")
    return [name.strip() for name in text.splitlines() if usable_distribution(name)]
