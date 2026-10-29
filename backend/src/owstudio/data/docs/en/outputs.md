---
title: Output variables and frequency
section: Outputs
order: 50
summary: Distinguish time series at chosen points from full maps, then set frequency and variables.
related: tslist, iofields, results
---

The **Outputs** page separates two uses:

- **Measurement points**: virtual points where weather is recorded at every WRF time step.
  Choose turbine locations and add your own sites on the map
  (see [WRF time series](doc:tslist)).
- **Full maps**: fields over every domain, written in `wrfout` files for maps and animations.

In **Full maps**, **Write every** sets `history_interval`, in minutes. More frequent outputs
increase volume and support finer charts/videos. A video cannot create missing outputs or
physical resolution. This interval does not change time-series frequency at points.

Add or remove history variables with `iofields`. Diagnostics require particular fields: 3D wind and geopotential for hub-height wind, fluxes/UST or RMOL for Monin–Obukhov, TKE for some turbulence estimates. The explorer distinguishes available, derivable and impossible.

Disk estimates depend on written fields, levels, compression and restart files.

WRF's standard variables remain included unless you remove them. Add/remove lists,
suggestions and the `iofields.txt` preview are in **Full maps**. Imported outputs are in the projects
folder (see **Settings > Storage**).

Official reference : [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

