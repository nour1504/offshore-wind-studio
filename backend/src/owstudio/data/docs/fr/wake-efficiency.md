---
title: Production et pertes de sillage
section: Résultats
order: 50
summary: Comment la production et les pertes de sillage sont calculées, par rapport à la référence sans éoliennes.
related: getting-started, namelists, results
---

Importez le calcul sans éoliennes comme tout autre calcul (un dossier par import), puis choisissez-le en haut de Résultats, dans « Sans éoliennes » : un calcul de ce projet ou d'un autre projet, sur la même grille. Le choix se change à tout moment.

Le calcul sans turbines fournit le vent de référence. Sa conversion en puissance utilise les mêmes turbines et la même méthode que le calcul avec parcs. La perte vaut production de référence moins production avec sillage ; le pourcentage est relatif à la référence.

Une valeur négative peut survenir localement ; ne la tronquez pas automatiquement. Avec le schéma de Fitch et `windfarm_induction = 1`, WRF ne prend pas le vent de la maille tel quel : il le divise par (1 − a)ⁿ, n étant le nombre d'éoliennes de la maille, pour retrouver le vent d'avant leur ralentissement. Quand une maille porte beaucoup d'éoliennes, cette correction dépasse le vent libre : sur une maille de 3 km à 28 éoliennes, le vent de la maille vaut 9,9 m/s, le vent sans éoliennes 11,1 m/s, et la puissance corrigée dépasse de 4 % celle du vent libre (sans la correction, la perte serait de 21 %). Le gain vient de la correction, pas d'une accélération réelle. Le mélange de plusieurs turbines ou parcs dans une maille limite la séparation individuelle. Les études multi-parcs séparent les effets de voisins et leurs interactions à partir de combinaisons réellement calculées.

La méthode par courbe et la méthode POWER WRF ne sont pas interchangeables. Elles sont identifiées dans chaque résultat.

Référence officielle : [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

