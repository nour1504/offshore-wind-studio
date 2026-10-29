---
title: WRF files
section: Runs
order: 50
summary: Export the WPS/WRF files to run on the compute machine, then import the outputs.
related: export, independent-windows, results
---

The **WRF files** page prepares the package of files and scripts that runs WPS then WRF on a
cluster or a Linux computer. The application does not launch the simulations itself.

## Prepare and execute

1. Save the project.
2. In **WRF files**, choose **Cluster (Slurm)** or **Linux computer** and set that machine's
   program paths, weather sources and resources.
3. Review checks and file previews. **Extract all the files** and **Download the ZIP** produce
   the same package; neither action runs a simulation.
4. Follow the package's `README.txt` to prepare data, run WPS, then WRF.

The package works without the application. The engine and inputs must be available on the
compute machine. The [export guide](doc:export) details commands and files.

Windows start cold, with spin-up every time and no restart from another window. They run from
last to first in the same folder. The common method supplies the plan, dates and order; a
period change requires another export. `wrfout` covers **[start, end]** and series **]start, end]**.

## Import results

In **Results and energy → Import outputs**, choose the executed package or its `wrf/`
subfolder, with `manifest.json` available. An optional no-turbine reference comes from a second
package. A parent folder is accepted when it holds a single
calculation. "Check" shows the files to import. Import by copy, or by hard link on the same
disk. Hard links
share content: keep linked files unchanged.
