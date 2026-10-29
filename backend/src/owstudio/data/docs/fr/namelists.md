---
title: Namelists et options avancées
section: Physique et namelists
order: 50
summary: Comment les namelists sont générées depuis le projet, et comment changer n'importe quelle option de WRF.
related: physics, input-data, domains, outputs
---

`namelist.wps` décrit la préparation des données ; `namelist.input` décrit l'initialisation et WRF. L'application les génère à partir du projet puis applique les valeurs de remplacement saisies dans l'éditeur.

Dans **Physique et namelists > Namelists**, choisissez `namelist.input` ou `namelist.wps`.
Chaque bloc présente les options du projet et s'ouvre à la demande. Dans **Ajouter une option**,
choisissez un groupe, puis recherchez l'option par son code ou son rôle. Le schéma WRF 4.8
détermine le type du champ, les valeurs par domaine et les défauts. Survolez le réglage pour
sa description et ses unités. Les options non documentées restent ajoutables par leur code.

Une valeur scalaire et une liste par domaine ne sont pas équivalentes. Une option valide
syntaxiquement peut encore être incompatible avec un autre choix.

Une valeur gérée par une autre page est verrouillée ici ; son lien ouvre le bon réglage.
Pour une option modifiable, votre valeur de remplacement est prioritaire.
**Annuler ma valeur** retire ce remplacement et rétablit la génération automatique.

**Importer** accepte un fichier existant ou du texte collé, avec des exemples et un aperçu
avant application au brouillon. Dans **Fichiers générés**, vérifiez la version finale avant
le calcul, puis copiez-la ou téléchargez-la. Pour une étude en fenêtres, l'aperçu présente la
première fenêtre calculée, la plus récente ; les autres dates sont adaptées automatiquement.

Référence officielle : [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

