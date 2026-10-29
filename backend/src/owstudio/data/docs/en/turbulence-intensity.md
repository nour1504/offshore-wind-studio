---
title: Turbulence intensity from TKE
section: Analyses
order: 30
summary: How the standard deviation of the wind and the turbulence intensity are derived from WRF's turbulent kinetic energy, assuming isotropic turbulence, and the limits of this estimate.
related: analyses, results, mynn
---

WRF does not write a turbulence intensity. With the MYNN boundary layer scheme
(`bl_pbl_physics = 5`) it writes `QKE`, twice the turbulent kinetic energy (TKE), and the
application derives the turbulence from it.

## Formulas

The TKE is half the sum of the variances of the three wind components:

    TKE = ½ (σu² + σv² + σw²)

Assuming **isotropic turbulence**, the three standard deviations are equal, so

    σ = √(2 TKE / 3)

and the turbulence intensity at the same height and time is

    TI = σ / U

where U is the horizontal wind speed. TI is not given below 2 m/s.

## Limits

- **Anisotropy near the surface.** In the surface layer the streamwise fluctuations are larger
  than the vertical ones (typically σu : σv : σw ≈ 2.4 : 1.9 : 1.25 times the friction velocity).
  The isotropic σ then underestimates the streamwise σu, by about 20 % in neutral conditions.
  A LiDAR or cup anemometer TI is closer to the streamwise value.
- **Sub-grid turbulence only.** The TKE of the boundary layer scheme represents the turbulence
  the model does not resolve; fluctuations resolved on the grid and mesoscale variability are not
  included, while a measured 10-minute TI contains part of them.
- **Wind farms.** With the Fitch scheme the turbines add TKE (`windfarm_tke_factor`), so the TI
  in and behind a farm includes the turbine-added turbulence; compare with the run without
  turbines to see the farm's effect.

Every series and map of σ or TI carries these caveats in its metadata.

The tslist series have no TKE (WRF 4.8 writes none): no TI is given at the tslist points.
