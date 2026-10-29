/** Names and explanations of the folders the application writes to, shared by the Settings sections. */
import { defineMessages } from "../../i18n";

export const LOCATION_KEYS = ["cases", "input", "observations", "exports", "videos", "reports", "jobs"] as const;
export type LocationKey = (typeof LOCATION_KEYS)[number];

export const isLocationKey = (key: string): key is LocationKey => (LOCATION_KEYS as readonly string[]).includes(key);

/** Folders that can be placed elsewhere than in the data folder. */
export const FOLDER_KEYS = ["input", "observations", "exports", "videos", "reports"] as const;
export type FolderKey = (typeof FOLDER_KEYS)[number];

export const isFolderKey = (key: string): key is FolderKey => (FOLDER_KEYS as readonly string[]).includes(key);

export const locationMessages = defineMessages({
  en: {
    name: {
      cases: "Projects and runs",
      input: "Map cache",
      observations: "Observations",
      exports: "Exports",
      videos: "Videos",
      reports: "Reports",
      jobs: "Background task logs",
    },
    about: {
      cases: "Each project's case, and one folder per run with its generated files, logs and WRF outputs (wrfout, time series).",
      input: "Cached base maps, terrain and 3D scenes. GFS and ERA5 data are in the engine input data folder.",
      observations: "Measured data imported for comparisons, and the saved import mappings.",
      exports: "Series and tables extracted from the results.",
      videos: "Rendered animations of wind fields and wakes.",
      reports: "Generated reports.",
      jobs: "Logs of downloads, extractions, renderings and other background tasks.",
    },
    sources: {
      gfs: "GFS downloads",
      era5: "ERA5 downloads",
      sst: "SST downloads",
    },
  },
  fr: {
    name: {
      cases: "Projets et calculs",
      input: "Cache de la carte",
      observations: "Observations",
      exports: "Exports",
      videos: "Vidéos",
      reports: "Rapports",
      jobs: "Journaux des tâches de fond",
    },
    about: {
      cases: "Le cas de chaque projet, et un dossier par calcul avec ses fichiers générés, ses journaux et les sorties de WRF (wrfout, séries temporelles).",
      input: "Fonds de carte, relief et scènes 3D en cache. Les données GFS et ERA5 sont dans le dossier des données d'entrée du moteur.",
      observations: "Mesures importées pour les comparaisons, et les correspondances d'import enregistrées.",
      exports: "Séries et tableaux extraits des résultats.",
      videos: "Animations des champs de vent et des sillages.",
      reports: "Rapports générés.",
      jobs: "Journaux des téléchargements, extractions, rendus et autres tâches de fond.",
    },
    sources: {
      gfs: "Téléchargements GFS",
      era5: "Téléchargements ERA5",
      sst: "Téléchargements SST",
    },
  },
});
