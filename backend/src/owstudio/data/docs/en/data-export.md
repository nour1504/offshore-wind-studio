---
title: Exporting outputs
section: Results
order: 55
summary: The outputs of a run as CSV: the tslist points at every model time step, or one wrfout variable at a point.
related: tslist, explorer, turbulence-intensity
---

The **Export** tab writes the CSV files of the chosen run. Results, Explorer, Wind analyses and Measurements keep their charts; their **Export** link opens this tab already filled in.

**tslist points**: the series WRF writes at every time step at the measurement points (turbines, masts).

- **Points**: the grid cells holding points. The points of one cell have the same series, written once.
- **Quantities**: every one of the tslist files, at the given heights above ground, plus the TKE, the turbulence intensity, the shear exponent and the wind veer between the lowest and the highest height.
- **Average**: every model step, or means over ]t - duration, t], stamped at their end t. TI comes from the mean TKE and the mean speed, the direction from the mean components, L from the mean of 1/L.
- **Layout**: **In rows**, one row per time and per cell, with its points, its number of turbines and their names; **In columns**, one row per time, each quantity of a cell once, its turbines in the column name.
- **Power**: `cell_power` is WRF's POWER of the whole grid cell; `turbine_power` is that POWER divided by the number of turbines of the cell (one turbine type per cell). In columns, each turbine has its own column. Without a wind farm parameterization, the power of a turbine comes from the power curve at the hub-height wind and the cell power is not given.
- With a run without turbines imported, its values follow, suffixed `_no_farm`.

The TKE comes from the `.TK` file of a WRF compiled by the installer: QKE/2 with MYNN, TKE_PBL with MYJ, QNSE and BouLac. The other boundary layer schemes have none: the TKE and the TI are then reported as not available.

**wrfout grid**: one variable of the history files at one point (a turbine, a tslist point or a position), at each output time, interpolated between the four nearest cells.

Each file starts with `#` lines: the source (tslist or wrfout), the time step, the averaging, the period ]start, end] in UTC and what is missing, with the reason. The units are in the column names.

Under every chart, the same line gives the source and the step of the values: "tslist, 10 min" or "wrfout, 60 min".
