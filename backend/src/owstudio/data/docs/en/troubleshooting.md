---
title: Understanding failures
section: Troubleshooting
order: 50
summary: Find the cause of a failed run, stage by stage (ungrib, metgrid, real, WRF).
related: getting-started, namelists, results
---

Start with the failed stage and its log tail. For ungrib check GRIB format, Vtable, fields, times and free space (ungrib does not report a full disk; `run_wps.sh` checks it before and after). For metgrid check area coverage, levels/fields and paths. For real check soils, boundaries, levels and terrain. For WRF check time step/CFL, compatible schemes, MPI resources and disk space.

The base map and the elevation tiles use the system certificates, as `wget` does. Behind a company proxy, the proxy's certificate authority must be installed there.

Memory or disk exhaustion requires reviewing volume and resources. Do not remove a WSL disk to fix a namelist. Settings shows inputs and outputs. Preserve the log and run configuration when seeking support.

Official reference : [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

