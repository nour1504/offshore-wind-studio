---
title: Period and input data
section: Input data
order: 10
summary: What WRF starts from, how the input data are prepared by WPS, and what the application checks before a run.
related: period, input-sources, sst, vtables
---

WRF is a limited-area model: it needs an **initial state** of the atmosphere, land and sea at the
start of the period, and **boundary conditions** around its outer domain for the whole period.
Both come from a global model or reanalysis.

## How the data reach WRF

1. **ungrib** (WPS) reads the GRIB files and extracts the fields listed in the variable table
   ([Vtable](doc:vtables)) into intermediate files, one per time, named `FILE:YYYY-MM-DD_HH`.
   A separate sea surface temperature product goes through a second ungrib pass under the
   prefix `SST` (see [Sea surface temperature](doc:sst)).
2. **geogrid** prepares the static fields of each domain (terrain, land use, soil) from the
   geographical data (WPS_GEOG).
3. **metgrid** interpolates the intermediate files horizontally onto the domains: `met_em` files.
4. **real.exe** interpolates vertically onto the WRF levels and writes the initial state
   (`wrfinput`) and the boundary file (`wrfbdy`), and the SST update file (`wrflowinp`) when the
   SST update is on.
5. **wrf.exe** runs the simulation.

The exported package runs these steps on the compute machine: WPS once per calendar year,
then real and WRF window by window (see [Export a run](doc:export)).

## Where are the files?

The exported package holds a download script in `data/`. For a Linux computer it downloads
into the engine's data folder (for example `/app/ows/donnees`), shared by every calculation:
data already there are not downloaded again. For a cluster it downloads into the package's
`data/`. ERA5 uses `cdsapi` and your CDS
access on the downloading machine. For your own GRIB / NetCDF, choose the folder in
**Period and data** instead.

`geo_em`, ungrib's `FILE:*` / `SST:*` files and `met_em` remain on the compute machine, in
the package's `wps/` folder. Only the imported WRF outputs come back to the application.

## Choices on the page

- [Period](doc:period): start and end (UTC), spacing of the boundary data, spin-up, outputs.
- [Source of the atmospheric data](doc:input-sources): GFS or ERA5 downloaded by the
  application, or your own GRIB files.
- [Sea surface temperature](doc:sst): from the atmospheric data or a separate product, and its
  update during long runs.

## Checks before a run

Before the export, the application checks that the source covers
the period, that your folder exists and contains a supported format (GRIB, or ERA5/OSTIA NetCDF
on a regular latitude-longitude grid), that the GRIB variable table is valid and, for a separate
SST, that it produces the field `SST`. Problems
are listed on the page, with the reason.

Supported NetCDF inputs are converted directly to WPS intermediate files, replacing ungrib.
A Vtable identifies GRIB codes; it does not convert arbitrary NetCDF. Required fields, units,
levels and dates are still checked.
