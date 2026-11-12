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
3. To add a mast, LiDAR or buoy, click **Place on the map**, then the desired position.
   Enter its name and check coordinates in the window that opens, then confirm.
   **Enter coordinates** and **Import a list** provide the other methods.
4. Find your named sites on the map and in the list beside it; edit or remove them there.
   The summary separates automatic sites from added sites and opens the `tslist` preview.

Prefixes identify files and must be unique. WRF imposes name and prefix length limits;
the form checks them. **See an example** shows the format for importing a list.

Requested sites are assigned to WRF cells. Requested and sampled positions can differ. Extraction records this, height and method. High-frequency series can be large; choose only useful sites and levels.

The **Export** tab gives these series as CSV: points, quantities, heights, averaging, period ]start, end] in UTC, values without turbines beside them ([Exporting outputs](doc:data-export)).

The TS file holds WRF's surface values: temperature and water vapor at 2 m, wind at 10 m, surface pressure, fluxes. Wind and temperature at a height come from the profiles (UU, VV, TH, PR on the model levels, heights in PH), interpolated linearly; T = θ (p / p₀)^(Rd/cp).

A WRF compiled by the application's installer also writes, at the end of each line of the TS file, 1/L (RMOL), the bulk Richardson number (BR), the friction velocity (UST), the boundary layer height (PBLH) and the power of the turbines of the cell (POWER, in kW; 0 without a wind-farm parameterization), and one more profile, TK (the TKE at each level: QKE/2 with MYNN, TKE_PBL with MYJ, QNSE and BouLac; a missing value with the other schemes). The application reads the stability, the turbulence and the power there; stock WRF 4.8 does not write them.

The power of a turbine is WRF's POWER of its cell at every step, divided by the number of turbines of the cell: one turbine type per cell, checked by the project. Without POWER in the TS file, it is the formula of the Fitch parameterization itself, recomputed at every step on the cell's profiles (hub wind, induction correction for the n turbines of the cell): it matches the POWER of the history files. Without turbines, it is the power curve at the free wind.

Official reference: [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

