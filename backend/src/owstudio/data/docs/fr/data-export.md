---
title: Exporter les sorties
section: Résultats
order: 55
summary: Les sorties d'un calcul en CSV : les points tslist à chaque pas du modèle, ou une variable des wrfout en un point.
related: tslist, explorer, turbulence-intensity
---

L'onglet **Exporter** écrit les fichiers CSV du calcul choisi. Résultats, Explorateur, Analyses du vent et Mesures gardent leurs graphiques ; leur lien **Exporter** ouvre cet onglet déjà rempli.

**Points tslist** : les séries écrites par WRF à chaque pas de temps aux points de mesure (éoliennes, mâts).

- **Points** : les mailles qui portent des points. Les points d'une même maille ont la même série, écrite une fois.
- **Grandeurs** : toutes celles des fichiers tslist, aux hauteurs données au-dessus du sol, plus la TKE, l'intensité de turbulence, l'exposant de cisaillement et la rotation du vent entre la plus basse et la plus haute des hauteurs.
- **Moyenne** : chaque pas du modèle, ou des moyennes sur ]t - durée, t], datées de leur fin t. La TI vient de la TKE moyenne et de la vitesse moyenne, la direction des composantes moyennes, L de la moyenne de 1/L.
- **Disposition** : **En lignes**, une ligne par instant et par maille, avec ses points, son nombre d'éoliennes et leurs noms ; **En colonnes**, une ligne par instant, chaque grandeur d'une maille une fois, ses éoliennes dans le nom de la colonne.
- **Puissance** : `puissance_maille` est le POWER de WRF de toute la maille ; `puissance_eolienne` est ce POWER divisé par le nombre d'éoliennes de la maille (un seul type d'éolienne par maille). En colonnes, chaque éolienne a sa colonne. Sans paramétrisation des parcs, la puissance d'une éolienne vient de la courbe de puissance au vent du moyeu et la puissance de maille n'est pas donnée.
- Avec un calcul sans éoliennes importé, ses valeurs suivent, suffixées `_sans_parc`.

La TKE vient du fichier `.TK` d'un WRF compilé par l'installateur : QKE/2 avec MYNN, TKE_PBL avec MYJ, QNSE et BouLac. Les autres schémas de couche limite n'en ont pas : la TKE et la TI sont alors signalées non disponibles.

**Grille wrfout** : une variable des fichiers d'historique en un point (une éolienne, un point tslist ou une position), à chaque sortie, interpolée entre les quatre mailles voisines.

Chaque fichier commence par des lignes `#` : la source (tslist ou wrfout), le pas de temps, la moyenne, la période ]début, fin] en UTC et ce qui manque, avec la raison. Les unités sont dans le nom des colonnes.

Sous chaque graphique, la même mention donne la source et le pas des valeurs : « tslist, 10 min » ou « wrfout, 60 min ».
