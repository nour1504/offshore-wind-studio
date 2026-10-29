---
title: Imbrication des domaines
section: Domaines
order: 50
summary: Imbriquer des domaines plus fins : rapport d'affinement, placement dans le parent et marges.
related: getting-started, namelists, results
---

`parent_id` désigne le parent ; `i_parent_start` et `j_parent_start` placent le coin du nid dans les indices du parent. Le parent doit exister avant son enfant. Le nid doit rester dans son parent avec une marge aux bords.

Les dimensions doivent respecter `(e_we - 1) % parent_grid_ratio == 0`, et de même pour `e_sn`. L'interface propose des dimensions compatibles. Après une modification, contrôlez la carte et les points d'observation. Un pas de temps adapté est nécessaire sur tous les domaines.

Référence officielle : [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

