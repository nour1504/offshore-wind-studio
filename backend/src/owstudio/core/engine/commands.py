"""Bash commands run on the engine machine (WSL or a Linux computer): the variables of an
installation, the check of an installation, and the start of a process that survives the end of the
command (the engine installation runs that way).

The application does not run WPS or WRF itself: the exported scripts do
(core/method/scripts.py).
"""

import shlex

from owstudio.core.engine.profiles import ComputeProfile
from owstudio.core.i18n import tr
from owstudio.core.method.scripts_text import FIND_BELOW

# The closest folder holding $2 below $1: the find_below of the exported scripts
BASH_FIND_BELOW_FUNCTION = "\n" + FIND_BELOW


def bash_path(path: str) -> str:
    """A path for bash in double quotes, keeping ~ and $VARIABLES working."""
    if path.startswith("~"):
        path = "$HOME" + path[1:]
    return '"' + path.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`") + '"'


def environment(profile: ComputeProfile) -> str:
    """Variables of the installation: WRF, WPS and the geography, and its own setup lines."""
    install = profile.install
    lines = [
        f"export OWS_WRF={bash_path(install.wrf_dir)}",
        f"export OWS_WPS={bash_path(install.wps_dir)}",
        f"export OWS_GEOG={bash_path(install.geog_dir)}",
        "ulimit -s unlimited 2>/dev/null || true",
    ]
    if install.env_setup.strip():
        lines.append(install.env_setup.strip())
    return "\n".join(lines) + "\n"


def detach(command: str, log: str, pid_file: str) -> str:
    """Shell lines starting ``command`` (bash -c text that writes its pid to ``pid_file`` first)
    in a new session, then waiting until it has, so that it survives the end of this script: WSL
    ends the processes of a command's group as soon as the command returns."""
    return (
        f"nohup setsid bash -c {shlex.quote(command)} >> {log} 2>&1 < /dev/null &\n"
        f"for i in $(seq 1 100); do [ -s {pid_file} ] && break; sleep 0.1; done\n"
        f"[ -s {pid_file} ] || {{ echo 'The detached process did not start' >&2; exit 1; }}\n"
    )


def verify_script(profile: ComputeProfile) -> str:
    """Checks the installation; prints one line per check: ok|warn|fail <tab> label <tab> detail
    (labels and details in the language of the interface)."""
    mpi = (profile.resources.mpi_command.split() or ["mpirun"])[0]
    missing = tr("missing", "absent")
    found = tr("found", "trouvé")
    folders = bash_path(profile.install.input_dir or "/tmp")
    below = tr("folder used", "dossier utilisé")
    return (
        environment(profile)
        + BASH_FIND_BELOW_FUNCTION
        + rf"""
report() {{ printf '%s\t%s\t%s\n' "$1" "$2" "$3"; }}
# A folder above the right one is not wrong: the exported scripts take the one below it
take_below() {{ local found; found=$(find_below "${{!1}}" "$2"); if [ -n "$found" ] && [ "$found" != "${{!1%/}}" ]; then report ok "$3" "{below}: $found"; printf -v "$1" '%s' "$found"; fi; }}
take_below OWS_WRF main/wrf.exe WRF
take_below OWS_WPS geogrid.exe WPS
geography=$(find_below "$OWS_GEOG" topo_gmted2010_30s/index)
[ -n "$geography" ] || geography=$(find_below "$OWS_GEOG" topo_gmted2010_5m/index)
if [ -n "$geography" ] && [ "$geography" != "${{OWS_GEOG%/}}" ]; then report ok "{tr("Geography", "Géographie")}" "{below}: $geography"; OWS_GEOG=$geography; fi
exists() {{ if [ -e "$1" ]; then report ok "$2" "$1"; else report fail "$2" "{missing}: $1"; fi; }}
exe() {{ if [ -x "$1" ] || [ -x "$2" ]; then report ok "$3" "{found}"; else report fail "$3" "{missing}: $1"; fi; }}
exe "$OWS_WRF/main/wrf.exe" "$OWS_WRF/run/wrf.exe" "wrf.exe"
exe "$OWS_WRF/main/real.exe" "$OWS_WRF/run/real.exe" "real.exe"
exists "$OWS_WRF/run/README.namelist" "{tr("WRF run directory and tables", "Dossier run et tables de WRF")}"
exe "$OWS_WPS/geogrid.exe" "$OWS_WPS/geogrid/src/geogrid.exe" "geogrid.exe"
exe "$OWS_WPS/ungrib.exe" "$OWS_WPS/ungrib/src/ungrib.exe" "ungrib.exe"
exe "$OWS_WPS/metgrid.exe" "$OWS_WPS/metgrid/src/metgrid.exe" "metgrid.exe"
exists "$OWS_WPS/link_grib.csh" "link_grib.csh"
exists "$OWS_WPS/ungrib/Variable_Tables" "Vtables"
exists "$OWS_WPS/geogrid/GEOGRID.TBL" "GEOGRID.TBL"
exists "$OWS_WPS/metgrid/METGRID.TBL" "METGRID.TBL"
resolutions=""
[ -e "$OWS_GEOG/topo_gmted2010_30s/index" ] && resolutions="{tr("high", "haute")}"
[ -e "$OWS_GEOG/topo_gmted2010_5m/index" ] && resolutions="${{resolutions:+$resolutions, }}{tr("low", "basse")}"
if [ -n "$resolutions" ]; then report ok "{tr("Geography", "Géographie")}" "{tr("resolution", "résolution")} $resolutions, $(ls "$OWS_GEOG" | wc -l) {tr("datasets in", "jeux de données dans")} $OWS_GEOG"; else report fail "{tr("Geography", "Géographie")}" "{tr("no geography in", "pas de géographie dans")} $OWS_GEOG"; fi
if command -v csh >/dev/null || command -v tcsh >/dev/null; then report ok "csh (link_grib.csh)" "{found}"; else report fail "csh (link_grib.csh)" "{tr("install csh or tcsh", "installez csh ou tcsh")}"; fi
if command -v ncdump >/dev/null; then report ok "ncdump (NetCDF)" "{found}"; else report fail "ncdump (NetCDF)" "{tr("install the NetCDF command line tools", "installez les outils en ligne de commande de NetCDF")}"; fi
if command -v {mpi} >/dev/null; then report ok "MPI ({mpi})" "$(command -v {mpi})"; else report fail "MPI ({mpi})" "{tr("not found in PATH", "introuvable dans le PATH")}"; fi
for d in {folders}; do
  if mkdir -p "$d" 2>/dev/null && touch "$d/.ows-test" 2>/dev/null; then rm -f "$d/.ows-test"; report ok "{tr("Writable folder", "Dossier accessible en écriture")}" "$d ($(df -h "$d" | awk 'NR==2 {{print $4}}') {tr("free", "libres")})"; else report fail "{tr("Writable folder", "Dossier accessible en écriture")}" "{tr("cannot write in", "impossible d'écrire dans")} $d"; fi
done
version=$(grep -h -o -E 'Version [0-9]+\.[0-9]+(\.[0-9]+)?' "$OWS_WRF/README" "$OWS_WRF/inc/version_decl" 2>/dev/null | head -n 1)
report ok "{tr("WRF version", "Version de WRF")}" "${{version:-?}}"
if grep -q windfarm_opt "$OWS_WRF/run/README.namelist" 2>/dev/null; then report ok "{tr("Wind farm schemes", "Schémas de parc")}" "Fitch, MAV"; else report warn "{tr("Wind farm schemes", "Schémas de parc")}" "{tr("windfarm_opt not documented in this WRF", "windfarm_opt absent de la documentation de ce WRF")}"; fi
report ok "{tr("Cores", "Cœurs")}" "$(env -u OMP_NUM_THREADS -u OMP_THREAD_LIMIT nproc 2>/dev/null)"
report ok "{tr("Memory", "Mémoire")}" "$(free -g 2>/dev/null | awk '/Mem:/ {{print $2 " GB / " $7 " GB"}}')"
"""
    )


def parse_verify(output: str) -> list[dict[str, str]]:
    checks = []
    for line in output.splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[0] in ("ok", "warn", "fail"):
            checks.append({"status": parts[0], "label": parts[1], "detail": parts[2]})
    return checks
