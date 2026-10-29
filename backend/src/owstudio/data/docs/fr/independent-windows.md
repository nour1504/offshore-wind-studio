---
title: Fenêtres de calcul et mise en route
section: Calculs
order: 51
summary: Une mise en route S avant chaque fenêtre, blocs découpés depuis leur fin et calcul antichronologique.
related: period, input-data, outputs, results, export
---

Dans **Période et données**, la période du projet est la période utile **[D, F]**. La mise en
route S vaut 12 h par défaut et la durée utile maximale L vaut 72 h. Ces deux valeurs sont
réglables. Une étude de durée inférieure ou égale à L donne une seule simulation de D − S à F.

## Découpage et ordre

Au-delà de L, les sorties sont rangées par mois calendaires, par trimestres civils (3 mois),
par semaines commençant le lundi à 00 h UTC, ou par fenêtre (réglage **Ranger les sorties
par**), puis assemblées sur toute la période. Ce rangement forme les blocs du calcul. Chaque bloc est découpé depuis sa fin : la fenêtre la plus courte
se trouve au début. Les heures utiles d'une fenêtre ne traversent pas une limite de bloc.

Chaque fenêtre simule de son début utile − S à sa fin utile, à froid : `real.exe`, puis
`wrf.exe`, sans restart de la précédente. Le calcul est **antichronologique** : les blocs et
leurs fenêtres les plus récents sont calculés en premier. La référence sans éoliennes suit
les mêmes dates et le même protocole. L'escalier montre les mises en route et les heures gardées ;
l'infobulle de chaque marche donne son rang dans cet ordre de calcul.

## Préparation WPS et sorties

Les données météo doivent couvrir D − S à F. WPS est préparé par année civile, chaque passage
commençant S heures avant le début de sa partie utile. Tous les `met_em` sont réunis dans le
même dossier, y compris pour une fenêtre traversant le 1er janvier.

Chaque fenêtre conserve **]début utile, fin utile]**. Les fichiers d'historique finaux couvrent
**[D, F]**, avec le fichier de D ; les séries temporelles couvrent **]D, F]**. Avec un fichier
`wrfout` par instant (`frames_per_outfile = 1`), les fenêtres calculées ensuite remplacent les
fichiers de mise en route des fenêtres plus récentes. Il reste ainsi le bon instant utile,
sans doublon. Les fichiers antérieurs à D sont mis à part.

L'export garde le plan dans `plan_fenetres.csv` et les conventions dans `manifest.json`.
Consultez l'[aide à l'export](doc:export) pour les scripts et les dossiers du calcul.

Au-delà de quelques jours, une simulation libre s'écarte de la réalité (elle dérive) : d'où des
fenêtres de 72 h au plus, chacune repartant des données météo. C'est le **protocole d'étude**
exporté ; WRF lui-même n'impose pas cette limite. Le guide officiel décrit aussi les simulations longues et les reprises. Ni ce découpage ni un pas de temps usuel ne garantissent la stabilité : examinez les vérifications, la physique, les domaines, les conditions aux limites et les journaux CFL.

Références : [exécution de WRF](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/running_wrf.html), [physique et simulations longues](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html#long-simulations).
