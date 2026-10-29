---
title: Paramétrisation MAV
section: Parcs éoliens
order: 50
summary: Le schéma MAV : sillages sous la maille, choix du modèle de sillage et de leur superposition.
related: getting-started, namelists, results
---

`windfarm_opt=2` ajoute une représentation des sillages sous-maille et de leur superposition. `windfarm_wake_model` choisit Jensen (1), XA (2), GM (3), Jensen+XA (4) ou les trois (5). `windfarm_overlap_method` règle la superposition des sillages Jensen/XA (1 à 4).

Comparer Fitch et MAV est une étude de sensibilité : conserver les mêmes entrées, période et implantation. Les estimations de production individuelle restent limitées par les sorties réellement écrites par WRF.

Référence officielle : [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

