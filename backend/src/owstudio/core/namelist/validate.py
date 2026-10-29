"""Validate final WRF/WPS settings while keeping advanced and indexed overrides available.

Registry types/dimensions are read from the bundled WRF 4.8 schema. Compatibility rules below
are explicit checks from WRF 4.8, not a claim to cover every physics interaction or guarantee
numerical stability. Sparse f90nml arrays and _start_index metadata retain their semantics.

Primary references:
https://raw.githubusercontent.com/wrf-model/WRF/v4.8.0/share/module_check_a_mundo.F
https://raw.githubusercontent.com/wrf-model/WRF/v4.8.0/run/README.namelist
https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/running_wrf.html
https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html
"""

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import cache
from importlib import resources
from itertools import pairwise
from typing import Any, Literal

from owstudio.core.case.model import Case
from owstudio.core.domains import (
    LambertConformal,
    Mercator,
    domain_outlines,
    projection_for,
)
from owstudio.core.i18n import tr
from owstudio.core.namelist.generate import build_namelist_input, build_namelist_wps


@dataclass(frozen=True)
class Finding:
    severity: Literal["error", "warning", "info"]
    message: str


@cache
def schema() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(
        (resources.files("owstudio.data") / "namelist_schema_4.8.0.json").read_text(
            encoding="utf-8"
        )
    )
    return loaded


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _leaves(value: Any) -> list[Any]:
    return (
        [leaf for item in value for leaf in _leaves(item)] if isinstance(value, list) else [value]
    )


def _typed(value: Any, kind: str) -> bool:
    if value is None:
        return True  # an unassigned Fortran array element, not the text 'null'
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind in ("real", "doubleprecision", "double precision"):
        return _number(value)
    if kind == "logical":
        return isinstance(value, bool)
    if kind == "character":
        return isinstance(value, str)
    return True


def _domain(
    values: dict[str, Any], group: str, option: str, number: int, default: Any = None
) -> Any:
    """Actual Fortran columns: a scalar assigns d01; subsequent columns retain their default."""
    options = values.get(group, {})
    value = options.get(option)
    indices = options.get("_start_index", {}).get(option, [1])
    start = (
        indices[0] if isinstance(indices, list) and indices and isinstance(indices[0], int) else 1
    )
    if isinstance(value, list):
        result = value[number - start] if 0 <= number - start < len(value) else None
    else:
        result = value if number == start else None
    if result is None:
        return schema()["groups"].get(group, {}).get(option, {}).get("default", default)
    return result


def _scalar(values: dict[str, Any], group: str, option: str, default: Any = None) -> Any:
    value = values.get(group, {}).get(option)
    if isinstance(value, list):
        value = value[0] if value else None
    return (
        schema()["groups"].get(group, {}).get(option, {}).get("default", default)
        if value is None
        else value
    )


def final_input(case: Case) -> dict[str, Any]:
    result = {}
    for group, options in build_namelist_input(case).items():
        result[group] = dict(options)
        if options.start_index:
            result[group]["_start_index"] = dict(options.start_index)
    return result


def domain_option(case: Case, group: str, option: str, number: int) -> Any:
    return _domain(final_input(case), group, option, number)


# WPS has no Registry. Only these documented types are asserted; other WPS options remain
# available with a coverage warning, rather than being mistaken for invalid names.
WPS_TYPES: dict[str, dict[str, tuple[str, bool]]] = {
    "share": {
        "wrf_core": ("character", False),
        "max_dom": ("integer", False),
        "start_date": ("character", True),
        "end_date": ("character", True),
        "interval_seconds": ("integer", False),
        "io_form_geogrid": ("integer", False),
        "opt_output_from_geogrid_path": ("character", False),
        "debug_level": ("integer", False),
    },
    "geogrid": {
        **{
            name: ("integer", True)
            for name in (
                "parent_id",
                "parent_grid_ratio",
                "i_parent_start",
                "j_parent_start",
                "e_we",
                "e_sn",
                "s_we",
                "s_sn",
            )
        },
        "geog_data_res": ("character", True),
        **{
            name: ("real", False)
            for name in (
                "dx",
                "dy",
                "ref_lat",
                "ref_lon",
                "ref_x",
                "ref_y",
                "truelat1",
                "truelat2",
                "stand_lon",
                "pole_lat",
                "pole_lon",
            )
        },
        **{
            name: ("character", False)
            for name in ("map_proj", "geog_data_path", "opt_geogrid_tbl_path")
        },
    },
    "ungrib": {"out_format": ("character", False), "prefix": ("character", False)},
    "metgrid": {
        "fg_name": ("character", True),
        "constants_name": ("character", True),
        "opt_metgrid_tbl_path": ("character", False),
        "io_form_metgrid": ("integer", False),
        "opt_output_from_metgrid_path": ("character", False),
        "process_only_bdy": ("integer", True),
        "active_grid": ("logical", True),
    },
}


def _type_checks(case: Case, wrf: dict[str, Any], wps: dict[str, Any]) -> list[Finding]:
    findings = []
    for filename, groups, overrides in (
        ("namelist.input", wrf, case.namelist_input),
        ("namelist.wps", wps, case.namelist_wps),
    ):
        for group, options in groups.items():
            specs = (
                schema()["groups"].get(group, {})
                if filename == "namelist.input"
                else WPS_TYPES.get(group, {})
            )
            for name, value in options.items():
                label = f"{filename} &{group}.{name}"
                if name == "_start_index":
                    if not isinstance(value, dict) or any(
                        not isinstance(indices, list)
                        or any(
                            not isinstance(index, int) or isinstance(index, bool)
                            for index in indices
                        )
                        for indices in value.values()
                    ):
                        findings.append(
                            Finding(
                                "error",
                                tr(
                                    f"{label}: invalid indexed-array metadata; retain integer Fortran start indices.",
                                    f"{label} : indices de tableau invalides ; gardez des indices de départ Fortran entiers.",
                                ),
                            )
                        )
                    continue
                spec: Any = specs.get(name)
                if spec is None:
                    # Known application-generated groups without a WPS catalogue are not noisy.
                    if name in overrides.get(group, {}):
                        findings.append(
                            Finding(
                                "warning",
                                tr(
                                    f"{label}: not described by the bundled {schema()['wrf_version'] if filename == 'namelist.input' else 'WPS'} schema. It is kept; verify the name, type and build support in the engine documentation.",
                                    f"{label} : absent du schéma {schema()['wrf_version'] if filename == 'namelist.input' else 'WPS'} livré avec le logiciel. L'option est gardée ; vérifiez son nom, son type et sa prise en charge dans la documentation du moteur.",
                                ),
                            )
                        )
                    elif filename == "namelist.input" and (
                        name in case.physics
                        if group == "physics"
                        else name in case.dynamics
                        if group == "dynamics"
                        else False
                    ):
                        findings.append(
                            Finding(
                                "warning",
                                tr(
                                    f"{label}: unknown advanced option is kept; verify it against your engine's Registry.",
                                    f"{label} : option avancée inconnue, gardée ; vérifiez-la dans le Registry de votre moteur.",
                                ),
                            )
                        )
                    continue
                if filename == "namelist.input":
                    kind, per_domain, dimension = (
                        spec["type"],
                        spec["per_domain"],
                        spec["dimension"],
                    )
                else:
                    kind, per_domain = spec
                    dimension = "list" if per_domain else "1"
                if isinstance(value, dict) or any(
                    not _typed(item, kind) for item in _leaves(value)
                ):
                    findings.append(
                        Finding(
                            "error",
                            tr(
                                f"{label}: expected {kind} values (finite numbers; logical values are true/false), found {value!r}.",
                                f"{label} : valeurs de type {kind} attendues (nombres finis ; valeurs logiques true/false), trouvé {value!r}.",
                            ),
                        )
                    )
                    continue
                if dimension == "1" and isinstance(value, list) and len(value) > 1:
                    findings.append(
                        Finding(
                            "error",
                            tr(
                                f"{label}: a scalar is required; a {len(value)}-element list would not fit this Registry dimension.",
                                f"{label} : une seule valeur est attendue ; une liste de {len(value)} éléments ne correspond pas à cette dimension du Registry.",
                            ),
                        )
                    )
                supplied_by_user = (
                    name in overrides.get(group, {})
                    or (group == "physics" and name in case.physics)
                    or (group == "dynamics" and name in case.dynamics)
                )
                if (
                    filename == "namelist.input"
                    and per_domain
                    and case.max_dom > 1
                    and supplied_by_user
                ):
                    supplied = len(value) if isinstance(value, list) else 1
                    if supplied < case.max_dom:
                        findings.append(
                            Finding(
                                "warning",
                                tr(
                                    f"{label}: only {supplied} column(s) for {case.max_dom} domains; unassigned columns use WRF defaults, not a repetition of d01.",
                                    f"{label} : seulement {supplied} colonne(s) pour {case.max_dom} domaines ; les colonnes manquantes prennent les valeurs par défaut de WRF, pas celle de d01.",
                                ),
                            )
                        )
                    elif supplied > case.max_dom:
                        findings.append(
                            Finding(
                                "info",
                                tr(
                                    f"{label}: only the first {case.max_dom} domain columns are active; extra columns are retained.",
                                    f"{label} : seules les {case.max_dom} premières colonnes de domaines sont actives ; les colonnes en trop sont gardées.",
                                ),
                            )
                        )
    return findings


def _physics_checks(case: Case, wrf: dict[str, Any]) -> list[Finding]:
    findings = []
    scheme = case.farm_scheme
    active = bool(scheme and case.active_turbines())
    for number in range(1, case.max_dom + 1):
        expected = (
            (1 if scheme.scheme == "fitch" else 2)
            if active and scheme and number in scheme.domains
            else 0
        )
        if _domain(wrf, "physics", "windfarm_opt", number, 0) != expected:
            findings.append(
                Finding(
                    "error",
                    tr(
                        f"Domain {number}: windfarm_opt must match the project's wind farm scheme and selected domains. Change Wind farms so turbine files and energy methods match the simulated scheme.",
                        f"Domaine {number} : windfarm_opt doit correspondre au schéma de parc du projet et aux domaines choisis. Modifiez Parcs éoliens pour que les fichiers des éoliennes et les méthodes d'énergie correspondent au schéma simulé.",
                    ),
                )
            )
    if active and scheme:
        expected_ij = 2 if scheme.scheme == "mav" else 0
        if _scalar(wrf, "physics", "windfarm_ij", expected_ij) != expected_ij:
            findings.append(
                Finding(
                    "error",
                    tr(
                        f"This application's turbine files use windfarm_ij = {expected_ij} for {scheme.scheme}; a raw override needs a compatible file workflow which is not currently supported.",
                        f"Les fichiers d'éoliennes du logiciel utilisent windfarm_ij = {expected_ij} pour {scheme.scheme} ; une autre valeur demanderait un format de fichiers compatible, non pris en charge aujourd'hui.",
                    ),
                )
            )
        if scheme.scheme == "fitch" and _scalar(wrf, "physics", "windfarm_induction", 1) != int(
            scheme.induction
        ):
            findings.append(
                Finding(
                    "error",
                    tr(
                        "windfarm_induction must match the Wind farms setting so per-turbine energy reconstruction uses the same formula as WRF.",
                        "windfarm_induction doit correspondre au réglage de Parcs éoliens pour que la reconstitution de l'énergie par éolienne utilise la même formule que WRF.",
                    ),
                )
            )

    def domain_values(option: str) -> list[Any]:
        return [_domain(wrf, "physics", option, n) for n in range(1, case.max_dom + 1)]

    for name in ("sf_surface_physics", "sf_sfclay_physics"):
        values = domain_values(name)
        if all(_number(value) and value >= 0 for value in values) and len(set(values)) > 1:
            findings.append(
                Finding(
                    "error",
                    tr(
                        f"{name} must be the same on all domains (WRF 4.8 module_check_a_mundo); final values are {values}.",
                        f"{name} doit être le même sur tous les domaines (WRF 4.8 module_check_a_mundo) ; valeurs finales : {values}.",
                    ),
                )
            )
    for name in ("mp_physics", "sf_urban_physics"):
        values = domain_values(name)
        if all(_number(value) and value >= 0 for value in values) and len(set(values)) > 1:
            findings.append(
                Finding(
                    "warning",
                    tr(
                        f"WRF resets differing {name} values to the innermost-domain value {values[-1]}; choose a consistent setting to avoid a misleading study.",
                        f"WRF remplace les valeurs différentes de {name} par celle du domaine le plus fin, {values[-1]} ; choisissez un réglage cohérent pour ne pas fausser l'étude.",
                    ),
                )
            )
    edmf = [
        _domain(wrf, "physics", "bl_mynn_edmf", n)
        if _domain(wrf, "physics", "bl_pbl_physics", n) == 5
        else 0
        for n in range(1, case.max_dom + 1)
    ]
    shallow = domain_values("shcu_physics")
    if any(_number(value) and value > 0 for value in edmf) and (
        any(_number(value) and value > 0 for value in shallow)
        or _scalar(wrf, "physics", "ishallow", 0) not in (None, 0)
    ):
        findings.append(
            Finding(
                "error",
                tr(
                    "MYNN bl_mynn_edmf > 0 requires shcu_physics = 0 and ishallow = 0; MYNN mass flux is enabled by default (WRF 4.8).",
                    "MYNN avec bl_mynn_edmf > 0 demande shcu_physics = 0 et ishallow = 0 ; le flux de masse de MYNN est actif par défaut (WRF 4.8).",
                ),
            )
        )
    dfi = _scalar(wrf, "dfi_control", "dfi_opt", 0)
    for number in range(1, case.max_dom + 1):
        pbl = _domain(wrf, "physics", "bl_pbl_physics", number)
        surface = _domain(wrf, "physics", "sf_sfclay_physics", number)
        land = _domain(wrf, "physics", "sf_surface_physics", number)
        km = _domain(wrf, "dynamics", "km_opt", number)
        if (
            (pbl == 10) != (surface == 10)
            and pbl is not None
            and surface is not None
            and pbl != -1
            and surface != -1
        ):
            findings.append(
                Finding(
                    "error",
                    tr(
                        f"Domain {number}: TEMF requires both bl_pbl_physics = 10 and sf_sfclay_physics = 10.",
                        f"Domaine {number} : TEMF demande à la fois bl_pbl_physics = 10 et sf_sfclay_physics = 10.",
                    ),
                )
            )
        if km == 5 and surface not in (0, 1, 5, 91):
            findings.append(
                Finding(
                    "error",
                    tr(
                        f"Domain {number}: SMS-3DTKE km_opt = 5 supports sf_sfclay_physics 0, 1, 5 or 91 only.",
                        f"Domaine {number} : SMS-3DTKE (km_opt = 5) n'accepte que sf_sfclay_physics 0, 1, 5 ou 91.",
                    ),
                )
            )
        if _domain(wrf, "physics", "shalwater_z0", number) not in (None, 0) and surface != 1:
            findings.append(
                Finding(
                    "error",
                    tr(
                        f"Domain {number}: shalwater_z0 requires revised MM5 sf_sfclay_physics = 1.",
                        f"Domaine {number} : shalwater_z0 demande la couche de surface MM5 révisée (sf_sfclay_physics = 1).",
                    ),
                )
            )
        if _scalar(wrf, "physics", "isftcflx", 0) in (1, 2) and surface != 1:
            findings.append(
                Finding(
                    "error",
                    tr(
                        f"Domain {number}: high-wind ocean isftcflx = 1 or 2 requires sf_sfclay_physics = 1.",
                        f"Domaine {number} : isftcflx = 1 ou 2 (océan par vent fort) demande sf_sfclay_physics = 1.",
                    ),
                )
            )
        if _scalar(wrf, "physics", "fractional_seaice", 0) == 1 and land == 1:
            findings.append(
                Finding(
                    "error",
                    tr(
                        f"Domain {number}: fractional_seaice = 1 cannot use the simple slab land model sf_surface_physics = 1.",
                        f"Domaine {number} : fractional_seaice = 1 ne peut pas utiliser le modèle de sol simple sf_surface_physics = 1.",
                    ),
                )
            )
        if _scalar(wrf, "physics", "seaice_albedo_opt", 0) == 1 and land not in (2, 4):
            findings.append(
                Finding(
                    "error",
                    tr(
                        f"Domain {number}: seaice_albedo_opt = 1 supports Noah (2) or Noah-MP (4) land surface only.",
                        f"Domaine {number} : seaice_albedo_opt = 1 n'accepte que les modèles de sol Noah (2) ou Noah-MP (4).",
                    ),
                )
            )
        if dfi not in (None, 0) and pbl == 10:
            findings.append(
                Finding(
                    "error",
                    tr(
                        f"Domain {number}: digital filtering (dfi_opt) is not available with TEMF bl_pbl_physics = 10.",
                        f"Domaine {number} : le filtrage numérique (dfi_opt) n'est pas disponible avec TEMF (bl_pbl_physics = 10).",
                    ),
                )
            )
    if _scalar(wrf, "physics", "sst_update", 0) == 1 and any(
        _domain(wrf, "physics", "sf_ocean_physics", n) not in (None, 0)
        for n in range(1, case.max_dom + 1)
    ):
        findings.append(
            Finding(
                "error",
                tr(
                    "sst_update cannot be combined with sf_ocean_physics; choose prescribed SST updates or an ocean scheme.",
                    "sst_update ne se combine pas avec sf_ocean_physics ; choisissez des mises à jour de la SST imposées ou un schéma d'océan.",
                ),
            )
        )
    if dfi not in (None, 0):
        if any(
            _domain(wrf, "fdda", option, n) not in (None, 0, False)
            for option in ("grid_fdda", "grid_sfdda", "obs_nudge_opt")
            for n in range(1, case.max_dom + 1)
        ):
            findings.append(
                Finding(
                    "error",
                    tr(
                        "Digital filter initialization cannot be combined with nudging options (WRF running guide).",
                        "L'initialisation par filtre numérique ne se combine pas avec le rappel (nudging) (guide d'utilisation de WRF).",
                    ),
                )
            )
        if _scalar(wrf, "time_control", "multi_bdy_files", False) is True:
            findings.append(
                Finding(
                    "error",
                    tr(
                        "Digital filter initialization cannot use multi_bdy_files = true.",
                        "L'initialisation par filtre numérique ne peut pas utiliser multi_bdy_files = true.",
                    ),
                )
            )
    return findings


def check_time_steps(case: Case, wrf: dict[str, Any] | None = None) -> list[Finding]:
    wrf = wrf if wrf is not None else final_input(case)
    findings = []
    adaptive = _scalar(wrf, "domains", "use_adaptive_time_step", False) is True
    if adaptive:
        driver = _scalar(wrf, "domains", "adaptation_domain", 1)
        if not isinstance(driver, int) or not 1 <= driver <= case.max_dom:
            findings.append(
                Finding(
                    "error",
                    tr(
                        "adaptation_domain must identify an existing domain.",
                        "adaptation_domain doit désigner un domaine existant.",
                    ),
                )
            )
        for n in range(1, case.max_dom + 1):
            low, high = (
                _domain(wrf, "domains", name, n, -1) for name in ("min_time_step", "max_time_step")
            )
            if _number(low) and _number(high) and low >= 0 and high >= 0 and low > high:
                findings.append(
                    Finding(
                        "error",
                        tr(
                            f"Domain {n}: min_time_step cannot exceed max_time_step.",
                            f"Domaine {n} : min_time_step ne peut pas dépasser max_time_step.",
                        ),
                    )
                )
            for name in ("target_cfl", "target_hcfl"):
                value = _domain(wrf, "domains", name, n)
                if _number(value) and value <= 0:
                    findings.append(
                        Finding(
                            "error",
                            tr(
                                f"Domain {n}: adaptive {name} must be positive.",
                                f"Domaine {n} : {name} (pas adaptatif) doit être positif.",
                            ),
                        )
                    )
        # Static time_step is ignored with adaptive stepping; 8*dx is the documented default
        # adaptive maximum, not a violation of the usual static 6*dx recommendation.
        return findings
    base, numerator, denominator = (
        _scalar(wrf, "domains", name)
        for name in ("time_step", "time_step_fract_num", "time_step_fract_den")
    )
    if not all(_number(value) for value in (base, numerator, denominator)):
        return findings  # schema type checks explain invalid fields without arithmetic exceptions
    if denominator <= 0:
        return [
            Finding(
                "error",
                tr(
                    "time_step_fract_den must be positive; it is the fractional time-step denominator.",
                    "time_step_fract_den doit être positif ; c'est le dénominateur de la partie fractionnaire du pas de temps.",
                ),
            )
        ]
    dt = base + numerator / denominator
    if dt <= 0:
        return [
            Finding(
                "error",
                tr(
                    "The effective time step time_step + time_step_fract_num/time_step_fract_den must be positive.",
                    "Le pas de temps effectif time_step + time_step_fract_num/time_step_fract_den doit être positif.",
                ),
            )
        ]
    steps = []
    unstable = []
    for n in range(1, case.max_dom + 1):
        parent = _domain(wrf, "domains", "parent_id", n)
        ratio = _domain(wrf, "domains", "parent_time_step_ratio", n)
        if n == 1:
            steps.append(dt)
        elif not isinstance(parent, int) or not 1 <= parent < n or not _number(ratio) or ratio <= 0:
            findings.append(
                Finding(
                    "error",
                    tr(
                        f"Domain {n}: parent_time_step_ratio must be positive and parent_id must refer to an earlier domain.",
                        f"Domaine {n} : parent_time_step_ratio doit être positif et parent_id doit désigner un domaine précédent.",
                    ),
                )
            )
            steps.append(None)
        else:
            ancestor = steps[parent - 1]
            steps.append(ancestor / ratio if ancestor is not None else None)
        dx = _domain(wrf, "domains", "dx", n)
        dy = _domain(wrf, "domains", "dy", n)
        if steps[-1] is not None and all(_number(value) and value > 0 for value in (dx, dy)):
            limit = 6 * min(dx, dy) / 1000
            if steps[-1] > limit:
                unstable.append(f"d{n:02d}: {steps[-1]:g} s versus {limit:g} s")
    if unstable:
        findings.append(
            Finding(
                "warning",
                tr(
                    f"Effective time steps exceed the usual 6 s/km grid-spacing recommendation ({'; '.join(unstable)}). This is not a guarantee of CFL stability; WRF's reasonable_time_step_ratio guard may also reject them.",
                    f"Des pas de temps effectifs dépassent la recommandation habituelle de 6 s par km de maille ({'; '.join(unstable)}). Ce n'est pas une garantie de stabilité CFL ; le garde-fou reasonable_time_step_ratio de WRF peut aussi les refuser.",
                ),
            )
        )
    # Larger projection scale factors reduce the physical grid length and hence the stability
    # margin. This diagnostic is independent of wind/terrain, not an actual computed CFL.
    try:
        projection = projection_for(case.grid.projection)
        rings = domain_outlines(case.grid, points_per_edge=4)
        factors = []
        for ring in rings:
            if isinstance(projection, LambertConformal):
                lats = [math.radians(projection.hemi * lat) for _, lat in ring]
                factors.append(
                    max(
                        abs(
                            projection.n
                            * projection.f
                            / (math.cos(lat) * math.tan(math.pi / 4 + lat / 2) ** projection.n)
                        )
                        for lat in lats
                    )
                )
            elif isinstance(projection, Mercator):
                factors.append(
                    max(
                        abs(projection.scale / (6_370_000 * math.cos(math.radians(lat))))
                        for _, lat in ring
                    )
                )
        for n, factor in enumerate(factors, 1):
            if factor > 1.1:
                findings.append(
                    Finding(
                        "warning",
                        tr(
                            f"Domain {n}: sampled map scale reaches {factor:.3f}; physical grid spacing is smaller than dx/dy, so a shorter time step may be needed. Actual CFL requires model winds and vertical-grid information.",
                            f"Domaine {n} : le facteur d'échelle de la carte atteint {factor:.3f} ; la maille réelle est plus petite que dx/dy, un pas de temps plus court peut être nécessaire. Le vrai CFL dépend des vents du modèle et de la grille verticale.",
                        ),
                    )
                )
    except (NotImplementedError, ArithmeticError, ValueError):
        pass
    return findings


def _geometry_checks(case: Case, wrf: dict[str, Any], wps: dict[str, Any]) -> list[Finding]:
    findings = []
    wn, pn = _scalar(wrf, "domains", "max_dom"), wps.get("share", {}).get("max_dom")
    if wn != pn:
        findings.append(
            Finding(
                "error",
                tr(
                    "WPS share.max_dom and WRF domains.max_dom must agree.",
                    "share.max_dom de WPS et domains.max_dom de WRF doivent être égaux.",
                ),
            )
        )
    if wn != case.max_dom or pn != case.max_dom:
        findings.append(
            Finding(
                "error",
                tr(
                    f"Raw max_dom must match the project's {case.max_dom} domains; add/remove domains in Domains or import a matching namelist.",
                    f"max_dom brut doit correspondre aux {case.max_dom} domaines du projet ; ajoutez ou retirez des domaines dans Domaines, ou importez une namelist correspondante.",
                ),
            )
        )
    for n in range(1, case.max_dom + 1):
        for option in (
            "e_we",
            "e_sn",
            "parent_grid_ratio",
            "i_parent_start",
            "j_parent_start",
            *(["parent_id"] if n > 1 else []),
        ):
            raw = wps.get("geogrid", {}).get(option)
            pv = raw[n - 1] if isinstance(raw, list) and n <= len(raw) else raw if n == 1 else None
            wv = _domain(wrf, "domains", option, n)
            if pv is None:
                findings.append(
                    Finding(
                        "error",
                        tr(
                            f"WPS geogrid.{option} needs a value for domain {n}.",
                            f"geogrid.{option} de WPS demande une valeur pour le domaine {n}.",
                        ),
                    )
                )
            elif _number(pv) and _number(wv) and pv != wv:
                findings.append(
                    Finding(
                        "error",
                        tr(
                            f"Domain {n}: WPS and WRF {option} differ ({pv} versus {wv}).",
                            f"Domaine {n} : {option} diffère entre WPS et WRF ({pv} contre {wv}).",
                        ),
                    )
                )
        for option in ("dx", "dy"):
            value = _domain(wrf, "domains", option, n)
            if _number(value) and value <= 0:
                findings.append(
                    Finding(
                        "error",
                        tr(
                            f"Domain {n}: {option} must be positive.",
                            f"Domaine {n} : {option} doit être positif.",
                        ),
                    )
                )
        if n > 1:
            parent = _domain(wrf, "domains", "parent_id", n)
            ratio = _domain(wrf, "domains", "parent_grid_ratio", n)
            if (
                not isinstance(parent, int)
                or not 1 <= parent < n
                or not isinstance(ratio, int)
                or ratio <= 0
            ):
                findings.append(
                    Finding(
                        "error",
                        tr(
                            f"Domain {n}: nesting requires an earlier parent and a positive integer grid ratio.",
                            f"Domaine {n} : l'imbrication demande un parent précédent et un rapport de maille entier positif.",
                        ),
                    )
                )
                continue
            for size, start in (("e_we", "i_parent_start"), ("e_sn", "j_parent_start")):
                points, first, parent_points = (
                    _domain(wrf, "domains", option, domain)
                    for option, domain in ((size, n), (start, n), (size, parent))
                )
                if all(
                    isinstance(value, int) and not isinstance(value, bool)
                    for value in (points, first, parent_points)
                ):
                    if (points - 1) % ratio:
                        findings.append(
                            Finding(
                                "error",
                                tr(
                                    f"Domain {n}: ({size} - 1) must be divisible by parent_grid_ratio.",
                                    f"Domaine {n} : ({size} - 1) doit être divisible par parent_grid_ratio.",
                                ),
                            )
                        )
                    if first < 1 or first + (points - 1) / ratio >= parent_points:
                        findings.append(
                            Finding(
                                "error",
                                tr(
                                    f"Domain {n}: {size}/{start} extends beyond its parent.",
                                    f"Domaine {n} : {size}/{start} dépasse de son parent.",
                                ),
                            )
                        )
            if ratio % 2 == 0:
                findings.append(
                    Finding(
                        "warning",
                        tr(
                            f"Domain {n}: real-data nesting recommends odd grid ratios 3 or 5; even feedback ratios require special care (WRF running guide).",
                            f"Domaine {n} : l'imbrication sur données réelles recommande un rapport de maille impair, 3 ou 5 ; un rapport pair avec rétroaction demande des précautions (guide d'utilisation de WRF).",
                        ),
                    )
                )
            for option in ("dx", "dy"):
                coarse, fine = (_domain(wrf, "domains", option, domain) for domain in (parent, n))
                if (
                    _number(coarse)
                    and _number(fine)
                    and not math.isclose(fine * ratio, coarse, rel_tol=1e-5)
                ):
                    findings.append(
                        Finding(
                            "error",
                            tr(
                                f"Domain {n}: {option} must equal its parent's {option}/parent_grid_ratio.",
                                f"Domaine {n} : {option} doit valoir {option} du parent divisé par parent_grid_ratio.",
                            ),
                        )
                    )
    vertical = [_domain(wrf, "domains", "e_vert", n) for n in range(1, case.max_dom + 1)]
    if any(_number(value) and value <= 2 for value in vertical):
        findings.append(
            Finding(
                "error",
                tr(
                    "e_vert needs more than two full vertical levels.",
                    "e_vert demande plus de deux niveaux verticaux complets.",
                ),
            )
        )
    if (
        all(_number(value) for value in vertical)
        and len(set(vertical)) > 1
        and _scalar(wrf, "domains", "rebalance", 0) != 1
    ):
        findings.append(
            Finding(
                "error",
                tr(
                    "Different e_vert across domains requires explicit concurrent vertical refinement with rebalance = 1; ordinary nesting uses equal vertical levels.",
                    "Des e_vert différents selon les domaines demandent un raffinement vertical explicite avec rebalance = 1 ; l'imbrication ordinaire utilise les mêmes niveaux verticaux.",
                ),
            )
        )
    top = _scalar(wrf, "domains", "p_top_requested")
    if _number(top) and top <= 0:
        findings.append(
            Finding(
                "error",
                tr(
                    "p_top_requested must be positive (Pa).",
                    "p_top_requested doit être positif (Pa).",
                ),
            )
        )
    if _number(top) and top != case.grid.p_top_requested:
        findings.append(
            Finding(
                "warning",
                tr(
                    "p_top_requested overrides the graphical model top; input-pressure coverage checks use the project value. Align the Vertical grid setting before launching.",
                    "p_top_requested remplace le sommet du modèle réglé dans l'interface ; les contrôles de couverture des données en pression utilisent la valeur du projet. Alignez le réglage de la grille verticale avant de lancer.",
                ),
            )
        )
    eta = wrf.get("domains", {}).get("eta_levels")
    if isinstance(eta, list) and len(eta) > 1 and all(_number(value) for value in eta):
        if (
            not math.isclose(eta[0], 1.0)
            or not math.isclose(eta[-1], 0.0)
            or any(a <= b for a, b in pairwise(eta))
        ):
            findings.append(
                Finding(
                    "error",
                    tr(
                        "Explicit eta_levels must decrease strictly from 1 at the surface to 0 at the model top.",
                        "Les eta_levels explicites doivent décroître strictement de 1 à la surface à 0 au sommet du modèle.",
                    ),
                )
            )
        if vertical and len(eta) != vertical[0]:
            findings.append(
                Finding(
                    "error",
                    tr(
                        "The number of explicit eta_levels must match e_vert on the outer domain.",
                        "Le nombre d'eta_levels explicites doit être égal à e_vert du domaine extérieur.",
                    ),
                )
            )
    return findings


def _dates(wrf: dict[str, Any], case: Case, which: str, n: int) -> datetime | None:
    values = [
        _domain(wrf, "time_control", f"{which}_{key}", n, 0)
        for key in ("year", "month", "day", "hour", "minute", "second")
    ]
    if not all(isinstance(value, int) and not isinstance(value, bool) for value in values):
        return None
    try:
        return datetime(
            values[0], values[1], values[2], values[3], values[4], values[5], tzinfo=UTC
        )
    except ValueError:
        return None


def _period_checks(case: Case, wrf: dict[str, Any], wps: dict[str, Any]) -> list[Finding]:
    findings = []
    wi, pi = (
        _scalar(wrf, "time_control", "interval_seconds"),
        wps.get("share", {}).get("interval_seconds"),
    )
    if wi != pi:
        findings.append(
            Finding(
                "error",
                tr(
                    "WPS and WRF interval_seconds must agree for the same meteorological input sequence.",
                    "interval_seconds de WPS et de WRF doivent être égaux pour la même suite de données météo.",
                ),
            )
        )
    if _number(wi) and wi <= 0:
        findings.append(
            Finding(
                "error",
                tr("interval_seconds must be positive.", "interval_seconds doit être positif."),
            )
        )
    if wi != case.period.interval_seconds:
        findings.append(
            Finding(
                "warning",
                tr(
                    "Raw interval_seconds differs from the input-data preparation interval; align Period and input data before launching.",
                    "interval_seconds brut diffère de l'intervalle de préparation des données d'entrée ; alignez Période et données d'entrée avant de lancer.",
                ),
            )
        )
    for n in range(1, case.max_dom + 1):
        start, end = (_dates(wrf, case, which, n) for which in ("start", "end"))
        if start is None or end is None:
            findings.append(
                Finding(
                    "error",
                    tr(
                        f"Domain {n}: WRF start/end date fields must form valid UTC dates.",
                        f"Domaine {n} : les champs de dates de début et de fin de WRF doivent former des dates UTC valides.",
                    ),
                )
            )
            continue
        duration = [
            _scalar(wrf, "time_control", f"run_{unit}", 0)
            for unit in ("days", "hours", "minutes", "seconds")
        ]
        if all(_number(value) for value in duration):
            seconds = sum(value * scale for value, scale in zip(duration, (86400, 3600, 60, 1)))
            if seconds < 0:
                findings.append(
                    Finding(
                        "error",
                        tr(
                            "run_days/hours/minutes/seconds cannot give a negative duration.",
                            "run_days/hours/minutes/seconds ne peuvent pas donner une durée négative.",
                        ),
                    )
                )
            try:
                effective_end = start + timedelta(seconds=seconds) if seconds > 0 else end
            except (OverflowError, ValueError):
                findings.append(
                    Finding(
                        "error",
                        tr(
                            "The requested run duration exceeds the application's supported UTC calendar range.",
                            "La durée demandée dépasse la plage de dates UTC prise en charge par le logiciel.",
                        ),
                    )
                )
                continue
        else:
            effective_end = end
        if effective_end <= start:
            findings.append(
                Finding(
                    "error",
                    tr(
                        f"Domain {n}: WRF must end after it starts.",
                        f"Domaine {n} : WRF doit finir après avoir commencé.",
                    ),
                )
            )
        for which, wrf_time in (("start", start), ("end", max(end, effective_end))):
            raw = wps.get("share", {}).get(f"{which}_date")
            value = (
                raw[n - 1] if isinstance(raw, list) and n <= len(raw) else raw if n == 1 else None
            )
            try:
                wps_time = datetime.fromisoformat(str(value).replace("_", "T")).replace(tzinfo=UTC)
            except ValueError:
                findings.append(
                    Finding(
                        "error",
                        tr(
                            f"Domain {n}: WPS {which}_date must be a valid date/time.",
                            f"Domaine {n} : {which}_date de WPS doit être une date et une heure valides.",
                        ),
                    )
                )
                continue
            if (which == "start" and wps_time > wrf_time) or (
                which == "end" and wps_time < wrf_time
            ):
                findings.append(
                    Finding(
                        "error",
                        tr(
                            f"Domain {n}: WPS dates must cover the WRF initial/boundary-data period.",
                            f"Domaine {n} : les dates de WPS doivent couvrir la période des données initiales et aux frontières de WRF.",
                        ),
                    )
                )
        if n == 1 and (
            start.replace(tzinfo=None) != case.period.start.replace(tzinfo=None)
            or effective_end.replace(tzinfo=None) != case.period.end.replace(tzinfo=None)
        ):
            findings.append(
                Finding(
                    "warning",
                    tr(
                        "Raw WRF dates/duration differ from the project period used to prepare inputs and report statistics. Align the project period before launching.",
                        "Les dates ou la durée brutes de WRF diffèrent de la période du projet, utilisée pour préparer les données et les statistiques. Alignez la période du projet avant de lancer.",
                    ),
                )
            )
    return findings


def check_namelists(case: Case) -> list[Finding]:
    try:
        wrf = final_input(case)
        wps = {group: dict(options) for group, options in build_namelist_wps(case).items()}
    except (
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        ArithmeticError,
        NotImplementedError,
    ) as error:
        return [
            Finding(
                "error",
                tr(
                    f"Namelists cannot be generated from these settings: {error}",
                    f"Les namelists ne peuvent pas être générées avec ces réglages : {error}",
                ),
            )
        ]
    types = _type_checks(case, wrf, wps)
    # Semantic checks must not perform arithmetic on an option whose type is already invalid.
    if any(finding.severity == "error" for finding in types):
        return types
    return (
        types
        + _geometry_checks(case, wrf, wps)
        + _period_checks(case, wrf, wps)
        + _physics_checks(case, wrf)
        + check_time_steps(case, wrf)
    )
