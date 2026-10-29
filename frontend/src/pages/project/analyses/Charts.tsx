/**
 * The charts of the wind analyses, drawn one way: a rose for what goes by direction, bars for
 * what goes by group, curves for what goes along an axis. Everything appears once when the values
 * change (petals grow from the centre, bars rise, lines draw themselves), the element under the
 * pointer stands out and its values show in the same small panel, and the axes carry round
 * values with the unit written once.
 */
import { Box, Group, Text } from "@mantine/core";
import { useElementSize } from "@mantine/hooks";
import { type ReactNode, useState } from "react";

import { defineMessages, useFormat, useT } from "../../../i18n";
import { CHART_COLORS, cssColor } from "../results/TimeChart";

const MAIN = cssColor(CHART_COLORS.main);
const PALE = cssColor(CHART_COLORS.reference);

const messages = defineMessages({
  en: { north: "N", east: "E", south: "S", west: "W" },
  fr: { north: "N", east: "E", south: "S", west: "O" },
});

/** A round step that cuts a span in about ``parts`` pieces. */
export function niceStep(span: number, parts = 4): number {
  const raw = span / parts;
  const power = 10 ** Math.floor(Math.log10(raw || 1));
  return [1, 2, 2.5, 5, 10].map((m) => m * power).find((s) => s >= raw) ?? 10 * power;
}

/** Decimals needed to write a step exactly (2.5 → 1, 0.25 → 2, 5 → 0). */
export function decimals(step: number): number {
  let digits = 0;
  while (digits < 6 && Math.abs(step * 10 ** digits - Math.round(step * 10 ** digits)) > 1e-6) digits += 1;
  return digits;
}

/** Round ticks covering [min, max]. */
export function niceAxis(min: number, max: number, parts = 4) {
  const span = max - min || Math.abs(max) || 1;
  const step = niceStep(span, parts);
  const lo = Math.floor(min / step) * step;
  const hi = Math.ceil(max / step) * step || step;
  const ticks = Array.from({ length: Math.round((hi - lo) / step) + 1 }, (_, k) => lo + k * step);
  return { lo, hi, step, ticks, digits: decimals(step) };
}

export interface Key { label: string; color: string; pale?: boolean; dashed?: boolean }

/** The colour keys of a chart, above it. */
export function Legend({ keys }: { keys: Key[] }) {
  if (keys.length < 2) return null;
  return (
    <Group justify="center" gap="md" mb={8}>
      {keys.map((key) => (
        <Group key={key.label} gap={6} wrap="nowrap">
          {key.dashed
            ? <svg width={18} height={10} aria-hidden><path d="M 0 5 H 18" stroke={key.color} strokeWidth={2} strokeDasharray="4 3" /></svg>
            : <span className={key.pale ? "ows-bars-key ows-bars-key-pale" : "ows-bars-key"} style={{ background: key.color }} />}
          <Text size="xs" fw={600}>{key.label}</Text>
        </Group>
      ))}
    </Group>
  );
}

export interface TipRow { label: string; value: string }

/** The values of the element under the pointer. */
function Tip({ title, rows, left }: { title: string; rows: TipRow[]; left: number }) {
  return (
    <div className="ows-bars-tip" style={{ left, top: 34 }}>
      <Text size="xs" fw={600} mb={4}>{title}</Text>
      {rows.map((row) => (
        <Group key={row.label} justify="space-between" gap="md" wrap="nowrap">
          <Text size="xs" c="dimmed" style={{ whiteSpace: "nowrap" }}>{row.label}</Text>
          <Text size="xs" fw={600} className="ows-num">{row.value}</Text>
        </Group>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------
// Rose

export interface RoseSector {
  centre: number;
  /** Stacked from the centre outwards */
  parts: { value: number; color: string }[];
  /** Drawn pale behind the petal */
  reference?: number | null;
}

const R = 140, C = 180;
const polar = (degrees: number, r: number) => [C + r * Math.sin((degrees * Math.PI) / 180), C - r * Math.cos((degrees * Math.PI) / 180)];

/**
 * A petal per direction sector, its length the value (parts stacked from the centre, the
 * reference pale behind). Directions are where the wind comes from, clockwise from north.
 */
export function Rose({ sectors, unit, keys, label, tip }: {
  sectors: RoseSector[]; unit: string; keys: Key[]; label: string;
  tip: (sector: RoseSector) => TipRow[];
}) {
  const t = useT(messages);
  const f = useFormat();
  const { ref, width } = useElementSize();
  const [lit, setLit] = useState<number | null>(null);
  const total = (s: RoseSector) => s.parts.reduce((sum, p) => sum + Math.max(0, p.value), 0);
  const top = Math.max(1e-9, ...sectors.flatMap((s) => [total(s), s.reference ?? 0]));
  const step = niceStep(top, 4);
  const outer = Math.ceil(top / step) * step;
  const rings = Array.from({ length: Math.round(outer / step) }, (_, k) => (k + 1) * step);
  const ringDigits = decimals(step);
  const half = (0.84 * 180) / Math.max(1, sectors.length);
  const wedge = (angle: number, from: number, to: number) => {
    const r1 = (R * from) / outer, r2 = (R * Math.max(from, to)) / outer;
    const [x1, y1] = polar(angle - half, r2), [x2, y2] = polar(angle + half, r2);
    const [x3, y3] = polar(angle + half, r1), [x4, y4] = polar(angle - half, r1);
    return `M ${x4} ${y4} L ${x1} ${y1} A ${r2} ${r2} 0 0 1 ${x2} ${y2} L ${x3} ${y3} ${r1 > 0 ? `A ${r1} ${r1} 0 0 0 ${x4} ${y4}` : ""} Z`;
  };
  const signature = sectors.map((s) => `${s.parts.map((p) => p.value).join(",")}:${s.reference}`).join("|");
  const shown = lit === null ? null : sectors[lit];
  return (
    <Box ref={ref} role="figure" aria-label={label} pos="relative">
      <Legend keys={keys} />
      <svg viewBox="0 0 360 360" style={{ width: 360, maxWidth: "100%", display: "block", margin: "0 auto" }} onPointerLeave={() => setLit(null)}>
        {[0, 45, 90, 135, 180, 225, 270, 315].map((angle) => { const [x, y] = polar(angle, R); return <path key={angle} d={`M ${C} ${C} L ${x} ${y}`} stroke="var(--ows-border)" />; })}
        {rings.map((value) => <circle key={value} cx={C} cy={C} r={(R * value) / outer} fill="none" stroke="var(--ows-border)" />)}
        <g key={signature} className="ows-rose-grow" data-hovering={lit !== null || undefined}>
          {sectors.map((sector, k) => {
            let base = 0;
            return (
              <g key={sector.centre} data-lit={lit === k || undefined} style={{ animationDelay: `${Math.round((k / sectors.length) * 320)}ms` }} onPointerEnter={() => setLit(k)}>
                <path d={wedge(sector.centre, 0, outer)} fill="transparent" />
                {typeof sector.reference === "number" && <path d={wedge(sector.centre, 0, sector.reference)} fill={PALE} opacity={0.32} />}
                {sector.parts.map((part, p) => {
                  const from = base;
                  base += Math.max(0, part.value);
                  return part.value > 0 ? <path key={p} d={wedge(sector.centre, from, base)} fill={part.color} stroke="var(--ows-card)" strokeWidth={0.6} /> : null;
                })}
              </g>
            );
          })}
        </g>
        {rings.map((value, k) => <text key={value} x={C + 4} y={C - (R * value) / outer + 11} fontSize={12} fill="currentColor" stroke="var(--ows-card)" strokeWidth={3} paintOrder="stroke" className="ows-num">{f.number(value, ringDigits)}{k === rings.length - 1 ? ` ${unit}` : ""}</text>)}
        <text x={C} y={22} textAnchor="middle" fontSize={13} fill="currentColor">{t("north")}</text>
        <text x={345} y={184} textAnchor="middle" fontSize={13} fill="currentColor">{t("east")}</text>
        <text x={C} y={350} textAnchor="middle" fontSize={13} fill="currentColor">{t("south")}</text>
        <text x={15} y={184} textAnchor="middle" fontSize={13} fill="currentColor">{t("west")}</text>
      </svg>
      {shown && <Tip title={`${f.number(shown.centre, 0)}°`} rows={tip(shown)} left={Math.max(90, width - 95)} />}
    </Box>
  );
}

// ---------------------------------------------------------------------------------------------
// Bars

export interface Bar { key: string; label: string; value: number | null; reference?: number | null; /** In the panel, when longer than the axis label */ title?: string }

const BAR_HEIGHT = 300, BAR_TOP = 12, BAR_BOTTOM = 40, AXIS = 52;

/** A bar per group (hour, month, class...), with its pale reference behind. */
export function Bars({ bars, unit, digits, keys, label, xLabel, tipLabels }: {
  bars: Bar[]; unit: string; digits: number; keys: Key[]; label: string; xLabel?: string;
  tipLabels: { main: string; reference?: string };
}) {
  const f = useFormat();
  const { ref, width } = useElementSize();
  const [lit, setLit] = useState<number | null>(null);
  const axis = niceAxis(0, Math.max(1e-9, ...bars.flatMap((b) => [b.value ?? 0, b.reference ?? 0])));
  const view = Math.max(0, width - AXIS);
  const slot = bars.length ? view / bars.length : 0;
  const bar = Math.max(3, Math.min(slot * 0.62, 46));
  const y = (value: number) => BAR_TOP + (BAR_HEIGHT - BAR_TOP - BAR_BOTTOM) * (1 - value / axis.hi);
  // Every label when they fit, otherwise one in n
  const every = Math.max(1, Math.ceil(Math.max(...bars.map((b) => b.label.length), 1) * 7.5 / Math.max(1, slot)));
  const signature = bars.map((b) => `${b.key}:${b.value}:${b.reference}`).join("|");
  const shown = lit === null ? null : bars[lit];
  const value = (v: number | null | undefined) => (typeof v === "number" ? `${f.number(v, digits)} ${unit}` : "–");
  return (
    <Box ref={ref} role="figure" aria-label={label} pos="relative">
      <Legend keys={keys} />
      <svg width={Math.max(0, width)} height={BAR_HEIGHT} style={{ display: "block" }} onPointerLeave={() => setLit(null)}>
        {axis.ticks.map((tick) => (
          <g key={tick}>
            <line x1={AXIS} x2={width} y1={y(tick)} y2={y(tick)} stroke="var(--ows-border)" />
            <text x={AXIS - 8} y={y(tick) + 4} textAnchor="end" fontSize={12} fill="var(--ows-muted)" className="ows-num">{f.number(tick, axis.digits)}</text>
          </g>
        ))}
        <text transform={`translate(12 ${(BAR_HEIGHT - BAR_BOTTOM) / 2}) rotate(-90)`} textAnchor="middle" fontSize={12} fill="var(--ows-muted)">{unit}</text>
        <g key={signature} className="ows-bars-grow" data-hovering={lit !== null || undefined}>
          {bars.map((b, k) => {
            const x = AXIS + (k + 0.5) * slot - bar / 2;
            return (
              <g key={b.key} data-lit={lit === k || undefined} style={{ animationDelay: `${Math.round((k / Math.max(1, bars.length)) * 380)}ms` }} onPointerEnter={() => setLit(k)}>
                <rect x={AXIS + k * slot} y={BAR_TOP} width={slot} height={BAR_HEIGHT - BAR_TOP - BAR_BOTTOM} fill="transparent" />
                {typeof b.reference === "number" && b.reference > 0 && <rect x={x} y={y(b.reference)} width={bar} height={y(0) - y(b.reference)} rx={Math.min(3, bar / 3)} fill={PALE} opacity={0.32} />}
                {typeof b.value === "number" && b.value > 0 && <rect x={x} y={y(b.value)} width={bar} height={y(0) - y(b.value)} rx={Math.min(3, bar / 3)} fill={MAIN} />}
              </g>
            );
          })}
        </g>
        <line x1={AXIS} x2={width} y1={y(0)} y2={y(0)} stroke="var(--ows-border-strong)" />
        {bars.map((b, k) => (k % every === 0 ? <text key={b.key} x={AXIS + (k + 0.5) * slot} y={BAR_HEIGHT - BAR_BOTTOM + 16} textAnchor="middle" fontSize={12} fill="var(--ows-muted)" className="ows-num">{b.label}</text> : null))}
        {xLabel && <text x={AXIS + view / 2} y={BAR_HEIGHT - 4} textAnchor="middle" fontSize={12} fill="var(--ows-muted)">{xLabel}</text>}
      </svg>
      {shown && (
        <Tip title={shown.title ?? shown.label} left={Math.min(Math.max(AXIS + ((lit ?? 0) + 0.5) * slot, AXIS + 90), Math.max(AXIS + 90, width - 90))}
          rows={[{ label: tipLabels.main, value: value(shown.value) }, ...(tipLabels.reference ? [{ label: tipLabels.reference, value: value(shown.reference) }] : [])]} />
      )}
    </Box>
  );
}

// ---------------------------------------------------------------------------------------------
// Curves

export interface Curve {
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

const XY_HEIGHT = 320, XY_TOP = 14, XY_BOTTOM = 46, XY_RIGHT = 16;

/**
 * Curves along one axis. ``along`` is the axis the pointer reads: "x" (values against wind
 * speed) or "y" (a profile: values against height).
 */
export function Curves({ curves, along = "x", x: xAxis, y: yAxis, label, children }: {
  curves: Curve[]; along?: "x" | "y"; label: string;
  x: { label: string; unit: string; digits: number; from0?: boolean };
  y: { label: string; unit: string; digits: number; from0?: boolean };
  children?: ReactNode;
}) {
  const f = useFormat();
  const { ref, width } = useElementSize();
  const [lit, setLit] = useState<number | null>(null);
  const all = curves.flatMap((c) => c.points.concat(c.widths ? c.points.map((p, k) => ({ x: c.widths![k], y: p.y })) : []));
  const xs = all.map((p) => p.x).filter(Number.isFinite), ys = all.map((p) => p.y).filter(Number.isFinite);
  const ax = niceAxis(xAxis.from0 ? 0 : Math.min(...xs, Infinity), Math.max(...xs, -Infinity), 5);
  const ay = niceAxis(yAxis.from0 ? 0 : Math.min(...ys, Infinity), Math.max(...ys, -Infinity), 4);
  const left = 58, plot = Math.max(10, width - left - XY_RIGHT);
  const sx = (v: number) => left + ((v - ax.lo) / (ax.hi - ax.lo || 1)) * plot;
  const sy = (v: number) => XY_TOP + (1 - (v - ay.lo) / (ay.hi - ay.lo || 1)) * (XY_HEIGHT - XY_TOP - XY_BOTTOM);
  // The positions read under the pointer: every point of the curves that are not clouds; each
  // curve gives its value there by linear interpolation, none outside its own range
  const readable = curves.filter((c) => !c.cloud && c.kind !== "histogram");
  const along_ = (p: { x: number; y: number }) => (along === "x" ? p.x : p.y);
  const across = (p: { x: number; y: number }) => (along === "x" ? p.y : p.x);
  const stops = [...new Set(readable.flatMap((c) => c.points.map(along_)).filter(Number.isFinite))].sort((a, b) => a - b);
  const at = lit === null ? null : stops[lit] ?? null;
  const valueOf = (curve: Curve, position: number): { x: number; y: number } | null => {
    const sorted = curve.points.filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y)).sort((a, b) => along_(a) - along_(b));
    if (!sorted.length || position < along_(sorted[0]) - 1e-9 || position > along_(sorted[sorted.length - 1]) + 1e-9) return null;
    const k = sorted.findIndex((p) => along_(p) >= position - 1e-9);
    const b = sorted[k], a = sorted[Math.max(0, k - 1)];
    if (curve.kind === "dots") return Math.abs(along_(b) - position) < 1e-9 ? b : null;
    const share = along_(b) === along_(a) ? 0 : (position - along_(a)) / (along_(b) - along_(a));
    const value = across(a) + share * (across(b) - across(a));
    return along === "x" ? { x: position, y: value } : { x: value, y: position };
  };
  const pick = (event: React.PointerEvent<SVGSVGElement>) => {
    if (!stops.length) return;
    const box = event.currentTarget.getBoundingClientRect();
    const pointer = along === "x" ? event.clientX - box.left : event.clientY - box.top;
    const screen = (v: number) => (along === "x" ? sx(v) : sy(v));
    let best = 0;
    stops.forEach((v, k) => { if (Math.abs(screen(v) - pointer) < Math.abs(screen(stops[best]) - pointer)) best = k; });
    setLit(best);
  };
  const signature = curves.map((c) => `${c.key}:${c.points.length}:${c.points[0]?.y}:${c.points.at(-1)?.y}`).join("|");
  const keys = curves.filter((c) => !c.cloud || curves.length > 1).map((c) => ({ label: c.label, color: c.color, dashed: c.dashed, pale: c.cloud || c.kind === "histogram" }));
  const tipLeft = at !== null ? Math.min(Math.max(along === "x" ? sx(at) : left + plot / 2, 90), Math.max(90, width - 90)) : 0;
  return (
    <Box ref={ref} role="figure" aria-label={label} pos="relative">
      <Legend keys={keys} />
      <svg width={Math.max(0, width)} height={XY_HEIGHT} style={{ display: "block" }} onPointerMove={pick} onPointerLeave={() => setLit(null)}>
        {ay.ticks.map((v) => (
          <g key={`y${v}`}>
            <line x1={left} x2={left + plot} y1={sy(v)} y2={sy(v)} stroke="var(--ows-border)" />
            <text x={left - 8} y={sy(v) + 4} textAnchor="end" fontSize={12} fill="var(--ows-muted)" className="ows-num">{f.number(v, ay.digits)}</text>
          </g>
        ))}
        {ax.ticks.map((v) => <text key={`x${v}`} x={sx(v)} y={XY_HEIGHT - XY_BOTTOM + 18} textAnchor="middle" fontSize={12} fill="var(--ows-muted)" className="ows-num">{f.number(v, ax.digits)}</text>)}
        <line x1={left} x2={left + plot} y1={sy(ay.lo)} y2={sy(ay.lo)} stroke="var(--ows-border-strong)" />
        <text x={left + plot / 2} y={XY_HEIGHT - 6} textAnchor="middle" fontSize={12} fill="var(--ows-muted)">{xAxis.label}{xAxis.unit ? ` (${xAxis.unit})` : ""}</text>
        <text transform={`translate(13 ${(XY_HEIGHT - XY_BOTTOM) / 2}) rotate(-90)`} textAnchor="middle" fontSize={12} fill="var(--ows-muted)">{yAxis.label}{yAxis.unit ? ` (${yAxis.unit})` : ""}</text>
        <g key={signature} className="ows-curves-in">
          {curves.map((curve) => {
            if (curve.kind === "histogram") {
              return <g key={curve.key} className="ows-bars-grow">{curve.points.map((p, k) => <g key={k} style={{ animationDelay: `${Math.round((k / curve.points.length) * 300)}ms` }}><rect x={sx(p.x) + 1} y={sy(p.y)} width={Math.max(0, sx(curve.widths?.[k] ?? p.x) - sx(p.x) - 2)} height={sy(ay.lo) - sy(p.y)} fill={curve.color} opacity={0.28} /></g>)}</g>;
            }
            const ordered = [...curve.points].sort((a, b) => (along === "x" ? a.x - b.x : a.y - b.y)).filter((p) => Number.isFinite(p.x) && Number.isFinite(p.y));
            const line = ordered.map((p, k) => `${k ? "L" : "M"} ${sx(p.x)} ${sy(p.y)}`).join(" ");
            return (
              <g key={curve.key}>
                {curve.kind !== "dots" && ordered.length > 1 && <path d={line} pathLength={curve.dashed ? undefined : 1} className="ows-curve-draw" fill="none" stroke={curve.color} strokeWidth={2} strokeDasharray={curve.dashed ? "6 4" : undefined} data-dashed={curve.dashed || undefined} />}
                {curve.kind !== "line" && <g className="ows-dots-in">{ordered.map((p, k) => <circle key={k} cx={sx(p.x)} cy={sy(p.y)} r={curve.cloud ? 2.2 : 3.2} fill={curve.color} opacity={curve.cloud ? 0.35 : 1} />)}</g>}
              </g>
            );
          })}
        </g>
        {at !== null && (
          <g pointerEvents="none">
            {along === "x"
              ? <line x1={sx(at)} x2={sx(at)} y1={XY_TOP} y2={sy(ay.lo)} stroke="var(--ows-border-strong)" />
              : <line x1={left} x2={left + plot} y1={sy(at)} y2={sy(at)} stroke="var(--ows-border-strong)" />}
            {readable.map((c) => { const p = valueOf(c, at); return p ? <circle key={c.key} cx={sx(p.x)} cy={sy(p.y)} r={4.5} fill={c.color} stroke="var(--ows-card)" strokeWidth={1.5} /> : null; })}
          </g>
        )}
        {children}
      </svg>
      {at !== null && (
        <Tip left={tipLeft}
          title={along === "x" ? `${f.number(at, xAxis.digits)} ${xAxis.unit}` : `${f.number(at, yAxis.digits)} ${yAxis.unit}`}
          rows={readable.map((c) => { const p = valueOf(c, at); return { label: c.label, value: p ? (along === "x" ? `${f.number(p.y, yAxis.digits)} ${yAxis.unit}` : `${f.number(p.x, xAxis.digits)} ${xAxis.unit}`) : "–" }; })} />
      )}
    </Box>
  );
}
