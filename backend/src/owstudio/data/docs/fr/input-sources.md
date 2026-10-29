---
title: Sources des données atmosphériques
section: Données d'entrée
order: 20
summary: GFS et ERA5 téléchargés par le script du paquet exporté, ou vos propres fichiers GRIB ou NetCDF (convertis à l'export).
related: input-data, input-checks, vtables, sst, era5-access
---

## GFS (NOAA)

Analyses du Global Forecast System du NCEP à 0,25°, toutes les 6 heures, téléchargées depuis
l'archive publique de la NOAA sur Amazon Web Services (sans compte). L'archive commence le
1er janvier 2021. Un fichier contient tous les champs d'une échéance (environ 500 Mo).
L'application utilise les analyses (échéance 0) et la table `Vtable.GFS` de WPS.

## ERA5 (Copernicus)

Cinquième réanalyse de l'ECMWF à 0,25°, disponible depuis 1940 et publiée avec environ cinq
jours de retard. L'application demande un jour à la fois au Climate Data Store de Copernicus
(CDS), sur niveaux de pression et niveaux uniques, sur votre domaine extérieur plus une marge de
2°, au format GRIB, et la lit avec `Vtable.ECMWF`. Il faut :

- un compte CDS gratuit et sa clé d'API, saisie dans **Paramètres** (voir [Accès à ERA5](doc:era5-access)) ;
- les licences ERA5 acceptées une fois sur le site du CDS.

## Vos propres fichiers (GRIB ou NetCDF)

Choisissez **Mes propres fichiers** quand vous avez déjà les données : ERA5 téléchargé depuis le
CDS (en GRIB ou en NetCDF), sorties d'un autre modèle global ou régional, archive opérationnelle.
Indiquez :

- le **dossier** sur cet ordinateur et un **motif** de fichiers (`*.grib`, `era5-*`…). Les
  sous-dossiers sont inclus. « Afficher les fichiers » montre les fichiers trouvés, que les
  scripts exportés utilisent aussi ;
- la **table des variables** (Vtable) qui indique à ungrib quels enregistrements extraire
  (`Vtable.ECMWF` pour ERA5, `Vtable.GFS` pour GFS… ou une table personnalisée, voir
  [Vtables](doc:vtables)).

La page liste les fichiers trouvés avec leur format, et **Examiner les fichiers** montre ce qui
en sera lu : champs, niveaux de pression, échéances, grille et zone couverte, avec les problèmes
qui arrêteraient WPS ou WRF (voir [Contrôle de vos fichiers d'entrée](doc:input-checks)).

ungrib (WPS) ne lit **que les éditions 1 et 2 du GRIB**. Un dossier de **fichiers NetCDF** (format
de téléchargement par défaut du nouveau CDS, ou analyses SST OSTIA) est converti par
l'application, sur cet ordinateur et avant le calcul, en fichiers intermédiaires WPS identiques à
ceux qu'ungrib aurait écrits : mêmes noms de champs, unités et niveaux, mêmes champs dérivés
(géopotentiel en hauteur, humidité à 2 m depuis le point de rosée, équivalent en eau de la neige,
masque terre-mer en 0/1). La Vtable n'est alors pas utilisée. Pris en charge : ERA5 sur niveaux
de pression et niveaux uniques, dans les présentations actuelle et ancienne du CDS (valeurs
compactées et dimension `expver` ERA5/ERA5T comprises), et analyses SST sur grilles
latitude-longitude régulières. Les fichiers convertis sont écrits dans le paquet exporté (voir ci-dessous). Un dossier ne doit contenir qu'un seul des deux formats.

### Où le paquet exporté lit vos fichiers

- **GRIB** : les scripts exportés lancent ungrib sur la machine de calcul ; indiquez le dossier
  Linux de vos fichiers dans les « PARAMÈTRES DE BASE » en tête des scripts (ou un chemin Linux
  absolu dans le logiciel, repris tel quel).
- **NetCDF** : ungrib ne lit que le GRIB. À l'export, le logiciel convertit vos fichiers sur cet
  ordinateur en fichiers intermédiaires de WPS, rangés dans `wps/intermediaires/<source>/` du
  paquet, pour tous les instants des passages de WPS (mise en route comprise). Le script WPS
  saute alors ungrib pour cette source : il relie ces fichiers sous les noms qu'ungrib leur
  aurait donnés (`FILE:2025-10-01_00`) et metgrid les lit. Le dossier doit être sur cet
  ordinateur au moment de l'export ; l'export peut prendre quelques minutes pour une longue
  période.

## Pas de temps des données aux frontières

Le réglage **Données aux frontières toutes les** (`interval_seconds`) doit correspondre au pas de
temps des fichiers : 6 h pour les analyses GFS, 6 h ou moins pour ERA5 (le script de téléchargement
prend ERA5 à ce pas). Avec vos propres fichiers GRIB, la première et la dernière échéance de la période
doivent figurer dans les fichiers : sinon ungrib s'arrête (« Data not found ») ; une échéance
manquante entre les deux est interpolée linéairement à partir de ses voisines (WPS
`ungrib/src/datint.F`), ce que les contrôles signalent. Avec des fichiers NetCDF, toute échéance
du calcul située entre deux échéances des fichiers est interpolée de la même façon.
