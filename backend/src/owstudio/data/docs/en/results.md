---
title: Reading and exporting results
section: Results
order: 50
summary: Read the production, the wind at the points and the maps of a run, then export them.
related: analyses, data-export, wake-efficiency
---

Choose a run and domain. Maps and series use actual available outputs; times are UTC. Hub-height values are interpolated from levels using the stated method. Vector winds are rotated to geographic axes.

The energy is that of the useful period. Capacity factors use the covered duration; gaps are not counted as zeros.

Power and energy come from the tslist outputs at the turbines when they exist (10-minute means), otherwise from WRF's POWER of the wrfout files (trapezoidal integration between the output times). The source is written at the bottom left of the page.

The energy is read per farm, per grid cell or per turbine: the power of a turbine is that of its cell divided by the number of turbines of the cell. The **Export** link of a chart opens the [Export](doc:data-export) tab: its CSV files keep the units, the source and the averaging.

Official reference: [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

