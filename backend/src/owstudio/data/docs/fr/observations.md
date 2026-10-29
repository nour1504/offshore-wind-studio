---
title: Comparer les mesures et WRF
section: Observations
order: 50
summary: Importer des mesures (mâts, LiDAR, bouées) et les comparer aux simulations, aux mêmes endroits et aux mêmes heures.
related: getting-started, namelists, results
---

Importez CSV ou NetCDF et contrôlez les colonnes : date, fuseau horaire, site, hauteur et référence de hauteur, variable, unité, qualité et intervalle de moyenne. Les fichiers sources sont copiés avec leurs métadonnées ; les données originales ne sont pas modifiées.

Les séries sont harmonisées en UTC et dans les unités communes avant leur alignement. Les changements d'heure ambiguës doivent être résolus explicitement. Une direction nécessite une moyenne circulaire ; 359° et 1° ne donnent pas 180°.

Comparez des périodes, hauteurs et moyennes compatibles. Biais, RMSE et corrélation ne sont interprétables qu'avec couverture et nombre de paires valides. Les différences de résolution et la représentativité du LiDAR restent des limites physiques.

Référence officielle : [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

