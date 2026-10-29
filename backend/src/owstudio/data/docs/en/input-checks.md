---
title: Checking your input files
section: Input data
order: 25
summary: What the application reads in your GRIB or NetCDF files before a run, and the problems it reports: missing fields, missing times, too few levels, an area too small for the domain.
related: input-sources, vtables, sst, period
---

Before a run, and on demand with **Examine the files** on the Data page, the application reads
your files and tells you what WPS will find in them. The aim is to stop a configuration that
would fail hours later in ungrib, metgrid or real.exe, and to explain why.

## What is read

For **GRIB** files, only the headers of the messages: parameter, level, date, grid. The data
themselves are skipped, so even large folders are read quickly; the result is kept until a file
changes. Dates are computed as ungrib computes them (forecast hours, averaged fields valid at
the end of their period). Each message is then matched against your **Vtable** with ungrib's
own rules, which gives the fields and levels ungrib will extract, and the messages it will
ignore.

For **NetCDF** files, the variables, their units, levels, times and grid.

The result lists the files, the originating centre (ECMWF, NCEP...), the grid and its step, the
first and last times and their spacing, every field with its number of levels and times, the
pressure levels and the soil layers. For GRIB files, the standard Vtables are ranked by how well
they read the files.

## Errors: the run would fail

- **A field metgrid or real.exe cannot do without**: temperature and wind on pressure levels
  (mandatory in metgrid's METGRID.TBL), humidity, surface or sea-level pressure, soil
  temperature on at least two levels for land surface models such as Noah (real.exe stops
  without them).
- **The first or the last time of the period is missing** (GRIB): ungrib stops with "Data not
  found". With NetCDF files, a time outside the times of the files.
- **A required field missing at some times** while other fields are there.
- **The model top above the data**: real.exe needs data up to the model top (`p_top_requested`,
  50 hPa by default).
- **The outer domain beyond the data's area**: metgrid cannot interpolate outside the grid of
  the data.
- **No message matches the Vtable**, a Vtable ungrib cannot read, damaged or incomplete files
  (a download cut short), a folder mixing GRIB and NetCDF files.
- **SST files**: no SST field, or SST times that do not reach the start and the end of the
  period.

## Warnings: the run would work, perhaps poorly

- Times missing between the first and the last: interpolated linearly in time.
- Fewer than 10 pressure levels: a coarse vertical interpolation.
- Fields that are not required but useful: geopotential height, skin temperature, land-sea mask,
  2 m temperature, 10 m wind, terrain height of the source, soil moisture.
- An outer domain within two grid steps of the edge of the data, where metgrid falls back to
  simpler interpolations.

## Quick checks while you edit

While you edit the case, folders not examined yet are read only up to 1 GB; larger folders are
reported as "not examined yet" and are read in full right away with
**Examine the files**.
