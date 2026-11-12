import { Button, Group, Select, Stack, Text, TextInput } from "@mantine/core";
import { IconTableExport } from "@tabler/icons-react";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { useCases } from "../../api/cases";
import type { SeriesRef } from "../../api/explore";
import { observationsApi, useObservationDatasets } from "../../api/observations";
import { useRunHistory } from "../../api/runs";
import { defineMessages, useFormat, useT } from "../../i18n";
import { CHART_COLORS, cssColor } from "../../ui/chart";
import { Fold } from "../../ui/Fold";
import { NumberField } from "../../ui/Inputs";
import { Stat, StatGrid } from "../../ui/Stat";
import { ErrorState, QueryView } from "../../ui/States";
import { exportHref } from "../project/export/link";
import { isQuantityKey } from "../project/export/messages";
import { prettyUnit } from "../project/explorer/quantities";
import { SourceLine } from "../project/results/SourceLine";
import { TimeChart } from "../project/results/TimeChart";

const messages = defineMessages({
  en: {
    title: "Compare measurements with WRF",
    dataset: "Measured dataset",
    series: "Measured quantity / height",
    project: "Project",
    run: "Run",
    latest: "Latest with outputs",
    domain: "Domain (blank: finest containing the station)",
    period: "Common averaging",
    availability: "Minimum availability",
    tolerance: "Pairing tolerance",
    start: "Start (UTC, optional)",
    end: "End (UTC, excluded, optional)",
    compare: "Compare",
    reference: "Measured",
    simulation: "WRF",
    bias: "Bias",
    rmse: "RMSE",
    correlation: "Correlation",
    pairs: "Paired values",
    export: "Export the WRF series",
    timeseries: "Aligned comparison",
    scatter: "Measured vs simulated",
    notes: "Alignment and limitations",
    noSeries: "No measurement datasets yet",
    noStation: "Measurements need station coordinates for comparison.",
  },
  fr: {
    title: "Comparer les mesures avec WRF",
    dataset: "Jeu de mesures",
    series: "Grandeur mesurée / hauteur",
    project: "Projet",
    run: "Calcul",
    latest: "Dernier avec sorties",
    domain: "Domaine (vide : le plus fin contenant la station)",
    period: "Moyenne commune",
    availability: "Disponibilité minimale",
    tolerance: "Tolérance d'appariement",
    start: "Début (UTC, facultatif)",
    end: "Fin (UTC, exclue, facultatif)",
    compare: "Comparer",
    reference: "Mesures",
    simulation: "WRF",
    bias: "Biais",
    rmse: "RMSE",
    correlation: "Corrélation",
    pairs: "Valeurs appariées",
    export: "Exporter la série de WRF",
    timeseries: "Comparaison alignée",
    scatter: "Mesures et simulation",
    notes: "Alignement et limites",
    noSeries: "Aucun jeu de mesures pour l'instant",
    noStation: "Les mesures doivent avoir des coordonnées de station pour la comparaison.",
  },
});

export function ComparisonSection() {
  const t = useT(messages);
  const f = useFormat();
  const datasets = useObservationDatasets();
  const projects = useCases();
  const [datasetId, setDatasetId] = useState<string | null>(null);
  const [seriesKey, setSeriesKey] = useState<string | null>(null);
  const [caseId, setCaseId] = useState<string | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [domain, setDomain] = useState<number | null>(null);
  const [period, setPeriod] = useState(3600);
  const [availability, setAvailability] = useState(0.7);
  const [tolerance, setTolerance] = useState(0);
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const runs = useRunHistory(caseId);
  const dataset = datasets.data?.find((d) => d.id === datasetId);
  const series = dataset?.series.find((s) => s.key === seriesKey);
  const measured = (): SeriesRef => ({ kind: "observation",dataset: datasetId!, variable: series!.variable, location: dataset!.station.id, height_m: series!.height_m, height_ref: series!.height_ref });
  const compare = useMutation({
    mutationFn: () => observationsApi.compare(
      measured(),
      { kind: "run", case_id: caseId!, run_id: runId ?? "", variable: series!.variable, domain: domain ?? undefined, reader: "", height_m: series!.height_m, height_ref: series!.height_ref === "surface" ? "agl" : series!.height_ref },
      period, availability, tolerance, start ? `${start}Z` : null, end ? `${end}Z` : null,
    ),
  });
  const reset = () => compare.reset();
  const result = compare.data;
  // The WRF series compared, in the Exporter tab of its project: the tslist fold when it was read
  // there, else the wrfout one at the station
  const simulated = result?.inputs.find((input) => input.source === "tslist" || input.source === "wrfout");
  const fromTslist = simulated?.source === "tslist";
  const exportLink = result && caseId && series && dataset ? (fromTslist
    ? exportHref(caseId, runId, { panel: "tslist", points: simulated?.location ? [String(simulated.location)] : undefined, quantities: isQuantityKey(series.variable) ? [series.variable] : undefined, heights: series.height_m ? [series.height_m] : undefined, average: period })
    : exportHref(caseId, runId, { panel: "wrfout", variable: series.variable, height: series.height_m, domain: domain ?? undefined, lat: dataset.station.lat, lon: dataset.station.lon })) : null;

  return (
    <Fold title={t("title")} help="observations">
      <Stack>
        <QueryView query={datasets}>
          {(items) => (
            <Select label={t("dataset")} value={datasetId} onChange={(v) => { setDatasetId(v); setSeriesKey(null); reset(); }}
              data={items.map((d) => ({ value: d.id, label: d.name }))} placeholder={items.length === 0 ? t("noSeries") : undefined} />
          )}
        </QueryView>
        <Select label={t("series")} value={seriesKey} onChange={(v) => { setSeriesKey(v); reset(); }}
          data={(dataset?.series ?? []).map((s) => ({ value: s.key, label: `${s.variable} · ${s.height_m == null ? "surface" : `${f.number(s.height_m, Number.isInteger(s.height_m) ? 0 : 1)} m ${s.height_ref}`} (${s.unit})` }))} />
        <Group grow>
          <Select label={t("project")} value={caseId} onChange={(v) => { setCaseId(v); setRunId(null); reset(); }} data={(projects.data ?? []).map((c) => ({ value: c.id, label: c.name }))} />
          <Select label={t("run")} value={runId ?? "__latest"} onChange={(v) => { setRunId(v === "__latest" ? null : v); reset(); }}
            data={[{ value: "__latest", label: t("latest") }, ...(runs.data ?? []).filter((r) => r.run_id && r.state === "succeeded").map((r) => ({ value: r.run_id!, label: `${r.label || r.run_id} · ${f.dateTime(r.finished_at)}` }))]} />
        </Group>
        <Group grow>
          <NumberField label={t("domain")} min={1} allowDecimal={false} value={domain} onValue={(v) => { setDomain(v); reset(); }} onClear={() => { setDomain(null); reset(); }} />
          <NumberField label={t("period")} unit="s" min={60} value={period} onValue={(v) => { setPeriod(v); reset(); }} />
          <NumberField label={t("availability")} min={0.01} max={1} step={0.05} value={availability} onValue={(v) => { setAvailability(v); reset(); }} />
          <NumberField label={t("tolerance")} unit="s" min={0} value={tolerance} onValue={(v) => { setTolerance(v); reset(); }} />
        </Group>
        <Group grow>
          <TextInput type="datetime-local" label={t("start")} value={start} onChange={(e) => { setStart(e.currentTarget.value); reset(); }} />
          <TextInput type="datetime-local" label={t("end")} value={end} onChange={(e) => { setEnd(e.currentTarget.value); reset(); }} />
        </Group>
        {dataset && dataset.station.lat == null && <Text c="dimmed" size="sm">{t("noStation")}</Text>}
        <Group>
          <Button disabled={!series || !caseId || dataset?.station.lat == null || dataset?.station.lon == null} loading={compare.isPending} onClick={() => compare.mutate()}>{t("compare")}</Button>
        </Group>
        {projects.error && <ErrorState error={projects.error} />} {runs.error && <ErrorState error={runs.error} />} {compare.error && <ErrorState error={compare.error} />}
        {result && <>
          <StatGrid cols={4}>
            <Stat label={t("pairs")} value={f.number(result.overall.count, 0)} />
            <Stat label={t("bias")} value={f.number(result.overall.bias, 3)} unit={prettyUnit(result.unit)} />
            <Stat label={t("rmse")} value={f.number(result.overall.rmse, 3)} unit={prettyUnit(result.unit)} />
            <Stat label={t("correlation")} value={f.number(result.overall.correlation, 3)} />
          </StatGrid>
          <TimeChart title={t("timeseries")} unit={prettyUnit(result.unit)} dotsOnly={result.circular} compass={result.circular}
            rows={result.series.times.map((time, i) => ({ time, reference: result.series.reference[i], simulation: result.series.evaluated[i] }))}
            series={[{ name: "reference", label: t("reference"), color: CHART_COLORS.measured }, { name: "simulation", label: t("simulation"), color: CHART_COLORS.main }]} />
          {simulated && <SourceLine source={fromTslist ? "tslist" : "wrfout"} seconds={period} method={simulated.method ? String(simulated.method) : undefined} />}
          <Scatter observed={result.scatter.reference} simulated={result.scatter.evaluated} unit={prettyUnit(result.unit)} />
          <Text fw={600}>{t("notes")}</Text>
          {[...result.alignment, ...result.caveats, ...result.notes].map((note, i) => <Text size="xs" c="dimmed" key={i}>{note}</Text>)}
          {exportLink && (
            <Group justify="flex-end">
              <Button component="a" href={exportLink} variant="default" leftSection={<IconTableExport size={16} />}>{t("export")}</Button>
            </Group>
          )}
        </>}
      </Stack>
    </Fold>
  );
}

function Scatter({ observed, simulated, unit }: { observed: number[]; simulated: number[]; unit: string }) {
  const t = useT(messages);
  const f = useFormat();
  const all = [...observed, ...simulated].filter(Number.isFinite);
  if (!all.length) return null;
  const min = Math.min(...all);
  const span = Math.max(...all) - min || 1;
  const coord = (v: number) => 50 + ((v - min) / span) * 260;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((k) => min + k * span);
  const digits = span < 2 ? 2 : span < 20 ? 1 : 0;
  return (
    <svg viewBox="0 0 340 350" width="100%" style={{ maxWidth: 420, alignSelf: "center" }} role="img" aria-label={t("scatter")}>
      {ticks.map((v) => (
        <g key={v}>
          <path d={`M 50 ${360 - coord(v)} H 310 M ${coord(v)} 50 V 310`} stroke="var(--ows-border)" />
          <text x={coord(v)} y="326" textAnchor="middle" fontSize="12" fill="currentColor">{f.number(v, digits)}</text>
          <text x="44" y={364 - coord(v)} textAnchor="end" fontSize="12" fill="currentColor">{f.number(v, digits)}</text>
        </g>
      ))}
      <path d="M 50 50 V 310 H 310" stroke="var(--ows-muted)" fill="none" />
      <path d="M 50 310 L 310 50" stroke="var(--ows-muted)" strokeDasharray="5 4" />
      {/* Full colour: at 60% opacity the green of the dark mode is lost on black (contrast 1.7:1) */}
      {observed.map((x, i) => <circle key={i} cx={coord(x)} cy={360 - coord(simulated[i])} r={2.2} fill={cssColor(CHART_COLORS.main)}><title>{f.numbers([x, simulated[i]], 3)} {unit}</title></circle>)}
      <text x="180" y="345" textAnchor="middle" fill="currentColor" fontSize="12">{t("reference")} ({unit})</text>
      <text transform="translate(12 180) rotate(-90)" textAnchor="middle" fill="currentColor" fontSize="12">{t("simulation")} ({unit})</text>
    </svg>
  );
}
