---
title: Sea surface temperature
section: Input data
order: 30
summary: Why the SST matters offshore, separate SST products (OSTIA, RTG, ERA5 SST), how WPS combines them with the atmospheric data, and the SST update during long runs.
related: input-data, input-sources, vtables
---

## Why it matters

Offshore, the difference between the sea surface temperature and the air temperature sets the
stability of the lowest layers: a sea colder than the air stabilises the flow, which increases
wind shear and makes wakes last longer; a warmer sea makes the flow unstable and mixes wakes
faster. An SST error of 1 K changes the simulated stability noticeably.

## From the atmospheric data (default)

WRF uses the sea surface temperature contained in the atmospheric data: the `SST` field when
the variable table extracts one (ERA5 with `Vtable.ECMWF`), otherwise the skin temperature over
water (`SKINTEMP`, as with GFS).

## A separate SST product

Choose **Separate SST files** to use a dedicated analysis (OSTIA, RTG, the SST of another source)
with its own folder, file pattern and variable table (`Vtable.SST` by default, which extracts the
single field `SST`). The application then:

- runs **ungrib a second time** on these files with the prefix `SST` (namelist `&ungrib`
  `prefix = 'SST'`), keeping the `FILE:` files of the first pass;
- sets `fg_name = 'FILE', 'SST'` in `&metgrid`. metgrid reads the sources in this order and a
  later source takes priority for a field present in both (WPS `metgrid/src/process_domain_module.F`),
  so the separate SST replaces the SST of the atmospheric data.

ungrib fills the times missing between two available records by linear interpolation in time
(WPS `ungrib/src/ungrib.F`, call to `datint`): a daily SST product serves 6-hourly boundary
times. The files must still **cover the start and the end of the period**: a record at or before
the start, and one at or after the end, on the steps of the boundary data (with 6-hourly data, an
analysis at 00, 06, 12 or 18 UTC). When the SST times do not fall exactly on the start and the
end, the application widens the period of the SST pass of ungrib to the SST times around them
(`namelist.wps.sst`), so that ungrib interpolates every boundary time of the run; the run itself
keeps its period.

SST analyses in **NetCDF** (OSTIA from the Copernicus Marine Service, the ERA5 SST...) are
converted on this computer into `SST:` intermediate files at the run's boundary times,
interpolated linearly between the analyses, over the outer domain and a margin; the SST pass of
ungrib is then not needed. Values missing over land are written as missing (-1e30), as ungrib
does for GRIB fields with a bitmap.

## SST update during the run

Without update, WRF keeps the SST of the initial time for the whole run, which is acceptable for
a few days but not for weeks or months. With **Update the SST during the run** the application
sets, following WRF's `README.namelist`:

- `sst_update = 1` in `&physics`: real.exe writes SST, sea ice (XICE), albedo and vegetation
  fraction at every boundary time into `wrflowinp_d<nn>` files, and WRF reads them during the run;
- `auxinput4_inname = "wrflowinp_d<domain>"`, `auxinput4_interval` (minutes, per domain) and
  `io_form_auxinput4 = 2` in `&time_control`. The interval follows the boundary data by default,
  as the README advises ("generally matches time given by interval_seconds").

`README.namelist` recommends `usemonalb = .true.` (monthly albedo) with the SST update: the
checks remind you of it when it is not set in Physics.

The application warns when a run longer than five days has no SST update.
