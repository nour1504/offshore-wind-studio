---
title: Calculation windows and spin-up
section: Runs
order: 51
summary: One spin-up S before every window, blocks cut from their ends and antichronological computation.
related: period, input-data, outputs, results, export
---

In **Period and data**, the project period is the useful period **[D, F]**. Spin-up S defaults
to 12 h and maximum useful window length L to 72 h. Both are adjustable. A study of length
at most L gives one simulation from D − S through F.

## Cutting and computation order

For a period longer than L, the outputs are stored by calendar month, by calendar quarter
(3 months), by week starting Monday at 00:00 UTC, or by window (setting **Store the outputs
by**), then assembled over the whole period. This storage forms the blocks of the calculation. Each block is cut from its end, placing the shortest window at
its start. Useful window intervals never cross a block boundary.

Every window simulates from its useful start − S through its useful end, cold-started with
`real.exe` followed by `wrf.exe`, without restarting from its predecessor. Computation runs
**antichronologically**: latest blocks and their latest windows first. The no-turbine reference
uses matching dates and protocol. The staircase shows the spin-ups and the kept hours;
the tooltip of each step gives its rank in the order of computation.

## WPS preparation and outputs

Weather inputs must cover D − S through F. WPS is prepared by calendar year, every pass
starting S hours before its own useful part. All `met_em` files go into one folder, including
those needed by a window crossing January 1.

Every window retains **]useful start, useful end]**. Final history files cover **[D, F]**,
including D itself; time series cover **]D, F]**. With one `wrfout` file per time
(`frames_per_outfile = 1`), windows computed afterwards replace the spin-up files of later
windows. The correct useful time remains once, without duplicates. Files before D are set aside.

The export records the plan in `window_plan.csv` and conventions in `manifest.json`.
See the [export guide](doc:export) for scripts and run folders.

Beyond a few days, a free simulation drifts away from reality: hence windows of 72 h at
most, each restarting from the weather data. This is the exported **study protocol**; WRF
itself does not impose this limit. The official guide also describes long simulations and restarts. Windowing and usual time-step recommendations do not guarantee numerical stability; review checks, physics, grids, boundary data and CFL logs.

References: [running WRF](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/running_wrf.html), [physics and long simulations](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html#long-simulations).
