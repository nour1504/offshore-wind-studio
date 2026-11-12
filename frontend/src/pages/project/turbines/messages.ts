import { defineMessages } from "../../../i18n";

/** Texts of the turbine models page and its parts. */
export const messages = defineMessages({
  en: {
    addCatalog: "Add from the catalog",
    addBlank: "Create a type",
    blankName: "Custom turbine {n}",
    copyName: "{name} (copy)",
    unnamed: "Unnamed type",
    typeN: "Type {n}",
    list: {
      notDefined: "Not defined",
      emptyTitle: "No turbine type",
      emptyText:
        "Add a type from the catalog or create one from curves.",
    },
    builtIn: {
      fallbackName: "WRF generic 2 MW",
    },
    missing: {
      text:
        "{count|# turbine uses|# turbines use} type {n}, not defined in the project. Define it or assign another type.",
      blank: "Start from a blank curve",
    },
    editor: {
      name: "Name",
      rated: "Rated power",
      ratedInfo:
        "Maximum electrical power. Used to check the curve and for the capacity factor.",
      rotor: "Rotor diameter",
      rotorInfo:
        "Diameter swept by the blades. A larger rotor gives a stronger wake.",
      hub: "Hub height",
      hubInfo:
        "Hub height above the sea. WRF applies the drag on the model levels between hub − radius and hub + radius.",
      standing: "Standing thrust coefficient",
      standingInfo:
        "Ct of the stopped turbine, used outside the curve (below cut-in, above cut-out). Typical value: 0.05 to 0.15.",
      duplicate: "Duplicate",
      delete: "Delete",
      deleteTitle: "Delete type {n} ({name})?",
      deleteText: "The type is removed from the project. No turbine uses it.",
      inUse: "Used by {count|# turbine|# turbines}: give them another type before deleting this type.",
      restore: "Restore WRF's table",
      restoreTitle: "Restore WRF's table for type 1?",
      restoreText:
        "Type 1 definition removed: type 1 turbines use the generic 2 MW WRF table again.",
    },
    rows: {
      farms: "Farms",
      turbines: "{n|turbine|turbines}",
      spacing: "Grid spacing {d} D",
      specific: "{w} W/m²",
      maxCp: "Cp max {cp}",
    },
    use: {
      ready: "Type ready. Next step: place the turbines in Wind farms.",
      goFarms: "Place the wind farms",
      label: "Use model {n} for every turbine of {farm}",
      assign: "Assign",
    },
    metrics: {
      specificInfo:
        "Rated power divided by swept area. Below about 300 W/m², the rotor is large for its power: rated power is reached at lower wind speeds and the capacity factor is higher.",
      maxCpHint: "{ws} m/s · Betz {betz}",
      maxCpInfo:
        "Cp = P / (½ ρ A U³), ρ = 1.225 kg/m³. Betz limit: 16/27. Above it, check the power unit and the rotor diameter.",
      rated: "Rated wind speed",
      ratedHint: "{cutIn} → {cutOut} m/s",
      ratedInfo:
        "Read on the curve: cut-in = first speed with power, rated = first speed at rated power, cut-out = last speed with power.",
      gridHint: "{dx} km · {domain} · {min} D at least",
      gridInfo:
        "WRF README.windturbine: grid spacing of at least 5 rotor diameters. Below that, the wind-farm parameterization assumptions no longer hold.",
    },
    problems: {
      errors: "To fix",
      warnings: "To check",
      tooFew: "The curve needs at least two rows.",
      notFinite: "Empty or unreadable values: {rows|row #|rows #}.",
      negative: "Values cannot be negative: {rows|row #|rows #}.",
      notIncreasing:
        "Speeds not strictly increasing: {rows|row #|rows #}. Correct or sort the table.",
      characteristics: "Rated power, rotor diameter and hub height must be greater than zero, and the standing thrust coefficient zero or more.",
      betz:
        "The power coefficient exceeds the Betz limit (16/27 ≈ 0.593) at {speeds} m/s: check that power is in kW and that the rotor diameter is right.",
      aboveRated: "The curve exceeds the rated power by more than 5 % (maximum {max} kW).",
      belowRated:
        "The curve does not reach the rated power (maximum {max} kW for {rated} kW). Check the unit (kW) or the rated power.",
      ctBelowCp:
        "Ct below Cp at {speeds} m/s, physically impossible. Power and Ct columns swapped?",
    },
    curve: {
      add: "Add a row",
      sort: "Sort by wind speed",
      paste: "Paste",
      points: "Points",
      speed: "Wind speed",
      power: "Power",
      ct: "Ct",
      cp: "Cp",
      speedRow: "Wind speed, row {n}",
      powerRow: "Power, row {n}",
      ctRow: "Thrust coefficient, row {n}",
      removeRow: "Remove row {n}",
      tableLabel: "Curve of type {n}",
    },
    charts: {
      power: "Power curve",
      powerLabel: "Power (kW) against wind speed (m/s)",
      coefficients: "Thrust and power coefficients",
      coefficientsLabel: "Thrust coefficient Ct and power coefficient Cp against wind speed (m/s), with the Betz limit",
      powerSeries: "Power",
      ctSeries: "Thrust coefficient Ct",
      cpSeries: "Power coefficient Cp",
      betz: "Betz limit 16/27",
    },
    paste: {
      help:
        "Paste from a spreadsheet: wind speed (m/s), power, Ct, one row per speed. Separators: tab, semicolon or space. Decimal comma accepted. With a header line, columns can come in any order. WRF wind-turbine-N.tbl files are accepted.",
      label: "Rows to read",
      file: "Read a file",
      unit: "Power in",
      read: "{n|# row read|# rows read}, from {from} to {to} m/s, up to {max} kW in the table.",
      wrf: "WRF table recognized: hub height, rotor diameter, standing Ct and rated power replaced too.",
      setRated: "Also set the rated power to the curve maximum ({mw} MW)",
      replace: "Replace the curve",
      empty: "Paste at least two rows.",
      tooFew: "At least two rows are needed.",
      line: "Line {line} unreadable: “{text}”. Expected: wind speed, power, Ct.",
      fileError: "The file could not be read.",
    },
    wrf: {
      title: "WRF table",
      description:
        "The file WRF reads for this type, written with each run as wind-turbine-{n}.tbl when an enabled farm uses it. Line 1: number of rows; line 2: hub height (m), rotor diameter (m), standing thrust coefficient, rated power (MW); then wind speed (m/s), Ct and power (kW) on each row.",
      download: "Download",
      fixFirst: "Fix the errors of the type to see its WRF table.",
      label: "Content of wind-turbine-{n}.tbl",
    },
  },
  fr: {
    addCatalog: "Ajouter depuis le catalogue",
    addBlank: "Créer un type",
    blankName: "Éolienne personnalisée {n}",
    copyName: "{name} (copie)",
    unnamed: "Type sans nom",
    typeN: "Type {n}",
    list: {
      notDefined: "Non défini",
      emptyTitle: "Aucun type d'éolienne",
      emptyText:
        "Ajouter un type du catalogue ou le créer à partir de courbes.",
    },
    builtIn: {
      fallbackName: "Générique WRF 2 MW",
    },
    missing: {
      text:
        "{count|# éolienne utilise|# éoliennes utilisent} le type {n}, non défini dans le projet. Définir ce type ou en attribuer un autre.",
      blank: "Partir d'une courbe vierge",
    },
    editor: {
      name: "Nom",
      rated: "Puissance nominale",
      ratedInfo:
        "Puissance électrique maximale. Sert au contrôle de la courbe et au facteur de charge.",
      rotor: "Diamètre du rotor",
      rotorInfo:
        "Diamètre balayé par les pales. Un rotor plus grand donne un sillage plus fort.",
      hub: "Hauteur de moyeu",
      hubInfo:
        "Hauteur du moyeu au-dessus de la mer. WRF applique la traînée sur les niveaux compris entre moyeu − rayon et moyeu + rayon.",
      standing: "Coefficient de poussée à l'arrêt",
      standingInfo:
        "Ct de l'éolienne à l'arrêt, utilisé hors de la courbe (sous le démarrage, au-dessus de la coupure). Valeur courante : 0,05 à 0,15.",
      duplicate: "Dupliquer",
      delete: "Supprimer",
      deleteTitle: "Supprimer le type {n} ({name}) ?",
      deleteText: "Le type est retiré du projet. Aucune éolienne ne l'utilise.",
      inUse:
        "Utilisé par {count|# éolienne|# éoliennes} : leur attribuer un autre type avant de supprimer celui-ci.",
      restore: "Revenir à la table de WRF",
      restoreTitle: "Revenir à la table de WRF pour le type 1 ?",
      restoreText:
        "Définition du type 1 supprimée : les éoliennes de type 1 reprennent la table générique 2 MW de WRF.",
    },
    rows: {
      farms: "Parcs",
      turbines: "{n|éolienne|éoliennes}",
      spacing: "Pas de grille {d} D",
      specific: "{w} W/m²",
      maxCp: "Cp max {cp}",
    },
    use: {
      ready: "Type prêt. Étape suivante : placer les éoliennes dans Parcs éoliens.",
      goFarms: "Placer les parcs éoliens",
      label: "Utiliser le modèle {n} pour toutes les éoliennes de {farm}",
      assign: "Attribuer",
    },
    metrics: {
      specificInfo:
        "Puissance nominale divisée par la surface balayée. Sous 300 W/m² environ, le rotor est grand pour sa puissance : la puissance nominale est atteinte plus tôt et le facteur de charge est plus élevé.",
      maxCpHint: "{ws} m/s · Betz {betz}",
      maxCpInfo:
        "Cp = P / (½ ρ A U³), ρ = 1,225 kg/m³. Limite de Betz : 16/27. Au-dessus, vérifier l'unité de puissance et le diamètre du rotor.",
      rated: "Vitesse nominale",
      ratedHint: "{cutIn} → {cutOut} m/s",
      ratedInfo:
        "Lues sur la courbe : démarrage = première vitesse avec puissance, nominale = première vitesse à puissance nominale, coupure = dernière vitesse avec puissance.",
      gridHint: "{dx} km · {domain} · {min} D au moins",
      gridInfo:
        "README.windturbine de WRF : pas de grille d'au moins 5 diamètres de rotor. En dessous, les hypothèses de la paramétrisation des parcs ne tiennent plus.",
    },
    problems: {
      errors: "À corriger",
      warnings: "À vérifier",
      tooFew: "La courbe doit compter au moins deux lignes.",
      notFinite: "Valeurs vides ou illisibles : {rows|ligne #|lignes #}.",
      negative: "Les valeurs ne peuvent pas être négatives : {rows|ligne #|lignes #}.",
      notIncreasing:
        "Vitesses non strictement croissantes : {rows|ligne #|lignes #}. Corriger ou trier le tableau.",
      characteristics:
        "La puissance nominale, le diamètre du rotor et la hauteur de moyeu doivent être supérieurs à zéro, et le coefficient de poussée à l'arrêt positif ou nul.",
      betz:
        "Le coefficient de puissance dépasse la limite de Betz (16/27 ≈ 0,593) à {speeds} m/s : vérifier que la puissance est en kW et que le diamètre du rotor est juste.",
      aboveRated: "La courbe dépasse la puissance nominale de plus de 5 % (maximum {max} kW).",
      belowRated:
        "La courbe n'atteint pas la puissance nominale (maximum {max} kW pour {rated} kW). Vérifier l'unité (kW) ou la puissance nominale.",
      ctBelowCp:
        "Ct inférieur à Cp à {speeds} m/s, physiquement impossible. Colonnes puissance et Ct inversées ?",
    },
    curve: {
      add: "Ajouter une ligne",
      sort: "Trier par vitesse",
      paste: "Coller",
      points: "Points",
      speed: "Vitesse du vent",
      power: "Puissance",
      ct: "Ct",
      cp: "Cp",
      speedRow: "Vitesse du vent, ligne {n}",
      powerRow: "Puissance, ligne {n}",
      ctRow: "Coefficient de poussée, ligne {n}",
      removeRow: "Supprimer la ligne {n}",
      tableLabel: "Courbe du type {n}",
    },
    charts: {
      power: "Courbe de puissance",
      powerLabel: "Puissance (kW) en fonction de la vitesse du vent (m/s)",
      coefficients: "Coefficients de poussée et de puissance",
      coefficientsLabel:
        "Coefficient de poussée Ct et coefficient de puissance Cp en fonction de la vitesse du vent (m/s), avec la limite de Betz",
      powerSeries: "Puissance",
      ctSeries: "Coefficient de poussée Ct",
      cpSeries: "Coefficient de puissance Cp",
      betz: "Limite de Betz 16/27",
    },
    paste: {
      help:
        "Coller depuis un tableur : vitesse du vent (m/s), puissance, Ct, une ligne par vitesse. Séparateurs : tabulation, point-virgule ou espace. Virgule décimale acceptée. Avec une ligne d'en-tête, les colonnes peuvent être dans n'importe quel ordre. Fichiers WRF wind-turbine-N.tbl acceptés.",
      label: "Lignes à lire",
      file: "Lire un fichier",
      unit: "Puissance en",
      read: "{n|# ligne lue|# lignes lues}, de {from} à {to} m/s, jusqu'à {max} kW dans le tableau.",
      wrf: "Table WRF reconnue : hauteur de moyeu, diamètre du rotor, Ct à l'arrêt et puissance nominale aussi remplacés.",
      setRated: "Régler aussi la puissance nominale sur le maximum de la courbe ({mw} MW)",
      replace: "Remplacer la courbe",
      empty: "Coller au moins deux lignes.",
      tooFew: "Il faut au moins deux lignes.",
      line: "Ligne {line} illisible : « {text} ». Attendu : vitesse du vent, puissance, Ct.",
      fileError: "Le fichier n'a pas pu être lu.",
    },
    wrf: {
      title: "Table WRF",
      description:
        "Le fichier que WRF lit pour ce type, écrit à chaque calcul sous le nom wind-turbine-{n}.tbl quand un parc actif l'utilise. Ligne 1 : nombre de lignes ; ligne 2 : hauteur de moyeu (m), diamètre du rotor (m), coefficient de poussée à l'arrêt, puissance nominale (MW) ; puis vitesse du vent (m/s), Ct et puissance (kW) sur chaque ligne.",
      download: "Télécharger",
      fixFirst: "Corriger les erreurs du type pour voir sa table WRF.",
      label: "Contenu de wind-turbine-{n}.tbl",
    },
  },
});
