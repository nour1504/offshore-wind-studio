"""The bash scripts of the export, laid out like the usual in-house WPS/WRF cluster scripts:
OPTIONS POUR SLURM, PARAMÈTRES DE BASE, PARAMÈTRES AVANCÉS, FONCTIONS, PROGRAMME, in the language
of the interface (French or English: comments, messages, names of variables, functions, files and
folders; the same logic, scripts_text.py).

Differences from those reference scripts, on purpose:
- every date is computed by the application in UTC (core/method/plan.py) and written in the
  scripts: no date arithmetic by hand, valid for any spin-up, including 24 h and more;
- the spin-up lines of the time series are removed by time step number, from the exact time
  step of each domain, never by a fixed line number; the counts are checked;
- real.exe and wrf.exe must end with SUCCESS COMPLETE, otherwise the script stops before
  touching any output; scripts end with 0 on success, so that chained Slurm jobs continue;
- GRIB files are linked by the script itself (no csh needed for link_grib.csh).
The scripts are plain ASCII (French without accents), so that any shell and editor read them.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from fractions import Fraction

from owstudio.core.i18n import current, tr
from owstudio.core.method import scripts_text as text
from owstudio.core.method.plan import WRF_DATE, Plan, Window, kept_steps

# Variables of the WRF 4.8 time series (share/wrf_timeseries.F: TS, then the profiles UU, VV, PH,
# TH, QV, WW, PR, and O3 with WRF-Chem); QK is written by some modified WRF versions, as in the
# reference script. A missing file is skipped.
TS_VARIABLES = ("TS", "UU", "VV", "WW", "TH", "PH", "QV", "PR", "QK", "O3")

# Names of the files and folders of the export and of the scripts' work, in each language (the
# names of WRF and WPS never change). The import of the outputs reads both.
FILE_NAMES = {
    "fr": {
        "readme": "LISEZ-MOI.txt",
        "plan": "plan_fenetres.csv",
        "cells": "cellules.csv",
        "common": "commun.sh",
        "state": "fenetres_faites.txt",
        "data": "donnees",
        "download_gfs": "telecharger_gfs.sh",
        "download_era5": "telecharger_era5.py",
        "spin_up": "mise_en_route",
        "logs": "journaux",
        "tslist_windows": "tslist_fenetres",
        "tslist_blocks": "tslist_blocs",
        "tslist_period": "tslist_periode",
        "path": "/chemin/vers",
        "own_files": "/chemin/vers/vos/fichiers",
        "intermediate": "intermediaires",
        "run_log": "calcul.log",
    },
    "en": {
        "readme": "README.txt",
        "plan": "window_plan.csv",
        "cells": "cells.csv",
        "common": "common.sh",
        "state": "windows_done.txt",
        "data": "data",
        "download_gfs": "download_gfs.sh",
        "download_era5": "download_era5.py",
        "spin_up": "spin_up",
        "logs": "logs",
        "tslist_windows": "tslist_windows",
        "tslist_blocks": "tslist_blocks",
        "tslist_period": "tslist_period",
        "path": "/path/to",
        "own_files": "/path/to/your/files",
        "intermediate": "intermediate",
        "run_log": "run.log",
    },
}


def names() -> dict[str, str]:
    """File and folder names of the export in the current language."""
    return FILE_NAMES[current()]


def _pick(texts: dict[str, str]) -> str:
    return texts[current()]


@dataclass(frozen=True)
class Slurm:
    nodes: int = 2
    ntasks_per_node: int | None = None
    time: str = "72:00:00"
    partition: str = "cn"
    exclusive: bool = True
    enable_turbo: bool = True
    wckey: str = ""
    # Raw header written as is instead of the fields above (editor mode); {job} is replaced by
    # the name of each job
    raw: str | None = None


@dataclass(frozen=True)
class Source:
    """One input of ungrib: its prefix, its Vtable file in wps/ and its files (%Y = year).
    ``converted``: the user's NetCDF files, converted at export into WPS intermediate files in
    wps/<intermediate>/<prefix>/ (``pattern`` is that folder): metgrid reads them, no ungrib."""

    prefix: str
    pattern: str
    vtable_file: str
    sst: bool = False
    converted: bool = False


@dataclass(frozen=True)
class Domain:
    number: int
    step: Fraction
    history_seconds: int


@dataclass
class ScriptContext:
    project: str
    version: str
    generated: datetime
    cluster: bool
    plan: Plan
    domains: list[Domain]
    adaptive: bool
    tslist: list[str]
    sources: list[Source]
    # SST pass of ungrib for each WPS pass, when the SST is separate: year -> (start, end)
    sst_windows: dict[int, tuple[datetime, datetime]] = field(default_factory=dict)
    wrf_dir: str = "/path/to/WRF"
    wps_dir: str = "/path/to/WPS"
    geog_dir: str = "/path/to/WPS_GEOG"
    # Shared folder of the downloaded input data (gfs/<year>/, era5/<year>/) on the machine,
    # empty: the data/ folder of the package
    data_dir: str = ""
    cores: int = 96
    wps_cores: int = 12
    slurm: Slurm = field(default_factory=Slurm)
    environment: list[str] = field(default_factory=list)


def ascii(text: str) -> str:
    """Plain ASCII: accents removed, other characters replaced."""
    import unicodedata

    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return "".join(c if 32 <= ord(c) < 127 or c in "\n\t" else "?" for c in plain)


def quote(text: str) -> str:
    """A bash double-quoted string."""
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`")
    return f'"{escaped}"'


# A variable at the start of a path: $HOME, ${HOME}
_LEADING_VARIABLE = re.compile(r"^\$(\{[A-Za-z_][A-Za-z0-9_]*\}|[A-Za-z_][A-Za-z0-9_]*)")


def quote_path(text: str) -> str:
    """A path in bash double quotes, as the Compute page accepts it: ~ and a variable at its
    start ($HOME/WRF) are expanded by bash, the rest is literal."""
    if text == "~" or text.startswith("~/"):
        text = "$HOME" + text[1:]
    match = _LEADING_VARIABLE.match(text)
    if match is None:
        return quote(text)
    return '"' + match.group(0) + quote(text[match.end() :])[1:]


def _date(time: datetime) -> str:
    return time.strftime(WRF_DATE)


def launcher(context: ScriptContext, cores: int) -> str:
    return f"srun -n {cores}" if context.cluster else f"mpirun -np {cores}"


# ------------------------------------------------------------------ common parts


def banner(context: ScriptContext, what: str) -> list[str]:
    return [
        "#!/bin/bash",
        "",
        "#" * 70,
        f"# Offshore Wind Studio {context.version} - "
        + tr(f"project {ascii(context.project)}", f"projet {ascii(context.project)}"),
        f"# {what}",
        tr(
            f"# Generated on {context.generated:%Y-%m-%d %H:%M} UTC. Dates in UTC.",
            f"# Genere le {context.generated:%Y-%m-%d %H:%M} UTC. Dates en UTC.",
        ),
        "#" * 70,
        "",
    ]


def slurm_header(context: ScriptContext, job: str, nodes: int | None = None) -> list[str]:
    if not context.cluster:
        return []
    lines = [
        *_title(tr("SLURM OPTIONS", "OPTIONS POUR SLURM")),
        "",
        tr("## Reminders:", "## Rappels :"),
        tr(
            "## CPUs per node: 48 | Never saturate a node",
            "## Nombre de CPU par noeud : 48 | Ne jamais saturer un noeud",
        ),
        tr(
            "## exclusive + enable-turbo recommended for WRF",
            "## exclusive + enable-turbo recommandes pour WRF",
        ),
        tr(
            "## time = 72:00:00 is the maximum | lower it if less is needed",
            "## time = 72:00:00 est le maximum | adapter si besoin de moins",
        ),
        "",
    ]
    slurm = context.slurm
    if slurm.raw is not None:
        lines += [ascii(line.replace("{job}", job)) for line in slurm.raw.strip().splitlines()]
        return [*lines, ""]
    lines.append(f"#SBATCH --nodes={nodes or slurm.nodes}")
    if slurm.ntasks_per_node:
        lines.append(f"#SBATCH --ntasks-per-node={slurm.ntasks_per_node}")
    lines += [f"#SBATCH --time={slurm.time}", f"#SBATCH --partition={ascii(slurm.partition)}"]
    if slurm.exclusive:
        lines.append("#SBATCH --exclusive")
    if slurm.enable_turbo:
        lines.append("#SBATCH --enable-turbo")
    if slurm.wckey:
        lines.append(f"#SBATCH --wckey={ascii(slurm.wckey)}")
    lines += [
        f"#SBATCH --output={job}_%j.out",
        f"#SBATCH --error={job}_%j.err",
        f"#SBATCH --job-name={job[:40]}",
        "",
    ]
    return lines


def environment(context: ScriptContext) -> list[str]:
    """Lines run before the programs: modules on a cluster, the engine's env.sh on a computer."""
    found = [ascii(line) for line in context.environment if line.strip()]
    if not found:
        return []
    title = tr(
        "# Environment (modules, matching MPI...)" if context.cluster else "# Environment (engine)",
        "# Environnement (modules, MPI compatible...)"
        if context.cluster
        else "# Environnement (moteur)",
    )
    return [title, *found, ""]


def _title(title: str) -> list[str]:
    """A section title framed by #, as in the reference scripts."""
    bar = "#" * (len(title) + 8)
    return [bar, f"### {title} ###", bar]


def _advanced_notice() -> list[str]:
    return [
        *_title(tr("ADVANCED SETTINGS", "PARAMETRES AVANCES")),
        "",
        tr(
            "## /!\\ Computed by Offshore Wind Studio: to change the period, export again /!\\",
            "## /!\\ Calcules par Offshore Wind Studio : pour changer la periode, exportez de nouveau /!\\",
        ),
        "",
    ]


def _functions_title() -> list[str]:
    common_file = names()["common"]
    return [
        *_title(tr("FUNCTIONS", "FONCTIONS")),
        "",
        tr(
            "## /!\\ Change only if you know what you are doing /!\\",
            "## /!\\ Ne modifier qu'en connaissance de cause /!\\",
        ),
        "",
        tr(
            f"## Functions shared by every script (log, namelists, links): ../{common_file}",
            f"## Fonctions communes a tous les scripts (journal, namelists, liens) : ../{common_file}",
        ),
        "# shellcheck source-path=SCRIPTDIR",
        f"source ../{common_file} || exit 1",
    ]


def common(context: ScriptContext) -> str:
    """The functions shared by every script; each script reads them (source)."""
    lines = banner(
        context,
        tr(
            "Functions shared by every script (read by them, not run alone)",
            "Fonctions communes a tous les scripts (lu par eux, pas lance seul)",
        ),
    )
    lines += [
        "# shellcheck shell=bash",
        _pick(text.JOURNAL_FUNCTIONS),
        _pick(text.NAMELIST_FUNCTIONS),
    ]
    return "\n".join(lines).rstrip() + "\n"


def _program_title() -> list[str]:
    return [*_title(tr("PROGRAM", "PROGRAMME")), ""]


# ------------------------------------------------------------------ WPS


def run_wps(context: ScriptContext) -> str:
    plan = context.plan
    fr = current() == "fr"
    lines = banner(
        context,
        tr(
            "WPS: geogrid, then ungrib and metgrid year by year",
            "WPS : geogrid, puis ungrib et metgrid annee par annee",
        ),
    )
    lines += slurm_header(context, "WPS", nodes=1)
    files_variable = "FICHIERS" if fr else "FILES"
    lines += [
        *_title(tr("BASIC SETTINGS", "PARAMETRES DE BASE")),
        "",
        tr(
            "## To be run from this folder (wps/), which holds namelist.wps and the Vtables.",
            "## A lancer depuis ce dossier (wps/), qui contient namelist.wps et les Vtables.",
        ),
        "",
        tr(
            f"WPS_DIR={quote_path(context.wps_dir)}\t\t# WPS installation (geogrid.exe, ungrib.exe, metgrid.exe)",
            f"DOSSIER_WPS={quote_path(context.wps_dir)}\t\t# Installation de WPS (geogrid.exe, ungrib.exe, metgrid.exe)",
        ),
        tr(
            f"GEOG_DIR={quote_path(context.geog_dir)}\t\t# Static geographical data (WPS_GEOG)",
            f"DOSSIER_GEOG={quote_path(context.geog_dir)}\t\t# Donnees geographiques statiques (WPS_GEOG)",
        ),
        tr(
            'UNGRIB_DIR="$PWD/ungrib"\t\t# Intermediate files of ungrib, one folder per year',
            'DOSSIER_UNGRIB="$PWD/ungrib"\t\t# Fichiers intermediaires d\'ungrib, un dossier par annee',
        ),
        tr(
            'MET_EM_DIR="$PWD/met_em"\t\t# Outputs of metgrid: every year in this folder',
            'DOSSIER_MET_EM="$PWD/met_em"\t\t# Sorties de metgrid : toutes les annees dans ce dossier',
        ),
        "",
        tr(
            "## Input files of each source (pattern; %Y is replaced by the year)",
            "## Fichiers d'entree de chaque source (motif ; %Y est remplace par l'annee)",
        ),
        tr(
            "# shellcheck disable=SC2034 # read by their name: FILES_<source>",
            "# shellcheck disable=SC2034 # lus par leur nom : FICHIERS_<source>",
        ),
    ]
    # A shellcheck directive covers the next line only: one per variable
    for n, source in enumerate(context.sources):
        if n:
            lines.append("# shellcheck disable=SC2034")
        lines.append(f"{files_variable}_{source.prefix}={quote_path(source.pattern)}")
    lines.append(
        tr(
            "## Vtable of each source (in wps/), linked as Vtable before ungrib",
            "## Vtable de chaque source (dans wps/), liee sous le nom Vtable avant ungrib",
        )
    )
    lines.append(
        tr(
            "# shellcheck disable=SC2034 # read by their name: VTABLE_<source>",
            "# shellcheck disable=SC2034 # lues par leur nom : VTABLE_<source>",
        )
    )
    for n, source in enumerate(context.sources):
        if n:
            lines.append("# shellcheck disable=SC2034")
        lines.append(f"VTABLE_{source.prefix}={quote(source.vtable_file)}")
    ungrib = quote("srun -n 1" if context.cluster else "")
    lines += [
        "",
        tr("GEOGRID_LAUNCHER", "LANCEUR_GEOGRID")
        + f"={quote(launcher(context, context.wps_cores))}",
        tr(
            f"UNGRIB_LAUNCHER={ungrib}\t\t# DO NOT PARALLELISE",
            f"LANCEUR_UNGRIB={ungrib}\t\t# NE PAS PARALLELISER",
        ),
        tr("METGRID_LAUNCHER", "LANCEUR_METGRID")
        + f"={quote(launcher(context, context.wps_cores))}",
        "",
        *environment(context),
        *_advanced_notice(),
        tr(
            "RUN_GEOGRID=1\t\t\t# 0 if the geo_em are already there",
            "FAIRE_GEOGRID=1\t\t\t# 0 si les geo_em sont deja la",
        ),
        f"MAX_DOM={len(context.domains)}",
        tr(
            "## Sources read by metgrid in this order: the last one prevails for a common field",
            "## Sources lues par metgrid dans cet ordre : la derniere l'emporte pour un champ commun",
        ),
        "SOURCES=(" + " ".join(s.prefix for s in context.sources) + ")",
        "SOURCES_SST=(" + " ".join(s.prefix for s in context.sources if s.sst) + ")",
        tr(
            "## NetCDF sources converted by the application (folders above): no ungrib",
            "## Sources NetCDF converties par le logiciel (dossiers ci-dessus) : pas d'ungrib",
        ),
        tr("CONVERTED=(", "CONVERTIS=(")
        + " ".join(s.prefix for s in context.sources if s.converted)
        + ")",
        "",
        tr(
            "## One pass per year, cut to the period of the study, spin-up included:",
            "## Un passage par annee, coupe a la periode d'etude, mise en route incluse :",
        ),
        tr(
            "## year | start | end | SST start | SST end",
            "## annee | debut | fin | debut SST | fin SST",
        ),
        tr("PASSES=(", "PASSAGES=("),
    ]
    for wps in plan.wps_passes:
        sst = context.sst_windows.get(wps.year, (wps.start, wps.end))
        lines.append(
            f'"{wps.year} {_date(wps.start)} {_date(wps.end)} {_date(sst[0])} {_date(sst[1])}"'
        )
    lines += [")", ""]
    lines += _functions_title()
    lines.append(_pick(text.WPS_FUNCTIONS))
    lines += [*_program_title(), _pick(text.WPS_PROGRAM)]
    return "\n".join(lines).rstrip() + "\n"


# ------------------------------------------------------------------ WRF


def plan_columns(window: Window, plan: Plan, domains: list[Domain]) -> list[str]:
    """Columns of the plan that run_wrf.sh reads, after the dates: simulated duration (s),
    offset of the simulation start from D (s), restart (1: starts from the restart file of the
    previous window), spin-up of the window (s), end and duration (s) of what real.exe prepares
    (a boundary data time, at or after the end of the simulation), last kept step of each
    domain."""
    offset = int((window.simulation_start - plan.start).total_seconds())
    last = [str(kept_steps(window, d.step)[1]) for d in domains]
    return [
        str(window.simulated_seconds),
        str(offset),
        str(int(window.restart)),
        str(int(window.spin_up.total_seconds())),
        window.preparation_end.strftime(WRF_DATE),
        str(window.preparation_seconds),
        *last,
    ]


def run_wrf(context: ScriptContext) -> str:
    """The one WRF script, the same on a cluster and on a Linux computer (only the Slurm header,
    the MPI command and the environment differ): every window of the plan file in the order of
    computation, the series of each block assembled, then the assembly of the period. A window
    already done is skipped, so that the script resumes after a stop; on Slurm it submits
    itself again before the job's time limit when the next window would not fit."""
    plan = context.plan
    n = names()
    lines = banner(
        context,
        tr(
            f"WRF: the {len(plan.windows)} window(s) of the period, chained by restart files, then the assembly",
            f"WRF : les {len(plan.windows)} fenetre(s) de la periode, enchainees par fichiers restart, puis l'assemblage",
        )
        if plan.restart
        else tr(
            f"WRF: the {len(plan.windows)} window(s) of the period, antichronologically, then the assembly",
            f"WRF : les {len(plan.windows)} fenetre(s) de la periode, dans l'ordre antichronologique, puis l'assemblage",
        ),
    )
    lines += slurm_header(context, "WRF")
    # The first window's spin-up: the origin of the time series after a restart may be its start
    spin_first = int(plan.windows[0].spin_up.total_seconds())
    launcher_line = quote(launcher(context, context.cores))
    lines += [
        *_title(tr("BASIC SETTINGS", "PARAMETRES DE BASE")),
        "",
        tr(
            "## To be run from this folder (wrf/), which holds namelist.input, the tslist and the",
            "## A lancer depuis ce dossier (wrf/), qui contient namelist.input, la tslist et les",
        ),
        tr(
            "## turbine files: sbatch run_wrf.sh on a cluster, bash run_wrf.sh on a computer.",
            "## fichiers des eoliennes : sbatch run_wrf.sh sur un cluster, bash run_wrf.sh sur un ordinateur.",
        ),
        tr(
            "## Stopped (time limit, failure)? Run it again: it resumes at the next window.",
            "## Arrete (limite de temps, echec) ? Relancez-le : il reprend a la fenetre suivante.",
        ),
        "",
        tr(
            f"WRF_DIR={quote_path(context.wrf_dir)}\t\t# WRF installation (main/real.exe, main/wrf.exe, run/)",
            f"DOSSIER_WRF={quote_path(context.wrf_dir)}\t\t# Installation de WRF (main/real.exe, main/wrf.exe, run/)",
        ),
        tr(
            'MET_EM_DIR="$PWD/../wps/met_em"\t\t# Outputs of metgrid',
            'DOSSIER_MET_EM="$PWD/../wps/met_em"\t\t# Sorties de metgrid',
        ),
        tr(
            f"LAUNCHER={launcher_line}\t\t# MPI command",
            f"LANCEUR={launcher_line}\t\t# Commande MPI",
        ),
        tr(
            'METGRID_LEVELS=""\t\t# Empty: read in the met_em with ncdump',
            'NIVEAUX_METGRID=""\t\t# Vide : lus dans les met_em avec ncdump',
        ),
        tr(
            f'SPIN_UP_DIR="{n["spin_up"]}"\t# wrfout before D (spin-up of the 1st window), set aside at the end',
            f'DOSSIER_MISE_EN_ROUTE="{n["spin_up"]}"\t# wrfout avant D (mise en route de la 1re fenetre), mis de cote a la fin',
        ),
        tr(
            "CHECK_ORIGIN=1\t\t# 1: checks with ncdump that each wrfout comes from its window",
            "VERIFIER_ORIGINE=1\t\t# 1 : verifie avec ncdump que chaque wrfout vient de sa fenetre",
        ),
        "",
        *environment(context),
        *_advanced_notice(),
        f"MAX_DOM={len(context.domains)}",
        tr(
            f"CONTINUOUS={int(plan.restart)}\t\t# 1: windows chained by restart files (one spin-up)",
            f"CONTINU={int(plan.restart)}\t\t# 1 : fenetres enchainees par fichiers restart (une mise en route)",
        ),
        tr(
            f'STUDY_START="{_date(plan.start)}"\t# D, useful start of the study (UTC)',
            f'DEBUT_ETUDE="{_date(plan.start)}"\t# D, debut utile de l\'etude (UTC)',
        ),
        tr(
            f'STUDY_END="{_date(plan.end)}"\t# F, end of the study (UTC)',
            f'FIN_ETUDE="{_date(plan.end)}"\t# F, fin de l\'etude (UTC)',
        ),
        tr(
            f"SPIN_UP_S={spin_first}\t\t# Spin-up of the 1st window, in seconds (S, or more to start on a data time)",
            f"MISE_EN_ROUTE_S={spin_first}\t\t# Mise en route de la 1re fenetre, en secondes (S, ou plus pour partir d'un instant des donnees)",
        ),
        "",
        tr(
            "## Time step of each domain, in seconds: STEP_NUM / STEP_DEN (exact fraction)",
            "## Pas de temps de chaque domaine, en secondes : PAS_NUM / PAS_DEN (fraction exacte)",
        ),
        tr("STEP_NUM=(", "PAS_NUM=(")
        + " ".join(str(d.step.numerator) for d in context.domains)
        + ")",
        tr("STEP_DEN=(", "PAS_DEN=(")
        + " ".join(str(d.step.denominator) for d in context.domains)
        + ")",
        tr("ADAPTIVE_STEP", "PAS_ADAPTATIF")
        + f"={int(context.adaptive)}\t\t# 1 : use_adaptive_time_step",
        "",
        tr(
            "## Prefixes of the tslist and variables to keep (missing file: skipped)",
            "## Prefixes de la tslist et variables a recuperer (fichier absent : ignore)",
        ),
        "TSNAME=(" + " ".join(quote(name) for name in context.tslist) + ")",
        "TSVARS=(" + " ".join(TS_VARIABLES) + ")",
        "",
        tr(
            "## Plan of the windows (one line per window, never to be edited by hand), state file",
            "## Plan des fenetres (une ligne par fenetre, a ne jamais modifier a la main), fichier",
        ),
        tr(
            "## of the steps done (to resume) and this script (submitted again on Slurm)",
            "## d'etat des etapes faites (pour reprendre) et ce script (resoumis sur Slurm)",
        ),
        f'PLAN="../{n["plan"]}"',
        tr(f'STATE="logs/{n["state"]}"', f'ETAT="journaux/{n["state"]}"'),
        tr('WRF_SCRIPT="run_wrf.sh"', 'SCRIPT_WRF="run_wrf.sh"'),
        "",
        tr(
            "## Assembly of the period: expected lines of each series, by domain (-: adaptive step)",
            "## Assemblage de la periode : lignes attendues de chaque serie, par domaine (- : pas adaptatif)",
        ),
        tr("EXPECTED_LINES=(", "LIGNES_ATTENDUES=(")
        + " ".join(
            "-" if e is None else str(e)
            for e in (expected_lines(context, d) for d in context.domains)
        )
        + ")",
        tr(
            "## Time step (s) and constant step over the whole period (1: dt divides S and the windows)",
            "## Pas de temps (s) et pas constant sur toute la periode (1 : dt divise S et les fenetres)",
        ),
        tr("STEP_S=(", "PAS_S=(") + " ".join(f"{float(d.step):.6f}" for d in context.domains) + ")",
        tr("CONSTANT_STEP=(", "PAS_CONSTANT=(")
        + " ".join(str(int(constant_step(context, d))) for d in context.domains)
        + ")",
        tr(
            "## Interval of the wrfout of each domain (s)",
            "## Intervalle des wrfout de chaque domaine (s)",
        ),
        tr("OUTPUT_S=(", "SORTIES_S=(")
        + " ".join(str(d.history_seconds) for d in context.domains)
        + ")",
        tr(
            "## Expected wrfout of each domain, from D to F",
            "## Nombre de wrfout attendus de chaque domaine, de D a F",
        ),
        tr("EXPECTED_TIMES=(", "INSTANTS_ATTENDUS=(")
        + " ".join(str(_expected_count(plan, d.history_seconds)) for d in context.domains)
        + ")",
        "",
    ]
    lines += _functions_title()
    lines += [
        _pick(text.WRF_FUNCTIONS),
        _pick(text.CONCATENATE_FUNCTIONS),
        _pick(text.ASSEMBLY_FUNCTION),
    ]
    lines += _program_title()
    lines.append(_pick(text.WRF_PROGRAM))
    return "\n".join(lines).rstrip() + "\n"


def constant_step(context: ScriptContext, domain: Domain) -> bool:
    """Whether the assembled series advance by exactly one time step everywhere: a fixed step
    dividing the spin-up and every useful window, so that each window's first kept step follows
    the previous window's last one by one step."""
    if context.adaptive:
        return False
    durations = [int(w.spin_up.total_seconds()) for w in context.plan.windows] + [
        int((w.useful_end - w.useful_start).total_seconds()) for w in context.plan.windows
    ]
    return all(Fraction(seconds) % domain.step == 0 for seconds in durations)


def expected_lines(context: ScriptContext, domain: Domain) -> int | None:
    """Lines of an assembled series of the domain (header excluded); None with an adaptive
    step."""
    if context.adaptive:
        return None
    total = 0
    for window in context.plan.windows:
        first, last = kept_steps(window, domain.step)
        total += last - first + 1
    return total


def _expected_count(plan: Plan, seconds: int) -> int:
    return int((plan.end - plan.start).total_seconds()) // seconds + 1
