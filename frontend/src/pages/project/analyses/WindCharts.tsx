import type { AnalysisResult } from "../../../api/analysis";
import { defineMessages, useFormat, useT } from "../../../i18n";
import { CHART_COLORS, cssColor } from "../results/TimeChart";
import { Curves, Rose } from "./Charts";

export type NumericRow = Record<string, unknown>;
export const records = (value: unknown): NumericRow[] => Array.isArray(value) ? value.filter((row) => row && typeof row === "object") as NumericRow[] : [];
// Calm to strong wind: the same sequential scale as the maps (viridis), readable in both themes
const COLORS = ["#46327e", "#365c8d", "#277f8e", "#1fa187", "#4ac16d", "#a0da39", "#fde725", "#ffb000", "#ff6b00", "#d7301f"];
const messages = defineMessages({
  en: { rose: "Wind rose", all: "All speeds", weibull: "Wind-speed distribution", observed: "Share of time per {w} m/s", fitted: "Weibull curve (A = {A} m/s, k = {k})", speed: "Wind speed", share: "Share of time" },
  fr: { rose: "Rose des vents", all: "Toutes vitesses", weibull: "Distribution de vitesse du vent", observed: "Part du temps par {w} m/s", fitted: "Courbe de Weibull (A = {A} m/s, k = {k})", speed: "Vitesse du vent", share: "Part du temps" },
});

/** Frequency of the directions the wind comes from, stacked by speed class. */
export function RoseChart({ result }: { result: AnalysisResult }) {
  const t = useT(messages); const f = useFormat();
  const frequency = result.frequency as number[][];
  const sectors = records(result.sectors), bins = records(result.speed_bins);
  const range = (bin: NumericRow | undefined) => (bin?.upper == null ? `≥ ${f.number(Number(bin?.lower), 0)}` : `${f.number(Number(bin?.lower), 0)}–${f.number(Number(bin?.upper), 0)}`);
  return (
    <Rose label={t("rose")} unit="%"
      keys={bins.map((bin, i) => ({ label: `${range(bin)} m/s`, color: COLORS[i % COLORS.length] }))}
      sectors={frequency.map((values, k) => ({ centre: Number(sectors[k]?.centre_deg ?? (k * 360) / frequency.length), parts: values.map((value, i) => ({ value, color: COLORS[i % COLORS.length] })) }))}
      tip={(sector) => [
        { label: t("all"), value: `${f.number(sector.parts.reduce((sum, p) => sum + p.value, 0), 1)} %` },
        ...sector.parts.flatMap((part, i) => (part.value > 0 ? [{ label: `${range(bins[i])} m/s`, value: `${f.number(part.value, 1)} %` }] : [])),
      ]} />
  );
}

/** The share of time in each wind speed class (calms of 0 m/s in the first one), and the
    Weibull curve fitted to the speeds above 0, scaled to the share of time they hold. */
export function WeibullChart({ result }: { result: AnalysisResult }) {
  const t = useT(messages); const f = useFormat();
  const curves = result.curves as Record<string, number[]>;
  const histogram = result.histogram as { edges: number[]; counts: number[]; counts_all: number[] };
  const every = histogram.counts_all.reduce((sum, n) => sum + n, 0);
  const positive = histogram.counts.reduce((sum, n) => sum + n, 0);
  const width = (histogram.edges[1] ?? 1) - (histogram.edges[0] ?? 0);
  const fit = ((result.all as NumericRow | undefined)?.fits as Record<string, NumericRow> | undefined)?.mle;
  const fitted = curves.mle;
  const scale = every > 0 ? (100 * width * positive) / every : 0;
  return (
    <Curves label={t("weibull")}
      x={{ label: t("speed"), unit: "m/s", digits: 1, from0: true }}
      y={{ label: t("share"), unit: "%", digits: 1, from0: true }}
      curves={[
        { key: "observed", label: t("observed", { w: f.number(width, width < 1 ? 1 : 0) }), color: cssColor(CHART_COLORS.reference), kind: "histogram", points: histogram.counts_all.map((count, i) => ({ x: histogram.edges[i], y: every ? (100 * count) / every : 0 })), widths: histogram.edges.slice(1) },
        ...(fitted ? [{ key: "weibull", label: t("fitted", { A: f.number(Number(fit?.A), 2), k: f.number(Number(fit?.k), 2) }), color: cssColor(CHART_COLORS.main), kind: "line" as const, points: curves.speed.map((speed, k) => ({ x: speed, y: scale * fitted[k] })).filter((p) => Number.isFinite(p.y)) }] : []),
      ]} />
  );
}
