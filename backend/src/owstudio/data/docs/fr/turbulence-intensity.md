---
title: Intensité de turbulence à partir de la TKE
section: Analyses
order: 30
summary: Comment l'écart type du vent et l'intensité de turbulence sont déduits de l'énergie cinétique turbulente de WRF, sous l'hypothèse d'une turbulence isotrope, et les limites de cette estimation.
related: analyses, results, mynn
---

WRF n'écrit pas d'intensité de turbulence. Avec le schéma de couche limite MYNN
(`bl_pbl_physics = 5`), il écrit `QKE`, le double de l'énergie cinétique turbulente (TKE), et
l'application en déduit la turbulence.

## Formules

La TKE est la demi-somme des variances des trois composantes du vent :

    TKE = ½ (σu² + σv² + σw²)

En supposant la **turbulence isotrope**, les trois écarts types sont égaux, donc

    σ = √(2 TKE / 3)

et l'intensité de turbulence à la même hauteur et au même instant vaut

    TI = σ / U

où U est la vitesse horizontale du vent. La TI n'est pas donnée en dessous de 2 m/s.

## Limites

- **Anisotropie près de la surface.** Dans la couche de surface, les fluctuations dans l'axe du
  vent sont plus fortes que les fluctuations verticales (typiquement σu : σv : σw ≈ 2,4 : 1,9 :
  1,25 fois la vitesse de frottement). Le σ isotrope sous-estime alors le σu dans l'axe du vent,
  d'environ 20 % en conditions neutres. La TI d'un LiDAR ou d'un anémomètre à coupelles est plus
  proche de la valeur dans l'axe du vent.
- **Turbulence sous-maille uniquement.** La TKE du schéma de couche limite représente la
  turbulence que le modèle ne résout pas ; les fluctuations résolues sur la grille et la
  variabilité de méso-échelle n'y sont pas, alors qu'une TI mesurée sur 10 minutes en contient
  une partie.
- **Parcs éoliens.** Avec le schéma de Fitch, les éoliennes ajoutent de la TKE
  (`windfarm_tke_factor`) : la TI dans le parc et dans son sillage inclut la turbulence ajoutée
  par les éoliennes ; comparez avec le calcul sans éoliennes pour voir l'effet du parc.

Chaque série et chaque carte de σ ou de TI porte ces réserves dans ses métadonnées.

Les séries tslist n'ont pas de TKE (WRF 4.8 n'en écrit pas) : aucune TI n'est donnée aux points tslist.
