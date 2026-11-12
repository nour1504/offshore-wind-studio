---
title: Fitch parameterization
section: Wind farms
order: 50
summary: The Fitch parameterization: how WRF represents turbine drag and turbulence, and what it requires (MYNN).
related: getting-started, namelists, results
---

`windfarm_opt=1` represents turbine drag and turbulence below the grid scale. The WRF guide requires MYNN (`bl_pbl_physics=5`). Positions, heights, diameters and power/thrust curves must be consistent.

`POWER` is the power of every turbine of a grid cell. The power of a turbine is this POWER divided by the number of turbines of the cell (one turbine type per cell): it is not the measured power of each rotor.

Official reference: [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

