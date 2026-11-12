import { type AnalysisResult, records, type ResultRow } from "../../../api/analysis";
import { defineMessages, useFormat, useT } from "../../../i18n";
import { CHART_COLORS, cssColor, rampColor } from "../../../ui/chart";
import { Curves, Rose } from "./Charts";

const messages = defineMessages({
  en: { rose: "Wind rose", weibull: "Wind-speed distribution", observed: "Share of time per {w} m/s", fitted: "Weibull curve (A = {A} m/s, k = {k})", speed: "Wind speed", share: "Share of time" },
  fr: { rose: "Rose des vents", weibull: "Distribution de vitesse du vent", observed: "Part du temps par {w} m/s", fitted: "Courbe de Weibull (A = {A} m/s, k = {k})", speed: "Vitesse du vent", share: "Part du temps" },
});

/** Frequency of the directions the wind comes from, stacked by speed class (calm to strong, in
    the ramp of ordered classes). */
export function RoseChart({ result }: { result: AnalysisResult }) {
  const t = useT(messages); const f = useFormat();
  const frequency = result.frequency as number[][];
  const sectors = records(result.sectors), bins = records(result.speed_bins);
  const range = (bin: ResultRow | undefined) => (bin?.upper == null ? `≥ ${f.number(Number(bin?.lower), 0)}` : `${f.number(Number(bin?.lower), 0)}–${f.number(Number(bin?.upper), 0)}`);
  const color = (i: number) => rampColor(i, bins.length);
  return (
    <Rose label={t("rose")} unit="%"
      keys={bins.map((bin, i) => ({ label: `${range(bin)} m/s`, color: color(i) }))}
      scale={{ bounds: bins.map((bin) => Number(bin.lower)), unit: "m/s" }}
      sectors={frequency.map((values, k) => ({ centre: Number(sectors[k]?.centre_deg ?? (k * 360) / frequency.length), parts: values.map((value, i) => ({ value, color: color(i) })) }))}
      read={(sector) => [{ text: `${f.number(sector.parts.reduce((sum, p) => sum + p.value, 0), 1)} %` }]} />
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
  const fit = ((result.all as ResultRow | undefined)?.fits as Record<string, ResultRow> | undefined)?.mle;
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
