---
title: Analyses du vent et stabilité
section: Analyses
order: 50
summary: Roses des vents, distributions de Weibull, profils et stabilité calculés à partir des sorties, et comment les lire.
related: getting-started, namelists, results
---

Les roses utilisent la direction météorologique **d'où vient le vent**, en degrés depuis le nord vrai. Les distributions et Weibull portent sur les échantillons valides de la période sélectionnée. Le nombre d'échantillons et les trous doivent accompagner leur interprétation.

Les profils, cisaillement, veer et jets dépendent des niveaux réellement disponibles. La stabilité est classée par la longueur d'Obukhov L (RMOL = 1/L écrit par WRF dans les fichiers d'historique, sinon tirée des flux de surface), selon les seuils de Gryning et al. (2007), Boundary-Layer Meteorology 124 : neutre pour |L| ≥ 500 m, instable pour L < 0, stable pour L > 0. Le Richardson bulk compare température potentielle virtuelle et cisaillement sur deux hauteurs ; ce n'est pas le Richardson gradient.

Les diagnostics disponibles et leurs exigences sont indiqués dans l'explorateur et les fiches de variables. Un champ manquant est signalé, jamais remplacé par un résultat inventé.

Les analyses portent sur une éolienne : la série tslist de sa maille, lue en moyennes sur 10 minutes de tous les pas de temps du modèle (direction tirée des composantes moyennes).

**Production** : pour chaque intervalle de 10 minutes des sorties tslist, la puissance moyenne de l'éolienne et la direction moyenne du vent au moyeu sur cet intervalle ; l'énergie de l'intervalle (puissance moyenne × 10 min) est rangée dans le secteur de cette direction. Même traitement pour le calcul sans éoliennes, d'où les pertes de sillage par secteur.

**Courbe de puissance** : la puissance de WRF de l'éolienne à chaque instant de sortie, face au vent libre au même instant (le vent à hauteur de moyeu, au même point, dans les sorties tslist du calcul sans éoliennes ; sans ce calcul, pas de courbe), rangée par classes de 0,5 m/s (méthode des classes de la norme IEC 61400-12-1). Cp = P / (½ ρ A U³), ρ = 1,23 kg/m³ comme dans WRF. La table de l'éolienne est tracée à côté ; une éolienne dans le sillage des autres passe sous la table.

Référence officielle : [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

