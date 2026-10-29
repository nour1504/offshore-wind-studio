"""Folders of a machine, one level at a time, for choosing a path by clicking.

Two machines: "engine", where WPS and WRF run (the WSL distribution or this Linux computer of the
default profile), and "here", the computer that runs the application (where the files of a
project are extracted). A listing never walks a tree: it reads one folder, a page at a time, with
the kind, the rights and the role of each entry (WRF, WPS, geography, engine, extracted project),
found by a few file tests. Nothing is ever written.

This computer is read by Python; a WSL engine by a bash script (its distribution may have no
Python), which makes the same tests and gives the same rows.
"""

import os
import posixpath
import shlex
import string
import sys
from pathlib import Path
from typing import Any, Literal

from owstudio.core import paths
from owstudio.core.engine.commands import BASH_FIND_BELOW_FUNCTION
from owstudio.core.engine.profiles import ComputeProfile
from owstudio.core.engine.shells import shell_for
from owstudio.core.i18n import tr

Machine = Literal["engine", "here"]
LIMIT = 200

# Files that tell the role of a folder, tested in this order
ROLES = (
    ("run", (("manifest.json",), ("wps",), ("wrf",)), ()),
    ("wrf", (), (("main", "wrf.exe"), ("run", "README.namelist"))),
    ("wps", (), (("geogrid.exe",), ("geogrid", "GEOGRID.TBL"))),
    ("geog", (), (("topo_gmted2010_30s",), ("topo_gmted2010_5m",), ("landuse_30s",))),
    ("engine", (("env.sh",),), (("WRF",), ("WPS",))),
)
# Topography of geog_data_res "default" (30 s) and "lowres" (5 min) in GEOGRID.TBL.ARW
RESOLUTIONS = (("default", "topo_gmted2010_30s"), ("lowres", "topo_gmted2010_5m"))


def _role(path: str) -> str | None:
    def has(parts: tuple[str, ...]) -> bool:
        return os.path.exists(os.path.join(path, *parts))

    for role, every, some in ROLES:
        if all(has(p) for p in every) and (not some or any(has(p) for p in some)):
            return role
    return None


def _bash_role() -> str:
    """The same tests as _role, as a bash function setting R (no subshell for each entry)."""
    lines = ["role_of() {", '  R=""']
    for role, every, some in ROLES:
        tests = [" && ".join(f'[ -e "$1/{"/".join(p)}" ]' for p in every)] if every else []
        if some:
            tests.append("{ " + " || ".join(f'[ -e "$1/{"/".join(p)}" ]' for p in some) + "; }")
        lines.append(f"  if {' && '.join(tests)}; then R={role}; return; fi")
    lines.append("}")
    return "\n".join(lines)


# Prints NUL-separated fields: a header of 6 (state, path, writable, role, resolutions, nearest),
# then 7 for each entry (kind, link, readable, writable, role, name, link target)
BASH_SCAN = (
    _bash_role()
    + r"""
emit() { printf '%s\0' "$@"; }
case $p in "~"|"") p=$HOME ;; "~/"*) p=$HOME/${p#"~/"} ;; esac
p=$(realpath -ms -- "$p")
if [ ! -d "$p" ]; then
  if [ -e "$p" ]; then s=file; else s=missing; fi
  n=$p
  while [ "$n" != / ] && [ ! -d "$n" ]; do n=$(dirname -- "$n"); done
  emit "$s" "$p" 0 "" "" "$n"
  exit 0
fi
role_of "$p"
res=""
"""
    + "".join(
        f'[ "$R" = geog ] && [ -e "$p/{folder}/index" ] && res="${{res:+$res,}}{name}"\n'
        for name, folder in RESOLUTIONS
    )
    + r"""w=0; [ -w "$p" ] && w=1
if [ ! -r "$p" ] || [ ! -x "$p" ]; then emit denied "$p" "$w" "$R" "$res" ""; exit 0; fi
emit ok "$p" "$w" "$R" "$res" ""
shopt -s nullglob dotglob
for e in "${p%/}"/*; do
  k=f; [ -d "$e" ] && k=d
  l=0; t=""; if [ -L "$e" ]; then l=1; t=$(readlink -f -- "$e"); fi
  r=0
  if [ $k = d ]; then [ -r "$e" ] && [ -x "$e" ] && r=1; else [ -r "$e" ] && r=1; fi
  ww=0; [ -w "$e" ] && ww=1
  R=""; [ $k = d ] && [ $r = 1 ] && role_of "$e"
  emit $k $l $r $ww "$R" "${e##*/}" "$t"
done
"""
)


def _header(state: str, path: str, writable: bool, role: str | None) -> dict[str, Any]:
    return {
        "path": path,
        "parent": None,
        "entries": [],
        "total": 0,
        "state": state,
        "role": role,
        "resolutions": [],
        "writable": writable,
    }


def _page(
    found: dict[str, Any], rows: list[dict[str, Any]], separator: str, offset: int, limit: int
) -> dict[str, Any]:
    """Folders first, names in alphabetical order, one page; the parent; links that loop."""
    path = found["path"]
    parent = os.path.dirname(path) if separator == os.sep else posixpath.dirname(path)
    found["parent"] = parent if parent != path else None
    if found["state"] != "ok":
        return found
    rows.sort(key=lambda r: (r["kind"] != "dir", r["name"].lower()))
    found["total"] = len(rows)
    if not rows:
        found["state"] = "empty"
    for row in rows[offset : offset + limit]:
        row["path"] = path.rstrip(separator) + separator + row["name"]
        target = row.get("target") or ""
        # A link to one of its own parents would loop: shown, never opened
        if row["kind"] == "dir" and target:
            row["loop"] = (path + separator).startswith(target.rstrip(separator) + separator)
        found["entries"].append(row)
    return found


def _scan_here(path: str, offset: int, limit: int) -> dict[str, Any]:
    path = os.path.abspath(os.path.expanduser(path or "~"))
    if not os.path.isdir(path):
        found = _header("file" if os.path.exists(path) else "missing", path, False, None)
        near = path
        while near != os.path.dirname(near) and not os.path.isdir(near):
            near = os.path.dirname(near)
        found["nearest"] = near
        return _page(found, [], os.sep, offset, limit)
    role = _role(path)
    found = _header("ok", path, os.access(path, os.W_OK), role)
    if role == "geog":
        found["resolutions"] = [
            name
            for name, folder in RESOLUTIONS
            if os.path.exists(os.path.join(path, folder, "index"))
        ]
    rows = []
    try:
        entries = list(os.scandir(path))
    except OSError:
        found["state"] = "denied"
        entries = []
    for entry in entries:
        try:
            is_dir = entry.is_dir()
            link = entry.is_symlink()
            readable = os.access(entry.path, os.R_OK | (os.X_OK if is_dir else 0))
            rows.append(
                {
                    "name": entry.name,
                    "kind": "dir" if is_dir else "file",
                    "link": link,
                    "readable": readable,
                    "writable": os.access(entry.path, os.W_OK),
                    "role": _role(entry.path) if is_dir and readable else None,
                    "target": os.path.realpath(entry.path) if link else "",
                }
            )
        except OSError:
            continue
    return _page(found, rows, os.sep, offset, limit)


def _scan_engine(profile: ComputeProfile, path: str, offset: int, limit: int) -> dict[str, Any]:
    script = f"p={shlex.quote(path or '~')}\n{BASH_SCAN}"
    done = shell_for(profile).run(script, timeout=30)
    fields = done.stdout.split("\0")
    if not done.ok or len(fields) < 7:
        return {"path": path, "state": "offline", "entries": [], "total": 0}
    state, real, writable, role, resolutions, nearest = fields[:6]
    found = _header(state, real, writable == "1", role or None)
    found["resolutions"] = [r for r in resolutions.split(",") if r]
    if nearest:
        found["nearest"] = nearest
    rows = []
    rest = fields[6:]
    for i in range(0, len(rest) - 6, 7):
        kind, link, readable, row_writable, row_role, name, target = rest[i : i + 7]
        rows.append(
            {
                "name": name,
                "kind": "dir" if kind == "d" else "file",
                "link": link == "1",
                "readable": readable == "1",
                "writable": row_writable == "1",
                "role": row_role or None,
                "target": target,
            }
        )
    return _page(found, rows, "/", offset, limit)


def _windows_root(distributions: list[str]) -> dict[str, Any]:
    """Above the drives of Windows: the drives, and the WSL distributions seen from Windows."""
    found = _header("ok", "", False, None)
    places = [(f"{c}:", f"{c}:\\") for c in string.ascii_uppercase if os.path.isdir(f"{c}:\\")]
    places += [(f"WSL · {d}", f"\\\\wsl.localhost\\{d}") for d in distributions]
    for name, path in places:
        found["entries"].append(
            {"name": name, "path": path, "kind": "dir", "link": False, "readable": True}
            | {"writable": True, "role": None, "target": ""}
        )
    found["total"] = len(found["entries"])
    return found


def engine_runs_here(profile: ComputeProfile | None) -> bool:
    """The engine machine is this one: a local profile, or Linux without any profile."""
    if profile is None:
        return sys.platform.startswith("linux")
    return profile.kind == "local"


def machine_name(machine: Machine, profile: ComputeProfile | None) -> str:
    if machine == "engine" and profile is not None and profile.kind == "wsl":
        return f"WSL · {profile.wsl_distro}"
    import socket

    return socket.gethostname()


def listing(
    machine: Machine, profile: ComputeProfile | None, path: str, offset: int = 0, limit: int = LIMIT
) -> dict[str, Any]:
    """One folder of a machine; state "offline" when the engine machine cannot be reached."""
    limit = max(1, min(limit, 1000))
    offset = max(0, offset)
    if machine == "here" or engine_runs_here(profile):
        if sys.platform == "win32" and machine == "here" and not path:
            distributions = [profile.wsl_distro] if profile and profile.kind == "wsl" else []
            found = _windows_root(distributions)
        else:
            found = _scan_here(path, offset, limit)
            if sys.platform == "win32" and found.get("parent") is None:
                found["parent"] = ""  # A drive: the list of drives above it
    elif profile is None:
        return {"path": path, "state": "offline", "entries": [], "total": 0}
    else:
        found = _scan_engine(profile, path, offset, limit)
    found["machine"] = machine_name(machine, profile)
    return found


def same_machine(profile: ComputeProfile | None, destination: str) -> bool:
    """Whether a folder of this computer is on the engine machine: always for a local engine,
    inside the engine's distribution (//wsl.localhost/<distro>) for a WSL engine."""
    if not destination.strip():
        return False
    if profile is None or profile.kind == "local":
        return engine_runs_here(profile)
    folder = destination.replace("\\", "/").lower().rstrip("/") + "/"
    distro = profile.wsl_distro.lower()
    return folder.startswith((f"//wsl.localhost/{distro}/", f"//wsl$/{distro}/"))


def needed_resolutions(geog_data_res: list[str]) -> list[str]:
    """The topography each domain reads: "lowres" (5 min) or "default" (30 s)."""
    needed = set()
    for value in geog_data_res:
        parts = value.split("+")
        if "lowres" in parts:
            needed.add("lowres")
        elif "default" in parts:
            needed.add("default")
    return sorted(needed)


# What makes each folder the right one, as the exported scripts look for it (resolve_folder)
TARGETS = {"wrf": "main/wrf.exe", "wps": "geogrid.exe"}


def _find_below_here(base: str, target: str) -> str | None:
    found = paths.find_below(Path(base), target)
    return str(found) if found is not None else None


# Prints, for each field: its state, then for each target the folder holding it, and whether the
# other targets are in the folder of the first one (one shell call for the three fields)
BASH_PROBE = r"""
probe() {
	local field=$1 p=${2%/} t w first="" n=0
	shift 2
	if [ ! -e "$p" ]; then printf '%s\tstate\tmissing\n' "$field"; return; fi
	if [ ! -d "$p" ]; then printf '%s\tstate\tfile\n' "$field"; return; fi
	if [ ! -r "$p" ] || [ ! -x "$p" ]; then printf '%s\tstate\tdenied\n' "$field"; return; fi
	printf '%s\tstate\tok\n' "$field"
	for t in "$@"; do
		w=$(find_below "$p" "$t")
		printf '%s\t%s\t%s\n' "$field" "$t" "$w"
		(( n++ == 0 )) && first=$w
		[ -n "$first" ] && [ -e "$first/$t" ] && printf '%s\twith\t%s\n' "$field" "$t"
	done
	return 0
}
"""


def _probe(
    profile: ComputeProfile | None, items: dict[str, tuple[str, list[str]]]
) -> dict[str, dict[str, Any]] | None:
    """For each field (folder, targets): {"state", target: folder holding it or None, "with":
    targets also in the folder of the first one}. None when the engine machine cannot be read."""
    result: dict[str, dict[str, Any]] = {}
    if engine_runs_here(profile):
        for field, (folder, targets) in items.items():
            base = folder.rstrip("/") or "/"
            if not os.path.exists(base):
                result[field] = {"state": "missing"}
            elif not os.path.isdir(base):
                result[field] = {"state": "file"}
            elif not os.access(base, os.R_OK | os.X_OK):
                result[field] = {"state": "denied"}
            else:
                found: dict[str, Any] = {"state": "ok", "with": set()}
                for target in targets:
                    found[target] = _find_below_here(base, target)
                first = found[targets[0]] if targets else None
                found["with"] = {
                    t for t in targets if first and os.path.exists(os.path.join(first, t))
                }
                result[field] = found
        return result
    if profile is None:
        return None
    lines = [BASH_FIND_BELOW_FUNCTION, BASH_PROBE]
    for field, (folder, targets) in items.items():
        lines.append(" ".join(shlex.quote(part) for part in ("probe", field, folder, *targets)))
    done = shell_for(profile).run("\n".join(lines), timeout=60)
    if not done.ok:
        return None
    for row in done.stdout.splitlines():
        field, key, value = (row.split("\t") + ["", ""])[:3]
        entry = result.setdefault(field, {"with": set()})
        if key == "state":
            entry["state"] = value
        elif key == "with":
            entry["with"].add(value)
        else:
            entry[key] = value or None
    return result if all(field in result for field in items) else None


def check(
    profile: ComputeProfile | None,
    folders: dict[str, str],
    resolutions: list[str],
    found: dict[str, str] | None = None,
) -> dict[str, str]:
    """A few words for each folder that is not what it should be on the engine machine: missing,
    not WRF, not WPS, not a geography, or a geography without the resolution the domains read.
    A folder whose right one is below it is not wrong: the scripts take that one, and ``found``
    receives it. The geography follows the rule of the scripts: the high resolution as soon as
    one domain reads it; with no known need, either."""
    expected = {"wrf_dir": "wrf", "wps_dir": "wps", "geog_dir": "geog"}
    wrong = {
        "wrf": tr("Not WRF", "Pas WRF"),
        "wps": tr("Not WPS", "Pas WPS"),
        "geog": tr("Not a geography", "Pas une géographie"),
    }
    high, low = (f"{folder}/index" for _, folder in RESOLUTIONS)
    items = {
        field: (folder, [high, low] if expected[field] == "geog" else [TARGETS[expected[field]]])
        for field, folder in folders.items()
        if field in expected and folder.strip().startswith("/")
    }
    probed = _probe(profile, items) if items else {}
    if probed is None:
        return {}  # Nothing known: the explorer says the machine cannot be reached
    result: dict[str, str] = {}
    for field, (folder, targets) in items.items():
        seen = probed[field]
        state = seen.get("state")
        if state in ("missing", "file"):
            result[field] = tr("Not found", "Introuvable")
            continue
        if state == "denied":
            result[field] = tr("Access denied", "Accès refusé")
            continue
        role = expected[field]
        if role != "geog":
            where = seen.get(targets[0])
        elif "default" in resolutions:
            where = seen.get(high)
            if where is None and seen.get(low):
                result[field] = tr("No high resolution", "Pas de haute résolution")
                continue
            if where is not None and "lowres" in resolutions and low not in seen["with"]:
                result[field] = tr("No low resolution", "Pas de basse résolution")
        elif "lowres" in resolutions:
            where = seen.get(low)
            if where is None and seen.get(high):
                result[field] = tr("No low resolution", "Pas de basse résolution")
                continue
        else:
            where = seen.get(high) or seen.get(low)
        if where is None:
            result[field] = wrong[role]
            continue
        if where.rstrip("/") != folder.rstrip("/") and found is not None:
            found[field] = where
    return result
