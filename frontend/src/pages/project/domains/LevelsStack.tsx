/**
 * The model levels of the first kilometre as sheets over the domains, at true heights on the ruler,
 * those crossed by a rotor in orange, each turbine model at its hub height and diameter. A click
 * spreads them evenly and tilts the view (another restores them; zoomed, the wheel spreads
 * further); the whole column stays in view.
 */
import { Box, Group, Text } from "@mantine/core";
import { IconChartArea } from "@tabler/icons-react";
import { motion } from "motion/react";
import { type CSSProperties, type KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";

import type { Case } from "../../../api/types";
import { defineMessages, useFormat, useT } from "../../../i18n";
import { SPRING, watchVisible } from "../../../motion";
import { Fold } from "../../../ui/Fold";
import { QueryView } from "../../../ui/States";
import { ToolBar, ToolGroup, ToolToggle } from "../../../ui/ToolBar";
import { useVertical, type VerticalAnswer } from "./VerticalLevels";

const messages = defineMessages({
  en: { title: "Levels in 3D", curtain: "Curtain", tools: "Levels in 3D", zoom: "Zoom on the levels (click, wheel)", zoomed: "Zoom", none: "No level below 1 km" },
  fr: { title: "Niveaux en 3D", curtain: "Rideau", tools: "Niveaux en 3D", zoom: "Zoom sur les niveaux (clic, molette)", zoomed: "Zoom", none: "Aucun niveau sous 1 km" },
});

const CEILING = 1000;
/** Size of the ground sheet's longer side and height of the column (spread or not), in CSS pixels */
const SIDE = 310, TALL = 300;
/** Heights marked on the ruler, in metres */
const RULER = [0, 250, 500, 750, 1000];
/** How far the wheel spreads the sheets: up to this many times the height of the column */
const STRETCH_MAX = 2;

/* ------------------------------------------------------------------------------------ framing */
/** The camera (degrees): at rest, under the pointer, spread (it looks more from the side as the
    wheel spreads the sheets further, up to TILT more). */
const CAMERA = { rest: { x: 58, z: -36 }, hover: { x: 55, z: -31 }, spread: { x: 67, z: -42 } } as const;
const TILT = 6;
/** Distance of the eye (the CSS perspective), the room kept around the drawing, and the room taken
    by a height written beside the column (its text keeps its size whatever the framing), in pixels. */
const EYE = 1600, MARGIN = 26, LABEL = 66, LINE = 9;

type Point = readonly [number, number, number];

/** Where a point of the stage (from its centre, z up) lands in the view, from its centre. */
function onScreen([x, y, z]: Point, camera: { x: number; z: number }, scale: number): [number, number] {
  const az = (camera.z * Math.PI) / 180, ax = (camera.x * Math.PI) / 180;
  const x1 = x * Math.cos(az) - y * Math.sin(az), y1 = x * Math.sin(az) + y * Math.cos(az);
  const y2 = y1 * Math.cos(ax) - z * Math.sin(ax), z2 = y1 * Math.sin(ax) + z * Math.cos(ax);
  const eye = EYE / (EYE - z2 * scale);
  return [x1 * scale * eye, y2 * scale * eye];
}

/** The scale and the shift that keep every point, with the room of its label, inside the view. */
function frame(points: readonly { at: Point; left?: number; right?: number }[], camera: { x: number; z: number }, width: number, height: number) {
  if (width <= 0 || height <= 0) return { scale: 1, x: 0, y: 0 };
  const bounds = (scale: number) => {
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (const point of points) {
      const [x, y] = onScreen(point.at, camera, scale);
      x0 = Math.min(x0, x - (point.left ?? 0));
      x1 = Math.max(x1, x + (point.right ?? 0));
      y0 = Math.min(y0, y - LINE);
      y1 = Math.max(y1, y + LINE);
    }
    return { x0, x1, y0, y1 };
  };
  // The labels keep their size (their room does not scale): the scale that fits is found in a few steps
  const labels = Math.max(...points.map((point) => (point.left ?? 0) + (point.right ?? 0)));
  const room = (size: number, used: number, fixed: number) => (size - 2 * MARGIN - fixed) / Math.max(1, used - fixed);
  let scale = 1;
  for (let pass = 0; pass < 5; pass++) {
    const box = bounds(scale);
    scale = Math.max(0.2, Math.min(1.2, scale * Math.min(room(width, box.x1 - box.x0, labels), room(height, box.y1 - box.y0, 2 * LINE))));
  }
  const box = bounds(scale);
  return { scale, x: -(box.x0 + box.x1) / 2, y: -(box.y0 + box.y1) / 2 };
}

interface Rect { x: number; y: number; w: number; h: number }

/** Footprints of the domains, as shares of the outer one (0 to 1, y downwards from the north). */
function footprints(draft: Case): Rect[] {
  const domains = draft.grid.domains;
  const rects: Rect[] = [];
  domains.forEach((d, k) => {
    if (k === 0) return void rects.push({ x: 0, y: 0, w: 1, h: 1 });
    const parent = rects[d.parent_id - 1] ?? rects[0];
    const p = domains[d.parent_id - 1] ?? domains[0];
    const w = ((d.e_we - 1) / d.parent_grid_ratio / Math.max(1, p.e_we - 1)) * parent.w;
    const h = ((d.e_sn - 1) / d.parent_grid_ratio / Math.max(1, p.e_sn - 1)) * parent.h;
    const x = parent.x + ((d.i_parent_start - 1) / Math.max(1, p.e_we - 1)) * parent.w;
    const y = parent.y + parent.h - ((d.j_parent_start - 1) / Math.max(1, p.e_sn - 1)) * parent.h - h;
    rects.push({ x, y, w, h });
  });
  return rects;
}

function Stack3D({ data, draft }: { data: VerticalAnswer; draft: Case }) {
  const t = useT(messages);
  const f = useFormat();
  const [spread, setSpread] = useState(false);
  const [stretch, setStretch] = useState(1);
  const [hovered, setHovered] = useState(false);
  const [curtain, setCurtain] = useState(true);
  // What moved last: a click (the sheets go one after the other) or the wheel (all together, at once)
  const [cause, setCause] = useState<"click" | "wheel">("click");
  // The size of the view (to frame the column in it); the curtain sweeps only while it is on screen
  const [scene, setScene] = useState<HTMLDivElement | null>(null);
  const [view, setView] = useState({ width: 0, height: 0 });
  const [visible, setVisible] = useState(true);
  const [settled, setSettled] = useState(false);
  const measured = view.width > 0;
  useEffect(() => {
    if (!measured) return;
    const timer = window.setTimeout(() => setSettled(true), 80);
    return () => window.clearTimeout(timer);
  }, [measured]);
  useEffect(() => {
    if (!scene) return;
    const sizes = new ResizeObserver(([entry]) => setView({ width: entry.contentRect.width, height: entry.contentRect.height }));
    sizes.observe(scene);
    const stop = watchVisible(scene, setVisible);
    return () => {
      sizes.disconnect();
      stop();
    };
  }, [scene]);
  // The sheets rise one after the other when shown, then move together
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const timer = window.setTimeout(() => setShown(true), 1400);
    return () => window.clearTimeout(timer);
  }, []);
  const outer = draft.grid.domains[0];
  const aspect = outer ? (outer.e_sn - 1) / Math.max(1, outer.e_we - 1) : 1;
  const width = aspect <= 1 ? SIDE : SIDE / aspect, depth = aspect <= 1 ? SIDE * aspect : SIDE;
  const cells = Math.max(4, Math.min(48, (outer?.e_we ?? 40) - 1));
  const rects = useMemo(() => footprints(draft), [draft]);
  const levels = data.levels.filter((level) => level.height_m <= CEILING);
  const rotors = data.turbines.map((turbine) => ({ ...turbine, low: turbine.hub_height_m - turbine.rotor_diameter_m / 2, high: turbine.hub_height_m + turbine.rotor_diameter_m / 2 }));
  const crossed = (n: number) => {
    const low = levels[n].height_m, high = levels[n + 1]?.height_m ?? low;
    return rotors.some((r) => (low <= r.high && high >= r.low) || (low >= r.low && low <= r.high));
  };
  // Where a height sits: true heights, or the levels spread evenly (heights between two levels in
  // proportion) over a column the wheel makes taller
  const top = spread ? TALL * stretch : TALL;
  const gap = top / Math.max(1, levels.length - 1);
  const zOf = (height: number) => {
    if (!spread) return (Math.min(height, CEILING) / CEILING) * TALL;
    for (let n = 0; n < levels.length - 1; n++) {
      const a = levels[n].height_m, b = levels[n + 1].height_m;
      if (height <= b) return (n + Math.max(0, (height - a) / Math.max(1e-6, b - a))) * gap;
    }
    return (levels.length - 1) * gap;
  };

  // The camera frames the whole column (the ruler or the heights written beside it included)
  const camera = spread ? { x: CAMERA.spread.x + (TILT * (stretch - 1)) / (STRETCH_MAX - 1), z: CAMERA.spread.z } : hovered ? CAMERA.hover : CAMERA.rest;
  const fit = useMemo(() => {
    const hw = width / 2, hd = depth / 2;
    const corners = [-hw, hw].flatMap((x) => [-hd, hd].flatMap((y) => [{ at: [x, y, 0] as const }, { at: [x, y, top + 20] as const }]));
    const marks = spread ? [] : RULER.map((height) => ({ at: [-hw, -hd, (height / CEILING) * TALL] as const, left: LABEL }));
    const labels = spread ? [{ at: [hw, hd, 0] as const, right: LABEL }, { at: [hw, hd, top] as const, right: LABEL }] : [];
    return frame([...corners, ...marks, ...labels], camera, view.width, view.height);
  }, [width, depth, top, spread, camera.x, camera.z, view]);

  // Once spread, the wheel spreads further (up) or back (down); at either end the page scrolls as usual
  const stretched = useRef(stretch);
  const stretchTo = (next: number) => {
    const value = Math.min(STRETCH_MAX, Math.max(1, next));
    if (Math.abs(value - stretched.current) < 1e-3) return false;
    stretched.current = value;
    setCause("wheel");
    setStretch(value);
    return true;
  };
  useEffect(() => {
    if (!scene || !spread) return;
    const wheel = (event: WheelEvent) => {
      const delta = event.deltaMode === 1 ? event.deltaY * 33 : event.deltaY;
      const value = Math.min(STRETCH_MAX, Math.max(1, stretched.current * Math.exp(-delta * 0.0015)));
      if (Math.abs(value - stretched.current) < 1e-3) return;
      event.preventDefault();
      stretched.current = value;
      setCause("wheel");
      setStretch(value);
    };
    scene.addEventListener("wheel", wheel, { passive: false });
    return () => scene.removeEventListener("wheel", wheel);
  }, [spread, scene]);
  const toggle = () => {
    setCause("click");
    if (spread) {
      stretched.current = 1;
      setStretch(1);
    }
    setSpread(!spread);
  };
  const onKey = (event: KeyboardEvent) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      toggle();
    } else if (spread && (event.key === "ArrowUp" || event.key === "ArrowDown")) {
      event.preventDefault();
      stretchTo(stretch * (event.key === "ArrowUp" ? 1.2 : 1 / 1.2));
    }
  };
  // Low to high as on the curtain; orange where a rotor crosses
  const colour = (n: number) => crossed(n) ? "var(--ows-stack-rotor)" : `color-mix(in srgb, var(--ows-stack-low) ${Math.round((1 - n / Math.max(1, levels.length - 1)) * 100)}%, var(--ows-stack-high))`;
  // The turbines along the middle of the innermost domain, one per model
  const inner = rects[rects.length - 1] ?? { x: 0, y: 0, w: 1, h: 1 };

  if (!levels.length) return <Text size="sm" c="dimmed">{t("none")}</Text>;
  const delay = (n: number) => (!shown ? 0.15 + n * 0.035 : cause === "wheel" ? 0 : spread ? n * 0.018 : (levels.length - n) * 0.012);
  return (
    <Box pos="relative">
      <Group justify="flex-end" mb={4}>
        <ToolBar label={t("tools")}>
          <ToolGroup>
            <ToolToggle icon={IconChartArea} label={t("curtain")} active={curtain} onChange={setCurtain} />
          </ToolGroup>
        </ToolBar>
      </Group>
      <div ref={setScene} className="ows-stack3d" role="button" tabIndex={0} aria-pressed={spread} aria-label={t("zoom")} onClick={toggle} onKeyDown={onKey}
        onPointerEnter={() => setHovered(true)} onPointerLeave={() => setHovered(false)}
        data-spread={spread || undefined} data-wheel={cause === "wheel" || undefined} data-paused={!visible || undefined} data-settled={settled || undefined}
        style={{ "--cam-x": `${camera.x}deg`, "--cam-z": `${camera.z}deg`, "--fit": fit.scale, "--fit-x": `${fit.x}px`, "--fit-y": `${fit.y}px` } as CSSProperties}>
        <div className="ows-stack3d-camera">
          <div className="ows-stack3d-stage" style={{ width, height: depth }}>
            {/* The ground: the footprint of the domains */}
            <div className="ows-stack3d-ground" style={{ backgroundSize: `${width / cells}px ${width / cells}px` }}>
              {rects.map((r, k) => (
                <span key={k} className="ows-stack3d-domain" data-outer={k === 0 || undefined} style={{ left: `${r.x * 100}%`, top: `${r.y * 100}%`, width: `${r.w * 100}%`, height: `${r.h * 100}%` }} />
              ))}
            </div>
            {/* The ruler: true heights at the back corner, while the sheets stand at them */}
            {RULER.map((height) => (
              <motion.div key={height} className="ows-stack3d-mark" initial={{ z: 0, opacity: 0 }} animate={{ z: zOf(height), opacity: spread ? 0 : 1 }} transition={{ ...SPRING.soft, delay: shown ? 0 : 0.2 + height / 2500 }}>
                <span className="ows-stack3d-face ows-num">{height ? `${f.number(height, 0)} m` : "0"}</span>
              </motion.div>
            ))}
            {levels.map((level, n) => (
              <motion.div
                key={level.number}
                className="ows-stack3d-sheet"
                data-rotor={crossed(n) || undefined}
                data-odd={n % 2 || undefined}
                initial={{ z: 0, opacity: 0 }}
                animate={{ z: zOf(level.height_m), opacity: 1 }}
                transition={{ ...SPRING.soft, delay: delay(n) }}
                style={{ "--sheet": colour(n) } as CSSProperties}
              >
                <motion.span className="ows-stack3d-label ows-num" initial={false} animate={{ opacity: spread ? 1 : 0, x: spread ? 0 : -6 }} transition={{ duration: 0.3, delay: spread ? 0.25 + n * 0.015 : 0 }}>
                  <span className="ows-stack3d-face">{f.number(level.height_m, level.height_m < 100 ? 1 : 0)} m</span>
                </motion.span>
              </motion.div>
            ))}
            {/* The curtain: the layers on a vertical cut through the middle, rotor layers in orange */}
            {curtain && (
              <div className="ows-stack3d-plane ows-stack3d-sweep" style={{ left: 0, width, height: top + 20, top: depth / 2 - (top + 20), "--half": `${depth / 2}px` } as CSSProperties}>
                <svg width={width} height={top + 20} className="ows-stack3d-curtain">
                  {levels.slice(0, -1).map((level, n) => {
                    const z0 = zOf(level.height_m), z1 = zOf(levels[n + 1].height_m);
                    const share = n / Math.max(1, levels.length - 2);
                    return (
                      <motion.rect key={level.number} x={0} width={width} initial={false} animate={{ y: top + 20 - z1, height: Math.max(0.5, z1 - z0) }} transition={SPRING.soft}
                        fill={crossed(n) ? "var(--ows-stack-rotor)" : `color-mix(in srgb, var(--ows-stack-low) ${Math.round((1 - share) * 100)}%, var(--ows-stack-high))`} fillOpacity={n % 2 ? 0.34 : 0.22} />
                    );
                  })}
                </svg>
              </div>
            )}
            {/* The turbines: tower to the hub, rotor of its true diameter */}
            {rotors.map((r, k) => {
              const x = (inner.x + inner.w * ((k + 1) / (rotors.length + 1))) * width;
              const y = (inner.y + inner.h / 2) * depth;
              const hub = zOf(r.hub_height_m), low = zOf(r.low), high = zOf(r.high);
              const half = (r.rotor_diameter_m / CEILING) * TALL / 2;
              const tall = top + 20, cx = half + 2;
              // Blades of the true length, stretched up and down with the layers they cross
              const tip = (degrees: number) => {
                const a = (degrees * Math.PI) / 180, s = Math.sin(a);
                return { x2: cx + half * Math.cos(a), y2: tall - hub - (s >= 0 ? s * (high - hub) : s * (hub - low)) };
              };
              return (
                <div key={r.type} className="ows-stack3d-plane" style={{ left: x - cx, top: y - tall, width: cx * 2, height: tall }}>
                  <svg width={cx * 2} height={tall} className="ows-stack3d-turbine">
                    <title>{`${r.name} · ${f.number(r.hub_height_m, 0)} m · ${f.number(r.rotor_diameter_m, 0)} m`}</title>
                    <motion.line x1={cx} x2={cx} y1={tall} initial={{ y2: tall }} animate={{ y2: tall - hub }} transition={{ ...SPRING.soft, delay: shown ? 0 : 0.5 }} strokeWidth={2.4} strokeLinecap="round" className="ows-stack3d-tower" />
                    {[90, 210, 330].map((angle) => (
                      <motion.line key={angle} x1={cx} initial={{ y1: tall, x2: cx, y2: tall }} animate={{ y1: tall - hub, ...tip(angle) }} transition={{ ...SPRING.soft, delay: shown ? 0 : 0.5 }} strokeWidth={1.8} strokeLinecap="round" className="ows-stack3d-blade" />
                    ))}
                    <motion.circle cx={cx} r={2.8} initial={{ cy: tall }} animate={{ cy: tall - hub }} transition={{ ...SPRING.soft, delay: shown ? 0 : 0.5 }} className="ows-stack3d-hub" />
                  </svg>
                </div>
              );
            })}
          </div>
        </div>
        <span className="ows-stack3d-note" aria-hidden={!spread}>{t("zoomed")}</span>
      </div>
    </Box>
  );
}

export function LevelsStack({ draft }: { draft: Case }) {
  const t = useT(messages);
  if (!draft.grid.domains.length) return null;
  return (
    <Fold title={t("title")} lazy>
      <Content draft={draft} />
    </Fold>
  );
}

function Content({ draft }: { draft: Case }) {
  const vertical = useVertical(draft);
  return <QueryView query={vertical}>{(data) => (data.error ? null : <Stack3D data={data} draft={draft} />)}</QueryView>;
}
