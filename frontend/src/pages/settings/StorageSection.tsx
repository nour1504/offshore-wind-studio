import { Accordion, Button, Group, Paper, Stack, Text, Tooltip } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { IconFolderCog, IconFolderShare, IconRefresh } from "@tabler/icons-react";

import { useStorage } from "../../api/system";
import type { StorageLocation, StorageUsage } from "../../api/types";
import { defineMessages, useFormat, useT } from "../../i18n";
import { DataTable } from "../../ui/DataTable";
import { FieldLabel } from "../../ui/Inputs";
import { Fold } from "../../ui/Fold";
import { Stat, StatGrid } from "../../ui/Stat";
import { QueryView } from "../../ui/States";
import { PathLine } from "./CopyPath";
import { FolderOverrides } from "./FolderOverrides";
import { isFolderKey, isLocationKey, locationMessages } from "./labels";
import { MoveDataRoot } from "./MoveDataRoot";
import { isInside } from "./queries";

/** Below this, a run with history files may not fit: the run estimate warns as well. */
const LOW_SPACE_BYTES = 20e9;

const messages = defineMessages({
  en: {
    title: "Storage",
    measure: "Measure again",
    dataFolder: "Data folder",
    dataFolderInfo:
      "Holds the projects, the calculations and, by default, the other folders. This setting is stored outside the folder.",
    change: "Change the data folder…",
    free: "Free space",
    lowSpace: "Low: a WRF run with history files can take tens of GB.",
    used: "Used by the application",
    runs: "Runs",
    runsHint: "{n|# project with runs|# projects with runs}",
    locations: "Locations",
    location: "Location",
    path: "Path",
    size: "Size",
    custom: "Custom place",
    customInfo: "Placed outside the data folder in the advanced settings below.",
    advanced: "Choose folders for downloads and exports",
  },
  fr: {
    title: "Stockage",
    measure: "Mesurer à nouveau",
    dataFolder: "Dossier de données",
    dataFolderInfo:
      "Contient les projets, les calculs et, par défaut, les autres dossiers. Ce réglage est enregistré en dehors du dossier.",
    change: "Changer de dossier de données…",
    free: "Espace libre",
    lowSpace: "Faible : un calcul WRF avec fichiers d'historique peut occuper des dizaines de Go.",
    used: "Utilisé par l'application",
    runs: "Calculs",
    runsHint: "{n|# projet avec des calculs|# projets avec des calculs}",
    locations: "Emplacements",
    location: "Emplacement",
    path: "Chemin",
    size: "Taille",
    custom: "Emplacement personnalisé",
    customInfo: "Placé hors du dossier de données dans les réglages avancés ci-dessous.",
    advanced: "Choisir les dossiers de téléchargement et d'export",
  },
});

/** Total size without counting twice a folder placed inside another one. */
function usedBytes(locations: StorageLocation[]): number {
  return locations
    .filter((loc) => !locations.some((other) => other !== loc && isInside(loc.path, other.path)))
    .reduce((sum, loc) => sum + loc.bytes, 0);
}

/** The disk of the data folder, filled from the left: the application, then the rest of what is used. */
function DiskBar({ disk, free, app }: { disk: number; free: number; app: number }) {
  const t = useT(messages);
  const f = useFormat();
  const used = Math.max(0, disk - free);
  const mine = Math.min(app, used);
  const share = (bytes: number) => `${(100 * bytes) / disk}%`;
  return (
    <div className="ows-disk" role="img" aria-label={`${t("used")} ${f.bytes(mine)} · ${t("free")} ${f.bytes(free)} / ${f.bytes(disk)}`}>
      <span className="ows-disk-app" style={{ width: share(mine) }} title={`${t("used")} · ${f.bytes(mine)}`} />
      <span className="ows-disk-other" style={{ width: share(used - mine) }} />
    </div>
  );
}

function Overview({ storage }: { storage: StorageUsage }) {
  const t = useT(messages);
  const tl = useT(locationMessages);
  const f = useFormat();
  const low = storage.free_bytes < LOW_SPACE_BYTES;
  const projects = new Set(storage.runs.map((r) => r.case)).size;

  return (
    <Stack gap="lg">
      <Paper withBorder p="md">
        <Stack gap={4}>
          <Text size="xs" c="dimmed" tt="uppercase" fw={600} style={{ letterSpacing: 0.4 }}>
            <FieldLabel label={t("dataFolder")} info={t("dataFolderInfo")} />
          </Text>
          <PathLine path={storage.data_root} name={t("dataFolder")} />
        </Stack>
      </Paper>

      <StatGrid cols={3}>
        <Stat
          label={t("free")}
          value={f.bytes(storage.free_bytes)}
          hint={low ? t("lowSpace") : undefined}
          tone={low ? "bad" : "default"}
        />
        <Stat label={t("used")} value={f.bytes(usedBytes(storage.locations))} />
        <Stat label={t("runs")} value={f.number(storage.runs.length, 0)} hint={t("runsHint", { n: projects })} />
      </StatGrid>
      {Boolean(storage.disk_bytes) && <DiskBar disk={storage.disk_bytes as number} free={storage.free_bytes} app={usedBytes(storage.locations)} />}

      <Stack gap="xs">
        <Text fw={600} size="sm">
          {t("locations")}
        </Text>
        <Paper withBorder>
          <DataTable<StorageLocation>
            caption={t("locations")}
            rowKey={(loc) => loc.key}
            rows={storage.locations}
            columns={[
              {
                key: "name",
                header: t("location"),
                width: "34%",
                render: (loc) => {
                  const known = isLocationKey(loc.key);
                  const custom = isFolderKey(loc.key) && storage.folders[loc.key].trim() !== "";
                  return (
                    <Stack gap={2}>
                      <Group gap={6} wrap="wrap">
                        <Text size="sm" fw={500}>
                          {known ? tl(`name.${loc.key}` as Parameters<typeof tl>[0]) : loc.label}
                        </Text>
                        {custom && (
                          <Tooltip label={t("customInfo")}>
                            <Text size="xs" c="dimmed" tabIndex={0}>
                              {t("custom")}
                            </Text>
                          </Tooltip>
                        )}
                      </Group>
                    </Stack>
                  );
                },
                sortValue: (loc) => (isLocationKey(loc.key) ? tl(`name.${loc.key}`) : loc.label),
              },
              {
                key: "path",
                header: t("path"),
                render: (loc) => (
                  <PathLine path={loc.path} name={isLocationKey(loc.key) ? tl(`name.${loc.key}`) : loc.label} size="xs" />
                ),
              },
              {
                key: "size",
                header: t("size"),
                align: "right",
                width: 110,
                render: (loc) => <Text size="sm" style={{ whiteSpace: "nowrap" }}>{f.bytes(loc.bytes)}</Text>,
                sortValue: (loc) => loc.bytes,
              },
            ]}
          />
        </Paper>
      </Stack>

      <Accordion variant="contained" chevronPosition="left">
        <Accordion.Item value="folders">
          <Accordion.Control icon={<IconFolderCog size={18} aria-hidden />}>
            <Text size="sm" fw={500}>
              {t("advanced")}
            </Text>
          </Accordion.Control>
          <Accordion.Panel>
            {/* Remounted when the saved folders change, so the form starts from them */}
            <FolderOverrides key={JSON.stringify(storage.folders)} storage={storage} />
          </Accordion.Panel>
        </Accordion.Item>
      </Accordion>
    </Stack>
  );
}

/** Data folder, every location with its size, moving the data and placing folders elsewhere. */
export function StorageSection() {
  const t = useT(messages);
  const storage = useStorage();
  const [moving, { open, close }] = useDisclosure(false);

  return (
    <Fold
      title={t("title")}
      help="storage"
      actions={
        <>
          <Button
            variant="subtle"
            color="gray"
            leftSection={<IconRefresh size={16} aria-hidden />}
            onClick={() => void storage.refetch()}
            loading={storage.isFetching && !storage.isLoading}
            disabled={storage.isLoading}
          >
            {t("measure")}
          </Button>
          <Button
            variant="default"
            leftSection={<IconFolderShare size={16} aria-hidden />}
            onClick={open}
            disabled={!storage.data}
          >
            {t("change")}
          </Button>
        </>
      }
    >
      <QueryView query={storage}>{(data) => <Overview storage={data} />}</QueryView>
      {storage.data && <MoveDataRoot opened={moving} onClose={close} storage={storage.data} />}
    </Fold>
  );
}
