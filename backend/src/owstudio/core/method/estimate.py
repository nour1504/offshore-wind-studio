"""Order of magnitude of the computing time of WRF and of its memory, for a number of cores.

WRF's work grows with the grid points of each domain (west-east × south-north × levels) times the
number of its steps (simulated time / its time step): a grid twice finer has 4 times the points
and twice the steps, 8 times the work. The work is shared between the cores, beyond the physical
cores nothing is gained.

Calibrated on this computer (26/10/2026): Horns Rev, 2 domains 100 × 100 (9 km, 3 km, steps 45 s
and 15 s), 51 levels, 6 physical cores: about 21 min for 12 h simulated. WPS and real.exe are left
out (a few minutes).
"""

from typing import Any

from owstudio.core.case.model import Case
from owstudio.core.method import plan as method
from owstudio.core.method import timesteps

_REFERENCE_WORK = 43200 * 100 * 100 * 51 * (1 / 45 + 1 / 15)
CORE_SECONDS_PER_POINT_STEP = 6 * 21 * 60 / _REFERENCE_WORK
# Memory, order of magnitude: about 1 kB per grid point of all domains, and each MPI process
# its own copy of the tables and buffers
BYTES_PER_POINT = 1_000
BYTES_PER_PROCESS = 200 * 1024**2


def estimate(case: Case) -> dict[str, Any]:
    """CPU time of WRF over the whole calculation (core seconds) and memory of the grid."""
    steps = timesteps.time_steps(case).steps
    simulated = method.plan(case).simulated_seconds
    levels = case.grid.e_vert
    points = [d.e_we * d.e_sn * levels for d in case.grid.domains[: case.max_dom]]
    work = simulated * sum(p / float(s) for p, s in zip(points, steps, strict=True))
    return {
        "core_seconds": work * CORE_SECONDS_PER_POINT_STEP,
        "memory_bytes": sum(points) * BYTES_PER_POINT,
        "process_bytes": BYTES_PER_PROCESS,
        "simulated_seconds": simulated,
    }
