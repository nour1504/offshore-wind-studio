import { Alert, Button, Group, SimpleGrid, Stack, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconInfoCircle } from "@tabler/icons-react";
import { useState } from "react";

import type { Folders, StorageUsage } from "../../api/types";
import { defineMessages, useT } from "../../i18n";
import { FieldLabel } from "../../ui/Inputs";
import { PathInput } from "../../ui/PathInput";
import { ErrorState } from "../../ui/States";
import { FOLDER_KEYS, type FolderKey, locationMessages } from "./labels";
import { isAbsolutePath, joinPath, useSetFolders } from "./queries";

const messages = defineMessages({
  en: {
    intro:
      "",
    notMoved:
      "Existing files are not moved. Move them manually if needed. The map cache is rebuilt.",
    notAbsolute: "Give a full path, for example D:\\WRF-data\\input",
    defaults: "Use the default places",
    save: "Save the folders",
    saved: "Folders saved",
    inputInfo: "Base maps, terrain and 3D scenes. GFS and ERA5 data are in the engine input data folder (Compute).",
  },
  fr: {
    intro:
      "",
    notMoved:
      "Les fichiers existants ne sont pas déplacés. Les déplacer manuellement si nécessaire. Le cache de carte se reconstitue.",
    notAbsolute: "Indiquez un chemin complet, par exemple D:\\Donnees-WRF\\input",
    defaults: "Utiliser les emplacements par défaut",
    save: "Enregistrer les dossiers",
    saved: "Dossiers enregistrés",
    inputInfo:
      "Fonds de carte, relief et scènes 3D. Les données GFS et ERA5 sont dans le dossier des données d'entrée du moteur (Calcul).",
  },
});

/** Input, observations, exports, videos and reports placed outside the data folder. */
export function FolderOverrides({ storage }: { storage: StorageUsage }) {
  const t = useT(messages);
  const tl = useT(locationMessages);
  const save = useSetFolders();
  const [values, setValues] = useState<Folders>(storage.folders);

  const errors = Object.fromEntries(
    FOLDER_KEYS.map((key) => [key, values[key].trim() && !isAbsolutePath(values[key]) ? t("notAbsolute") : null]),
  ) as Record<FolderKey, string | null>;
  const invalid = FOLDER_KEYS.some((key) => errors[key]);
  const dirty = FOLDER_KEYS.some((key) => values[key].trim() !== storage.folders[key].trim());
  const custom = FOLDER_KEYS.some((key) => values[key].trim());

  const submit = () => {
    const trimmed = Object.fromEntries(FOLDER_KEYS.map((key) => [key, values[key].trim()])) as unknown as Folders;
    save.mutate(trimmed, { onSuccess: () => notifications.show({ color: "teal", message: t("saved") }) });
  };

  return (
    <Stack>
      <Text size="sm" c="dimmed">
        {t("intro")}
      </Text>
      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="md" verticalSpacing="md">
        {FOLDER_KEYS.map((key) => (
          <PathInput example="data"
            key={key}
            label={<FieldLabel label={tl(`name.${key}`)} info={key === "input" ? t("inputInfo") : tl(`about.${key}`)} />}
            aria-label={tl(`name.${key}`)}
            value={values[key]}
            onChange={(path) => setValues((v) => ({ ...v, [key]: path }))}
            placeholder={joinPath(storage.data_root, key === "input" ? "cache" : key)}
            error={errors[key]}
          />
        ))}
      </SimpleGrid>
      <Alert color="gray" variant="light" icon={<IconInfoCircle size={18} />} py="xs">
        <Text size="sm">{t("notMoved")}</Text>
      </Alert>
      {save.error && <ErrorState error={save.error} />}
      <Group justify="flex-end" gap="xs">
        <Button
          variant="subtle"
          color="gray"
          onClick={() => setValues(Object.fromEntries(FOLDER_KEYS.map((key) => [key, ""])) as unknown as Folders)}
          disabled={!custom || save.isPending}
        >
          {t("defaults")}
        </Button>
        <Button onClick={submit} disabled={!dirty || invalid} loading={save.isPending}>
          {t("save")}
        </Button>
      </Group>
    </Stack>
  );
}
