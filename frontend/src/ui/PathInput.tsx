import { ActionIcon, TextInput, type TextInputProps, Tooltip } from "@mantine/core";
import { IconSitemap } from "@tabler/icons-react";
import { useState } from "react";

import type { FolderRole, Machine } from "../api/fs";
import { defineMessages, useT } from "../i18n";
import { FolderExplorer } from "./FolderExplorer";

/** An example matching what each field expects, never a generic one. */
export type PathExample = "weather" | "sst" | "engine" | "observation" | "geo" | "wrfout" | "data" | "key" | "folder" | "file";

const messages = defineMessages({
  en: {
    explore: "Browse",
    examples: {
      weather: "For example D:\\Weather\\ERA5_2025",
      sst: "For example D:\\Weather\\OSTIA_2025",
      engine: "For example C:\\OffshoreWindStudio\\Engine",
      observation: "For example C:\\Measurements\\FINO3_2025.csv",
      geo: "For example C:\\Maps\\wind_farms.geojson",
      wrfout: "For example D:\\WRF\\my_run (folder of the wrfout files)",
      data: "For example D:\\OffshoreWindStudio",
      key: "For example C:\\Users\\you\\.ssh\\id_ed25519",
      folder: "Choose a folder",
      file: "Choose a file",
      any: "Choose a file or a folder",
    },
  },
  fr: {
    explore: "Parcourir",
    examples: {
      weather: "Par exemple D:\\Météo\\ERA5_2025",
      sst: "Par exemple D:\\Météo\\OSTIA_2025",
      engine: "Par exemple C:\\OffshoreWindStudio\\Moteur",
      observation: "Par exemple C:\\Mesures\\FINO3_2025.csv",
      geo: "Par exemple C:\\Cartes\\parcs_eoliens.geojson",
      wrfout: "Par exemple D:\\WRF\\mon_calcul (dossier des fichiers wrfout)",
      data: "Par exemple D:\\OffshoreWindStudio",
      key: "Par exemple C:\\Users\\vous\\.ssh\\id_ed25519",
      folder: "Choisissez un dossier",
      file: "Choisissez un fichier",
      any: "Choisissez un fichier ou un dossier",
    },
  },
});

interface Browse {
  /** The machine whose folders are explored: the engine's, or this computer's (by default);
   * null for a machine the application cannot read (a cluster): the path is only copied */
  machine?: Machine | null;
  expect?: FolderRole;
  marks?: string[];
  writable?: boolean;
  /** The profile whose engine machine is explored, the default one otherwise */
  profile?: string;
}

/** A pasted path without the quotes Windows adds ("Copy as path"). */
export function cleanPath(text: string): string {
  const quoted = /^\s*(["'])(.*)\1\s*$/.exec(text);
  return quoted ? quoted[2] : text;
}

/** A path typed or pasted (Ctrl+V), or chosen in the folder tree of a machine (this computer
 * unless the engine is named); a file field chooses a file in the same tree, an "any" field
 * a file or a folder. */
export function PathInput({
  value,
  onChange,
  kind = "folder",
  example,
  machine = "here",
  expect,
  marks,
  writable,
  profile,
  ...props
}: Omit<TextInputProps, "value" | "onChange"> & Browse & { value: string; onChange: (path: string) => void; kind?: "folder" | "file" | "any"; example?: PathExample }) {
  const t = useT(messages);
  const [exploring, setExploring] = useState(false);
  return (
    <>
      <TextInput
        placeholder={t(`examples.${example ?? kind}`)}
        value={value}
        onChange={(e) => onChange(cleanPath(e.currentTarget.value))}
        spellCheck={false}
        styles={{ input: { fontFamily: "var(--mantine-font-family-monospace)", fontSize: 13 } }}
        rightSection={
          machine ? (
            <Tooltip label={t("explore")}>
              <ActionIcon variant="subtle" aria-label={t("explore")} onClick={() => setExploring(true)}>
                <IconSitemap size={18} style={{ transform: "rotate(-90deg)" }} />
              </ActionIcon>
            </Tooltip>
          ) : undefined
        }
        {...props}
      />
      {machine && <FolderExplorer opened={exploring} onClose={() => setExploring(false)} machine={machine} value={value} onChoose={onChange} expect={expect} marks={marks} writable={writable} profile={profile} pick={kind} />}
    </>
  );
}
