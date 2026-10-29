---
title: Fitch parameterization
section: Wind farms
order: 50
summary: The Fitch scheme: how WRF represents turbine drag and turbulence, and what it requires (MYNN).
related: getting-started, namelists, results
---

`windfarm_opt=1` represents turbine drag and turbulence below the grid scale. The WRF guide requires MYNN (`bl_pbl_physics=5`). Positions, heights, diameters and power/thrust curves must be consistent.

`POWER` is aggregated per grid cell. Turbine shares are reconstructed with the energy module's method and assumptions; they are not individually measured rotor power. Result notes and method documentation report approximations.

Official reference : [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

