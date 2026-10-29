"""What a search found in a folder given by the user, summed up as the folders of a tree: each
folder with its number of files, their size, the first and last names and, when they are few,
every name. A long list stays short to read and to send."""

import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

# Names listed for one folder; above that, only the first and the last
NAMES = 6


def tree(files: Iterable[tuple[Path, int]], root: Path | None = None) -> dict[str, Any]:
    """The folders holding ``files`` (path, size), relative to ``root`` (by default the folder
    that holds them all)."""
    found = [(Path(path), size) for path, size in files]
    if root is None and found:
        try:
            root = Path(os.path.commonpath([str(p.parent) for p, _ in found]))
        except ValueError:  # on several Windows drives: whole paths
            root = None
    folders: dict[str, dict[str, Any]] = {}
    for path, size in found:
        try:
            relative = Path(os.path.relpath(path, root) if root is not None else path).as_posix()
        except ValueError:  # another drive than the root
            relative = path.as_posix()
        parent = relative.rpartition("/")[0]
        folder = folders.setdefault(parent, {"path": parent, "files": 0, "bytes": 0, "names": []})
        folder["files"] += 1
        folder["bytes"] += size
        folder["names"].append(relative.rpartition("/")[2])
    for folder in folders.values():
        names = sorted(folder["names"])
        folder["first"], folder["last"] = names[0], names[-1]
        folder["names"] = names if len(names) <= NAMES else []
    return {
        "root": str(root) if root is not None else "",
        "files": len(found),
        "bytes": sum(size for _, size in found),
        "folders": [folders[key] for key in sorted(folders)],
    }
