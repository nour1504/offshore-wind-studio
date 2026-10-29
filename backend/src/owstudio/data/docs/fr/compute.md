---
title: Profils de calcul locaux
section: Calcul
order: 50
summary: Utiliser WRF/WPS sous Windows avec WSL dédié ou directement sous Linux.
related: engine-install, export, storage
---

Un profil indique où est le moteur WRF/WPS de cet ordinateur. **Calcul** propose deux environnements :

- **Windows · WSL dédié** : la distribution `OffshoreWindStudio-WRF`, utilisateur `owstudio`.
- **Linux · installation locale** : le Linux qui exécute l’application.

**Installer un moteur** configure le profil après vérification de WRF/WPS.
Pour une installation existante, ouvrez **Options avancées > Décrire un moteur installé à la main**.
L’enregistrement du profil ne lance ni installation ni calcul. Le profil sert à installer et
vérifier le moteur ; la vue 3D y lit la géographie (WPS_GEOG).

## Dossiers

Les chemins du profil sont des chemins Linux. WRF, WPS et WPS_GEOG désignent les programmes
et la géographie. Un dossier parent est accepté : **Vérifier** et les scripts utilisent le bon
sous-dossier et l'indiquent. Le dossier des données d'entrée (GFS, ERA5) est commun à tous les
calculs. Les scripts y téléchargent les données et ungrib les y lit. Il doit être accessible en
écriture.

Un chemin changé ici passe aussi dans **Fichiers WRF** et dans le nettoyage de **Stockage**.
L'inverse non : un chemin changé à la main dans Fichiers WRF ne vaut que pour ces fichiers.

Un moteur installé avant la version 0.6.2 garde ses données dans le moteur (`<moteur>/input`).
**Calcul** l'affiche (« Dans le moteur (avant 0.6.2) ») : **Déplacer vers …** les met dans le
dossier partagé à côté du moteur, sans rien télécharger de nouveau.
Les dossiers locaux de l’application se règlent séparément dans **Paramètres**.

**Vérifier** contrôle les programmes et les chemins, sans simulation.

Pour préparer des fichiers et scripts à exécuter ailleurs, consultez [Exporter un calcul](doc:export).
