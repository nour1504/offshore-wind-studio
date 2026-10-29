---
title: Tables des variables (Vtables)
section: Données d'entrée
order: 40
summary: Ce qu'est une Vtable, laquelle choisir, comment lire ses lignes, et quand écrire une table personnalisée.
related: input-sources, sst, input-data
---

Une **Vtable** indique à ungrib (WPS) quels enregistrements des fichiers GRIB extraire et sous
quel nom metgrid les connaîtra. WPS fournit une table par source de données courante dans
`ungrib/Variable_Tables` ; l'application contient les tables de WPS 4.7.0 pour que vous puissiez
les consulter et les vérifier sans installation de WPS. Un calcul avec une table standard utilise
la copie du WPS de la machine de calcul.

## Quelle table

| Données | Table |
|---|---|
| GFS, GDAS | `Vtable.GFS` |
| ERA5, ECMWF IFS | `Vtable.ECMWF` |
| Analyses de SST (OSTIA, RTG…) | `Vtable.SST` |
| CFSR, CFSv2 | `Vtable.CFSR` |
| NAM | `Vtable.NAM` |
| Modèle unifié du Met Office | `Vtable.UKMO_ENDGame` |
| DWD ICON (niveaux de pression) | `Vtable.ICONp` |

La page affiche les **champs produits** par la table choisie (TT, UU, VV, RH, GHT, PSFC, PMSL,
SKINTEMP, SST, LANDSEA, couches de sol…).

## Lire une ligne

```
GRIB1| Level| From |  To  | metgrid  | metgrid  | metgrid      |GRIB2|GRIB2|GRIB2|GRIB2|
Param| Type |Level1|Level2| Name     | Units    | Description  |Discp|Catgy|Param|Level|
-----+------+------+------+----------+----------+--------------+-----------------------+
  11 | 100  |   *  |      | TT       | K        | Temperature  |  0  |  0  |  0  | 100 |
```

- numéro de paramètre et type de niveau GRIB1, puis l'intervalle de niveaux (`*` = tous les
  niveaux de ce type) ;
- le nom, les unités et la description pour metgrid ;
- la discipline, la catégorie, le numéro de paramètre et le type de niveau GRIB2.

L'en-tête se termine par une ligne de tirets, et la table par une autre ligne de tirets ; le
texte placé après cette dernière ligne est une note ignorée par ungrib.

## Tables personnalisées

Choisissez **Table personnalisée…** pour adapter une table standard, par exemple pour ajouter un
champ présent dans vos fichiers, ou en retirer un dont la signification diffère. Partez de la
table standard la plus proche et modifiez ses lignes : l'application vérifie la présentation et
liste les champs produits. Le texte est enregistré dans le projet et écrit comme `Vtable` du
calcul.

Une table erronée n'échoue pas toujours : ungrib peut n'extraire aucun enregistrement pour un
champ sans erreur, et metgrid ou real.exe s'arrêtent ensuite faute d'un champ obligatoire.
Comparez les champs produits avec le contenu des fichiers.
