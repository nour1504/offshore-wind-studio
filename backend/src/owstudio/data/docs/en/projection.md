---
title: Projection and coordinates
section: Domains
order: 50
summary: The WRF map projection (Lambert, Mercator…) and its settings.
related: getting-started, namelists, results
---

`map_proj` selects Lambert, Mercator, polar or latitude-longitude. `ref_lat` and `ref_lon` anchor the outer domain. `truelat1`, `truelat2` and `stand_lon` depend on the projection; consult WPS before changing them.

The display uses longitude/latitude degrees; WRF grid distances depend on its projection. Map factor describes local distortion. Geographic distances and grid indices are different quantities.

Official reference : [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

