"""Folders given by the user are recognised by what they hold, not by their names: the right
folder is looked for in the one given and below it, the closest first. The exported scripts and
the engine machine use the same search in bash (find_below in core/method/scripts_text.py)."""

from collections.abc import Callable
from pathlib import Path

# Levels below a folder given where the right one is looked for, and folders looked at at most
BELOW = 5
MAX_FOLDERS = 5000


def folders_below(
    root: Path,
    depth: int = BELOW,
    stop: Callable[[Path], bool] | None = None,
) -> list[Path]:
    """``root`` and its subfolders down to ``depth`` levels, breadth first and in name order
    (the closest come first), hidden ones left out, linked ones followed once. A folder for
    which ``stop`` is true is kept but not searched further."""
    found: list[Path] = []
    seen: set[str] = set()
    level = [root]
    for _ in range(depth + 1):
        below: list[Path] = []
        for folder in level:
            try:
                real = str(folder.resolve())
            except OSError:
                continue
            if real in seen or not folder.is_dir():
                continue
            seen.add(real)
            found.append(folder)
            if len(found) >= MAX_FOLDERS:
                return found
            if stop is not None and stop(folder):
                continue
            try:
                below += sorted(
                    p for p in folder.iterdir() if not p.name.startswith(".") and p.is_dir()
                )
            except OSError:
                continue
        level = below
    return found


def find_below(root: Path, target: str, depth: int = BELOW) -> Path | None:
    """The closest folder holding ``target`` (a relative path such as main/wrf.exe): ``root``
    itself or one of its subfolders, whatever their names."""
    for folder in folders_below(root, depth):
        if (folder / target).exists():
            return folder
    return None
