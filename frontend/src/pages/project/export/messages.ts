import { defineMessages } from "../../../i18n";

/** The quantities of the tslist export, in the order of the server (core/extract/tslist_export.py) */
export const QUANTITY_KEYS = [
  "wind_speed", "wind_direction", "turbulence_intensity", "tke", "temperature", "potential_temperature", "mixing_ratio", "pressure", "vertical_wind",
  "shear_exponent", "wind_veer", "power_turbine", "power_cell",
  "wind_speed_10m", "wind_direction_10m", "temperature_2m", "mixing_ratio_2m", "surface_pressure", "skin_temperature", "soil_temperature",
  "sensible_heat_flux", "latent_heat_flux", "longwave_down", "shortwave_down", "rain_convective", "rain_grid", "cloud_water",
  "inverse_obukhov_length", "obukhov_length", "bulk_richardson", "friction_velocity", "boundary_layer_height",
] as const;
export type QuantityKey = (typeof QUANTITY_KEYS)[number];
export const isQuantityKey = (key: string): key is QuantityKey => (QUANTITY_KEYS as readonly string[]).includes(key);

export const exportMessages = defineMessages({
  en: {
    tslist: "tslist points", tslistAside: "every model time step",
    wrfout: "wrfout grid", wrfoutAside: "every output time",
    points: "Points", all: "All", quantities: "Quantities", profiles: "At the heights", power: "Power", surface: "Surface",
    heights: "Heights · m", average: "Average", each: "Each step", day: "1 d",
    layout: "Layout", long: "In rows", wide: "In columns",
    layoutAbout: "In rows: one row per time and per grid cell, with its points and turbines. In columns: one row per time; each quantity of a cell once, its turbines in the column name; the power of each turbine in its own column.",
    runs: "Runs", both: "Both",
    period: "Period · UTC", preview: "Preview", times: "{n|# time|# times}", perCell: "{n} cells side by side",
    missing: "Not available", download: "Download (CSV)",
    noTslist: "No tslist output in this run", noChoice: "Choose points and quantities",
    variable: "Variable", derived: "Wind and turbulence", raw: "WRF variables", domain: "Domain", height: "Height", point: "Point", position: "Position", lat: "Latitude", lon: "Longitude",
    cell: "{d} cell {i},{j}",
    about: {
      power_turbine: "WRF's POWER of the cell divided by the number of turbines in the cell. Without a wind farm parameterization: the power curve at the hub-height wind.",
      power_cell: "WRF's POWER of the whole grid cell.",
      tke: "TKE of the boundary layer scheme (.TK file): QKE/2 with MYNN; TKE_PBL with MYJ, QNSE and BouLac.",
      turbulence_intensity: "σu / U with σu = √(TKE / 0.945), from the mean TKE and the mean speed.",
      shear_exponent: "α = ln(U2/U1) / ln(z2/z1) between the lowest and the highest height; left out under 1 m/s.",
      wind_veer: "Upper minus lower direction, between the lowest and the highest height.",
    },
    quantity: {
      wind_speed: "Wind speed", wind_direction: "Wind direction", turbulence_intensity: "Turbulence intensity", tke: "TKE",
      temperature: "Temperature", potential_temperature: "Potential temperature", mixing_ratio: "Mixing ratio", pressure: "Pressure", vertical_wind: "Vertical wind",
      shear_exponent: "Shear exponent", wind_veer: "Wind veer", power_turbine: "Turbine power", power_cell: "Cell power",
      wind_speed_10m: "Wind speed · 10 m", wind_direction_10m: "Wind direction · 10 m", temperature_2m: "Temperature · 2 m", mixing_ratio_2m: "Mixing ratio · 2 m",
      surface_pressure: "Surface pressure", skin_temperature: "Skin temperature", soil_temperature: "Soil temperature",
      sensible_heat_flux: "Sensible heat flux", latent_heat_flux: "Latent heat flux", longwave_down: "Downward longwave", shortwave_down: "Downward shortwave",
      rain_convective: "Convective rain, total", rain_grid: "Resolved rain, total", cloud_water: "Cloud water, column",
      inverse_obukhov_length: "1/L", obukhov_length: "Obukhov length L", bulk_richardson: "Bulk Richardson", friction_velocity: "Friction velocity u*", boundary_layer_height: "Boundary layer height",
    },
  },
  fr: {
    tslist: "Points tslist", tslistAside: "chaque pas du modèle",
    wrfout: "Grille wrfout", wrfoutAside: "à chaque sortie",
    points: "Points", all: "Tous", quantities: "Grandeurs", profiles: "Aux hauteurs", power: "Puissance", surface: "Surface",
    heights: "Hauteurs · m", average: "Moyenne", each: "Chaque pas", day: "1 j",
    layout: "Disposition", long: "En lignes", wide: "En colonnes",
    layoutAbout: "En lignes : une ligne par instant et par maille, avec ses points et ses éoliennes. En colonnes : une ligne par instant ; chaque grandeur d'une maille une fois, ses éoliennes dans le nom de la colonne ; la puissance de chaque éolienne dans sa colonne.",
    runs: "Calculs", both: "Les deux",
    period: "Période · UTC", preview: "Aperçu", times: "{n|# instant|# instants}", perCell: "{n} mailles côte à côte",
    missing: "Non disponible", download: "Télécharger (CSV)",
    noTslist: "Aucune sortie tslist dans ce calcul", noChoice: "Choisir points et grandeurs",
    variable: "Variable", derived: "Vent et turbulence", raw: "Variables de WRF", domain: "Domaine", height: "Hauteur", point: "Point", position: "Position", lat: "Latitude", lon: "Longitude",
    cell: "{d} maille {i},{j}",
    about: {
      power_turbine: "POWER de WRF de la maille divisé par le nombre d'éoliennes de la maille. Sans paramétrisation des parcs : courbe de puissance au vent du moyeu.",
      power_cell: "POWER de WRF de toute la maille.",
      tke: "TKE du schéma de couche limite (fichier .TK) : QKE/2 avec MYNN ; TKE_PBL avec MYJ, QNSE et BouLac.",
      turbulence_intensity: "σu / U avec σu = √(TKE / 0,945), de la TKE moyenne et de la vitesse moyenne.",
      shear_exponent: "α = ln(U2/U1) / ln(z2/z1) entre la plus basse et la plus haute des hauteurs ; écarté sous 1 m/s.",
      wind_veer: "Direction du haut moins celle du bas, entre la plus basse et la plus haute des hauteurs.",
    },
    quantity: {
      wind_speed: "Vitesse du vent", wind_direction: "Direction du vent", turbulence_intensity: "Intensité de turbulence", tke: "TKE",
      temperature: "Température", potential_temperature: "Température potentielle", mixing_ratio: "Rapport de mélange", pressure: "Pression", vertical_wind: "Vent vertical",
      shear_exponent: "Exposant de cisaillement", wind_veer: "Rotation du vent", power_turbine: "Puissance éolienne", power_cell: "Puissance maille",
      wind_speed_10m: "Vitesse du vent · 10 m", wind_direction_10m: "Direction du vent · 10 m", temperature_2m: "Température · 2 m", mixing_ratio_2m: "Rapport de mélange · 2 m",
      surface_pressure: "Pression en surface", skin_temperature: "Température de surface", soil_temperature: "Température du sol",
      sensible_heat_flux: "Flux de chaleur sensible", latent_heat_flux: "Flux de chaleur latente", longwave_down: "Infrarouge descendant", shortwave_down: "Solaire descendant",
      rain_convective: "Pluie convective cumulée", rain_grid: "Pluie résolue cumulée", cloud_water: "Eau nuageuse, colonne",
      inverse_obukhov_length: "1/L", obukhov_length: "Longueur d'Obukhov L", bulk_richardson: "Richardson global", friction_velocity: "Vitesse de frottement u*", boundary_layer_height: "Hauteur de couche limite",
    },
  },
});
