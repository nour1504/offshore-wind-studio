/**
 * The calculation windows as a spiral staircase, half 3D, half 2D: one step per window in
 * chronological order, turning and rising around an empty centre, carried by a curved stringer;
 * the spin-up of a window is a thin hatched ledge before its step (simulated, never kept), not a
 * step of its own. When the part seen holds many windows, they gather into one step per month,
 * then per year; zooming narrows the part seen, which then fills the whole turn, and the windows
 * come back one by one. Nothing here changes the plan: the groups, the zoom and the opening (the
 * rail drawn, the steps rising from the first date to the last) are only a way to look at it; the
 * order of computation stays the server's (from the last window to the first), in each tooltip.
 * Where the part seen lies is always shown: its dates above, its month or year in the empty
 * centre, and the period bar below (PeriodBar.tsx), which also moves it.
 *
 * Layers: data (model.ts), geometry (spiral.ts), navigation (view.ts, useStairsView.ts), and
 * here the drawing; the steps are memoised apart from the hover, so that moving the pointer
 * redraws only the highlight, the label and the tooltip.
 */
import { ActionIcon, Box, Button, Group, Stack, Text, Tooltip } from "@mantine/core";
import { useElementSize, useReducedMotion } from "@mantine/hooks";
import { IconArrowsMaximize, IconMinus, IconPlayerPlay, IconPlayerStop, IconPlus } from "@tabler/icons-react";
import { memo, useEffect, useId, useMemo, useRef, useState } from "react";

import type { WindowPlan } from "../../../../api/method";
import { defineMessages, useFormat, useLang, useT } from "../../../../i18n";
import { buildStairs, type Stairs, visibleRange } from "./model";
import { drawn, frame, type Geometry, hourAt, type Item, type Shape, slabs } from "./spiral";
import { frameHours, type Limits, type Range, whole } from "./view";
import { useStairsView } from "./useStairsView";
import { PeriodBar } from "./PeriodBar";

const messages = defineMessages({
  en: {
    label: "Calculation windows, from {start} to {end}",
    window: "Window {id}",
    spin: "spin-up {h} h",
    restart: "continues the previous window",
    order: "computed {n} of {total}",
    windows: "{n|# window|# windows}",
    zoomIn: "Zoom in",
    zoomOut: "Zoom out",
    whole: "Whole period",
    week: "week of {date}",
    seen: "Part seen",
    play: "Play the order of computation",
    stop: "Stop",
  },
  fr: {
    label: "Fenêtres de calcul, du {start} au {end}",
    window: "Fenêtre {id}",
    spin: "mise en route {h} h",
    restart: "suite de la fenêtre précédente",
    order: "calculée en {n} sur {total}",
    windows: "{n|# fenêtre|# fenêtres}",
    zoomIn: "Zoomer",
    zoomOut: "Dézoomer",
    whole: "Toute la période",
    week: "sem. du {date}",
    seen: "Partie vue",
    play: "Rejouer l'ordre de calcul",
    stop: "Arrêter",
  },
});

const HOUR = 3.6e6;
const HEIGHT = 440;
const OPENING = 1100;
// The faces: tops in the accent colour (every other month lighter), sides and risers darker,
// a light edge on the nose of each step, the stringer in the colour of the page, darker inside
const TOP = "var(--mantine-primary-color-filled)";
const TOP_ALT = "color-mix(in srgb, var(--mantine-primary-color-filled) 70%, var(--ows-canvas))";
const SIDE = "color-mix(in srgb, var(--mantine-primary-color-filled) 66%, black)";
const RISER = "color-mix(in srgb, var(--mantine-primary-color-filled) 80%, black)";
const STRINGER_OUT = "color-mix(in srgb, var(--ows-canvas) 89%, var(--mantine-color-text))";
const STRINGER_IN = "color-mix(in srgb, var(--ows-canvas) 82%, var(--mantine-color-text))";

type Layer = "windows" | "months" | "years";
const LAYERS: Layer[] = ["years", "months", "windows"];

const smooth = (a: number, b: number, v: number) => {
  const t = Math.min(1, Math.max(0, (v - a) / (b - a)));
  return t * t * (3 - 2 * t);
};

function items(stairs: Stairs, layer: Layer): Item[] {
  if (layer === "windows") return stairs.steps.map((s) => ({ key: s.window.id, index: s.index, h0: s.x0, h1: s.x1, s0: s.s0 }));
  return stairs[layer].map((g, index) => ({ key: g.key, index, h0: g.x0, h1: g.x1 }));
}

/** How much of each level is shown: the windows while there are few in the part seen, then the months, then the years. */
function detail(stairs: Stairs, range: Range) {
  const count = (list: { x0: number; x1: number }[]) => {
    const [a, b] = visibleRange(list, range.t0, range.t1);
    return b - a;
  };
  const windows = stairs.months.length <= 1 ? 1 : 1 - smooth(40, 50, count(stairs.steps));
  const years = stairs.years.length <= 1 ? 0 : smooth(56, 68, count(stairs.months));
  return { windows, months: (1 - windows) * (1 - years), years: (1 - windows) * years };
}

function StepFaces({ shape, layer, front, hatch, intro }: { shape: Shape; layer: Layer; front: boolean; hatch: string; intro: boolean }) {
  const pieces = shape.pieces.filter((p) => p.front === front);
  const spin = shape.spin && shape.spin.front === front ? shape.spin : null;
  if (!pieces.length && !spin) return null;
  const top = layer !== "windows" && shape.index % 2 ? TOP_ALT : TOP;
  return (
    <g data-k={`${layer}:${shape.index}`} className={intro ? "ows-stair-in" : undefined} style={intro ? { animationDelay: `${Math.round(shape.at * OPENING * 0.85)}ms` } : undefined}>
      {pieces.map((piece, n) => (
        <g key={n}>
          <path d={piece.stringer} style={{ fill: front ? STRINGER_OUT : STRINGER_IN }} />
          <path d={piece.under} fill="none" stroke="var(--ows-border-strong)" strokeWidth={1} />
          {piece.side && <path d={piece.side} style={{ fill: SIDE }} />}
          {piece.riser && <path d={piece.riser} style={{ fill: RISER }} />}
          <path d={piece.top} style={{ fill: top }} />
          {piece.nose && <path d={piece.nose} fill="none" stroke="var(--ows-canvas)" strokeOpacity={0.45} strokeWidth={1} />}
        </g>
      ))}
      {spin && <path d={spin.d} fill={`url(#${hatch})`} stroke="var(--ows-muted)" strokeOpacity={0.5} strokeWidth={0.6} />}
    </g>
  );
}

/** The staircase for a part of the period: back pieces, then front pieces, each from the lowest step to the highest. */
const Staircase = memo(function Staircase({ stairs, range, geometry, hatch, intro }: { stairs: Stairs; range: Range; geometry: Geometry; hatch: string; intro: boolean }) {
  const shown = detail(stairs, range);
  const all = useMemo(() => ({ windows: items(stairs, "windows"), months: items(stairs, "months"), years: items(stairs, "years") }), [stairs]);
  const layers = LAYERS.filter((layer) => shown[layer] > 0.02).map((layer) => {
    const list = all[layer];
    const [a, b] = visibleRange(list.map((i) => ({ x0: i.h0, x1: i.h1 })), range.t0, range.t1);
    const shapes = slabs(list.slice(a, b), drawn(range, stairs.typical), geometry).sort((p, q) => p.z - q.z);
    return { layer, opacity: shown[layer], shapes };
  });
  // The rail runs along the period only (a short period does not fill the turn)
  const shownPart = drawn(range, stairs.typical);
  const railFrom = (range.t0 - shownPart.t0) / (shownPart.t1 - shownPart.t0) - 1e-6;
  const railTo = (range.t1 - shownPart.t0) / (shownPart.t1 - shownPart.t0) + 1e-6;
  const rail = (front: boolean) => geometry.rail.filter((r) => r.front === front && r.from >= railFrom - 1 / 48 && r.to <= railTo + 1 / 48).map((r, n) => (
    <path key={n} d={r.d} pathLength={1} fill="none" stroke="var(--ows-muted)" strokeOpacity={0.5} strokeWidth={1.1} strokeLinecap="round"
      className={intro ? "ows-rail-in" : undefined} style={intro ? { animationDelay: `${Math.round(r.from * OPENING)}ms`, animationDuration: `${Math.max(20, Math.round((r.to - r.from) * OPENING))}ms` } : undefined} />
  ));
  const half = (front: boolean) => layers.map(({ layer, opacity, shapes }) => (
    <g key={`${front}-${layer}`} opacity={opacity}>
      {shapes.map((shape) => <StepFaces key={shape.key} shape={shape} layer={layer} front={front} hatch={hatch} intro={intro} />)}
    </g>
  ));
  return (
    <>
      <path d={geometry.shadow} fill="var(--ows-subtle)" className={intro ? "ows-stair-ground" : undefined} />
      {rail(false)}
      {half(false)}
      {half(true)}
      {rail(true)}
    </>
  );
});

type Hover = { layer: Layer; index: number; sx: number; sy: number } | null;

export function WindowStairs({ plan }: { plan: WindowPlan }) {
  const t = useT(messages);
  const f = useFormat();
  const { lang } = useLang();
  const reduced = useReducedMotion();
  const hatch = useId().replace(/:/g, "");
  const { ref: box, width } = useElementSize();
  const [svg, setSvg] = useState<SVGSVGElement | null>(null);
  const stairs = useMemo(() => buildStairs(plan), [plan]);
  const geometry = useMemo(() => frame(Math.max(1, width), HEIGHT), [width]);
  // Down to about five windows over the whole turn
  const limits = useMemo<Limits>(() => ({ span: stairs.span, shortest: stairs.count <= 5 ? stairs.span : Math.min(stairs.span, 5 * stairs.typical) }), [stairs]);
  const [hover, setHover] = useState<Hover>(null);
  const hoverRef = useRef<Hover>(null);
  hoverRef.current = hover;
  const rangeRef = useRef<Range>(whole(limits));

  const nav = useStairsView(svg, limits, {
    hourAt: (sx, sy) => hourAt(sx, sy, drawn(rangeRef.current, stairs.typical), geometry),
    dragSpan: geometry.sweepLength * 0.9,
    onClick: () => {
      const current = hoverRef.current;
      if (!current) return;
      if (current.layer === "windows") {
        const step = stairs.steps[current.index];
        nav.animateTo(frameHours(step.x0 - 2 * stairs.typical, step.x1 + 2 * stairs.typical, limits, 0));
      } else {
        const group = stairs[current.layer][current.index];
        nav.animateTo(frameHours(group.x0, group.x1, limits));
      }
    },
  });
  const range = nav.range;
  rangeRef.current = range;

  // The opening: once, from the first date to the last; again, shorter, for a new plan
  const [intro, setIntro] = useState(!reduced);
  useEffect(() => {
    if (reduced) return;
    setIntro(true);
    const done = window.setTimeout(() => setIntro(false), OPENING + 800);
    return () => window.clearTimeout(done);
  }, [stairs, reduced]);

  const move = (event: React.PointerEvent<SVGSVGElement>) => {
    if (event.buttons) return setHover(null);
    const target = (event.target as Element).closest("[data-k]");
    if (!target) return setHover(null);
    const [layer, index] = target.getAttribute("data-k")!.split(":");
    const rect = event.currentTarget.getBoundingClientRect();
    setHover({ layer: layer as Layer, index: Number(index), sx: event.clientX - rect.left, sy: event.clientY - rect.top });
  };

  const monthName = (time: number) => new Intl.DateTimeFormat(lang, { month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(time));
  let overlay = null;
  let tip = null;
  if (hover) {
    const source = hover.layer === "windows" ? stairs.steps[hover.index] : stairs[hover.layer][hover.index];
    const [shape] = slabs([{ key: "hover", index: hover.index, h0: source.x0, h1: source.x1 }], drawn(range, stairs.typical), geometry);
    const label = (() => {
      if (hover.layer === "years") return String(new Date(stairs.years[hover.index].time).getUTCFullYear());
      if (hover.layer === "months") return monthName(stairs.months[hover.index].time);
      const start = new Date(stairs.origin + stairs.steps[hover.index].x0 * HOUR);
      const windowsSeen = (range.t1 - range.t0) / stairs.typical;
      if (windowsSeen > 12) return monthName(Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), 1));
      const monday = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth(), start.getUTCDate() - ((start.getUTCDay() + 6) % 7)));
      return t("week", { date: new Intl.DateTimeFormat(lang, { day: "2-digit", month: "2-digit", year: "numeric", timeZone: "UTC" }).format(monday) });
    })();
    if (shape) {
      overlay = (
        <g pointerEvents="none">
          <g key={`${hover.layer}:${hover.index}`} className="ows-stair-lift">
            {shape.pieces.map((piece, n) => <path key={n} d={piece.top} fill="var(--ows-canvas)" fillOpacity={0.22} stroke="var(--mantine-color-text)" strokeOpacity={0.75} strokeWidth={1.3} strokeLinejoin="round" />)}
          </g>
          <text key={label} className="ows-stair-label" x={shape.anchor[0]} y={shape.anchor[1] - 16} fontSize={12} fontWeight={600} textAnchor="middle" fill="var(--mantine-color-text)" stroke="var(--mantine-color-body)" strokeWidth={4} strokeLinejoin="round" paintOrder="stroke">{label}</text>
        </g>
      );
    }
    const lines = (() => {
      if (hover.layer === "windows") {
        const step = stairs.steps[hover.index];
        return [t("window", { id: step.window.id }), `${f.dateTime(step.window.useful_start)} → ${f.dateTime(step.window.useful_end)}`, `${f.number(step.x1 - step.x0, 0)} h · ${step.window.restart ? t("restart") : t("spin", { h: f.number(step.x0 - step.s0, 0) })}`, t("order", { n: step.window.order, total: stairs.count })];
      }
      const group = stairs[hover.layer][hover.index];
      const iso = (hours: number) => new Date(stairs.origin + hours * HOUR).toISOString();
      return [label, t("windows", { n: group.last - group.first + 1 }), `${f.dateTime(iso(group.x0))} → ${f.dateTime(iso(group.x1))}`];
    })();
    const left = hover.sx + 18 + 250 > width ? hover.sx - 18 - 250 : hover.sx + 18;
    // Below the step and its label, or above them near the bottom of the frame
    const below = Math.max(hover.sy, shape ? shape.anchor[1] : 0) + 18;
    const tipTop = below + 100 <= HEIGHT ? below : Math.max(0, (shape ? shape.anchor[1] - 16 : hover.sy) - 24 - 100);
    tip = (
      <Box key={`${hover.layer}:${hover.index}`} className="ows-stair-tip" style={{ position: "absolute", left: Math.max(0, left), top: tipTop, width: 250, pointerEvents: "none", padding: "8px 10px", borderRadius: 10, background: "var(--mantine-color-body)", border: "1px solid var(--ows-border-strong)", boxShadow: "var(--ows-shadow-pop)" }}>
        {lines.map((line, n) => <Text key={n} size="xs" fw={n === 0 ? 600 : 400} c={n === 0 ? undefined : "dimmed"} lh={1.45}>{line}</Text>)}
      </Box>
    );
  }

  // The order of computation played: each window lights up in turn (about 6 s in all)
  const order = useMemo(() => [...stairs.steps].sort((a, b) => a.window.order - b.window.order).map((step) => step.index), [stairs]);
  const [playing, setPlaying] = useState<number | null>(null);
  useEffect(() => {
    if (playing === null) return;
    const delay = Math.min(350, Math.max(45, 6000 / order.length));
    const next = window.setTimeout(() => setPlaying(playing + 1 < order.length ? playing + 1 : null), playing + 1 < order.length ? delay : 900);
    return () => window.clearTimeout(next);
  }, [playing, order]);
  useEffect(() => setPlaying(null), [stairs]);
  if (playing !== null) {
    const step = stairs.steps[order[playing]];
    const [shape] = slabs([{ key: "play", index: step.index, h0: step.x0, h1: step.x1 }], drawn(range, stairs.typical), geometry);
    if (shape) {
      overlay = (
        <g pointerEvents="none">
          <g key={`play:${playing}`} className="ows-stair-lift">
            {shape.pieces.map((piece, n) => <path key={n} d={piece.top} fill="var(--mantine-primary-color-filled)" fillOpacity={0.55} stroke="var(--mantine-color-text)" strokeOpacity={0.8} strokeWidth={1.3} strokeLinejoin="round" />)}
          </g>
          <text className="ows-stair-label" x={shape.anchor[0]} y={shape.anchor[1] - 16} fontSize={12} fontWeight={650} textAnchor="middle" fill="var(--mantine-color-text)" stroke="var(--mantine-color-body)" strokeWidth={4} strokeLinejoin="round" paintOrder="stroke">{t("order", { n: playing + 1, total: order.length })}</text>
        </g>
      );
    }
  }

  const zoomed = range.t1 - range.t0 < limits.span - 1e-6;
  // The part seen, in words: its dates above, its month or year in the centre of the spiral
  const at = (hours: number) => new Date(stairs.origin + hours * HOUR);
  const from = at(Math.max(range.t0, stairs.spinUp));
  const to = at(range.t1);
  const day = new Intl.DateTimeFormat(lang, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  const seenText = `${day.format(from)} → ${day.format(to)}`;
  const middle = at((range.t0 + range.t1) / 2);
  const days = (range.t1 - range.t0) / 24;
  const centre = days > 200
    ? (from.getUTCFullYear() === new Date(to.getTime() - 1).getUTCFullYear() ? String(from.getUTCFullYear()) : `${from.getUTCFullYear()} – ${new Date(to.getTime() - 1).getUTCFullYear()}`)
    : days > 20
      ? new Intl.DateTimeFormat(lang, { month: "long", year: "numeric", timeZone: "UTC" }).format(middle)
      : `${new Intl.DateTimeFormat(lang, { day: "numeric", month: "short", timeZone: "UTC" }).format(from)} – ${new Intl.DateTimeFormat(lang, { day: "numeric", month: "short", timeZone: "UTC" }).format(to)}`;
  const centreText = (
    <>
      <text className="ows-stair-centre" key={centre} x={geometry.cx} y={geometry.cy - geometry.rise * 0.42} textAnchor="middle" dominantBaseline="middle" fontSize={centre.length > 12 ? 17 : 22} fontWeight={650} fill="var(--ows-muted)" fillOpacity={0.55}>{centre}</text>
      <Staircase stairs={stairs} range={range} geometry={geometry} hatch={hatch} intro={intro} />
    </>
  );
  return (
    <Stack gap="sm" className="ows-stairs-frame">
      <Group justify="space-between" wrap="nowrap" gap="sm" mih={28}>
        <Text size="sm" fw={600} className="ows-num" aria-live="polite">{seenText}</Text>
        <Group gap="xs" wrap="nowrap">
          {zoomed && <Button size="compact-xs" variant="subtle" leftSection={<IconArrowsMaximize size={13} />} onClick={() => nav.animateTo(whole(limits))}>{t("whole")}</Button>}
          {stairs.count > 1 && (
            <Tooltip label={t(playing === null ? "play" : "stop")} withArrow>
              <ActionIcon variant="default" size="sm" aria-label={t(playing === null ? "play" : "stop")} onClick={() => setPlaying(playing === null ? 0 : null)}>
                {playing === null ? <IconPlayerPlay size={13} /> : <IconPlayerStop size={13} />}
              </ActionIcon>
            </Tooltip>
          )}
          {nav.canZoom && (
            <ActionIcon.Group>
              <ActionIcon variant="default" size="sm" aria-label={t("zoomOut")} onClick={() => nav.zoomBy(1 / 1.8)} disabled={!zoomed}><IconMinus size={14} /></ActionIcon>
              <ActionIcon variant="default" size="sm" aria-label={t("zoomIn")} onClick={() => nav.zoomBy(1.8)} disabled={range.t1 - range.t0 <= limits.shortest + 1e-6}><IconPlus size={14} /></ActionIcon>
            </ActionIcon.Group>
          )}
        </Group>
      </Group>
      <Box ref={box} style={{ position: "relative", width: "100%", height: HEIGHT }}>
        {width > 0 && (
          <svg
            ref={setSvg}
            width={width}
            height={HEIGHT}
            role="img"
            aria-label={t("label", { start: f.dateTime(plan.start), end: f.dateTime(plan.end) })}
            tabIndex={0}
            onKeyDown={nav.onKeyDown}
            onPointerMove={move}
            onPointerLeave={() => setHover(null)}
            className="ows-stairs"
            style={{ display: "block", cursor: nav.canZoom ? "grab" : "default", touchAction: "none", outline: "none", overflow: "hidden" }}
          >
            <defs>
              <pattern id={hatch} width={4} height={4} patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                <rect width={4} height={4} fill="var(--ows-canvas)" />
                <line x1={0} y1={0} x2={0} y2={4} stroke="var(--ows-muted)" strokeWidth={1.7} strokeOpacity={0.9} />
              </pattern>
            </defs>
            {centreText}
            {overlay}
          </svg>
        )}
        {tip}
      </Box>
      {nav.canZoom && <PeriodBar stairs={stairs} range={range} limits={limits} onJump={nav.jumpTo} onMove={(to) => nav.animateTo(to, 360)} label={t("seen")} />}
    </Stack>
  );
}
