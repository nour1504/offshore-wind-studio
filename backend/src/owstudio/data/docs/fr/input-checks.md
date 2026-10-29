---
title: Contrôle de vos fichiers d'entrée
section: Données d'entrée
order: 25
summary: Ce que l'application lit dans vos fichiers GRIB ou NetCDF avant un calcul, et les problèmes qu'elle signale : champs ou échéances manquants, trop peu de niveaux, zone trop petite pour le domaine.
related: input-sources, vtables, sst, period
---

Avant un calcul, et à la demande avec **Examiner les fichiers** sur la page Données,
l'application lit vos fichiers et vous dit ce que WPS y trouvera. Le but est d'arrêter une
configuration qui échouerait des heures plus tard dans ungrib, metgrid ou real.exe, et
d'expliquer pourquoi.

## Ce qui est lu

Pour les fichiers **GRIB**, seulement les en-têtes des messages : paramètre, niveau, date, grille.
Les données elles-mêmes sont sautées : même un gros dossier est lu rapidement, et le résultat est
gardé tant qu'aucun fichier ne change. Les dates sont calculées comme ungrib les calcule
(échéances de prévision, champs moyennés valables à la fin de leur période). Chaque message est
ensuite confronté à votre **Vtable** avec les règles d'ungrib lui-même, ce qui donne les champs et
niveaux qu'ungrib extraira et les messages qu'il ignorera.

Pour les fichiers **NetCDF**, les variables, leurs unités, niveaux, échéances et grille.

Le résultat liste les fichiers, le centre producteur (ECMWF, NCEP…), la grille et son pas, la
première et la dernière échéance et leur espacement, chaque champ avec son nombre de niveaux et
d'échéances, les niveaux de pression et les couches de sol. Pour les fichiers GRIB, les Vtables
standard sont classées selon leur capacité à lire les fichiers.

## Erreurs : le calcul échouerait

- **Un champ indispensable à metgrid ou real.exe** : température et vent sur les niveaux de
  pression (obligatoires dans METGRID.TBL de metgrid), humidité, pression de surface ou au niveau
  de la mer, température du sol sur au moins deux niveaux pour les modèles de surface comme Noah
  (real.exe s'arrête sans elles).
- **La première ou la dernière échéance de la période manque** (GRIB) : ungrib s'arrête avec
  « Data not found ». Avec des fichiers NetCDF, une échéance hors des dates des fichiers.
- **Un champ indispensable absent à certaines échéances** alors que d'autres champs y sont.
- **Le sommet du modèle au-dessus des données** : real.exe a besoin de données jusqu'au sommet
  du modèle (`p_top_requested`, 50 hPa par défaut).
- **Le domaine extérieur dépasse la zone des données** : metgrid ne peut pas interpoler hors de
  la grille des données.
- **Aucun message ne correspond à la Vtable**, une Vtable illisible par ungrib, des fichiers
  endommagés ou incomplets (téléchargement interrompu), un dossier mêlant GRIB et NetCDF.
- **Fichiers SST** : pas de champ SST, ou des échéances SST qui n'atteignent pas le début et la
  fin de la période.

## Avertissements : le calcul fonctionnerait, peut-être mal

- Des échéances manquantes entre la première et la dernière : interpolées linéairement dans le
  temps.
- Moins de 10 niveaux de pression : une interpolation verticale grossière.
- Des champs non indispensables mais utiles : hauteur géopotentielle, température de surface
  (skin), masque terre-mer, température à 2 m, vent à 10 m, altitude du relief de la source,
  humidité du sol.
- Un domaine extérieur à moins de deux pas de grille du bord des données, où metgrid se replie
  sur des interpolations plus simples.

## Contrôles rapides pendant la saisie

Pendant que vous modifiez le cas, les dossiers pas encore examinés ne sont lus que jusqu'à 1 Go ;
les dossiers plus gros sont signalés « pas encore examinés » et sont lus entièrement
tout de suite avec **Examiner les fichiers**.
