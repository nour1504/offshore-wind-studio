"""The diagnostics offered for a run, and whether each one is direct, derivable or impossible
with the files the run produced."""

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from owstudio.core.extract.history import HistoryFiles
from owstudio.core.extract.quantities import LEVEL_QUANTITIES, SURFACE

Status = Literal["direct", "derivable", "impossible"]


@dataclass(frozen=True)
class Diagnostic:
    key: str
    label: str
    unit: str
    needs_height: bool
    # Alternatives in order of preference: (variables required, status when present, method)
    ways: tuple[tuple[tuple[str, ...], Status, str], ...]
    # Also available from the tslist files at the locations of the time series
    in_tslist: bool = False
    enable: str = ""
    notes: tuple[str, ...] = field(default_factory=tuple)


HEIGHT = ("PH", "PHB", "HGT")
DIAGNOSTICS: tuple[Diagnostic, ...] = (
    Diagnostic(
        "wind_speed",
        "Wind speed",
        "m/s",
        True,
        (
            (
                ("U", "V", "COSALPHA", "SINALPHA", *HEIGHT),
                "derivable",
                "U, V destaggered, rotated to earth-relative, interpolated in height",
            ),
        ),
        True,
    ),
    Diagnostic(
        "wind_direction",
        "Wind direction (from, clockwise from north)",
        "°",
        True,
        (
            (
                ("U", "V", "COSALPHA", "SINALPHA", *HEIGHT),
                "derivable",
                "direction of the earth-relative components",
            ),
        ),
        True,
    ),
    Diagnostic(
        "u",
        "Eastward wind (earth-relative)",
        "m/s",
        True,
        (
            (
                ("U", "V", "COSALPHA", "SINALPHA", *HEIGHT),
                "derivable",
                "rotation of U, V with COSALPHA, SINALPHA",
            ),
        ),
        True,
    ),
    Diagnostic(
        "v",
        "Northward wind (earth-relative)",
        "m/s",
        True,
        (
            (
                ("U", "V", "COSALPHA", "SINALPHA", *HEIGHT),
                "derivable",
                "rotation of U, V with COSALPHA, SINALPHA",
            ),
        ),
        True,
    ),
    Diagnostic(
        "potential_temperature",
        "Potential temperature",
        "K",
        True,
        ((("T", *HEIGHT), "derivable", "T + 300 K"),),
        True,
    ),
    Diagnostic(
        "virtual_potential_temperature",
        "Virtual potential temperature",
        "K",
        True,
        ((("T", "QVAPOR", *HEIGHT), "derivable", "θ (1 + 0.608 qv)"),),
    ),
    Diagnostic(
        "temperature",
        "Air temperature",
        "K",
        True,
        ((("T", "P", "PB", *HEIGHT), "derivable", "θ (p/p0)^(Rd/cp)"),),
        True,
        notes=("2 m: T2",),
    ),
    Diagnostic(
        "pressure", "Pressure", "Pa", True, ((("P", "PB", *HEIGHT), "derivable", "P + PB"),), True
    ),
    Diagnostic(
        "density",
        "Air density",
        "kg/m³",
        True,
        ((("T", "P", "PB", "QVAPOR", *HEIGHT), "derivable", "p / (Rd T (1 + 0.608 qv))"),),
    ),
    Diagnostic(
        "mixing_ratio",
        "Water vapour mixing ratio",
        "kg/kg",
        True,
        ((("QVAPOR", *HEIGHT), "direct", "QVAPOR"),),
        True,
    ),
    Diagnostic(
        "tke",
        "Turbulent kinetic energy",
        "m²/s²",
        True,
        (
            (("QKE", *HEIGHT), "derivable", "QKE / 2 (MYNN)"),
            (("TKE_PBL", *HEIGHT), "direct", "TKE_PBL"),
        ),
        enable="Use a PBL scheme that writes TKE (MYNN, bl_pbl_physics = 5, writes QKE).",
    ),
    Diagnostic(
        "wind_speed_std",
        "Standard deviation of the wind (from TKE, isotropic)",
        "m/s",
        True,
        (
            (("QKE", "U", "V", *HEIGHT), "derivable", "σ = √(2 TKE / 3), TKE = QKE / 2"),
            (("TKE_PBL", "U", "V", *HEIGHT), "derivable", "σ = √(2 TKE / 3)"),
        ),
        enable="Use a PBL scheme that writes TKE (MYNN, bl_pbl_physics = 5, writes QKE).",
        notes=(
            "Isotropy assumed (σu = σv = σw): in the surface layer σu is about 20 % larger.",
            "Sub-grid turbulence of the PBL scheme only.",
        ),
    ),
    Diagnostic(
        "turbulence_intensity",
        "Turbulence intensity (from TKE, isotropic)",
        "–",
        True,
        (
            (("QKE", "U", "V", "COSALPHA", "SINALPHA", *HEIGHT), "derivable", "√(2 TKE / 3) / U"),
            (
                ("TKE_PBL", "U", "V", "COSALPHA", "SINALPHA", *HEIGHT),
                "derivable",
                "√(2 TKE / 3) / U",
            ),
        ),
        enable="Use a PBL scheme that writes TKE (MYNN, bl_pbl_physics = 5, writes QKE).",
        notes=(
            "Isotropy assumed (σu = σv = σw): in the surface layer σu is about 20 % larger.",
            "Not given where U < 2 m/s.",
            "Sub-grid turbulence of the PBL scheme only, unlike a measured 10-minute TI.",
        ),
    ),
    Diagnostic("pblh", "Boundary layer height", "m", False, ((("PBLH",), "direct", "PBLH"),)),
    Diagnostic(
        "friction_velocity", "Friction velocity u*", "m/s", False, ((("UST",), "direct", "UST"),)
    ),
    Diagnostic(
        "sensible_heat_flux",
        "Sensible heat flux (upward)",
        "W/m²",
        False,
        ((("HFX",), "direct", "HFX"),),
        True,
    ),
    Diagnostic(
        "latent_heat_flux",
        "Latent heat flux (upward)",
        "W/m²",
        False,
        ((("LH",), "direct", "LH"),),
        True,
    ),
    Diagnostic("sst", "Sea surface temperature", "K", False, ((("SST",), "direct", "SST"),)),
    Diagnostic(
        "skin_temperature", "Skin temperature", "K", False, ((("TSK",), "direct", "TSK"),), True
    ),
    Diagnostic(
        "roughness_length",
        "Roughness length",
        "m",
        False,
        ((("ZNT",), "direct", "ZNT"),),
        enable="Add ZNT to the history outputs (Outputs page).",
    ),
    Diagnostic(
        "inverse_obukhov_length",
        "Inverse Obukhov length 1/L",
        "1/m",
        False,
        (
            (("RMOL",), "direct", "RMOL written by WRF"),
            (
                ("UST", "HFX", "T2", "PSFC", "Q2", "QFX"),
                "derivable",
                "from u*, HFX, QFX, T2, Q2, PSFC",
            ),
        ),
        enable="RMOL is a restart-only variable in WRF 4.8: add RMOL to the history outputs (Outputs page) to get the surface layer scheme's own value.",
    ),
    Diagnostic(
        "obukhov_length",
        "Obukhov length L",
        "m",
        False,
        (
            (("RMOL",), "derivable", "1 / RMOL"),
            (("UST", "HFX", "T2", "PSFC", "Q2", "QFX"), "derivable", "1 / (1/L) from the fluxes"),
        ),
        notes=("Near-neutral values (|L| above 10^6 m) are left empty: use 1/L.",),
    ),
    Diagnostic(
        "power",
        "Turbine power per grid cell",
        "W",
        False,
        ((("POWER",), "direct", "POWER (all turbines of the cell)"),),
        enable="Simulate wind farms with the Fitch or MAV scheme.",
    ),
)

assert {d.key for d in DIAGNOSTICS} >= set(LEVEL_QUANTITIES) | set(SURFACE) - {
    "surface_pressure",
    "moisture_flux",
}


def availability(files: HistoryFiles | None, tslist: bool) -> list[dict[str, Any]]:
    """For each diagnostic: direct, derivable or impossible with these files, and why."""
    result = []
    for diagnostic in DIAGNOSTICS:
        status: Status = "impossible"
        method = ""
        missing: list[str] = []
        for needed, way_status, way in diagnostic.ways:
            absent = [name for name in needed if files is None or not files.has(name)]
            if not absent:
                status, method = way_status, way
                break
            missing = missing or absent
        entry = {**asdict(diagnostic), "status": status, "method": method}
        del entry["ways"]
        if status == "impossible":
            entry["missing"] = missing
            if diagnostic.in_tslist and tslist:
                entry["status"], entry["method"] = (
                    "derivable",
                    "from the tslist files at the time series locations only",
                )
        result.append(entry)
    return result
