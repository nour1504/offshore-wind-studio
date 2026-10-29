---
title: iofields file
section: Outputs
order: 50
summary: Add or remove variables from the wrfout output files with the iofields file.
related: getting-started, namelists, results
---

For history stream 0, `+:h:0:NAME` adds a variable and `-:h:0:NAME` removes one. Names must exist in Registry and variables must be allocated by the chosen physics.

Adding a name cannot create a field absent from a scheme. Check its fiche and WRF logs. Removing necessary fields can prevent later analyses.

Official reference : [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

