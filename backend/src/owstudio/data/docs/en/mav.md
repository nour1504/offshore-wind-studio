---
title: MAV parameterization
section: Wind farms
order: 50
summary: The MAV scheme: sub-grid wakes, choice of the wake model and of how wakes combine.
related: getting-started, namelists, results
---

`windfarm_opt=2` adds subgrid wakes and their superposition. `windfarm_wake_model` selects Jensen (1), XA (2), GM (3), Jensen+XA (4) or all three (5). `windfarm_overlap_method` controls Jensen/XA wake superposition (1 to 4).

Compare Fitch and MAV as a sensitivity study with identical inputs, period and layout. Individual production estimates remain limited by the outputs actually written by WRF.

Official reference : [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

