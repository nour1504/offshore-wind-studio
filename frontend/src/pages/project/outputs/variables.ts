/**
 * WRF output variables in plain words: names for the variables a wind study meets most often,
 * their units written for reading (m/s, W/m²), and the searches in the Registry catalogue
 * (backend/src/owstudio/data/variables_4.8.0.json, through /api/variables).
 */
import { useQuery } from "@tanstack/react-query";

import { get } from "../../../api/client";
import { defineMessages } from "../../../i18n";

export interface WrfVariable {
  name: string;
  description: string;
  units: string;
  dims: string;
  history: boolean;
  file: string;
}

export const variableNames = defineMessages({
  en: {
    U10: "Wind at 10 m, west–east component",
    V10: "Wind at 10 m, south–north component",
    U: "Wind, west–east component",
    V: "Wind, south–north component",
    W: "Vertical wind speed",
    T2: "Air temperature at 2 m",
    TH2: "Potential temperature at 2 m",
    Q2: "Humidity at 2 m",
    PSFC: "Surface pressure",
    TSK: "Surface skin temperature",
    SST: "Sea surface temperature",
    T: "Potential temperature (perturbation)",
    P: "Pressure (perturbation)",
    PB: "Pressure (base state)",
    PH: "Geopotential (perturbation)",
    PHB: "Geopotential (base state)",
    MU: "Air column mass (perturbation)",
    MUB: "Air column mass (base state)",
    HGT: "Terrain height",
    XLAT: "Latitude",
    XLONG: "Longitude",
    LANDMASK: "Land or sea",
    SEAICE: "Sea ice",
    PBLH: "Boundary layer height",
    UST: "Friction velocity",
    ZNT: "Surface roughness",
    RMOL: "Stability (inverse Monin–Obukhov length)",
    HFX: "Sensible heat flux at the surface",
    LH: "Latent heat flux at the surface",
    QFX: "Moisture flux at the surface (evaporation)",
    TKE_PBL: "Turbulent kinetic energy",
    QKE: "Twice the turbulent kinetic energy (MYNN)",
    TKE: "Turbulent kinetic energy (LES)",
    EL_PBL: "Turbulent mixing length",
    EXCH_H: "Turbulent heat exchange coefficient",
    POWER: "Power of the turbines",
    RUBLTEN: "Boundary-layer tendency of the west–east wind",
    RVBLTEN: "Boundary-layer tendency of the south–north wind",
    QVAPOR: "Water vapour",
    QCLOUD: "Cloud water",
    QRAIN: "Rain water",
    QICE: "Cloud ice",
    QSNOW: "Snow",
    QGRAUP: "Graupel",
    CLDFRA: "Cloud fraction",
    REFL_10CM: "Radar reflectivity",
    RAINC: "Convective rain, accumulated",
    RAINNC: "Rain from the microphysics, accumulated",
    SWDOWN: "Sunlight reaching the surface",
    GLW: "Infrared radiation reaching the surface",
    OLR: "Infrared radiation leaving the atmosphere",
    EMISS: "Surface emissivity",
  },
  fr: {
    U10: "Vent à 10 m, composante ouest–est",
    V10: "Vent à 10 m, composante sud–nord",
    U: "Vent, composante ouest–est",
    V: "Vent, composante sud–nord",
    W: "Vitesse verticale du vent",
    T2: "Température de l'air à 2 m",
    TH2: "Température potentielle à 2 m",
    Q2: "Humidité à 2 m",
    PSFC: "Pression en surface",
    TSK: "Température de la surface",
    SST: "Température de la mer en surface",
    T: "Température potentielle (écart)",
    P: "Pression (écart)",
    PB: "Pression (état de base)",
    PH: "Géopotentiel (écart)",
    PHB: "Géopotentiel (état de base)",
    MU: "Masse de la colonne d'air (écart)",
    MUB: "Masse de la colonne d'air (état de base)",
    HGT: "Altitude du terrain",
    XLAT: "Latitude",
    XLONG: "Longitude",
    LANDMASK: "Terre ou mer",
    SEAICE: "Glace de mer",
    PBLH: "Hauteur de la couche limite",
    UST: "Vitesse de frottement",
    ZNT: "Rugosité de la surface",
    RMOL: "Stabilité (inverse de la longueur de Monin-Obukhov)",
    HFX: "Flux de chaleur sensible en surface",
    LH: "Flux de chaleur latente en surface",
    QFX: "Flux d'humidité en surface (évaporation)",
    TKE_PBL: "Énergie cinétique turbulente",
    QKE: "Double de l'énergie cinétique turbulente (MYNN)",
    TKE: "Énergie cinétique turbulente (LES)",
    EL_PBL: "Longueur de mélange turbulent",
    EXCH_H: "Coefficient d'échange turbulent de chaleur",
    POWER: "Puissance des éoliennes",
    RUBLTEN: "Tendance du vent ouest–est due à la couche limite",
    RVBLTEN: "Tendance du vent sud–nord due à la couche limite",
    QVAPOR: "Vapeur d'eau",
    QCLOUD: "Eau nuageuse",
    QRAIN: "Eau de pluie",
    QICE: "Glace nuageuse",
    QSNOW: "Neige",
    QGRAUP: "Grésil",
    CLDFRA: "Fraction nuageuse",
    REFL_10CM: "Réflectivité radar",
    RAINC: "Pluie convective cumulée",
    RAINNC: "Pluie de la microphysique cumulée",
    SWDOWN: "Rayonnement solaire reçu en surface",
    GLW: "Rayonnement infrarouge reçu en surface",
    OLR: "Rayonnement infrarouge sortant de l'atmosphère",
    EMISS: "Émissivité de la surface",
  },
});

export const NAMED = Object.keys(variableNames.en) as (keyof typeof variableNames.en)[];

const SUPERSCRIPT: Record<string, string> = { "2": "²", "3": "³" };

/** Units the Registry leaves out or writes as names */
const UNIT_OF: Record<string, string> = { RMOL: "m-1" };
const UNIT_WORDS: Record<string, string> = { degree_north: "°", degree_east: "°", degrees: "°", "degrees north": "°", "degrees east": "°" };

/** Registry units written for reading: "m s-1" → "m/s", "W m-2" → "W/m²", "" → "". */
export function unitOf(variable: Pick<WrfVariable, "name" | "units">): string {
  return formatUnit(UNIT_OF[variable.name.toUpperCase()] ?? variable.units);
}

export function formatUnit(units: string): string {
  if (UNIT_WORDS[units.trim().toLowerCase()]) return UNIT_WORDS[units.trim().toLowerCase()];
  const tokens = units.trim().split(/\s+/).filter((token) => token && token !== "-" && token !== "1" && token !== "dimensionless");
  const up: string[] = [], down: string[] = [];
  for (const token of tokens) {
    const match = /^([A-Za-z%°]+)(-?\d+)?$/.exec(token);
    if (!match) return units.trim();
    const [, base, power = "1"] = match;
    const n = Math.abs(Number(power));
    const written = n === 1 ? base : `${base}${SUPERSCRIPT[String(n)] ?? `^${n}`}`;
    (Number(power) < 0 ? down : up).push(written);
  }
  if (!up.length && !down.length) return "";
  const top = up.join("·") || "1";
  return !down.length ? top : down.length === 1 ? `${top}/${down[0]}` : `${top}/(${down.join("·")})`;
}

/** A Registry description in sentence case ("UPWARD HEAT FLUX" → "Upward heat flux"). */
export function plainDescription(text: string): string {
  const clean = text.replace(/\s+/g, " ").trim();
  if (!clean) return "";
  const lower = clean === clean.toUpperCase() ? clean.toLowerCase() : clean;
  return lower.charAt(0).toUpperCase() + lower.slice(1);
}

/** Lower case without accents, for matching typed words against names. */
export const fold = (text: string) => text.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLowerCase();

/** Registry entries matching typed text (name or English description). */
export function useVariableSearch(text: string) {
  const q = text.trim();
  return useQuery({
    queryKey: ["wrf-variables", q],
    queryFn: ({ signal }) => get<WrfVariable[]>("/api/variables", { q, limit: 40 }, signal),
    enabled: q.length > 0,
    staleTime: Infinity,
  });
}

/** Registry entries of these variables (units, levels, default output): by default the named ones. */
export function useNamedVariables(names: readonly string[] = NAMED) {
  const list = names.map((name) => name.toUpperCase()).join(",");
  return useQuery({
    queryKey: ["wrf-variables-named", list],
    queryFn: () => get<WrfVariable[]>("/api/variables", { names: list }),
    enabled: list.length > 0,
    staleTime: Infinity,
  });
}
