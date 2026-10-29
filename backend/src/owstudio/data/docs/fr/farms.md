---
title: Parcs
section: Parcs éoliens
order: 50
summary: Créer des parcs, y placer des éoliennes et activer ou désactiver chacun pour le calcul.
related: turbines, coordinates, fitch, mav, results
---

Chaque parc a un identifiant stable, un nom et une liste de turbines. Désactiver un parc conserve son implantation mais retire son action dans le calcul. Sans paramétrisation de parc, aucune turbine n'agit sur WRF.

**Couleur** et **symbole** : cliquer le parc dans la liste (« + » : autre couleur). Par défaut,
chaque parc a ses propres repères. Sans effet sur les positions ni sur le calcul.

Quand les repères deviennent trop serrés, la carte affiche un contour léger et le nombre
exact d'éoliennes pour chaque parc. Sélectionnez le parc ou zoomez pour retrouver les repères
individuels. **Chaque éolienne** force leur affichage à toute échelle. Le contour relie les
positions extérieures : ce n'est ni une limite de concession ni une zone simulée.

Choisir un parc, puis **Clic carte** (un clic, une éolienne), **Une éolienne**, ou **Coller, générer** :

- **Coller** : nom ; latitude ; longitude ; modèle, une ligne par éolienne (Excel, fichier texte).
- **Zone** : un polygone dessiné sur la carte, rempli d'éoliennes.
- **Grille** : rangées × colonnes autour d'un centre placé sur la carte.
- **Fichier SIG** : GeoJSON, KML ou shapefile ; ses points, ou l'un de ses polygones rempli.

Réglages du placement : **Espacement** (le long d'une rangée), **Entre rangées**, **Orientation**
(sens horaire depuis l'est), **Disposition** (alignée, quinconce), **Marge au bord**. Le diamètre du rotor (D) est indiqué
sous chaque espacement. **Remplacer** remplace les éoliennes du parc ; **Ajouter** les garde. Les
coordonnées restent modifiables dans la table.

Pour mesurer les pertes dues aux sillages, comparez des calculs avec les mêmes données, dates et domaines. Une étude multi-parcs prévoit les sous-ensembles nécessaires : trois parcs donnent huit combinaisons, dont le calcul sans turbines. La production d'un parc seul, sa production avec un voisin et sa production avec tous les voisins permettent des comparaisons distinctes ; les effets ne s'additionnent pas toujours.

Référence officielle : [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

