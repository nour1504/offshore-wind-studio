/**
 * Installing the WRF/WPS engine, on one page: the machine (this PC through a dedicated WSL, or
 * this Linux computer), the geography (high or low resolution from NCAR, or a WPS_GEOG folder
 * already there, found on the target), the folder, then the check of the target in four figures
 * and the components, closed. One button installs: on Windows it first prepares the dedicated
 * Linux, then checks, then installs; the progress takes the place of the choices. Nothing touches
 * a machine before that click. When NCAR cannot be reached (a proxy answering 403), its archive
 * can be sent from this computer. A stopped installation is resumed from here, with the
 * geography chosen again.
 */
import { Button, FileButton, Group, Loader, Modal, Progress, SegmentedControl, Select, SimpleGrid, Stack, Table, Text, Checkbox, UnstyledButton } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  engineApi,
  type EngineCatalog,
  type FoundGeography,
  type Installation,
  type InstallRequest,
  type Preflight,
  uploadGeography,
  useEngineCatalog,
  useFoundGeography,
  useGeographyUploads,
  useInstallEngine,
  usePrepareWsl,
  useResumeEngine,
  useWslStatus,
} from "../../api/engine";
import { useJob, useProfiles } from "../../api/system";
import type { ComputeProfile } from "../../api/types";
import { defineMessages, useFormat, useT } from "../../i18n";
import { Fold } from "../../ui/Fold";
import { PathInput } from "../../ui/PathInput";
import { ErrorState, LoadingState } from "../../ui/States";
import { engineMessages } from "./engineMessages";
import { blankProfile, localProfile, MANAGED_DISTRO, MANAGED_USER, uniqueId, validInstallRoot } from "./profile";

export type Target = "wsl" | "local";
type Geography = InstallRequest["geography"];

const messages = defineMessages({
  en: {
    title: "Install an engine",
    machine: "Machine",
    wsl: "This PC (WSL)",
    local: "Linux computer",
    geography: "Geography",
    high: "High resolution · {size}",
    low: "Low resolution · {size}",
    download: "{size} to download",
    existing: "Already there",
    found: "Found: {path} · {resolutions}",
    resolutions: { default: "High resolution", lowres: "Low resolution" },
    choose: "Choose",
    sent: "File sent · {size}",
    send: "Send the file",
    blocked: "NCAR blocked ({code})",
    folder: "Folder",
    linux: "{name} · already there",
    space: "Space",
    network: "Network",
    tools: "Tools",
    cores: "Cores",
    free: "{size} free",
    lacking: "{size} short",
    ok: "OK",
    missing: "No {tools}",
    components: "Components",
    complements: "Complements",
    cancel: "Cancel",
    close: "Close",
    install: "Install",
    resume: "Resume",
    change: "Change",
    preparing: "Preparing Linux",
    checking: "Checking",
    restart: "Restart Windows, then open this window again",
    done: "Engine ready",
    log: "Log",
    folderStates: { foreign: "Used by something else", busy: "An installation is running", ready: "Engine already there: kept, nothing is compiled again", partial: "Earlier installation: it goes on from where it stopped" },
    errors: {
      space: "Disk full: free some space, then resume",
      network: "Download failed: check the network, then resume",
      blocked: "NCAR blocked: send the file, then resume",
      corrupted: "Damaged download: resume to fetch it again",
      build: "Compilation failed: see the log",
      tools: "Tool missing on Linux: see the log",
      busy: "Another installation is running in this folder",
      cancelled: "Installation cancelled",
      taken: "Geography folder already there: choose \"Already there\"",
      memory: "Out of memory: resume with fewer processes",
      other: "Installation stopped: see the log",
    },
    rootInvalid: "Absolute Linux folder, no spaces",
  },
  fr: {
    title: "Installer un moteur",
    machine: "Machine",
    wsl: "Ce PC (WSL)",
    local: "Ordinateur Linux",
    geography: "Géographie",
    high: "Haute résolution · {size}",
    low: "Basse résolution · {size}",
    download: "{size} à télécharger",
    existing: "Déjà là",
    found: "Trouvée : {path} · {resolutions}",
    resolutions: { default: "Haute résolution", lowres: "Basse résolution" },
    choose: "Choisir",
    sent: "Fichier envoyé · {size}",
    send: "Envoyer le fichier",
    blocked: "NCAR bloqué ({code})",
    folder: "Dossier",
    linux: "{name} · déjà là",
    space: "Espace",
    network: "Réseau",
    tools: "Outils",
    cores: "Cœurs",
    free: "{size} libres",
    lacking: "{size} manquants",
    ok: "OK",
    missing: "Manque {tools}",
    components: "Composants",
    complements: "Compléments",
    cancel: "Annuler",
    close: "Fermer",
    install: "Installer",
    resume: "Reprendre",
    change: "Modifier",
    preparing: "Préparation de Linux",
    checking: "Vérification",
    restart: "Redémarrez Windows, puis rouvrez cette fenêtre",
    done: "Moteur prêt",
    log: "Journal",
    folderStates: { foreign: "Déjà utilisé par autre chose", busy: "Une installation y tourne", ready: "Moteur déjà là : gardé, rien n'est recompilé", partial: "Installation précédente : elle reprend où elle s'était arrêtée" },
    errors: {
      space: "Disque plein : libérez de la place, puis reprenez",
      network: "Téléchargement raté : vérifiez le réseau, puis reprenez",
      blocked: "NCAR bloqué : envoyez le fichier, puis reprenez",
      corrupted: "Téléchargement abîmé : reprenez pour le refaire",
      build: "Compilation ratée : voir le journal",
      tools: "Outil manquant sur Linux : voir le journal",
      busy: "Une autre installation tourne dans ce dossier",
      cancelled: "Installation annulée",
      taken: "Dossier de géographie déjà là : choisissez « Déjà là »",
      memory: "Mémoire pleine : reprenez avec moins de processus",
      other: "Installation arrêtée : voir le journal",
    },
    rootInvalid: "Dossier Linux absolu, sans espaces",
  },
});

interface Choices {
  target: Target;
  geography: Geography;
  geogPath: string;
  extras: string[];
  folder: string;
  root: string;
  /** The saved profile this installation completes, instead of a new one */
  fromId: string | null;
}

type Saved = ComputeProfile & { missing?: unknown; default?: unknown };

/** A saved profile without the status fields the server adds to it. */
function plain(profile: Saved): ComputeProfile {
  const { missing: _missing, default: _default, ...rest } = profile;
  return structuredClone(rest);
}

/** The profile and request the choices describe. */
function request(choices: Choices, name: string, taken: string[], saved: ComputeProfile[], jobs: number): InstallRequest {
  const kind = choices.target;
  const from = saved.find((p) => p.id === choices.fromId && p.kind === kind);
  const base = from ? plain(from) : blankProfile(kind, name, taken);
  const profile: ComputeProfile = { ...base, id: from ? from.id : uniqueId(name, taken), name: from ? from.name : name, resources: { mpi_command: "mpirun -np {ranks}" } };
  if (kind === "wsl") {
    profile.wsl_distro = MANAGED_DISTRO;
    profile.wsl_user = MANAGED_USER;
  }
  return {
    profile,
    root: choices.root.trim(),
    jobs,
    dependency_mode: "managed",
    geography: choices.geography,
    geog_path: choices.geography === "existing" ? choices.geogPath.trim() : "",
    extras: choices.geography === "existing" ? [] : choices.extras,
  };
}

const host = (url: string) => (url.includes("ucar") ? "NCAR" : url.includes("anaconda") ? "conda" : url.includes("github") ? "GitHub" : url);

export function EngineWizard({ taken, onClose, from, target, resume }: { taken: string[]; onClose: () => void; from?: ComputeProfile; target?: Target; resume?: Installation }) {
  const t = useT(messages);
  const catalog = useEngineCatalog();
  return (
    <Modal opened onClose={onClose} title={<Text fw={600}>{t("title")}</Text>} size="lg">
      {catalog.isLoading && <LoadingState rows={6} />}
      {catalog.error ? <ErrorState error={catalog.error} /> : null}
      {catalog.data && <OnePage catalog={catalog.data} taken={taken} onClose={onClose} from={from} target={target} resume={resume} />}
    </Modal>
  );
}

function OnePage({ catalog, taken, onClose, from, target, resume }: { catalog: EngineCatalog; taken: string[]; onClose: () => void; from?: ComputeProfile; target?: Target; resume?: Installation }) {
  const t = useT(messages);
  const te = useT(engineMessages);
  const f = useFormat();
  const client = useQueryClient();
  const native = catalog.host_platform.startsWith("linux");
  const wsl = useWslStatus(true);
  const profiles = useProfiles();
  const saved = useMemo(() => (profiles.data?.profiles ?? []).map(plain), [profiles.data]);
  const [choices, setChoices] = useState<Choices>(() => {
    const start: Choices = { target: target ?? (native ? "local" : "wsl"), geography: "mandatory-high", geogPath: "", extras: [], folder: catalog.local_folder, root: native ? catalog.native_root : "", fromId: null };
    if (resume) return { ...start, target: resume.profile.kind as Target, geography: resume.options.geography, geogPath: resume.options.geog_path, extras: resume.options.extras, root: resume.root, fromId: resume.profile.id };
    if (from && localProfile(from)) return { ...start, target: from.kind as Target, fromId: from.id, root: from.engine_manifest.root ?? start.root };
    return start;
  });
  const [touched, setTouched] = useState(Boolean(resume));
  const set = (change: Partial<Choices>) => {
    setTouched(true);
    setChoices((c) => ({ ...c, ...change }));
  };
  const isWsl = choices.target === "wsl";
  const targetExists = isWsl ? Boolean(wsl.data?.managed_exists && wsl.data.ready) : native;
  const search = useFoundGeography(choices.target, targetExists);
  // The high resolution first: the one chosen when several are found
  const found = useMemo(() => ({ data: search.data ? [...search.data].sort((a, b) => Number(b.resolutions.includes("default")) - Number(a.resolutions.includes("default"))) : undefined }), [search.data]);
  const uploads = useGeographyUploads();
  const name = te(`target.${choices.target}`);

  // A geography already on the target is chosen at first: nothing to download
  useEffect(() => {
    const first = found.data?.[0];
    if (first && !touched) setChoices((c) => ({ ...c, geography: "existing", geogPath: first.path }));
  }, [found.data, touched]);

  const [jobs, setJobs] = useState(4);
  const body = useMemo(() => request(choices, name, taken, saved, jobs), [choices, name, taken, saved, jobs]);
  const valid = (choices.geography !== "existing" || choices.geogPath.trim().startsWith("/")) && (isWsl ? choices.folder.trim() !== "" || Boolean(wsl.data?.managed_exists) : validInstallRoot(choices.root));

  // The check of the target, again after each change, once the target exists
  const [checked] = useDebouncedValue(body, 600);
  const preflight = useQuery({
    queryKey: ["engine-preflight", checked, uploads.data],
    queryFn: () => engineApi.preflight(checked),
    enabled: targetExists && valid,
    retry: false,
    staleTime: 60_000,
  });
  useEffect(() => {
    const suggested = preflight.data?.suggested_jobs;
    if (suggested) setJobs(Math.min(suggested, 8));
  }, [preflight.data?.suggested_jobs]);

  // After the click: prepare the dedicated Linux (Windows, once), check, install
  const [phase, setPhase] = useState<"choose" | "prepare" | "check" | "install">("choose");
  const [jobId, setJobId] = useState<string | null>(null);
  const prepare = usePrepareWsl();
  const prepareJob = useJob<{ state: string }>(prepare.data?.job_id ?? null);
  const install = useInstallEngine();
  const resumed = useResumeEngine();
  const [startError, setStartError] = useState<Error | null>(null);
  const started = useRef(false);

  const launch = async () => {
    setStartError(null);
    try {
      setPhase("check");
      const result = await engineApi.preflight(body);
      client.setQueryData(["engine-preflight", checked, uploads.data], result);
      if (!result.ready) {
        setPhase("choose");
        return;
      }
      setPhase("install");
      const changes = { geography: body.geography, geog_path: body.geog_path, extras: body.extras };
      const { job_id } = resume ? await resumed.mutateAsync({ id: resume.id, changes }) : await install.mutateAsync(body);
      setJobId(job_id);
    } catch (error) {
      setStartError(error as Error);
      setPhase("choose");
    }
  };

  const go = () => {
    started.current = true;
    if (isWsl && !targetExists) {
      setPhase("prepare");
      prepare.mutate(choices.folder);
    } else void launch();
  };

  // The dedicated Linux ready: the check and the installation follow on their own
  const prepared = prepareJob.data?.state === "succeeded" ? prepareJob.data.result?.state : null;
  useEffect(() => {
    if (phase !== "prepare") return;
    if (prepared === "ready") {
      void client.invalidateQueries({ queryKey: ["engine-wsl"] });
      void launch();
    } else if (prepareJob.data?.state === "failed") setPhase("choose");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prepared, prepareJob.data?.state, phase]);

  if (phase !== "choose") {
    return <Working phase={phase} jobId={jobId} prepareLog={prepareJob.data?.log ?? ""} restart={prepared === "needs_restart"} onClose={onClose} />;
  }

  const high = catalog.geography.find((g) => g.id === "mandatory-high");
  const low = catalog.geography.find((g) => g.id === "mandatory-low");
  const gb = (bytes: number) => f.bytes(bytes);
  const result = preflight.data;
  const ncar = result?.checks.find((c) => c.key === "network")?.detail.split(" ").find((_, i, parts) => parts[i - 1]?.includes("ucar")) ?? null;
  const geographyLabel = (g: FoundGeography) => g.resolutions.map((r) => t(`resolutions.${r}`)).join(" · ");
  const sentSize = choices.geography !== "existing" ? uploads.data?.[choices.geography] : undefined;
  const folderState = result?.checks.find((c) => c.key === "folder");

  return (
    <Stack gap="xl">
      <Stack gap={8}>
        <Text size="sm" fw={600}>{t("machine")}</Text>
        <SegmentedControl fullWidth value={choices.target} onChange={(value) => set({ target: value as Target, root: value === "local" ? catalog.native_root : "", fromId: null })} data={[
          { value: "wsl", label: t("wsl"), disabled: catalog.host_platform !== "win32" || Boolean(resume) },
          { value: "local", label: t("local"), disabled: !native || Boolean(resume) },
        ]} />
      </Stack>

      <Stack gap={8}>
        <Text size="sm" fw={600}>{t("geography")}</Text>
        <SegmentedControl fullWidth value={choices.geography} onChange={(value) => set({ geography: value as Geography, geogPath: value === "existing" ? (found.data?.[0]?.path ?? choices.geogPath) : choices.geogPath })} data={[
          { value: "mandatory-high", label: t("high", { size: gb((high?.unpacked_gb ?? 0) * 1e9) }) },
          { value: "mandatory-low", label: t("low", { size: gb((low?.unpacked_gb ?? 0) * 1e9) }) },
          { value: "existing", label: t("existing") },
        ]} />
        {choices.geography === "existing" ? (
          found.data && found.data.length > 0 ? (
            <Select value={choices.geogPath} onChange={(path) => path && set({ geogPath: path })} allowDeselect={false} data={found.data.map((g) => ({ value: g.path, label: `${g.path} · ${geographyLabel(g)}` }))} styles={{ input: { fontFamily: "var(--mantine-font-family-monospace)", fontSize: 13 } }} />
          ) : (
            <PathInput value={choices.geogPath} onChange={(geogPath) => set({ geogPath })} machine={native ? "here" : "engine"} expect="geog" placeholder="/home/…/WPS_GEOG" />
          )
        ) : (
          <Group gap="md" className="ows-install-note">
            {!found.data?.[0] && !sentSize && !ncar && <Text size="xs" c="dimmed">{t("download", { size: gb((choices.geography === "mandatory-high" ? high : low)?.download_bytes ?? 0) })}</Text>}
            {found.data?.[0] && (
              <UnstyledButton className="ows-install-link" onClick={() => set({ geography: "existing", geogPath: found.data![0].path })}>
                {t("found", { path: found.data[0].path, resolutions: geographyLabel(found.data[0]) })}
              </UnstyledButton>
            )}
            {sentSize ? <Text size="xs" c="dimmed">{t("sent", { size: gb(sentSize) })}</Text> : ncar && <SendArchive geography={choices.geography} code={ncar} />}
          </Group>
        )}
      </Stack>

      <Stack gap={8}>
        <Text size="sm" fw={600}>{t("folder")}</Text>
        {isWsl ? (
          wsl.data?.managed_exists ? (
            <Text size="sm" ff="monospace" className="ows-install-fixed">{t("linux", { name: MANAGED_DISTRO })}</Text>
          ) : (
            <PathInput value={choices.folder} onChange={(folder) => set({ folder })} machine="here" writable />
          )
        ) : (
          <PathInput value={choices.root} onChange={(root) => set({ root })} machine="here" error={!validInstallRoot(choices.root) ? t("rootInvalid") : undefined} disabled={Boolean(resume)} />
        )}
        {folderState?.status === "fail" && (folderState.detail === "foreign" || folderState.detail === "busy") && <Text size="xs" c="red">{t(`folderStates.${folderState.detail}`)}</Text>}
        {folderState?.detail === "ours" && !resume && <Text size="xs" c="dimmed">{t(result?.present.includes("WRF/.ows-built") && result.present.includes("WPS/.ows-built") ? "folderStates.ready" : "folderStates.partial")}</Text>}
      </Stack>

      <Checks result={result} loading={preflight.isFetching} available={targetExists && valid} />

      <Fold className="ows-install-fold" title={t("components")} aside={`WRF ${catalog.wrf.version} · WPS ${catalog.wps.version}`}>
        <Stack gap="lg">
          <Table verticalSpacing={4}>
            <Table.Tbody>
              {[["WRF", catalog.wrf.version], ["WPS", catalog.wps.version], ...Object.entries(catalog.dependencies), ...Object.entries(catalog.bundled_by_wps)].map(([component, version]) => (
                <Table.Tr key={component}><Table.Td>{component}</Table.Td><Table.Td className="ows-num">{version}</Table.Td></Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
          {choices.geography !== "existing" && (
            <Checkbox.Group label={t("complements")} value={choices.extras} onChange={(extras) => set({ extras })}>
              <Stack gap={6} mt={6}>
                {catalog.complements.map((c) => (
                  <Checkbox key={c.id} value={c.id} label={`${c.id in engineMessages.en.complementNames ? te(`complementNames.${c.id as keyof typeof engineMessages.en.complementNames}`) : c.description} · ${gb(c.download_bytes)}`} />
                ))}
              </Stack>
            </Checkbox.Group>
          )}
        </Stack>
      </Fold>

      {(startError || prepare.error || prepareJob.data?.state === "failed") && <ErrorState error={startError ?? prepare.error ?? new Error(prepareJob.data?.error ?? "")} />}

      <Group justify="space-between">
        <Button variant="default" onClick={onClose}>{t("cancel")}</Button>
        <Button onClick={go} disabled={!valid || (Boolean(result) && !result?.ready) || preflight.isFetching}>{resume ? t("resume") : t("install")}</Button>
      </Group>
    </Stack>
  );
}

/** The check of the target in four figures: free space, network, tools, cores. */
function Checks({ result, loading, available }: { result?: Preflight; loading: boolean; available: boolean }) {
  const t = useT(messages);
  const f = useFormat();
  const by = (key: string) => result?.checks.find((c) => c.key === key);
  const space = by("space");
  const network = by("network");
  const tools = [by("tools"), by("system"), by("python")].filter((c) => c && c.status === "fail");
  const failing = network?.detail.split(" ").reduce<string[]>((all, part, i, parts) => (i % 2 === 0 ? [...all, `${host(part)} ${parts[i + 1] ?? ""}`.trim()] : all), []) ?? [];
  const cell = (label: string, value: string, ok: boolean | null) => (
    <div className="ows-install-check">
      <Text size="xs" c="dimmed">{label}</Text>
      <Text size="sm" fw={600} className="ows-install-value" data-ok={ok === null ? undefined : ok}>{loading && !result ? <Loader size={12} /> : value}</Text>
    </div>
  );
  if (!available) {
    return <SimpleGrid cols={4} spacing={0} className="ows-install-checks">{[t("space"), t("network"), t("tools"), t("cores")].map((label) => cell(label, "–", null))}</SimpleGrid>;
  }
  const [free, need] = (space?.detail ?? "0/0").split("/").map(Number);
  return (
    <SimpleGrid cols={4} spacing={0} className="ows-install-checks" data-loading={loading || undefined}>
      {cell(t("space"), space?.status === "fail" ? t("lacking", { size: f.bytes(need - free) }) : t("free", { size: f.bytes(free) }), space ? space.status !== "fail" : null)}
      {cell(t("network"), network?.status === "fail" ? failing.join(" · ") : t("ok"), network ? network.status !== "fail" : null)}
      {cell(t("tools"), tools.length ? t("missing", { tools: tools.map((c) => c!.detail).join(" ") }) : t("ok"), result ? tools.length === 0 : null)}
      {cell(t("cores"), result ? String(result.cpus) : "–", result ? true : null)}
    </SimpleGrid>
  );
}

/** The NCAR archive sent from this computer, when the target cannot download it. */
function SendArchive({ geography, code }: { geography: Geography; code: string }) {
  const t = useT(messages);
  const client = useQueryClient();
  const [progress, setProgress] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const send = async (file: File | null) => {
    if (!file) return;
    setError(null);
    setProgress(0);
    try {
      await uploadGeography(geography, file, setProgress);
      await client.invalidateQueries({ queryKey: ["engine-geography-uploads"] });
    } catch (failure) {
      setError((failure as Error).message);
    } finally {
      setProgress(null);
    }
  };
  return (
    <Group gap="md">
      <Text size="xs" c="orange">{t("blocked", { code })}</Text>
      {progress === null ? (
        <FileButton accept=".gz,.tar.gz,application/gzip" onChange={(file) => void send(file)}>
          {(props) => <UnstyledButton {...props} className="ows-install-link">{t("send")}</UnstyledButton>}
        </FileButton>
      ) : (
        <Progress value={progress * 100} w={160} size="sm" />
      )}
      {error && <Text size="xs" c="red">{error}</Text>}
    </Group>
  );
}

/** The cause of a stopped installation, from its error and the end of its log, in a few words. */
export function failure(text: string): keyof typeof messages.en.errors {
  const has = (pattern: RegExp) => pattern.test(text);
  if (has(/No space left|Not enough free space|Disk quota/i)) return "space";
  if (has(/^Cancelled\.$/m)) return "cancelled";
  if (has(/Another installation is working/)) return "busy";
  if (has(/already exists and is not a geography/)) return "taken";
  if (has(/ucar\.edu.*403|403.*ucar|returned error: 403/i)) return "blocked";
  if (has(/checksum|corrupted|Incomplete download|unexpected end of file|gzip: .*(invalid|corrupt)/i)) return "corrupted";
  if (has(/Could not resolve host|Failed to connect|Connection (timed out|reset|refused)|Operation timed out|curl: \(\d+\)/i)) return "network";
  if (has(/Killed|Cannot allocate memory|out of memory|signal 9/i)) return "memory";
  if (has(/Not available on the target|Managed tool missing|No C preprocessor|NetCDF C and Fortran/)) return "tools";
  if (has(/build failed|not configured for dmpar|dmpar option not found|Could not set the C preprocessor/)) return "build";
  return "other";
}

/** After the click: preparing Linux, checking, then the installation with its stage and log. */
function Working({ phase, jobId, prepareLog, restart, onClose }: { phase: "prepare" | "check" | "install"; jobId: string | null; prepareLog: string; restart: boolean; onClose: () => void }) {
  const t = useT(messages);
  const te = useT(engineMessages);
  const job = useJob<{ manifest?: unknown }>(jobId);
  const lines = job.data?.log ?? prepareLog;
  const stage = useMemo(() => {
    const matches = [...lines.matchAll(/^\[\d\d:\d\d:\d\d\] ([a-z0-9-]+)(?: (.*))?$/gm)];
    const last = matches[matches.length - 1];
    return last ? { key: last[1], detail: last[2] ?? "" } : null;
  }, [lines]);
  const label = phase === "prepare" ? t("preparing") : phase === "check" || !job.data ? t("checking") : stage && stage.key in engineMessages.en.stages ? te(`stages.${stage.key as keyof typeof engineMessages.en.stages}`) : te("stages.queued");
  const percent = Math.round((job.data?.progress ?? 0) * 100);
  const state = job.data?.state;
  return (
    <Stack gap="xl">
      <Stack gap={8} className="ows-install-progress">
        <Group justify="space-between">
          <Text fw={600}>{state === "succeeded" ? t("done") : label}</Text>
          {phase === "install" && job.data && <Text size="sm" c="dimmed" className="ows-num">{percent} %</Text>}
        </Group>
        <Progress value={phase === "install" && job.data ? percent : 100} animated={state === "running" || phase !== "install"} striped={phase !== "install"} color={state === "failed" ? "red" : undefined} />
        {stage?.detail && state === "running" && <Text size="xs" c="dimmed">{stage.detail}</Text>}
        {restart && <Text size="sm" c="orange">{t("restart")}</Text>}
        {state === "failed" && <Text size="sm" c="red">{t(`errors.${failure([job.data?.error ?? "", lines.slice(-3000)].join(" "))}`)}</Text>}
      </Stack>
      {lines && (
        <Fold className="ows-install-fold" title={t("log")}>
          <Text component="pre" size="xs" ff="monospace" className="ows-install-log">{lines.split("\n").slice(-200).join("\n")}</Text>
        </Fold>
      )}
      <Group justify="flex-end">
        <Button variant="default" onClick={onClose}>{t("close")}</Button>
      </Group>
    </Stack>
  );
}
