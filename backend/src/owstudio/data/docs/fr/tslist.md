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

1. Activer **Enregistrer des points de mesure**.
2. Choisir une série par éolienne, par maille contenant des éoliennes, ou aucune série
   automatique. Régler le nombre de niveaux verticaux conservés.
3. Pour ajouter un mât, un LiDAR ou une bouée, cliquer sur **Placer sur la carte**, puis à
   l'endroit voulu. Renseigner le nom et vérifier les coordonnées dans la fenêtre qui s'ouvre,
   puis valider. **Saisir les coordonnées** et **Importer une liste** sont les autres méthodes.
4. Les points nommés apparaissent sur la carte et dans la liste à côté, où ils se modifient
   ou se retirent. La synthèse sépare les points automatiques des points ajoutés et permet
   d'ouvrir l'aperçu `tslist`.

Le préfixe identifie les fichiers et doit être unique. Les noms et préfixes ont des limites
WRF ; le formulaire les vérifie. **Voir un exemple** illustre le format d'une liste importée.

Le point est associé à une maille WRF. La position demandée et la position de cette maille peuvent différer. L'extraction conserve cette information, la hauteur et la méthode. Les séries à haute fréquence peuvent produire un gros volume ; s'en tenir aux points et niveaux utiles.

L'onglet **Exporter** donne ces séries en CSV : points, grandeurs, hauteurs, moyenne, période ]début, fin] en UTC, valeurs sans éoliennes à côté ([Exporter les sorties](doc:data-export)).

Le fichier TS donne les valeurs de surface de WRF : température et vapeur d'eau à 2 m, vent à 10 m, pression en surface, flux. Le vent et la température à une hauteur viennent des profils (UU, VV, TH, PR sur les niveaux du modèle, hauteurs dans PH), interpolés linéairement ; T = θ (p / p₀)^(Rd/cp).

Un WRF compilé par l'installateur du logiciel écrit en plus, à la fin de chaque ligne du fichier TS, 1/L (RMOL), le nombre de Richardson global (BR), la vitesse de frottement (UST), la hauteur de couche limite (PBLH) et la puissance des éoliennes de la maille (POWER, en kW ; 0 sans paramétrisation des parcs), et un profil de plus, TK (la TKE à chaque niveau : QKE/2 avec MYNN, TKE_PBL avec MYJ, QNSE et BouLac ; valeur manquante avec les autres schémas). Le logiciel y lit la stabilité, la turbulence et la puissance ; le WRF 4.8 d'origine ne les écrit pas.

La puissance d'une éolienne est le POWER de WRF de sa maille à chaque pas, divisé par le nombre d'éoliennes de la maille : un seul type d'éolienne par maille, vérifié par le projet. Sans POWER dans le fichier TS, c'est la formule de la paramétrisation de Fitch elle-même, recalculée à chaque pas sur les profils de la maille (vent au moyeu, correction d'induction pour les n éoliennes de la maille) : elle retombe sur le POWER des fichiers d'historique. Sans éoliennes, c'est la courbe de puissance au vent libre.

Référence officielle : [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

