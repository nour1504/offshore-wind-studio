---
title: WRF domains
section: Domains
order: 50
summary: Place the computational domains: size, resolution and projection of the simulated area.
related: nesting, projection, namelists, turbines, outputs
---

The outer domain defines the simulated area. `dx` is horizontal spacing in metres; `e_we` and `e_sn` count grid points. Nest spacing is its parent's spacing divided by `parent_grid_ratio`.

Sections are closed initially. In **Map**, **Centre on** only moves the view. To move a
domain, select it, activate **Place on the map**, then click. In **Domains**, set extent,
spacing and nesting. A domain's placement command reopens the map.

Choose a projection appropriate to the region and check the outline after moving a domain.
Keep farms away from boundaries and allow upstream fetch. Grid spacing and rotor diameter
are different scales: turbines are parameterized below the grid scale.

The time step (`time_step`, in seconds) is how far WRF advances at each computation step. Usual rule: about 5 s per km of d01 grid spacing, 6 at most. A larger step makes the computation unstable, and WRF stops d01 above `reasonable_time_step_ratio` (6 by default); a smaller one only makes it longer. Each nest divides its parent's step by `parent_time_step_ratio`, equal to its refinement. Left automatic, the time step follows the grid spacing of d01; with `use_adaptive_time_step`, WRF chooses it during the run.

`e_vert` is the vertical level count; `p_top_requested` is top pressure in Pa. Level count alone does not guarantee sufficient rotor-height resolution.

## Vertical grid and 3D view

Open **Vertical grid** and choose how the **levels are computed**: **Automatic** (real.exe
computes them from the first layer and the stretching, `auto_levels_opt = 2`) or **By hand** (you
type or paste the full eta levels, `eta_levels`, from 1 at the ground to 0 at the top, strictly
decreasing; their number sets `e_vert`). The interface displays the model top in hPa and converts
it to Pa for WRF.

Nothing is shown when all is well. If real.exe would refuse the settings (top not reached, upper
layers thicker than 1.5 x `max_dz`, eta levels out of order or in a wrong number, after
`dyn_em/module_initialize_real.F` of WRF 4.8), the problem is shown in red, in keywords, with the
correction when one exists (already checked with the same computation as real.exe) and the
**Apply** button; the full explanation and the source are in the tooltip.

### Advice: the layers in the rotor

For WRF's wind farm scheme (Fitch), publications advise thin layers at rotor height:

- **about 10 m in the lowest ~200 m**: Tomaszewski & Lundquist (2020), *Geoscientific Model
  Development* 13, 2645-2662 (about 7 levels across a 77 m rotor);
- **12 m at most** to reproduce the measured power: Lee & Lundquist (2017), *Geoscientific Model
  Development* 10, 4229-4244.

With the **automatic** levels, layers grow from one level to the next (stretching): a thinner
**first layer** and less **stretching** get closer, but cannot reach 10-12 m up to 200 m and still
reach the top, even with 200 levels. Example computed by the application, 51 levels and a top at
50 hPa: WRF's defaults (first layer 50 m, stretching 1.3), thickest layer below 200 m ≈ 103 m;
first layer 10 m and stretching 1.15, ≈ 35 m. For thinner layers still, type the levels **by
hand** (eta_levels): the column and the table of the levels show the heights at once. The column, level table and 3D view remain available in their sections; the 3D
scene loads only when opened.

Heights are those of **WRF's reference atmosphere** (base state), computed from the project's
vertical settings and hybrid coordinate. They are not the actual meteorological heights at
a simulated time: those vary with temperature. The figure shows levels and rotors at the
same scale.

In the **3D view**, the icons above it show or hide (name on hover): **Terrain**, **Levels**,
**Curtain** (the layers on a vertical cut, green near the sea to blue aloft), **Rotor layers**
(those crossed by the blades, orange on the curtain), **Turbines**, **Farm air** (a column over
each farm, from the sea to the top of the blades). **Grid cells**, one choice: none, on the
ground, or on every level shown, never both. They are the real cells of the domain shown and,
brighter, those of the domains nested in it: on d01, d02's refinement shows. Beyond 120 cells a
side, one line in N is drawn (said in the tooltip). Each farm carries a label
with its name; a click on it, or **Frame a farm**, brings the camera to that farm.

**3D view > Terrain** offers two sources. **Geography**: a `geo_em` file of the domain or a
folder holding a WPS_GEOG geography; a parent folder is accepted. Empty field: the engine
geography. **Public tiles**: terrain downloaded from the Internet, with bathymetry; without
Internet access, the geography is used. With no source, the terrain is flat. The **Terrain**
line shows the source used and, unfolded, its path and any errors. The `geo_em` must match the
domain (number, spacing, dimensions, coordinates). These display choices do not modify WRF files.

Official reference : [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

