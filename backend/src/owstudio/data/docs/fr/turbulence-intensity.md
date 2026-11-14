---
title: Intensité de turbulence à partir de la TKE
section: Analyses
order: 30
summary: Comment l'écart type du vent dans son axe et l'intensité de turbulence sont déduits de l'énergie cinétique turbulente de WRF, et les limites de cette estimation.
related: analyses, results, mynn
---

WRF n'écrit pas d'intensité de turbulence. Avec le schéma de couche limite MYNN
(`bl_pbl_physics = 5`), il écrit `QKE`, le double de l'énergie cinétique turbulente (TKE) ;
avec MYJ, QNSE et BouLac, `TKE_PBL`, la TKE elle-même. L'application en déduit la turbulence.

## Formules

La TKE est la demi-somme des variances des trois composantes du vent :

    TKE = ½ (σu² + σv² + σw²)

σu est l'écart type dans l'axe du vent, σv en travers, σw sur la verticale. Avec les rapports
entre composantes de la norme IEC 61400-1 (modèle de Kaimal), σv = 0,8 σu et σw = 0,5 σu :

    TKE = ½ σu² (1 + 0,8² + 0,5²) = 0,945 σu²

    σu = √(TKE / 0,945)

et l'intensité de turbulence à la même hauteur et au même instant vaut

    TI = σu / U

où U est la vitesse horizontale du vent. La TI n'est pas donnée en dessous de 2 m/s.

Jusqu'à la version 0.7.3, la turbulence était supposée isotrope, σ = √(2 TKE / 3) : σ et TI
sont 26 % plus hauts depuis la version 0.7.4.

## Aux points tslist

Un WRF compilé par l'installateur du logiciel écrit un profil de plus par point, le fichier
`.TK` : la TKE à chaque niveau, QKE/2 avec MYNN, TKE_PBL avec MYJ, QNSE et BouLac, valeur
manquante avec les autres schémas. La TKE y est interpolée à la hauteur demandée, comme le
vent. Sur 10 minutes, la TKE et la vitesse sont moyennées d'abord :

    σu = √(TKE moyenne / 0,945)        TI = σu / U moyenne

Le fichier `.QK` de la version 0.7.4 (QKE de MYNN) est encore lu. Sans l'un ni l'autre (WRF 4.8
d'origine), la TI vient des fichiers wrfout, à leurs instants de sortie.

## Limites

- **Rapports fixes entre les composantes.** σv / σu et σw / σu changent avec la stabilité et la
  hauteur ; 0,8 et 0,5 sont les valeurs de la norme.
- **Turbulence sous-maille uniquement.** La TKE du schéma de couche limite représente la
  turbulence que le modèle ne résout pas ; les fluctuations résolues sur la grille et la
  variabilité de méso-échelle n'y sont pas, alors qu'une TI mesurée sur 10 minutes en contient
  une partie.
- **Parcs éoliens.** Avec la paramétrisation de Fitch, les éoliennes ajoutent de la TKE
  (`windfarm_tke_factor`) : la TI dans le parc et dans son sillage inclut la turbulence ajoutée
  par les éoliennes ; la comparaison avec le calcul sans éoliennes montre l'effet du parc.

Chaque série et chaque carte de σu ou de TI porte ces réserves dans ses métadonnées.
