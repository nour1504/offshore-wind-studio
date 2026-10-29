"""Every file WPS and WRF need, in WRF's own formats, with the scripts that run the method on a
cluster (Slurm) or on a Linux computer, without the application.

    <project>-WRF/
      LISEZ-MOI.txt         order of execution and conventions (README.txt in English)
      manifest.json         plan, domains, time steps, time series, cells (read back on import)
      commun.sh             functions shared by every script (common.sh)
      plan_fenetres.csv     every window: block, order of computation, dates, read by run_wrf.sh
                            (window_plan.csv)
      wps/                  namelist.wps (+ .sst), Vtable.<source>, run_wps.sh
      wrf/                  namelist.input, turbine files, tslist, iofields, cellules.csv,
                            run_wrf.sh (the same on a cluster and a computer, assembly included)
      donnees/              download script of the input data (GFS or ERA5), when relevant; the
                            data go to the shared folder of the machine when one is given

Everything written for the user is in the language of the interface, names of files and folders
included (scripts.FILE_NAMES; the names of WRF and WPS never change). Text files are ASCII with LF
line ends, whatever system exports them; scripts are executable (permissions kept in the ZIP).
"""

import io
import json
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from owstudio import __version__
from owstudio.core import tslist
from owstudio.core.case.model import Case, GribInput
from owstudio.core.data import era5, gfs, vtables
from owstudio.core.data.examine import requested_times
from owstudio.core.engine.windows import child_case, wps_pass_case
from owstudio.core.i18n import current, tr
from owstudio.core.method import scripts, timesteps
from owstudio.core.method.plan import WRF_DATE, Plan, plan
from owstudio.core.method.scripts import ScriptContext, Source, ascii, names
from owstudio.core.namelist.generate import (
    IOFIELDS_FILE,
    EnginePaths,
    build_namelist_input,
    build_namelist_wps,
    iofields_text,
)
from owstudio.core.windfarm.files import LAYOUT_FILES, layout_text, turbine_rows, turbine_table

EXPORT_FORMAT = "offshore-wind-studio-export"
EXPORT_VERSION = 1
EXECUTABLE = 0o755


class SlurmOptions(BaseModel):
    nodes: int = Field(2, ge=1)
    ntasks_per_node: int | None = Field(None, ge=1)
    time: str = Field("72:00:00", pattern=r"^(\d+-)?\d{1,3}:\d{2}:\d{2}$")
    partition: str = Field("cn", max_length=64)
    exclusive: bool = True
    enable_turbo: bool = True
    wckey: str = Field("", max_length=64)
    # Editor mode: the raw #SBATCH header, used as is ({job}: name of each job)
    raw: str | None = Field(None, max_length=20_000)


class ExportOptions(BaseModel):
    target: Literal["cluster", "local"] = "cluster"
    # MPI processes of WRF (srun -n on a cluster, mpirun -np on a computer)
    cores: int = Field(96, ge=1, le=100_000)
    # MPI processes of geogrid and metgrid; ungrib always runs alone
    wps_cores: int = Field(12, ge=1, le=10_000)
    slurm: SlurmOptions = Field(default_factory=SlurmOptions)
    # Lines run before the programs: module load impi/... on a cluster, source <engine>/env.sh
    # on a computer
    environment: list[str] = Field(default_factory=list, max_length=50)
    # Empty, or a placeholder of either language: the placeholder of the current one
    wrf_dir: str = Field("", max_length=500)
    wps_dir: str = Field("", max_length=500)
    geog_dir: str = Field("", max_length=500)
    # Shared folder of the downloaded input data on a Linux computer (the engine's): every
    # calculation reads and downloads there; empty: the data/ folder of the package
    data_dir: str = Field("", max_length=500)
    # Files of each source on the machine that runs WPS, by prefix (%Y = year); empty: the
    # project's folder when it is a Linux path, else a placeholder
    inputs: dict[str, str] = Field(default_factory=dict)


def safe_name(name: str) -> str:
    plain = ascii(name).strip()
    cleaned = "".join(c if c.isalnum() or c in "-_" else "-" for c in plain).strip("-")
    return cleaned or tr("project", "projet")


def program_folder(value: str, program: str) -> str:
    """The folder of a program on the machine that runs it, or a placeholder in the current
    language when it is not given (a placeholder of the other language included)."""
    from owstudio.core.method.scripts import FILE_NAMES

    placeholders = {f"{names['path']}/{program}" for names in FILE_NAMES.values()}
    value = value.strip()
    return f"{names()['path']}/{program}" if not value or value in placeholders else value


def data_folder(options: ExportOptions) -> str:
    """The shared folder of the input data, when a Linux path is given (absolute, or from ~ or
    $HOME as the Compute page accepts it)."""
    value = options.data_dir.strip().rstrip("/")
    return value if value.startswith(("/", "~", "$")) else ""


def _data_base(options: ExportOptions) -> str:
    """Where ungrib finds the downloaded data, seen from wps/."""
    return data_folder(options) or f"../{names()['data']}"


def _iso(time: datetime) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ")


def _netcdf_files(settings: GribInput) -> list[Path]:
    """The user's files when the folder is on this computer and holds only NetCDF files, which
    ungrib cannot read: they are converted at export. Empty otherwise (GRIB read by ungrib)."""
    from owstudio.core.data import userfiles

    folder = settings.folder.strip()
    if not folder or folder.replace("\\", "/").startswith("/") and not Path(folder).is_dir():
        return []
    try:
        files = userfiles.list_files(folder, settings.pattern, sniff_all=True)
    except (FileNotFoundError, OSError):
        return []
    return [f.path for f in files] if userfiles.all_netcdf(files) else []


def _own_pattern(settings: GribInput) -> str:
    folder = settings.folder.strip().replace("\\", "/")
    if folder.startswith("/"):
        return f"{folder.rstrip('/')}/{settings.pattern}"
    return f"{names()['own_files']}/{settings.pattern}"


def _vtable_text(settings: GribInput | None, standard: str) -> str:
    if settings is not None and settings.vtable == "custom":
        return settings.custom_vtable
    return vtables.read(settings.vtable if settings is not None else standard)


def _vtable_name(settings: GribInput | None, standard: str, prefix: str) -> str:
    """The file of a Vtable in wps/: the name of the table itself (Vtable.GFS, Vtable.ECMWF...),
    linked as Vtable before ungrib; a table of the user is Vtable.<prefix>.perso."""
    if settings is not None and settings.vtable == "custom":
        return f"Vtable.{prefix}.perso"
    return settings.vtable if settings is not None else standard


def sources(case: Case, options: ExportOptions) -> list[tuple[Source, str]]:
    """Inputs of ungrib in metgrid's order, each with its Vtable text."""
    found: list[tuple[Source, str]] = []
    if case.input_source == "gfs":
        atmosphere = Source("FILE", f"{_data_base(options)}/gfs/%Y/gfs.*.grib2", "Vtable.GFS")
        found.append((atmosphere, vtables.read("Vtable.GFS")))
    elif case.input_source == "era5":
        atmosphere = Source("FILE", f"{_data_base(options)}/era5/%Y/era5-*.grib", "Vtable.ECMWF")
        found.append((atmosphere, vtables.read("Vtable.ECMWF")))
    else:
        assert case.grib is not None
        found.append(_own_source("FILE", case.grib, "Vtable.GFS"))
    if case.land is not None:
        found.append(_own_source(case.land.prefix, case.land, "Vtable.ECMWF"))
    if case.sea_surface.source == "grib" and case.sea_surface.grib is not None:
        found.append(_own_source("SST", case.sea_surface.grib, "Vtable.SST", sst=True))
    # Two sources may use the same table (one file); the same name with another text gets the
    # source's prefix
    texts: dict[str, str] = {}
    out: list[tuple[Source, str]] = []
    for s, text in found:
        name = s.vtable_file
        if not s.converted and texts.get(name, text) != text:
            name = f"{name}.{s.prefix}"
        texts[name] = text
        pattern = s.pattern if s.converted else options.inputs.get(s.prefix, s.pattern)
        out.append((Source(s.prefix, pattern, name, sst=s.sst, converted=s.converted), text))
    return out


def _own_source(
    prefix: str, settings: GribInput, standard: str, sst: bool = False
) -> tuple[Source, str]:
    if _netcdf_files(settings):
        folder = f"{names()['intermediate']}/{prefix}"
        return Source(prefix, folder, "", sst=sst, converted=True), ""
    vtable = _vtable_name(settings, standard, prefix)
    return Source(prefix, _own_pattern(settings), vtable, sst=sst), _vtable_text(settings, standard)


def conversions(case: Case) -> list[tuple[str, list[Path], list[datetime]]]:
    """The user's NetCDF sources to convert at export: (prefix, files, times). The times are
    every boundary time of every WPS pass (spin-up included), which metgrid reads."""
    windows_plan = plan(case)
    times = sorted(
        {
            t
            for wps in windows_plan.wps_passes
            for t in requested_times(wps.start, wps.end, case.period.interval_seconds)
        }
    )
    found = []
    settings: list[tuple[str, GribInput | None]] = [
        ("FILE", case.grib if case.input_source == "grib" else None),
        (case.land.prefix if case.land is not None else "", case.land),
        ("SST", case.sea_surface.grib if case.sea_surface.source == "grib" else None),
    ]
    for prefix, chosen in settings:
        if chosen is not None:
            paths = _netcdf_files(chosen)
            if paths:
                found.append((prefix, paths, times))
    return found


def convert_inputs(case: Case, wps_folder: Path) -> list[Path]:
    """Converts the user's NetCDF files into wps/<intermediate>/<prefix>/ of the package, on
    this computer; returns the files written."""
    from owstudio.core.data import examine, netcdf

    box = examine.context_of(case).domain
    area = None if box is None else (box.south, box.north, box.west, box.east)
    written: list[Path] = []
    for prefix, paths, times in conversions(case):
        folder = wps_folder / names()["intermediate"] / prefix
        done = netcdf.convert(paths, prefix, times, case.period.interval_seconds, folder, area)
        (folder / ".complete").unlink(missing_ok=True)
        written += [folder / name for name in done.names]
    return written


def sst_windows(
    case: Case, windows_plan: Plan, step_hours: int = 24
) -> dict[int, tuple[datetime, datetime]]:
    """SST pass of ungrib for each WPS pass: from the last SST time at or before its start to the
    first at or after its end, SST times every ``step_hours`` from 00 UTC, so that ungrib
    interpolates every boundary time between two SST records (WPS ungrib.F, datint)."""
    if case.sea_surface.source != "grib":
        return {}
    step = timedelta(hours=step_hours)
    result = {}
    for wps in windows_plan.wps_passes:
        midnight = wps.start.replace(hour=0, minute=0, second=0, microsecond=0)
        start = midnight + ((wps.start - midnight) // step) * step
        midnight = wps.end.replace(hour=0, minute=0, second=0, microsecond=0)
        end = midnight + -((midnight - wps.end) // step) * step
        result[wps.year] = (start, end)
    return result


def _sst_step_hours(case: Case) -> int:
    """Time step of the separate SST files, read from them when they are reachable; 24 h
    (daily analyses: OSTIA, RTG) otherwise."""
    try:
        from owstudio.core.data import examine

        report = examine.examine_case(case, "sst", budget_bytes=200_000_000)
    except (OSError, ValueError):  # unreachable or unreadable files: the usual daily step
        return 24
    step = report.step_hours if report is not None else None
    return int(step) if step and step >= 1 and float(step).is_integer() else 24


def context_for(case: Case, options: ExportOptions, now: datetime) -> ScriptContext:
    windows_plan = plan(case)
    steps = timesteps.time_steps(case)
    history = timesteps.history_seconds(case)
    return ScriptContext(
        project=case.name,
        version=__version__,
        generated=now,
        cluster=options.target == "cluster",
        plan=windows_plan,
        domains=[
            scripts.Domain(n, steps.steps[n - 1], history[n - 1])
            for n in range(1, case.max_dom + 1)
        ],
        adaptive=steps.adaptive,
        tslist=[point.prefix for point in tslist.locations(case)],
        sources=[source for source, _ in sources(case, options)],
        sst_windows=sst_windows(case, windows_plan, _sst_step_hours(case)),
        wrf_dir=program_folder(options.wrf_dir, "WRF"),
        wps_dir=program_folder(options.wps_dir, "WPS"),
        geog_dir=program_folder(options.geog_dir, "WPS_GEOG"),
        data_dir=data_folder(options),
        cores=options.cores,
        wps_cores=options.wps_cores,
        slurm=scripts.Slurm(**options.slurm.model_dump()),
        environment=options.environment,
    )


def namelist_text(nml: Any) -> str:
    buffer = io.StringIO()
    nml.write(buffer)
    return buffer.getvalue()


def _csv(rows: list[list[object]]) -> str:
    def cell(value: object) -> str:
        text = ascii(str(value))
        return f'"{text.replace(chr(34), chr(34) * 2)}"' if any(c in text for c in ',"') else text

    return "".join(",".join(cell(v) for v in row) + "\n" for row in rows)


def plan_csv(context: ScriptContext) -> str:
    """The plan of the windows, for a spreadsheet and for run_wrf.sh, which reads every column
    after the dates (never quoted: no comma in them)."""
    windows_plan = context.plan
    if current() == "en":
        header = [
            "window",
            "computation_order",
            "block",
            "simulation_start",
            "simulation_end",
            "useful_start",
            "useful_end",
            "useful_hours",
            "simulated_hours",
            "simulated_s",
            "offset_from_D_s",
            "restart",
            "spin_up_s",
            "real_end",
            "real_s",
            *[f"last_step_d{d.number:02d}" for d in context.domains],
        ]
    else:
        header = [
            "fenetre",
            "ordre_calcul",
            "bloc",
            "debut_simulation",
            "fin_simulation",
            "debut_utile",
            "fin_utile",
            "heures_utiles",
            "heures_simulees",
            "duree_simulee_s",
            "decalage_depuis_D_s",
            "reprise",
            "mise_en_route_s",
            "fin_real",
            "duree_real_s",
            *[f"dernier_pas_d{d.number:02d}" for d in context.domains],
        ]
    rows: list[list[object]] = [list(header)]
    for w in windows_plan.windows:
        rows.append(
            [
                w.id,
                w.order,
                w.block,
                w.simulation_start.strftime(WRF_DATE),
                w.simulation_end.strftime(WRF_DATE),
                w.useful_start.strftime(WRF_DATE),
                w.useful_end.strftime(WRF_DATE),
                f"{w.useful_hours:g}",
                f"{w.simulated_seconds / 3600:g}",
                *scripts.plan_columns(w, windows_plan, context.domains),
            ]
        )
    return _csv(rows)


def cells_csv(case: Case) -> str:
    rows: list[list[object]] = [
        ["tslist_prefix", "domain", "i", "j", "turbine_count", "turbines", "farms"]
        if current() == "en"
        else ["prefixe_tslist", "domaine", "i", "j", "nombre_eoliennes", "eoliennes", "parcs"]
    ]
    for cell in tslist.cells(case):
        prefixes = (
            cell.prefix
            if cell.prefix
            else " ".join(t.prefix for t in cell.turbines if t.prefix) or ""
        )
        rows.append(
            [
                prefixes,
                cell.domain,
                cell.i,
                cell.j,
                len(cell.turbines),
                " ".join(t.label for t in cell.turbines),
                " ".join(cell.farms),
            ]
        )
    return _csv(rows)


def _grouping(grouping: str) -> str:
    return {
        "month": tr("calendar month", "mois civil"),
        "quarter": tr("quarter (3 calendar months)", "trimestre (3 mois civils)"),
        "week": tr("week (Monday 00:00 UTC)", "semaine (lundi 00:00 UTC)"),
        "window": tr("each window", "chaque fenetre"),
    }[grouping]


def _chain(case: Case) -> str:
    """Every step of a Linux computer in one command line, from the package's folder."""
    n = names()
    steps = []
    if case.input_source == "gfs":
        steps.append(f"cd {n['data']} && bash {n['download_gfs']} && cd ..")
    elif case.input_source == "era5":
        steps.append(f"cd {n['data']} && python3 {n['download_era5']} && cd ..")
    steps.append("cd wps && bash run_wps.sh && cd ../wrf && bash run_wrf.sh")
    return " && ".join(steps)


def _steps(case: Case, cluster: bool, french: bool, data_dir: str = "") -> list[str]:
    """The steps of a calculation in the README: each with where to run it, what it does,
    how to see that it is done, and what to do when it stops."""
    n = names()
    run = "sbatch" if cluster else "bash"
    data = case.input_source in ("gfs", "era5")
    script = n["download_era5"] if case.input_source == "era5" else n["download_gfs"]
    tool = "python3" if case.input_source == "era5" else "bash"
    log = n["run_log"]
    where = data_dir or n["data"]
    # On a cluster each Slurm job writes its own journal next to its script
    if cluster:
        journal = (
            "wps/WPS_<numero>.out et wrf/WRF_<numero>.out (lignes ERREUR dans les .err)"
            if french
            else "wps/WPS_<number>.out and wrf/WRF_<number>.out (ERROR lines in the .err)"
        )
        tail = "tail -n 15 wrf/WRF_*.out wrf/WRF_*.err"
    else:
        journal, tail = log, f"tail -n 15 {log}"
    if french:
        lines = [
            "ETAPES (dans l'ordre ; chaque commande se lance depuis le dossier indique)",
            "",
            "1. Verifier les chemins",
            "   En tete de wps/run_wps.sh et de wrf/run_wrf.sh, les PARAMETRES DE BASE donnent",
            "   les dossiers de WRF, de WPS, de la geographie (WPS_GEOG) et les fichiers d'entree.",
            "   Le logiciel les a remplis ; un chemin faux arrete le calcul (geogrid, ungrib).",
            "   Pour les lire, depuis ce dossier :",
            "     head -n 45 wps/run_wps.sh",
            *(["   Verifier aussi les OPTIONS POUR SLURM de chaque script."] if cluster else []),
            "",
        ]
        if cluster:
            lines += [
                "2. Copier ce dossier sur le cluster, puis, dans l'ordre :",
                *([f"   - les donnees, depuis {n['data']}/ : {tool} {script}"] if data else []),
                f"   - WPS, depuis wps/ : {run} run_wps.sh",
                f"   - WRF, quand WPS est fini, depuis wrf/ : {run} run_wrf.sh",
                "   Avant chaque fenetre, run_wrf.sh verifie qu'il lui reste le temps de la finir",
                "   avant la limite du calcul (--time) ; sinon il se soumet de nouveau (sbatch) et",
                "   s'arrete : le nouveau calcul reprend a la fenetre suivante.",
                "",
            ]
        else:
            lines += [
                "2. Lancer tout le calcul d'un coup (conseille), depuis ce dossier :",
                *(
                    [f"   donnees ({n['data']}/), puis WPS (wps/), puis WRF (wrf/) ;"]
                    if data
                    else ["   WPS (wps/), puis WRF (wrf/) ;"]
                ),
                f"   chaque etape est notee avec l'heure dans {log}.",
                "   - Sur une VM ou un serveur (continue apres la deconnexion) :",
                f"     setsid nohup bash -c '{_chain(case)}' > {log} 2>&1 < /dev/null &",
                "   - Sur cet ordinateur (s'arrete si on l'eteint ou ferme le terminal) :",
                f"     bash -c '{_chain(case)}' 2>&1 | tee {log}",
                "",
            ]
        lines += [
            "3. Les etapes du calcul, une par une",
            f"   Pour toutes : {journal} note chaque etape avec l'heure ; c'est le",
            f"   premier journal a lire. Ou en est-on : {tail}",
            "",
            *(
                [
                    f"   a. Donnees d'entree ({n['data']}/{script})",
                    f"      Fait : telecharge les donnees du projet dans {where}/{case.input_source}/<annee>/ ;",
                    "      un fichier deja present n'est pas retelecharge.",
                    f"      Journal : {log if not cluster else "l'ecran (lance a la main)"}.",
                    f"      Fini quand : '{case.input_source.upper()} telecharge' apparait {'dans ' + log if not cluster else "a l'ecran"}.",
                    "      Rate le plus souvent : pas d'internet ou un proxy (relancer garde les fichiers",
                    "      deja telecharges)"
                    + (
                        " ; cle Copernicus absente de ~/.cdsapirc."
                        if case.input_source == "era5"
                        else "."
                    ),
                    "",
                ]
                if data
                else []
            ),
            "   b. WPS (wps/run_wps.sh) : met les donnees au format de WRF, sur vos domaines",
            "      1) geogrid : decoupe la geographie (relief, sol, vegetation) sur les domaines",
            "         -> wps/geo_em.d0N.nc. Une seule fois.",
            "      2) ungrib : lit les donnees d'entree (GRIB) avec la table Vtable",
            "         -> wps/ungrib/<annee>/ (format intermediaire de WPS).",
            "      3) metgrid : les interpole sur les domaines -> wps/met_em/met_em.d0N.<date>.nc.",
            f"      Journaux : wps/{n['logs']}/geogrid.txt, ungrib_<source>_<annee>.txt,",
            "      metgrid_<annee>.txt (ce que chaque programme affiche) ; le detail ecrit par WPS :",
            "      wps/geogrid.log*, wps/ungrib.log, wps/metgrid.log*.",
            f"      Fini quand : 'WPS termine' apparait dans {journal}.",
            "      Rate le plus souvent : geogrid -> chemin de la geographie faux, ou sans la",
            "      resolution choisie ; ungrib -> donnees d'entree absentes ou incompletes.",
            "",
            "   c. WRF (wrf/run_wrf.sh) : le calcul, fenetre par fenetre, de la derniere a la premiere",
            "      Pour chaque fenetre :",
            "      1) real.exe : prepare l'etat de depart et les bords -> wrf/wrfinput_d0N,",
            "         wrf/wrfbdy_d01 ;",
            "      2) wrf.exe : le calcul -> wrf/wrfout_d0N_<date> (un fichier par instant) et les",
            "         series de vos points (tslist), decoupees dans wrf/tslist_fenetres/ ;",
            f"      3) la fenetre est notee dans wrf/{n['logs']}/{n['state']} (relance : elle est sautee).",
            "      Apres les fenetres d'un bloc, ses series vont dans wrf/tslist_blocs/ ; a la fin,",
            "      toute la periode dans wrf/tslist_periode/, et les wrfout d'avant D (mise en route)",
            f"      dans wrf/{n['spin_up']}/.",
            "      Journaux : pendant real.exe ou wrf.exe, wrf/rsl.error.0000 (chaque pas de temps y",
            "      ajoute une ligne 'Timing for main' avec l'instant simule) ; apres chaque fenetre,",
            f"      wrf/{n['logs']}/real_<fenetre>.txt et wrf_<fenetre>.txt (ce que le programme affiche),",
            "      *.rsl.txt (la copie de son rsl.error.0000) et namelist.input.<fenetre>.",
            f"      Fini quand : 'Termine.' apparait dans {journal}.",
            "      Rate le plus souvent : real.exe -> met_em manquants ; wrf.exe -> instabilite",
            "      ('cfl' dans rsl.error.0000 : pas de temps trop grand) ou plus de place disque.",
            "",
            "4. Si le calcul s'arrete",
            f"   - La ligne 'ERREUR :' a la fin de {journal} dit quelle etape a rate et pourquoi",
            f"     ({tail}) ; le detail est dans les journaux (etape 3 et COMMANDES UTILES).",
            "   - Corriger (souvent un chemin, ou une donnee manquante), puis relancer :",
            *(
                [
                    "     la meme commande que pour l'etape qui a rate.",
                ]
                if cluster
                else [
                    "     tout (etape 2) : les donnees deja la ne sont pas retelechargees, WPS est",
                    "     refait, WRF reprend a la premiere fenetre non finie ;",
                    "     ou seulement WRF, si WPS etait fini (VM ou serveur), depuis ce dossier :",
                    f"     setsid nohup bash -c 'cd wrf && bash run_wrf.sh' >> {log} 2>&1 < /dev/null &",
                ]
            ),
            "",
            "5. A la fin : importer les resultats dans le logiciel",
            "   Resultats > Importer des sorties > ce dossier (celui qui contient manifest.json) ;",
            "   Lier evite de recopier les gros fichiers. Le logiciel prend les wrfout de [D, F]",
            "   dans wrf/ et les series de wrf/tslist_periode/.",
        ]
        return lines
    lines = [
        "STEPS (in order; each command runs from the folder given)",
        "",
        "1. Check the paths",
        "   At the top of wps/run_wps.sh and wrf/run_wrf.sh, the BASIC SETTINGS give the folders",
        "   of WRF, WPS, the geography (WPS_GEOG) and the input files. The application filled",
        "   them in; a wrong path stops the run (geogrid, ungrib). To read them, from this folder:",
        "     head -n 45 wps/run_wps.sh",
        *(["   Check the SLURM OPTIONS of each script too."] if cluster else []),
        "",
    ]
    if cluster:
        lines += [
            "2. Copy this folder to the cluster, then, in order:",
            *([f"   - the data, from {n['data']}/: {tool} {script}"] if data else []),
            f"   - WPS, from wps/: {run} run_wps.sh",
            f"   - WRF, once WPS is done, from wrf/: {run} run_wrf.sh",
            "   Before each window, run_wrf.sh checks that there is time left to finish it before",
            "   the job's limit (--time); otherwise it submits itself again (sbatch) and stops:",
            "   the new job resumes at the next window.",
            "",
        ]
    else:
        lines += [
            "2. Run the whole calculation at once (recommended), from this folder:",
            *(
                [f"   data ({n['data']}/), then WPS (wps/), then WRF (wrf/);"]
                if data
                else ["   WPS (wps/), then WRF (wrf/);"]
            ),
            f"   each step is written with its time in {log}.",
            "   - On a VM or a server (goes on after disconnecting):",
            f"     setsid nohup bash -c '{_chain(case)}' > {log} 2>&1 < /dev/null &",
            "   - On this computer (stops if it is switched off or the terminal is closed):",
            f"     bash -c '{_chain(case)}' 2>&1 | tee {log}",
            "",
        ]
    lines += [
        "3. The steps of the run, one by one",
        f"   For all of them: {journal} writes each step with its time; it is the",
        f"   first log to read. Where the run is: {tail}",
        "",
        *(
            [
                f"   a. Input data ({n['data']}/{script})",
                f"      Does: downloads the data of the project into {where}/{case.input_source}/<year>/;",
                "      a file already there is not downloaded again.",
                f"      Log: {log if not cluster else 'the screen (run by hand)'}.",
                f"      Done when: '{case.input_source.upper()} downloaded' appears {'in ' + log if not cluster else 'on the screen'}.",
                "      Most often fails: no internet or a proxy (running again keeps the files",
                "      already downloaded)"
                + (
                    "; Copernicus key missing from ~/.cdsapirc."
                    if case.input_source == "era5"
                    else "."
                ),
                "",
            ]
            if data
            else []
        ),
        "   b. WPS (wps/run_wps.sh): puts the data in WRF's format, on your domains",
        "      1) geogrid: cuts the geography (relief, soil, vegetation) on the domains",
        "         -> wps/geo_em.d0N.nc. Once only.",
        "      2) ungrib: reads the input data (GRIB) with the Vtable",
        "         -> wps/ungrib/<year>/ (WPS intermediate format).",
        "      3) metgrid: interpolates them on the domains -> wps/met_em/met_em.d0N.<date>.nc.",
        f"      Logs: wps/{n['logs']}/geogrid.txt, ungrib_<source>_<year>.txt, metgrid_<year>.txt",
        "      (what each program prints); the detail written by WPS: wps/geogrid.log*,",
        "      wps/ungrib.log, wps/metgrid.log*.",
        f"      Done when: 'WPS done' appears in {journal}.",
        "      Most often fails: geogrid -> wrong geography path, or without the resolution",
        "      chosen; ungrib -> input data missing or incomplete.",
        "",
        "   c. WRF (wrf/run_wrf.sh): the run, window by window, from the last to the first",
        "      For each window:",
        "      1) real.exe: prepares the initial state and the boundaries -> wrf/wrfinput_d0N,",
        "         wrf/wrfbdy_d01;",
        "      2) wrf.exe: the run -> wrf/wrfout_d0N_<date> (one file per instant) and the series",
        "         of your points (tslist), cut into wrf/tslist_windows/;",
        f"      3) the window is written in wrf/{n['logs']}/{n['state']} (run again: it is skipped).",
        "      After the windows of a block, its series go to wrf/tslist_blocks/; at the end, the",
        "      whole period in wrf/tslist_period/, and the wrfout before D (spin-up) in",
        f"      wrf/{n['spin_up']}/.",
        "      Logs: while real.exe or wrf.exe runs, wrf/rsl.error.0000 (each time step adds a",
        "      'Timing for main' line with the simulated instant); after each window,",
        f"      wrf/{n['logs']}/real_<window>.txt and wrf_<window>.txt (what the program prints),",
        "      *.rsl.txt (the copy of its rsl.error.0000) and namelist.input.<window>.",
        f"      Done when: 'Done.' appears in {journal}.",
        "      Most often fails: real.exe -> met_em missing; wrf.exe -> instability ('cfl' in",
        "      rsl.error.0000: time step too large) or no disk space left.",
        "",
        "4. If the run stops",
        f"   - The 'ERROR:' line at the end of {journal} says which step failed and why",
        f"     ({tail}); the detail is in the logs (step 3 and USEFUL COMMANDS).",
        "   - Fix it (often a path, or missing data), then run again:",
        *(
            ["     the same command as for the step that failed."]
            if cluster
            else [
                "     everything (step 2): data already there are not downloaded again, WPS is",
                "     redone, WRF resumes at the first window not done;",
                "     or WRF only, if WPS was done (VM or server), from this folder:",
                f"     setsid nohup bash -c 'cd wrf && bash run_wrf.sh' >> {log} 2>&1 < /dev/null &",
            ]
        ),
        "",
        "5. At the end: import the results into the application",
        "   Results > Import outputs > this folder (the one holding manifest.json); Link avoids",
        "   copying the large files. The application takes the wrfout of [D, F] in wrf/ and the",
        "   series of wrf/tslist_period/.",
    ]
    return lines


def readme(case: Case, context: ScriptContext, files: list[str]) -> str:
    """LISEZ-MOI.txt (README.txt in English): the method, the order of execution, the
    conventions and one line per file."""
    if current() == "en":
        return _readme_en(case, context, files)
    n = names()
    p = context.plan
    converted = [s.prefix for s in context.sources if s.converted]
    first = p.computation[0]
    cluster = context.cluster
    lines = [
        f"OFFSHORE WIND STUDIO {context.version} - FICHIERS WRF DU PROJET {ascii(case.name)}",
        f"Exportes le {context.generated:%Y-%m-%d %H:%M} UTC pour {'un cluster (Slurm)' if cluster else 'un ordinateur Linux'}.",
        "",
        "PERIODE, FENETRES, BLOCS",
        "- La periode : ce qu'on etudie, de D a F ; ce sont les resultats gardes.",
        "- Une fenetre : un lancement de WRF sur un morceau de la periode, precede de quelques",
        "  heures de mise en route (WRF part des donnees d'entree et se stabilise ; ces heures",
        "  sont jetees). Une longue periode est calculee en plusieurs fenetres.",
        "- Un bloc : des fenetres qui se suivent (un mois, une semaine...) ; les series de ses",
        "  fenetres sont mises bout a bout, puis les blocs entre eux pour toute la periode.",
        "",
        "PERIODE ET METHODE",
        f"- Periode d'etude (UTC) : D = {p.start:%Y-%m-%d %H:%M} -> F = {p.end:%Y-%m-%d %H:%M}.",
        *(
            [
                f"- Mise en route (spin-up) S = {p.spin_up_hours} h avant la 1re fenetre seulement, ecartee.",
                f"- Fenetre utile L = {p.useful_hours} h ; regroupement : {_grouping(p.grouping)}.",
                f"- {len(p.windows)} fenetre(s), {len(p.blocks)} bloc(s) : voir {n['plan']}.",
                "- FENETRES ENCHAINEES (restart de WRF) : une seule simulation. Les fenetres sont calculees dans l'ordre",
                "  chronologique ; chacune repart (restart = .true.) du wrfrst ecrit a la fin de la",
                "  precedente (restart_interval = sa duree). Seul le dernier wrfrst est garde.",
                "- frames_per_outfile = 1 : un wrfout par instant. Chaque wrfout de [D, F] vient de la",
                "  fenetre dont l'intervalle utile ]debut, fin] le contient (D vient de la 1re fenetre).",
                f"  Les wrfout d'avant D sont deplaces dans wrf/{n['spin_up']}/.",
            ]
            if p.restart
            else [
                f"- Mise en route (spin-up) S = {p.spin_up_hours} h avant chaque fenetre, toujours ecartee.",
                f"- Fenetre utile L = {p.useful_hours} h ; regroupement : {_grouping(p.grouping)}.",
                f"- {len(p.windows)} fenetre(s), {len(p.blocks)} bloc(s) : voir {n['plan']}.",
                "- Chaque fenetre part a froid (real.exe puis wrf.exe), sans reprise (restart = .false.,",
                "  aucun fichier wrfrst). Les fenetres sont decoupees depuis la fin de leur bloc (la plus",
                "  courte est au debut) et calculees dans l'ordre antichronologique, dans le meme dossier.",
                "- frames_per_outfile = 1 : un wrfout par instant. La mise en route d'une fenetre recouvre",
                "  la fin de la precedente ; celle-ci, calculee apres, ecrase ces wrfout. A la fin, chaque",
                "  wrfout de [D, F] vient de la fenetre dont l'intervalle utile ]debut, fin] le contient",
                f"  (D vient de la 1re fenetre). Les wrfout d'avant D sont deplaces dans wrf/{n['spin_up']}/.",
            ]
        ),
        "",
    ]
    lines += _steps(case, cluster, french=True, data_dir=context.data_dir)
    lines += [
        "",
        "COMMANDES UTILES (depuis ce dossier)",
        *(
            ['- Calculs en file ou en cours : squeue -u "$USER"']
            if cluster
            else [
                f"- Ou en est le calcul, ou il s'est arrete : tail -n 15 {n['run_log']}",
                "  (derniere ligne '> programme...' : l'etape en cours ; 'ERREUR :' : l'etape ratee",
                "  et pourquoi ; 'Termine.' : fini)",
                f"- Etapes au fil de l'eau : tail -f {n['run_log']}",
            ]
        ),
        "- Programmes qui tournent : ps -ef | grep -E '(geogrid|ungrib|metgrid|real|wrf)[.]exe' | grep -v grep",
        "- Instant atteint par WRF : grep 'Timing for main' wrf/rsl.error.0000 | tail -n 3",
        f"- Fenetres finies : cat wrf/{n['logs']}/{n['state']}",
        "- Erreurs de WRF : grep -i -E 'error|fatal' wrf/rsl.error.0000",
        "- Erreurs de WPS : tail -n 20 wps/geogrid.log* wps/metgrid.log*",
        "",
        "WPS",
        "- Un passage par annee civile, coupe a la periode, commencant S heures avant son debut",
        "  (y compris au 1er janvier). Les met_em de toutes les annees vont dans wps/met_em/.",
        "- ungrib par source (" + ", ".join(s.prefix for s in context.sources) + ") puis metgrid",
        "  avec tous les fg_name ; la derniere source l'emporte pour un champ commun.",
        *(
            [
                f"- Sources NetCDF ({', '.join(converted)}) : converties par le logiciel dans",
                f"  wps/{n['intermediate']}/<source>/ ; le script les relie sans lancer ungrib.",
            ]
            if converted
            else []
        ),
        "- Chaque programme doit afficher 'Successful completion', sinon le script s'arrete.",
        "",
        "WRF",
        f"- namelist.input est pret pour la premiere fenetre calculee ({first.simulation_start:%Y-%m-%d %H:%M} ->",
        f"  {first.simulation_end:%Y-%m-%d %H:%M}) ; le script reecrit les dates (start_*, end_*, run_*)",
        "  de chaque fenetre. num_metgrid_levels est lu dans les met_em (ncdump).",
        "- real.exe et wrf.exe doivent ecrire SUCCESS COMPLETE dans rsl.error.0000, sinon le",
        "  script s'arrete sans toucher aux sorties. Les scripts rendent 0 en cas de succes.",
        "",
        "SERIES TEMPORELLES (TSLIST)",
        "- Apres chaque wrf.exe, chaque fichier <prefixe>.dNN.<VAR> est decoupe : on garde les pas",
        "  de ]debut utile, fin utile], selectionnes par numero de pas (dt exact de chaque domaine,",
        "  temps WRF = n x dt depuis le debut de la simulation) ; les nombres de lignes sont controles.",
        "- Le temps (2e colonne de .TS, 1re des profils) devient des HEURES DEPUIS D ; la ligne",
        "  d'en-tete (le point) est gardee une fois, avec la date D a la place du debut de simulation.",
        f"- wrf/{n['tslist_blocks']}/ : un fichier par bloc ; wrf/{n['tslist_period']}/ : la periode ]D, F],",
        "  temps strictement croissant, sans trou ni doublon, nombre de lignes controle.",
        f"- {n['cells']} : prefixe, domaine, maille (i, j), eoliennes et parcs de chaque maille.",
        "  Plusieurs eoliennes d'une meme maille donnent la meme serie : une serie par maille.",
        "",
        "CONVENTIONS",
        "- Toutes les dates sont en UTC.",
        "- wrfout : instants de [D, F] ; series tslist et moyennes : ]D, F].",
        "- Moyennes 10 min (faites par le logiciel a l'import) : intervalles ]t - 10 min, t],",
        "  horodates a la fin t ; chaque valeur WRF compte pour le pas qui se termine a elle.",
        "- POWER (wrfout) est la puissance de toutes les eoliennes d'une maille.",
        "",
        "PAS DE TEMPS (s)",
    ]
    for domain in context.domains:
        lines.append(
            f"- d{domain.number:02d} : {float(domain.step):g} s"
            f"{' (adaptatif)' if context.adaptive else ''} ; wrfout toutes les {domain.history_seconds // 60} min."
        )
    lines += ["", "FICHIERS", *[f"- {name}{_role(name)}" for name in files], ""]
    return "\n".join(lines)


def _readme_en(case: Case, context: ScriptContext, files: list[str]) -> str:
    n = names()
    p = context.plan
    converted = [s.prefix for s in context.sources if s.converted]
    first = p.computation[0]
    cluster = context.cluster
    lines = [
        f"OFFSHORE WIND STUDIO {context.version} - WRF FILES OF THE PROJECT {ascii(case.name)}",
        f"Exported on {context.generated:%Y-%m-%d %H:%M} UTC for {'a cluster (Slurm)' if cluster else 'a Linux computer'}.",
        "",
        "PERIOD, WINDOWS, BLOCKS",
        "- The period: what is studied, from D to F; these are the results kept.",
        "- A window: one run of WRF over a piece of the period, after a few hours of spin-up",
        "  (WRF starts from the input data and settles; these hours are thrown away). A long",
        "  period is computed in several windows.",
        "- A block: windows that follow each other (a month, a week...); the series of its",
        "  windows are put end to end, then the blocks together for the whole period.",
        "",
        "PERIOD AND METHOD",
        f"- Study period (UTC): D = {p.start:%Y-%m-%d %H:%M} -> F = {p.end:%Y-%m-%d %H:%M}.",
        *(
            [
                f"- Spin-up S = {p.spin_up_hours} h before the 1st window only, left out.",
                f"- Useful window L = {p.useful_hours} h; grouping: {_grouping(p.grouping)}.",
                f"- {len(p.windows)} window(s), {len(p.blocks)} block(s): see {n['plan']}.",
                "- CHAINED WINDOWS (WRF restart): one simulation. The windows are computed in chronological",
                "  order; each one starts again (restart = .true.) from the wrfrst written at the end of",
                "  the previous one (restart_interval = its length). Only the last wrfrst is kept.",
                "- frames_per_outfile = 1: one wrfout per time. Each wrfout of [D, F] comes from the",
                "  window whose useful interval ]start, end] holds it (D comes from the 1st window).",
                f"  The wrfout before D are moved to wrf/{n['spin_up']}/.",
            ]
            if p.restart
            else [
                f"- Spin-up S = {p.spin_up_hours} h before each window, always left out.",
                f"- Useful window L = {p.useful_hours} h; grouping: {_grouping(p.grouping)}.",
                f"- {len(p.windows)} window(s), {len(p.blocks)} block(s): see {n['plan']}.",
                "- Each window starts cold (real.exe then wrf.exe), without restart (restart = .false.,",
                "  no wrfrst file). The windows are cut from the end of their block (the shortest one",
                "  comes first) and computed in antichronological order, in the same folder.",
                "- frames_per_outfile = 1: one wrfout per time. The spin-up of a window overlaps the end",
                "  of the previous one; that one, computed afterwards, overwrites those wrfout. In the end,",
                "  each wrfout of [D, F] comes from the window whose useful interval ]start, end] holds it",
                f"  (D comes from the 1st window). The wrfout before D are moved to wrf/{n['spin_up']}/.",
            ]
        ),
        "",
    ]
    lines += _steps(case, cluster, french=False, data_dir=context.data_dir)
    lines += [
        "",
        "USEFUL COMMANDS (from this folder)",
        *(
            ['- Jobs queued or running: squeue -u "$USER"']
            if cluster
            else [
                f"- Where the run is, where it stopped: tail -n 15 {n['run_log']}",
                "  (last line '> program...': the step running; 'ERROR:': the step that failed and",
                "  why; 'Done.': finished)",
                f"- Steps as they go: tail -f {n['run_log']}",
            ]
        ),
        "- Programs running: ps -ef | grep -E '(geogrid|ungrib|metgrid|real|wrf)[.]exe' | grep -v grep",
        "- Instant reached by WRF: grep 'Timing for main' wrf/rsl.error.0000 | tail -n 3",
        f"- Windows done: cat wrf/{n['logs']}/{n['state']}",
        "- WRF errors: grep -i -E 'error|fatal' wrf/rsl.error.0000",
        "- WPS errors: tail -n 20 wps/geogrid.log* wps/metgrid.log*",
        "",
        "WPS",
        "- One pass per calendar year, cut to the period, starting S hours before its start",
        "  (also on 1 January). The met_em of every year go to wps/met_em/.",
        "- ungrib for each source ("
        + ", ".join(s.prefix for s in context.sources)
        + ") then metgrid",
        "  with every fg_name; the last source prevails for a common field.",
        *(
            [
                f"- NetCDF sources ({', '.join(converted)}): converted by the application into",
                f"  wps/{n['intermediate']}/<source>/; the script links them without running ungrib.",
            ]
            if converted
            else []
        ),
        "- Each program must print 'Successful completion', otherwise the script stops.",
        "",
        "WRF",
        f"- namelist.input is ready for the first computed window ({first.simulation_start:%Y-%m-%d %H:%M} ->",
        f"  {first.simulation_end:%Y-%m-%d %H:%M}); the script rewrites the dates (start_*, end_*, run_*)",
        "  of each window. num_metgrid_levels is read in the met_em (ncdump).",
        "- real.exe and wrf.exe must write SUCCESS COMPLETE in rsl.error.0000, otherwise the",
        "  script stops without touching the outputs. The scripts return 0 on success.",
        "",
        "TIME SERIES (TSLIST)",
        "- After each wrf.exe, each file <prefix>.dNN.<VAR> is cut: the steps of ]useful start,",
        "  useful end] are kept, selected by step number (exact dt of each domain, WRF time =",
        "  n x dt since the start of the simulation); the numbers of lines are checked.",
        "- The time (2nd column of .TS, 1st of the profiles) becomes HOURS SINCE D; the header",
        "  line (the point) is kept once, with the date D instead of the start of the simulation.",
        f"- wrf/{n['tslist_blocks']}/: one file per block; wrf/{n['tslist_period']}/: the period ]D, F],",
        "  time strictly increasing, without gap or duplicate, number of lines checked.",
        f"- {n['cells']}: prefix, domain, grid cell (i, j), turbines and farms of each cell.",
        "  Several turbines of one cell give the same series: one series per cell.",
        "",
        "CONVENTIONS",
        "- Every date is in UTC.",
        "- wrfout: times of [D, F]; tslist series and means: ]D, F].",
        "- 10-minute means (made by the application at import): intervals ]t - 10 min, t],",
        "  stamped at the end t; each WRF value counts for the step that ends at it.",
        "- POWER (wrfout) is the power of every turbine of a grid cell.",
        "",
        "TIME STEPS (s)",
    ]
    for domain in context.domains:
        lines.append(
            f"- d{domain.number:02d}: {float(domain.step):g} s"
            f"{' (adaptive)' if context.adaptive else ''}; wrfout every {domain.history_seconds // 60} min."
        )
    lines += ["", "FILES", *[f"- {name}{_role(name)}" for name in files], ""]
    return "\n".join(lines)


def _roles() -> dict[str, str]:
    """What each exported file is for, one line each in the read-me file."""
    n = names()
    return {
        n["readme"]: tr(
            "this file: order of execution and conventions",
            "ce fichier : ordre d'execution et conventions",
        ),
        "manifest.json": tr(
            "description of the computation (period, windows, domains, time steps, series);"
            " the application reads it back at the import of the outputs",
            "description du calcul (periode, fenetres, domaines, pas de temps, series) ;"
            " le logiciel la relit a l'import des sorties",
        ),
        n["plan"]: tr(
            "list of the windows (block, order of computation, simulated and useful dates),"
            " readable in a spreadsheet; run_wrf.sh reads it: do not edit it",
            "liste des fenetres (bloc, ordre de calcul, dates simulees et utiles),"
            " lisible dans un tableur ; run_wrf.sh la lit : ne pas la modifier",
        ),
        "wps/namelist.wps": tr(
            "settings of WPS (domains, dates, paths)", "reglages de WPS (domaines, dates, chemins)"
        ),
        "wps/namelist.wps.sst": tr(
            "settings of WPS for the sea surface temperature",
            "reglages de WPS pour la temperature de surface de la mer",
        ),
        "wps/run_wps.sh": tr(
            "runs geogrid, then ungrib and metgrid year by year",
            "lance geogrid, puis ungrib et metgrid annee par annee",
        ),
        "wrf/namelist.input": tr(
            "settings of WRF for the first window; the script writes the dates of each window",
            "reglages de WRF de la premiere fenetre ; le script ecrit les dates de chaque fenetre",
        ),
        n["common"]: tr(
            "functions shared by every script (log, namelists, links), read by them",
            "fonctions communes a tous les scripts (journal, namelists, liens), lues par eux",
        ),
        "wrf/run_wrf.sh": tr(
            "runs real.exe then wrf.exe for every window of the plan, from the last to the first,"
            " cuts the series, assembles each block then the period; run again after a stop,"
            " it resumes at the next window",
            "lance real.exe puis wrf.exe pour chaque fenetre du plan, de la derniere a la"
            " premiere, decoupe les series, assemble chaque bloc puis la periode ; relance"
            " apres un arret, il reprend a la fenetre suivante",
        ),
        "wrf/tslist": tr(
            "points where WRF writes time series", "points ou WRF ecrit des series temporelles"
        ),
        f"wrf/{n['cells']}": tr(
            "turbines and farms of each grid cell of the time series",
            "eoliennes et parcs de chaque maille des series temporelles",
        ),
        f"{n['data']}/{n['download_gfs']}": tr(
            "downloads the GFS data of the project", "telecharge les donnees GFS du projet"
        ),
        f"{n['data']}/{n['download_era5']}": tr(
            "downloads the ERA5 data of the project", "telecharge les donnees ERA5 du projet"
        ),
    }


def _role(name: str) -> str:
    role = _roles().get(name)
    if role is None and name.startswith("wps/Vtable"):
        role = tr(
            "table of the GRIB fields for ungrib, linked as Vtable",
            "table de correspondance des champs GRIB pour ungrib, liee sous le nom Vtable",
        )
    if role is None and name.startswith("wrf/") and name.endswith((".txt", ".tbl", ".csv")):
        role = tr(
            "positions and models of the turbines for the wind farm scheme",
            "positions et modeles des eoliennes pour le schema de parc",
        )
    return tr(f": {role}", f" : {role}") if role else ""


def download_era5(case: Case, windows_plan: Plan, folder: str = "") -> str:
    from owstudio.core.case.model import Period

    period = Period(
        start=windows_plan.forcing_start,
        end=windows_plan.forcing_end,
        interval_seconds=case.period.interval_seconds,
    )
    requests = [
        {
            "dataset": r.dataset,
            "request": r.request,
            "target": f"era5/{r.request['year'][0]}/{r.name}",
        }
        for r in era5.requests_for(period, case.grid)
    ]
    body = json.dumps(requests, indent=1)
    if current() == "en":
        return (
            "#!/usr/bin/env python3\n"
            f'"""Downloads the ERA5 data of the project (Copernicus CDS) into {folder or "."}/era5/<year>/.\n\n'
            f"To be run from the {names()['data']}/ folder: python3 {names()['download_era5']}\n"
            "It needs the cdsapi module (pip install cdsapi), a Copernicus account, the key in\n"
            "~/.cdsapirc and the ERA5 licences accepted on the CDS website. Files already\n"
            'there are not downloaded again."""\n\n'
            "import json\nimport os\n\nimport cdsapi\n\n"
            f"DATA_DIR = {folder or '.'!r}  # shared folder of the input data ('.': this folder)\n"
            f"REQUESTS = json.loads(r'''{body}''')\n\n"
            "client = cdsapi.Client()\n"
            "for item in REQUESTS:\n"
            "    target = os.path.join(DATA_DIR, item['target'])\n"
            "    if os.path.exists(target):\n"
            "        continue\n"
            "    os.makedirs(os.path.dirname(target), exist_ok=True)\n"
            "    partial = target + '.part'\n"
            "    client.retrieve(item['dataset'], item['request'], partial)\n"
            "    os.replace(partial, target)\n"
            "print('ERA5 downloaded')\n"
        )
    return (
        "#!/usr/bin/env python3\n"
        f'"""Telecharge les donnees ERA5 du projet (Copernicus CDS) dans {folder or "."}/era5/<annee>/.\n\n'
        f"A lancer depuis le dossier {names()['data']}/ : python3 {names()['download_era5']}\n"
        "Il faut le module cdsapi (pip install cdsapi), un compte Copernicus, la cle dans\n"
        "~/.cdsapirc et les licences ERA5 acceptees sur le site du CDS. Les fichiers deja\n"
        'presents ne sont pas retelecharges."""\n\n'
        "import json\nimport os\n\nimport cdsapi\n\n"
        f"DOSSIER_DONNEES = {folder or '.'!r}  # dossier commun des donnees d'entree ('.' : ce dossier)\n"
        f"REQUETES = json.loads(r'''{body}''')\n\n"
        "client = cdsapi.Client()\n"
        "for item in REQUETES:\n"
        "    cible = os.path.join(DOSSIER_DONNEES, item['target'])\n"
        "    if os.path.exists(cible):\n"
        "        continue\n"
        "    os.makedirs(os.path.dirname(cible), exist_ok=True)\n"
        "    partiel = cible + '.part'\n"
        "    client.retrieve(item['dataset'], item['request'], partiel)\n"
        "    os.replace(partiel, cible)\n"
        "print('ERA5 telecharge')\n"
    )


def download_gfs(case: Case, windows_plan: Plan, folder: str = "") -> str:
    from owstudio.core.case.model import Period

    period = Period(
        start=windows_plan.forcing_start,
        end=windows_plan.forcing_end,
        interval_seconds=case.period.interval_seconds,
    )
    files = gfs.files_for(period)
    if current() == "en":
        return (
            "\n".join(
                [
                    "#!/bin/bash",
                    "# Downloads the GFS 0.25 deg analyses of the project (NOAA, open archive on AWS) into",
                    f"# DATA_DIR/gfs/<year>/. To be run from the {names()['data']}/ folder: bash {names()['download_gfs']}",
                    "# About 500 MB per time; files already there are not downloaded again.",
                    "set -eu",
                    f"DATA_DIR={scripts.quote_path(folder) if folder else '.'}\t# shared folder of the input data (.: this folder)",
                    "FILES=(",
                    *[f'"{f.name[4:8]} {f.url} {f.name}"' for f in files],
                    ")",
                    'for line in "${FILES[@]}"; do',
                    '\tread -r year address name <<< "$line"',
                    '\tmkdir -p "$DATA_DIR/gfs/$year"',
                    '\t[ -f "$DATA_DIR/gfs/$year/$name" ] && continue',
                    '\tcurl -fSL --retry 3 -o "$DATA_DIR/gfs/$year/$name.part" "$address"',
                    '\tmv "$DATA_DIR/gfs/$year/$name.part" "$DATA_DIR/gfs/$year/$name"',
                    "done",
                    'echo "GFS downloaded"',
                    "exit 0",
                ]
            )
            + "\n"
        )
    lines = [
        "#!/bin/bash",
        "# Telecharge les analyses GFS 0.25 deg du projet (NOAA, archive ouverte sur AWS) dans",
        f"# DOSSIER_DONNEES/gfs/<annee>/. A lancer depuis le dossier {names()['data']}/ : bash {names()['download_gfs']}",
        "# Environ 500 Mo par instant ; les fichiers deja presents ne sont pas retelecharges.",
        "set -eu",
        f"DOSSIER_DONNEES={scripts.quote_path(folder) if folder else '.'}\t# dossier commun des donnees d'entree (. : ce dossier)",
        "FICHIERS=(",
        *[f'"{f.name[4:8]} {f.url} {f.name}"' for f in files],
        ")",
        'for ligne in "${FICHIERS[@]}"; do',
        '\tread -r annee adresse nom <<< "$ligne"',
        '\tmkdir -p "$DOSSIER_DONNEES/gfs/$annee"',
        '\t[ -f "$DOSSIER_DONNEES/gfs/$annee/$nom" ] && continue',
        '\tcurl -fSL --retry 3 -o "$DOSSIER_DONNEES/gfs/$annee/$nom.part" "$adresse"',
        '\tmv "$DOSSIER_DONNEES/gfs/$annee/$nom.part" "$DOSSIER_DONNEES/gfs/$annee/$nom"',
        "done",
        'echo "GFS telecharge"',
        "exit 0",
    ]
    return "\n".join(lines) + "\n"


def manifest(case: Case, context: ScriptContext, files: list[str]) -> dict[str, Any]:
    p = context.plan
    points = tslist.locations(case)
    kinds = {"T": "turbine", "C": "cell"}
    return {
        "format": EXPORT_FORMAT,
        "format_version": EXPORT_VERSION,
        "application_version": context.version,
        "exported_at": _iso(context.generated),
        "project": case.name,
        "target": "cluster" if context.cluster else "local",
        "timezone": "UTC",
        "period": {"start": _iso(p.start), "end": _iso(p.end)},
        "spin_up_hours": p.spin_up_hours,
        "useful_hours": p.useful_hours,
        "grouping": p.grouping,
        "restart": p.restart,
        "boundary_interval_s": case.period.interval_seconds,
        "conventions": {
            "history": "[D, F]: every window keeps ]useful_start, useful_end], the first one also D",
            "time_series": "]D, F]",
            "time_series_time": "hours since D (period.start)",
            "time_series_header": "one header line per file, with the date D",
            "averages": "10 min, intervals ]t - 10 min, t] stamped at t; each WRF value counts for the step ending at it",
            "restart": p.restart,
            "frames_per_outfile": 1,
        },
        "adaptive_time_step": context.adaptive,
        "domains": [
            {
                "number": d.number,
                "time_step_s": [d.step.numerator, d.step.denominator],
                "history_interval_s": d.history_seconds,
                "constant_step": scripts.constant_step(context, d),
                "expected_series_lines": scripts.expected_lines(context, d),
            }
            for d in context.domains
        ],
        "blocks": [
            {
                "id": b.id,
                "start": _iso(b.start),
                "end": _iso(b.end),
                "windows": [w.id for w in b.windows],
            }
            for b in p.blocks
        ],
        "windows": [
            {
                "id": w.id,
                "order": w.order,
                "block": w.block,
                "simulation_start": _iso(w.simulation_start),
                "simulation_end": _iso(w.simulation_end),
                "useful_start": _iso(w.useful_start),
                "useful_end": _iso(w.useful_end),
                "restart": w.restart,
            }
            for w in p.windows
        ],
        "wps_passes": [
            {
                "year": wps.year,
                "start": _iso(wps.start),
                "end": _iso(wps.end),
                **(
                    {
                        "sst_start": _iso(context.sst_windows[wps.year][0]),
                        "sst_end": _iso(context.sst_windows[wps.year][1]),
                    }
                    if wps.year in context.sst_windows
                    else {}
                ),
            }
            for wps in p.wps_passes
        ],
        "sources": [{"prefix": s.prefix, "files": s.pattern} for s in context.sources],
        "time_series": {
            "mode": case.time_series.turbines if case.time_series else "none",
            "variables": list(scripts.TS_VARIABLES),
            "points": [
                {
                    "prefix": point.prefix,
                    "name": point.name,
                    "lat": point.lat,
                    "lon": point.lon,
                    "kind": kinds.get(point.prefix[0], "point")
                    if point.prefix[1:].isdigit()
                    else "point",
                }
                for point in points
            ],
        },
        "cells": [
            {
                "domain": cell.domain,
                "i": cell.i,
                "j": cell.j,
                "prefix": cell.prefix,
                "turbines": [
                    {"farm": t.farm, "label": t.label, "prefix": t.prefix, "simulated": t.simulated}
                    for t in cell.turbines
                ],
            }
            for cell in tslist.cells(case)
        ],
        "turbines": turbine_rows(case),
        "files": files,
    }


def export_files(
    case: Case, options: ExportOptions, now: datetime | None = None
) -> dict[str, tuple[str, bool]]:
    """Relative path -> (text, executable)."""
    if not case.grid.domains:
        raise ValueError(
            tr(
                "Add the domains before exporting the files.",
                "Ajoutez les domaines avant d'exporter les fichiers.",
            )
        )
    n = names()
    now = (now or datetime.now(UTC)).replace(tzinfo=None, microsecond=0)
    context = context_for(case, options, now)
    windows_plan = context.plan
    files: dict[str, tuple[str, bool]] = {}
    first = windows_plan.computation[0]
    window_case = child_case(case, first)
    paths = EnginePaths(
        geog_data=context.geog_dir.rstrip("/") + "/",
        geogrid_tables="./geogrid/",
        metgrid_tables="./metgrid/",
    )

    # WPS: dates of the first pass; the script rewrites them for each pass
    first_pass = windows_plan.wps_passes[0]
    wps_case = wps_pass_case(case, first_pass)
    # Rewritten by run_wps.sh for each year: the met_em folder of every pass
    wps_case.namelist_wps.setdefault("metgrid", {})["opt_output_from_metgrid_path"] = "./met_em/"
    nml = build_namelist_wps(wps_case, paths)
    files["wps/namelist.wps"] = (namelist_text(nml), False)
    if first_pass.year in context.sst_windows:
        sst_start, sst_end = context.sst_windows[first_pass.year]
        nml["share"]["start_date"] = [sst_start.strftime(WRF_DATE)] * case.max_dom
        nml["share"]["end_date"] = [sst_end.strftime(WRF_DATE)] * case.max_dom
        nml["ungrib"]["prefix"] = "SST"
        files["wps/namelist.wps.sst"] = (namelist_text(nml), False)
    for source, text in sources(case, options):
        if not source.converted:
            files[f"wps/{source.vtable_file}"] = (text, False)
    files["wps/run_wps.sh"] = (scripts.run_wps(context), True)

    # WRF: namelist of the first computed window
    files["wrf/namelist.input"] = (namelist_text(build_namelist_input(window_case)), False)
    if case.farm_scheme and turbine_rows(case):
        files[f"wrf/{LAYOUT_FILES[case.farm_scheme.scheme]}"] = (layout_text(case), False)
        rows = turbine_rows(case)
        table: list[list[object]] = [
            ["index", "farm", "farm_number", "turbine", "type", "lat", "lon"]
        ]
        table += [
            [
                r["index"],
                r["farm"],
                r["farm_number"],
                r["turbine"],
                r["type"],
                f"{r['lat']:.6f}",
                f"{r['lon']:.6f}",
            ]
            for r in rows
        ]
        files["wrf/turbines.csv"] = (_csv(table), False)
        used = {r["type"] for r in rows}
        for number, turbine in sorted(case.turbine_types.items()):
            if number in used:
                files[f"wrf/wind-turbine-{number}.tbl"] = (turbine_table(turbine), False)
    points = tslist.locations(case)
    if points:
        files["wrf/tslist"] = (tslist.tslist_text(points), False)
    iofields = iofields_text(case)
    if iofields:
        files[f"wrf/{IOFIELDS_FILE}"] = (iofields, False)
    if case.farm_scheme or case.farms:
        files[f"wrf/{n['cells']}"] = (cells_csv(case), False)

    files["wrf/run_wrf.sh"] = (scripts.run_wrf(context), True)

    if case.input_source == "era5":
        files[f"{n['data']}/{n['download_era5']}"] = (
            download_era5(case, windows_plan, context.data_dir),
            True,
        )
    elif case.input_source == "gfs":
        files[f"{n['data']}/{n['download_gfs']}"] = (
            download_gfs(case, windows_plan, context.data_dir),
            True,
        )

    files[n["plan"]] = (plan_csv(context), False)
    files[n["common"]] = (scripts.common(context), True)
    listed = sorted([*files, n["readme"], "manifest.json"])
    files["manifest.json"] = (
        json.dumps(manifest(case, context, listed), indent=2, ensure_ascii=True) + "\n",
        False,
    )
    files[n["readme"]] = (readme(case, context, listed), False)
    # ASCII with LF line ends, whatever the system exporting
    return {
        path: (ascii(text.replace("\r\n", "\n").replace("\r", "\n")), executable)
        for path, (text, executable) in files.items()
    }


def validate_export(case: Case) -> None:
    """Fatal method conditions must hold before producing an executable package.

    Preview stays available to inspect and correct invalid settings. A non-dividing model
    step remains a warning: changing it is a stability choice left to the user.
    """
    from owstudio.core.case.checks import _check_method

    errors = [issue for issue in _check_method(case) if issue.severity == "error"]
    if errors:
        raise ValueError("\n".join(issue.message for issue in errors))


def export_zip(
    case: Case, options: ExportOptions, now: datetime | None = None
) -> tuple[str, bytes]:
    """File name and content of the ZIP; scripts keep their execution permission."""
    validate_export(case)
    import tempfile

    files = export_files(case, options, now)
    root = f"{safe_name(case.name)}-WRF"
    buffer = io.BytesIO()

    def entry(path: str, executable: bool) -> zipfile.ZipInfo:
        info = zipfile.ZipInfo(f"{root}/{path}", date_time=(2026, 1, 1, 0, 0, 0))
        info.create_system = 3  # Unix: the permissions below are honoured by unzip
        info.external_attr = ((EXECUTABLE if executable else 0o644) | 0o100000) << 16
        info.compress_type = zipfile.ZIP_DEFLATED
        return info

    with (
        zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive,
        tempfile.TemporaryDirectory(prefix="ows-netcdf-") as scratch,
    ):
        for path in sorted(files):
            text, executable = files[path]
            archive.writestr(entry(path, executable), text.encode("ascii"))
        wps = Path(scratch) / "wps"
        for converted in convert_inputs(case, wps):
            relative = "wps/" + converted.relative_to(wps).as_posix()
            archive.writestr(entry(relative, False), converted.read_bytes())
    return f"{root}.zip", buffer.getvalue()


def write_folder(
    case: Case, options: ExportOptions, target: Any, now: datetime | None = None
) -> list[str]:
    """Writes the files under ``target`` (a Path), with LF line ends and execution rights."""
    import os

    validate_export(case)
    folder = Path(target)
    files = export_files(case, options, now)
    for path, (text, executable) in files.items():
        destination = folder / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(text.encode("ascii"))
        if executable and os.name != "nt":
            destination.chmod(EXECUTABLE)
    converted = convert_inputs(case, folder / "wps")
    return sorted([*files, *(p.relative_to(folder).as_posix() for p in converted)])
