"""The catalogues shipped in backend/src/owstudio/data, regenerated from their official sources.

- namelist schema: every namelist.input option of a WRF release (Registry + README.namelist)
- variables: every WRF output variable (Registry files of a local WRF source tree)
- turbines: the offshore reference turbines of NREL's turbine-models library

Run through tools/dev.py (schema, variables, turbines). They download from GitHub, except the
variables, read from a WRF source tree on this computer.
"""

import csv
import io
import json
import re
import shlex
import urllib.request
from pathlib import Path

import yaml

DATA = Path(__file__).resolve().parents[1] / "backend" / "src" / "owstudio" / "data"


def fetch(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "owstudio-catalogs"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return str(response.read().decode("utf-8-sig", errors="replace"))


# ----------------------------------------------------------- namelist schema

RAW = "https://raw.githubusercontent.com/wrf-model/WRF/v{version}"
API = "https://api.github.com/repos/wrf-model/WRF/contents/Registry?ref=v{version}"
DESCRIPTION_LIMIT = 1500


def parse_default(kind: str, text: str) -> object:
    if kind == "logical":
        return text.strip(".").lower() == "true"
    if kind == "integer":
        try:
            return int(text)
        except ValueError:
            return text
    if kind == "real":
        try:
            return float(text.rstrip("d").replace("d", "e"))
        except ValueError:
            return text
    return text.strip("'\"")


def registry_options(version: str) -> dict[str, dict[str, dict[str, object]]]:
    listing = json.loads(fetch(API.format(version=version)))
    groups: dict[str, dict[str, dict[str, object]]] = {}
    for item in listing:
        text = fetch(item["download_url"])
        for line in text.splitlines():
            if not line.startswith("rconfig") or "namelist," not in line:
                continue
            try:
                fields = shlex.split(line, comments=False, posix=True)
            except ValueError:
                continue
            _, kind, name, use, dims, default, *rest = fields
            group = use.split(",", 1)[1].strip()
            description = rest[2] if len(rest) > 2 else ""
            groups.setdefault(group, {})[name.lower()] = {
                "type": kind.lower(),
                "per_domain": dims == "max_domains",
                "dimension": dims,
                "default": parse_default(kind.lower(), default),
                "description": "" if description == name else description,
                "units": rest[3] if len(rest) > 3 else "",
            }
    return groups


# An option name at the start of a line, then anything; names absent from the Registry are
# ignored when merging, so prose lines that happen to match do no harm
OPTION_LINE = re.compile(r"^\s{1,3}([a-z][a-z0-9_]*)\s*(\(max_dom\))?(?=\s|$)")


def clean(text: str) -> str:
    """Drops the "=", ";" and "!" separators README.namelist puts before values and comments."""
    text = text.strip()
    text = re.sub(r"^[=;]\s*", "", text)
    return re.sub(r"\s*!\s*", " — ", text).strip(" —")


def readme_descriptions(version: str) -> dict[tuple[str, str], str]:
    """Descriptions keyed by (group, option); continuation lines are appended."""
    text = fetch(f"{RAW.format(version=version)}/run/README.namelist")
    descriptions: dict[tuple[str, str], list[str]] = {}
    group, current = "", None
    for line in text.splitlines():
        header = re.match(r"^\s*&(\w+)", line)
        if header:
            group, current = header.group(1).lower(), None
            continue
        match = OPTION_LINE.match(line)
        if match and group:
            current = (group, match.group(1))
            descriptions.setdefault(current, []).append(clean(line[match.end() :]))
        elif current and line.startswith(" " * 20) and line.strip():
            descriptions[current].append(clean(line))
        elif not line.strip():
            current = None
    return {key: " ".join(parts).strip() for key, parts in descriptions.items()}


def namelist_schema(version: str) -> None:
    """data/namelist_schema_<version>.json: every option of the Registry, described by
    run/README.namelist where it documents it."""
    groups = registry_options(version)
    documented = readme_descriptions(version)
    for (group, name), text in documented.items():
        option = groups.get(group, {}).get(name)
        if option is not None and text:
            option["description"] = text[:DESCRIPTION_LIMIT]
    schema = {
        "wrf_version": version,
        "groups": {g: dict(sorted(options.items())) for g, options in sorted(groups.items())},
    }
    path = DATA / f"namelist_schema_{version}.json"
    path.write_text(
        json.dumps(schema, indent=1, ensure_ascii=False), encoding="utf-8", newline="\n"
    )
    total = sum(len(o) for o in groups.values())
    described = sum(1 for o in groups.values() for v in o.values() if v["description"])
    print(f"{path.name}: {total} options in {len(groups)} groups, {described} with a description")


# ----------------------------------------------------------------- variables


def streams(io: str) -> dict[str, bool]:
    """Stream letters before any '=' modifier: i input, r restart, h history, b boundary..."""
    letters = io.split("=")[0].lower() if io != "-" else ""
    letters = re.sub(r"\{[^}]*\}", "", letters)
    return {
        "history": "h" in letters,
        "restart": "r" in letters,
        "input": "i" in letters,
        "boundary": "b" in letters,
    }


def registry_variables(registry: Path) -> dict[str, dict[str, object]]:
    variables: dict[str, dict[str, object]] = {}
    packages: dict[str, list[str]] = {}
    # The ARW core's own Registry first, so that its definitions win over chemistry or
    # data-assimilation registries that redeclare a variable
    first = {"Registry.EM_COMMON": 0, "Registry.EM": 1}
    for path in sorted(registry.iterdir(), key=lambda p: (first.get(p.name, 2), p.name)):
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        # A backslash at the end of a line continues the entry on the next line
        text = re.sub(r"\\[ \t]*\r?\n", " ", text)
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            try:
                parts = shlex.split(line)
            except ValueError:
                continue
            kind = parts[0].lower()
            if kind in ("state", "i1") and len(parts) >= 11:
                (
                    _,
                    type_,
                    sym,
                    dims,
                    use,
                    _ntl,
                    stagger,
                    io,
                    dname,
                    description,
                    units,
                ) = parts[:11]
                # WRF writes the output name in upper case (Registry "qke" is QKE in wrfout)
                name = (dname if dname not in ("-", "") else sym).upper()
                if name in variables and variables[name]["file"] != path.name:
                    continue
                variables[name] = {
                    "name": name,
                    "symbol": sym,
                    "type": type_,
                    "dims": dims,
                    "use": use,
                    "stagger": "" if stagger == "-" else stagger,
                    "io": io,
                    **streams(io),
                    "description": description,
                    "units": units,
                    "file": path.name,
                }
            elif kind == "package" and len(parts) >= 5:
                name, condition = parts[1], parts[2]
                for group in parts[4].split(";"):
                    for sym in group.split(":", 1)[-1].split(","):
                        if sym:
                            packages.setdefault(sym.lower(), []).append(f"{name} ({condition})")
    for entry in variables.values():
        found = packages.get(str(entry["symbol"]).lower())
        if found:
            entry["packages"] = sorted(set(found))
    return variables


def variable_catalog(registry: Path, target: Path) -> None:
    """The catalogue of WRF variables (data/variables_4.8.0.json) from the Registry files of a
    WRF release: every `state` and `i1` entry, with the schemes (`package`) that allocate it."""
    variables = registry_variables(registry)
    target.write_text(
        json.dumps(
            {"wrf_version": "4.8.0", "variables": variables},
            separators=(",", ":"),
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    print(f"{len(variables)} variables written to {target}")


# ------------------------------------------------------------------ turbines

TURBINES_REPO = "https://raw.githubusercontent.com/NatLabRockies/turbine-models/main"
TURBINES_LICENSE = f"{TURBINES_REPO}/LICENSE.txt"
TURBINES = [
    "IEA_Reference_15MW_240",
    "IEA_Reference_10MW_198",
    "DTU_Reference_v1_10MW_178",
    "NREL_Reference_5MW_126",
    "LEANWIND_Reference_8MW_164",
]
# The other offshore models of the library have no thrust curve, which the wind farm schemes need

# Thrust coefficient of a parked turbine; the library does not provide it, WRF's example uses 0.13
STANDING_THRUST_COEFFICIENT = 0.1


def turbine_curve(text: str) -> list[dict[str, float]]:
    rows = csv.DictReader(io.StringIO(text))
    points = []
    for row in rows:
        speed, power, ct = (
            row.get("Wind Speed [m/s]"),
            row.get("Power [kW]"),
            row.get("Ct [-]"),
        )
        if not speed or not power or not ct:
            continue
        points.append(
            {
                "wind_speed": round(float(speed), 3),
                "thrust_coefficient": round(float(ct), 4),
                "power_kw": round(float(power), 2),
            }
        )
    return points


def turbine_catalog() -> None:
    """One YAML file per offshore reference turbine of NREL's turbine-models library in
    data/turbines/, with the source and licence (BSD-3-Clause) of each."""
    out = DATA / "turbines"
    out.mkdir(parents=True, exist_ok=True)
    (out / "LICENSE-turbine-models.txt").write_text(
        fetch(TURBINES_LICENSE), encoding="utf-8", newline="\n"
    )
    for name in TURBINES:
        spec = yaml.safe_load(fetch(f"{TURBINES_REPO}/turbine_models/specs/Offshore/{name}.yaml"))
        points = turbine_curve(fetch(f"{TURBINES_REPO}/turbine_models/data/Offshore/{name}.csv"))
        entry = {
            "id": name.lower().replace("_", "-"),
            "name": name.replace("_", " "),
            "origin": spec.get("origin"),
            "power_curve_type": spec.get("power_curve_type"),
            "cut_in_wind_speed": spec.get("cut_in_wind_speed"),
            "rated_wind_speed": spec.get("rated_wind_speed"),
            "cut_out_wind_speed": spec.get("cut_out_wind_speed"),
            "source": f"{TURBINES_REPO}/turbine_models/data/Offshore/{name}.csv",
            "license": "BSD-3-Clause (NREL turbine-models)",
            "turbine": {
                "name": name.replace("_", " "),
                "hub_height_m": float(spec["hub_height"]),
                "rotor_diameter_m": float(spec["rotor_diameter"]),
                "standing_thrust_coefficient": STANDING_THRUST_COEFFICIENT,
                "rated_power_mw": float(spec["rated_power"]) / 1000,
                "curve": points,
            },
        }
        path = out / f"{entry['id']}.yaml"
        path.write_text(yaml.safe_dump(entry, sort_keys=False), encoding="utf-8", newline="\n")
        print(f"{path.name}: {len(points)} points, hub {spec['hub_height']} m")
