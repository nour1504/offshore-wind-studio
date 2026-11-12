---
title: Lire et exporter les résultats
section: Résultats
order: 50
summary: Lire la production, le vent aux points et les cartes d'un calcul, puis les exporter.
related: analyses, data-export, wake-efficiency
---

Choisir un calcul et son domaine. Les cartes et séries viennent des sorties effectivement disponibles ; les dates sont affichées en UTC. La hauteur au moyeu est interpolée depuis les niveaux avec la méthode indiquée. Les variables vectorielles sont tournées vers les axes géographiques.

L'énergie est celle de la période utile. Les facteurs de charge utilisent la durée couverte ; les trous ne sont pas comptés pour zéro.

La puissance et l'énergie viennent des sorties tslist aux éoliennes quand elles existent (moyennes sur 10 minutes), sinon du POWER de WRF des fichiers wrfout (intégration par trapèzes entre les instants de sortie). La source est écrite en bas à gauche de la page.

L'énergie se lit par parc, par maille ou par éolienne : la puissance d'une éolienne est celle de sa maille divisée par le nombre d'éoliennes de la maille. Le lien **Exporter** d'un graphique ouvre l'onglet [Exporter](doc:data-export) : ses fichiers CSV gardent les unités, la source et la moyenne.

Référence officielle : [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

