---
title: Variables et fréquence des sorties
section: Sorties
order: 50
summary: Distinguer les séries en des points choisis des cartes complètes, puis régler fréquence et variables.
related: tslist, iofields, results
---

La page **Sorties** sépare deux usages :

- **Points de mesure** : des points virtuels où suivre la météo à chaque pas de temps WRF.
  Choisissez les points des éoliennes et ajoutez vos propres emplacements sur la carte
  (voir [Séries temporelles WRF](doc:tslist)).
- **Cartes complètes** : les champs sur tous les domaines, enregistrés dans les fichiers
  `wrfout`, pour les cartes et les animations.

Dans **Cartes complètes**, **Écrire toutes les** règle `history_interval`, en minutes.
Une fréquence plus élevée augmente le volume et permet des graphes et vidéos plus fins.
Une vidéo ne crée pas de nouvelles sorties ni de résolution physique. Ce réglage ne change
pas la fréquence des séries aux points.

Ajoutez ou retirez des variables dans le flux historique avec `iofields`. Les diagnostics demandent certains champs : vent tridimensionnel et géopotentiel pour le vent au moyeu, flux/UST ou RMOL pour Monin–Obukhov, TKE pour certaines estimations de turbulence. L'explorateur distingue disponible, dérivable et impossible.

L'estimation d'espace est indicative et dépend des champs écrits, des niveaux, de la compression et des fichiers restart.

Les variables WRF standard restent présentes tant que vous ne les retirez pas. Les listes
d'ajout/retrait, les suggestions et l'aperçu `iofields.txt` se trouvent dans **Cartes complètes**.
Les sorties importées se trouvent dans le dossier des projets (voir **Paramètres > Stockage**).

Référence officielle : [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

