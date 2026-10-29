---
title: Paramétrisation Fitch
section: Parcs éoliens
order: 50
summary: Le schéma de Fitch : comment WRF représente la traînée et la turbulence des éoliennes, et ce qu'il exige (MYNN).
related: getting-started, namelists, results
---

`windfarm_opt=1` représente la traînée et la production de turbulence des turbines à une échelle inférieure à la maille. Le guide WRF exige MYNN (`bl_pbl_physics=5`). Les positions, hauteurs, diamètres et courbes de puissance/poussée doivent être cohérents.

`POWER` est agrégé par maille. La répartition entre turbines est reconstruite avec la méthode du module énergie et ses hypothèses ; elle ne constitue pas une mesure individuelle de chaque rotor. La documentation de méthode et les notes du résultat indiquent les approximations.

Référence officielle : [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

