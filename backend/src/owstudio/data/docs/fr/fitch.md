---
title: Paramétrisation Fitch
section: Parcs éoliens
order: 50
summary: La paramétrisation de Fitch : comment WRF représente la traînée et la turbulence des éoliennes, et ce qu'elle exige (MYNN).
related: getting-started, namelists, results
---

`windfarm_opt=1` représente la traînée et la production de turbulence des éoliennes à une échelle inférieure à la maille. Le guide WRF exige MYNN (`bl_pbl_physics=5`). Les positions, hauteurs, diamètres et courbes de puissance/poussée doivent être cohérents.

`POWER` est la puissance de toutes les éoliennes d'une maille. La puissance d'une éolienne est ce POWER divisé par le nombre d'éoliennes de la maille (un seul type d'éolienne par maille) : ce n'est pas une mesure de chaque rotor.

Référence officielle : [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

