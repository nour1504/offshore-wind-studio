---
title: Stockage et nettoyage
section: Stockage
order: 50
summary: Où l'application range ses fichiers, la place qu'ils prennent et comment faire le ménage.
related: compute, input-data, results
---

Paramètres affiche les dossiers de projets/calculs, cache de la carte, observations, exports, vidéos, rapports et journaux. Chaque calcul conserve sa configuration et ses sorties dans son propre dossier. Vous pouvez définir des dossiers alternatifs pour les catégories de données.

Ces bases sont celles de l'ordinateur de l'application. Les dossiers Linux du moteur — données
d'entrée et WPS_GEOG — se règlent dans **Calcul**, profil par profil. « Données téléchargées »
montre et vide le dossier des données d'entrée du moteur, sous-dossiers compris. Un clic sur
une ligne affiche ses fichiers. Les sous-dossiers des
calculs sont créés automatiquement ; il n'y a pas de chemin distinct à saisir pour chaque
`geo_em`, `met_em` ou `wrfout`.

Le nettoyage affiche ce qu'il retire. Les fichiers d'entrée peuvent être communs à plusieurs études ; supprimer des sorties empêche leurs analyses. Sauvegardez les données utiles avant une suppression. Le désinstalleur conserve vos projets et données.

Les données WSL sont sur le disque local lorsqu'elles sont dans un VHDX local, même accessibles via un partage réseau Windows. Le logiciel ne supprime jamais ces disques virtuels.

Référence officielle : [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

