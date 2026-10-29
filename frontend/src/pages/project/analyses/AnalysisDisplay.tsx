import { Stack, Text } from "@mantine/core";
import type { AnalysisResult } from "../../../api/analysis";
import { defineMessages, useFormat, useLang, useT } from "../../../i18n";
import { DataTable } from "../../../ui/DataTable";
import { prettyUnit } from "../explorer/quantities";
import { CHART_COLORS, cssColor, SERIES_COLORS, TimeChart } from "../results/TimeChart";
import { Bars, Curves } from "./Charts";
import { RoseChart, WeibullChart } from "./WindCharts";

const messages = defineMessages({
  en: {
    mean: "Mean", frequency: "Frequency", speed: "Wind speed", height: "Height", pairwise: "Between lowest and highest height", fitted: "Fit over all heights",
    shear: "Shear exponent over time", veer: "Wind veer over time", average: "Hourly mean", month: "Month · UTC", hour: "Hour · UTC", all: "All",
  },
  fr: {
    mean: "Moyenne", frequency: "Fréquence", speed: "Vitesse du vent", height: "Hauteur", pairwise: "Entre les hauteurs minimale et maximale", fitted: "Ajustement sur toutes les hauteurs",
    shear: "Exposant de cisaillement au cours du temps", veer: "Rotation du vent au cours du temps", average: "Moyenne horaire", month: "Mois · UTC", hour: "Heure · UTC", all: "Ensemble",
  },
});
const tableMessages = defineMessages({ en: { count: "Samples", mean: "Mean", std: "Standard deviation", min: "Minimum", max: "Maximum", k: "Shape k", A: "Scale A (m/s)", method: "Fit", r2_cdf: "R² · CDF", ks: "KS distance", frequency_pct: "Frequency (%)", centre_deg: "Direction (°)", mean_speed: "Mean speed (m/s)", energy_pct: "U³ share (%)", height_m: "Height (m)", availability: "Availability", label: "Group", share_pct: "Share of time (%)", power_density: "Power density (W/m²)", mean_cube: "Mean U³", mean_cube_ratio: "Fitted / observed U³", share_above_mean: "Share above mean", refused: "Reason", sector: "Sector (°)", energy_mwh: "Energy (MWh)", energy_control_mwh: "Without turbines (MWh)", loss_pct: "Wake loss (%)", hours: "Hours", speed_class: "Speed (m/s)", centre_ms: "Bin (m/s)", speed_ms: "Mean speed (m/s)", power_mw: "Mean power (MW)", cp: "Cp" }, fr: { count: "Valeurs", mean: "Moyenne", std: "Écart-type", min: "Minimum", max: "Maximum", k: "Forme k", A: "Échelle A (m/s)", method: "Ajustement", r2_cdf: "R² · CDF", ks: "Distance KS", frequency_pct: "Fréquence (%)", centre_deg: "Direction (°)", mean_speed: "Vitesse moyenne (m/s)", energy_pct: "Part de U³ (%)", height_m: "Hauteur (m)", availability: "Disponibilité", label: "Groupe", share_pct: "Part du temps (%)", power_density: "Densité de puissance (W/m²)", mean_cube: "Moyenne de U³", mean_cube_ratio: "U³ ajusté / observé", share_above_mean: "Part au-dessus de la moyenne", refused: "Motif", sector: "Secteur (°)", energy_mwh: "Énergie (MWh)", energy_control_mwh: "Sans éoliennes (MWh)", loss_pct: "Pertes de sillage (%)", hours: "Heures", speed_class: "Vitesse (m/s)", centre_ms: "Classe (m/s)", speed_ms: "Vitesse moyenne (m/s)", power_mw: "Puissance moyenne (MW)", cp: "Cp" } });

type Row = Record<string, unknown>;
const records = (data: unknown): Row[] => (Array.isArray(data) ? (data.filter((v) => v && typeof v === "object") as Row[]) : []);

/** The class name without its bounds: "Very unstable (-100 < L ≤ -50 m)" → "Very unstable". */
export const shortClass = (label: unknown) => String(label ?? "–").replace(/\s*\(.*\)\s*$/, "");

export function AnalysisDisplay({ result }: { result: AnalysisResult }) {
  const t = useT(messages);
  const { lang } = useLang();
  const unit = prettyUnit(String(result.unit ?? ""));
  let chart = null;
  if (result.kind === "rose") chart = <RoseChart result={result} />;
  else if (result.kind === "weibull") chart = <WeibullChart result={result} />;
  else if (result.kind === "aggregate" || result.kind === "shear" || result.kind === "veer") {
    const times = result.times as string[];
    const names = result.kind === "shear" ? ["alpha_pairwise", "alpha_fit"] : result.kind === "veer" ? ["veer_deg"] : ["mean"];
    const title = t(result.kind === "aggregate" ? "average" : result.kind);
    chart = (
      <TimeChart title={title} unit={result.kind === "veer" ? "°" : result.kind === "shear" ? "" : unit} digits={result.kind === "shear" ? 3 : result.kind === "veer" ? 1 : 2}
        rows={times.map((time, i) => ({ time, ...Object.fromEntries(names.map((k) => [k, (result[k] as (number | null)[])[i]])) }))}
        series={names.map((name, i) => ({ name, label: result.kind === "shear" ? t(i === 0 ? "pairwise" : "fitted") : title, color: i === 0 ? CHART_COLORS.main : CHART_COLORS.reference, dashed: i > 0 }))}
        dotsOnly={result.kind === "veer"} />
    );
  } else if (result.kind === "profile") {
    const rows = records(result.rows).filter((r) => typeof r.mean === "number");
    const groups = [...new Set(rows.map((r) => String(r.group)))];
    chart = (
      <Curves along="y" label={t("height")}
        x={{ label: t("speed"), unit, digits: 2 }} y={{ label: t("height"), unit: "m", digits: 0, from0: true }}
        curves={groups.map((group, i) => ({
          key: group, label: groups.length === 1 ? t("mean") : group.toLowerCase() === "all" ? t("all") : group, color: cssColor(SERIES_COLORS[i % SERIES_COLORS.length]), kind: "both" as const,
          points: rows.filter((r) => String(r.group) === group).map((r) => ({ x: Number(r.mean), y: Number(r.height_m) })),
        }))} />
    );
  } else {
    const grouping = result.grouping as { key?: string } | undefined;
    const month = new Intl.DateTimeFormat(lang === "fr" ? "fr-FR" : "en-GB", { month: "short", timeZone: "UTC" });
    const rows = records(result.rows ?? result.classes ?? result.groups);
    const stability = result.kind === "stability";
    const metric = stability ? "frequency_pct" : "mean";
    if (rows.some((r) => typeof r[metric] === "number")) {
      chart = (
        <Bars label={t(stability ? "frequency" : "mean")} unit={stability ? "%" : unit} digits={stability ? 1 : 2} keys={[]}
          xLabel={grouping?.key === "month" ? t("month") : grouping?.key === "hour" ? t("hour") : undefined}
          tipLabels={{ main: t(stability ? "frequency" : "mean") }}
          bars={rows.map((row, k) => ({
            key: String(row.key ?? row.label ?? k),
            label: grouping?.key === "month" ? month.format(new Date(Date.UTC(2000, Number(row.key) - 1, 1)))
              : grouping?.key === "hour" ? String(row.key ?? k).padStart(2, "0")
                : stability ? shortClass(row.label) : String(row.label ?? k),
            title: stability || grouping?.key === "hour" ? String(row.label ?? "") : undefined,
            value: typeof row[metric] === "number" ? (row[metric] as number) : null,
          }))} />
      );
    }
  }
  const refused = (result.all as { refused?: string } | undefined)?.refused;
  return <Stack gap="lg">{chart}{refused && <Text size="sm" fw={600} c="dimmed" ta="center">{refused}</Text>}</Stack>;
}

/** The numbers behind the chart, as a sortable table. */
export function AnalysisTable({ result, rows: given }: { result: AnalysisResult; rows?: Row[] }) {
  const th = useT(tableMessages);
  const f = useFormat();
  const histogram = result.histogram as { edges: number[]; counts_all: number[] } | undefined;
  const total = histogram ? histogram.counts_all.reduce((sum, n) => sum + n, 0) : 0;
  const rows = given ?? (result.kind === "weibull" && histogram
    ? histogram.counts_all.map((count, i) => ({ speed_class: `${histogram.edges[i]}–${histogram.edges[i + 1]}`, count, share_pct: total ? (100 * count) / total : null }))
    : records(result.rows ?? result.sectors ?? result.classes ?? result.groups));
  const columns = rows.length
    ? Object.keys(rows[0]).filter((k) => !rows.some((r) => typeof r[k] === "object" && r[k] !== null)).map((key) => ({
      key, header: key in tableMessages.en ? th(key as keyof typeof tableMessages.en) : key,
      render: (r: Row) => (typeof r[key] === "number" ? f.number(r[key] as number, Number.isInteger(r[key]) ? 0 : 3) : String(r[key] ?? "–")),
    }))
    : [];
  return rows.length ? <DataTable rows={rows} columns={columns} rowKey={(r) => JSON.stringify(r)} maxHeight={360} /> : null;
}
