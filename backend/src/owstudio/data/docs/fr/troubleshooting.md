---
title: Comprendre les erreurs
section: Dépannage
order: 50
summary: Trouver la cause d'un calcul en erreur, étape par étape (ungrib, metgrid, real, WRF).
related: getting-started, namelists, results
---

Commencez par l'étape en erreur et la fin de son journal. Pour ungrib : format GRIB, Vtable, champs, échéances et place libre (ungrib ne signale pas un disque plein ; `run_wps.sh` le vérifie avant et après). Pour metgrid : couverture géographique, niveaux/champs et chemins de fichiers. Pour real : sols, frontières, niveaux et topographie. Pour WRF : pas de temps/CFL, schémas compatibles, ressources MPI et espace disque.

Le fond de carte et les tuiles d'altitude utilisent les certificats du système, comme `wget`. Derrière un proxy d'entreprise, l'autorité de certification du proxy doit y être installée.

Un arrêt faute de mémoire ou de disque demande d'abord de revoir le volume et les ressources. Ne supprimez pas un disque WSL pour corriger une namelist. Les entrées et sorties sont localisées dans Paramètres. Exportez le journal et la configuration du calcul avant de demander de l'aide.

Référence officielle : [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

