"""Write the turbine files read by the WRF wind farm schemes.

WRF 4.8 reads the turbines from different files depending on the scheme
(phys/module_wind_fitch.F and phys/module_wind_mav.F):

- Fitch (windfarm_opt = 1, windfarm_ij = 0): windturbines.txt, one line per turbine:
  ``latitude longitude type``
- MAV (windfarm_opt = 2, windfarm_ij = 2): windturbines-ll.txt, one line per turbine:
  ``latitude longitude farm type``, turbines grouped by farm, since the scheme computes each
  farm's local coordinates from consecutive lines with the same farm number.

Both read wind-turbine-<type>.tbl for each turbine type.
"""

from owstudio.core.case.model import Case, TurbineType

LAYOUT_FILES = {"fitch": "windturbines.txt", "mav": "windturbines-ll.txt"}


def turbine_table(turbine: TurbineType) -> str:
    """Content of wind-turbine-N.tbl, in the format described in WRF's README.windturbine."""
    characteristics = (
        f"{turbine.hub_height_m:g} {turbine.rotor_diameter_m:g} "
        f"{turbine.standing_thrust_coefficient:g} {turbine.rated_power_mw:g}"
    )
    lines = [str(len(turbine.curve)), characteristics]
    lines += [f"{p.wind_speed:g} {p.thrust_coefficient:g} {p.power_kw:g}" for p in turbine.curve]
    return "\n".join(lines) + "\n"


def turbine_rows(case: Case) -> list[dict[str, object]]:
    """The simulated turbines in the order of the layout file, which is WRF's numbering."""
    rows: list[dict[str, object]] = []
    for farm_number, farm in enumerate(case.enabled_farms if case.farm_scheme else [], start=1):
        for k, turbine in enumerate(farm.turbines, start=1):
            rows.append(
                {
                    "index": len(rows) + 1,
                    "farm": farm.id,
                    "farm_number": farm_number,
                    "turbine": turbine.id or f"{farm.id}-{k}",
                    "type": turbine.type,
                    "lat": turbine.lat,
                    "lon": turbine.lon,
                }
            )
    return rows


def layout_text(case: Case) -> str:
    rows = turbine_rows(case)
    if case.farm_scheme and case.farm_scheme.scheme == "mav":
        return "".join(
            f"{r['lat']:.6f} {r['lon']:.6f} {r['farm_number']} {r['type']}\n" for r in rows
        )
    return "".join(f"{r['lat']:.6f} {r['lon']:.6f} {r['type']}\n" for r in rows)
