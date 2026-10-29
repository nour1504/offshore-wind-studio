---
title: Period, spin-up and outputs
section: Input data
order: 15
summary: Useful UTC period, one spin-up setting, window length and grouping.
related: input-data, input-sources, outputs, independent-windows
---

## Start and end

Times are **UTC**, as in the input data and in WRF. The start must be a time present in the input
data (for GFS and the usual ERA5 setup, 00, 06, 12 or 18 UTC).

## Boundary data every…

`interval_seconds` in both namelists: the spacing in time of the input data, which also sets how
often WRF receives new boundary conditions. It must match the files (see
[Sources](doc:input-sources)).

## One spin-up setting S

The project period is the useful period **[D, F]**. **Spin-up** (in **Calculation windows**), denoted S,
applies to every simulation, including a study fitting in one window. S defaults to 12 h;
6/12/24 h and another duration remain available. The model starts S hours before useful time
to adjust its initial state to its grid and physics. Those hours are simulated then discarded;
there is no second spin-up setting for statistics.

## Output frequency

`history_interval` (minutes) of the history files (`wrfout`), which hold full 3-D fields: shorter
intervals give smoother maps and animations but use a lot of disk. Time series written at
turbines and masts (tslist) are written at **every model time step** whatever this interval.

Set this interval in **Outputs > Full maps**. It is separate from boundary-data spacing
and the WRF numerical time step, which is set in **Domains**.

## Independent windows

The **length of a window** L defaults to 72 h. A period of length at most L gives a single
calculation. Otherwise, **Store the outputs by** chooses how the outputs are stored before being
assembled over the whole period: by month, by 3 months (calendar quarter), by week (Monday
00:00 UTC) or by window. Each of them is cut from its end, so its shortest window comes first.
A window never runs across two of them.

Each window uses fresh files from `real.exe`, then runs `wrf.exe`, with `restart = .false.`.
Computation runs **antichronologically**, from the latest window to the earliest.
Input weather data must cover **D − S through F**, rounded to the data times.

**Any length** is possible (10 minutes as well as a year): weather files exist only at some times (every 6 h for GFS, every hour for ERA5), so real.exe prepares from one data time to another (the spin-up starts at the data time before, and lasts at least S; the preparation goes to the data time after the end) and wrf.exe stops exactly at the wanted end (`run_*`, which takes precedence over `end_*` per README.namelist). The history interval must divide the period.
 The staircase in **Calculation windows**
shows one step per window, from the first date to the last; the spin-up is the hatched strip
before each step (never kept). From afar, the steps are gathered by month or by year; the
wheel, dragging and the +, − buttons zoom and move. The tooltip of a step gives its dates and
its rank in the order of computation (from the last window to the first). See the [detailed protocol](doc:independent-windows).

## Independent or chained windows

- **Independent** (default): as above.
- **Chained**: the same windows form one continuous simulation. A single spin-up, before the
  first; **chronological** computation; each window starts again (`restart = .true.`) from the
  `wrfrst` written at the end of the previous one (`restart_interval` = its length). Only the
  last `wrfrst` is kept. Kept outputs, assembly and import: unchanged.

Example, 2016, L = 72 h, S = 12 h: independent, the window of 29 March starts on 28 March 12:00;
chained, it carries on at 29 March 00:00, where the previous one stopped. In the staircase, the
spin-up (hatched strip) then appears only before the first step.
