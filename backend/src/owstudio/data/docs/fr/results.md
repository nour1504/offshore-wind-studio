---
title: Lire et exporter les résultats
section: Résultats
order: 50
summary: Lire la production, le vent aux points et les cartes d'un calcul, puis les exporter.
related: getting-started, namelists, results
---

Choisissez un calcul et son domaine. Les cartes et séries viennent des sorties effectivement disponibles ; les dates sont affichées en UTC. La hauteur au moyeu est interpolée depuis les niveaux avec la méthode indiquée. Les variables vectorielles sont tournées vers les axes géographiques.

EP est l'énergie sur la période calculée. Les facteurs de charge utilisent la durée couverte ; les trous ne sont pas assimilés à zéro. L'AEP nécessite une couverture annuelle suffisante et ne remplace pas une correction climatique à long terme.

Les sorties peuvent être agrégées par maille, parc ou turbine avec des hypothèses différentes. Consultez les notes de méthode et exportez les séries CSV pour garder les unités et métadonnées.

Référence officielle : [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

