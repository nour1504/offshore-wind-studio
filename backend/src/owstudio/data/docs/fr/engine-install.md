---
title: Installer le moteur WRF/WPS
section: Calcul
order: 40
summary: Installer WRF/WPS sous Windows avec WSL dédié ou dans un dossier Linux choisi.
related: compute, export, getting-started
---

**Calcul > Installer un moteur** installe et vérifie WRF/WPS. Rien n’est installé au démarrage.
Seule la cible correspondant au système qui exécute l’application est disponible.

## Choisir l’emplacement

- **Windows · WSL dédié** : choisissez le dossier Windows qui recevra le disque de la
  distribution `OffshoreWindStudio-WRF` (Ubuntu 24.04, utilisateur `owstudio`). Une distribution
  dédiée déjà présente est réutilisée à son emplacement actuel. Activer WSL peut demander une
  autorisation administrateur et un redémarrage. Les autres distributions ne sont pas modifiées.
- **Linux · installation locale** : choisissez le **dossier d’installation du moteur** dès le
  premier écran. Il peut se trouver hors du dossier personnel, si vous disposez des droits
  d’écriture. Utilisez un dossier Linux absolu, dédié, sans espaces ni `..`.

Le dossier par défaut est `~/OffshoreWindStudioEngine/wrf4.8.0-wps4.7.0-gnu13-v1`.
Un dossier non vide étranger à l’installateur est refusé.

## Contenu

| Composant | Version |
|---|---|
| WRF officiel, em_real, GNU, dmpar | 4.8.0, commit `06d4240ae9` |
| WPS officiel, GNU, dmpar, GRIB1/GRIB2 | 4.7.0, commit `5feccecd63` |
| GNU C/C++/Fortran | 13.3.0 |
| OpenMPI | 4.1.6 |
| NetCDF C / Fortran | 4.9.2 / 4.6.1 |

Les bibliothèques conda-forge sont installées avec le moteur. zlib, libpng et JasPer proviennent
des sources WPS. Le profil conserve les versions effectivement installées et leur manifeste.

## Géographie et espace

- **Haute résolution** : paquet officiel NCAR, 29 Go une fois décompressé (2,8 Go à
  télécharger). Prévoyez environ 45 Go avec le moteur.
- **Basse résolution** : 0,5 Go décompressé (150 Mo à télécharger), réservée aux tests et à
  l’enseignement.

Les boutons donnent la taille décompressée. Une géographie déjà sur la machine est choisie
d’elle-même (la haute résolution d’abord) : rien n’est téléchargé.
- **Dossier WPS_GEOG existant** : indiquez son chemin Linux ; aucune géographie n’est téléchargée.

La géographie téléchargée ou envoyée va à côté du moteur, dans `geog/WPS_GEOG` ou
`geog/WPS_GEOG_LOW_RES` (moteur dans `/app/ows/moteur` : `/app/ows/geog/...`). Les données
d’entrée vont dans `donnees/`, au même niveau.

Les compléments dépendent des options physiques utilisées. L’assistant les propose ; les
vérifications du projet signalent ceux qui manquent. Les archives contrôlées sont supprimées
après décompression.

## Vérifier et installer

**Vérifier la cible** contrôle système, outils, place disponible, accès internet et dossier.
**Installer le moteur** télécharge puis compile : généralement 20 minutes à 2 heures selon
la connexion et le processeur. Le suivi reste accessible dans **Installations de moteurs**.
Une reprise conserve les étapes terminées ; l’annulation cible uniquement cette installation.
Un dossier qui contient déjà ce moteur est dit sous **Dossier** : il est gardé, rien n’est
recompilé. Un arrêt est dit en quelques mots (disque plein, réseau, NCAR bloqué, compilation…) ;
le détail est dans **Journal**.

La vérification finale porte sur les sources, exécutables, bibliothèques, MPI, NetCDF et index
géographiques. Le profil est configuré après succès. Aucune donnée météo ni simulation ne fait
partie de l’installation. La recette vise Linux x86_64, glibc 2.17 ou plus récent.

Pour exécuter une étude sur une autre infrastructure, utilisez les [fichiers et scripts exportés](doc:export).
