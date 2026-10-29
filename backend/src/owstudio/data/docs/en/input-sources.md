---
title: Sources of the atmospheric data
section: Input data
order: 20
summary: GFS and ERA5 downloaded by the exported package's script, or your own GRIB or NetCDF files (converted at export).
related: input-data, input-checks, vtables, sst, era5-access
---

## GFS (NOAA)

NCEP Global Forecast System analyses at 0.25°, every 6 hours, downloaded from NOAA's public
archive on Amazon Web Services (no account needed). The archive starts on 1 January 2021. One
file holds every field of one time (about 500 MB). The application uses the analyses (forecast
hour 0) and WPS's `Vtable.GFS`.

## ERA5 (Copernicus)

ECMWF's fifth reanalysis at 0.25°, available from 1940 and published about five days behind
real time. The application requests one day at a time from the Copernicus Climate Data Store
(CDS), on pressure levels and single levels, over your outer domain plus a 2° margin, in GRIB,
and reads it with `Vtable.ECMWF`. It needs:

- a free CDS account and its API key, typed in **Settings** (see [ERA5 access](doc:era5-access));
- the ERA5 licences accepted once on the CDS website.

## Your own files (GRIB or NetCDF)

Choose **My own files** when you already have the data: ERA5 downloaded from the CDS (in GRIB
or NetCDF), output of another global or regional model, an operational archive. Give:

- the **folder** on this computer and a file **pattern** (`*.grib`, `era5-*`…). Subfolders
  are included. "Show the files" lists the files found, which the exported scripts use too;
- the **variable table** (Vtable) that tells ungrib which records to extract
  (`Vtable.ECMWF` for ERA5, `Vtable.GFS` for GFS, … or a custom table, see
  [Vtables](doc:vtables)).

The page lists the matching files with their format, and **Examine the files** shows what
will be read from them: fields, pressure levels, times, grid and area, with the problems that
would stop WPS or WRF (see [Checking your input files](doc:input-checks)).

WPS's ungrib reads **GRIB editions 1 and 2 only**. A folder of **NetCDF files** (the default
download format of the new CDS, or OSTIA SST analyses) is converted by the application, on this
computer and before the run, into the WPS intermediate files ungrib would have written: same
field names, units and levels, same derived fields (geopotential to height, 2 m humidity from the
dew point, snow water equivalent, land-sea flag). The Vtable is not used then. Supported: ERA5
on pressure levels and single levels in the current and the legacy CDS layouts (including packed
values and the ERA5/ERA5T `expver` dimension) and SST analyses on regular latitude-longitude
grids. The converted files are written into the exported package (see below). A folder must hold one kind of file only.

### Where the exported package reads your files

- **GRIB**: the exported scripts run ungrib on the compute machine; give the Linux folder of your
  files in the "BASE SETTINGS" at the top of the scripts (or an absolute Linux path in the
  application, used as is).
- **NetCDF**: ungrib reads only GRIB. At export, the application converts your files on this
  computer into WPS intermediate files, in `wps/intermediate/<source>/` of the package, for every
  time of the WPS passes (spin-up included). The WPS script then skips ungrib for this source:
  it links these files under the names ungrib would have given them (`FILE:2025-10-01_00`) and
  metgrid reads them. The folder must be on this computer at export; the export may take a few
  minutes for a long period.

## Spacing of the boundary data

The **boundary data every** setting (`interval_seconds`) must match the time spacing of the
files: 6 h for GFS analyses, 6 h or less for ERA5 (the download script takes ERA5 at this
spacing). With your own GRIB files, the first and the last time of the period must be in the
files: ungrib stops otherwise ("Data not found"); a time missing in between is interpolated
linearly from the surrounding ones (WPS `ungrib/src/datint.F`), which the checks report. With
NetCDF files, any time of the run between two times of the files is interpolated the same way.
