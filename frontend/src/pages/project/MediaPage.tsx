import { Alert, Anchor, Button, Checkbox, Code, Group, Progress, Select, SimpleGrid, Stack, Text } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { IconDownload, IconFileText, IconMovie, IconPlayerStop } from "@tabler/icons-react";
import { useEffect, useState } from "react";

import { get, post } from "../../api/client";
import { useRunHistory } from "../../api/runs";
import { useLoadedDraft } from "../../app/CaseDraft";
import { sectionMessages } from "../../app/sections";
import { defineMessages, useFormat, useLang, useT } from "../../i18n";
import { Fold } from "../../ui/Fold";
import { Page, Section } from "../../ui/Page";
import { EmptyState, ErrorState, LoadingState } from "../../ui/States";
import { NumberField } from "../../ui/Inputs";
import { ImportOutputs } from "./results/ImportOutputs";

const messages = defineMessages({
  en: {
    description: "Export of the outputs as MP4 animation or report.",
    video: "Animation", report: "PDF report", exports: "Saved exports", run: "Run", config: "Configuration only",
    domain: "Domain", variable: "Variable", height: "Height (m)", surface: "Surface field",
    first: "First output", last: "Last output", stride: "One output in", fps: "Frames per second",
    width: "Width (px)", vectors: "Show wind vectors", render: "Render MP4", create: "Create PDF",
    empty: "No export", noOutputsTitle: "No outputs",
    frames: "{n} frames · {seconds} seconds of video",
    range: "{first} → {last}",
    unsaved: "Save the project first", cancel: "Stop export", progress: "Export progress", download: "Download",
    done: "Export completed", failed: "Export failed", stopped: "Export cancelled", running: "Rendering…", notes: "Export notes",
    wind: "Wind speed", direction: "Wind direction", temperature: "Air temperature", pblh: "Boundary layer height", sst: "Sea surface temperature", power: "WRF power per cell", tke: "Turbulent kinetic energy",
  },
  fr: {
    description: "Export des sorties en animation MP4 ou en rapport.",
    video: "Animation", report: "Rapport PDF", exports: "Exports enregistrés", run: "Calcul", config: "Configuration seule",
    domain: "Domaine", variable: "Variable", height: "Hauteur (m)", surface: "Champ de surface",
    first: "Première sortie", last: "Dernière sortie", stride: "Une sortie sur", fps: "Images par seconde",
    width: "Largeur (px)", vectors: "Afficher les vecteurs de vent", render: "Créer le MP4", create: "Créer le PDF",
    empty: "Aucun export", noOutputsTitle: "Aucune sortie",
    frames: "{n} images · {seconds} secondes de vidéo",
    range: "{first} → {last}",
    unsaved: "Enregistrez d'abord le projet", cancel: "Arrêter l'export", progress: "Progression de l'export", download: "Télécharger",
    done: "Export terminé", failed: "Échec de l'export", stopped: "Export annulé", running: "Rendu en cours…", notes: "Notes de l'export",
    wind: "Vitesse du vent", direction: "Direction du vent", temperature: "Température de l'air", pblh: "Hauteur de couche limite", sst: "Température de surface de la mer", power: "Puissance WRF par maille", tke: "Énergie cinétique turbulente",
  },
});

interface ExportFile { name: string; path: string; size: number; kind: string; url: string; warnings?: string[] }
interface ExportJob { state: string; progress: number; error: string | null; log: string; result: ExportFile | null }

export default function MediaPage() {
  const t = useT(messages);
  const ts = useT(sectionMessages);
  const f = useFormat();
  const { lang } = useLang();
  const { caseId, dirty } = useLoadedDraft();
  const client = useQueryClient();
  const history = useRunHistory(caseId);
  // Not chosen yet: the latest run that succeeded, so that a report has its results by default
  const [chosen, setRun] = useState<string | null | undefined>(undefined);
  const [domain, setDomain] = useState("1");
  const [variable, setVariable] = useState("wind_speed");
  const [height, setHeight] = useState(100);
  const [first, setFirst] = useState(0);
  const [last, setLast] = useState<number | null>(null);
  const [stride, setStride] = useState(1);
  const [fps, setFps] = useState(12);
  const [width, setWidth] = useState("1280");
  const [vectors, setVectors] = useState(true);
  const [jobId, setJobId] = useState<string | null>(null);
  const base = `/api/cases/${caseId}/media`;
  const runs = (history.data ?? []).filter(r => r.state === "succeeded" && r.run_id);
  const latest = runs.reduce<(typeof runs)[number] | null>((best, r) => !best || (r.started_at ?? "") > (best.started_at ?? "") ? r : best, null);
  const run = chosen === undefined ? latest?.run_id ?? null : chosen;
  const inventory = useQuery({ queryKey: ["media-outputs", caseId, run], queryFn: () => get<{ times: Record<string, string[]> }>(`/api/cases/${caseId}/runs/${run}/variables`), enabled: Boolean(run), retry: false });
  const exports = useQuery({ queryKey: ["media", caseId], queryFn: () => get<ExportFile[]>(base) });
  const job = useQuery({ queryKey: ["media-job", jobId], queryFn: () => get<ExportJob>(`/api/jobs/${jobId}`), enabled: Boolean(jobId), refetchInterval: q => q.state.data?.state === "running" ? 1000 : false });
  const busy = job.data?.state === "running";
  useEffect(() => { if (job.data?.state === "succeeded") void client.invalidateQueries({ queryKey: ["media", caseId] }); }, [job.data?.state, client, caseId]);
  useEffect(() => { setFirst(0); setLast(null); }, [run, domain]);
  const times = inventory.data?.times[domain] ?? [];
  const end = last ?? Math.max(0, times.length - 1);
  const count = first <= end ? Math.floor((end - first) / stride) + 1 : 0;
  const surface = ["power", "sst", "pblh"].includes(variable);
  const render = useMutation({ mutationFn: () => post<{ job_id: string }>(`${base}/video`, { run, domain: Number(domain), variable, height_m: surface ? null : height, first, last: end, stride, fps, width: Number(width), vectors }), onSuccess: data => setJobId(data.job_id) });
  const report = useMutation({ mutationFn: () => post<{ job_id: string }>(`${base}/report`, { run, lang }), onSuccess: data => setJobId(data.job_id) });
  const cancel = useMutation({ mutationFn: () => post(`/api/jobs/${jobId}/cancel`), onSuccess: () => void job.refetch() });
  return <Page title={ts("project.media")} help="media">
    <Group justify="space-between" align="flex-end" gap="md" wrap="wrap">
      <Select label={t("run")} w={{ base: "100%", sm: 240 }} value={run ?? ""} onChange={v => setRun(v || null)} data={[{ value: "", label: t("config") }, ...runs.map(r => ({ value: r.run_id!, label: f.dateTime(r.finished_at ?? r.started_at) }))]} allowDeselect={false} checkIconPosition="right" />
      <ImportOutputs compact />
    </Group>
    {dirty && <Alert color="gray">{t("unsaved")}</Alert>}
    <Fold title={t("video")} help="media">
        <Stack>
          {!run && <EmptyState icon={<IconMovie size={26} stroke={1.5} />} title={t("noOutputsTitle")} />}
          {inventory.isLoading && <LoadingState rows={3} />}{inventory.error && <ErrorState error={inventory.error} />}
          {run && <>
          <SimpleGrid cols={2}>
            <Select label={t("domain")} data={Object.keys(inventory.data?.times ?? {}).map(d => ({ value: d, label: `d${d.padStart(2, "0")}` }))} value={domain} onChange={v => v && setDomain(v)} />
            <Select label={t("variable")} value={variable} onChange={v => v && setVariable(v)} allowDeselect={false} data={[
              { value: "wind_speed", label: t("wind") }, { value: "wind_direction", label: t("direction") }, { value: "temperature", label: t("temperature") }, { value: "tke", label: t("tke") },
              { value: "power", label: t("power") }, { value: "sst", label: t("sst") }, { value: "pblh", label: t("pblh") },
            ]} />
            <NumberField label={t("height")} value={height} min={0} disabled={surface} onValue={setHeight} />
            <Select label={t("width")} value={width} onChange={v => v && setWidth(v)} data={["640", "1280", "1920", "2560"]} />
            <NumberField label={t("first")} value={first} min={0} max={Math.max(0, times.length - 1)} onValue={setFirst} allowDecimal={false} />
            <NumberField label={t("last")} value={end} min={first} max={Math.max(0, times.length - 1)} onValue={setLast} allowDecimal={false} />
            <NumberField label={t("stride")} value={stride} min={1} onValue={setStride} allowDecimal={false} />
            <NumberField label={t("fps")} value={fps} min={1} max={60} onValue={setFps} allowDecimal={false} />
          </SimpleGrid>
          <Checkbox label={t("vectors")} checked={vectors} disabled={surface} onChange={e => setVectors(e.currentTarget.checked)} />
          {times.length > 0 && <Text size="sm" c="dimmed">{t("range", { first: times[first] ? f.dateTime(times[first]) : "—", last: times[end] ? f.dateTime(times[end]) : "—" })}<br />{t("frames", { n: count, seconds: f.number(count / fps, 1) })}</Text>}
          {render.error && <ErrorState error={render.error} />}
          <Button leftSection={<IconMovie size={17} />} onClick={() => render.mutate()} loading={render.isPending} disabled={!run || !times.length || !count || busy}>{t("render")}</Button>
          </>}
        </Stack>
      </Fold>
      <Fold title={t("report")}>
        <Stack>{report.error && <ErrorState error={report.error} />}<Button w="fit-content" leftSection={<IconFileText size={17} />} loading={report.isPending} disabled={dirty || busy} onClick={() => report.mutate()}>{t("create")}</Button></Stack>
      </Fold>
    {jobId && <Section title={t(busy ? "running" : job.data?.state === "succeeded" ? "done" : job.data?.state === "cancelled" ? "stopped" : "failed")}>
      <Stack>
        {job.isLoading && <LoadingState rows={2} />}{job.error && <ErrorState error={job.error} />}
        <Progress aria-label={t("progress")} value={(job.data?.progress ?? 0) * 100} animated={busy} />
        {job.data?.error && <Alert color="red">{job.data.error}</Alert>}
        {busy && <Button w="fit-content" variant="light" color="red" leftSection={<IconPlayerStop size={16} />} loading={cancel.isPending} onClick={() => cancel.mutate()}>{t("cancel")}</Button>}
        {job.data?.result && <Anchor href={job.data.result.url} download>{t("download")} · {job.data.result.name}</Anchor>}
        {job.data?.result?.warnings?.map(w => <Text key={w} size="sm" c="dimmed">{w}</Text>)}
        {job.data?.log && <Code block>{job.data.log}</Code>}
      </Stack>
    </Section>}
    <Fold title={t("exports")}>
      {exports.isLoading && <LoadingState rows={3} />}{exports.error && <ErrorState error={exports.error} />}
      {exports.data?.length === 0 && <EmptyState icon={<IconFileText size={26} stroke={1.5} />} title={t("empty")} />}
      <Stack>{exports.data?.map(item => <Group key={item.name} justify="space-between">
        <Stack gap={2}><Anchor href={item.url} download><Group gap={6}><IconDownload size={15} />{item.name}</Group></Anchor><Text size="xs" c="dimmed">{item.path}</Text></Stack><Text size="sm">{f.bytes(item.size)}</Text>
      </Group>)}</Stack>
    </Fold>
  </Page>;
}
