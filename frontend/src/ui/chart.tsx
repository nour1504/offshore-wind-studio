/**
 * What every chart shares, after the motion book: one palette, the values that morph from one set
 * to the next (nothing restarts from zero), the first appearance once the chart comes into view,
 * the reading written above the point or the bar (no floating box), and the colour keys.
 */
import { Group, Stack, Text, type MantineColor } from "@mantine/core";
import { Fragment, type RefCallback, useCallback, useEffect, useRef, useState } from "react";

import { prefersReducedMotion } from "../motion";

/** The palette of every chart, defined once (Mantine theme colours). */
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

/** A Mantine colour ("forest.6") as a CSS value, for charts drawn in SVG. The main series is
    drawn in the second green of the palette, as in the motion book. */
export const cssColor = (color: MantineColor) => (color === CHART_COLORS.main ? "var(--ows-accent-2)" : `var(--mantine-color-${color.replace(".", "-")})`);

/** Steps of the ramp of ordered classes (--ows-ramp-0 to 7 in styles.css): one hue, light to dark
    on white, dark to light on black. */
const RAMP_STEPS = 8;

/** The colour of class `index` of `count` ordered classes (calm to strong...): the ends of the
    ramp always used, the steps between spread evenly. */
export const rampColor = (index: number, count: number) =>
  `var(--ows-ramp-${count <= 1 ? RAMP_STEPS - 1 : Math.round((index * (RAMP_STEPS - 1)) / (count - 1))})`;

/** The curve of every morph of the charts: fast start, soft landing (ease-out cubic). */
const easeChart = (t: number) => 1 - Math.pow(1 - t, 3);

/** Durations of the charts (ms): a curve drawn, a curve or bars that morph, petals that grow. */
export const CHART_MS = { draw: 1400, line: 700, bars: 620, rose: 640, roseIn: 820 } as const;

/** True once the element has come into view: the charts draw themselves then, not before. */
export function useSeen<T extends Element>(): [RefCallback<T>, boolean] {
  const [seen, setSeen] = useState(false);
  const observer = useRef<IntersectionObserver | null>(null);
  const ref = useCallback((node: T | null) => {
    observer.current?.disconnect();
    observer.current = null;
    if (!node || seen) return;
    if (typeof IntersectionObserver === "undefined") return setSeen(true);
    observer.current = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        observer.current?.disconnect();
        setSeen(true);
      }
    });
    observer.current.observe(node);
  }, [seen]);
  useEffect(() => () => observer.current?.disconnect(), []);
  return [ref, seen];
}

type Value = number | null;

const same = (a: readonly Value[], b: readonly Value[]) => a.length === b.length && a.every((v, k) => Object.is(v, b[k]));

/**
 * Values shown while they morph to `target` (`duration` ms, `first` the first time). `grow`: bars and
 * petals grow from zero, new values too. Still before `ready`, with a duration of 0 or reduced
 * motion; a new `key` shows the values at once. Keep `target` stable (useMemo). `stagger`: each
 * `group` of values starts `stagger` ms after the one before.
 */
export function useMorph(
  target: readonly Value[],
  duration: number,
  { grow = false, ready = true, first, key = "", stagger = 0, group = 1 }: { grow?: boolean; ready?: boolean; first?: number; key?: string; stagger?: number; group?: number } = {},
): readonly Value[] {
  const [shown, setShown] = useState<readonly Value[]>(() => (grow ? target.map((v) => (v === null ? null : 0)) : target));
  const current = useRef(shown);
  const goal = useRef<{ values: readonly Value[]; key: string } | null>(null);
  useEffect(() => {
    if (!ready || (goal.current?.values === target && goal.current.key === key)) return;
    const previous = goal.current;
    goal.current = { values: target, key };
    if (previous && previous.key === key && same(previous.values, target)) return;
    const from = current.current;
    const ms = previous === null ? first ?? duration : duration;
    const moving = ms > 0 && !prefersReducedMotion() && (previous === null || previous.key === key) && (grow || (previous !== null && from.length === target.length));
    if (!moving) {
      current.current = target;
      setShown(target);
      return;
    }
    const began = performance.now();
    const delay = (i: number) => (previous === null ? Math.floor(i / group) * stagger : 0);
    const span = ms + delay(target.length - 1);
    let frame = 0;
    const step = (now: number) => {
      const elapsed = now - began;
      const next = target.map((v, i) => {
        const a = i < from.length ? from[i] : grow ? 0 : null;
        const k = easeChart(Math.min(1, Math.max(0, (elapsed - delay(i)) / ms)));
        return v === null || a === null || !Number.isFinite(a) ? v : a + (v - a) * k;
      });
      current.current = next;
      setShown(next);
      if (elapsed < span) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [target, duration, grow, ready, first, key, stagger, group]);
  return shown;
}

/** Room taken by a reading of 11 px bold, per character (Manrope). */
const CHAR = 6.3;

/** A piece of a reading: a value (or the time read), after a dot of its series' colour when
    several series are read. No labels: the dots match the keys of the chart. */
export interface ReadPart { text: string; dot?: string }

/** The reading as plain text (screen readers). */
export const readText = (parts: readonly ReadPart[]) => parts.map((part) => part.text).join(" ");

/**
 * The keys that read a chart as the pointer does: the arrows move by `jump`, Home and End go to
 * the ends, Escape stops reading (null); undefined for any other key.
 */
export function stepReading(key: string, from: number, count: number, jump = 1): number | null | undefined {
  return ({ ArrowRight: Math.min(count - 1, from + jump), ArrowLeft: Math.max(0, from - jump), Home: 0, End: count - 1, Escape: null } as Record<string, number | null>)[key];
}

/**
 * The reading of the point or the bar under the pointer, written above it in one short line: the
 * time or the position read, then the values. It stays inside [left, right].
 */
export function Readout({ x, y, parts, left, right, top = 11 }: { x: number; y: number; parts: readonly ReadPart[]; left: number; right: number; top?: number }) {
  const chars = parts.reduce((sum, part) => sum + part.text.length + (part.dot ? 2 : 0) + 1, -1);
  const half = Math.min((right - left) / 2, (chars * CHAR) / 2 + 2);
  const at = Math.max(left + half, Math.min(right - half, x));
  return (
    <text className="ows-readout" x={at} y={Math.max(top, y - 12)} textAnchor="middle">
      {parts.map((part, k) => (
        <Fragment key={k}>
          {k > 0 && " "}
          {part.dot && <tspan className="ows-readout-dot" fill={part.dot}>{"● "}</tspan>}
          {part.text}
        </Fragment>
      ))}
    </text>
  );
}

/** The same reading as a line of text under a chart (the rose). */
export function ReadingLine({ parts }: { parts: readonly ReadPart[] | null }) {
  return (
    <div className="ows-chart-reading" aria-live="polite">
      {parts?.map((part, k) => (
        <Fragment key={k}>
          {k > 0 && " "}
          {part.dot && <span className="ows-readout-dot" style={{ color: part.dot }} aria-hidden="true">{"● "}</span>}
          {part.text}
        </Fragment>
      ))}
    </div>
  );
}

export interface Key { label: string; color: string; pale?: boolean; dashed?: boolean }

/** The colour keys of a chart (only when there is more than one): in a row above it, or in a
    `column` beside it. */
export function Legend({ keys, column = false }: { keys: Key[]; column?: boolean }) {
  if (keys.length < 2) return null;
  const items = keys.map((key) => (
    <Group key={key.label} gap={6} wrap="nowrap">
      {key.dashed
        ? <svg width={18} height={10} aria-hidden><path d="M 0 5 H 18" stroke={key.color} strokeWidth={2} strokeDasharray="4 3" /></svg>
        : <span className="ows-legend-key" data-pale={key.pale || undefined} style={{ background: key.color }} />}
      <Text size="xs" fw={600}>{key.label}</Text>
    </Group>
  ));
  return column ? <Stack gap={8} className="ows-legend">{items}</Stack> : <Group justify="center" gap="md" mb={8} className="ows-legend">{items}</Group>;
}
