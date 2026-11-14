---
title: Projection et coordonnées
section: Domaines
order: 50
summary: La projection de la carte de WRF (Lambert, Mercator…) et ses paramètres.
related: getting-started, namelists, results
---

`map_proj` choisit Lambert, Mercator, polaire ou latitude-longitude. `ref_lat` et `ref_lon` ancrent le domaine extérieur. `truelat1`, `truelat2` et `stand_lon` dépendent de la projection ; consulter WPS avant de les changer. Une latitude vraie est une latitude où la carte ne déforme pas les distances ; `stand_lon` est la longitude parallèle à l'axe y. WPS conseille de choisir la projection qui limite la déformation sur le domaine : une forte déformation (facteur de carte loin de 1) réduit le pas de temps possible. **Ajuster la projection au domaine** place les latitudes vraies au sixième du domaine depuis ses bords sud et nord et la longitude standard à son centre ; après un changement de la taille ou du pas de grille du domaine, **À ajuster** s'affiche tant que les paramètres ne sont pas ceux-là. Des paramètres saisis exprès ne sont pas signalés tant que le domaine ne change pas.

La carte utilise des degrés longitude/latitude pour l'affichage. Les distances de la grille WRF sont définies par sa projection. Le facteur de carte mesure la déformation locale. Une distance géographique n'est pas un indice de grille.

Référence officielle : [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

