---
title: Séries temporelles WRF
section: Sorties
order: 50
summary: Activer les séries, placer un point nommé sur la carte et vérifier le fichier tslist.
related: outputs, coordinates, namelists
---

`tslist` est le fichier qui donne à WRF les points où écrire des séries à chaque pas de temps
et des profils. Ces points de mesure sont virtuels, dans la simulation.

Dans **Sorties > Points de mesure** :

1. Activez **Enregistrer des points de mesure**.
2. Choisissez une série par éolienne, par maille contenant des éoliennes, ou aucune série
   automatique. Réglez le nombre de niveaux verticaux conservés.
3. Pour ajouter un mât, un LiDAR ou une bouée, cliquez sur **Placer sur la carte**, puis à
   l'endroit voulu. Renseignez le nom et vérifiez les coordonnées dans la fenêtre qui s'ouvre,
   puis validez. **Saisir les coordonnées** et **Importer une liste** sont les autres méthodes.
4. Retrouvez vos points nommés sur la carte et dans la liste à côté ; vous pouvez les modifier
   ou les retirer. La synthèse sépare les points automatiques des points ajoutés et permet
   d'ouvrir l'aperçu `tslist`.

Le préfixe identifie les fichiers et doit être unique. Les noms et préfixes ont des limites
WRF ; le formulaire les vérifie. **Voir un exemple** illustre le format d'une liste importée.

Le point est associé à une maille WRF. La position demandée et la position de cette maille peuvent différer. L'extraction conserve cette information, la hauteur et la méthode. Les séries à haute fréquence peuvent produire un gros volume ; limitez points et niveaux utiles.

Dans **Résultats > Points de mesure**, **Exporter en CSV** donne le tableau du point choisi : grandeurs cochées, valeurs sans éoliennes à côté, période ]début, fin] en UTC, moyennes sur la durée choisie.

Le fichier TS donne les valeurs de surface de WRF : température et vapeur d'eau à 2 m, vent à 10 m, pression en surface, flux. Le vent et la température à une hauteur viennent des profils (UU, VV, TH, PR sur les niveaux du modèle, hauteurs dans PH), interpolés linéairement ; T = θ (p / p₀)^(Rd/cp). La puissance des éoliennes est celle du schéma de Fitch, recalculée à chaque pas avec sa propre formule sur les profils de la maille (vent au moyeu, correction d'induction pour les n éoliennes de la maille) : elle retombe sur le POWER des fichiers d'historique. Sans éoliennes, c'est la courbe de puissance au vent libre.

Référence officielle : [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

