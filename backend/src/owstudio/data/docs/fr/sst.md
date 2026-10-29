---
title: Température de surface de la mer
section: Données d'entrée
order: 30
summary: Pourquoi la SST compte en mer, les produits SST séparés (OSTIA, RTG, SST d'ERA5), comment WPS les combine avec les données atmosphériques, et la mise à jour de la SST pendant les longs calculs.
related: input-data, input-sources, vtables
---

## Pourquoi c'est important

En mer, l'écart entre la température de surface de la mer et la température de l'air fixe la
stabilité des basses couches : une mer plus froide que l'air stabilise l'écoulement, ce qui
augmente le cisaillement du vent et prolonge les sillages ; une mer plus chaude rend l'écoulement
instable et mélange plus vite les sillages. Une erreur de 1 K sur la SST modifie sensiblement la
stabilité simulée.

## Issue des données atmosphériques (par défaut)

WRF utilise la température de surface de la mer contenue dans les données atmosphériques : le
champ `SST` quand la table des variables en extrait un (ERA5 avec `Vtable.ECMWF`), sinon la
température de peau sur l'eau (`SKINTEMP`, comme avec GFS).

## Un produit SST séparé

Choisissez **Fichiers SST séparés** pour utiliser une analyse dédiée (OSTIA, RTG, la SST d'une
autre source) avec son propre dossier, son motif de fichiers et sa table des variables
(`Vtable.SST` par défaut, qui extrait le seul champ `SST`). L'application :

- exécute **ungrib une seconde fois** sur ces fichiers avec le préfixe `SST` (namelist `&ungrib`
  `prefix = 'SST'`), en conservant les fichiers `FILE:` du premier passage ;
- règle `fg_name = 'FILE', 'SST'` dans `&metgrid`. metgrid lit les sources dans cet ordre et une
  source placée après a la priorité pour un champ présent dans les deux
  (WPS `metgrid/src/process_domain_module.F`) : la SST séparée remplace donc celle des données
  atmosphériques.

ungrib comble les échéances manquantes entre deux enregistrements disponibles par interpolation
linéaire dans le temps (WPS `ungrib/src/ungrib.F`, appel à `datint`) : un produit SST journalier
convient pour des échéances aux frontières de 6 heures. Les fichiers doivent cependant **couvrir
le début et la fin de la période** : un enregistrement au début ou avant, et un à la fin ou après,
sur les pas de temps des données aux frontières (avec des données toutes les 6 heures, une analyse
à 00, 06, 12 ou 18 UTC). Quand les échéances SST ne tombent pas exactement au début et à la fin,
l'application élargit la période du passage SST d'ungrib jusqu'aux échéances SST qui les
encadrent (`namelist.wps.sst`), pour qu'ungrib interpole chaque échéance du calcul ; le calcul
garde sa propre période.

Les analyses SST au format **NetCDF** (OSTIA du Copernicus Marine Service, la SST d'ERA5…) sont
converties sur cet ordinateur en fichiers intermédiaires `SST:` aux échéances aux frontières du
calcul, interpolées linéairement entre les analyses, sur le domaine extérieur et une marge ; le
passage SST d'ungrib n'est alors pas nécessaire. Les valeurs absentes sur terre sont écrites comme
manquantes (-1e30), comme ungrib le fait pour les champs GRIB munis d'un masque (bitmap).

## Mise à jour de la SST pendant le calcul

Sans mise à jour, WRF conserve la SST de l'instant initial pendant tout le calcul, ce qui reste
acceptable sur quelques jours mais pas sur des semaines ou des mois. Avec **Mettre à jour la SST
pendant le calcul**, l'application règle, conformément au `README.namelist` de WRF :

- `sst_update = 1` dans `&physics` : real.exe écrit la SST, la glace de mer (XICE), l'albédo et la
  fraction de végétation à chaque échéance aux frontières dans les fichiers `wrflowinp_d<nn>`, et
  WRF les lit pendant le calcul ;
- `auxinput4_inname = "wrflowinp_d<domain>"`, `auxinput4_interval` (minutes, par domaine) et
  `io_form_auxinput4 = 2` dans `&time_control`. L'intervalle suit par défaut celui des données aux
  frontières, comme le conseille le README (« generally matches time given by interval_seconds »).

Le `README.namelist` recommande `usemonalb = .true.` (albédo mensuel) avec la mise à jour de la
SST : les vérifications vous le rappellent s'il n'est pas réglé dans Physique.

L'application prévient lorsqu'un calcul de plus de cinq jours n'a pas de mise à jour de la SST.
