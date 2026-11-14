---
title: Fichiers WRF
section: Calculs
order: 50
summary: Exporter les fichiers WPS/WRF à exécuter sur la machine de calcul, puis importer les sorties.
related: export, independent-windows, results
---

La page **Fichiers WRF** prépare le paquet de fichiers et de scripts qui exécute WPS puis WRF
sur un cluster ou un ordinateur Linux. L'application ne lance pas les simulations elle-même.

## Préparer puis exécuter

1. Enregistrer le projet.
2. Dans **Fichiers WRF**, choisir le mode **Cluster (Slurm)** ou **Ordinateur Linux** et
   renseigner les chemins, les sources météo et les ressources de cette machine.
3. Examiner les contrôles et l'aperçu. **Extraire tous les fichiers** et **Télécharger le zip**
   créent le même paquet ; aucune simulation n'est lancée par ces actions.
4. Suivre le `LISEZ-MOI.txt` du paquet pour préparer les données, exécuter WPS, puis WRF.

Le paquet fonctionne sans l'application. Son moteur et ses données doivent être présents sur
la machine de calcul. Le [guide de l'export](doc:export) détaille les commandes et les fichiers.

Les fenêtres démarrent à froid, avec un spin-up à chaque fois, sans reprise d'une autre
fenêtre. Elles sont calculées de la dernière à la première dans le même dossier. Le plan,
les dates et l'ordre viennent de la méthode commune ; un changement de période demande un
nouvel export. Les sorties `wrfout` couvrent **[début, fin]**, les séries **]début, fin]**.

## Importer les résultats

Dans **Résultats et énergie → Importer des sorties**, choisir le paquet exécuté ou son
sous-dossier `wrf/`, avec son `manifest.json`. Le dossier de référence sans éoliennes est
facultatif et provient d'un second paquet. Un dossier parent est accepté s'il ne
contient qu'un calcul. « Vérifier » affiche les fichiers à importer. L'import se fait par copie
ou par lien sur le même disque. Un lien partage le contenu : ne pas
modifier les fichiers liés.
