---
title: Local compute profiles
section: Compute
order: 50
summary: Use WRF/WPS on Windows with dedicated WSL or directly on Linux.
related: engine-install, export, storage
---

A profile tells where this computer's WRF/WPS engine is. **Compute** offers two environments:

- **Windows · dedicated WSL**: distribution `OffshoreWindStudio-WRF`, user `owstudio`.
- **Linux · local installation**: the Linux running this application.

**Install an engine** configures the profile after checking WRF/WPS.
For an existing installation, open **Advanced options > Describe an engine installed by hand**.
Saving a profile does not start an installation or a run. The profile serves to install and
check the engine; the 3D view reads the geography (WPS_GEOG) from it.

## Folders

Profile paths are Linux paths. WRF, WPS and WPS_GEOG point to the programs and the
geography. A parent folder is accepted: **Verify** and the scripts use the right subfolder and
report it. The input data folder (GFS, ERA5) is shared by all calculations. The scripts
download the data there and ungrib reads it there. It must be writable.

A path changed here also reaches **WRF files** and the cleanup in **Storage**. Not the reverse:
a path changed by hand in WRF files only holds for those files.

An engine installed before version 0.6.2 keeps its data inside the engine (`<engine>/input`).
**Compute** shows it ("Inside the engine (before 0.6.2)"): **Move to …** puts them into the
shared folder next to the engine, without downloading anything again.
The application's local folders are set separately in **Settings**.

**Verify installation** checks programs and paths without simulating.

To prepare files and scripts to run elsewhere, see [Export a run](doc:export).
