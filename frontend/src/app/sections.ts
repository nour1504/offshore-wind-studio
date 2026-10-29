import {
  IconAdjustmentsHorizontal,
  IconBook2,
  IconBuildingWindTurbine,
  IconCalendarTime,
  IconChartAreaLine,
  IconCpu,
  IconFileExport,
  IconFolders,
  IconGauge,
  IconLayoutDashboard,
  IconMap2,
  IconMovie,
  IconRadar2,
  IconSettings,
  IconTimeline,
  IconVariable,
  IconWindmill,
} from "@tabler/icons-react";

import { defineMessages } from "../i18n";

/** Sections of a project, in the order of the work: prepare, run, analyse. */
export const PROJECT_SECTIONS = [
  { key: "overview", group: "prepare", icon: IconLayoutDashboard },
  { key: "data", group: "prepare", icon: IconCalendarTime },
  { key: "domains", group: "prepare", icon: IconMap2 },
  { key: "turbines", group: "prepare", icon: IconBuildingWindTurbine },
  { key: "farms", group: "prepare", icon: IconWindmill },
  { key: "physics", group: "prepare", icon: IconAdjustmentsHorizontal },
  { key: "outputs", group: "prepare", icon: IconTimeline },
  { key: "run", group: "run", icon: IconFileExport },
  { key: "results", group: "analyse", icon: IconGauge },
  { key: "explorer", group: "analyse", icon: IconVariable },
  { key: "analyses", group: "analyse", icon: IconChartAreaLine },
  { key: "media", group: "analyse", icon: IconMovie },
] as const;

export type ProjectSection = (typeof PROJECT_SECTIONS)[number]["key"];

export const GLOBAL_SECTIONS = [
  { key: "projects", icon: IconFolders },
  { key: "compute", icon: IconCpu },
  { key: "observations", icon: IconRadar2 },
  { key: "help", icon: IconBook2 },
  { key: "settings", icon: IconSettings },
] as const;


export const sectionMessages = defineMessages({
  en: {
    groups: { prepare: "Prepare", run: "Run", analyse: "Analyse" },
    global: {
      projects: "Projects",
      compute: "Compute",
      observations: "Observations",
      help: "Help",
      settings: "Settings",
    },
    project: {
      overview: "Overview",
      data: "Period and data",
      domains: "Domains",
      farms: "Wind farms",
      turbines: "Turbine models",
      physics: "Physics and namelists",
      outputs: "Outputs",
      run: "WRF files",
      results: "Results and energy",
      explorer: "Variable explorer",
      analyses: "Wind analyses",
      media: "Videos and reports",
    },
  },
  fr: {
    groups: { prepare: "Préparer", run: "Calculer", analyse: "Analyser" },
    global: {
      projects: "Projets",
      compute: "Calcul",
      observations: "Observations",
      help: "Aide",
      settings: "Paramètres",
    },
    project: {
      overview: "Vue d'ensemble",
      data: "Période et données",
      domains: "Domaines",
      farms: "Parcs éoliens",
      turbines: "Modèles d'éoliennes",
      physics: "Physique et namelists",
      outputs: "Sorties",
      run: "Fichiers WRF",
      results: "Résultats et énergie",
      explorer: "Explorateur de variables",
      analyses: "Analyses du vent",
      media: "Vidéos et rapports",
    },
  },
});
