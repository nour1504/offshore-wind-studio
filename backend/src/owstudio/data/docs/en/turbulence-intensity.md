---
title: Turbulence intensity from TKE
section: Analyses
order: 30
summary: How the standard deviation of the wind along its direction and the turbulence intensity are derived from WRF's turbulent kinetic energy, and the limits of this estimate.
related: analyses, results, mynn
---

WRF does not write a turbulence intensity. With the MYNN boundary layer scheme
(`bl_pbl_physics = 5`) it writes `QKE`, twice the turbulent kinetic energy (TKE); with MYJ,
QNSE and BouLac, `TKE_PBL`, the TKE itself. The application derives the turbulence from it.

## Formulas

The TKE is half the sum of the variances of the three wind components:

    TKE = ½ (σu² + σv² + σw²)

σu is the standard deviation along the wind, σv across it, σw on the vertical. With the ratios
between components of IEC 61400-1 (Kaimal model), σv = 0.8 σu and σw = 0.5 σu:

    TKE = ½ σu² (1 + 0.8² + 0.5²) = 0.945 σu²

    σu = √(TKE / 0.945)

and the turbulence intensity at the same height and time is

    TI = σu / U

where U is the horizontal wind speed. TI is not given below 2 m/s.

Up to version 0.7.3 the turbulence was taken as isotropic, σ = √(2 TKE / 3): σ and TI are
26 % higher since version 0.7.4.

## At the tslist points

A WRF compiled by the application's installer writes one more profile per point, the `.TK`
file: the TKE at each level, QKE/2 with MYNN, TKE_PBL with MYJ, QNSE and BouLac, a missing
value with the other schemes. The TKE is interpolated to the height asked for, like the wind.
Over 10 minutes, the TKE and the speed are averaged first:

    σu = √(mean TKE / 0.945)        TI = σu / mean U

The `.QK` file of version 0.7.4 (QKE of MYNN) is still read. Without either (stock WRF 4.8),
TI comes from the wrfout files, at their output times.

## Limits

- **Fixed ratios between the components.** σv / σu and σw / σu change with stability and
  height; 0.8 and 0.5 are the values of the standard.
- **Sub-grid turbulence only.** The TKE of the boundary layer scheme represents the turbulence
  the model does not resolve; fluctuations resolved on the grid and mesoscale variability are not
  included, while a measured 10-minute TI contains part of them.
- **Wind farms.** With the Fitch parameterization the turbines add TKE (`windfarm_tke_factor`), so the TI
  in and behind a farm includes the turbine-added turbulence; compare with the run without
  turbines to see the farm's effect.

Every series and map of σu or TI carries these caveats in its metadata.
