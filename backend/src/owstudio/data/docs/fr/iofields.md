---
title: Fichier iofields
section: Sorties
order: 50
summary: Ajouter ou retirer des variables des fichiers de sortie wrfout avec le fichier iofields.
related: getting-started, namelists, results
---

Pour le flux historique 0, `+:h:0:NOM` ajoute une variable et `-:h:0:NOM` la retire. Les noms doivent correspondre au Registry et la variable doit être allouée par la configuration physique.

Ajouter un nom n'invente pas un champ absent du schéma sélectionné. Consultez la fiche de la variable et les journaux WRF. Retirer un champ indispensable peut empêcher une analyse ultérieure.

Référence officielle : [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

