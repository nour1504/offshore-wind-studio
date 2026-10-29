---
title: Storage and cleanup
section: Storage
order: 50
summary: Where the application keeps its files, how much space they take and how to clean up.
related: compute, input-data, results
---

Settings shows projects/runs, map cache, observations, exports, videos, reports and logs. Each run keeps its snapshot and outputs in its own folder. Categories may use alternative folders.

These bases belong to the application computer. "Downloaded data" shows and empties the
engine's input data folder, subfolders included. A click on a row shows its files. Set the engine's Linux folders — input
data and WPS_GEOG — in **Compute**, for each profile. Run subfolders are generated
automatically; there is no separate path to enter for every `geo_em`, `met_em` or `wrfout`.

Cleanup shows what it removes. Inputs may be shared between studies; deleted outputs cannot be analysed. Preserve needed data before deleting. Uninstalling retains projects and data.

WSL data in a local VHDX occupies local disk even through Windows network-style shares. The app never removes those virtual disks.

Official reference : [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

