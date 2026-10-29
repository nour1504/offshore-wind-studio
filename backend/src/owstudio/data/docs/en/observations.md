---
title: Comparing observations and WRF
section: Observations
order: 50
summary: Import measurements (masts, LiDAR, buoys) and compare them with simulations at the same places and times.
related: getting-started, namelists, results
---

Import CSV or NetCDF and check time, timezone, site, height/reference, variable, unit, quality and averaging interval. Source files are copied with metadata; originals are untouched.

Series are harmonized to UTC and common units before alignment. Resolve ambiguous daylight-saving times explicitly. Directions need circular averaging; 359° and 1° do not average to 180°.

Compare compatible periods, heights and averaging. Bias, RMSE and correlation need coverage and valid-pair counts. Spatial resolution and LiDAR representativeness remain physical limitations.

Official reference : [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

