/**
 * A line chart over time for the results page: a real time axis in UTC (ticks on round hours
 * or days), numbers in the language of the interface, gaps where values are missing.
 */
import { type ChartReferenceLineProps, LineChart } from "@mantine/charts";
import { Box, type MantineColor } from "@mantine/core";
import { useMemo } from "react";

import { defineMessages, parseUtc, useFormat, useLang, useT } from "../../../i18n";

/** The palette of every chart of the page, defined once (Mantine theme colours). */
export const CHART_COLORS = {
  main: "forest.6",
  reference: "gray.6",
  limit: "gray.5",
  marker: "ember.6",
  direction: "violet.6",
  measured: "blue.7",
  others: ["blue.6", "ember.6", "grape.6", "forest.3"],
} as const satisfies Record<string, MantineColor | readonly MantineColor[]>;

/** Colours of several groups on one chart (profiles per class, fits...), in this order. */
export const SERIES_COLORS: readonly MantineColor[] = [CHART_COLORS.main, ...CHART_COLORS.others, CHART_COLORS.direction];

/** A Mantine colour ("forest.6") as a CSS value, for charts drawn in SVG. */
export const cssColor = (color: MantineColor) => `var(--mantine-color-${color.replace(".", "-")})`;

const axisMessages = defineMessages({
  en: { north: "N", east: "E", south: "S", west: "W" },
  fr: { north: "N", east: "E", south: "S", west: "O" },
});

export interface ChartLine {
  name: string;
  label: string;
  color: MantineColor;
  /** Dashed: the reference (without farms, without wakes), so that colour is not the only signal */
  dashed?: boolean;
}

/** Any row with a UTC time; the other keys are read by series name */
type Row = { readonly time: string };

const HOUR = 3_600_000;
// Candidate spacings of the ticks, from ten minutes to a month
const TICK_STEPS = [HOUR / 6, HOUR / 4, HOUR / 2, HOUR, 2 * HOUR, 3 * HOUR, 6 * HOUR, 12 * HOUR, 24 * HOUR, 48 * HOUR, 96 * HOUR, 168 * HOUR, 336 * HOUR, 720 * HOUR];

/** Formatting of times on charts: short ticks, full labels in tooltips, both in UTC. */
export function useTimeAxis() {
  const { lang } = useLang();
  return useMemo(() => {
    const locale = lang === "fr" ? "fr-FR" : "en-GB";
    const day = new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", timeZone: "UTC" });
    const clock = new Intl.DateTimeFormat(locale, { hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: "UTC" });
    const full = new Intl.DateTimeFormat(locale, {
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
      timeZone: "UTC",
    });
    const fullSeconds = new Intl.DateTimeFormat(locale, {
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hourCycle: "h23",
      timeZone: "UTC",
    });
    return {
      /** Round times between min and max, at most about eight */
      ticks(min: number, max: number): number[] {
        if (!Number.isFinite(min) || !Number.isFinite(max) || max <= min) return [];
        const step = TICK_STEPS.find((s) => (max - min) / s <= 8) ?? TICK_STEPS[TICK_STEPS.length - 1];
        const ticks: number[] = [];
        for (let t = Math.ceil(min / step) * step; t <= max; t += step) ticks.push(t);
        return ticks;
      },
      /** Midnight shows the day, other ticks the hour */
      tick(ms: number, step: number): string {
        const date = new Date(ms);
        if (step >= 24 * HOUR || (date.getUTCHours() === 0 && date.getUTCMinutes() === 0)) return day.format(date);
        return clock.format(date);
      },
      label(ms: number): string {
        // A tooltip may be asked for a point that is not a time (a reference line): no label
        if (!Number.isFinite(ms)) return "";
        const date = new Date(ms);
        return `${(date.getUTCSeconds() ? fullSeconds : full).format(date)} UTC`;
      },
    };
  }, [lang]);
}

interface TimeChartProps {
  rows: readonly Row[];
  series: ChartLine[];
  /** Unit of the values, shown in tooltips and next to the axis */
  unit: string;
  /** What the chart shows, read by screen readers */
  title: string;
  digits?: number;
  height?: number;
  referenceLines?: ChartReferenceLineProps[];
  /** A vertical line at this time (the time shown on the map) */
  markTime?: string | null;
  markLabel?: string;
  /** Points without lines: for directions, which jump from 360° to 0° */
  dotsOnly?: boolean;
  /** Directions: 0 to 360° with N, E, S, W on the axis */
  compass?: boolean;
  yDomain?: [number | "auto" | "dataMin" | "dataMax", number | "auto" | "dataMin" | "dataMax"];
  yTicks?: number[];
}

export function TimeChart({
  rows,
  series,
  unit,
  title,
  digits = 1,
  height = 240,
  referenceLines = [],
  markTime,
  markLabel,
  dotsOnly = false,
  compass = false,
  yDomain,
  yTicks,
}: TimeChartProps) {
  const f = useFormat();
  const axis = useTimeAxis();
  const ta = useT(axisMessages);
  const points = ["north", "east", "south", "west", "north"] as const;

  const data = useMemo(
    () => rows.map((r): Record<string, unknown> & { t: number } => ({ ...r, t: parseUtc(r.time).getTime() })),
    [rows],
  );
  // Lines without any value (no run without turbines, no profile files) are left out
  const shown = useMemo(
    () => series.filter((s) => data.some((row) => typeof row[s.name] === "number" && Number.isFinite(row[s.name]))),
    [series, data],
  );
  const min = data.length ? data[0].t : NaN;
  const max = data.length ? data[data.length - 1].t : NaN;
  const ticks = useMemo(() => axis.ticks(min, max), [axis, min, max]);
  const step = ticks.length > 1 ? ticks[1] - ticks[0] : 24 * HOUR;

  const lines: ChartReferenceLineProps[] = [...referenceLines];
  if (markTime) {
    lines.push({ x: parseUtc(markTime).getTime(), color: CHART_COLORS.marker, label: markLabel, labelPosition: "insideTopRight" });
  }

  return (
    // The curves are revealed from left to right once, when the chart appears (never on updates)
    <Box role="figure" aria-label={title} className="ows-chart">
      <LineChart
        h={height}
        data={data}
        dataKey="t"
        series={shown.map((s) => ({ name: s.name, label: s.label, color: s.color, strokeDasharray: s.dashed ? "6 4" : undefined }))}
        withLegend={shown.length > 1}
        legendProps={{ verticalAlign: "top", height: 36 }}
        withDots={dotsOnly}
        dotProps={dotsOnly ? { r: 1.6, strokeWidth: 0 } : undefined}
        activeDotProps={{ r: 3.5 }}
        strokeWidth={dotsOnly ? 0 : 1.8}
        curveType="linear"
        connectNulls={false}
        gridAxis="xy"
        referenceLines={lines}
        valueFormatter={(v) => `${f.number(v, digits)} ${unit}`}
        lineProps={{ isAnimationActive: false }}
        xAxisProps={{
          type: "number",
          scale: "time",
          domain: [min, max],
          ticks,
          tickFormatter: (v: number) => axis.tick(v, step),
          minTickGap: 24,
        }}
        yAxisProps={{
          tickFormatter: (v: number) => (compass ? ta(points[Math.round(v / 90)] ?? "north") : f.number(v, Math.max(0, digits - 1))),
          width: 56,
          domain: compass ? [0, 360] : yDomain,
          ticks: compass ? [0, 90, 180, 270, 360] : yTicks,
        }}
        yAxisLabel={unit}
        xAxisLabel="UTC"
        tooltipProps={{ labelFormatter: (v: unknown) => axis.label(Number(v)) }}
        tooltipAnimationDuration={120}
      />
    </Box>
  );
}
