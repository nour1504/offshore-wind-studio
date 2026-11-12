/**
 * Line chart over time: UTC axis (round hours or days), numbers in the interface language, gaps
 * where values are missing; curves draw in when first seen, then morph. Under the pointer: a dashed
 * cursor, a dot per curve, the reading and a value ruler; arrow keys move it. Long series are drawn
 * in 2-px columns (extremes in order): a year of 10-minute values costs no more than a day.
 */
import { Box, type MantineColor } from "@mantine/core";
import { useElementSize } from "@mantine/hooks";
import { type KeyboardEvent, type PointerEvent, useId, useMemo, useState } from "react";

import { defineMessages, HOUR_MS, parseUtc, useFormat, useLang, useT } from "../../../i18n";
import { CHART_COLORS, CHART_MS, cssColor, Legend, type ReadPart, Readout, readText, stepReading, useMorph, useSeen } from "../../../ui/chart";
import { niceAxis } from "../../../ui/ticks";

const axisMessages = defineMessages({
  en: { north: "N", east: "E", south: "S", west: "W" },
  fr: { north: "N", east: "E", south: "S", west: "O" },
});

interface ChartLine {
  name: string;
  label: string;
  color: MantineColor;
  /** Dashed: the reference (without farms, without wakes), so that colour is not the only signal */
  dashed?: boolean;
}

/** A horizontal line at a value (the installed power), with its label */
interface ChartLevel {
  y: number;
  label?: string;
}

/** Any row with a UTC time; the other keys are read by series name */
type Row = { readonly time: string };

// Candidate spacings of the ticks, from ten minutes to a month
const TICK_STEPS = [HOUR_MS / 6, HOUR_MS / 4, HOUR_MS / 2, HOUR_MS, 2 * HOUR_MS, 3 * HOUR_MS, 6 * HOUR_MS, 12 * HOUR_MS, 24 * HOUR_MS, 48 * HOUR_MS, 96 * HOUR_MS, 168 * HOUR_MS, 336 * HOUR_MS, 720 * HOUR_MS];

/** Room above the curves (unit, reading), on the right, and below (dates, then the ruler) */
const TOP = 22;
const RIGHT = 8;
const BOTTOM = 60;
/** Width of a column of the drawn curves (px) and number of ticks of the ruler */
const COLUMN = 2;
const RULER = 96;

/** Formatting of times on charts: short ticks, the time read under the pointer, both in UTC. */
function useTimeAxis() {
  const { lang } = useLang();
  return useMemo(() => {
    const locale = lang === "fr" ? "fr-FR" : "en-GB";
    const day = new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", timeZone: "UTC" });
    const dayYear = new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
    const clock = new Intl.DateTimeFormat(locale, { hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: "UTC" });
    const clockSeconds = new Intl.DateTimeFormat(locale, { hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23", timeZone: "UTC" });
    return {
      /** Round times between min and max, at most `most` */
      ticks(min: number, max: number, most = 8): number[] {
        if (!Number.isFinite(min) || !Number.isFinite(max) || max <= min) return [];
        const step = TICK_STEPS.find((s) => (max - min) / s <= most) ?? TICK_STEPS[TICK_STEPS.length - 1];
        const ticks: number[] = [];
        for (let t = Math.ceil(min / step) * step; t <= max; t += step) ticks.push(t);
        return ticks;
      },
      /** Midnight shows the day, other ticks the hour */
      tick(ms: number, step: number): string {
        const date = new Date(ms);
        if (step >= 24 * HOUR_MS || (date.getUTCHours() === 0 && date.getUTCMinutes() === 0)) return day.format(date);
        return clock.format(date);
      },
      /** The time read: day, month and hour (UTC), with the year when the chart spans several */
      read(ms: number, withYear: boolean): string {
        const date = new Date(ms);
        return `${(withYear ? dayYear : day).format(date)} ${(date.getUTCSeconds() ? clockSeconds : clock).format(date)}`;
      },
    };
  }, [lang]);
}

const value = (row: Row | undefined, name: string): number | null => {
  const v = (row as Record<string, unknown> | undefined)?.[name];
  return typeof v === "number" && Number.isFinite(v) ? v : null;
};

/**
 * One curve reduced to the columns of the chart: for each column, its two extreme values in the
 * order they occur, the columns between two rows interpolated, null where values are missing.
 * `breaks` marks the columns not joined to the previous one (a missing value in between).
 */
function toColumns(xs: Float64Array, rows: readonly Row[], name: string, n: number) {
  const lo = new Float64Array(n).fill(NaN);
  const hi = new Float64Array(n).fill(NaN);
  const loAt = new Int32Array(n);
  const hiAt = new Int32Array(n);
  const breaks = new Uint8Array(n);
  const between: number[] = [];
  let lastC = -1;
  let lastX = 0;
  let lastV = 0;
  let missing = false;
  for (let i = 0; i < rows.length; i++) {
    const v = value(rows[i], name);
    if (v === null) {
      missing = lastC >= 0;
      continue;
    }
    const c = Math.min(n - 1, Math.max(0, Math.floor(xs[i] / COLUMN)));
    if (Number.isNaN(lo[c])) {
      lo[c] = hi[c] = v;
      loAt[c] = hiAt[c] = i;
      if (lastC >= 0 && c > lastC) {
        if (missing) breaks[c] = 1;
        else for (let k = lastC + 1; k < c; k++) between.push(k, lastV + ((v - lastV) * ((k + 0.5) * COLUMN - lastX)) / (xs[i] - lastX || 1));
      }
    } else {
      if (v < lo[c]) { lo[c] = v; loAt[c] = i; }
      if (v > hi[c]) { hi[c] = v; hiAt[c] = i; }
    }
    lastC = c;
    lastX = xs[i];
    lastV = v;
    missing = false;
  }
  const values = new Array<number | null>(2 * n).fill(null);
  for (let c = 0; c < n; c++) {
    if (Number.isNaN(lo[c])) continue;
    const lowFirst = loAt[c] <= hiAt[c];
    values[2 * c] = lowFirst ? lo[c] : hi[c];
    values[2 * c + 1] = lowFirst ? hi[c] : lo[c];
  }
  for (let k = 0; k < between.length; k += 2) values[2 * between[k]] = values[2 * between[k] + 1] = between[k + 1];
  return { values, breaks };
}

/**
 * The line through the columns, and the area under it down to the axis, piece by piece. A value
 * alone between two gaps has no line to be drawn on: it is a dot.
 */
function curvePaths(values: readonly (number | null)[], from: number, n: number, breaks: Uint8Array, x: (c: number) => number, y: (v: number) => number, base: number) {
  let line = "";
  let area = "";
  let dots = "";
  // The first point of the piece being drawn, while it is the only one
  let alone = "";
  let pen = false;
  let lastX = "";
  for (let c = 0; c < n; c++) {
    const a = values[from + 2 * c];
    const b = values[from + 2 * c + 1];
    if (a === null || a === undefined || b === null || b === undefined) {
      if (pen) area += `L${lastX},${base}Z`;
      dots += alone;
      alone = "";
      pen = false;
      continue;
    }
    const X = x(c).toFixed(1);
    const ya = y(a).toFixed(1);
    const yb = y(b).toFixed(1);
    if (pen && breaks[c]) area += `L${lastX},${base}Z`;
    const join = pen && !breaks[c];
    dots += join ? "" : alone;
    alone = join || yb !== ya ? "" : `M${X},${ya}h0`;
    line += `${join ? "L" : "M"}${X},${ya}`;
    area += join ? `L${X},${ya}` : `M${X},${base}L${X},${ya}`;
    if (yb !== ya) {
      line += `L${X},${yb}`;
      area += `L${X},${yb}`;
    }
    pen = true;
    lastX = X;
  }
  if (pen) area += `L${lastX},${base}Z`;
  return { line, area, dots: dots + alone };
}

/** Points without lines (directions): one round dot per row, one per pixel at most. */
function dotsPath(xs: Float64Array, rows: readonly Row[], name: string, x0: number, y: (v: number) => number) {
  const taken = new Set<number>();
  let d = "";
  for (let i = 0; i < rows.length; i++) {
    const v = value(rows[i], name);
    if (v === null) continue;
    const X = Math.round(x0 + xs[i]);
    const Y = Math.round(y(v));
    const key = X * 16384 + Y;
    if (taken.has(key)) continue;
    taken.add(key);
    d += `M${X},${Y}h0`;
  }
  return d;
}

/** The row nearest to a time (rows in time order). */
function nearest(times: Float64Array, t: number): number {
  let lo = 0;
  let hi = times.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (times[mid] < t) lo = mid + 1;
    else hi = mid;
  }
  return lo > 0 && t - times[lo - 1] < times[lo] - t ? lo - 1 : lo;
}

const EMPTY: readonly (number | null)[] = [];

interface TimeChartProps {
  rows: readonly Row[];
  series: ChartLine[];
  /** Unit of the values, above the axis and in the reading */
  unit: string;
  /** What the chart shows, read by screen readers */
  title: string;
  digits?: number;
  /** Height of the drawing (px), dates and ruler included */
  height?: number;
  /** Horizontal lines at given values (the installed power) */
  referenceLines?: ChartLevel[];
  /** A vertical line at this time (the time shown on the map) */
  markTime?: string | null;
  markLabel?: string;
  /** Points without lines: for directions, which jump from 360° to 0° */
  dotsOnly?: boolean;
  /** Directions: 0 to 360° with N, E, S, W on the axis */
  compass?: boolean;
  /** Bounds of the value axis; "auto" (default) from the values, from zero when they are all positive and spread */
  yDomain?: [number | "auto", number | "auto"];
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
}: TimeChartProps) {
  const f = useFormat();
  const axis = useTimeAxis();
  const ta = useT(axisMessages);
  const ids = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const { ref: sizeRef, width } = useElementSize();
  const [seenRef, seen] = useSeen<HTMLDivElement>();
  const [at, setAt] = useState<number | null>(null);

  const times = useMemo(() => Float64Array.from(rows, (r) => parseUtc(r.time).getTime()), [rows]);
  // Lines without any value (no run without turbines, no profile files) are left out
  const shown = useMemo(() => series.filter((s) => rows.some((row) => value(row, s.name) !== null)), [series, rows]);
  const names = shown.map((s) => s.name).join("|");
  const start = rows.length ? times[0] : 0;
  const end = rows.length ? times[times.length - 1] : 0;
  const span = end > start ? end - start : HOUR_MS;
  const withYear = new Date(start).getUTCFullYear() !== new Date(end).getUTCFullYear();

  // Values only added at the end (a run in progress): no morph
  const [track, setTrack] = useState({ rows, start, end, appended: false });
  if (track.rows !== rows) setTrack({ rows, start, end, appended: track.start === start && end > track.end });

  // Value axis: compass, given bounds, or round bounds around the values (and the levels)
  const plotH = height - TOP - BOTTOM;
  const domain = useMemo(() => {
    if (compass) return { lo: 0, hi: 360, ticks: [0, 90, 180, 270, 360], digits: 0 };
    let min = Infinity;
    let max = -Infinity;
    for (const row of rows) {
      for (const s of shown) {
        const v = value(row, s.name);
        if (v === null) continue;
        if (v < min) min = v;
        if (v > max) max = v;
      }
    }
    for (const level of referenceLines) {
      min = Math.min(min, level.y);
      max = Math.max(max, level.y);
    }
    if (!Number.isFinite(min)) {
      min = 0;
      max = 1;
    }
    const lo = typeof yDomain?.[0] === "number" ? yDomain[0] : min >= 0 && min < 0.5 * max ? 0 : min;
    const hi = typeof yDomain?.[1] === "number" ? yDomain[1] : max;
    return niceAxis(lo, hi, Math.max(2, Math.floor(plotH / 34)));
  }, [compass, rows, shown, referenceLines, yDomain, plotH]);
  const compassLabels = ["north", "east", "south", "west", "north"] as const;
  const yLabel = (v: number) => (compass ? ta(compassLabels[Math.round(v / 90)] ?? "north") : f.number(v, domain.digits));

  // Geometry in pixels: the labels of the value axis decide the left margin
  const x0 = Math.max(34, 10 + 6 * Math.max(...domain.ticks.map((v) => yLabel(v).length)));
  const x1 = width - RIGHT;
  const plotW = x1 - x0;
  const y0 = height - BOTTOM;
  const y = (v: number) => y0 - ((v - domain.lo) / (domain.hi - domain.lo || 1)) * plotH;
  const xOf = (t: number) => x0 + ((t - start) / span) * plotW;

  const curves = useMemo(() => {
    if (plotW <= 0 || !rows.length) return null;
    const n = Math.max(1, Math.ceil(plotW / COLUMN));
    const xs = times.map((t) => ((t - start) / span) * plotW);
    const parts = shown.map((s) => toColumns(xs, rows, s.name, n));
    return { n, xs, values: parts.flatMap((p) => p.values), breaks: parts.map((p) => p.breaks) };
  }, [rows, times, shown, start, span, plotW]);
  const morphed = useMorph(curves?.values ?? EMPTY, dotsOnly || track.appended ? 0 : CHART_MS.line, { ready: seen, key: names });
  const values = curves && morphed.length === curves.values.length ? morphed : curves?.values ?? EMPTY;

  const paths = useMemo(() => {
    if (!curves) return [];
    const x = (c: number) => x0 + (c + 0.5) * COLUMN;
    return shown.map((s, k) =>
      dotsOnly
        ? { line: dotsPath(curves.xs, rows, s.name, x0, y), area: "", dots: "" }
        : curvePaths(values, k * 2 * curves.n, curves.n, curves.breaks[k], x, y, y0),
    );
    // y follows from y0 and the domain
  }, [curves, values, shown, dotsOnly, rows, x0, y0, domain]);

  // The ruler: one tick per 96th of the chart, as tall as the first curve there
  const ruler = useMemo(() => {
    if (!curves || plotW <= 0) return [];
    return Array.from({ length: RULER }, (_, i) => {
      let sum = 0;
      let count = 0;
      for (let c = Math.floor((i * curves.n) / RULER); c < Math.floor(((i + 1) * curves.n) / RULER); c++) {
        for (const v of [values[2 * c], values[2 * c + 1]]) {
          if (v === null || v === undefined) continue;
          sum += v;
          count += 1;
        }
      }
      const h = count ? 4 + (12 * (sum / count - domain.lo)) / (domain.hi - domain.lo || 1) : 0;
      return { x: x0 + ((i + 0.5) * plotW) / RULER, h };
    });
  }, [curves, values, plotW, x0, domain]);

  const xTicks = useMemo(() => (plotW > 0 ? axis.ticks(start, end, Math.max(2, Math.floor(plotW / 90))) : []), [axis, start, end, plotW]);
  const step = xTicks.length > 1 ? xTicks[1] - xTicks[0] : 24 * HOUR_MS;

  // A value read; the unit after the last one only
  const valueText = (v: number | null, last: boolean) => {
    if (compass) return `${f.number(v, 0)}°`;
    const n = f.number(v, digits);
    return !last || !unit ? n : unit === "°" ? `${n}°` : `${n} ${unit}`;
  };

  // The reading under the pointer (or the keyboard)
  const read = useMemo(() => {
    if (at === null || !curves || at >= rows.length) return null;
    const X = x0 + curves.xs[at];
    const read = shown.map((s) => value(rows[at], s.name));
    const parts: ReadPart[] = [
      { text: `${axis.read(times[at], withYear)} ·` },
      ...shown.map((s, k) => ({ text: valueText(read[k], k === shown.length - 1), dot: shown.length > 1 ? cssColor(s.color) : undefined })),
    ];
    const first = read.find((v) => v !== null);
    return { X, read, parts, Y: first === undefined || first === null ? TOP : y(first) };
    // valueText and y follow from the format, the unit and the domain
  }, [at, curves, rows, shown, times, withYear, axis, x0, domain, f, unit, digits, compass]);

  const mark = markTime ? parseUtc(markTime).getTime() : NaN;
  const markX = mark >= start && mark <= end ? xOf(mark) : null;

  const onMove = (event: PointerEvent<SVGSVGElement>) => {
    if (!curves) return;
    const px = Math.max(0, Math.min(plotW, event.clientX - event.currentTarget.getBoundingClientRect().left - x0));
    setAt(nearest(times, start + (px / plotW) * span));
  };
  const onKey = (event: KeyboardEvent<SVGSVGElement>) => {
    if (!rows.length) return;
    const jump = Math.max(1, Math.round(rows.length / RULER));
    const from = at ?? 0;
    const next = stepReading(event.key, from, rows.length, jump);
    if (next === undefined) return;
    event.preventDefault();
    setAt(next);
  };

  const drawn = width > 0 && plotW > 0;
  return (
    <Box ref={seenRef} role="figure" aria-label={title} className="ows-chart" data-unseen={!seen || undefined}>
      {/* Dots only: every series is drawn as dots, a dashed key would show a line that is not there */}
      <Legend keys={shown.map((s) => ({ label: s.label, color: cssColor(s.color), dashed: !dotsOnly && s.dashed }))} />
      <div ref={sizeRef}>
        <svg
          width={Math.max(width, 1)}
          height={height}
          tabIndex={0}
          aria-label={read ? readText(read.parts) : title}
          onPointerMove={onMove}
          onPointerLeave={() => setAt(null)}
          onKeyDown={onKey}
          onBlur={() => setAt(null)}
        >
          {drawn && (
            <>
              <g className="ows-axis">
                {domain.ticks.map((v) => (
                  <g key={v}>
                    <line x1={x0} x2={x1} y1={y(v)} y2={y(v)} />
                    <text x={x0 - 6} y={y(v) + 3} textAnchor="end">{yLabel(v)}</text>
                  </g>
                ))}
                {unit && !compass && <text x={x0 - 6} y={TOP - 10} textAnchor="end">{unit}</text>}
                {xTicks.map((t) => {
                  const X = xOf(t);
                  return <text key={t} x={X} y={y0 + 14} textAnchor={X < x0 + 30 ? "start" : X > x1 - 30 ? "end" : "middle"}>{axis.tick(t, step)}</text>;
                })}
              </g>
              {referenceLines.map((level) => (
                <g key={level.y} className="ows-chart-level">
                  <line x1={x0} x2={x1} y1={y(level.y)} y2={y(level.y)} stroke={cssColor(CHART_COLORS.limit)} strokeDasharray="4 4" />
                  {level.label && <text className="ows-axis-text" x={x0 + 4} y={y(level.y) - 5}>{level.label}</text>}
                </g>
              ))}
              {markX !== null && (
                <g className="ows-chart-mark" style={{ color: cssColor(CHART_COLORS.marker) }}>
                  <line x1={markX} x2={markX} y1={TOP} y2={y0} stroke="currentColor" />
                  {markLabel && <text x={markX > x1 - 90 ? markX - 4 : markX + 4} y={TOP + 9} textAnchor={markX > x1 - 90 ? "end" : "start"} fill="currentColor">{markLabel}</text>}
                </g>
              )}
              {read && !dotsOnly && read.read[0] !== null && paths[0] && (
                <>
                  <clipPath id={`${ids}-area`}><rect x={x0} y={0} width={Math.max(0, read.X - x0)} height={height} /></clipPath>
                  <path className="ows-ts-area" d={paths[0].area} clipPath={`url(#${ids}-area)`} />
                </>
              )}
              <g key={names} className="ows-ts-curves">
                <clipPath id={`${ids}-reveal`}><rect className={seen ? "ows-ts-reveal" : undefined} x={x0 - 4} y={0} width={plotW + 8} height={height} /></clipPath>
                {shown.map((s, k) =>
                  dotsOnly ? (
                    <path key={s.name} className="ows-ts-dots" data-other={k > 0 || undefined} d={paths[k]?.line} stroke={cssColor(s.color)} clipPath={`url(#${ids}-reveal)`} />
                  ) : s.dashed ? (
                    <path key={s.name} className="ows-ts-line" d={paths[k]?.line} stroke={cssColor(s.color)} strokeDasharray="6 4" clipPath={`url(#${ids}-reveal)`} />
                  ) : (
                    <path key={s.name} className={seen ? "ows-ts-line ows-ts-draw" : "ows-ts-line"} pathLength={1} d={paths[k]?.line} stroke={cssColor(s.color)} />
                  ),
                )}
                {shown.map((s, k) => paths[k]?.dots && <path key={`${s.name}-alone`} className="ows-ts-dots" d={paths[k].dots} stroke={cssColor(s.color)} clipPath={`url(#${ids}-reveal)`} />)}
              </g>
              {read && (
                <g pointerEvents="none">
                  <line className="ows-ts-cursor" x1={read.X} x2={read.X} y1={TOP} y2={y0} />
                  {shown.map((s, k) => read.read[k] !== null && (
                    <circle key={s.name} className="ows-ts-dot" cx={read.X} cy={y(read.read[k]!)} r={k === 0 ? 4.5 : 3.5} fill={cssColor(s.color)} />
                  ))}
                  <Readout x={read.X} y={read.Y} parts={read.parts} left={x0} right={x1} />
                </g>
              )}
              <g aria-hidden>
                {ruler.map((tick, i) => {
                  const near = read ? Math.max(0, 1 - Math.abs(tick.x - read.X) / 46) : 0;
                  return tick.h > 0 && (
                    <line key={i} className="ows-mm-tick" data-hot={near > 0.92 || undefined} x1={tick.x} x2={tick.x} y1={height - 14} y2={height - 14 - tick.h * (1 + near * 1.4)} />
                  );
                })}
              </g>
            </>
          )}
        </svg>
      </div>
    </Box>
  );
}
