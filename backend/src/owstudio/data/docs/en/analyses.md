---
title: Wind and stability analyses
section: Analyses
order: 50
summary: Wind roses, Weibull distributions, profiles and stability computed from the outputs, and how to read them.
related: getting-started, namelists, results
---

Roses use meteorological **wind-from** direction in degrees clockwise from true north. Distributions and Weibull use valid samples in the selected period. Interpret them with sample count and gaps.

Profiles, shear and veer depend on the available levels. Stability is classed by the Obukhov length L, with the thresholds of Gryning et al. (2007), Boundary-Layer Meteorology 124: neutral for |L| ≥ 500 m, unstable for L < 0, stable for L > 0. With a WRF compiled by the application's installer, 1/L is in the tslist outputs at every time step: it is averaged over 10 minutes, L = 1 / (mean 1/L), and the classes count 10-minute values. Otherwise L comes from the wrfout files, at their output times (RMOL = 1/L written by WRF, otherwise from the surface fluxes).

Explorer and variable fiches show diagnostic requirements. Missing fields are reported rather than replaced with invented results.

The analyses are for one turbine: the tslist series of its cell, read as 10-minute means of every model time step (direction from the mean components).

Without tslist outputs at the turbines, the analyses come from the wrfout files, at their output times: wind interpolated at the turbine; production from WRF's POWER, the energy of each interval between two times (mean of the two powers × duration) in the sector of the mean wind of the two times; power curve against the free wind of the same time. The source is written at the bottom left of the page.

**Production**: for each 10-minute interval of the tslist outputs, the turbine's mean power and the mean wind direction at the hub over that interval; the interval's energy (mean power × 10 min) goes to the sector of that direction. The same for the run without turbines, hence the wake loss per sector.

**Power curve**: the turbine's mean power over each 10-minute interval, against the mean free wind of the same interval (the hub-height wind at the same place in the tslist outputs of the run without turbines; without that run, no curve), sorted in 0.5 m/s bins (method of bins of IEC 61400-12-1). Cp = P / (½ ρ A U³), ρ = 1.23 kg/m³ as in WRF. The turbine table is drawn beside it; a turbine in the wake of others lies below the table.

Official reference: [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

