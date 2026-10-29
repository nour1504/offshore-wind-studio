/**
 * Names of the quantities derived from WRF outputs (server: core/extract/catalogue.py), in the
 * language of the interface, and units written the way people read them.
 */
import { defineMessages } from "../../../i18n";

export const quantityNames = defineMessages({
  en: {
    wind_speed: "Wind speed", wind_direction: "Wind direction", u: "Eastward wind", v: "Northward wind",
    potential_temperature: "Potential temperature", virtual_potential_temperature: "Virtual potential temperature",
    temperature: "Air temperature", pressure: "Pressure", density: "Air density", mixing_ratio: "Water vapour",
    tke: "Turbulent kinetic energy", wind_speed_std: "Wind standard deviation", turbulence_intensity: "Turbulence intensity",
    pblh: "Boundary layer height", friction_velocity: "Friction velocity u*", sensible_heat_flux: "Sensible heat flux",
    latent_heat_flux: "Latent heat flux", sst: "Sea surface temperature", skin_temperature: "Skin temperature",
    roughness_length: "Roughness length", inverse_obukhov_length: "Inverse Obukhov length", obukhov_length: "Obukhov length",
    power: "Turbine power",
  },
  fr: {
    wind_speed: "Vitesse du vent", wind_direction: "Direction du vent", u: "Vent vers l'est", v: "Vent vers le nord",
    potential_temperature: "Température potentielle", virtual_potential_temperature: "Température potentielle virtuelle",
    temperature: "Température de l'air", pressure: "Pression", density: "Masse volumique de l'air", mixing_ratio: "Vapeur d'eau",
    tke: "Énergie cinétique turbulente", wind_speed_std: "Écart type du vent", turbulence_intensity: "Intensité de turbulence",
    pblh: "Hauteur de couche limite", friction_velocity: "Vitesse de frottement u*", sensible_heat_flux: "Flux de chaleur sensible",
    latent_heat_flux: "Flux de chaleur latente", sst: "Température de surface de la mer", skin_temperature: "Température de surface",
    roughness_length: "Longueur de rugosité", inverse_obukhov_length: "Inverse de la longueur d'Obukhov", obukhov_length: "Longueur d'Obukhov",
    power: "Puissance des éoliennes",
  },
});

/** What each quantity is and how it comes out of WRF, in a few words. */
export const quantityAbout = defineMessages({
  en: {
    wind_speed: "Horizontal speed √(u² + v²), interpolated linearly to the height between model levels; at 10 m, WRF's U10 and V10.",
    wind_direction: "Direction the wind comes from, clockwise from north, from u and v.",
    u: "Wind towards the east: WRF's U and V (along the grid) turned to the earth's axes.",
    v: "Wind towards the north: WRF's U and V (along the grid) turned to the earth's axes.",
    potential_temperature: "θ = T + 300 K (WRF writes the difference from 300 K).",
    virtual_potential_temperature: "θv = θ (1 + 0.608 qv).",
    temperature: "θ (p / p₀)^(Rd/cp), p = P + PB, p₀ = 1000 hPa; at 2 m, WRF's T2.",
    pressure: "P + PB (perturbation plus base state).",
    density: "p / (Rd T (1 + 0.608 qv)).",
    mixing_ratio: "QVAPOR: mass of water vapour per mass of dry air.",
    tke: "Turbulent kinetic energy of the boundary-layer scheme: QKE / 2 with MYNN, otherwise TKE_PBL.",
    wind_speed_std: "σ = √(2 TKE / 3): turbulence taken as isotropic.",
    turbulence_intensity: "TI = σ / U with σ = √(2 TKE / 3). History files only: the tslist outputs hold no TKE.",
    pblh: "PBLH written by WRF.",
    friction_velocity: "UST written by WRF.",
    sensible_heat_flux: "HFX written by WRF (upwards positive).",
    latent_heat_flux: "LH written by WRF (upwards positive).",
    sst: "SST written by WRF.",
    skin_temperature: "TSK written by WRF.",
    roughness_length: "ZNT written by WRF.",
    inverse_obukhov_length: "RMOL written by WRF, otherwise −κ g w'θv' / (u*³ θv) from the surface fluxes.",
    obukhov_length: "L = 1 / (1/L), 1/L as RMOL.",
    power: "POWER written by WRF: the power of all the turbines of a grid cell.",
  },
  fr: {
    wind_speed: "Vitesse horizontale √(u² + v²), interpolée linéairement à la hauteur entre les niveaux du modèle ; à 10 m, U10 et V10 de WRF.",
    wind_direction: "Direction d'où vient le vent, depuis le nord dans le sens horaire, tirée de u et v.",
    u: "Vent vers l'est : U et V de WRF (selon la grille) tournés dans le repère terrestre.",
    v: "Vent vers le nord : U et V de WRF (selon la grille) tournés dans le repère terrestre.",
    potential_temperature: "θ = T + 300 K (WRF écrit l'écart à 300 K).",
    virtual_potential_temperature: "θv = θ (1 + 0,608 qv).",
    temperature: "θ (p / p₀)^(Rd/cp), p = P + PB, p₀ = 1000 hPa ; à 2 m, T2 de WRF.",
    pressure: "P + PB (perturbation plus état de base).",
    density: "p / (Rd T (1 + 0,608 qv)).",
    mixing_ratio: "QVAPOR : masse de vapeur d'eau par masse d'air sec.",
    tke: "Énergie cinétique turbulente du schéma de couche limite : QKE / 2 avec MYNN, sinon TKE_PBL.",
    wind_speed_std: "σ = √(2 TKE / 3) : turbulence supposée isotrope.",
    turbulence_intensity: "TI = σ / U avec σ = √(2 TKE / 3). Fichiers d'historique seulement : les sorties tslist n'ont pas de TKE.",
    pblh: "PBLH écrit par WRF.",
    friction_velocity: "UST écrit par WRF.",
    sensible_heat_flux: "HFX écrit par WRF (positif vers le haut).",
    latent_heat_flux: "LH écrit par WRF (positif vers le haut).",
    sst: "SST écrit par WRF.",
    skin_temperature: "TSK écrit par WRF.",
    roughness_length: "ZNT écrit par WRF.",
    inverse_obukhov_length: "RMOL écrit par WRF, sinon −κ g w'θv' / (u*³ θv) tiré des flux de surface.",
    obukhov_length: "L = 1 / (1/L), 1/L comme RMOL.",
    power: "POWER écrit par WRF : la puissance de toutes les éoliennes d'une maille.",
  },
});

export type QuantityKey = keyof typeof quantityNames.en;
export const isQuantity = (key: string): key is QuantityKey => key in quantityNames.en;

/** WRF writes units as "m s-1", "m2 s-2", "W m-2": written here as m/s, m²/s², W/m². */
export function prettyUnit(unit: string | undefined): string {
  if (!unit) return "";
  const map: Record<string, string> = {
    "m s-1": "m/s", "m2 s-2": "m²/s²", "W m-2": "W/m²", "kg m-3": "kg/m³", "kg kg-1": "kg/kg", "m-1": "1/m", "s-1": "1/s",
    "-": "", "1": "", "dimensionless": "",
  };
  return map[unit.trim()] ?? unit;
}
