---
title: Domaines WRF
section: Domaines
order: 50
summary: Placer les domaines de calcul : taille, résolution et projection de la zone simulée.
related: nesting, projection, namelists, turbines, outputs
---

Le domaine extérieur définit l'aire simulée. `dx` est le pas horizontal en mètres ; `e_we` et `e_sn` comptent les points dans chaque direction. La résolution d'un domaine imbriqué est celle de son parent divisée par `parent_grid_ratio`.

Les rubriques sont repliées au départ. Dans **Carte**, **Centrer sur** déplace uniquement la
vue. Pour déplacer un domaine, choisissez-le, activez **Placer sur la carte**, puis cliquez.
Dans **Domaines**, réglez la taille, le pas et l'imbrication. Une commande de placement dans
un domaine rouvre la carte.

Choisissez une projection adaptée à la région. Contrôlez le contour après un déplacement.
Gardez les parcs loin des frontières et prévoyez une zone amont suffisante. La résolution WRF
et le diamètre du rotor sont des échelles différentes : les turbines restent paramétrées
sous la maille.

Le pas de temps (`time_step`, en secondes) est l'avance de WRF à chaque étape de calcul. Règle habituelle : environ 5 s par km de maille de d01, 6 au plus. Plus grand, le calcul devient instable, et WRF arrête d01 au-delà de `reasonable_time_step_ratio` (6 par défaut) ; plus petit, il dure seulement plus longtemps. Chaque domaine imbriqué divise le pas de son parent par `parent_time_step_ratio`, égal à son affinement. Laissé automatique, le pas de temps suit la maille de d01 ; avec `use_adaptive_time_step`, WRF le choisit pendant le calcul.

`e_vert` règle le nombre de niveaux verticaux ; `p_top_requested` est la pression au sommet, en Pa. Le nombre de niveaux ne suffit pas à garantir une bonne résolution autour du rotor.

## Grille verticale et vue 3D

Ouvrez **Grille verticale** et choisissez le **calcul des niveaux** : **Automatiques** (real.exe
les calcule à partir de la 1re couche et de l'étirement, `auto_levels_opt = 2`) ou **À la main**
(vous tapez ou collez les niveaux eta pleins, `eta_levels`, de 1 au sol à 0 au sommet, strictement
décroissants ; leur nombre fixe `e_vert`). L'interface affiche le sommet en hPa et convertit en Pa
pour WRF.

Rien ne s'affiche quand tout va bien. Si real.exe refuserait les réglages (sommet non atteint,
couches du haut plus épaisses que 1,5 x `max_dz`, niveaux eta mal ordonnés ou en mauvais nombre,
d'après `dyn_em/module_initialize_real.F` de WRF 4.8), le problème s'affiche en rouge, en
mots-clés, avec la correction quand elle existe (déjà vérifiée par le même calcul que real.exe) et
le bouton **Appliquer** ; l'explication complète et la source sont dans l'infobulle.

### Conseils : les couches dans le rotor

Pour le schéma de parc de WRF (Fitch), les publications recommandent des couches fines à hauteur
des rotors :

- **environ 10 m dans les ~200 premiers mètres** : Tomaszewski & Lundquist (2020), *Geoscientific
  Model Development* 13, 2645-2662 (environ 7 niveaux dans un rotor de 77 m) ;
- **12 m au plus** pour retrouver la production mesurée : Lee & Lundquist (2017), *Geoscientific
  Model Development* 10, 4229-4244.

Avec les niveaux **automatiques**, les couches grossissent d'un niveau à l'autre (étirement) : on
s'en approche en diminuant la **1re couche** et l'**étirement**, mais sans pouvoir descendre à
10-12 m jusqu'à 200 m tout en atteignant le sommet, même avec 200 niveaux. Exemple calculé par le
logiciel, 51 niveaux et sommet à 50 hPa : réglages par défaut de WRF (1re couche 50 m,
étirement 1,3), couche la plus épaisse sous 200 m ≈ 103 m ; 1re couche 10 m et étirement 1,15,
≈ 35 m. Pour des couches plus fines encore, tapez les niveaux **à la main** (eta_levels) : la
colonne et le tableau des niveaux montrent aussitôt les hauteurs obtenues. Le schéma, la table des niveaux et la vue 3D restent accessibles dans leurs
rubriques ; la scène 3D n'est chargée que lorsqu'elle est ouverte.

Les hauteurs sont celles de l'**atmosphère de référence de WRF** (base state), calculées
avec les réglages verticaux et la coordonnée hybride du projet. Ce ne sont pas les hauteurs
météorologiques réelles d'un instant simulé : celles-ci varient avec la température.
La figure permet notamment de voir les niveaux et les rotors à la même échelle.

Dans la **Vue 3D**, les icônes au-dessus affichent ou masquent (nom au survol) : **Relief**,
**Niveaux**, **Rideau** (les couches sur une coupe verticale, du vert près de la mer au bleu en
altitude), **Couches des rotors** (celles traversées par les pales, en orange sur le rideau),
**Éoliennes**, **Air des parcs** (une colonne au-dessus de chaque parc, de la mer au haut des
pales). **Mailles**, un seul choix : aucune, au sol, ou sur chaque niveau affiché, jamais les deux.
Ce sont les vraies mailles du domaine affiché et, plus claires, celles des domaines imbriqués : sur
d01, on voit le raffinement de d02. Au-delà de 120 mailles par côté, une ligne sur N est tracée
(indiqué dans l'infobulle). Chaque parc porte une étiquette à son nom ; un clic dessus, ou le choix **Cadrer un
parc**, amène la caméra sur ce parc.

**Vue 3D > Relief** propose deux sources. **Géographie** : un fichier `geo_em` du domaine ou
un dossier qui contient une géographie WPS_GEOG ; un dossier parent est accepté. Champ vide :
géographie du moteur. **Tuiles publiques** : relief téléchargé sur Internet, avec la
bathymétrie ; sans accès Internet, la géographie est utilisée. Sans aucune source, le relief
est plat. La ligne **Relief** indique la source utilisée et, dépliée, son chemin et les
erreurs éventuelles. Le fichier `geo_em` doit correspondre au domaine (numéro, maille,
dimensions, coordonnées).
Ces choix de visualisation ne modifient pas les fichiers WRF.

Référence officielle : [WRF User Guide](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/) · [WPS](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/wps.html) · [WRF Physics](https://www2.mmm.ucar.edu/wrf/site/documentation/users_guide/physics.html).

