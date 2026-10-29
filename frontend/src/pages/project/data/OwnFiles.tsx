import {
  Alert,
  Badge,
  Button,
  Collapse,
  Group,
  Loader,
  Select,
  SimpleGrid,
  Stack,
  Text,
  Textarea,
  TextInput,
} from "@mantine/core";
import { useDebouncedValue, useDisclosure } from "@mantine/hooks";
import { IconAlertTriangle, IconCircleCheck, IconFileDatabase } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { dataApi, useFileListing, useVtables } from "../../../api/data";
import type { GribInput } from "../../../api/types";
import { useFieldIssue } from "../../../app/CaseDraft";
import { defineMessages, useFormat, useT } from "../../../i18n";
import { FieldLabel } from "../../../ui/Inputs";
import { FoundTree } from "../../../ui/FoundTree";
import { PathInput } from "../../../ui/PathInput";

const messages = defineMessages({
  en: {
    folder: "Folder on this computer",
    folderInfo:
      "The files are read in place.",
    pattern: "Files to use",
    patternInfo: "Examples: *.grib, *.nc, era5-*. Subfolders are included.",
    netcdf:
      "NetCDF files are converted to WPS intermediate files on this computer before the run. No variable table needed.",
    found: "{n|# file|# files} · {size}",
    noFile: "No file matches.",
    notFound: "This folder does not exist on this computer.",
    showFiles: "Show the files",
    hideFiles: "Hide the files",
    vtable: "Variable table (Vtable): how to read your files",
    vtableInfo:
      "Tells ungrib which fields to read in the GRIB files. Use the table of the data provider.",
    recommended: "Recommended",
    others: "Other WPS tables",
    custom: "Custom table…",
    customText: "Custom table",
    customInfo: "Same format as the WPS tables. Start from a standard table.",
    startFrom: "Start from {name}",
    valid: "The table is readable by ungrib.",
  },
  fr: {
    folder: "Dossier sur cet ordinateur",
    folderInfo:
      "Les fichiers sont lus sur place.",
    pattern: "Fichiers à utiliser",
    patternInfo: "Exemples : *.grib, *.nc, era5-*. Les sous-dossiers sont inclus.",
    netcdf:
      "Les fichiers NetCDF sont convertis en fichiers intermédiaires WPS sur cet ordinateur avant le calcul. Pas de table des variables.",
    found: "{n|# fichier|# fichiers} · {size}",
    noFile: "Aucun fichier ne correspond.",
    notFound: "Ce dossier n'existe pas sur cet ordinateur.",
    showFiles: "Afficher les fichiers",
    hideFiles: "Masquer les fichiers",
    vtable: "Table des variables (Vtable) : comment lire vos fichiers",
    vtableInfo:
      "Indique à ungrib les champs à lire dans les fichiers GRIB. Prendre la table du fournisseur des données.",
    recommended: "Recommandées",
    others: "Autres tables WPS",
    custom: "Table personnalisée…",
    customText: "Table personnalisée",
    customInfo: "Même format que les tables WPS. Partir d'une table standard.",
    startFrom: "Partir de {name}",
    valid: "La table est lisible par ungrib.",
  },
});

const formatLabel: Record<string, string> = { grib1: "GRIB 1", grib2: "GRIB 2", netcdf: "NetCDF", unknown: "?" };

interface Props {
  value: GribInput;
  onChange: (value: GribInput) => void;
  /** Table proposed when starting a custom one */
  defaultVtable: string;
}

/** Choice of the user's own GRIB or NetCDF files and of the variable table that reads GRIB files. */
export function OwnFiles({ value, onChange, defaultVtable }: Props) {
  const folderIssue = useFieldIssue(defaultVtable === "Vtable.SST" ? "sea_surface.grib.folder" : "grib.folder");
  const t = useT(messages);
  const f = useFormat();
  const [folder] = useDebouncedValue(value.folder, 400);
  const [pattern] = useDebouncedValue(value.pattern, 400);
  const listing = useFileListing(folder, pattern || "*");
  const tables = useVtables();
  const [filesOpen, files] = useDisclosure(false);
  const [base, setBase] = useState(defaultVtable);
  const [customText] = useDebouncedValue(value.custom_vtable, 500);
  const validation = useQuery({
    queryKey: ["vtable-validate", customText],
    queryFn: () => dataApi.validateVtable(customText),
    enabled: value.vtable === "custom" && customText.trim().length > 0,
  });

  const set = (changes: Partial<GribInput>) => onChange({ ...value, ...changes });
  const netcdf = Boolean(listing.data && listing.data.count > 0 && listing.data.formats.netcdf === listing.data.count);
  const options = [
    { group: t("recommended"), items: (tables.data ?? []).filter((v) => v.recommended).map((v) => ({ value: v.name, label: v.name })) },
    { group: t("others"), items: (tables.data ?? []).filter((v) => !v.recommended).map((v) => ({ value: v.name, label: v.name })) },
    { group: "", items: [{ value: "custom", label: t("custom") }] },
  ];

  const startCustom = async () => {
    const text = await dataApi.vtable(base);
    set({ vtable: "custom", custom_vtable: text });
  };

  return (
    <Stack gap="md">
      <SimpleGrid cols={{ base: 1, sm: 3 }}>
        <PathInput example={defaultVtable === "Vtable.SST" ? "sst" : "weather"}
          label={<FieldLabel label={t("folder")} info={t("folderInfo")} />}
          error={folderIssue?.severity === "error" ? folderIssue.text : undefined}
          value={value.folder}
          onChange={(folderPath) => set({ folder: folderPath })}
          style={{ gridColumn: "span 2" }}
        />
        <TextInput
          label={<FieldLabel label={t("pattern")} info={t("patternInfo")} />}
          value={value.pattern}
          onChange={(e) => set({ pattern: e.currentTarget.value })}
          styles={{ input: { fontFamily: "var(--mantine-font-family-monospace)" } }}
        />
      </SimpleGrid>

      {listing.isFetching && !listing.data && <Loader size="xs" />}
      {listing.error ? (
        <Alert color="red" variant="light" icon={<IconAlertTriangle size={18} />}>
          {(listing.error as { status?: number }).status === 404 ? t("notFound") : (listing.error as Error).message}
        </Alert>
      ) : null}
      {listing.data && (
        <Stack gap="xs">
          <Group gap="xs">
            <IconFileDatabase size={18} stroke={1.6} />
            <Text size="sm" fw={500}>
              {listing.data.count === 0 ? t("noFile") : t("found", { n: listing.data.count, size: f.bytes(listing.data.total_bytes) })}
            </Text>
            {Object.entries(listing.data.formats).map(([format, count]) => (
              <Badge key={format} color={format === "unknown" ? "red" : format === "netcdf" ? "gray" : "teal"}>
                {formatLabel[format]} · {count}
              </Badge>
            ))}
            {listing.data.count > 0 && (
              <Button variant="subtle" size="compact-xs" onClick={files.toggle}>
                {filesOpen ? t("hideFiles") : t("showFiles")}
              </Button>
            )}
          </Group>
          {listing.data.problems.map((problem) => (
            <Alert key={problem} color="red" variant="light" icon={<IconAlertTriangle size={18} />}>
              {problem}
            </Alert>
          ))}
          <Collapse expanded={filesOpen}>
            <FoundTree summary={listing.data.tree} />
          </Collapse>
        </Stack>
      )}

      {netcdf && (
        <Text size="sm" c="dimmed">
          {t("netcdf")}
        </Text>
      )}
      {!netcdf && (
        <Select
          label={<FieldLabel label={t("vtable")} info={t("vtableInfo")} />}
          data={options.filter((o) => o.items.length)}
          value={value.vtable}
          onChange={(name) => {
            if (name === "custom") void startCustom();
            else if (name) set({ vtable: name });
          }}
          searchable
          allowDeselect={false}
          maw={420}
        />
      )}
      {value.vtable === "custom" && !netcdf && (
        <Stack gap="xs">
          <Group gap="xs" align="flex-end">
            <Select
              size="xs"
              data={(tables.data ?? []).map((v) => v.name)}
              value={base}
              onChange={(name) => name && setBase(name)}
              searchable
              allowDeselect={false}
              w={220}
            />
            <Button size="xs" variant="light" onClick={() => void startCustom()}>
              {t("startFrom", { name: base })}
            </Button>
          </Group>
          <Textarea
            label={<FieldLabel label={t("customText")} info={t("customInfo")} />}
            value={value.custom_vtable}
            onChange={(e) => set({ custom_vtable: e.currentTarget.value })}
            autosize
            minRows={8}
            maxRows={20}
            spellCheck={false}
            styles={{ input: { fontFamily: "var(--mantine-font-family-monospace)", fontSize: 12, whiteSpace: "pre", overflowX: "auto" } }}
          />
          {validation.data &&
            (validation.data.problems.length === 0 ? (
              <Group gap={6}>
                <IconCircleCheck size={16} color="var(--mantine-color-teal-6)" />
                <Text size="sm">{t("valid")}</Text>
                {validation.data.fields.map((field) => (
                  <Badge key={field} size="xs" color="gray" variant="outline">
                    {field}
                  </Badge>
                ))}
              </Group>
            ) : (
              <Alert color="red" variant="light" icon={<IconAlertTriangle size={18} />}>
                {validation.data.problems.map((p) => (
                  <Text key={p} size="sm">
                    {p}
                  </Text>
                ))}
              </Alert>
            ))}
        </Stack>
      )}
    </Stack>
  );
}
