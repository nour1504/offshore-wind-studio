/**
 * Wind analyses of the run at one point: the analysis in tabs, its few settings on the left
 * (filled in), the result on the right as soon as the settings change: three figures, the chart,
 * and the table folded under it. How each analysis is computed is in the "i" tooltip.
 *
 * The points are the turbines, read in the tslist outputs as 10-minute means of every model
 * time step (the turbines of one grid cell share its wind; each keeps its own power curve).
 * A sentence under the title says what is looked at; the equations are under the table.
 */
import { Grid, Group, Paper, SegmentedControl, Select, SimpleGrid, Stack, Tabs, Text, TextInput, Tooltip } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { IconAngle, IconArrowsVertical, IconBolt, IconChartDots, IconChartHistogram, IconChartLine, IconClockHour4, IconCompass, IconDownload, IconInfoCircle, IconRotateClockwise2, IconTemperatureSun, type Icon } from "@tabler/icons-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { analysisApi, type AnalysisKind, type AnalysisResult } from "../../api/analysis";
import { energyApi } from "../../api/energy";
import { ApiError } from "../../api/client";
import type { SeriesRef } from "../../api/explore";
import type { ResultsSummary } from "../../api/types";
import { useLoadedDraft } from "../../app/CaseDraft";
import { sectionMessages } from "../../app/sections";
import { defineMessages, useFormat, useLang, useT } from "../../i18n";
import { Equations } from "../../ui/Equation";
import { Fold } from "../../ui/Fold";
import { GlideTabsList } from "../../ui/GlideTabs";
import { NumberField } from "../../ui/Inputs";
import { Page } from "../../ui/Page";
import { ErrorState, LoadingState } from "../../ui/States";
import { ToolBar, ToolButton } from "../../ui/ToolBar";
import { AnalysisDisplay, AnalysisTable, shortClass } from "./analyses/AnalysisDisplay";
import type { EnergySectors, PowerCurve } from "../../api/energy";
import { analysisEquations } from "./analyses/documentation";
import { PowerCurveChart, ProductionChart, type SectorEnergy, sectorEnergy } from "./analyses/PointCharts";
import { turbineLabels } from "./explorer/turbineLabels";
import { downloadText } from "./results/download";
import { ResultContext } from "./results/ResultContext";
import { sharedMessages } from "./results/shared";

// The tabs; the production per direction and the power curve come from the power of WRF (the
// energy of the results page)
type Kind = Extract<AnalysisKind, "rose" | "weibull" | "profile" | "grouped" | "stability" | "shear" | "veer" | "aggregate"> | "production" | "curve";
const KINDS: { kind: Kind; icon: Icon }[] = [
  { kind: "rose", icon: IconCompass },
  { kind: "production", icon: IconBolt },
  { kind: "curve", icon: IconChartDots },
  { kind: "weibull", icon: IconChartHistogram },
  { kind: "profile", icon: IconArrowsVertical },
  { kind: "grouped", icon: IconClockHour4 },
  { kind: "stability", icon: IconTemperatureSun },
  { kind: "shear", icon: IconAngle },
  { kind: "veer", icon: IconRotateClockwise2 },
  { kind: "aggregate", icon: IconChartLine },
];
const MULTI: Kind[] = ["profile", "shear", "veer"];
// Fewer values than this make a wind rose say nothing: six hours of 10-minute means
const ROSE_MINIMUM = 36;
// The tslist series are read as means over this period (the window method's 10 minutes)
const AVERAGING_S = 600;

const messages = defineMessages({
  en: {
    kinds: { rose: "Wind rose", production: "Production", curve: "Power curve", weibull: "Distribution", profile: "Profile", grouped: "Daily cycle", stability: "Stability", shear: "Shear", veer: "Veer", aggregate: "Over time" },
    point: "Turbine", domain: "Domain", height: "Height", heights: "Heights (m)",
    run: "Run", sectors: "Sectors", grouping: "Grouping", hour: "Hour", month: "Month",
    energy: "Energy", loss: "Wake loss",
    scheme: "Classes", seven: "7 classes", extended: "Extended", three: "3 classes", table: "Table", csv: "Download (CSV)",
    samples: "Values", calm: "Calm", dominant: "Main direction", mean: "Mean", deviation: "Standard deviation", peak: "Maximum",
    scale: "Scale A", shape: "Shape k", alphaProfile: "Exponent of the mean profile", alphaMean: "Mean exponent", lowest: "Lowest", highest: "Highest", frequent: "Most frequent",
    veer: "Mean veer", fewer: "Too few values: {n} for {min}", share: "Share", values: "Values", cpMax: "Highest Cp", powerMax: "Highest power",
    show: "Shown", power: "Power", documentation: "Documentation", noFree: "No run without turbines: the power curve is drawn against its free wind.",
    about: {
      rose: "Where the wind comes from, and how fast, at the chosen height.",
      production: "The energy produced by the turbine, by wind direction.",
      curve: "The power of the turbine against the free wind at hub height.",
      weibull: "How the wind speeds are spread at the chosen height.",
      profile: "The mean wind speed at each height.",
      grouped: "The mean wind speed by hour of the day.",
      groupedMonth: "The mean wind speed by month.",
      stability: "The stability of the atmosphere, from the Obukhov length.",
      shear: "How much the wind speed grows with height.",
      veer: "How much the wind direction turns between the lowest and highest heights.",
      aggregate: "The mean wind speed, hour by hour.",
    },
  },
  fr: {
    kinds: { rose: "Rose des vents", production: "Production", curve: "Courbe de puissance", weibull: "Distribution", profile: "Profil", grouped: "Cycle journalier", stability: "Stabilité", shear: "Cisaillement", veer: "Rotation", aggregate: "Au cours du temps" },
    point: "Éolienne", domain: "Domaine", height: "Hauteur", heights: "Hauteurs (m)",
    run: "Calcul", sectors: "Secteurs", grouping: "Regroupement", hour: "Heure", month: "Mois",
    energy: "Énergie", loss: "Pertes de sillage",
    scheme: "Classes", seven: "7 classes", extended: "Étendue", three: "3 classes", table: "Tableau", csv: "Télécharger (CSV)",
    samples: "Valeurs", calm: "Calmes", dominant: "Direction principale", mean: "Moyenne", deviation: "Écart type", peak: "Maximum",
    scale: "Échelle A", shape: "Forme k", alphaProfile: "Exposant du profil moyen", alphaMean: "Exposant moyen", lowest: "En bas", highest: "En haut", frequent: "La plus fréquente",
    veer: "Rotation moyenne", fewer: "Trop peu de valeurs : {n} pour {min}", share: "Part", values: "Valeurs", cpMax: "Cp le plus haut", powerMax: "Puissance la plus haute",
    show: "Affichage", power: "Puissance", documentation: "Documentation", noFree: "Pas de calcul sans éoliennes : la courbe de puissance se trace au vent libre de ce calcul.",
    about: {
      rose: "La direction d'où vient le vent, et sa vitesse, à la hauteur choisie.",
      production: "L'énergie produite par l'éolienne, selon la direction du vent.",
      curve: "La puissance de l'éolienne selon le vent libre à hauteur de moyeu.",
      weibull: "La répartition des vitesses du vent à la hauteur choisie.",
      profile: "La vitesse moyenne du vent à chaque hauteur.",
      grouped: "La vitesse moyenne du vent selon l'heure de la journée.",
      groupedMonth: "La vitesse moyenne du vent selon le mois.",
      stability: "La stabilité de l'atmosphère, d'après la longueur d'Obukhov.",
      shear: "L'augmentation de la vitesse du vent avec la hauteur.",
      veer: "La rotation de la direction du vent entre la hauteur la plus basse et la plus haute.",
      aggregate: "La vitesse moyenne du vent, heure par heure.",
    },
  },
});

type Row = Record<string, unknown>;
const rows = (value: unknown): Row[] => (Array.isArray(value) ? (value.filter((v) => v && typeof v === "object") as Row[]) : []);
const num = (value: unknown) => (typeof value === "number" && Number.isFinite(value) ? value : null);
const UNITS: Record<string, string> = { "m s-1": "m/s" };

type Figure = { label: string; value: number | null; unit: string; digits: number; text?: string };

/** Three figures that summarise a result, read from what each analysis returns. */
function figures(result: AnalysisResult, t: ReturnType<typeof useT<typeof messages.en>>, f: ReturnType<typeof useFormat>): Figure[] {
  const unit = UNITS[String(result.unit ?? "m s-1")] ?? String(result.unit ?? "");
  const stats = result.statistics as Row | undefined;
  if (result.kind === "rose") {
    const sectors = rows(result.sectors);
    const top = sectors.reduce<Row | null>((best, s) => (best === null || Number(s.frequency_pct) > Number(best.frequency_pct) ? s : best), null);
    return [
      { label: t("samples"), value: num((result.samples as Row | undefined)?.valid), unit: "", digits: 0 },
      { label: t("dominant"), value: num(top?.centre_deg), unit: "°", digits: 0 },
      { label: t("calm"), value: num((result.calm as Row | undefined)?.frequency_pct), unit: "%", digits: 1 },
    ];
  }
  if (result.kind === "weibull") {
    // Every valid speed, calms included; A and k: the Weibull curve fitted to the speeds above 0
    const seen = result.observed_all as Row | undefined;
    const fit = ((result.all as Row | undefined)?.fits as Record<string, Row> | undefined)?.mle;
    const histogram = result.histogram as { edges: number[]; counts_all: number[] } | undefined;
    const top = histogram ? histogram.counts_all.indexOf(Math.max(...histogram.counts_all)) : -1;
    return [
      { label: t("mean"), value: num(seen?.mean), unit: "m/s", digits: 2 },
      { label: t("frequent"), value: null, unit: "", digits: 0, text: histogram && top >= 0 ? `${f.number(histogram.edges[top], 0)}–${f.number(histogram.edges[top + 1], 0)} m/s` : "–" },
      { label: t("scale"), value: num(fit?.A), unit: "m/s", digits: 2 },
      { label: t("shape"), value: num(fit?.k), unit: "", digits: 2 },
    ];
  }
  if (result.kind === "profile") {
    const profile = rows(result.rows).filter((r) => num(r.mean) !== null).sort((a, b) => Number(a.height_m) - Number(b.height_m));
    const low = profile[0], high = profile.at(-1);
    const alpha = low && high && Number(low.mean) > 0 && Number(high.height_m) > Number(low.height_m)
      ? Math.log(Number(high.mean) / Number(low.mean)) / Math.log(Number(high.height_m) / Number(low.height_m)) : null;
    return [
      { label: `${t("lowest")} · ${num(low?.height_m) ?? "–"} m`, value: num(low?.mean), unit, digits: 2 },
      { label: `${t("highest")} · ${num(high?.height_m) ?? "–"} m`, value: num(high?.mean), unit, digits: 2 },
      { label: t("alphaProfile"), value: alpha, unit: "", digits: 3 },
    ];
  }
  if (result.kind === "shear" || result.kind === "veer") {
    const group = rows(result.groups)[0];
    const stat = (result.kind === "shear" ? group?.pairwise : group) as Row | undefined;
    const label = result.kind === "shear" ? t("alphaMean") : t("veer");
    const u = result.kind === "shear" ? "" : "°";
    return [
      { label, value: num(stat?.mean), unit: u, digits: result.kind === "shear" ? 3 : 1 },
      { label: t("deviation"), value: num(stat?.std), unit: u, digits: result.kind === "shear" ? 3 : 1 },
      { label: t("peak"), value: num(stat?.max), unit: u, digits: result.kind === "shear" ? 3 : 1 },
    ];
  }
  if (result.kind === "stability") {
    const classes = rows(result.classes);
    const top = classes.reduce<Row | null>((best, c) => (best === null || Number(c.frequency_pct) > Number(best.frequency_pct) ? c : best), null);
    const count = classes.reduce((sum, c) => sum + (num(c.count) ?? 0), 0);
    return [
      { label: t("samples"), value: count, unit: "", digits: 0 },
      { label: t("frequent"), value: null, unit: "", digits: 0, text: shortClass(top?.label) },
      { label: t("share"), value: num(top?.frequency_pct), unit: "%", digits: 1 },
    ];
  }
  if (result.kind === "grouped") {
    const groups = rows(result.groups).filter((g) => num(g.mean) !== null);
    const top = groups.reduce<Row | null>((best, g) => (best === null || Number(g.mean) > Number(best.mean) ? g : best), null);
    const all = groups.reduce((sum, g) => sum + Number(g.mean) * (num(g.count) ?? 0), 0) / Math.max(1, groups.reduce((sum, g) => sum + (num(g.count) ?? 0), 0));
    return [
      { label: t("mean"), value: groups.length ? all : null, unit, digits: 2 },
      { label: t("peak"), value: num(top?.mean), unit, digits: 2 },
      { label: t("hour"), value: null, unit: "", digits: 0, text: String(top?.label ?? "–").split("–")[0].trim() },
    ];
  }
  return [
    { label: t("mean"), value: num(stats?.mean), unit, digits: 2 },
    { label: t("deviation"), value: num(stats?.std), unit, digits: 2 },
    { label: t("peak"), value: num(stats?.max), unit, digits: 2 },
  ];
}

/** The three figures of the production tab. */
function productionFigures(energy: SectorEnergy[], t: ReturnType<typeof useT<typeof messages.en>>): Figure[] {
  const total = energy.reduce((sum, row) => sum + (row.energy_mwh ?? 0), 0);
  const without = energy.reduce((sum, row) => sum + (row.energy_control_mwh ?? 0), 0);
  const top = energy.reduce<SectorEnergy | null>((best, row) => (best === null || (row.energy_mwh ?? 0) > (best.energy_mwh ?? 0) ? row : best), null);
  return [
    { label: t("energy"), value: total, unit: "MWh", digits: 1 },
    { label: t("dominant"), value: top?.sector ?? null, unit: "°", digits: 0 },
    without > 0
      ? { label: t("loss"), value: 100 * (1 - total / without), unit: "%", digits: 1 }
      : { label: t("samples"), value: energy.reduce((sum, row) => sum + row.hours, 0), unit: "", digits: 0 },
  ];
}

/** The three figures of the power curve tab. */
function curveFigures(curve: PowerCurve, t: ReturnType<typeof useT<typeof messages.en>>): Figure[] {
  const cps = curve.bins.map((b) => b.cp).filter((v): v is number => typeof v === "number");
  return [
    { label: t("values"), value: curve.points.length, unit: "", digits: 0 },
    { label: t("cpMax"), value: cps.length ? Math.max(...cps) : null, unit: "", digits: 3 },
    { label: t("powerMax"), value: curve.bins.length ? Math.max(...curve.bins.map((b) => b.power_mw)) : null, unit: "MW", digits: 2 },
  ];
}

function Analyses({ summary }: { summary: ResultsSummary }) {
  const { caseId, draft } = useLoadedDraft();
  const t = useT(messages);
  const ts = useT(sharedMessages);
  const f = useFormat();
  const { lang } = useLang();
  const run = summary.run_id;
  const [kind, setKind] = useState<Kind>("rose");
  const [domain, setDomain] = useState(summary.farm_domain ?? summary.domains.at(-1) ?? 1);
  // The height is the hub of the chosen turbine until another one is typed
  const [typed, setHeight] = useState<number | null>(null);
  const [heights, setHeights] = useState(() => {
    const hub = Math.round(summary.hub_height_m);
    return [25, 50, hub, 150, 200].filter((h, i, all) => all.indexOf(h) === i).sort((a, b) => a - b).join(", ");
  });
  const [stage, setStage] = useState<"main" | "control">("main");
  const [sectors, setSectors] = useState("12");
  const [grouping, setGrouping] = useState("hour");
  const [scheme, setScheme] = useState("gryning2007");
  const [show, setShow] = useState<"power" | "cp">("power");

  // Points: the turbines (the wind of their cell in the tslist outputs, their own power)
  const labels = useMemo(() => turbineLabels(draft.farms), [draft.farms]);
  const places = useMemo(() => draft.farms.flatMap((farm) => farm.turbines.map((tb, i) => ({
    value: labels.get(`${farm.id}:${i + 1}`) ?? `${farm.id}-${i + 1}`, label: `${farm.name} · ${tb.id || i + 1}`,
    hub: draft.turbine_types[String(tb.type)]?.hub_height_m ?? summary.hub_height_m,
  }))), [draft.farms, draft.turbine_types, labels, summary.hub_height_m]);
  const [place, setPlace] = useState<string | null>(null);
  const chosen = places.find((p) => p.value === place) ?? places[0];
  const height = typed ?? chosen?.hub ?? summary.hub_height_m;
  const base: SeriesRef = { kind: "run", case_id: caseId, run_id: run, domain, stage, variable: "wind_speed", height_m: height, options: { averaging_s: AVERAGING_S }, location: chosen?.value };
  const heightList = heights.split(/[,;\s]+/).filter(Boolean).map(Number).filter((h) => Number.isFinite(h) && h > 0).sort((a, b) => a - b);
  const levels = kind === "profile" ? heightList : [heightList[0], heightList.at(-1)].filter((h): h is number => h !== undefined);

  // The request of the tab
  const requests: { kind: AnalysisKind | "sectors" | "curve"; body: unknown }[] = (() => {
    const selection = {};
    const wind = { speed: { ...base, variable: "wind_speed" }, direction: { ...base, variable: "wind_direction" } };
    if (kind === "production") return [{ kind: "sectors", body: { turbine: chosen?.value ?? "", count: Number(sectors) } }];
    if (kind === "curve") return [{ kind: "curve", body: { turbine: chosen?.value ?? "" } }];
    if (kind === "rose") return [{ kind, body: { selection, winds: [wind], sectors: Number(sectors), speed_bins: [0, 3, 6, 9, 12, 15, 20, 25], calm: 0 } }];
    if (kind === "weibull") return [{ kind, body: { selection, wind, sectors: 0, methods: ["mle"] } }];
    if (kind === "profile" || kind === "shear" || kind === "veer") return [{ kind, body: { selection, series: levels.map((h) => ({ ...base, height_m: h, variable: kind === "veer" ? "wind_direction" : "wind_speed" })) } }];
    if (kind === "stability") return [{ kind, body: { selection, series: { ...base, variable: "obukhov_length" }, scheme } }];
    if (kind === "grouped") return [{ kind, body: { selection, series: base, grouping: { kind: grouping } } }];
    return [{ kind: "aggregate", body: { selection, series: base, period: "hour" } }];
  })();
  // The power curve is drawn against the free wind: without a run without turbines, none
  const noFree = kind === "curve" && !summary.has_control;
  const ready = Boolean(chosen) && (!MULTI.includes(kind) || levels.length >= 2) && !noFree;
  const [asked] = useDebouncedValue(requests, 350);
  const result = useQuery({
    queryKey: ["analysis", asked],
    queryFn: () => Promise.all(asked.map((request) => (request.kind === "sectors"
      // The energy of the results page per direction sector, in the shape of an analysis
      ? (() => {
        const { turbine, count } = request.body as { turbine: string; count: number };
        return energyApi.sectors(caseId, run, count, turbine)
          .then((answer): AnalysisResult => ({ kind: "sectors", method: [answer.method_text, answer.direction].filter(Boolean).join(" · "), notes: [], inputs: [], tables: [], energy: answer }));
      })()
      : request.kind === "curve"
      // The power curve rebuilt from the run, in the shape of an analysis
      ? (() => {
        const body = request.body as { turbine: string };
        return energyApi.curve(caseId, run, body.turbine)
          .then((curve): AnalysisResult => ({ kind: "curve", method: [curve.method_text, curve.wind].filter(Boolean).join(" · "), notes: [], inputs: [], tables: [], curve }));
      })()
      : analysisApi.run(request.kind, request.body)))),
    enabled: ready, retry: false, staleTime: Infinity,
  });
  const data = result.data?.[0];
  const energy = useMemo(() => (data?.energy ? sectorEnergy(data.energy as EnergySectors) : []), [data]);
  const withControl = typeof (data?.energy as EnergySectors | undefined)?.reference_mwh === "number";
  const csv = useMutation({ mutationFn: (table: string) => analysisApi.csv(requests[0].kind as AnalysisKind, requests[0].body, table), onSuccess: (text) => downloadText(text, `${kind}.csv`) });

  // A refusal for lack of values is a state of the data, said in a few words
  const refusal = result.error instanceof ApiError && result.error.status === 422 ? String(result.error.message) : null;
  const fewer = refusal?.match(/(\d+) samples?, fewer than the minimum of (\d+)/) ?? refusal?.match(/(\d+) valeurs?.*minimum de (\d+)/);
  // What is drawn follows the result itself (settings are sent a moment later than they change)
  const production = data?.kind === "sectors";
  const curve = data?.kind === "curve" ? (data.curve as PowerCurve) : null;
  const shown = data && (production ? productionFigures(energy, t) : curve ? curveFigures(curve, t) : figures(data, t, f));
  const about = kind === "grouped" && grouping === "month" ? t("about.groupedMonth") : t(`about.${kind}`);

  return (
    <Tabs value={kind} onChange={(value) => value && setKind(value as Kind)} keepMounted={false}>
      <GlideTabsList mb="xl" grow style={{ flexWrap: "nowrap", overflowX: "auto" }}>
        {KINDS.map(({ kind: value }) => (
          <Tabs.Tab key={value} value={value}>{t(`kinds.${value}`)}</Tabs.Tab>
        ))}
      </GlideTabsList>
      <Grid gap="xl" align="stretch">
        <Grid.Col span={{ base: 12, md: 4 }}>
          <Paper withBorder radius="lg" p="lg" h="100%">
          <Stack gap="md">
            <Select searchable label={t("point")} value={chosen?.value ?? null} onChange={(value) => { if (value) { setPlace(value); setHeight(null); } }} allowDeselect={false} data={places} />
            {summary.domains.length > 1 && kind !== "production" && kind !== "curve" && (
              <Stack gap={6}>
                <Text size="sm" fw={500}>{t("domain")}</Text>
                <SegmentedControl fullWidth value={String(domain)} onChange={(value) => setDomain(Number(value))} data={summary.domains.map((d) => ({ value: String(d), label: `d${String(d).padStart(2, "0")}` }))} />
              </Stack>
            )}
            {MULTI.includes(kind)
              ? <TextInput label={t("heights")} value={heights} onChange={(event) => setHeights(event.currentTarget.value)} />
              : kind !== "stability" && kind !== "production" && kind !== "curve" && <NumberField label={t("height")} unit="m" min={1} value={height} onValue={setHeight} />}
            {(kind === "rose" || kind === "production") && (
              <Stack gap={6}>
                <Text size="sm" fw={500}>{t("sectors")}</Text>
                <SegmentedControl fullWidth value={sectors} onChange={setSectors} data={["8", "12", "16", "36"]} />
              </Stack>
            )}
            {kind === "grouped" && (
              <Stack gap={6}>
                <Text size="sm" fw={500}>{t("grouping")}</Text>
                <SegmentedControl fullWidth value={grouping} onChange={setGrouping} data={[{ value: "hour", label: t("hour") }, { value: "month", label: t("month") }]} />
              </Stack>
            )}
            {kind === "stability" && (
              <Stack gap={6}>
                <Text size="sm" fw={500}>{t("scheme")}</Text>
                <SegmentedControl fullWidth value={scheme} onChange={setScheme} data={[{ value: "gryning2007", label: t("seven") }, { value: "gryning2007-extended", label: t("extended") }, { value: "gryning2007-3", label: t("three") }]} />
              </Stack>
            )}
            {kind === "curve" && (
              <Stack gap={6}>
                <Text size="sm" fw={500}>{t("show")}</Text>
                <SegmentedControl fullWidth value={show} onChange={(value) => setShow(value as "power" | "cp")} data={[{ value: "power", label: t("power") }, { value: "cp", label: "Cp" }]} />
              </Stack>
            )}
            {summary.has_control && kind !== "production" && kind !== "curve" && (
              <Stack gap={6}>
                <Text size="sm" fw={500}>{t("run")}</Text>
                <SegmentedControl fullWidth value={stage} onChange={(value) => setStage(value as "main" | "control")} data={[{ value: "main", label: ts("withFarm") }, { value: "control", label: ts("withoutFarm") }]} />
              </Stack>
            )}
          </Stack>
          </Paper>
        </Grid.Col>
        <Grid.Col span={{ base: 12, md: 8 }}>
          <Paper withBorder radius="lg" p="lg" h="100%" className="ows-analysis">
            <Group justify="space-between" mb="md" wrap="nowrap" align="flex-start">
              <Stack gap={2}>
                <Group gap={6} wrap="nowrap">
                  <Text fw={600} size="lg">{t(`kinds.${kind}`)}</Text>
                  {data && <Tooltip label={data.method} multiline w={340} withArrow><IconInfoCircle size={15} className="ows-kpi-info" aria-label={data.method} /></Tooltip>}
                </Group>
                <Text size="sm" c="dimmed">{about}</Text>
              </Stack>
              {data && data.tables.length > 0 && (
                <ToolBar label={t("table")}>
                  <ToolButton icon={IconDownload} label={t("csv")} onClick={() => csv.mutate(data.kind === "weibull" && data.tables.includes("histogram") ? "histogram" : data.tables[0])} />
                </ToolBar>
              )}
            </Group>
            {noFree ? <Text size="sm" fw={600} c="dimmed" ta="center" py={60}>{t("noFree")}</Text>
              : result.isLoading || (ready && result.isFetching && !data) ? <LoadingState rows={6} />
              : refusal ? <Text size="sm" fw={600} c="dimmed" ta="center" py={60}>{fewer ? t("fewer", { n: fewer[1], min: fewer[2] }) : refusal}</Text>
                : result.error ? <ErrorState error={result.error} />
                  : data && data.kind === "rose" && Number((data.samples as Row | undefined)?.valid ?? 0) < ROSE_MINIMUM
                    ? <Text size="sm" fw={600} c="dimmed" ta="center" py={60}>{t("fewer", { n: String((data.samples as Row | undefined)?.valid ?? 0), min: String(ROSE_MINIMUM) })}</Text>
                  : data && shown && (
                    <Stack gap="lg" className="ows-stagger">
                      <SimpleGrid cols={shown.length} spacing={0} className="ows-kpis">
                        {shown.map((figure) => (
                          <Stack key={figure.label} gap={6} className="ows-kpi">
                            <Text size="sm" fw={600} c="dimmed">{figure.label}</Text>
                            <Group gap={6} align="baseline" wrap="nowrap">
                              <Text className="ows-num ows-kpi-value" fz={figure.text ? 22 : undefined} title={figure.text}>{figure.text ?? (figure.value === null ? "–" : f.number(figure.value, figure.digits))}</Text>
                              {figure.value !== null && figure.unit && <Text size="sm" fw={600} c="dimmed">{figure.unit}</Text>}
                            </Group>
                          </Stack>
                        ))}
                      </SimpleGrid>
                      {production ? <ProductionChart rows={energy} control={withControl} /> : curve ? <PowerCurveChart curve={curve} show={show} /> : <AnalysisDisplay result={data} />}
                    </Stack>
                  )}
          </Paper>
        </Grid.Col>
      </Grid>
      {csv.error && <ErrorState error={csv.error} />}
      {data && (
        <Stack mt="xl" gap="xl">
          {(data.tables.length > 0 || production || curve) && (
            <Fold title={t("table")}>
              <AnalysisTable result={data} rows={production ? energy.map((row) => ({ ...row })) : curve ? curve.bins.map(({ centre_ms, count, speed_ms, power_mw, cp }) => ({ centre_ms, count, speed_ms, power_mw, cp })) : undefined} />
            </Fold>
          )}
          <Fold title={t("documentation")}>
            <Equations lines={analysisEquations(production ? "production" : curve ? "curve" : (data.kind as Parameters<typeof analysisEquations>[0]), lang, scheme)} />
          </Fold>
        </Stack>
      )}
    </Tabs>
  );
}

export default function AnalysesPage() {
  const t = useT(sectionMessages);
  return (
    <Page title={t("project.analyses")} help="analyses" fluid>
      <ResultContext>{(summary) => <Analyses key={summary.run_id} summary={summary} />}</ResultContext>
    </Page>
  );
}
