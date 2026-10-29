---
title: Namelists and advanced options
section: Physics and namelists
order: 50
summary: How the namelists are generated from the project, and how to change any WRF option.
related: physics, input-data, domains, outputs
---

`namelist.wps` configures preprocessing; `namelist.input` configures initialization and WRF. The app generates them from the project and then applies editor overrides.

In **Physics and namelists > Namelists**, choose `namelist.input` or `namelist.wps`.
Each block shows the project's options and opens on demand. In **Add an option**, choose
a group, then search by option code or purpose. The WRF 4.8 schema determines field types,
per-domain values and defaults; hover a setting for its description and units.
Undocumented options can still be added by their code.

Scalars and per-domain arrays are different. Syntactically valid options can still be
incompatible.

A value controlled by another page is locked here; its link opens the correct setting.
For an editable option, your override takes priority. **Undo my value** removes that override
and restores automatic generation.

**Import** accepts an existing file or pasted text, with examples and a preview before
applying it to the draft. In **Generated files**, review the final version before a run,
then copy or download it. For a windowed study, the preview shows the first computed window,
the latest; dates in the remaining windows are adapted automatically.

Official reference : [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

