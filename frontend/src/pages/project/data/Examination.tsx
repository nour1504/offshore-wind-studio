import { Alert, Badge, Button, Collapse, Group, List, Paper, SimpleGrid, Stack, Table, Text } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { IconAlertTriangle, IconCircleCheck, IconCircleX, IconInfoCircle, IconListSearch } from "@tabler/icons-react";
import { useState } from "react";

import { type Examination as Report, type FileRole, type LevelKind, useExamination } from "../../../api/data";
import { useLoadedDraft } from "../../../app/CaseDraft";
import { defineMessages, useFormat, useT } from "../../../i18n";
import { ErrorState } from "../../../ui/States";

const messages = defineMessages({
  en: {
    examine: "Examine the files",
    again: "Examine again",
    examining: "Reading the files…",
    intro:
      "Reads the files as WPS will: fields, levels, times, grid, area, and errors that would stop ungrib, metgrid or real.exe.",
    netcdf: "NetCDF · converted before the run",
    grib: "GRIB {editions}",
    files: "{n|# file|# files}",
    records: "{n|# field record|# field records}",
    period: "{first} → {last} · every {step} h",
    oneTime: "Single time: {time}",
    levels: "{n|# pressure level|# pressure levels} ({top}–{bottom} hPa)",
    soil: "{n|# soil field|# soil fields}",
    unused: "{n|# record|# records} not read by this table",
    noProblem: "No problem: files readable by WPS for this period and these domains.",
    sstPass: "SST pass of ungrib: {start} → {end} (SST times around the run, interpolated in between).",
    suggestions: "Standard tables for these files",
    table: "Table",
    fieldsCount: "Fields",
    required: "Required fields",
    used: "Records used",
    use: "Use",
    inUse: "In use",
    showFields: "Show the fields",
    hideFields: "Hide the fields",
    field: "Field",
    kind: "Level",
    levelCount: "Levels",
    times: "Times",
    written: "Written",
    derivedOnly: "read to derive other fields",
    kinds: {
      pressure: "pressure levels",
      surface: "surface",
      "sea level": "sea level",
      "model level": "model levels",
      soil: "soil layer",
      other: "other",
    },
  },
  fr: {
    examine: "Examiner les fichiers",
    again: "Examiner à nouveau",
    examining: "Lecture des fichiers…",
    intro:
      "Lecture des fichiers comme le fera WPS : champs, niveaux, échéances, grille, zone, et erreurs bloquantes pour ungrib, metgrid ou real.exe.",
    netcdf: "NetCDF · converti avant le calcul",
    grib: "GRIB {editions}",
    files: "{n|# fichier|# fichiers}",
    records: "{n|# enregistrement de champ|# enregistrements de champs}",
    period: "{first} → {last} · toutes les {step} h",
    oneTime: "Une seule échéance : {time}",
    levels: "{n|# niveau de pression|# niveaux de pression} ({top}–{bottom} hPa)",
    soil: "{n|# champ de sol|# champs de sol}",
    unused: "{n|# enregistrement non lu|# enregistrements non lus} par cette table",
    noProblem: "Aucun problème : fichiers lisibles par WPS pour cette période et ces domaines.",
    sstPass:
      "Passage SST d'ungrib : {start} → {end} (échéances SST qui encadrent le calcul, interpolées entre elles).",
    suggestions: "Tables standard pour ces fichiers",
    table: "Table",
    fieldsCount: "Champs",
    required: "Champs indispensables",
    used: "Enregistrements lus",
    use: "Utiliser",
    inUse: "Utilisée",
    showFields: "Afficher les champs",
    hideFields: "Masquer les champs",
    field: "Champ",
    kind: "Niveau",
    levelCount: "Niveaux",
    times: "Échéances",
    written: "Écrit",
    derivedOnly: "lu pour dériver d'autres champs",
    kinds: {
      pressure: "niveaux de pression",
      surface: "surface",
      "sea level": "niveau de la mer",
      "model level": "niveaux du modèle",
      soil: "couche de sol",
      other: "autre",
    },
  },
});

const ICONS = {
  error: <IconCircleX size={16} color="var(--mantine-color-red-6)" />,
  warning: <IconAlertTriangle size={16} color="var(--mantine-color-orange-6)" />,
  info: <IconInfoCircle size={16} color="var(--mantine-color-blue-6)" />,
};

interface Props {
  role: FileRole;
  /** Called with a standard table chosen among the suggestions */
  onUseVtable?: (name: string) => void;
}

/** What WPS will read in the case's own files, examined on demand and kept up to date. */
export function Examination({ role, onUseVtable }: Props) {
  const t = useT(messages);
  const { draft } = useLoadedDraft();
  const [asked, setAsked] = useState(false);
  const query = useExamination(draft, role, asked);
  const report = query.data;

  return (
    <Paper withBorder radius="md" p="md">
      <Stack gap="sm">
        <Group justify="space-between" gap="sm" wrap="wrap">
          <Text size="sm" c="dimmed" maw={620}>
            {t("intro")}
          </Text>
          <Button
            size="xs"
            variant={report ? "default" : "light"}
            leftSection={<IconListSearch size={16} />}
            loading={query.isFetching}
            onClick={() => (asked ? void query.refetch() : setAsked(true))}
          >
            {report ? t("again") : t("examine")}
          </Button>
        </Group>
        {query.isFetching && !report && (
          <Text size="sm" c="dimmed">
            {t("examining")}
          </Text>
        )}
        {query.error ? <ErrorState error={query.error} onRetry={() => void query.refetch()} /> : null}
        {report && <ReportView report={report} onUseVtable={onUseVtable} />}
      </Stack>
    </Paper>
  );
}

function ReportView({ report, onUseVtable }: { report: Report; onUseVtable?: (name: string) => void }) {
  const t = useT(messages);
  const f = useFormat();
  const [fieldsOpen, fields] = useDisclosure(false);
  const levels = report.pressure_levels_hpa;
  const problems = report.findings.filter((x) => x.severity !== "info");
  const notes = report.findings.filter((x) => x.severity === "info");

  return (
    <Stack gap="sm">
      <Group gap="xs">
        <Badge color={report.format === "netcdf" ? "gray" : "teal"} variant="light">
          {report.format === "netcdf" ? t("netcdf") : t("grib", { editions: report.editions.join(" + ") || "?" })}
        </Badge>
        {report.centres.map((centre) => (
          <Badge key={centre} color="gray" variant="outline">
            {centre}
          </Badge>
        ))}
        {report.grids.map((grid) => (
          <Badge key={grid} color="gray" variant="outline" tt="none">
            {grid}
          </Badge>
        ))}
      </Group>
      <SimpleGrid cols={{ base: 1, sm: 2 }} spacing={4}>
        <Text size="sm">
          {t("files", { n: report.files })} · {t("records", { n: report.messages })}
        </Text>
        {report.first && report.last && (
          <Text size="sm">
            {report.first === report.last
              ? t("oneTime", { time: f.dateTime(report.first) })
              : t("period", { first: f.dateTime(report.first), last: f.dateTime(report.last), step: f.number(report.step_hours, 0) })}
          </Text>
        )}
        {levels.length > 0 && (
          <Text size="sm">
            {t("levels", { n: levels.length, top: f.number(levels[0], 0), bottom: f.number(levels[levels.length - 1], 0) })}
          </Text>
        )}
        {report.soil_fields.length > 0 && <Text size="sm">{t("soil", { n: report.soil_fields.length })}</Text>}
        {report.unused_messages > 0 && (
          <Text size="sm" c="dimmed">
            {t("unused", { n: report.unused_messages })}
          </Text>
        )}
      </SimpleGrid>

      {problems.length === 0 && report.fields.length > 0 ? (
        <Alert color="teal" variant="light" icon={<IconCircleCheck size={18} />}>
          {t("noProblem")}
        </Alert>
      ) : (
        <List spacing={6} size="sm">
          {problems.map((finding, i) => (
            <List.Item key={i} icon={ICONS[finding.severity]}>
              {finding.message}
            </List.Item>
          ))}
        </List>
      )}
      {(notes.length > 0 || report.window) && (
        <List spacing={4} size="sm" c="dimmed">
          {notes.map((finding, i) => (
            <List.Item key={i} icon={ICONS.info}>
              {finding.message}
            </List.Item>
          ))}
          {report.window && (
            <List.Item icon={ICONS.info}>
              {t("sstPass", { start: f.dateTime(report.window[0]), end: f.dateTime(report.window[1]) })}
            </List.Item>
          )}
        </List>
      )}

      {report.format === "grib" && report.suggestions.length > 0 && (
        <Stack gap={4}>
          <Text size="sm" fw={600}>
            {t("suggestions")}
          </Text>
          <Table.ScrollContainer minWidth={480}>
            <Table verticalSpacing={4}>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>{t("table")}</Table.Th>
                  <Table.Th ta="right">{t("fieldsCount")}</Table.Th>
                  <Table.Th>{t("required")}</Table.Th>
                  <Table.Th ta="right">{t("used")}</Table.Th>
                  <Table.Th />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {report.suggestions.map((s) => (
                  <Table.Tr key={s.vtable}>
                    <Table.Td className="ows-mono">{s.vtable}</Table.Td>
                    <Table.Td ta="right" className="ows-num">
                      {s.fields}
                    </Table.Td>
                    <Table.Td>{s.required_ok ? <IconCircleCheck size={16} color="var(--mantine-color-teal-6)" /> : ICONS.error}</Table.Td>
                    <Table.Td ta="right" className="ows-num">
                      {f.percent(s.used_share, 0)}
                    </Table.Td>
                    <Table.Td ta="right">
                      {s.vtable === report.vtable ? (
                        <Text size="xs" c="dimmed">
                          {t("inUse")}
                        </Text>
                      ) : (
                        onUseVtable && (
                          <Button size="compact-xs" variant="light" onClick={() => onUseVtable(s.vtable)}>
                            {t("use")}
                          </Button>
                        )
                      )}
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Stack>
      )}

      {report.fields.length > 0 && (
        <Stack gap={4}>
          <Group>
            <Button variant="subtle" size="compact-xs" onClick={fields.toggle}>
              {fieldsOpen ? t("hideFields") : t("showFields")}
            </Button>
          </Group>
          <Collapse expanded={fieldsOpen}>
            <Table.ScrollContainer minWidth={420} mah={320}>
              <Table stickyHeader verticalSpacing={2}>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>{t("field")}</Table.Th>
                    <Table.Th>{t("kind")}</Table.Th>
                    <Table.Th ta="right">{t("levelCount")}</Table.Th>
                    <Table.Th ta="right">{t("times")}</Table.Th>
                    <Table.Th>{t("written")}</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {report.fields.map((field) => (
                    <Table.Tr key={`${field.name}-${field.kind}`}>
                      <Table.Td className="ows-mono">{field.name}</Table.Td>
                      <Table.Td>{t(`kinds.${field.kind}` as `kinds.${LevelKind}`)}</Table.Td>
                      <Table.Td ta="right" className="ows-num">
                        {field.kind === "pressure" || field.kind === "model level" ? field.levels : "–"}
                      </Table.Td>
                      <Table.Td ta="right" className="ows-num">
                        {field.times}
                      </Table.Td>
                      <Table.Td>
                        {field.output ? (
                          <IconCircleCheck size={14} color="var(--mantine-color-teal-6)" />
                        ) : (
                          <Text size="xs" c="dimmed">
                            {t("derivedOnly")}
                          </Text>
                        )}
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          </Collapse>
        </Stack>
      )}
    </Stack>
  );
}
