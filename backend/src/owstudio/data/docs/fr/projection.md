---
title: Projection et coordonnées
section: Domaines
order: 50
summary: La projection de la carte de WRF (Lambert, Mercator…) et ses paramètres.
related: getting-started, namelists, results
---

`map_proj` choisit Lambert, Mercator, polaire ou latitude-longitude. `ref_lat` et `ref_lon` ancrent le domaine extérieur. `truelat1`, `truelat2` et `stand_lon` dépendent de la projection ; consulter WPS avant de les changer.

La carte utilise des degrés longitude/latitude pour l'affichage. Les distances de la grille WRF sont définies par sa projection. Le facteur de carte mesure la déformation locale. Ne confondez pas une distance géographique avec un indice de grille.

Référence officielle : [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

