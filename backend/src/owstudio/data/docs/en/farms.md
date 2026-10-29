---
title: Farms
section: Wind farms
order: 50
summary: Create farms, place turbines in them and switch each one on or off for the run.
related: turbines, coordinates, fitch, mav, results
---

Each farm has a stable identifier, a name and turbines. Disabling a farm retains its layout but removes its forcing from the run. Without a wind farm scheme, turbines have no effect on WRF.

**Colour** and **symbol**: click the farm in the list ("+": other colour). By default, each
farm has its own markers. No effect on positions or on the computation.

When markers become crowded, the map shows a light outline and the exact turbine count for
each farm. Select the farm or zoom in to recover individual markers. **Every turbine** forces
their display at any scale. The outline joins the outer positions; it is neither a lease
boundary nor a simulation area.

Select a farm, then **Map click** (one click, one turbine), **One turbine**, or **Paste, generate**:

- **Paste**: name; latitude; longitude; model, one line per turbine (Excel, text file).
- **Zone**: draw a polygon on the map; it is filled with turbines.
- **Grid**: rows × columns around a centre placed on the map.
- **GIS file**: GeoJSON, KML or shapefile; its points, or one of its polygons filled.

Layout settings: **Spacing** (along a row), **Between rows**, **Orientation** (clockwise from
east), **Layout** (aligned, staggered), **Edge setback**. The rotor diameter (D) is shown below each spacing.
**Replace** swaps the farm's turbines; **Add** keeps them. Coordinates stay editable in the table.

Wake losses require comparable runs with identical inputs, dates and domains. A multi-farm study plans subsets: three farms give eight combinations, including no turbines. Farm-alone, one-neighbour and all-neighbour energy are distinct comparisons; their effects need not add linearly.

Official reference : [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

