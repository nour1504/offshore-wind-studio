---
title: WPS/WRF files and scripts
section: Runs
order: 5
summary: Prepare, export, execute and import the results.
related: period, independent-windows, input-data, tslist, results
---

## Prepare

Save the project, then open **WRF files**.
Choose **Cluster (Slurm)** or **Linux computer**. Sections start closed.

- **Program folders**: Linux paths to WRF, WPS and WPS_GEOG on the compute machine.
  A parent folder is accepted. The scripts look for the subfolder holding `main/wrf.exe`,
  `geogrid.exe` or the topography of the chosen resolution (`topo_gmted2010_30s` or
  `topo_gmted2010_5m`) and write it in their log. The page shows "Folder used".
- **Input files**: pattern for each source; `%Y` represents the year. ERA5-Land and separate SST
  remain distinct sources.
- **Processes**: WRF and geogrid/metgrid; ungrib always runs with one process.
- **Slurm header**: cluster resources, time limit, partition and environment. Editor mode accepts
  `#SBATCH` directives; `{job}` is replaced by the job name.
- **Files**: exact content preview. Resolve errors before exporting; non-dividing time-step
  warnings do not change your model time step.

**Extract all the files** creates a new subfolder in the chosen folder.
**Download the ZIP** produces the same content, preserving script execution permissions.
Text files use ASCII and LF line endings, including exports made on Windows.

## Execute

The package runs without Offshore Wind Studio. The compute machine needs WRF/WPS, their
libraries and the input data. First read its `README.txt`: its dates, paths and script names
match the exported project.

1. Prepare the input data using the provided script in `data/`, or your existing files.
   On a Linux computer it downloads into the engine's data folder, shared by every
   calculation; ungrib reads there too.
   ERA5 requires `cdsapi` and your CDS access on the download machine.
2. From `wps/`, run `run_wps.sh`: `bash run_wps.sh` on a computer, `sbatch run_wps.sh` on a
   cluster. Before ungrib it checks the free space (about 3 times the size of one GRIB file per
   time); after it, that there is one file per time. Otherwise it stops with the reason instead
   of letting metgrid fail further on.
3. Once WPS is done, from `wrf/`, run `run_wrf.sh` the same way. It is the one WRF script, the
   same on a cluster and on a computer (only its header differs): every window, the series
   stored by month (or quarter, week, window), then the assembly of the period.

If it stops (failure, interruption), run the same command again: it resumes at the next window.
On a cluster, before each window, it checks that there is time left to finish it before the
job's limit (`--time`); otherwise it submits itself again and the new job resumes at the next
window. There is nothing to split by hand.

WPS runs once per calendar year with the spin-up margin. All `met_em` files go to
`wps/met_em/`. WRF windows start cold, from last to first, in the same folder.
`window_plan.csv` and `manifest.json` record the plan. Changing the period requires exporting
again.

## Retrieve results

Keep the package and its `manifest.json`. History files cover **[start, end]**; series in
`wrf/tslist_period/` cover **]start, end]**, in hours since the study start.
Spin-up history files are set aside in `wrf/spin_up/`.

In **Results and energy → Import outputs**, choose the package or its `wrf/` folder.
For a reference without turbines, export a second package with no simulated farms and provide
its reference folder. Check the preview, then import by copying or linking.
A same-disk hard link shares file contents: changes affect both paths.

Ten-minute means use UTC intervals **]t − 10 min, t]**, stamped at their end.
Each value is constant over the preceding model step; incomplete intervals are excluded.
Speed is averaged after computing its magnitude, direction from the mean components.

`POWER` is power per grid cell; a per-turbine value is a reconstruction.

Opening a page or exporting never launches a simulation.
