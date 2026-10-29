---
title: Période et données d'entrée
section: Données d'entrée
order: 10
summary: Ce dont WRF part, comment WPS prépare les données d'entrée, et ce que l'application vérifie avant un calcul.
related: period, input-sources, sst, vtables
---

WRF est un modèle à aire limitée : il lui faut un **état initial** de l'atmosphère, des sols et
de la mer au début de la période, et des **conditions aux frontières** autour de son domaine
extérieur pendant toute la période. Les deux viennent d'un modèle global ou d'une réanalyse.

## Comment les données arrivent jusqu'à WRF

1. **ungrib** (WPS) lit les fichiers GRIB et extrait les champs listés dans la table des
   variables ([Vtable](doc:vtables)) vers des fichiers intermédiaires, un par échéance, nommés
   `FILE:AAAA-MM-JJ_HH`. Un produit de température de surface de la mer séparé passe par un
   second passage d'ungrib sous le préfixe `SST` (voir [Température de surface de la mer](doc:sst)).
2. **geogrid** prépare les champs statiques de chaque domaine (relief, occupation du sol, sols)
   à partir des données géographiques (WPS_GEOG).
3. **metgrid** interpole horizontalement les fichiers intermédiaires sur les domaines : fichiers
   `met_em`.
4. **real.exe** interpole verticalement sur les niveaux de WRF et écrit l'état initial
   (`wrfinput`), le fichier de frontières (`wrfbdy`) et, si la mise à jour de la SST est active,
   le fichier `wrflowinp`.
5. **wrf.exe** effectue la simulation.

Le paquet exporté exécute ces étapes sur la machine de calcul : WPS une fois par année civile,
puis real et WRF fenêtre par fenêtre (voir [Exporter un calcul](doc:export)).

## Où sont les fichiers ?

Le paquet exporté contient un script de téléchargement dans `donnees/`. Pour un ordinateur
Linux, il télécharge dans le dossier des données du moteur (par exemple `/app/ows/donnees`),
commun à tous les calculs : une donnée déjà là n'est pas retéléchargée. Pour un cluster, il
télécharge dans `donnees/` du paquet. ERA5 utilise
`cdsapi` et votre accès CDS sur la machine de téléchargement. Pour vos propres
GRIB / NetCDF, choisissez au contraire le dossier dans **Période et données**.

Les `geo_em`, fichiers `FILE:*` / `SST:*` d'ungrib et `met_em` restent sur la machine de
calcul, dans le dossier `wps/` du paquet. Seules les sorties WRF importées reviennent dans
l'application.

## Choix de la page

- [Période](doc:period) : début et fin (UTC), pas de temps des données aux frontières, mise en
  route, sorties.
- [Source des données atmosphériques](doc:input-sources) : GFS ou ERA5 téléchargés par
  l'application, ou vos propres fichiers GRIB.
- [Température de surface de la mer](doc:sst) : issue des données atmosphériques ou d'un produit
  séparé, et sa mise à jour pendant les longs calculs.

## Vérifications avant un calcul

Avant l'export, l'application vérifie que la source couvre la
période, que le dossier existe et contient un format pris en charge (GRIB, ou NetCDF
ERA5/OSTIA sur une grille latitude-longitude régulière), que la table GRIB est valide et,
pour une SST séparée, qu'elle produit bien le champ
`SST`. Les problèmes sont listés sur la page, avec leur raison.

Les fichiers NetCDF compatibles sont convertis directement au format intermédiaire WPS :
la conversion remplace ungrib. Une Vtable identifie des codes GRIB ; elle ne convertit pas un
fichier NetCDF arbitraire. Les champs, unités, niveaux et dates requis restent vérifiés.
