import {
  Alert,
  Button,
  Checkbox,
  Divider,
  Group,
  List,
  Loader,
  Modal,
  Paper,
  ScrollArea,
  SegmentedControl,
  Select,
  Stack,
  Text,
  Tooltip,
} from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { IconTrash } from "@tabler/icons-react";
import { useMemo, useState } from "react";

import { useCases } from "../../api/cases";
import { useStorage } from "../../api/system";
import type { StorageRun, StorageUsage } from "../../api/types";
import { common } from "../../i18n/common";
import { defineMessages, useFormat, useT } from "../../i18n";
import { type Column, DataTable } from "../../ui/DataTable";
import { FieldLabel } from "../../ui/Inputs";
import { Fold } from "../../ui/Fold";
import { FoundTree } from "../../ui/FoundTree";
import { StateBadge } from "../../ui/Stat";
import { QueryView } from "../../ui/States";
import { PathLine } from "./CopyPath";
import { locationMessages } from "./labels";
import {
  type InputFolder,
  type InputFolderSize,
  isActive,
  joinPath,
  runKey,
  runStart,
  useCleanup,
  useInputFolderSizes,
} from "./queries";

type Mode = "delete" | "intermediates";

const messages = defineMessages({
  en: {
    title: "Cleanup",
    runs: "Runs",
    project: "Project",
    allProjects: "All projects",
    run: "Start (UTC)",
    state: "State",
    total: "Total",
    outputs: "Outputs",
    other: "Other files",
    otherInfo: "Prepared files, logs, run details.",
    selectAll: "Select every run shown",
    selectRun: "Select the run {run} of {project}",
    activeRun: "Queued or running",
    noRuns: "No run",
    noRunsFiltered: "No run for this project",
    delete: "Whole run",
    deleteText: "Whole folder: snapshot, prepared files, logs, outputs. Removed from the history.",
    intermediates: "Prepared files",
    intermediatesText: "Namelists, turbine tables, tslist (generated folders). Outputs, logs and history kept.",
    inputs: "Downloaded data",
    inputsText: "Downloaded again when needed: GFS (NOAA), ERA5 (Copernicus CDS, can take hours).",
    source: "Source",
    size: "Size",
    files: "Files",
    folder: "Folder",
    selectInput: "Select {source}",
    empty: "Empty",
    unreadable: "Unknown: {error}",
    untouched: "This computer only. WPS cache and compute machines untouched.",
    nothing: "Nothing selected",
    summary: "{runs|# run|# runs} · {inputs|# folder|# folders} · {size}",
    upTo: "up to {size}",
    review: "Delete…",
    confirmTitle: "Delete these files?",
    confirmRuns: "Runs deleted ({n})",
    confirmIntermediates: "Prepared files deleted ({n})",
    confirmInputs: "Folders emptied ({n})",
    atMost: "at most {size}",
    freed: "Space freed",
    freeAfter: "Free afterwards: about {size}",
    irreversible: "Irreversible.",
    confirm: "Delete",
    done: "{n|# item deleted|# items deleted} · {size} freed",
    failed: "Cleanup stopped",
  },
  fr: {
    title: "Nettoyage",
    runs: "Calculs",
    project: "Projet",
    allProjects: "Tous les projets",
    run: "Début (UTC)",
    state: "État",
    total: "Total",
    outputs: "Sorties",
    other: "Autres fichiers",
    otherInfo: "Fichiers préparés, journaux, détails du calcul.",
    selectAll: "Sélectionner tous les calculs affichés",
    selectRun: "Sélectionner le calcul {run} de {project}",
    activeRun: "En file d'attente ou en cours",
    noRuns: "Aucun calcul",
    noRunsFiltered: "Aucun calcul pour ce projet",
    delete: "Calcul entier",
    deleteText: "Tout le dossier : copie du cas, fichiers préparés, journaux, sorties. Retiré de l'historique.",
    intermediates: "Fichiers préparés",
    intermediatesText: "Namelists, tables d'éoliennes, tslist (dossiers generated). Sorties, journaux et historique conservés.",
    inputs: "Données téléchargées",
    inputsText: "Téléchargées à nouveau si besoin : GFS (NOAA), ERA5 (CDS de Copernicus, parfois des heures).",
    source: "Source",
    size: "Taille",
    files: "Fichiers",
    folder: "Dossier",
    selectInput: "Sélectionner {source}",
    empty: "Vide",
    unreadable: "Inconnue : {error}",
    untouched: "Cet ordinateur seulement. Cache WPS et machines de calcul non touchés.",
    nothing: "Rien de sélectionné",
    summary: "{runs|# calcul|# calculs} · {inputs|# dossier|# dossiers} · {size}",
    upTo: "jusqu'à {size}",
    review: "Supprimer…",
    confirmTitle: "Supprimer ces fichiers ?",
    confirmRuns: "Calculs supprimés ({n})",
    confirmIntermediates: "Fichiers préparés supprimés ({n})",
    confirmInputs: "Dossiers vidés ({n})",
    atMost: "au plus {size}",
    freed: "Espace libéré",
    freeAfter: "Libre ensuite : environ {size}",
    irreversible: "Irréversible.",
    confirm: "Supprimer",
    done: "{n|# élément supprimé|# éléments supprimés} · {size} libérés",
    failed: "Nettoyage interrompu",
  },
});

interface Plan {
  mode: Mode;
  runs: StorageRun[];
  inputs: InputFolderSize[];
  /** Bytes known exactly: whole runs and input folders */
  exact: number;
  /** Upper bound of the prepared files (their size is not measured separately) */
  upTo: number;
}

const otherBytes = (run: StorageRun) => Math.max(0, run.bytes - run.outputs_bytes);

function Cleanup({ storage }: { storage: StorageUsage }) {
  const t = useT(messages);
  const tl = useT(locationMessages);
  const f = useFormat();
  const cases = useCases();
  const cleanup = useCleanup();
  const [project, setProject] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [inputs, setInputs] = useState<Set<InputFolder>>(() => new Set());
  // The download folder whose files are shown
  const [shown, setShown] = useState<InputFolder | null>(null);
  const [mode, setMode] = useState<Mode>("delete");
  const [confirming, { open, close }] = useDisclosure(false);

  const names = useMemo(() => new Map((cases.data ?? []).map((c) => [c.id, c.name])), [cases.data]);
  const nameOf = (id: string) => names.get(id) ?? id;
  const inputRoot = storage.downloads_root || (storage.locations.find((l) => l.key === "input")?.path ?? joinPath(storage.data_root, "cache"));
  const sizes = useInputFolderSizes(inputRoot);
  const shownTree = sizes.find((s) => s.source === shown && s.files)?.tree ?? null;

  const projects = [...new Set(storage.runs.map((r) => r.case))];
  const visible = project ? storage.runs.filter((r) => r.case === project) : storage.runs;
  const selectable = visible.filter((r) => !isActive(r.state));
  const allChecked = selectable.length > 0 && selectable.every((r) => selected.has(runKey(r)));
  const someChecked = selectable.some((r) => selected.has(runKey(r)));

  // Only runs that still exist and are not active count, whatever the filter shows
  const chosenRuns = storage.runs.filter((r) => selected.has(runKey(r)) && !isActive(r.state));
  const chosenInputs = sizes.filter((s) => inputs.has(s.source) && (s.bytes ?? 0) > 0);
  const plan: Plan = {
    mode,
    runs: chosenRuns,
    inputs: chosenInputs,
    exact:
      (mode === "delete" ? chosenRuns.reduce((sum, r) => sum + r.bytes, 0) : 0) +
      chosenInputs.reduce((sum, s) => sum + (s.bytes ?? 0), 0),
    upTo: mode === "intermediates" ? chosenRuns.reduce((sum, r) => sum + otherBytes(r), 0) : 0,
  };
  const anything = chosenRuns.length + chosenInputs.length > 0;
  const freedText = (p: Plan) => (p.upTo > 0 ? t("upTo", { size: f.bytes(p.exact + p.upTo) }) : f.bytes(p.exact));

  const toggle = (key: string, on: boolean) =>
    setSelected((previous) => {
      const next = new Set(previous);
      if (on) next.add(key);
      else next.delete(key);
      return next;
    });

  const toggleVisible = (on: boolean) =>
    setSelected((previous) => {
      const next = new Set(previous);
      for (const r of selectable) {
        if (on) next.add(runKey(r));
        else next.delete(runKey(r));
      }
      return next;
    });

  const submit = () => {
    const before = storage.free_bytes;
    const keysOf = chosenRuns.map(runKey);
    cleanup.mutate(
      {
        runs: mode === "delete" ? keysOf : [],
        intermediates: mode === "intermediates" ? keysOf : [],
        inputs: chosenInputs.map((s) => s.source),
      },
      {
        onSuccess: (result) => {
          close();
          setSelected(new Set());
          setInputs(new Set());
          notifications.show({
            color: "teal",
            message: t("done", { n: result.done.length, size: f.bytes(Math.max(0, result.free_bytes - before)) }),
          });
        },
        onError: (error) => {
          close();
          notifications.show({ color: "red", title: t("failed"), message: error.message });
        },
      },
    );
  };

  const columns: Column<StorageRun>[] = [
    {
      key: "select",
      width: 40,
      header: (
        <Checkbox
          aria-label={t("selectAll")}
          checked={allChecked}
          indeterminate={someChecked && !allChecked}
          disabled={selectable.length === 0}
          onChange={(e) => toggleVisible(e.currentTarget.checked)}
        />
      ),
      render: (r) => {
        const active = isActive(r.state);
        const box = (
          <Checkbox
            aria-label={t("selectRun", { run: r.run, project: nameOf(r.case) })}
            checked={!active && selected.has(runKey(r))}
            disabled={active}
            onChange={(e) => toggle(runKey(r), e.currentTarget.checked)}
          />
        );
        return active ? (
          <Tooltip label={t("activeRun")}>
            <span>{box}</span>
          </Tooltip>
        ) : (
          box
        );
      },
    },
    {
      key: "project",
      header: t("project"),
      render: (r) => <Text size="sm">{nameOf(r.case)}</Text>,
      sortValue: (r) => nameOf(r.case).toLowerCase(),
    },
    {
      key: "run",
      header: t("run"),
      render: (r) => {
        const start = runStart(r.run);
        return (
          <Stack gap={0}>
            {start && (
              <Text size="sm" className="ows-num" style={{ whiteSpace: "nowrap" }}>
                {f.dateTime(start)}
              </Text>
            )}
            <Text size="xs" c="dimmed" className="ows-mono">
              {r.run}
            </Text>
          </Stack>
        );
      },
      sortValue: (r) => r.run,
    },
    {
      key: "state",
      header: t("state"),
      render: (r) => <StateBadge state={r.state} />,
      sortValue: (r) => r.state,
    },
    {
      key: "total",
      header: t("total"),
      align: "right",
      render: (r) => <span style={{ whiteSpace: "nowrap" }}>{f.bytes(r.bytes)}</span>,
      sortValue: (r) => r.bytes,
    },
    {
      key: "outputs",
      header: t("outputs"),
      align: "right",
      render: (r) => <span style={{ whiteSpace: "nowrap" }}>{f.bytes(r.outputs_bytes)}</span>,
      sortValue: (r) => r.outputs_bytes,
    },
    {
      key: "other",
      header: <FieldLabel label={t("other")} info={t("otherInfo")} />,
      align: "right",
      render: (r) => <span style={{ whiteSpace: "nowrap" }}>{f.bytes(otherBytes(r))}</span>,
      sortValue: otherBytes,
    },
  ];

  const toggleInput = (source: InputFolder, on: boolean) =>
    setInputs((previous) => {
      const next = new Set(previous);
      if (on) next.add(source);
      else next.delete(source);
      return next;
    });
  const inputColumns: Column<InputFolderSize>[] = [
    {
      key: "select",
      width: 40,
      header: "",
      render: (s) => (
        <Checkbox
          aria-label={t("selectInput", { source: tl(`sources.${s.source}`) })}
          checked={inputs.has(s.source) && s.bytes !== 0}
          disabled={s.loading || s.bytes === 0 || s.bytes === null}
          onClick={(e) => e.stopPropagation()}
          onChange={(e) => toggleInput(s.source, e.currentTarget.checked)}
        />
      ),
    },
    { key: "source", header: t("source"), render: (s) => <Text size="sm">{s.source.toUpperCase()}</Text>, sortValue: (s) => s.source },
    {
      key: "size",
      header: t("size"),
      align: "right",
      render: (s) => {
        if (s.loading) return <Loader size="xs" aria-label={tl(`sources.${s.source}`)} />;
        if (s.error) return <Text size="sm" c="red">{t("unreadable", { error: s.error })}</Text>;
        return (
          <Text size="sm" c={s.bytes === 0 ? "dimmed" : undefined} style={{ whiteSpace: "nowrap" }}>
            {s.bytes === 0 ? t("empty") : f.bytes(s.bytes)}
          </Text>
        );
      },
      sortValue: (s) => s.bytes,
    },
    { key: "files", header: t("files"), align: "right", render: (s) => <span>{s.files === null ? "" : f.number(s.files, 0)}</span>, sortValue: (s) => s.files },
    { key: "folder", header: t("folder"), render: (s) => <PathLine path={s.path} name={tl(`sources.${s.source}`)} size="xs" />, sortValue: (s) => s.path },
  ];

  return (
    <Stack gap="xl" className="ows-cleanup">
      <Stack gap="xs">
        <Group justify="space-between" wrap="wrap" gap="sm" className="ows-cleanup-head">
          <Text fw={600} size="sm">
            {t("runs")}{" "}
            <Text span c="dimmed" size="sm" className="ows-num">
              {storage.runs.length}
            </Text>
          </Text>
          <Group gap="sm" wrap="wrap">
            {projects.length > 1 && (
              <Select
                aria-label={t("project")}
                size="xs"
                w={200}
                value={project}
                onChange={setProject}
                placeholder={t("allProjects")}
                clearable
                data={projects.map((id) => ({ value: id, label: nameOf(id) }))}
              />
            )}
            <SegmentedControl
              size="xs"
              value={mode}
              onChange={(v) => setMode(v as Mode)}
              disabled={storage.runs.length === 0}
              data={(["delete", "intermediates"] as const).map((value) => ({
                value,
                label: <FieldLabel label={t(value)} info={t(value === "delete" ? "deleteText" : "intermediatesText")} />,
              }))}
            />
          </Group>
        </Group>
        <Paper withBorder>
          <DataTable<StorageRun>
            caption={t("runs")}
            columns={columns}
            rows={visible}
            rowKey={runKey}
            empty={storage.runs.length === 0 ? t("noRuns") : t("noRunsFiltered")}
            maxHeight={420}
          />
        </Paper>
      </Stack>

      <Stack gap="xs">
        <Group justify="space-between" wrap="wrap" gap="sm" className="ows-cleanup-head">
          <Text fw={600} size="sm" component="div">
            <FieldLabel label={t("inputs")} info={t("inputsText")} />
          </Text>
        </Group>
        <Paper withBorder>
          <DataTable<InputFolderSize> caption={t("inputs")} columns={inputColumns} rows={sizes} rowKey={(s) => s.source}
            selected={shown} onRowClick={(s) => setShown(shown === s.source || !s.files ? null : s.source)} />
        </Paper>
        {shownTree && <FoundTree summary={shownTree} />}
      </Stack>

      <Group justify="space-between" wrap="wrap" gap="sm" className="ows-cleanup-bar">
        <Stack gap={2}>
          <Text size="sm" fw={600} className="ows-num" aria-live="polite" c={anything ? undefined : "dimmed"}>
            {anything
              ? t("summary", { runs: chosenRuns.length, inputs: chosenInputs.length, size: freedText(plan) })
              : t("nothing")}
          </Text>
          <Text size="xs" c="dimmed">
            {t("untouched")}
          </Text>
        </Stack>
        <Button color="red" leftSection={<IconTrash size={16} aria-hidden />} disabled={!anything} onClick={open}>
          {t("review")}
        </Button>
      </Group>

      <ConfirmCleanup
        opened={confirming}
        onClose={close}
        onConfirm={submit}
        loading={cleanup.isPending}
        plan={plan}
        freeBytes={storage.free_bytes}
        nameOf={nameOf}
        freedText={freedText(plan)}
      />
    </Stack>
  );
}

/** Lists exactly what is about to be deleted, with the space it frees. */
function ConfirmCleanup({
  opened,
  onClose,
  onConfirm,
  loading,
  plan,
  freeBytes,
  nameOf,
  freedText,
}: {
  opened: boolean;
  onClose: () => void;
  onConfirm: () => void;
  loading: boolean;
  plan: Plan;
  freeBytes: number;
  nameOf: (id: string) => string;
  freedText: string;
}) {
  const t = useT(messages);
  const tc = useT(common);
  const tl = useT(locationMessages);
  const f = useFormat();

  const runLabel = (r: StorageRun) => {
    const start = runStart(r.run);
    return `${nameOf(r.case)} · ${start ? f.dateTime(start) : r.run}`;
  };

  return (
    <Modal
      opened={opened}
      onClose={loading ? () => undefined : onClose}
      closeOnClickOutside={!loading}
      closeOnEscape={!loading}
      title={<Text fw={600}>{t("confirmTitle")}</Text>}
      size="lg"
    >
      <Stack>
        <ScrollArea.Autosize mah={340} type="auto" offsetScrollbars>
          <Stack gap="md">
            {plan.runs.length > 0 && (
              <Stack gap={4}>
                <Text size="sm" fw={600}>
                  {plan.mode === "delete"
                    ? t("confirmRuns", { n: plan.runs.length })
                    : t("confirmIntermediates", { n: plan.runs.length })}
                </Text>
                <List size="sm" spacing={2}>
                  {plan.runs.map((r) => (
                    <List.Item key={runKey(r)}>
                      <Text size="sm" span>
                        {runLabel(r)} —{" "}
                        <span className="ows-num">
                          {plan.mode === "delete" ? f.bytes(r.bytes) : t("atMost", { size: f.bytes(otherBytes(r)) })}
                        </span>
                      </Text>
                      <Text size="xs" c="dimmed" className="ows-mono" style={{ overflowWrap: "anywhere" }}>
                        {plan.mode === "delete" ? r.path : `${joinPath(r.path, "generated")}, ${joinPath(r.path, "generated-control")}`}
                      </Text>
                    </List.Item>
                  ))}
                </List>
              </Stack>
            )}
            {plan.inputs.length > 0 && (
              <Stack gap={4}>
                <Text size="sm" fw={600}>
                  {t("confirmInputs", { n: plan.inputs.length })}
                </Text>
                <List size="sm" spacing={2}>
                  {plan.inputs.map((s) => (
                    <List.Item key={s.source}>
                      <Text size="sm" span>
                        {tl(`sources.${s.source}`)} — <span className="ows-num">{f.bytes(s.bytes)}</span>
                      </Text>
                      <Text size="xs" c="dimmed" className="ows-mono" style={{ overflowWrap: "anywhere" }}>
                        {s.path}
                      </Text>
                    </List.Item>
                  ))}
                </List>
              </Stack>
            )}
          </Stack>
        </ScrollArea.Autosize>

        <Divider />
        <Group justify="space-between" wrap="wrap">
          <Text size="sm" fw={600}>
            {t("freed")}
          </Text>
          <Text size="sm" fw={600} className="ows-num">
            {freedText}
          </Text>
        </Group>
        <Text size="xs" c="dimmed">
          {t("freeAfter", { size: f.bytes(freeBytes + plan.exact + plan.upTo) })}
        </Text>

        <Alert color="red" variant="light" icon={<IconTrash size={18} />} py="xs">
          <Stack gap={4}>
            <Text size="sm" fw={600}>
              {t("irreversible")}
            </Text>
            <Text size="sm">{t("untouched")}</Text>
          </Stack>
        </Alert>

        <Group justify="flex-end">
          <Button variant="default" onClick={onClose} disabled={loading} data-autofocus>
            {tc("cancel")}
          </Button>
          <Button color="red" onClick={onConfirm} loading={loading} leftSection={<IconTrash size={16} aria-hidden />}>
            {t("confirm")}
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}

/** Deleting runs, their prepared files or downloaded input data, after an exact confirmation. */
export function CleanupSection() {
  const t = useT(messages);
  const storage = useStorage();
  return (
    <Fold title={t("title")} help="storage">
      <QueryView query={storage}>{(data) => <Cleanup storage={data} />}</QueryView>
    </Fold>
  );
}
