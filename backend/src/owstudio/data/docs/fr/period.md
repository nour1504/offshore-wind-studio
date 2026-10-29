---
title: Période, mise en route et sorties
section: Données d'entrée
order: 15
summary: Période utile UTC, mise en route unique, durée et regroupement des fenêtres de calcul.
related: input-data, input-sources, outputs, independent-windows
---

## Début et fin

Les heures sont en **UTC**, comme dans les données d'entrée et dans WRF. Le début doit être une
échéance présente dans les données d'entrée (pour GFS et la configuration ERA5 habituelle : 00,
06, 12 ou 18 UTC).

## Données aux frontières toutes les…

`interval_seconds` dans les deux namelists : le pas de temps des données d'entrée, qui fixe aussi
la fréquence à laquelle WRF reçoit de nouvelles conditions aux frontières. Il doit correspondre
aux fichiers (voir [Sources](doc:input-sources)).

## Une seule mise en route S

La période du projet est la période utile **[D, F]**. Le réglage **Mise en route** (bloc
**Fenêtres de calcul**), noté S, s'applique à chaque simulation, même si l'étude tient dans une seule fenêtre.
Par défaut S vaut 12 h ; les choix 6/12/24 h et une autre durée restent disponibles.
Le modèle commence S heures avant le début utile pour ajuster son état initial à sa grille
et à sa physique. Ces heures sont simulées puis écartées ; il n'y a pas un second réglage de
mise en route pour les statistiques.

## Fréquence des sorties

`history_interval` (minutes) des fichiers d'historique (`wrfout`), qui contiennent les champs 3D
complets : un intervalle court donne des cartes et des animations plus fluides mais occupe
beaucoup de disque. Les séries temporelles écrites aux éoliennes et aux mâts (tslist) le sont à
**chaque pas de temps du modèle**, quel que soit cet intervalle.

Cet intervalle se règle dans **Sorties > Cartes complètes**. Il est distinct du pas de temps
des données aux frontières et du pas de temps numérique de WRF, réglé dans **Domaines**.

## Fenêtres indépendantes

La **durée d'une fenêtre** L vaut 72 h par défaut. Une période de durée inférieure ou égale à
L donne un seul calcul. Au-delà, **Ranger les sorties par** choisit comment les sorties sont
rangées avant d'être assemblées sur toute la période : par mois, par 3 mois (trimestre civil),
par semaine (lundi 00 h UTC) ou par fenêtre. Chaque rangement est découpé depuis sa fin : sa
fenêtre la plus courte vient donc au début. Une fenêtre ne déborde jamais d'un rangement sur
l'autre.

Chaque fenêtre repart de nouveaux fichiers produits par `real.exe`, puis de `wrf.exe`,
avec `restart = .false.`. L'ordre de calcul est **antichronologique**, de la fenêtre la plus
récente à la plus ancienne. Les données météo doivent couvrir **D − S à F**, arrondis aux instants des données.

**Toute durée** est possible (10 minutes comme une année) : les fichiers météo n'existent qu'à certaines heures (toutes les 6 h avec GFS, toutes les heures avec ERA5) ; real.exe prépare donc d'un instant des données à l'autre (la mise en route part de l'instant d'avant, et dure au moins S ; la préparation va jusqu'à l'instant d'après la fin) et wrf.exe s'arrête pile à la fin voulue (`run_*`, prioritaire sur `end_*` d'après README.namelist). L'intervalle des sorties doit diviser la période.

L'escalier de **Fenêtres de calcul** montre une marche par fenêtre, de la première date à la
dernière ; la mise en route est la bande hachurée avant chaque marche (jamais gardée). De loin,
les marches sont regroupées par mois ou par année ; la molette, le glisser et les boutons +, −
zooment et se déplacent. L'infobulle d'une marche donne ses dates et son rang dans l'ordre de
calcul (de la dernière fenêtre à la première).
Voir le [protocole détaillé](doc:independent-windows).

## Fenêtres indépendantes ou enchaînées

- **Indépendantes** (par défaut) : ce qui précède.
- **Enchaînées** : les mêmes fenêtres forment une seule simulation continue. Une seule mise en
  route, avant la première ; calcul **chronologique** ; chaque fenêtre repart (`restart = .true.`)
  du `wrfrst` écrit à la fin de la précédente (`restart_interval` = sa durée). Seul le dernier
  `wrfrst` est gardé. Sorties gardées, assemblage et import : identiques.

Exemple, 2016, L = 72 h, S = 12 h : indépendante, la fenêtre du 29 mars part du 28 mars 12 h ;
enchaînée, elle reprend au 29 mars 00 h, là où la précédente s'est arrêtée. Dans l'escalier, la
mise en route (bande hachurée) n'apparaît alors qu'avant la première marche.
