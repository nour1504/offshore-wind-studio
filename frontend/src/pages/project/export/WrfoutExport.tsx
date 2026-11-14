/**
 * The wrfout fold of the Exporter tab: one variable of the history files at one point (a turbine,
 * a tslist point or a position), at each output time, over the period chosen; the choices of the
 * Variable explorer.
 */
import { Button, Group, RangeSlider, SegmentedControl, Select, SimpleGrid, Stack, Text } from "@mantine/core";
import { IconDownload } from "@tabler/icons-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { exploreApi } from "../../../api/explore";
import { exportApi } from "../../../api/export";
import type { ResultsSummary } from "../../../api/types";
import { useLoadedDraft } from "../../../app/CaseDraft";
import { parseUtc, useLang, useT } from "../../../i18n";
import { downloadText } from "../../../ui/download";
import { NumberField } from "../../../ui/Inputs";
import { ErrorState } from "../../../ui/States";
import { domainName } from "../domains/grid";
import { isQuantity, prettyUnit, quantityNames } from "../explorer/quantities";
import { turbineLabels } from "../explorer/turbineLabels";
import { sharedMessages } from "../results/shared";
import type { ExportInitial } from "./link";
import { exportMessages } from "./messages";

const POSITION = "__position";

export function WrfoutExport({ caseId, summary, initial }: { caseId: string; summary: ResultsSummary; initial: ExportInitial["wrfout"] }) {
  const { draft } = useLoadedDraft();
  const t = useT(exportMessages);
  const tq = useT(quantityNames);
  const ts = useT(sharedMessages);
  const { lang } = useLang();
  const run = summary.run_id;
  const name = (key: string, fallback?: unknown) => (isQuantity(key) ? tq(key) : String(fallback ?? key));
  const [variable, setVariable] = useState(initial.variable ?? "wind_speed");
  const [domain, setDomain] = useState(initial.domain !== null && summary.domains.includes(initial.domain) ? initial.domain : summary.farm_domain ?? summary.domains.at(-1) ?? 1);
  const [height, setHeight] = useState<number | null>(initial.height ?? summary.hub_height_m);
  const [stage, setStage] = useState<"main" | "control">(summary.has_control ? initial.stage : "main");
  const labels = useMemo(() => turbineLabels(draft.farms), [draft.farms]);
  const locations = useMemo(() => [
    ...draft.farms.flatMap((farm) => farm.turbines.map((turbine, i) => ({ value: labels.get(`${farm.id}:${i + 1}`)!, label: `${farm.name} · ${turbine.id || i + 1}` }))),
    ...(draft.time_series?.points ?? []).map((p) => ({ value: p.prefix, label: p.name })),
  ], [draft.farms, draft.time_series, labels]);
  const [location, setLocation] = useState(initial.location ?? (initial.lat !== null && initial.lon !== null ? POSITION : locations[0]?.value ?? POSITION));
  const [lat, setLat] = useState<number | null>(initial.lat);
  const [lon, setLon] = useState<number | null>(initial.lon);
  const [range, setRange] = useState<[number, number] | null>(null);
  const short = useMemo(() => new Intl.DateTimeFormat(lang === "fr" ? "fr-FR" : "en-GB", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: "UTC" }), [lang]);

  const variables = useQuery({ queryKey: ["variables", caseId, run, stage], queryFn: () => exploreApi.variables(caseId, run, stage), retry: false, staleTime: Infinity });
  const diagnostics = useQuery({ queryKey: ["diagnostics", caseId, run, domain, stage], queryFn: () => exploreApi.diagnostics(caseId, run, domain, stage), retry: false, staleTime: Infinity });
  const derived = (diagnostics.data?.diagnostics ?? []).filter((d) => d.status !== "impossible");
  const raw = variables.data?.domains[String(domain)] ?? [];
  const diagnostic = derived.find((d) => d.key === variable);
  const rawVariable = raw.find((v) => v.name === variable);
  const needsHeight = diagnostic ? Boolean(diagnostic.needs_height) : Boolean(rawVariable?.vertical);

  // The period: from one output time to another (all at first); the server keeps ]start, end]
  const times = (variables.data?.times[String(domain)] ?? []).map((time) => parseUtc(time).getTime());
  const last = Math.max(0, times.length - 1);
  const [from, to] = range && range[1] <= last ? range : [0, last];
  const whole = from === 0 && to === last;
  const position = location === POSITION;
  const ready = Boolean(variable) && (!position || (lat !== null && lon !== null)) && (!needsHeight || (height !== null && height > 0));
  const choice = {
    variable, domain, stage, height: needsHeight ? height : undefined,
    location: position ? undefined : location, lat: position ? lat : undefined, lon: position ? lon : undefined,
    start: whole || !times.length ? undefined : new Date(times[from] - 1000).toISOString(),
    end: whole || !times.length ? undefined : new Date(times[to]).toISOString(),
  };
  const where = position ? `${lat ?? ""}_${lon ?? ""}` : location;
  const download = useMutation({
    mutationFn: () => exportApi.wrfoutCsv(caseId, run, choice),
    onSuccess: (text) => downloadText(text, `${caseId}-wrfout-${variable}-${where}.csv`.replace(/[^A-Za-z0-9_.-]+/g, "-")),
  });

  return (
    <Stack gap="xl">
      <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing="md">
        <Select searchable label={t("variable")} value={variable} onChange={(value) => value && setVariable(value)} allowDeselect={false} maxDropdownHeight={360}
          data={[
            { group: t("derived"), items: derived.map((d) => ({ value: d.key, label: `${name(d.key, d.label)}${prettyUnit(d.unit) ? ` (${prettyUnit(d.unit)})` : ""}` })) },
            { group: t("raw"), items: raw.filter((v) => !derived.some((d) => d.key === v.name)).map((v) => ({ value: v.name, label: `${v.name}${prettyUnit(v.units) ? ` (${prettyUnit(v.units)})` : ""}` })) },
          ]} />
        {needsHeight && <NumberField label={t("height")} unit="m" min={0} value={height} onValue={setHeight} onClear={() => setHeight(null)} />}
        <Select searchable label={t("point")} value={location} allowDeselect={false} onChange={(value) => value && setLocation(value)}
          data={[...locations, { value: POSITION, label: t("position") }]} />
        {position && (
          <>
            <NumberField label={t("lat")} unit="°" value={lat} onValue={setLat} onClear={() => setLat(null)} />
            <NumberField label={t("lon")} unit="°" value={lon} onValue={setLon} onClear={() => setLon(null)} />
          </>
        )}
      </SimpleGrid>
      {(summary.domains.length > 1 || summary.has_control) && (
        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="md">
          {summary.domains.length > 1 && (
            <Stack gap={6}>
              <Text size="sm" fw={500}>{t("domain")}</Text>
              <SegmentedControl fullWidth value={String(domain)} onChange={(value) => { setDomain(Number(value)); setRange(null); }}
                data={summary.domains.map((d) => ({ value: String(d), label: domainName(d - 1) }))} />
            </Stack>
          )}
          {summary.has_control && (
            <Stack gap={6}>
              <Text size="sm" fw={500}>{t("runs")}</Text>
              <SegmentedControl fullWidth value={stage} onChange={(value) => setStage(value as "main" | "control")}
                data={[{ value: "main", label: ts("withFarm") }, { value: "control", label: ts("withoutFarm") }]} />
            </Stack>
          )}
        </SimpleGrid>
      )}
      {times.length > 1 && (
        <Stack gap={10}>
          <Group justify="space-between" gap="xs">
            <Text size="sm" fw={500}>{t("period")}</Text>
            <Text size="sm" c="dimmed" className="ows-num">{`${short.format(times[from])} → ${short.format(times[to])}`}</Text>
          </Group>
          <RangeSlider min={0} max={last} step={1} minRange={0} value={[from, to]} onChange={setRange} label={null} />
        </Stack>
      )}
      {download.error && <ErrorState error={download.error} />}
      <Group justify="flex-end">
        <Button leftSection={<IconDownload size={18} />} disabled={!ready} loading={download.isPending} onClick={() => download.mutate()}>
          {t("download")}
        </Button>
      </Group>
    </Stack>
  );
}
