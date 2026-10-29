---
title: Install the WRF/WPS engine
section: Compute
order: 40
summary: Install WRF/WPS on Windows with dedicated WSL or in a chosen Linux folder.
related: compute, export, getting-started
---

**Compute > Install an engine** installs and checks WRF/WPS. Nothing is installed at startup.
Only the target matching the system running the application is available.

## Choose the location

- **Windows · dedicated WSL**: choose the Windows folder for the virtual disk of
  `OffshoreWindStudio-WRF` (Ubuntu 24.04, user `owstudio`). An existing dedicated distribution
  is reused at its current location. Enabling WSL may require administrator approval and a
  restart. Other distributions are not changed.
- **Linux · local installation**: choose the **engine installation folder** on the first
  screen. It can be outside your home folder if you have write access. Use a dedicated
  absolute Linux folder without spaces or `..`.

The default is `~/OffshoreWindStudioEngine/wrf4.8.0-wps4.7.0-gnu13-v1`.
A nonempty folder unrelated to the installer is refused.

## Contents

| Component | Version |
|---|---|
| Official WRF, em_real, GNU, dmpar | 4.8.0, commit `06d4240ae9` |
| Official WPS, GNU, dmpar, GRIB1/GRIB2 | 4.7.0, commit `5feccecd63` |
| GNU C/C++/Fortran | 13.3.0 |
| OpenMPI | 4.1.6 |
| NetCDF C / Fortran | 4.9.2 / 4.6.1 |

Conda-forge libraries are installed with the engine. zlib, libpng and JasPer come from WPS
sources. The profile keeps the actual installed versions and their manifest.

## Geography and space

- **High resolution**: official NCAR package, about 2.8 GB downloaded and 29 GB unpacked.
  Allow about 45 GB including the engine.
- **Low resolution**: about 150 MB, for tests and teaching only.
- **Existing WPS_GEOG folder**: give its Linux path; no geography is downloaded.

A downloaded or sent geography goes next to the engine, into `geog/WPS_GEOG` or
`geog/WPS_GEOG_LOW_RES` (engine in `/app/ows/moteur`: `/app/ows/geog/...`). The input data go
into `donnees/`, at the same level.

The buttons show the unpacked size (29 GB high, 0.5 GB low; 2.8 GB and 150 MB to download).
A geography already on the machine is chosen by itself (high resolution first): nothing is
downloaded.

Complements depend on the physics options in use. The assistant offers them, and project
checks report any that are missing. Checked archives are removed after unpacking.

## Check and install

**Check the target** checks the system, tools, available space, internet access and folder.
**Install the engine** downloads and compiles, generally taking 20 minutes to 2 hours depending
on the connection and processor. Follow it under **Engine installations**. Resuming keeps
completed stages; cancellation targets only this installation.
A folder that already holds this engine is said under **Folder**: it is kept, nothing is
compiled again. A stop is said in a few words (disk full, network, NCAR blocked,
compilation…); the detail is in **Log**.

The final check covers sources, executables, libraries, MPI, NetCDF and geography indexes.
The profile is configured after success. Installation includes no weather download or
simulation. The recipe targets Linux x86_64 with glibc 2.17 or later.

To run a study on other infrastructure, use the [exported files and scripts](doc:export).
