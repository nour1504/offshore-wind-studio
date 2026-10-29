---
title: Physics and dynamics
section: Physics and namelists
order: 50
summary: Review physics by topic, access advanced options and check the generated files.
related: namelists, mynn, fitch, mav
---

The page has two tabs, with sections closed initially:

- **Namelists**: choose `namelist.input` or `namelist.wps`, then open a block.
  **Physics** groups turbulence, clouds, radiation and land surface; **Dynamics** holds
  flow settings. Choices use their familiar names, with per-domain values when needed.
  **Add an option** gives access to the remaining WRF options.
- **Generated files**: the final files to review, copy or download.

Microphysics, radiation, surface, boundary layer and convection schemes form a consistent
configuration. Some options are per domain. Wind farm schemes impose compatibility
requirements, including MYNN for Fitch.

**Offshore preset** compares the proposed values with your current settings before applying
them. It is a starting point: scientific choices depend on region, resolution and period.
Nudging and other advanced options remain in the [namelist editor](doc:namelists).

Dates, grid settings, farms and outputs are controlled on their own pages. Links on the
managed options take you there without entering the same values twice.

Official reference : [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

