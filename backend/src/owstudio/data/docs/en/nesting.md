---
title: Domain nesting
section: Domains
order: 50
summary: Nested domains: grid ratio, placement in the parent domain and margins.
related: getting-started, namelists, results
---

`parent_id` identifies the parent; `i_parent_start` and `j_parent_start` locate the nested domain's corner in its parent's indices. Parents come before their nested domains. A nested domain must stay inside its parent, with margins.

Dimensions must satisfy `(e_we - 1) % parent_grid_ratio == 0`, and likewise for `e_sn`. The interface suggests compatible dimensions. After editing, check the map and observation sites. All domains need an appropriate time step.

Official reference: [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

