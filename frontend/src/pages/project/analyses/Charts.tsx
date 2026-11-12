/**
 * Charts of the wind analyses: a rose by direction, bars by group, curves along an axis. Petals and
 * bars grow from zero when first seen and morph to new values; curves draw in, then morph. The
 * element under the pointer stands out with its reading.
 */
import { Box } from "@mantine/core";
import { useElementSize, useMergedRef } from "@mantine/hooks";
import { type CSSProperties, type KeyboardEvent, type PointerEvent, type ReactNode, useId, useMemo, useState } from "react";

import { defineMessages, useFormat, useT } from "../../../i18n";
import { CHART_COLORS, CHART_MS, cssColor, type Key, Legend, type ReadPart, Readout, ReadingLine, readText, stepReading, useMorph, useSeen } from "../../../ui/chart";
import { decimals, niceAxis, niceStep } from "../../../ui/ticks";

const PALE = cssColor(CHART_COLORS.reference);

const messages = defineMessages({
  en: { north: "N", east: "E", south: "S", west: "W" },
  fr: { north: "N", east: "E", south: "S", west: "O" },
});

/** Room taken by a label of 10 px, per character */
const CHAR = 6;

// ---------------------------------------------------------------------------------------------
// Rose

interface RoseSector {
  centre: number;
  /** Stacked from the hub outwards */
  parts: { value: number; color: string }[];
  /** Drawn pale behind the petal */
  reference?: number | null;
}

/** The square the rose is drawn in and the radius of its outer ring (px): the values run from the
    hub to it; the ring of ticks and the cardinal points are beyond */
const SIZE = 400, C = SIZE / 2, R = 146;
const RAD = Math.PI / 180;
const polar = (degrees: number, r: number): [number, number] => [C + r * Math.sin(degrees * RAD), C - r * Math.cos(degrees * RAD)];
const spot = (degrees: number, r: number) => polar(degrees, r).map((v) => v.toFixed(2)).join(",");
/** Room (px) between two petals, the same from the hub to the rim, and between the stacked parts of a petal */
const PETAL_GAP = 2, PART_GAP = 1;
/** Rounding (px) of the two outer corners of a petal */
const CORNER = 3;
/** The petals grow one sector after the other, clockwise from north, within this time (ms) */
const SWEEP_MS = 520;
/** The ring of ticks around the rose, every 5 degrees (longer every 45): where they start, and the
    angle (degrees) around the direction read within which they swell */
const TICKS = Array.from({ length: 72 }, (_, k) => k * 5);
const TICK_FROM = R + 7, TICK_REACH = 22;
/** From this width (px) the keys stand beside the rose; under it, above */
const ROSE_WIDE = 520;

/**
 * A petal of the sector centred on `angle` (degrees, `half` on each side), from radius r1 to r2.
 * Its sides stay parallel to the edges of the sector, `gap` / 2 inside them: the room between two
 * petals is the same from the hub to the rim. With `corner`, its two outer corners are rounded.
 */
function petal(angle: number, half: number, r1: number, r2: number, gap: number, corner = 0): string {
  const taken = (r: number) => Math.asin(Math.min(1, gap / 2 / r)) / RAD;
  const a1 = half - taken(r1), a2 = half - taken(r2);
  if (r2 <= r1 || a1 <= 0 || a2 <= 0) return "";
  const inner = `L${spot(angle + a1, r1)}A${r1},${r1} 0 0 0 ${spot(angle - a1, r1)}Z`;
  const rho = Math.min(corner, r2 - r1, a2 * RAD * r2 - 0.2);
  if (rho < 0.4) return `M${spot(angle - a1, r1)}L${spot(angle - a2, r2)}A${r2},${r2} 0 0 1 ${spot(angle + a2, r2)}${inner}`;
  // Each corner: the side left `rho` before its end, the arc joined `rho` further, a curve between
  const turn = rho / r2 / RAD;
  const along = (degrees: number, [x, y]: [number, number]) => `${(x - rho * Math.sin(degrees * RAD)).toFixed(2)},${(y + rho * Math.cos(degrees * RAD)).toFixed(2)}`;
  const left = polar(angle - a2, r2), right = polar(angle + a2, r2);
  return `M${spot(angle - a1, r1)}L${along(angle - half, left)}Q${left.map((v) => v.toFixed(2)).join(",")} ${spot(angle - a2 + turn, r2)}`
    + `A${r2},${r2} 0 0 1 ${spot(angle + a2 - turn, r2)}Q${right.map((v) => v.toFixed(2)).join(",")} ${along(angle + half, right)}${inner}`;
}

/** What lets a chart be read with the keys as with the pointer (stepReading), its reading said aloud. */
function readingProps(count: number, lit: number | null, setLit: (k: number | null) => void, parts: readonly ReadPart[], label: string) {
  return {
    tabIndex: 0,
    "aria-label": parts.length ? readText(parts) : label,
    onKeyDown: (event: KeyboardEvent<SVGSVGElement>) => {
      if (!count) return;
      const next = stepReading(event.key, lit ?? -1, count);
      if (next === undefined) return;
      event.preventDefault();
      setLit(next);
    },
    onBlur: () => setLit(null),
  };
}

/**
 * The scale of ordered classes, calm to strong: a block per class in its colour, the bounds at
 * the joints and the unit at the open end. `upright`: beside the chart, strong at the top;
 * otherwise lying above it. The class pointed stands out (in the chart too).
 */
function ClassScale({ keys, bounds, unit, picked, onPick, upright }: { keys: Key[]; bounds: number[]; unit: string; picked: number | null; onPick: (k: number | null) => void; upright: boolean }) {
  const f = useFormat();
  return (
    <div className="ows-scale" data-upright={upright || undefined} style={{ "--n": keys.length } as CSSProperties} onPointerLeave={() => onPick(null)}>
      <div className="ows-scale-bar" role="img" aria-label={keys.map((key) => key.label).join(", ")} data-picking={picked !== null || undefined}>
        {keys.map((key, k) => (
          <span key={key.label} className="ows-scale-block" data-on={picked === k || undefined} style={{ background: key.color, "--i": k } as CSSProperties} onPointerEnter={() => onPick(k)} />
        ))}
      </div>
      <div className="ows-scale-ticks" aria-hidden="true">
        {[...bounds.slice(0, keys.length).map((bound) => f.number(bound, 0)), unit].map((text, k) => <span key={k} style={{ "--k": k } as CSSProperties}>{text}</span>)}
      </div>
    </div>
  );
}

/**
 * One petal per direction sector (wind from, clockwise from north), parts stacked outwards over the
 * pale reference, ring values inside their ring. The sector under the pointer, anywhere on the rose
 * or its ticks, stands out and is read below; with a `scale` (ordered parts) a class pointed stands
 * out in every petal. Arrow keys step through the sectors.
 */
export function Rose({ sectors, unit, keys, label, read, scale }: {
  sectors: RoseSector[]; unit: string; keys: Key[]; label: string;
  /** The values read on the petal under the pointer (the direction comes first) */
  read: (sector: RoseSector) => ReadPart[];
  /** Ordered parts: the lower bound of each class, and their unit */
  scale?: { bounds: number[]; unit: string };
}) {
  const t = useT(messages);
  const f = useFormat();
  const clip = useId();
  const { ref: sizeRef, width } = useElementSize();
  const [seenRef, seen] = useSeen<HTMLDivElement>();
  const ref = useMergedRef(seenRef, sizeRef);
  // The sector read, the part pointed in its petal, the class pointed in the scale, and the
  // direction of the pointer itself (degrees), which the ticks follow
  const [lit, setLit] = useState<number | null>(null);
  const [part, setPart] = useState<number | null>(null);
  const [picked, setPicked] = useState<number | null>(null);
  const [bearing, setBearing] = useState<number | null>(null);
  const count = sectors.length;
  const half = 180 / Math.max(1, count);
  // Many thin petals start farther from the centre, where they have some width
  const hub = count > 16 ? 30 : 22;
  const reach = R - hub;
  const total = (s: RoseSector) => s.parts.reduce((sum, p) => sum + Math.max(0, p.value), 0);
  const top = Math.max(1e-9, ...sectors.flatMap((s) => [total(s), s.reference ?? 0]));
  const step = niceStep(top, 4);
  const outer = Math.ceil(top / step) * step;
  const rings = Array.from({ length: Math.round(outer / step) }, (_, k) => (k + 1) * step);
  const ringDigits = decimals(step);
  const quiet = sectors.reduce<RoseSector | null>((best, s) => (best === null || total(s) < total(best) ? s : best), null)?.centre ?? 0;
  // Lengths from the hub (px): per sector the reference, then the stacked parts; they grow sector
  // after sector, then morph
  const perSector = 1 + (sectors[0]?.parts.length ?? 0);
  const target = useMemo(() => sectors.flatMap((s) => {
    let base = 0;
    return [(reach * Math.max(0, s.reference ?? 0)) / outer, ...s.parts.map((p) => (reach * (base += Math.max(0, p.value))) / outer)];
  }), [sectors, outer, reach]);
  const morphed = useMorph(target, CHART_MS.rose, { grow: true, ready: seen, first: CHART_MS.roseIn, stagger: SWEEP_MS / Math.max(1, count), group: perSector });
  const lengths = morphed.length === target.length ? morphed : target;
  /** Length of the reference (j = 0) or of the parts up to the j-th (j > 0) of sector k */
  const length = (k: number, j: number) => Math.max(0, lengths[k * perSector + j] ?? 0);
  const shown = lit === null ? null : sectors[lit] ?? null;

  const leave = () => { setLit(null); setPart(null); setBearing(null); };
  // The direction under the pointer, anywhere on the rose or on its ring of ticks, and the part
  // of its petal the pointer is on
  const point = (event: PointerEvent<SVGSVGElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const x = ((event.clientX - box.left) / box.width) * SIZE - C, y = ((event.clientY - box.top) / box.height) * SIZE - C;
    const r = Math.hypot(x, y);
    if (!count || r < hub - 6 || r > R + 46) return leave();
    const angle = (Math.atan2(x, -y) / RAD + 360) % 360;
    const k = Math.round(((((angle - sectors[0].centre) % 360) + 360) % 360) / (2 * half)) % count;
    let found: number | null = null;
    for (let j = 0, from = 0; j < sectors[k].parts.length && found === null; j++) {
      const to = length(k, j + 1);
      if (to > from && r - hub >= from && r - hub <= to) found = j;
      from = to;
    }
    setLit(k);
    setPart(found);
    setBearing(Math.round(angle));
  };
  // The ticks swell around the pointer; read with the keys, around the sector read
  const eye = bearing ?? shown?.centre ?? null;
  const near = (angle: number) => {
    if (eye === null) return 0;
    const away = Math.abs(((angle - eye + 540) % 360) - 180);
    return away >= TICK_REACH ? 0 : 0.5 + 0.5 * Math.cos((Math.PI * away) / TICK_REACH);
  };
  // A part read: its value first, then its class, after a dot of its colour
  const partRead = (value: number, k: number): ReadPart => ({ text: `${f.number(value, 1)} ${unit} · ${keys[k]?.label ?? ""}`, dot: keys[k]?.color });
  const pointed = shown && part !== null ? shown.parts[part] : undefined;
  const parts: ReadPart[] = shown
    ? [{ text: `${f.number(shown.centre, Number.isInteger(shown.centre) ? 0 : 1)}° ·` }, ...read(shown), ...(scale && pointed && part !== null ? [partRead(pointed.value, part)] : [])]
    : picked !== null ? [partRead(sectors.reduce((sum, s) => sum + Math.max(0, s.parts[picked]?.value ?? 0), 0), picked)] : [];
  const reading = readingProps(count, lit, (k) => { setLit(k); setPart(null); setBearing(null); }, parts, label);
  const wide = width === 0 || width >= ROSE_WIDE;
  const side = scale ? <ClassScale keys={keys} bounds={scale.bounds} unit={scale.unit} picked={picked} onPick={setPicked} upright={wide} /> : keys.length > 1 ? <Legend keys={keys} column={wide} /> : null;
  // Drawn again only when the petals change, not at each move of the pointer around them
  const petals = useMemo(() => sectors.map((sector, k) => {
    const end = length(k, sector.parts.length), pale = length(k, 0);
    return (
      <g key={sector.centre} data-lit={lit === k || undefined} data-parting={(lit === k && part !== null) || undefined}>
        {typeof sector.reference === "number" && pale > 0.5 && <path className="ows-petal-pale" d={petal(sector.centre, half, hub, hub + pale, PETAL_GAP, CORNER)} />}
        {end > 0.5 && (
          <>
            <clipPath id={`${clip}${k}`}><path d={petal(sector.centre, half, hub, hub + end, PETAL_GAP, CORNER)} /></clipPath>
            <g clipPath={`url(#${clip}${k})`}>
              {sector.parts.map((p, j) => {
                // A thin line of the surface before each part but the first, when it has the room
                const from = j > 0 ? length(k, j) : 0, to = length(k, j + 1);
                if (to - from < 0.05) return null;
                const gap = j > 0 && to - from > PART_GAP + 1 ? PART_GAP : 0;
                return <path key={j} className="ows-petal" data-on={picked === j || undefined} data-at={(lit === k && part === j) || undefined} d={petal(sector.centre, half, hub + from + gap, hub + to, PETAL_GAP)} style={{ "--petal": p.color } as CSSProperties} />;
              })}
            </g>
          </>
        )}
      </g>
    );
  }), [sectors, lengths, lit, part, picked, half, hub, clip]);
  return (
    <Box ref={ref} role="figure" aria-label={label} className="ows-chart ows-rose-chart" data-unseen={!seen || undefined} data-wide={wide || undefined} data-side={side ? true : undefined}>
      {side && <div className="ows-rose-side">{side}</div>}
      <svg viewBox={`0 0 ${SIZE} ${SIZE}`} className="ows-rose" data-picking={picked !== null || undefined}
        onPointerMove={point} onPointerDown={point} onPointerLeave={leave} {...reading}>
        <circle className="ows-rose-hub" cx={C} cy={C} r={hub} />
        {rings.map((value, k) => <circle key={value} className="ows-rose-grid" cx={C} cy={C} r={hub + (reach * value) / outer} pathLength={1} transform={`rotate(-90 ${C} ${C})`} style={{ animationDelay: `${k * 90}ms` }} />)}
        <path className="ows-rose-beam" data-on={shown ? true : undefined} d={shown ? petal(shown.centre, half, hub, R + 4, 0) : undefined} />
        <g className="ows-rose-ticks">
          {TICKS.map((angle, k) => {
            const major = angle % 45 === 0, swell = near(angle);
            return (
              <g key={angle} transform={`rotate(${angle} ${C} ${C})`}>
                <line x1={C} x2={C} y1={C - TICK_FROM} y2={C - TICK_FROM - (major ? 9 : 5)} className="ows-rose-tick" data-major={major || undefined}
                  style={{ transformOrigin: `${C}px ${C - TICK_FROM}px`, transform: `scaleY(${1 + swell * (major ? 0.8 : 1.6)})`, opacity: 0.45 + swell * 0.55, animationDelay: `${k * 7}ms` }} />
              </g>
            );
          })}
        </g>
        <g className="ows-rose-petals" data-hovering={lit !== null || undefined}>{petals}</g>
        {rings.map((value, k) => {
          // Inside its ring, never across it: towards the centre along the quietest direction
          const [x, y] = polar(quiet, hub + (reach * value) / outer - 5);
          const sin = Math.sin(quiet * RAD), cos = Math.cos(quiet * RAD);
          return (
            <text key={value} className="ows-rose-ring" x={x} y={y + (cos > 0.34 ? 11 : cos < -0.34 ? -3 : 4)} textAnchor={sin > 0.34 ? "end" : sin < -0.34 ? "start" : "middle"}>
              {f.number(value, ringDigits)}{k === rings.length - 1 ? ` ${unit}` : ""}
            </text>
          );
        })}
        <g className="ows-rose-points">
          {(["north", "east", "south", "west"] as const).map((name, k) => {
            // Beyond the ticks swollen at their full length
            const [x, y] = polar(k * 90, R + 36);
            return <text key={name} x={x} y={y + 4}>{t(name)}</text>;
          })}
        </g>
      </svg>
      <ReadingLine parts={parts.length ? parts : null} />
    </Box>
  );
}

// ---------------------------------------------------------------------------------------------
// Bars

interface Bar { key: string; label: string; value: number | null; reference?: number | null; /** In the reading, when longer than the axis label */ title?: string }

const BAR_HEIGHT = 300, BAR_TOP = 22, BAR_BOTTOM = 40, BAR_RIGHT = 8;

/** A bar per group (hour, month, class...), with its pale reference behind. */
export function Bars({ bars, unit, digits, keys, label, xLabel }: {
  bars: Bar[]; unit: string; digits: number; keys: Key[]; label: string; xLabel?: string;
}) {
  const f = useFormat();
  const { ref, width } = useElementSize();
  const [seenRef, seen] = useSeen<HTMLDivElement>();
  const [lit, setLit] = useState<number | null>(null);
  const axis = niceAxis(0, Math.max(1e-9, ...bars.flatMap((b) => [b.value ?? 0, b.reference ?? 0])));
  const left = Math.max(34, 10 + CHAR * Math.max(...axis.ticks.map((v) => f.number(v, axis.digits).length)));
  const view = Math.max(0, width - left - BAR_RIGHT);
  const slot = bars.length ? view / bars.length : 0;
  const bar = Math.max(3, Math.min(slot * 0.64, 46));
  const base = BAR_HEIGHT - BAR_BOTTOM;
  const plot = base - BAR_TOP;
  const y = (value: number) => base - (plot * value) / axis.hi;
  // Heights (px) grow from zero once in view, then morph towards other values
  const target = useMemo(() => bars.flatMap((b) => [(plot * Math.max(0, b.value ?? 0)) / axis.hi, (plot * Math.max(0, b.reference ?? 0)) / axis.hi]), [bars, plot, axis.hi]);
  const morphed = useMorph(target, CHART_MS.bars, { grow: true, ready: seen });
  const heights = morphed.length === target.length ? morphed : target;
  // Every label when they fit, otherwise one in n
  const every = Math.max(1, Math.ceil((Math.max(...bars.map((b) => b.label.length), 1) * CHAR + 6) / Math.max(1, slot)));
  // Under the pointer: the group, then the value (and the reference), the unit once
  const withReference = bars.some((b) => typeof b.reference === "number");
  const value = (v: number | null | undefined, last: boolean) => `${f.number(v ?? null, digits)}${last && unit ? ` ${unit}` : ""}`;
  const read = lit === null || !bars[lit] ? null : bars[lit];
  const parts: ReadPart[] = read ? [
    { text: `${read.title ?? read.label} ·` },
    { text: value(read.value, !withReference), dot: withReference ? cssColor(CHART_COLORS.main) : undefined },
    ...(withReference ? [{ text: value(read.reference, true), dot: PALE }] : []),
  ] : [];
  const pick = (event: PointerEvent<SVGSVGElement>) => {
    if (!bars.length || slot <= 0) return;
    const x = event.clientX - event.currentTarget.getBoundingClientRect().left - left;
    setLit(x < 0 || x > view ? null : Math.min(bars.length - 1, Math.floor(x / slot)));
  };
  return (
    <Box ref={seenRef} role="figure" aria-label={label} className="ows-chart">
      <Legend keys={keys} />
      <Box ref={ref}>
        <svg width={Math.max(1, width)} height={BAR_HEIGHT} style={{ display: "block" }} onPointerMove={pick} onPointerLeave={() => setLit(null)} {...readingProps(bars.length, lit, setLit, parts, label)}>
          {width > 0 && (
            <>
              <g className="ows-axis">
                {axis.ticks.map((tick) => (
                  <g key={tick}>
                    <line x1={left} x2={left + view} y1={y(tick)} y2={y(tick)} />
                    <text x={left - 6} y={y(tick) + 3} textAnchor="end">{f.number(tick, axis.digits)}</text>
                  </g>
                ))}
                <text x={left - 6} y={BAR_TOP - 10} textAnchor="end">{unit}</text>
                {bars.map((b, k) => (k % every === 0 ? <text key={b.key} x={left + (k + 0.5) * slot} y={base + 14} textAnchor="middle">{b.label}</text> : null))}
                {xLabel && <text x={left + view / 2} y={BAR_HEIGHT - 6} textAnchor="middle">{xLabel}</text>}
              </g>
              {bars.map((b, k) => {
                const x = left + (k + 0.5) * slot - bar / 2;
                const main = heights[2 * k] ?? 0;
                const reference = heights[2 * k + 1] ?? 0;
                const hot = lit === k;
                return (
                  <g key={b.key}>
                    {typeof b.reference === "number" && reference > 0 && <rect className="ows-bar-pale" x={x} y={base - reference} width={bar} height={reference} rx={2} />}
                    {typeof b.value === "number" && main > 0 && <rect className="ows-bar" data-hot={hot || undefined} x={x} y={base - main} width={bar} height={main} rx={hot ? bar * 0.32 : 2} />}
                  </g>
                );
              })}
              {read && lit !== null && (
                <Readout x={left + (lit + 0.5) * slot} y={y(Math.max(read.value ?? 0, read.reference ?? 0)) + 4} parts={parts} left={left} right={left + view} />
              )}
            </>
          )}
        </svg>
      </Box>
    </Box>
  );
}

// ---------------------------------------------------------------------------------------------
// Curves

interface Curve {
  key: string;
  label: string;
  color: string;
  /** line, dots, line with dots, or a histogram (x: bin edges) */
  kind: "line" | "dots" | "both" | "histogram";
  dashed?: boolean;
  /** Small pale dots: a cloud of values, not read under the pointer */
  cloud?: boolean;
  points: { x: number; y: number }[];
  /** For histograms: the right edge of each bin */
  widths?: number[];
}

const XY_HEIGHT = 320, XY_TOP = 22, XY_BOTTOM = 46, XY_RIGHT = 16;

type Point = { x: number; y: number };
const finite = (p: Point) => Number.isFinite(p.x) && Number.isFinite(p.y);

/**
 * Curves along one axis. ``along`` is the axis the pointer reads: "x" (values against wind
 * speed) or "y" (a profile: values against height).
 */
export function Curves({ curves, along = "x", x: xAxis, y: yAxis, label, height = XY_HEIGHT, children }: {
  curves: Curve[]; along?: "x" | "y"; label: string; height?: number;
  x: { label: string; unit: string; digits: number; from0?: boolean };
  y: { label: string; unit: string; digits: number; from0?: boolean };
  children?: ReactNode;
}) {
  const f = useFormat();
  const { ref, width } = useElementSize();
  const [seenRef, seen] = useSeen<HTMLDivElement>();
  const [lit, setLit] = useState<number | null>(null);
  const ids = useId().replace(/[^a-zA-Z0-9_-]/g, "");
  const alongOf = (p: Point) => (along === "x" ? p.x : p.y);
  const across = (p: Point) => (along === "x" ? p.y : p.x);
  // Each curve's points in reading order, without missing values
  const ordered = useMemo(() => curves.map((c) => (c.kind === "histogram" ? c.points : c.points.filter(finite).sort((a, b) => (along === "x" ? a.x - b.x : a.y - b.y)))), [curves, along]);
  const all = curves.flatMap((c) => c.points.concat(c.widths ? c.points.map((p, k) => ({ x: c.widths![k], y: p.y })) : []));
  const xs = all.map((p) => p.x).filter(Number.isFinite), ys = all.map((p) => p.y).filter(Number.isFinite);
  const ax = niceAxis(xAxis.from0 ? 0 : Math.min(...xs, Infinity), Math.max(...xs, -Infinity), 5);
  const ay = niceAxis(yAxis.from0 ? 0 : Math.min(...ys, Infinity), Math.max(...ys, -Infinity), 4);
  const left = Math.max(34, 10 + CHAR * Math.max(...ay.ticks.map((v) => f.number(v, ay.digits).length)));
  const plot = Math.max(10, width - left - XY_RIGHT);
  const base = height - XY_BOTTOM;
  const sx = (v: number) => left + ((v - ax.lo) / (ax.hi - ax.lo || 1)) * plot;
  const sy = (v: number) => XY_TOP + (1 - (v - ay.lo) / (ay.hi - ay.lo || 1)) * (base - XY_TOP);

  // Screen positions of every point, which morph towards other values (the same number of points)
  // (sx and sy follow from the axes, the margin and the width)
  const target = useMemo(() => ordered.flatMap((points) => points.flatMap((p) => [sx(p.x), sy(p.y)])), [ordered, ax.lo, ax.hi, ay.lo, ay.hi, plot, left]);
  // Another number of points draws the curves again
  const counts = ordered.map((points) => points.length).join("|");
  const morphed = useMorph(target, CHART_MS.line, { ready: seen, key: counts });
  const screen = morphed.length === target.length ? morphed : target;
  let offset = 0;
  const drawn = ordered.map((points) => {
    const at = offset;
    offset += 2 * points.length;
    return points.map((_, k) => ({ X: screen[at + 2 * k] ?? 0, Y: screen[at + 2 * k + 1] ?? 0 }));
  });

  // The positions read under the pointer: every point of the curves that are not clouds, and the
  // centre of each bin of a histogram; each curve gives its value there by linear interpolation
  // (a histogram, the share of its bin), none outside its own range
  const readable = curves.map((c, k) => ({ c, k })).filter(({ c }) => !c.cloud);
  // The bin of a histogram holding a position (the last bin holds its right edge too)
  const binOf = (k: number, position: number) => ordered[k].findIndex((p, j) => {
    const right = curves[k].widths?.[j] ?? p.x;
    return position >= p.x - 1e-9 && (position < right - 1e-9 || (j === ordered[k].length - 1 && position <= right + 1e-9));
  });
  const stops = [...new Set(readable.flatMap(({ c, k }) => ordered[k].map((p, j) => (c.kind === "histogram" ? (p.x + (c.widths?.[j] ?? p.x)) / 2 : alongOf(p)))))].sort((a, b) => a - b);
  const at = lit === null ? null : stops[lit] ?? null;
  const valueOf = (k: number, position: number): Point | null => {
    const sorted = ordered[k];
    if (curves[k].kind === "histogram") {
      const j = binOf(k, position);
      return j < 0 ? null : { x: position, y: sorted[j].y };
    }
    if (!sorted.length || position < alongOf(sorted[0]) - 1e-9 || position > alongOf(sorted[sorted.length - 1]) + 1e-9) return null;
    const j = sorted.findIndex((p) => alongOf(p) >= position - 1e-9);
    const b = sorted[j], a = sorted[Math.max(0, j - 1)];
    if (curves[k].kind === "dots") return Math.abs(alongOf(b) - position) < 1e-9 ? b : null;
    const share = alongOf(b) === alongOf(a) ? 0 : (position - alongOf(a)) / (alongOf(b) - alongOf(a));
    const value = across(a) + share * (across(b) - across(a));
    return along === "x" ? { x: position, y: value } : { x: value, y: position };
  };
  const pick = (event: PointerEvent<SVGSVGElement>) => {
    if (!stops.length) return;
    const box = event.currentTarget.getBoundingClientRect();
    const pointer = along === "x" ? event.clientX - box.left : event.clientY - box.top;
    const place = (v: number) => (along === "x" ? sx(v) : sy(v));
    let best = 0;
    stops.forEach((v, k) => { if (Math.abs(place(v) - pointer) < Math.abs(place(stops[best]) - pointer)) best = k; });
    setLit(best);
  };
  const keys = curves.filter((c) => !c.cloud || curves.length > 1).map((c) => ({ label: c.label, color: c.color, dashed: c.dashed, pale: c.cloud || c.kind === "histogram" }));
  // The area under the first curve read along x, up to the position read
  const filled = along === "x" ? readable.find(({ c }) => c.kind !== "dots" && c.kind !== "histogram") : undefined;
  const area = filled && drawn[filled.k].length > 1
    ? `M${drawn[filled.k][0].X},${base}${drawn[filled.k].map((p) => `L${p.X},${p.Y}`).join("")}L${drawn[filled.k][drawn[filled.k].length - 1].X},${base}Z`
    : null;
  const reading = at === null ? null : readable.map(({ c, k }) => ({ c, p: valueOf(k, at) }));
  // Under the pointer: the position, then the value of each curve there, the unit once
  const withUnit = (text: string, unit: string) => (unit ? `${text} ${unit}` : text);
  const across_ = along === "x" ? yAxis : xAxis;
  const valueText = (p: Point | null, last: boolean) => {
    const text = p ? f.number(along === "x" ? p.y : p.x, across_.digits) : "–";
    return last ? withUnit(text, across_.unit) : text;
  };
  // A histogram read alone is read as bars: its bin (9–10 m/s, as in the key figures), no cursor
  const lone = readable.length === 1 && readable[0].c.kind === "histogram" ? readable[0] : null;
  const bin = lone && at !== null ? binOf(lone.k, at) : -1;
  const binText = (() => {
    if (!lone || bin < 0) return null;
    const lo = ordered[lone.k][bin].x, hi = lone.c.widths?.[bin] ?? lo;
    const digits = Number.isInteger(lo) && Number.isInteger(hi) ? 0 : xAxis.digits;
    return withUnit(`${f.number(lo, digits)}–${f.number(hi, digits)}`, xAxis.unit);
  })();
  const parts: ReadPart[] = !reading || at === null ? [] : [
    { text: `${binText ?? (along === "x" ? withUnit(f.number(at, xAxis.digits), xAxis.unit) : withUnit(f.number(at, yAxis.digits), yAxis.unit))} ·` },
    ...reading.map(({ c, p }, j) => ({ text: valueText(p, j === reading.length - 1), dot: reading.length > 1 ? c.color : undefined })),
  ];
  const first = reading?.find(({ p }) => p !== null)?.p ?? null;
  return (
    <Box ref={seenRef} role="figure" aria-label={label} className="ows-chart" data-unseen={!seen || undefined}>
      <Legend keys={keys} />
      <Box ref={ref}>
        <svg width={Math.max(1, width)} height={height} style={{ display: "block" }} onPointerMove={pick} onPointerLeave={() => setLit(null)} {...readingProps(stops.length, lit, setLit, parts, label)}>
          {width > 0 && (
            <>
              <g className="ows-axis">
                {ay.ticks.map((v) => (
                  <g key={`y${v}`}>
                    <line x1={left} x2={left + plot} y1={sy(v)} y2={sy(v)} />
                    <text x={left - 6} y={sy(v) + 3} textAnchor="end">{f.number(v, ay.digits)}</text>
                  </g>
                ))}
                {ax.ticks.map((v) => <text key={`x${v}`} x={sx(v)} y={base + 14} textAnchor="middle">{f.number(v, ax.digits)}</text>)}
                <text x={left + plot / 2} y={height - 6} textAnchor="middle">{xAxis.label}{xAxis.unit ? ` (${xAxis.unit})` : ""}</text>
                <text x={0} y={10}>{yAxis.label}{yAxis.unit ? ` (${yAxis.unit})` : ""}</text>
              </g>
              {at !== null && area && (
                <>
                  <clipPath id={`${ids}-area`}><rect x={left} y={0} width={Math.max(0, sx(at) - left)} height={height} /></clipPath>
                  <path className="ows-ts-area" d={area} clipPath={`url(#${ids}-area)`} />
                </>
              )}
              <g key={counts} className="ows-ts-curves">
                <clipPath id={`${ids}-reveal`}><rect className={seen ? "ows-ts-reveal" : undefined} x={left - 4} y={0} width={plot + 8} height={height} /></clipPath>
                {curves.map((curve, k) => {
                  const points = drawn[k];
                  if (curve.kind === "histogram") {
                    // The bin read under the pointer turns into a pill, as a bar does
                    const hot = at === null ? -1 : binOf(k, at);
                    return (
                      <g key={curve.key}>
                        {ordered[k].map((p, j) => {
                          const top = points[j]?.Y ?? base;
                          const wide = Math.max(0, sx(curve.widths?.[j] ?? p.x) - sx(p.x) - 2);
                          return Number.isFinite(top) && top < base
                            ? <rect key={j} className="ows-bar-pale" data-hot={hot === j || undefined} x={sx(p.x) + 1} y={top} width={wide} height={base - top} rx={hot === j ? wide * 0.32 : 0} style={{ fill: curve.color }} />
                            : null;
                        })}
                      </g>
                    );
                  }
                  const line = points.map((p, j) => `${j ? "L" : "M"}${p.X.toFixed(1)},${p.Y.toFixed(1)}`).join("");
                  const dots = points.map((p) => `M${p.X.toFixed(1)},${p.Y.toFixed(1)}h0`).join("");
                  return (
                    <g key={curve.key}>
                      {curve.kind !== "dots" && points.length > 1 && (curve.dashed
                        ? <path className="ows-ts-line" d={line} stroke={curve.color} strokeDasharray="6 4" clipPath={`url(#${ids}-reveal)`} />
                        : <path className={seen ? "ows-ts-line ows-ts-draw" : "ows-ts-line"} pathLength={1} d={line} stroke={curve.color} />)}
                      {curve.kind !== "line" && (
                        <path className="ows-ts-dots" d={dots} stroke={curve.color} strokeWidth={curve.cloud ? 4.4 : 6.4} opacity={curve.cloud ? 0.35 : 1} clipPath={`url(#${ids}-reveal)`} />
                      )}
                    </g>
                  );
                })}
              </g>
              {reading && at !== null && (
                <g pointerEvents="none">
                  {lone ? null : along === "x"
                    ? <line className="ows-ts-cursor" x1={sx(at)} x2={sx(at)} y1={XY_TOP} y2={base} />
                    : <line className="ows-ts-cursor" x1={left} x2={left + plot} y1={sy(at)} y2={sy(at)} />}
                  {reading.filter(({ c }) => c.kind !== "histogram").map(({ c, p }, j) => (p ? <circle key={c.key} className="ows-ts-dot" cx={sx(p.x)} cy={sy(p.y)} r={j === 0 ? 4.5 : 3.5} fill={c.color} /> : null))}
                  <Readout x={first ? sx(first.x) : along === "x" ? sx(at) : left + plot / 2} y={first ? sy(first.y) : XY_TOP} parts={parts} left={left} right={left + plot} />
                </g>
              )}
              {children}
            </>
          )}
        </svg>
      </Box>
    </Box>
  );
}
