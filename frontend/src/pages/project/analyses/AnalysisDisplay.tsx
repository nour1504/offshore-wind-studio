import { Stack, Text } from "@mantine/core";
import { type AnalysisResult, records, type ResultRow } from "../../../api/analysis";
import { defineMessages, useFormat, useLang, useT } from "../../../i18n";
import { DataTable } from "../../../ui/DataTable";
import { prettyUnit } from "../explorer/quantities";
import { CHART_COLORS, cssColor, SERIES_COLORS } from "../../../ui/chart";
import { TimeChart } from "../results/TimeChart";
import { Bars, Curves } from "./Charts";
import { RoseChart, WeibullChart } from "./WindCharts";

const messages = defineMessages({
  en: {
    mean: "Mean", frequency: "Frequency", speed: "Wind speed", height: "Height", pairwise: "Between lowest and highest height",
    shear: "Shear exponent over time", veer: "Wind veer over time", average: "10-minute mean", month: "Month · UTC", hour: "Hour · UTC", all: "All",
  },
  fr: {
    mean: "Moyenne", frequency: "Fréquence", speed: "Vitesse du vent", height: "Hauteur", pairwise: "Entre les hauteurs minimale et maximale",
    shear: "Exposant de cisaillement au cours du temps", veer: "Rotation du vent au cours du temps", average: "Moyenne sur 10 min", month: "Mois · UTC", hour: "Heure · UTC", all: "Ensemble",
  },
});
const tableMessages = defineMessages({
  en: { count: "Values", mean: "Mean", std: "Standard deviation", min: "Minimum", max: "Maximum", frequency_pct: "Frequency (%)", centre_deg: "Direction (°)", mean_speed: "Mean speed (m/s)", energy_pct: "U³ share (%)", height_m: "Height (m)", share_pct: "Share of time (%)", sector: "Sector (°)", energy_mwh: "Energy (MWh)", energy_control_mwh: "Without turbines (MWh)", loss_pct: "Wake loss (%)", energy_share_pct: "Share of energy (%)", speed_class: "Speed (m/s)", centre_ms: "Bin (m/s)", speed_ms: "Mean speed (m/s)", power_mw: "Mean power (MW)", cp: "Cp", class: "Class", hour: "Hour (UTC)", month: "Month", time: "Time", times: "wrfout times" },
  fr: { count: "Valeurs", mean: "Moyenne", std: "Écart type", min: "Minimum", max: "Maximum", frequency_pct: "Fréquence (%)", centre_deg: "Direction (°)", mean_speed: "Vitesse moyenne (m/s)", energy_pct: "Part de U³ (%)", height_m: "Hauteur (m)", share_pct: "Part du temps (%)", sector: "Secteur (°)", energy_mwh: "Énergie (MWh)", energy_control_mwh: "Sans éoliennes (MWh)", loss_pct: "Pertes de sillage (%)", energy_share_pct: "Part de l'énergie (%)", speed_class: "Vitesse (m/s)", centre_ms: "Classe (m/s)", speed_ms: "Vitesse moyenne (m/s)", power_mw: "Puissance moyenne (MW)", cp: "Cp", class: "Classe", hour: "Heure (UTC)", month: "Mois", time: "Date", times: "Instants wrfout" },
});

// The columns of each table, in order (the server rows hold more: bounds, codes, percentiles)
const COLUMNS: Record<string, string[]> = {
  rose: ["centre_deg", "count", "frequency_pct", "mean_speed", "energy_pct"],
  weibull: ["speed_class", "count", "share_pct"],
  stability: ["label", "count", "frequency_pct"],
  grouped: ["label", "count", "mean", "std", "min", "max"],
  profile: ["height_m", "count", "mean", "std", "min", "max"],
  shear: ["count", "mean", "std", "min", "max"],
  veer: ["count", "mean", "std", "min", "max"],
  aggregate: ["time", "mean"],
  sectors: ["sector", "count", "energy_mwh", "energy_control_mwh", "loss_pct", "energy_share_pct"],
  curve: ["centre_ms", "count", "speed_ms", "power_mw", "cp"],
};
const DIGITS: Record<string, number> = { centre_deg: 0, sector: 0, height_m: 0, count: 0, frequency_pct: 1, share_pct: 1, energy_pct: 1, loss_pct: 1, energy_share_pct: 1, mean_speed: 2, speed_ms: 2, energy_mwh: 2, energy_control_mwh: 2, centre_ms: 1, power_mw: 3, cp: 3 };


/** The class name without its bounds: "Very unstable (-100 < L ≤ -50 m)" → "Very unstable". */
export const shortClass = (label: unknown) => String(label ?? "–").replace(/\s*\(.*\)\s*$/, "");

/** Every series of the result was read in the tslist outputs (10-minute means), none in the history files. */
export const fromTslist = (result: AnalysisResult) => result.inputs.length > 0 && result.inputs.every((input) => input.source === "tslist");

export function AnalysisDisplay({ result }: { result: AnalysisResult }) {
  const t = useT(messages);
  const { lang } = useLang();
  const unit = prettyUnit(String(result.unit ?? ""));
  let chart = null;
  if (result.kind === "rose") chart = <RoseChart result={result} />;
  else if (result.kind === "weibull") chart = <WeibullChart result={result} />;
  else if (result.kind === "aggregate" || result.kind === "shear" || result.kind === "veer") {
    const times = result.times as string[];
    // Shear between the lowest and the highest height only: the fit over two heights is the same curve
    const names = result.kind === "shear" ? ["alpha_pairwise"] : result.kind === "veer" ? ["veer_deg"] : ["mean"];
    const title = t(result.kind === "aggregate" ? "average" : result.kind);
    chart = (
      <TimeChart title={title} unit={result.kind === "veer" ? "°" : result.kind === "shear" ? "" : unit} digits={result.kind === "shear" ? 3 : result.kind === "veer" ? 1 : 2}
        rows={times.map((time, i) => ({ time, ...Object.fromEntries(names.map((k) => [k, (result[k] as (number | null)[])[i]])) }))}
        series={names.map((name, i) => ({ name, label: result.kind === "shear" ? t("pairwise") : title, color: i === 0 ? CHART_COLORS.main : CHART_COLORS.reference, dashed: i > 0 }))}
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

/** The rows of a result's table: one per sector, class, group, height or time. */
function tableRows(result: AnalysisResult): ResultRow[] {
  if (result.kind === "weibull") {
    const histogram = result.histogram as { edges: number[]; counts_all: number[] } | undefined;
    if (!histogram) return [];
    const total = histogram.counts_all.reduce((sum, n) => sum + n, 0);
    return histogram.counts_all.map((count, i) => ({ speed_class: `${histogram.edges[i]}–${histogram.edges[i + 1]}`, count, share_pct: total ? (100 * count) / total : null }));
  }
  if (result.kind === "aggregate") {
    const times = (result.times as string[] | undefined) ?? [];
    return times.map((time, i) => ({ time, mean: (result.mean as (number | null)[])[i] }));
  }
  if (result.kind === "shear") return records(result.groups).map((g) => (g.pairwise ?? {}) as ResultRow);
  if (result.kind === "grouped") return records(result.groups).filter((g) => Number(g.count) > 0);
  return records(result.rows ?? result.sectors ?? result.classes ?? result.groups);
}

/** The numbers behind the chart, as a sortable table. */
export function AnalysisTable({ result, rows: given }: { result: AnalysisResult; rows?: ResultRow[] }) {
  const th = useT(tableMessages);
  const f = useFormat();
  const rows = given ?? tableRows(result);
  const kind = String(result.kind);
  // Mean, deviation and extremes in the unit of the analysis
  const unit = kind === "veer" ? "°" : kind === "shear" ? "" : prettyUnit(String(result.unit ?? ""));
  const grouping = (result.grouping as { key?: string } | undefined)?.key;
  const stats = ["mean", "std", "min", "max"];
  const header = (key: string) => {
    if (key === "label") return th(kind === "stability" ? "class" : grouping === "month" ? "month" : "hour");
    // 1/L of the history files: one value per wrfout time; of the tslist outputs: one per 10 minutes
    if (key === "count" && kind === "stability" && !fromTslist(result)) return th("times");
    const base = th(key as keyof typeof tableMessages.en);
    return stats.includes(key) && unit ? `${base} (${unit})` : base;
  };
  // The centres of 16 sectors are not whole degrees (22.5°): one decimal then
  const halves = (key: string) => (key === "centre_deg" || key === "sector") && rows.some((r) => typeof r[key] === "number" && !Number.isInteger(r[key]));
  const digits = (key: string) => (halves(key) ? 1 : DIGITS[key] ?? (kind === "shear" ? 3 : kind === "veer" ? 1 : 2));
  const columns = (COLUMNS[kind] ?? []).filter((key) => rows.some((r) => key in r)).map((key) => ({
    key, header: header(key),
    render: (r: ResultRow) => (key === "time" ? f.dateTime(String(r.time)) : typeof r[key] === "number" ? f.number(r[key] as number, digits(key)) : String(r[key] ?? "–")),
  }));
  return rows.length && columns.length ? <DataTable rows={rows} columns={columns} rowKey={(r) => JSON.stringify(r)} maxHeight={360} /> : null;
}
