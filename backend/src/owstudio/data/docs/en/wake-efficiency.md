---
title: Production and wake losses
section: Results
order: 50
summary: How production and wake losses are computed, against the reference without turbines.
related: getting-started, namelists, results
---

Import the run without turbines like any other run (one folder per import), then choose it at the top of Results, under “Without turbines”: a run of this project or of another one, on the same grid. The choice can be changed at any time.

The no-turbine run provides reference wind. Its power conversion uses the same turbines and method as the farm run. Loss is reference production minus waked production; the percentage is relative to reference.

Local negative losses can occur; do not clip them automatically. With the Fitch scheme and `windfarm_induction = 1`, WRF does not take the cell's wind as it is: it divides it by (1 − a)ⁿ, n being the number of turbines in the cell, to recover the wind before they slowed it. When a cell holds many turbines, this correction overshoots the free wind: in a 3 km cell with 28 turbines, the cell's wind is 9.9 m/s, the wind without turbines 11.1 m/s, and the corrected power is 4 % above that of the free wind (without the correction the loss would be 21 %). The gain comes from the correction, not from a real speed-up. Multiple turbines/farms within a cell limit individual separation. Multi-farm studies distinguish neighbour effects and interactions from actual simulated combinations.

Curve and WRF POWER methods are not interchangeable; each result identifies the method used.

Official reference : [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

