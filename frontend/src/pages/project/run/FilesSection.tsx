/**
 * Every WPS and WRF file of the project with the scripts of the method, for a cluster (Slurm) or a
 * Linux computer: options, preview of each file, extraction to a folder or a ZIP. The files are
 * those of the saved project; the options are remembered on this computer.
 */
import { Accordion, Alert, Badge, Button, Code, Group, List, Modal, SegmentedControl, SimpleGrid, Stack, Switch, Text, Textarea, TextInput, Tooltip } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { IconCheck, IconClock, IconDeviceDesktop, IconDownload, IconFolderDown, IconRefresh, IconTrash } from "@tabler/icons-react";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { type ComputingEstimate, DEFAULT_EXPORT, type ExportOptions, exportZipUrl, useComputingEstimate, useExportPreview, useExportToFolder } from "../../../api/method";
import { useLoadedDraft } from "../../../app/CaseDraft";
import { defineMessages, useFormat, useT } from "../../../i18n";
import { FieldLabel, NumberField } from "../../../ui/Inputs";
import { Fold } from "../../../ui/Fold";
import { HelpLink } from "../../../ui/Help";
import { PathInput } from "../../../ui/PathInput";
import { ErrorState, QueryView } from "../../../ui/States";
import { useProfiles } from "../../../api/system";
import { RunProgress } from "./RunProgress";
import { type FolderRole, useDeleteExtracted, useExtractedFolder, useFolderCheck } from "../../../api/fs";

const STORAGE_KEY = "ows.export.options";
const CPUS_PER_NODE = 48;

const messages = defineMessages({
  en: {
    title: "Files", paths: "Program folders", resources: "Processes", fileCount: "{n|# file|# files}",
    cluster: "Cluster (Slurm)",
    local: "Linux computer",
    wrfDir: "WRF folder",
    wpsDir: "WPS folder",
    geogDir: "Static geography (WPS_GEOG)",
    dataDir: "Input data folder (GFS, ERA5)",
    dataDirInfo: "Shared by all calculations. The scripts download the data there and ungrib reads it there. Files already present are not downloaded again.",
    foundBelow: "Folder used: {path}",
    pathsInfo: "Paths on the machine that runs WPS and WRF. Also editable at the top of each script.",
    cores: "WRF processes",
    coresInfoCluster: "srun -n. 48 CPUs per node: never saturate a node.",
    coresInfoLocal: "mpirun -np, at most the physical cores of the computer.",
    wpsCores: "geogrid / metgrid processes",
    wpsCoresInfo: "ungrib always runs alone.",
    inputs: "Input files",
    inputsInfo: "File pattern of each source, %Y = year.",
    slurm: "Slurm header",
    nodes: "Nodes",
    tasksPerNode: "Tasks per node",
    time: "Time limit",
    timeInfo: "72:00:00 at most.",
    partition: "Partition",
    wckey: "wckey",
    exclusive: "exclusive",
    turbo: "enable-turbo",
    editor: "Editor mode",
    editorInfo: "Header copied as is into each script, {job} = name of the job.",
    environment: "Environment lines",
    environmentInfo: "One command per line, run before the programs. Example: module load impi/2019.9.",
    environmentInfoLocal: "Run before the programs: source of the engine's env.sh (mpirun).",
    saturate: "{cores} processes on {nodes} × {cpus} CPUs: a node would be saturated.",
    tooLong: "Slurm jobs are limited to 72 hours here.",
    destination: "Destination folder",
    extract: "Extract all the files",
    zip: "Download the ZIP",
    saveFirst: "Save the project first: the files are generated from the saved version.",
    extracted: "Files written in {folder}",
    checks: "Method checks",
    preview: "Files",
    executable: "script",
    replace: "Replace",
    replaceInfo: "Downloaded data kept",
    remove: "Delete",
    removeTitle: "Delete {folder}?",
    cancel: "Cancel",
    filled: "Already filled",
    removed: "{folder} deleted",
    wrfTime: "WRF time",
    machine: "Machine",
    loads: { free: "Usable", busy: "Slowed", full: "Saturated", memory: "Short of memory" },
  },
  fr: {
    title: "Fichiers", paths: "Dossiers des programmes", resources: "Processus", fileCount: "{n|# fichier|# fichiers}",
    cluster: "Cluster (Slurm)",
    local: "Ordinateur Linux",
    wrfDir: "Dossier de WRF",
    wpsDir: "Dossier de WPS",
    geogDir: "Géographie statique (WPS_GEOG)",
    dataDir: "Dossier des données d'entrée (GFS, ERA5)",
    dataDirInfo: "Commun à tous les calculs. Les scripts y téléchargent les données et ungrib les y lit. Les fichiers présents ne sont pas retéléchargés.",
    foundBelow: "Dossier utilisé : {path}",
    pathsInfo: "Chemins sur la machine qui exécute WPS et WRF. Modifiables aussi en tête de chaque script.",
    cores: "Processus WRF",
    coresInfoCluster: "srun -n. 48 CPU par nœud : ne jamais saturer un nœud.",
    coresInfoLocal: "mpirun -np, au plus les cœurs physiques de l'ordinateur.",
    wpsCores: "Processus geogrid / metgrid",
    wpsCoresInfo: "ungrib tourne toujours seul.",
    inputs: "Fichiers d'entrée",
    inputsInfo: "Motif des fichiers de chaque source, %Y = année.",
    slurm: "En-tête Slurm",
    nodes: "Nœuds",
    tasksPerNode: "Tâches par nœud",
    time: "Durée maximale",
    timeInfo: "72:00:00 au plus.",
    partition: "Partition",
    wckey: "wckey",
    exclusive: "exclusive",
    turbo: "enable-turbo",
    editor: "Mode éditeur",
    editorInfo: "En-tête copié tel quel dans chaque script, {job} = nom du calcul.",
    environment: "Lignes d'environnement",
    environmentInfo: "Une commande par ligne, exécutée avant les programmes. Exemple : module load impi/2019.9.",
    environmentInfoLocal: "Exécutées avant les programmes : source du env.sh du moteur (mpirun).",
    saturate: "{cores} processus sur {nodes} × {cpus} CPU : un nœud serait saturé.",
    tooLong: "Les calculs Slurm sont limités à 72 heures ici.",
    destination: "Dossier de destination",
    extract: "Extraire tous les fichiers",
    zip: "Télécharger le zip",
    saveFirst: "Enregistrer d'abord le projet : les fichiers sont générés à partir de la version enregistrée.",
    extracted: "Fichiers écrits dans {folder}",
    checks: "Contrôles de la méthode",
    preview: "Fichiers",
    executable: "script",
    replace: "Remplacer",
    replaceInfo: "Données téléchargées gardées",
    remove: "Supprimer",
    removeTitle: "Supprimer {folder} ?",
    cancel: "Annuler",
    filled: "Déjà rempli",
    removed: "{folder} supprimé",
    wrfTime: "Temps WRF",
    machine: "Machine",
    loads: { free: "Utilisable", busy: "Ralentie", full: "Saturée", memory: "Mémoire juste" },
  },
});

type Target = ExportOptions["target"];

// A Linux computer starts empty: its folders, environment and cores come from the engine installed
const LOCAL_START: ExportOptions = { ...structuredClone(DEFAULT_EXPORT), target: "local", wrf_dir: "", wps_dir: "", geog_dir: "", data_dir: "", environment: [], cores: 0, wps_cores: 0 };

/** The options of each target, remembered separately (cluster paths are not those of a computer). */
function loadOptions(): Record<Target, ExportOptions> {
  const start = { cluster: structuredClone(DEFAULT_EXPORT), local: structuredClone(LOCAL_START) };
  try {
    for (const target of ["cluster", "local"] as const) {
      const saved = window.localStorage.getItem(`${STORAGE_KEY}.${target}`) ?? (target === "cluster" ? window.localStorage.getItem(STORAGE_KEY) : null);
      if (saved) {
        const parsed = JSON.parse(saved) as Partial<ExportOptions>;
        start[target] = { ...start[target], ...parsed, target, slurm: { ...DEFAULT_EXPORT.slurm, ...parsed.slurm }, inputs: {} };
      }
    }
  } catch {
    // Private window or blocked storage: the defaults
  }
  return start;
}

function loadTarget(): Target {
  try {
    return window.localStorage.getItem(`${STORAGE_KEY}.target`) === "local" ? "local" : "cluster";
  } catch {
    return "cluster";
  }
}

function saveOptions(options: Record<Target, ExportOptions>, target: Target) {
  try {
    // Input patterns belong to a project: not remembered across projects
    for (const each of ["cluster", "local"] as const) window.localStorage.setItem(`${STORAGE_KEY}.${each}`, JSON.stringify({ ...options[each], inputs: {} }));
    window.localStorage.setItem(`${STORAGE_KEY}.target`, target);
  } catch {
    // Not remembered: nothing else depends on it
  }
}

/** The paths of the default engine, as Files last took them (to know which fields still follow it). */
type EnginePaths = { wrf_dir: string; wps_dir: string; geog_dir: string; data_dir: string; env_setup: string };

function enginePaths(install?: { wrf_dir: string; wps_dir: string; geog_dir: string; input_dir: string; env_setup: string }): EnginePaths {
  return {
    wrf_dir: install?.wrf_dir ?? "",
    wps_dir: install?.wps_dir ?? "",
    geog_dir: install?.geog_dir ?? "",
    data_dir: install?.input_dir ?? "",
    env_setup: (install?.env_setup ?? "").split("\n").filter((line) => line.trim()).join("\n"),
  };
}

function loadEnginePaths(): EnginePaths | null {
  try {
    const saved = window.localStorage.getItem(`${STORAGE_KEY}.engine`);
    return saved ? (JSON.parse(saved) as EnginePaths) : null;
  } catch {
    return null;
  }
}

function saveEnginePaths(paths: EnginePaths) {
  try {
    window.localStorage.setItem(`${STORAGE_KEY}.engine`, JSON.stringify(paths));
  } catch {
    // Not remembered: a field equal to the engine's path still follows it
  }
}

/** The generated #SBATCH lines of a script, with the job name replaced by {job}. */
function generatedHeader(text: string, job: string): string {
  return text
    .split("\n")
    .filter((line) => line.startsWith("#SBATCH"))
    .map((line) => line.split(job).join("{job}"))
    .join("\n");
}

/** What the chosen cores do to the computer: free for other work, slowed, saturated, or short of memory. */
function machineLoad(estimate: ComputingEstimate, cores: number): "free" | "busy" | "full" | "memory" {
  if (estimate.memory_bytes + cores * estimate.process_bytes > 0.85 * estimate.memory_total) return "memory";
  const physical = estimate.physical_cores;
  if (cores >= physical) return "full";
  return cores >= physical - 1 ? "busy" : "free";
}

function hours(time: string): number {
  const match = /^(?:(\d+)-)?(\d+):(\d{2}):(\d{2})$/.exec(time);
  if (!match) return 0;
  return Number(match[1] ?? 0) * 24 + Number(match[2]) + Number(match[3]) / 60;
}

export function FilesSection() {
  const t = useT(messages);
  const format = useFormat();
  const { caseId, draft, dirty } = useLoadedDraft();
  const [byTarget, setByTarget] = useState(loadOptions);
  const [target, setTarget] = useState<Target>(loadTarget);
  const options = byTarget[target];
  // What is sent: at least one process while the cores of a computer are not known yet
  const sent = useMemo(() => ({ ...options, cores: options.cores || 1, wps_cores: options.wps_cores || 1 }), [options]);
  // The destination is remembered: coming back shows where its calculation stands
  const [folder, setFolder] = useState(() => {
    try {
      return window.localStorage.getItem(`${STORAGE_KEY}.destination`) ?? "";
    } catch {
      return "";
    }
  });
  useEffect(() => {
    try {
      window.localStorage.setItem(`${STORAGE_KEY}.destination`, folder);
    } catch {
      // Not remembered: typed again next time
    }
  }, [folder]);
  const preview = useExportPreview(draft, sent);
  const toFolder = useExportToFolder(caseId);
  const profiles = useProfiles();
  const cluster = target === "cluster";
  const client = useQueryClient();
  const extracted = useExtractedFolder(caseId, folder.trim());
  const remove = useDeleteExtracted(caseId);
  const [confirming, setConfirming] = useState(false);
  // On a Linux computer the folders are checked on the engine machine (WRF, WPS, the geography of
  // the resolution of each domain); they stop the extraction into that same machine
  const [checked] = useDebouncedValue(cluster ? null : { wrf_dir: options.wrf_dir, wps_dir: options.wps_dir, geog_dir: options.geog_dir }, 400);
  const geogRes = useMemo(() => (draft?.grid.domains ?? []).map((d) => d.geog_data_res), [draft]);
  const [destination] = useDebouncedValue(folder.trim(), 400);
  const check = useFolderCheck(cluster ? null : checked, geogRes, destination);
  const issues = cluster ? {} : (check.data?.issues ?? {});
  const foundBelow = cluster ? {} : (check.data?.found ?? {});
  const marks = [options.wrf_dir, options.wps_dir, options.geog_dir].filter(Boolean);
  const refresh = () => void client.invalidateQueries({ queryKey: ["extracted", caseId] });

  useEffect(() => saveOptions(byTarget, target), [byTarget, target]);
  const change = (edit: (o: ExportOptions) => void) =>
    setByTarget((current) => {
      const next = structuredClone(current);
      edit(next[target]);
      return next;
    });

  // A Linux computer: its paths follow the engine (Compute page). A field still empty, or still
  // equal to what the engine said last time, takes the engine's path; a field changed by hand stays
  // (it only holds for these files)
  useEffect(() => {
    const data = profiles.data;
    if (!data) return;
    const engine = data.profiles.find((p) => p.default) ?? data.profiles[0];
    const now = enginePaths(engine?.install);
    const before = loadEnginePaths();
    setByTarget((current) => {
      const local = current.local;
      const follow = (field: "wrf_dir" | "wps_dir" | "geog_dir" | "data_dir") => (!local[field] || local[field] === before?.[field] ? now[field] || local[field] : local[field]);
      const environment = local.environment.filter((line) => line.trim());
      const keepEnvironment = environment.length > 0 && (before === null || environment.join("\n") !== before.env_setup);
      const filled = {
        ...local,
        wrf_dir: follow("wrf_dir"),
        wps_dir: follow("wps_dir"),
        geog_dir: follow("geog_dir"),
        data_dir: follow("data_dir"),
        environment: keepEnvironment || !now.env_setup ? local.environment : now.env_setup.split("\n"),
        cores: local.cores || data.physical_cores || 1,
        wps_cores: local.wps_cores || data.physical_cores || 1,
      };
      return JSON.stringify(filled) === JSON.stringify(local) ? current : { ...current, local: filled };
    });
    if (engine) saveEnginePaths(now);
  }, [profiles.data]);

  const files = preview.data?.files ?? [];
  const manifest = useMemo(() => {
    const text = files.find((file) => file.path === "manifest.json")?.text;
    return text ? (JSON.parse(text) as { sources: { prefix: string; files: string }[] }) : null;
  }, [files]);
  const firstScript = files.find((file) => file.path.startsWith("wrf/run_wrf"));
  const job = firstScript ? (/#SBATCH --job-name=(\S+)/.exec(firstScript.text)?.[1] ?? "") : "";
  const saturated = cluster && (options.cores > options.slurm.nodes * CPUS_PER_NODE || (options.slurm.ntasks_per_node ?? 0) >= CPUS_PER_NODE);
  const blocked = !cluster && Boolean(check.data?.blocking);
  // Order of magnitude of WRF on this computer for the cores chosen (not known for a cluster)
  const estimate = useComputingEstimate(cluster ? undefined : draft).data;
  const wrfTime = estimate && options.cores > 0 ? estimate.core_seconds / Math.min(options.cores, estimate.physical_cores) : null;
  const load = estimate && options.cores > 0 ? machineLoad(estimate, options.cores) : null;
  const unavailable = dirty || preview.isFetching || !preview.data || Boolean(preview.error) || preview.data.issues.some((issue) => issue.severity === "error");

  return (
      <Stack gap="xl">
        <Group justify="space-between"><SegmentedControl value={target} onChange={(value) => setTarget(value as Target)} data={[{ value: "cluster", label: t("cluster") }, { value: "local", label: t("local") }]} maw={420} /><HelpLink topic="export" /></Group>

        <Fold title={t("paths")}><Stack gap="lg">
          {(["wrf_dir", "wps_dir", "geog_dir"] as const).map((field) => {
            const label = field === "wrf_dir" ? <FieldLabel label={t("wrfDir")} info={t("pathsInfo")} /> : t(field === "wps_dir" ? "wpsDir" : "geogDir");
            const set = (v: string) => change((o) => { o[field] = v; });
            const role: FolderRole = field === "wrf_dir" ? "wrf" : field === "wps_dir" ? "wps" : "geog";
            return cluster ? (
              <PathInput key={field} label={label} value={options[field]} onChange={set} machine={null} />
            ) : (
              <PathInput key={field} label={label} value={options[field]} onChange={set} machine="engine" expect={role} marks={marks} error={issues[field]} description={foundBelow[field] ? t("foundBelow", { path: foundBelow[field] }) : undefined} />
            );
          })}
          {!cluster && <PathInput label={<FieldLabel label={t("dataDir")} info={t("dataDirInfo")} />} value={options.data_dir} onChange={(v) => change((o) => { o.data_dir = v; })} machine="engine" marks={marks} />}
          <Textarea label={<FieldLabel label={t("environment")} info={cluster ? t("environmentInfo") : t("environmentInfoLocal")} />} autosize minRows={2} value={options.environment.join("\n")} onChange={(e) => { const lines = e.currentTarget.value.split("\n"); change((o) => { o.environment = lines; }); }} styles={{ input: { fontFamily: "var(--mantine-font-family-monospace)", fontSize: 13 } }} />
        </Stack></Fold>

        {manifest && manifest.sources.length > 0 && (
          <Fold title={t("inputs")}><Stack gap="lg">
            {manifest.sources.map((source) => (
              <TextInput key={source.prefix} label={<FieldLabel label={source.prefix} info={t("inputsInfo")} />} value={options.inputs[source.prefix] ?? source.files} onChange={(e) => { const v = e.currentTarget.value; change((o) => { o.inputs[source.prefix] = v; }); }} styles={{ input: { fontFamily: "var(--mantine-font-family-monospace)" } }} />
            ))}
          </Stack></Fold>
        )}

        <Fold title={t("resources")} aside={`${options.cores} WRF · ${options.wps_cores} WPS${wrfTime === null ? "" : ` · ≈ ${format.duration(wrfTime)}`}`}><SimpleGrid cols={{ base: 1, sm: 2 }} spacing="lg">
          <NumberField label={t("cores")} info={cluster ? t("coresInfoCluster") : t("coresInfoLocal")} min={1} allowDecimal={false} w="100%" value={options.cores} onValue={(v) => change((o) => { o.cores = v; })} />
          <NumberField label={t("wpsCores")} info={t("wpsCoresInfo")} min={1} allowDecimal={false} w="100%" value={options.wps_cores} onValue={(v) => change((o) => { o.wps_cores = v; })} />
          {wrfTime !== null && load && (
            <Group gap="lg" className="ows-estimate" data-load={load === "free" ? undefined : load === "busy" ? "busy" : "full"}>
              <Tooltip label={t("wrfTime")}><Group gap={6} c="dimmed"><IconClock size={15} stroke={1.7} />{`≈ ${format.duration(wrfTime)}`}</Group></Tooltip>
              <Tooltip label={t("machine")}><Group gap={6}><IconDeviceDesktop size={15} stroke={1.7} />{t(`loads.${load}`)}</Group></Tooltip>
            </Group>
          )}
        </SimpleGrid></Fold>

        {cluster && (
          <Fold title={t("slurm")} aside={options.slurm.raw === null ? `${options.slurm.nodes} × ${CPUS_PER_NODE} CPU · ${options.slurm.time}` : t("editor")}><Stack gap="lg">
            <Group justify="space-between">
              <Switch label={<FieldLabel label={t("editor")} info={t("editorInfo")} />} checked={options.slurm.raw !== null} onChange={(e) => { const on = e.currentTarget.checked; const header = firstScript ? generatedHeader(firstScript.text, job) : ""; change((o) => { o.slurm.raw = on ? header : null; }); }} />
            </Group>
            {options.slurm.raw === null ? (
              <>
                <SimpleGrid cols={{ base: 1, sm: 2, xl: 3 }} spacing="lg">
                  <NumberField label={t("nodes")} min={1} allowDecimal={false} value={options.slurm.nodes} onValue={(v) => change((o) => { o.slurm.nodes = v; })} />
                  <NumberField label={t("tasksPerNode")} min={1} max={CPUS_PER_NODE} allowDecimal={false} value={options.slurm.ntasks_per_node} onValue={(v) => change((o) => { o.slurm.ntasks_per_node = v; })} onClear={() => change((o) => { o.slurm.ntasks_per_node = null; })} />
                  <TextInput label={<FieldLabel label={t("time")} info={t("timeInfo")} />} value={options.slurm.time} onChange={(e) => { const v = e.currentTarget.value; change((o) => { o.slurm.time = v; }); }} />
                  <TextInput label={t("partition")} value={options.slurm.partition} onChange={(e) => { const v = e.currentTarget.value; change((o) => { o.slurm.partition = v; }); }} />
                  <TextInput label={t("wckey")} value={options.slurm.wckey} onChange={(e) => { const v = e.currentTarget.value; change((o) => { o.slurm.wckey = v; }); }} />
                </SimpleGrid>
                <Group gap="lg">
                  <Switch label={t("exclusive")} checked={options.slurm.exclusive} onChange={(e) => { const on = e.currentTarget.checked; change((o) => { o.slurm.exclusive = on; }); }} />
                  <Switch label={t("turbo")} checked={options.slurm.enable_turbo} onChange={(e) => { const on = e.currentTarget.checked; change((o) => { o.slurm.enable_turbo = on; }); }} />
                </Group>
              </>
            ) : (
              <Textarea autosize minRows={6} value={options.slurm.raw} onChange={(e) => { const v = e.currentTarget.value; change((o) => { o.slurm.raw = v; }); }} styles={{ input: { fontFamily: "var(--mantine-font-family-monospace)", fontSize: 13 } }} />
            )}
            {saturated && <Text size="sm" c="orange">{t("saturate", { cores: options.cores, nodes: options.slurm.nodes, cpus: CPUS_PER_NODE })}</Text>}
            {options.slurm.raw === null && hours(options.slurm.time) > 72 && <Text size="sm" c="orange">{t("tooLong")}</Text>}
          </Stack></Fold>
        )}

        {preview.data && preview.data.issues.length > 0 && (
          <Alert color="gray" title={t("checks")}>
            <List size="sm" spacing={4}>{preview.data.issues.map((issue, i) => <List.Item key={i}><Text size="sm" c={issue.severity === "error" ? "red" : undefined}>{issue.message}</Text></List.Item>)}</List>
          </Alert>
        )}

        <Stack gap="xs">
          <Group align="flex-end" gap="sm">
            <PathInput label={t("destination")} value={folder} onChange={(v) => { setFolder(v); toFolder.reset(); remove.reset(); }} kind="folder" example="folder" machine="here" writable marks={marks} error={extracted.data?.exists && !extracted.data.ours ? t("filled") : undefined} style={{ flex: 1, minWidth: 260 }} />
            {extracted.data?.ours ? (
              <>
                <Tooltip label={t("replaceInfo")}>
                  <Button leftSection={<IconRefresh size={18} />} disabled={unavailable || blocked} loading={toFolder.isPending} onClick={() => toFolder.mutate({ options: sent, folder: folder.trim(), replace: true }, { onSettled: refresh })}>{t("replace")}</Button>
                </Tooltip>
                <Button variant="default" color="red" leftSection={<IconTrash size={18} />} loading={remove.isPending} onClick={() => setConfirming(true)}>{t("remove")}</Button>
              </>
            ) : (
              <Button leftSection={<IconFolderDown size={18} />} disabled={unavailable || blocked || !folder.trim() || Boolean(extracted.data?.exists)} loading={toFolder.isPending} onClick={() => toFolder.mutate({ options: sent, folder: folder.trim() }, { onSettled: refresh })}>{t("extract")}</Button>
            )}
            <Button component="a" variant="default" leftSection={<IconDownload size={18} />} href={unavailable ? undefined : exportZipUrl(caseId, sent)} download="" data-disabled={unavailable || undefined} onClick={(e) => { if (unavailable) e.preventDefault(); }}>{t("zip")}</Button>
          </Group>
          {dirty && <Text size="sm" c="dimmed">{t("saveFirst")}</Text>}
          {toFolder.error && <ErrorState error={toFolder.error} />}
          {toFolder.data && (
            <Stack gap={6}>
              <Text size="sm">{t("extracted", { folder: toFolder.data.folder })}</Text>
              {/* The files written, one after the other, each with its tick */}
              <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing={4} verticalSpacing={2} className="ows-written">
                {toFolder.data.files.map((path, k) => (
                  <Group key={path} gap={6} wrap="nowrap" style={{ animationDelay: `${Math.min(k, 40) * 45}ms` }}>
                    <IconCheck size={14} color="var(--mantine-color-forest-6)" style={{ flex: "none" }} />
                    <Text size="xs" ff="monospace" truncate>{path}</Text>
                  </Group>
                ))}
              </SimpleGrid>
            </Stack>
          )}
          {remove.error && <ErrorState error={remove.error} />}
          {remove.data?.deleted && !toFolder.data && <Text size="sm">{t("removed", { folder: remove.data.folder })}</Text>}
        </Stack>

        {extracted.data?.ours && <RunProgress caseId={caseId} folder={folder.trim()} />}
        <Modal opened={confirming} onClose={() => setConfirming(false)} title={<Text fw={600}>{t("removeTitle", { folder: (extracted.data?.folder ?? "").split(/[\\/]/).pop() ?? "" })}</Text>} size="md" centered>
          <Text size="xs" ff="monospace" c="dimmed" mb="lg" style={{ wordBreak: "break-all" }}>{extracted.data?.folder}</Text>
          <Group justify="flex-end" gap="sm">
            <Button variant="default" onClick={() => setConfirming(false)}>{t("cancel")}</Button>
            <Button color="red" leftSection={<IconTrash size={18} />} onClick={() => { setConfirming(false); toFolder.reset(); remove.mutate(folder.trim(), { onSettled: refresh }); }}>{t("remove")}</Button>
          </Group>
        </Modal>

        <Fold lazy title={t("preview")} aside={t("fileCount", { n: files.length })}><QueryView query={preview}>
          {(data) => (
            <Accordion variant="contained">
              {data.files.map((file) => (
                <Accordion.Item key={file.path} value={file.path}>
                  <Accordion.Control><Group gap="xs"><Text size="sm" ff="monospace">{file.path}</Text>{file.executable && <Badge size="xs" variant="light">{t("executable")}</Badge>}</Group></Accordion.Control>
                  <Accordion.Panel><Code block style={{ maxHeight: 480, overflow: "auto", whiteSpace: "pre" }}>{file.text}</Code></Accordion.Panel>
                </Accordion.Item>
              ))}
            </Accordion>
          )}
        </QueryView></Fold>
      </Stack>
  );
}
