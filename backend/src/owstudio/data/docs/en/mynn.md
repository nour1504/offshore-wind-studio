---
title: MYNN boundary layer
section: Physics and namelists
order: 50
summary: The MYNN boundary layer, needed for wind farms, and what its TKE can tell.
related: getting-started, namelists, results
---

`bl_pbl_physics=5` selects MYNN. Levels, surface layer, turbulence options and TKE treatment must fit the study and farm scheme.

MYNN may provide `QKE` (twice TKE). TI derived under isotropy is not a measured ten-minute LiDAR TI. See [Turbulence intensity](doc:turbulence-intensity) for methods, units and limits.

Official reference : [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

