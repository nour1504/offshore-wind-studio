"""Consistency checks run before a case is submitted.

Errors describe configurations WRF cannot run or that the schemes do not support.
Warnings describe configurations that run but are likely to give poor results.
"""

import calendar
import math
from dataclasses import dataclass, replace
from datetime import datetime
from fractions import Fraction
from typing import Literal

from owstudio.core import tslist
from owstudio.core.case.model import Case
from owstudio.core.data import era5, examine, gfs, vtables
from owstudio.core.domains import EARTH_RADIUS_M, cell_of
from owstudio.core.i18n import tr
from owstudio.core.namelist.validate import check_namelists, domain_option
from owstudio.core.windfarm.catalog import BETZ_LIMIT, power_coefficients

MYNN_PBL = 5
# Turbine tables shipped in WRF's run directory
WRF_BUILT_IN_TYPES = {1}
WRF_BUILT_IN_ROTOR_M = {1: 85.0}
SCHEME_NAMES = {"fitch": "Fitch", "mav": "MAV"}
# WRF's README.windturbine advises against grid spacings finer than 5 rotor diameters
MIN_ROTOR_DIAMETERS_PER_CELL = 5
# Turbines closer than this, in rotor diameters, shadow each other far more than usual layouts
MIN_SPACING_ROTOR_DIAMETERS = 3
# Beyond this, a constant sea surface temperature drifts away from reality
SST_UPDATE_ADVISED_DAYS = 5
# The checks read at most this much of GRIB files not examined yet
QUICK_EXAMINE_BYTES = 1_000_000_000


@dataclass(frozen=True)
class Issue:
    severity: Literal["error", "warning", "info"]
    # In the language of the interface (core/i18n.py)
    message: str
    # The field it is about (as the interface names it, e.g. "windows.useful_hours"), and the
    # reason in a few words, shown next to that field
    field: str | None = None
    short: str | None = None
    # The page of the project it belongs to: data, domains, turbines, farms, physics, outputs
    page: str | None = None


def _on(page: str, issues: list[Issue]) -> list[Issue]:
    return [issue if issue.page else replace(issue, page=page) for issue in issues]


def check_case(case: Case) -> list[Issue]:
    """Every check. What a project being prepared simply has not got yet (no domain, a farm
    without turbines) is reported as something to do ("info"); own GRIB files are examined
    within a reading budget (QUICK_EXAMINE_BYTES)."""
    todo = _check_unfinished(case)
    if not case.grid.domains:
        return todo
    method = [
        replace(issue, page="outputs") if issue.field == "history_interval_minutes" else issue
        for issue in _check_method(case)
    ]
    return todo + (
        _on("data", _check_input_data(case))
        + _on("data", _check_sea_surface(case))
        + _on("farms", _check_farms(case))
        + _on("turbines", _check_turbine_types(case))
        + _on("farms", _check_farm_scheme(case))
        + _on("farms", _check_layout(case))
        + _on("physics", [Issue(f.severity, f.message) for f in check_namelists(case)])
        + _on("data", method)
        + _on("domains", _check_vertical(case))
        + _on("domains", _check_static_data(case))
        + _on("outputs", _check_time_series(case))
    )


def _check_unfinished(case: Case) -> list[Issue]:
    issues = []
    if not case.grid.domains:
        issues.append(
            Issue(
                "info",
                tr(
                    "To do: place the area to simulate in Domains.",
                    "À faire : placez la zone à simuler dans Domaines.",
                ),
                page="domains",
            )
        )
    for farm in case.farms:
        if not farm.turbines:
            issues.append(
                Issue(
                    "info",
                    tr(
                        f"To do: add turbines to the farm {farm.name}, or delete it.",
                        f"À faire : ajoutez des éoliennes au parc {farm.name}, ou supprimez-le.",
                    ),
                    page="farms",
                )
            )
    return issues


def _epoch(time: datetime) -> int:
    return calendar.timegm(time.timetuple())


def _check_method(case: Case) -> list[Issue]:
    """Conditions of the window method (core/method/plan.py) that must hold for exact results:
    chained windows start on a boundary data time, all windows write their history files
    at the same instants (so that a later-computed window replaces the spin-up files of the one
    after it), one file per instant, and no restart file unless the windows are chained."""
    from owstudio.core.method import plan as method
    from owstudio.core.method import timesteps

    try:
        plan = method.plan(case)
        history = timesteps.history_seconds(case)
        frames = timesteps.frames_per_outfile(case)
        steps = timesteps.time_steps(case) if case.max_dom else None
    except (ValueError, OverflowError, TypeError) as error:
        return [Issue("error", tr(f"Period: {error}", f"Période : {error}"), "period", str(error))]
    issues = []
    data = case.period.interval_seconds
    # real.exe works between data times: a cold start begins at the data time before its
    # spin-up and prepares up to the one after its end, so any length is possible. A window
    # chained by a restart file begins at its own start, which must then be a data time.
    ends = [(w, w.simulation_start) for w in plan.windows if w.restart]
    for window, time in ends:
        if _epoch(time) % data:
            issues.append(
                Issue(
                    "error",
                    tr(
                        f"Chained window {window.index} starts at {time:%Y-%m-%d %H:%M} UTC, between two boundary data times (every {data / 3600:g} h): real.exe starts there. Choose windows ending on those times, or independent windows.",
                        f"La fenêtre enchaînée {window.index} commence le {time:%d/%m/%Y %H:%M} UTC, entre deux instants des données aux frontières (toutes les {data / 3600:g} h) : real.exe part de là. Choisissez des fenêtres qui finissent sur ces instants, ou des fenêtres indépendantes.",
                    ),
                    "windows.useful_hours",
                    tr(
                        f"Off the data times (every {data / 3600:g} h)",
                        f"Hors des instants des données (toutes les {data / 3600:g} h)",
                    ),
                )
            )
            break
    for number, seconds in enumerate(history, 1):
        offsets = [(w.simulation_start - plan.start).total_seconds() for w in plan.windows]
        offsets.append((plan.end - plan.start).total_seconds())
        if seconds <= 0 or any(offset % seconds for offset in offsets):
            issues.append(
                Issue(
                    "error",
                    tr(
                        f"Domain {number}: history every {seconds / 60:g} min does not divide the spin-up, the windows and the period. The windows would not write their files at the same times and could not replace each other's spin-up files.",
                        f"Domaine {number} : des sorties toutes les {seconds / 60:g} min ne divisent pas la mise en route, les fenêtres et la période. Les fenêtres n'écriraient pas leurs fichiers aux mêmes instants et ne pourraient pas remplacer ceux de la mise en route.",
                    ),
                    "history_interval_minutes",
                    tr(
                        "Must divide the spin-up and the windows",
                        "Doit diviser la mise en route et les fenêtres",
                    ),
                )
            )
        if (
            steps
            and not steps.adaptive
            and seconds > 0
            and Fraction(seconds) % steps.steps[number - 1]
        ):
            issues.append(
                Issue(
                    "warning",
                    tr(
                        f"Domain {number}: the time step ({steps.text(number)} s) does not divide the history interval ({seconds / 60:g} min). WRF writes each history file at the first step reaching its time, so the files would not be at exact times.",
                        f"Domaine {number} : le pas de temps ({steps.text(number)} s) ne divise pas l'intervalle des sorties ({seconds / 60:g} min). WRF écrit chaque sortie au premier pas qui atteint son heure : les fichiers ne seraient pas à l'heure exacte.",
                    ),
                    "history_interval_minutes",
                    tr(
                        f"Not a multiple of the d0{number} time step ({steps.text(number)} s)",
                        f"Pas un multiple du pas de temps de d0{number} ({steps.text(number)} s)",
                    ),
                )
            )
    if any(value != 1 for value in frames):
        issues.append(
            Issue(
                "error",
                tr(
                    "frames_per_outfile must be 1: one history file per time, so that each window replaces the spin-up files of the next one by name.",
                    "frames_per_outfile doit valoir 1 : un fichier de sortie par instant, pour que chaque fenêtre remplace par leur nom les fichiers de mise en route de la suivante.",
                ),
            )
        )
    restart = timesteps.restart_seconds(case)
    longest = max(w.simulated_seconds for w in plan.windows)
    # With restart the scripts set restart_interval to the length of each window
    if not plan.restart and 0 < restart <= longest:
        issues.append(
            Issue(
                "error",
                tr(
                    f"restart_interval ({restart / 60:g} min) must exceed the longest window ({longest // 60} min): the method writes no restart file.",
                    f"restart_interval ({restart / 60:g} min) doit dépasser la plus longue fenêtre ({longest // 60} min) : la méthode n'écrit aucun fichier de reprise.",
                ),
            )
        )
    return issues


# Resolution keywords of geogrid's GEOGRID.TBL.ARW in WPS 4.7 (rel_path = <keyword>:...)
GEOG_KEYWORDS_WPS47 = frozenset(
    [
        "default",
        "lowres",
        "30s",
        "2m",
        "5m",
        "10m",
        "20m",
        "30m",
        "1deg",
        "2deg",
        "gmted2010_30s",
        "gtopo_30s",
        "gtopo_2m",
        "gtopo_5m",
        "gtopo_10m",
        "usgs_30s",
        "usgs_2m",
        "usgs_5m",
        "usgs_10m",
        "usgs_lakes",
        "modis_15s",
        "modis_15s_lake",
        "modis_30s",
        "modis_30s_lake",
        "modis_lakes",
        "modis_2010",
        "modis_2010_lake",
        "modis_2050",
        "modis_2050_lake",
        "modis_lai",
        "modis_fpar",
        "modis_veg_no_search",
        "nlcd2006",
        "nlcd2006_9s",
        "nlcd2006_30s",
        "nlcd2011_9s",
        "bnu_soil_30s",
        "ssib_5m",
        "ssib_10m",
        "cgls_veg",
        "nesdis_greenfrac",
        "albedo_ncep",
        "albedo_modis",
        "maxsnowalb_ncep",
        "maxsnowalb_modis",
        "y2010_urb",
        "y2050_urb",
        "y2010_ahe",
        "y2050_ahe",
    ]
)


def _check_static_data(case: Case) -> list[Issue]:
    """geog_data_res of each domain: required, and made of GEOGRID.TBL keywords joined by +."""
    issues = []
    for index, domain in enumerate(case.grid.domains):
        field = f"grid.domains.{index}.geog_data_res"
        name = f"d{index + 1:02d}"
        value = domain.geog_data_res.strip()
        if not value:
            issues.append(
                Issue(
                    "error",
                    tr(
                        f"{name}: static data resolution required.",
                        f"{name} : résolution des données statiques requise.",
                    ),
                    field,
                    tr("Required", "Requis"),
                )
            )
            continue
        unknown = [part for part in value.split("+") if part not in GEOG_KEYWORDS_WPS47]
        if unknown:
            issues.append(
                Issue(
                    "warning",
                    tr(
                        f"{name}: {', '.join(unknown)} unknown to GEOGRID.TBL of WPS 4.7.",
                        f"{name} : {', '.join(unknown)} inconnu de GEOGRID.TBL de WPS 4.7.",
                    ),
                    field,
                    tr("Unknown to WPS 4.7", "Inconnu de WPS 4.7"),
                )
            )
    return issues


def _check_vertical(case: Case) -> list[Issue]:
    """The vertical levels as real.exe computes them: its refusals become errors."""
    from owstudio.core.method import vertical

    if not case.max_dom:
        return []
    try:
        vertical.profile(case)
    except vertical.VerticalError as error:
        return [Issue("error", tr(f"Vertical levels: {error}.", f"Niveaux verticaux : {error}."))]
    except (ValueError, ZeroDivisionError, OverflowError) as error:
        return [Issue("error", tr(f"Vertical levels: {error}.", f"Niveaux verticaux : {error}."))]
    return []


def _check_time_series(case: Case) -> list[Issue]:
    if (
        case.time_series
        and case.time_series.turbines == "each"
        and sum(len(farm.turbines) for farm in case.farms) > 9999
    ):
        return [
            Issue(
                "error",
                tr(
                    "Time series: one-per-turbine output supports at most 9999 generated TNNNN locations (WRF prefixes have five characters). Use one per grid cell, or reduce the locations.",
                    "Séries temporelles : une série par éolienne permet au plus 9999 points TNNNN générés (les préfixes de WRF ont cinq caractères). Choisissez une série par maille, ou réduisez les points.",
                ),
            )
        ]
    try:
        points = tslist.locations(case)
    except (ValueError, ArithmeticError, NotImplementedError) as error:
        return [
            Issue(
                "error",
                tr(
                    f"Time series locations cannot be generated: {error}",
                    f"Les points des séries temporelles ne peuvent pas être générés : {error}",
                ),
            )
        ]
    issues = []
    duplicates = tslist.duplicate_prefixes(points)
    if duplicates:
        issues.append(
            Issue(
                "error",
                tr(
                    f"Time series: prefixes must be unique (output file names); repeated: "
                    f"{', '.join(sorted(set(duplicates)))}.",
                    f"Séries temporelles : les préfixes doivent être uniques (noms des fichiers de sortie) ; répétés : {', '.join(sorted(set(duplicates)))}.",
                ),
            )
        )
    try:
        outside = [
            p.name
            for p in points
            if all(cell_of(case.grid, n, p.lat, p.lon) is None for n in range(1, case.max_dom + 1))
        ]
    except NotImplementedError:
        outside = []
    if outside:
        issues.append(
            Issue(
                "warning",
                tr(
                    f"Time series: {len(outside)} location(s) outside every domain will be ignored "
                    f"by WRF ({', '.join(outside[:3])}{'…' if len(outside) > 3 else ''}).",
                    f"Séries temporelles : {len(outside)} point(s) hors de tous les domaines seront ignorés par WRF ({', '.join(outside[:3])}{'…' if len(outside) > 3 else ''}).",
                ),
            )
        )
    if case.time_series and case.time_series.turbines == "each":
        try:
            shared = [cell for cell in tslist.cells(case) if len(cell.turbines) > 1]
        except (ValueError, NotImplementedError):
            shared = []
        if shared:
            turbines = sum(len(cell.turbines) for cell in shared)
            issues.append(
                Issue(
                    "warning",
                    tr(
                        f"Time series one per turbine: {turbines} turbines share {len(shared)} grid "
                        "cells with others. WRF writes the same series for the turbines of a cell; "
                        "results show one series per cell.",
                        f"Séries une par éolienne : {turbines} éoliennes partagent {len(shared)} "
                        "mailles avec d'autres. WRF écrit la même série pour les éoliennes d'une "
                        "maille ; les résultats montrent une série par maille.",
                    ),
                )
            )
    return issues


def _check_own_files(case: Case, role: examine.Role) -> list[Issue]:
    """The user's files: folder, format, table, and what ungrib (or the NetCDF conversion) will
    find in them (fields, levels, times, area), as examine.py checks it."""
    settings = examine.own_files(case, role)
    assert settings is not None
    report = examine.examine(
        settings, role, examine.context_of(case), budget_bytes=QUICK_EXAMINE_BYTES
    )
    field = "grib.folder" if role == "atmosphere" else "sea_surface.grib.folder"
    return [Issue(f.severity, f.message, field) for f in report.findings]


def _check_input_data(case: Case) -> list[Issue]:
    """Whether the chosen source covers the period at the chosen interval."""
    from owstudio.core.engine.windows import forcing_case, plan_windows

    if case.input_source == "grib":
        assert case.grib is not None
        if not case.grib.folder.strip():
            return [
                Issue(
                    "error",
                    tr(
                        "Input data: choose the folder of your weather files.",
                        "Données d'entrée : choisissez le dossier de vos fichiers météo.",
                    ),
                    "grib.folder",
                    tr("Folder to choose", "Dossier à choisir"),
                )
            ]
        return _check_own_files(case, "atmosphere")
    try:
        forcing = forcing_case(case)
    except (ValueError, OverflowError) as error:
        return [Issue("error", tr(f"Input data: {error}", f"Données d'entrée : {error}"))]
    if case.input_source == "era5":
        problem = era5.availability_error(forcing.period)
        if problem is None:
            try:
                era5.times_for(forcing.period)
            except ValueError as error:
                problem = str(error)
    else:
        try:
            gfs.files_for(forcing.period)
            problem = None
            # Every independent real.exe starts from its own forcing cycle; checking only
            # the first expanded period would miss e.g. a 73 h useful-window cadence.
            for window in plan_windows(case):
                start = window.simulation_start
                if start.hour % gfs.CYCLE_HOURS or start.minute or start.second:
                    problem = tr(
                        f"Independent window {window.number} starts at {start:%Y-%m-%d %H:%M:%S} UTC. "
                        "GFS analyses start at 00, 06, 12 or 18 UTC; choose useful and spin-up hours "
                        "that align every window with those cycles, or use ERA5/your own files.",
                        f"La fenêtre {window.number} commence le {start:%d/%m/%Y %H:%M:%S} UTC. Les "
                        "analyses GFS commencent à 00, 06, 12 ou 18 UTC ; choisissez des durées de mise "
                        "en route et de fenêtre utile qui alignent chaque fenêtre sur ces cycles, ou "
                        "utilisez ERA5 ou vos propres fichiers.",
                    )
                    break
        except ValueError as error:
            problem = str(error)
    return (
        [
            Issue(
                "error",
                tr(f"Input data: {problem}", f"Données d'entrée : {problem}"),
                "input_source",
                problem,
            )
        ]
        if problem
        else []
    )


def _check_sea_surface(case: Case) -> list[Issue]:
    sea = case.sea_surface
    issues = []
    if sea.source == "grib":
        assert sea.grib is not None
        if not sea.grib.folder.strip():
            return [
                Issue(
                    "error",
                    tr(
                        "SST files: choose the folder of your sea temperature files.",
                        "Fichiers SST : choisissez le dossier de vos fichiers de température de la mer.",
                    ),
                    "sea_surface.grib.folder",
                    tr("Folder to choose", "Dossier à choisir"),
                )
            ]
        issues += _check_own_files(case, "sst")
        table = (
            sea.grib.custom_vtable
            if sea.grib.vtable == "custom"
            else (vtables.read(sea.grib.vtable) if sea.grib.vtable in vtables.names() else "")
        )
        if table and "SST" not in vtables.fields(table):
            issues.append(
                Issue(
                    "error",
                    tr(
                        "SST files: the Vtable does not produce the field SST (use Vtable.SST or add an SST row).",
                        "Fichiers SST : la Vtable ne produit pas le champ SST (utilisez Vtable.SST ou ajoutez une ligne SST).",
                    ),
                )
            )
    # Each window is a separate simulation: the longest one decides
    try:
        from owstudio.core.method.plan import plan

        days = max(w.simulated_seconds for w in plan(case).windows) / 86400
    except ValueError:
        days = 0.0
    if not sea.update and days > SST_UPDATE_ADVISED_DAYS:
        issues.append(
            Issue(
                "warning",
                tr(
                    f"A window lasts {days:.1f} days without SST update: WRF keeps its initial sea surface "
                    "temperature all along. Enable the SST update.",
                    f"Une fenêtre dure {days:.1f} jours sans mise à jour de la SST : WRF garde la température "
                    "de mer du départ tout du long. Activez la mise à jour de la SST.",
                ),
            )
        )
    if sea.update:
        boundary_minutes = case.period.interval_seconds // 60
        if sea.update_interval_minutes and sea.update_interval_minutes != boundary_minutes:
            issues.append(
                Issue(
                    "warning",
                    tr(
                        f"SST updates every {sea.update_interval_minutes} min while the boundary data come every "
                        f"{boundary_minutes} min: real.exe writes wrflowinp at the boundary times, so the "
                        "intervals should match (README.namelist).",
                        f"La SST est mise à jour toutes les {sea.update_interval_minutes} min alors que les données aux frontières arrivent toutes les {boundary_minutes} min : real.exe écrit wrflowinp aux instants des frontières, les intervalles devraient donc être égaux (README.namelist).",
                    ),
                    "sea_surface.update_interval_minutes",
                    tr(
                        f"Boundary data every {boundary_minutes} min",
                        f"Données aux frontières toutes les {boundary_minutes} min",
                    ),
                )
            )
        if str(case.physics.get("usemonalb", "")).lower() not in ("true", ".true.", "1"):
            issues.append(
                Issue(
                    "warning",
                    tr(
                        "With the SST update, README.namelist recommends usemonalb = .true. (monthly albedo) in Physics.",
                        "Avec la mise à jour de la SST, README.namelist recommande usemonalb = .true. (albédo mensuel) dans Physique.",
                    ),
                )
            )
    return issues


def _check_farms(case: Case) -> list[Issue]:
    issues = []
    if case.farm_scheme and not case.active_turbines():
        issues.append(
            Issue(
                "warning",
                tr(
                    "A wind farm scheme is selected but no farm is enabled: WRF runs without turbines.",
                    "Un schéma de parc est choisi mais aucun parc n'est activé : WRF tourne sans éoliennes.",
                ),
            )
        )
    if case.farms and not case.farm_scheme:
        issues.append(
            Issue(
                "warning",
                tr(
                    "Farms are defined but no wind farm scheme is selected: WRF ignores the turbines.",
                    "Des parcs existent mais aucun schéma de parc n'est choisi : WRF ignore les éoliennes.",
                ),
            )
        )
    for farm in case.farms:
        labels = [t.id for t in farm.turbines if t.id]
        repeated = sorted({label for label in labels if labels.count(label) > 1})
        if repeated:
            issues.append(
                Issue(
                    "error",
                    tr(
                        f"Farm {farm.id}: turbine labels must be unique ({', '.join(repeated)}).",
                        f"Parc {farm.id} : les noms des éoliennes doivent être uniques ({', '.join(repeated)}).",
                    ),
                )
            )
    raw_labels = [
        t.id or f"{farm.id}-{index}"
        for farm in case.farms
        for index, t in enumerate(farm.turbines, 1)
    ]
    if len(set(raw_labels)) != len(raw_labels):
        issues.append(
            Issue(
                "info",
                tr(
                    "Repeated turbine labels are qualified by their farm in energy results. "
                    "Generated tslist prefixes remain unique; truncated display names are not used for lookup.",
                    "Les noms d'éoliennes répétés sont précisés par leur parc dans les résultats d'énergie. Les préfixes tslist générés restent uniques ; les noms affichés tronqués ne servent pas à la recherche.",
                ),
            )
        )
    return issues


def _rotor_diameter(case: Case, turbine_type: int) -> float | None:
    if turbine_type in case.turbine_types:
        return case.turbine_types[turbine_type].rotor_diameter_m
    return WRF_BUILT_IN_ROTOR_M.get(turbine_type)


def _check_layout(case: Case) -> list[Issue]:
    active = case.active_turbines()
    if not active or case.farm_scheme is None:
        return []
    issues = []
    domains = case.farm_scheme.domains
    try:
        outside = sum(
            1
            for _, t in active
            if all(cell_of(case.grid, number, t.lat, t.lon) is None for number in domains)
        )
    except NotImplementedError:
        outside = 0
    if outside:
        names = ", ".join(f"d0{n}" for n in domains)
        issues.append(
            Issue(
                "error",
                tr(
                    f"{outside} turbine(s) lie outside {names}, where the wind farm scheme runs; "
                    "move the turbines or the nests.",
                    f"{outside} éolienne(s) hors de {names}, où tourne le schéma de parc ; déplacez les éoliennes ou les domaines imbriqués.",
                ),
            )
        )

    # Nearest neighbour of each turbine, in rotor diameters of the larger of the two rotors,
    # across farms: neighbouring farms closer than a few diameters interact like one farm
    turbines = [t for _, t in active]
    lat0 = math.radians(sum(t.lat for t in turbines) / len(turbines))
    points = [
        (
            EARTH_RADIUS_M * math.radians(t.lon) * math.cos(lat0),
            EARTH_RADIUS_M * math.radians(t.lat),
        )
        for t in turbines
    ]
    diameters = [_rotor_diameter(case, t.type) for t in turbines]
    too_close, closest = 0, math.inf
    for i, (xi, yi) in enumerate(points):
        nearest = math.inf
        for j, (xj, yj) in enumerate(points):
            di, dj = diameters[i], diameters[j]
            if i != j and di and dj:
                nearest = min(nearest, math.hypot(xi - xj, yi - yj) / max(di, dj))
        if nearest < MIN_SPACING_ROTOR_DIAMETERS:
            too_close += 1
            closest = min(closest, nearest)
    if too_close:
        issues.append(
            Issue(
                "warning",
                tr(
                    f"{too_close} turbine(s) are closer than {MIN_SPACING_ROTOR_DIAMETERS} rotor "
                    f"diameters to a neighbour (closest {closest:.1f} D); offshore farms are usually "
                    "spaced 6 to 10 D.",
                    f"{too_close} éolienne(s) à moins de {MIN_SPACING_ROTOR_DIAMETERS} diamètres de rotor d'une voisine (la plus proche à {closest:.1f} D) ; en mer, les éoliennes sont en général espacées de 6 à 10 D.",
                ),
            )
        )
    return issues


def _check_turbine_types(case: Case) -> list[Issue]:
    issues = []
    used = sorted({t.type for farm in case.farms for t in farm.turbines})
    for number in used:
        if number not in case.turbine_types and number not in WRF_BUILT_IN_TYPES:
            issues.append(
                Issue(
                    "error",
                    tr(
                        f"Turbine type {number} is used by a farm but not defined; add it in the Turbines tab.",
                        f"Le modèle d'éolienne {number} est utilisé par un parc mais n'est pas défini ; ajoutez-le dans Modèles d'éoliennes.",
                    ),
                )
            )
    for number, turbine in sorted(case.turbine_types.items()):
        label = tr(
            f"Turbine type {number} ({turbine.name or 'unnamed'})",
            f"Le modèle d'éolienne {number} ({turbine.name or 'sans nom'})",
        )
        max_cp = max(power_coefficients(turbine))
        if max_cp > BETZ_LIMIT:
            issues.append(
                Issue(
                    "warning",
                    tr(
                        f"{label}: the power curve implies Cp = {max_cp:.2f}, above the Betz limit "
                        f"({BETZ_LIMIT:.3f}); check the units (kW) and the rotor diameter.",
                        f"{label} : la courbe de puissance donne Cp = {max_cp:.2f}, au-dessus de la limite de Betz ({BETZ_LIMIT:.3f}) ; vérifiez les unités (kW) et le diamètre du rotor.",
                    ),
                )
            )
        if max(p.power_kw for p in turbine.curve) > 1.05 * turbine.rated_power_mw * 1000:
            issues.append(
                Issue(
                    "warning",
                    tr(
                        f"{label}: the power curve exceeds the rated power.",
                        f"{label} : la courbe de puissance dépasse la puissance nominale.",
                    ),
                )
            )
        if number not in used:
            issues.append(
                Issue(
                    "warning",
                    tr(
                        f"{label} is defined but no turbine uses it.",
                        f"{label} est défini mais aucune éolienne ne l'utilise.",
                    ),
                )
            )
    return issues


def _check_farm_scheme(case: Case) -> list[Issue]:
    scheme = case.farm_scheme
    active = case.active_turbines()
    if scheme is None or not active:
        return []
    issues = []
    name = SCHEME_NAMES[scheme.scheme]
    spacing = case.grid.domain_dx()
    rotors = [d for d in (_rotor_diameter(case, t.type) for _, t in active) if d]
    for number in scheme.domains:
        try:
            pbl = domain_option(case, "physics", "bl_pbl_physics", number)
            tkeadvect = domain_option(case, "physics", "bl_mynn_tkeadvect", number)
        except (ValueError, TypeError, KeyError, ArithmeticError, NotImplementedError):
            continue  # final namelist validation reports the generation problem
        if pbl != MYNN_PBL:
            issues.append(
                Issue(
                    "error",
                    tr(
                        f"Domain {number}: the {name} wind farm scheme requires the MYNN "
                        f"boundary layer (bl_pbl_physics = {MYNN_PBL}), found {pbl}.",
                        f"Domaine {number} : le schéma de parc {name} demande la couche limite MYNN (bl_pbl_physics = {MYNN_PBL}), trouvé {pbl}.",
                    ),
                )
            )
        if not tkeadvect:
            issues.append(
                Issue(
                    "warning",
                    tr(
                        f"Domain {number}: bl_mynn_tkeadvect is off, so turbulence produced by the "
                        "turbines is not carried downstream.",
                        f"Domaine {number} : bl_mynn_tkeadvect est désactivé, la turbulence produite par les éoliennes n'est donc pas transportée en aval.",
                    ),
                )
            )
        if rotors:
            limit = MIN_ROTOR_DIAMETERS_PER_CELL * max(rotors)
            if spacing[number - 1] < limit:
                issues.append(
                    Issue(
                        "warning",
                        tr(
                            f"Domain {number}: grid spacing {spacing[number - 1]:.0f} m is finer than "
                            f"{MIN_ROTOR_DIAMETERS_PER_CELL} rotor diameters ({limit:.0f} m); the wind "
                            "farm parameterization is not recommended at this resolution.",
                            f"Domaine {number} : la maille de {spacing[number - 1]:.0f} m est plus fine que {MIN_ROTOR_DIAMETERS_PER_CELL} diamètres de rotor ({limit:.0f} m) ; le schéma de parc n'est pas recommandé à cette résolution.",
                        ),
                    )
                )
    if scheme.scheme == "mav" and not scheme.induction:
        issues.append(
            Issue(
                "warning",
                tr(
                    "The induction correction only applies to the Fitch scheme; it is ignored with MAV.",
                    "La correction d'induction ne s'applique qu'au schéma Fitch ; elle est ignorée avec MAV.",
                ),
            )
        )
    if scheme.scheme == "mav" and scheme.wake_model == 3 and scheme.overlap_method != 4:
        issues.append(
            Issue(
                "warning",
                tr(
                    "The GM wake model does not use a superposition method; the chosen method is ignored.",
                    "Le modèle de sillage GM n'utilise pas de méthode de superposition ; la méthode choisie est ignorée.",
                ),
            )
        )
    if scheme.scheme == "fitch" and (scheme.wake_model != 2 or scheme.overlap_method != 4):
        issues.append(
            Issue(
                "warning",
                tr(
                    "Wake models and superposition methods belong to the MAV scheme; Fitch ignores them.",
                    "Les modèles de sillage et les méthodes de superposition appartiennent au schéma MAV ; Fitch les ignore.",
                ),
            )
        )
    return issues
