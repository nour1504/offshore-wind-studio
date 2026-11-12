---
title: Variable tables (Vtables)
section: Input data
order: 40
summary: What a Vtable is, which one to choose, how to read its rows, and when to write a custom one.
related: input-sources, sst, input-data
---

A **Vtable** tells WPS's ungrib which records of the GRIB files to extract and under which name
metgrid will know them. WPS ships one table per common data source in
`ungrib/Variable_Tables`; the application includes the tables of WPS 4.7.0 so that you can see
and check them without a WPS installation. A run with a standard table uses the copy of the
engine's own WPS.

## Which table

| Data | Table |
|---|---|
| GFS, GDAS | `Vtable.GFS` |
| ERA5, ECMWF IFS | `Vtable.ECMWF` |
| SST analyses (OSTIA, RTG…) | `Vtable.SST` |
| CFSR, CFSv2 | `Vtable.CFSR` |
| NAM | `Vtable.NAM` |
| UK Met Office Unified Model | `Vtable.UKMO_ENDGame` |
| DWD ICON (pressure levels) | `Vtable.ICONp` |

The page shows the **fields produced** by the selected table (TT, UU, VV, RH, GHT, PSFC, PMSL,
SKINTEMP, SST, LANDSEA, soil layers…).

## Reading a row

```
GRIB1| Level| From |  To  | metgrid  | metgrid  | metgrid      |GRIB2|GRIB2|GRIB2|GRIB2|
Param| Type |Level1|Level2| Name     | Units    | Description  |Discp|Catgy|Param|Level|
-----+------+------+------+----------+----------+--------------+-----------------------+
  11 | 100  |   *  |      | TT       | K        | Temperature  |  0  |  0  |  0  | 100 |
```

- GRIB1 parameter number and level type, then the level range (`*` = every level of this type);
- the metgrid name, units and description;
- the GRIB2 discipline, category, parameter number and level type.

The header ends with a line of dashes, and the table with another line of dashes; text after
the last line is a note ignored by ungrib.

## Custom tables

Choose **Custom table…** to adapt a standard table, for example to add a field your files
contain, or to remove one with a different meaning. Start from the closest standard table and
edit its rows: the application checks the layout and lists the fields produced. The custom text
is stored in the project and written as the run's `Vtable`.

A wrong table does not always fail: ungrib may silently extract nothing for a field, and metgrid
or real.exe then stop because a required field is missing. Check the fields produced against
what the files contain.
