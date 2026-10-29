---
title: WRF time series
section: Outputs
order: 50
summary: Enable time series, place a named point on the map and review the tslist file.
related: outputs, coordinates, namelists
---

`tslist` is the file telling WRF where to write time series at every model time step and
profiles. These measurement points are virtual sites in the simulation.

In **Outputs > Measurement points**:

1. Turn on **Record measurement points**.
2. Choose one series per turbine, per cell containing turbines, or no automatic sites.
   Set the number of vertical levels to retain.
3. To add a mast, LiDAR or buoy, click **Place on the map**, then the desired location.
   Enter its name and check coordinates in the window that opens, then confirm.
   **Enter coordinates** and **Import a list** provide the other methods.
4. Find your named sites on the map and in the list beside it; edit or remove them there.
   The summary separates automatic sites from added sites and opens the `tslist` preview.

Prefixes identify files and must be unique. WRF imposes name and prefix length limits;
the form checks them. **See an example** shows the format for importing a list.

Requested sites are assigned to WRF cells. Requested and sampled positions can differ. Extraction records this, height and method. High-frequency series can be large; choose only useful sites and levels.

In **Results > Measurement points**, **Export as CSV** gives the table of the chosen point: the quantities ticked, the values without turbines beside them, the period ]start, end] in UTC, means over the chosen duration.

The TS file holds WRF's surface values: temperature and water vapour at 2 m, wind at 10 m, surface pressure, fluxes. Wind and temperature at a height come from the profiles (UU, VV, TH, PR on the model levels, heights in PH), interpolated linearly; T = θ (p / p₀)^(Rd/cp). The turbine power is the Fitch scheme's, recomputed at every step with its own formula on the cell's profiles (hub wind, induction correction for the n turbines of the cell): it matches the POWER of the history files. Without turbines, it is the power curve at the free wind.

Official reference : [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

