---
title: Physique et dynamique
section: Physique et namelists
order: 50
summary: Régler la physique par rubrique, accéder aux options avancées et vérifier les fichiers générés.
related: namelists, mynn, fitch, mav
---

La page comporte deux onglets, avec les rubriques fermées au départ :

- **Namelists** : choisissez `namelist.input` ou `namelist.wps`, puis ouvrez un bloc.
  **Physique** regroupe turbulence, nuages, rayonnement et surface ; **Dynamique** contient
  les réglages de l'écoulement. Les choix portent leur nom usuel, avec une valeur par domaine
  lorsque nécessaire. **Ajouter une option** donne accès aux autres options WRF.
- **Fichiers générés** : les fichiers finaux à vérifier, copier ou télécharger.

Les schémas de microphysique, rayonnement, surface, couche limite et convection forment une
configuration cohérente. Certaines options sont définies par domaine. Les schémas de parc
imposent des contraintes de compatibilité, notamment MYNN pour Fitch.

**Préréglage en mer** compare les valeurs proposées aux réglages actuels avant application.
C'est un point de départ : le choix scientifique dépend de la région, de la résolution et
de la période. Le nudging et les autres options avancées restent dans
l'[éditeur des namelists](doc:namelists).

Les dates, le maillage, les parcs et les sorties se règlent sur leurs pages respectives.
Les liens des options gérées ailleurs permettent de les retrouver sans ressaisir les valeurs.

Référence officielle : [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

