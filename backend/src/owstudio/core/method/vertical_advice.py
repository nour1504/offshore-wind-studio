"""Checks of the vertical grid: only what real.exe would refuse (advice belongs to the help).

Refusals (WRF 4.8 module_initialize_real.F, ported in vertical.py): too few levels to reach the top,
upper layers over 1.5 x max_dz, eta_levels not from 1 to 0, not strictly decreasing, or not e_vert
of them. Each comes with its source and, when one exists, a correction verified with real.exe's
computation: the fewest levels (e_vert) reaching the top, else WRF's default stretching aloft and
thickest layer (README.namelist). Nothing here changes the levels.
"""

import dataclasses
from dataclasses import dataclass
from typing import Any

from owstudio.core.case.model import Case
from owstudio.core.i18n import tr
from owstudio.core.method import vertical

# README.namelist, WRF 4.8
WRF_DEFAULTS = {"dzstretch_u": 1.1, "max_dz": 1000.0}
MOST_LEVELS = 200

SOURCES = {
    "real": "WRF 4.8, dyn_em/module_initialize_real.F (levels) ; run/README.namelist",
}


@dataclass(frozen=True)
class Check:
    key: str
    ok: bool
    # Keywords for the screen; the full explanation is in `detail`, for the tooltip
    message: str
    source: str
    # A verified correction: values to apply, in the case's units (p_top_requested in Pa)
    changes: dict[str, float] | None = None
    # The full explanation (real.exe's message with every way out), for the tooltip
    detail: str = ""


def _heights(s: vertical.VerticalSettings) -> list[float]:
    znw = vertical.full_levels(s)
    c = vertical.coefficients(znw, s.hybrid_opt, s.etac, s.p_top)
    return vertical.column(s, znw, c, 0.0)


def _works(s: vertical.VerticalSettings) -> bool:
    try:
        _heights(s)
    except vertical.VerticalError:
        return False
    return True


def _fewest_levels(s: vertical.VerticalSettings) -> int | None:
    for e_vert in range(max(3, s.e_vert), MOST_LEVELS + 1):
        if _works(dataclasses.replace(s, e_vert=e_vert)):
            return e_vert
    return None


def _real_check(s: vertical.VerticalSettings) -> Check:
    try:
        _heights(s)
    except vertical.VerticalError as error:
        changes: dict[str, float] | None = None
        if s.eta_levels is None and s.auto_levels_opt == 2:
            levels = _fewest_levels(s)
            if levels is not None:
                changes = {"e_vert": levels}
            else:
                reset = dataclasses.replace(
                    s, dzstretch_u=WRF_DEFAULTS["dzstretch_u"], max_dz=WRF_DEFAULTS["max_dz"]
                )
                levels = _fewest_levels(reset)
                if levels is not None:
                    changes = {**WRF_DEFAULTS, "e_vert": levels}
        return Check(
            "real",
            False,
            error.keyword,
            SOURCES["real"],
            changes,
            tr(f"real.exe would stop: {error}.", f"real.exe s'arrêterait : {error}."),
        )
    return Check(
        "real",
        True,
        tr("real.exe: OK", "real.exe : OK"),
        SOURCES["real"],
    )


def checks(case: Case) -> list[Check]:
    if not case.max_dom:
        return []
    s = vertical.settings(case)
    return [_real_check(s)]


def as_json(found: list[Check]) -> list[dict[str, Any]]:
    return [dataclasses.asdict(c) for c in found]
