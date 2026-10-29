---
title: Domain nesting
section: Domains
order: 50
summary: Nest finer domains: refinement ratio, placement in the parent and margins.
related: getting-started, namelists, results
---

`parent_id` identifies the parent; `i_parent_start` and `j_parent_start` locate the nest corner in parent indices. Parents precede children. A nest must remain inside its parent with boundary margins.

Dimensions must satisfy `(e_we - 1) % parent_grid_ratio == 0`, and likewise for `e_sn`. The interface suggests compatible dimensions. After editing, check the map and observation sites. All domains need an appropriate time step.

Official reference : [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

