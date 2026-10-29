---
title: Fichiers et scripts WPS/WRF
section: Calculs
order: 5
summary: Préparer, exporter, exécuter puis importer les résultats.
related: period, independent-windows, input-data, tslist, results
---

## Préparer

Enregistrez le projet, puis ouvrez **Fichiers WRF**.
Choisissez **Cluster (Slurm)** ou **Ordinateur Linux**. Les rubriques sont fermées au départ.

- **Dossiers des programmes** : chemins Linux de WRF, WPS et WPS_GEOG sur la machine de calcul.
  Un dossier parent est accepté. Les scripts cherchent le sous-dossier qui contient
  `main/wrf.exe`, `geogrid.exe` ou le relief de la résolution choisie (`topo_gmted2010_30s`
  ou `topo_gmted2010_5m`) et l'écrivent dans leur journal. La page affiche « Dossier
  utilisé ».
- **Fichiers d'entrée** : motif de chaque source ; `%Y` représente l'année. ERA5-Land et la SST
  séparée restent des sources distinctes.
- **Processus** : WRF et geogrid/metgrid ; ungrib utilise toujours un seul processus.
- **En-tête Slurm** : ressources du cluster, durée, partition et environnement. Le mode éditeur
  permet de saisir les directives `#SBATCH` ; `{job}` est remplacé par le nom du calcul.
- **Fichiers** : aperçu du contenu exact. Corrigez les erreurs avant l'export ; les avertissements
  sur un pas de temps non divisible ne changent pas votre pas de temps.

**Extraire tous les fichiers** crée un nouveau sous-dossier dans le dossier choisi.
**Télécharger le zip** produit le même contenu, avec les droits d'exécution des scripts.
Les fichiers texte utilisent ASCII et des fins de ligne LF, y compris depuis Windows.

## Exécuter

Le paquet fonctionne sans Offshore Wind Studio. Il faut WRF/WPS, leurs bibliothèques et les
données d'entrée sur la machine de calcul. Lisez d'abord son `LISEZ-MOI.txt` : ses dates,
chemins et noms de scripts correspondent au projet exporté.

1. Préparez les données avec le script fourni dans `donnees/`, ou vos fichiers existants.
   Sur un ordinateur Linux, il télécharge dans le dossier des données du moteur, commun à
   tous les calculs ; ungrib lit au même endroit.
   ERA5 utilise `cdsapi` et votre accès CDS sur la machine de téléchargement.
2. Depuis `wps/`, lancez `run_wps.sh` : `bash run_wps.sh` sur un ordinateur,
   `sbatch run_wps.sh` sur un cluster. Avant ungrib, il vérifie la place libre (environ 3 fois
   la taille d'un fichier GRIB par instant) ; après, qu'il y a un fichier par instant. Sinon il
   s'arrête avec la raison au lieu de laisser metgrid échouer plus loin.
3. Quand WPS est fini, depuis `wrf/`, lancez `run_wrf.sh` de la même façon. C'est le seul
   script WRF, le même sur un cluster et sur un ordinateur (seul son en-tête change) : toutes
   les fenêtres, les séries rangées par mois (ou trimestre, semaine, fenêtre), puis
   l'assemblage de la période.

S'il s'arrête (échec, coupure), relancez la même commande : il reprend à la fenêtre suivante.
Sur un cluster, avant chaque fenêtre, il vérifie qu'il lui reste le temps de la finir avant la
limite du calcul (`--time`) ; sinon il se soumet de nouveau et le nouveau calcul reprend à la
fenêtre suivante. Vous n'avez rien à découper vous-même.

WPS passe une fois par année civile, avec la marge de mise en route. Tous les `met_em` vont
dans `wps/met_em/`. Les fenêtres WRF partent à froid, de la dernière à la première, dans le
même dossier. `plan_fenetres.csv` et `manifest.json` enregistrent le plan.
Un changement de période demande un nouvel export.

## Récupérer les résultats

Gardez le paquet et son `manifest.json`. Les `wrfout` couvrent **[début, fin]** ; les séries
de `wrf/tslist_periode/` couvrent **]début, fin]**, en heures depuis le début de l'étude.
Les sorties de mise en route sont mises à part dans `wrf/mise_en_route/`.

Dans **Résultats et énergie → Importer des sorties**, choisissez le paquet ou son dossier
`wrf/`. Pour une référence sans éoliennes, utilisez un second paquet produit sans parc simulé
et renseignez le dossier de référence. Vérifiez l'aperçu, puis importez par copie ou par lien.
Un lien sur le même disque partage les fichiers : une modification affecte les deux chemins.

Les moyennes de dix minutes utilisent des intervalles UTC **]t − 10 min, t]**, datés à leur
fin. Chaque valeur est constante sur le pas qui la précède ; un intervalle incomplet est
écarté. La vitesse est moyennée après calcul de sa norme, la direction depuis les composantes
moyennes.
`POWER` est une puissance par maille ; une valeur par éolienne est une reconstruction.

Ni l'ouverture d'une page ni l'export ne lancent une simulation.
