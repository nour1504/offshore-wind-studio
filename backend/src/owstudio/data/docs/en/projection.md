---
title: Projection and coordinates
section: Domains
order: 50
summary: The WRF map projection (Lambert, Mercator…) and its settings.
related: getting-started, namelists, results
---

`map_proj` selects Lambert, Mercator, polar or latitude-longitude. `ref_lat` and `ref_lon` anchor the outer domain. `truelat1`, `truelat2` and `stand_lon` depend on the projection; consult WPS before changing them. A true latitude is a latitude where the map does not distort distances; `stand_lon` is the longitude parallel to the y-axis. WPS advises choosing the projection that keeps the distortion low over the domain: a high distortion (map factor far from 1) restricts the model time step. **Fit the projection to the domain** puts the true latitudes at one sixth of the domain from its south and north edges and the standard longitude at its centre; after a change of the size or of the grid spacing of the domain, **To adjust** shows as long as the parameters are not those. Parameters typed on purpose are not flagged as long as the domain does not change.

The display uses longitude/latitude degrees; WRF grid distances depend on its projection. Map factor describes local distortion. Geographic distances and grid indices are different quantities.

Official reference: [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

