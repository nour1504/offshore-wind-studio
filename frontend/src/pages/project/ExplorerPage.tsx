/**
 * Any WRF variable of the run on the map and at a point: choices on the left (variable, domain,
 * height, run with or without turbines, point), the map and its time on the right, the series at
 * the point below (a map click, a turbine or a tslist point). The map reads the wrfout files; the
 * series' source is written under it.
 */
import { Box, Grid, Group, Paper, SegmentedControl, Select, Slider, Stack, Text, Tooltip } from "@mantine/core";
import { IconInfoCircle, IconTableExport } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { exploreApi, type SeriesData, type SeriesRef, useRunGeometry } from "../../api/explore";
import type { ResultsSummary } from "../../api/types";
import { useLoadedDraft } from "../../app/CaseDraft";
import { sectionMessages } from "../../app/sections";
import { defineMessages, useFormat, useT } from "../../i18n";
import { Fold } from "../../ui/Fold";
import { NumberField } from "../../ui/Inputs";
import { Page } from "../../ui/Page";
import { ErrorState, LoadingState } from "../../ui/States";
import { ToolBar, ToolLink } from "../../ui/ToolBar";
import { ProjectMap } from "../../ui/map/ProjectMap";
import { exportHref } from "./export/link";
import { isQuantityKey } from "./export/messages";
import { isQuantity, prettyUnit, quantityAbout, quantityNames } from "./explorer/quantities";
import { turbineLabels } from "./explorer/turbineLabels";
import { ResultContext } from "./results/ResultContext";
import { SourceLine } from "./results/SourceLine";
import { CHART_COLORS } from "../../ui/chart";
import { TimeChart } from "./results/TimeChart";
import { sharedMessages } from "./results/shared";
import { Ruler } from "../../ui/Ruler";
import { domainName } from "./domains/grid";

const messages = defineMessages({
  en: {
    variable: "Variable", derived: "Wind and turbulence", raw: "WRF variables", domain: "Domain", height: "Height",
    run: "Run", point: "Point", onMap: "On the map",
    map: "Map", series: "At the point", export: "Export", time: "Time", noPoint: "Click the map",
    mapSource: "Map: history files (wrfout).",
  },
  fr: {
    variable: "Variable", derived: "Vent et turbulence", raw: "Variables de WRF", domain: "Domaine", height: "Hauteur",
    run: "Calcul", point: "Point", onMap: "Sur la carte",
    map: "Carte", series: "Au point", export: "Exporter", time: "Instant", noPoint: "Clic sur la carte",
    mapSource: "Carte : fichiers d'historique (wrfout).",
  },
});

/** The Exporter tab with the series shown: the tslist fold when it was read there, else wrfout. */
function seriesExport(caseId: string, run: string, ref: SeriesRef, shown: SeriesData | undefined): string {
  if (shown?.meta.source === "tslist" && ref.location && isQuantityKey(ref.variable)) {
    return exportHref(caseId, run, {
      panel: "tslist", points: [ref.location], quantities: [ref.variable], average: Number(shown.meta.averaging_s ?? 600),
      heights: ref.height_m ? [ref.height_m] : undefined,
    });
  }
  return exportHref(caseId, run, {
    panel: "wrfout", variable: ref.variable, domain: ref.domain, height: ref.height_m, stage: ref.stage,
    location: ref.location, lat: ref.lat, lon: ref.lon,
  });
}

function Explorer({ summary }: { summary: ResultsSummary }) {
  const { caseId, draft } = useLoadedDraft();
  const t = useT(messages);
  const tq = useT(quantityNames);
  const ta = useT(quantityAbout);
  const ts = useT(sharedMessages);
  const f = useFormat();
  const run = summary.run_id;
  const name = (key: string, fallback?: unknown) => (isQuantity(key) ? tq(key) : String(fallback ?? key));
  const [variable, setVariable] = useState("wind_speed");
  const [domain, setDomain] = useState(summary.farm_domain ?? summary.domains.at(-1) ?? 1);
  const [height, setHeight] = useState<number | null>(summary.hub_height_m);
  const [stage, setStage] = useState<"main" | "control">("main");
  const [location, setLocation] = useState("");
  const [point, setPoint] = useState<{ lat: number; lon: number } | null>(null);
  const [time, setTime] = useState(0);

  const variables = useQuery({ queryKey: ["variables", caseId, run, stage], queryFn: () => exploreApi.variables(caseId, run, stage), retry: false, staleTime: Infinity });
  const diagnostics = useQuery({ queryKey: ["diagnostics", caseId, run, domain, stage], queryFn: () => exploreApi.diagnostics(caseId, run, domain, stage), retry: false, staleTime: Infinity });
  const fiche = useQuery({ queryKey: ["fiche", variable], queryFn: () => exploreApi.fiche(variable), retry: false, staleTime: Infinity });
  const geometry = useRunGeometry(caseId, run);

  const derived = (diagnostics.data?.diagnostics ?? []).filter((d) => d.status !== "impossible");
  const raw = variables.data?.domains[String(domain)] ?? [];
  const diagnostic = derived.find((d) => d.key === variable);
  const rawVariable = raw.find((v) => v.name === variable);
  const needsHeight = diagnostic ? Boolean(diagnostic.needs_height) : Boolean(rawVariable?.vertical);
  const label = name(variable, diagnostic?.label);
  const about = isQuantity(variable) ? ta(variable) : (fiche.data?.canonical as { description?: string } | undefined)?.description ?? rawVariable?.description ?? diagnostic?.method as string | undefined;
  const description = about ? `${about} ${t("mapSource")}` : undefined;

  const times = variables.data?.times[String(domain)] ?? [];
  const index = Math.min(time, Math.max(0, times.length - 1));
  const timeline = useRef<HTMLDivElement>(null);
  const mapQuery = { variable, domain, time: index, height: needsHeight ? height ?? undefined : undefined, stage };
  const map = useQuery({ queryKey: ["explore-map", caseId, run, mapQuery], queryFn: () => exploreApi.map(caseId, run, mapQuery), enabled: times.length > 0, retry: false, staleTime: Infinity });

  const labels = turbineLabels(draft.farms);
  const locations = [
    ...draft.farms.flatMap((farm) => farm.turbines.map((turbine, i) => ({ value: labels.get(`${farm.id}:${i + 1}`)!, label: `${farm.name} · ${turbine.id || i + 1}` }))),
    ...(draft.time_series?.points ?? []).map((p) => ({ value: p.prefix, label: p.name })),
  ];
  const ref: SeriesRef = {
    // A turbine or a tslist point is read in the innermost domain holding it, whatever the map
    // shows, as 10-minute means of every model step
    kind: "run", case_id: caseId, run_id: run, variable, domain: location ? undefined : domain, stage, reader: "",
    options: location ? { averaging_s: 600 } : undefined,
    height_m: needsHeight ? height : null, location: location || undefined, lat: location ? null : point?.lat ?? null, lon: location ? null : point?.lon ?? null,
  };
  const hasPoint = Boolean(location || point);
  const series = useQuery({ queryKey: ["explore-series", ref], queryFn: () => exploreApi.series([ref]), enabled: hasPoint, retry: false, staleTime: Infinity });
  const shown = series.data?.series[0];

  const digits = map.data ? (Math.abs(map.data.vmax - map.data.vmin) < 2 ? 2 : Math.abs(map.data.vmax - map.data.vmin) < 30 ? 1 : 0) : 1;
  return (
    <Stack gap={32}>
      <Grid gap="xl" align="stretch">
        <Grid.Col span={{ base: 12, md: 4 }}>
          <Paper withBorder radius="lg" p="lg" h="100%">
          <Stack gap="md" className="ows-explorer-choices">
            <Select searchable label={<Group gap={5} wrap="nowrap" component="span"><span>{t("variable")}</span>{description && <Tooltip label={description} multiline w={300} withArrow><IconInfoCircle size={14} className="ows-info-icon" aria-label={description} /></Tooltip>}</Group>}
              value={variable} onChange={(value) => value && setVariable(value)} allowDeselect={false} maxDropdownHeight={360}
              data={[
                { group: t("derived"), items: derived.map((d) => ({ value: d.key, label: `${name(d.key, d.label)}${prettyUnit(d.unit) ? ` (${prettyUnit(d.unit)})` : ""}` })) },
                { group: t("raw"), items: raw.filter((v) => !derived.some((d) => d.key === v.name)).map((v) => ({ value: v.name, label: `${v.name}${prettyUnit(v.units) ? ` (${prettyUnit(v.units)})` : ""}` })) },
              ]} />
            {summary.domains.length > 1 && (
              <Stack gap={6}>
                <Text size="sm" fw={500}>{t("domain")}</Text>
                <SegmentedControl fullWidth value={String(domain)} onChange={(value) => { setDomain(Number(value)); setTime(0); }} data={summary.domains.map((d) => ({ value: String(d), label: domainName(d - 1) }))} />
              </Stack>
            )}
            {needsHeight && <NumberField label={t("height")} unit="m" min={0} value={height} onValue={setHeight} onClear={() => setHeight(null)} />}
            {summary.has_control && (
              <Stack gap={6}>
                <Text size="sm" fw={500}>{t("run")}</Text>
                <SegmentedControl fullWidth value={stage} onChange={(value) => setStage(value as "main" | "control")} data={[{ value: "main", label: ts("withFarm") }, { value: "control", label: ts("withoutFarm") }]} />
              </Stack>
            )}
            <Select searchable clearable label={t("point")} placeholder={t("noPoint")} value={location || (point ? "__map" : null)}
              onChange={(value) => { if (value === "__map") return; setLocation(value ?? ""); setPoint(null); }}
              data={[...(point && !location ? [{ value: "__map", label: `${t("onMap")} · ${f.numbers([point.lat, point.lon], 3)}` }] : []), ...locations]} />
          </Stack>
          </Paper>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 8 }}>
          <Paper withBorder radius="lg" p="lg" h="100%">
          <Stack gap="md">
            {map.error && <ErrorState error={map.error} />}
            <ProjectMap geometry={geometry.data} farmOrder={draft.farms.map((farm) => farm.id)} farms="dots" height={460} ariaLabel={t("map")} showProbes={false}
              frame={{ target: `domain:${domain}`, key: domain }}
              onMapClick={(lat, lon) => { setLocation(""); setPoint({ lat, lon }); }}
              onTurbineClick={(feature) => { const key = labels.get(`${feature.farm}:${feature.number}`); if (key) { setLocation(key); setPoint(null); } }}
              marker={!location && point ? point : null}
              overlay={map.data ? { url: exploreApi.mapUrl(caseId, run, { ...mapQuery, vmin: map.data.vmin, vmax: map.data.vmax }), coordinates: map.data.coordinates, opacity: 0.85 } : null} />
            <Box ref={timeline}>
              <Group gap="md" wrap="nowrap">
                <Slider style={{ flex: 1 }} min={0} max={Math.max(1, times.length - 1)} value={index} onChange={setTime} disabled={times.length < 2} step={1} aria-label={t("time")} label={(value) => f.dateTime(times[value])} />
                <Text size="sm" fw={600} className="ows-num" style={{ whiteSpace: "nowrap" }}>{times[index] ? f.dateTime(times[index]) : "–"}</Text>
              </Group>
              {times.length > 1 && <Ruler host={timeline} under=".mantine-Slider-track" at={index / (times.length - 1)} />}
            </Box>
            {map.data && (
              <Group gap={10} wrap="nowrap" className="ows-map-legend">
                <Text size="sm" className="ows-num">{f.number(map.data.vmin, digits)}</Text>
                <div className="ows-map-legend-bar" style={{ background: `linear-gradient(to right, ${map.data.colors.join(", ")})` }} />
                <Text size="sm" className="ows-num">{f.number(map.data.vmax, digits)}</Text>
                <Text size="sm" fw={600} c="dimmed">{prettyUnit(map.data.unit)}</Text>
              </Group>
            )}
          </Stack>
          </Paper>
        </Grid.Col>
      </Grid>
      <Fold defaultOpen title={t("series")} aside={label}
        actions={shown ? <ToolBar label={t("series")}><ToolLink icon={IconTableExport} label={t("export")} href={seriesExport(caseId, run, ref, shown)} /></ToolBar> : undefined}>
        {!hasPoint ? <Text size="sm" fw={600} c="dimmed" ta="center" py="lg">{t("noPoint")}</Text>
          : series.isLoading ? <LoadingState rows={4} />
            : series.error ? <ErrorState error={series.error} />
              : series.data?.series.map((s) => (
                <Stack key={s.meta.key} gap={6}>
                  <TimeChart title={label} unit={prettyUnit(s.meta.unit)} dotsOnly={variable === "wind_direction"} height={280}
                    rows={s.times.map((when, k) => ({ time: when, value: s.values[k] }))} series={[{ name: "value", label, color: CHART_COLORS.main }]} markTime={times[index] ?? null} />
                  <SourceLine source={s.meta.source === "tslist" ? "tslist" : "wrfout"}
                    seconds={s.meta.source === "tslist" ? Number(s.meta.averaging_s ?? 0) : Number(s.meta.frequency_s ?? 0) || null} method={s.meta.method} />
                </Stack>
              ))}
      </Fold>
    </Stack>
  );
}

export default function ExplorerPage() {
  const t = useT(sectionMessages);
  return (
    <Page title={t("project.explorer")} help="explorer" fluid>
      <ResultContext>{(summary) => <Explorer key={summary.run_id} summary={summary} />}</ResultContext>
    </Page>
  );
}
