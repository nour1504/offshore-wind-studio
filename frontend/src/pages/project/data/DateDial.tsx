/**
 * A date field with a dial: a click zooms into four rings (years, months, days, hours). The ring in
 * front (vertical drag, wheel away from it, click, ↑↓ or the buttons below) turns under the needle:
 * wheel, sideways drag, click on a value, ←→ (Shift: ten years). ✓ or Enter keeps the date, ✕ or
 * Escape leaves it.
 */
import { ActionIcon, SegmentedControl, TextInput, Tooltip } from "@mantine/core";
import { IconCheck, IconX } from "@tabler/icons-react";
import { animate, type MotionValue, useMotionValue, useReducedMotion } from "motion/react";
import { type CSSProperties, Fragment, type KeyboardEvent, memo, type PointerEvent, type ReactNode, type SyntheticEvent, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { defineMessages, parseUtc, useLang, useT } from "../../../i18n";
import { clamp, EASE_OUT_POINTS, smoothstep } from "../../../motion";

const messages = defineMessages({
  en: { open: "Choose on the dial", keep: "Keep this date", leave: "Leave unchanged", rings: { year: "Year", month: "Month", day: "Day", hour: "Hour" } },
  fr: { open: "Choisir sur le cadran", keep: "Garder cette date", leave: "Ne pas changer", rings: { year: "Année", month: "Mois", day: "Jour", hour: "Heure" } },
});

const YEAR0 = 1940;
const pad = (n: number) => String(n).padStart(2, "0");
const daysIn = (y: number, m: number) => new Date(Date.UTC(y, m + 1, 0)).getUTCDate();
const mod = (a: number, n: number) => ((a % n) + n) % n;

interface Parts { y: number; mo: number; d: number; h: number; mi: number }
type RingId = "year" | "month" | "day" | "hour";
const ORDER: RingId[] = ["year", "month", "day", "hour"];
const LAST = ORDER.length - 1;
/** Space between two values along each ring, in pixels */
const SPACING: Record<RingId, number> = { year: 42, month: 100, day: 50, hour: 56 };
/** Where the name of each ring stands on its arc, from the left edge, in pixels */
const NAME_X = 56;
/**
 * Pixels from each arc, outwards: the foot of its row of values (`LIFT`); the needle under the chosen
 * value, from just above the arc (`NEEDLE_TOP`) down past the ticks (`NEEDLE_FOOT`), so that nothing
 * crosses a value; the middle of the ring's band, for the pointer (`MIDDLE`).
 */
const LIFT = 28, NEEDLE_TOP = 8, NEEDLE_FOOT = 34, MIDDLE = 4;
const SPRING = { type: "spring", stiffness: 320, damping: 34 } as const;
const FRONT_SPRING = { type: "spring", stiffness: 200, damping: 28 } as const;

const toParts = (value: string): Parts | null => {
  const t = parseUtc(value);
  return Number.isFinite(t.getTime()) ? { y: t.getUTCFullYear(), mo: t.getUTCMonth(), d: t.getUTCDate(), h: t.getUTCHours(), mi: t.getUTCMinutes() } : null;
};
const write = (p: Parts) => `${p.y}-${pad(p.mo + 1)}-${pad(p.d)}T${pad(p.h)}:${pad(p.mi)}:00`;
const toInput = (value: string) => { const p = toParts(value); return p ? write(p).slice(0, 16) : value.slice(0, 16); };
const lastYear = () => new Date().getUTCFullYear() + 2;

/** The date at these ring positions (months, days and hours go round; years stop at both ends). */
function partsAt(pos: Record<RingId, number>, mi: number): Parts {
  const y = YEAR0 + clamp(Math.round(pos.year), 0, lastYear() - YEAR0);
  const mo = mod(Math.round(pos.month), 12);
  return { y, mo, d: mod(Math.round(pos.day), daysIn(y, mo)) + 1, h: mod(Math.round(pos.hour), 24), mi };
}

/**
 * The rings, wide apart (`gap`), drawn with the year ring on the line `front` (centre `cy`): bringing
 * another ring to the front slides them all up by `gap` a ring, as a transform (see `paint`).
 */
interface Geometry { cx: number; cy: number; gap: number; radius: Record<RingId, number>; front: number; width: number; height: number }
function geometry(width: number, height: number): Geometry {
  const outer = Math.max(width * 1.5, 1250);
  const gap = clamp(height * 0.26, 160, 260);
  const front = Math.max(190, height * 0.42);
  return {
    cx: width / 2,
    cy: front + outer,
    gap,
    radius: { year: outer, month: outer - gap, day: outer - gap * 2, hour: outer - gap * 3 },
    front,
    width,
    height,
  };
}

/** The dial's own presses and clicks stay in it (it is portalled from inside the field) */
const keepInside = (event: SyntheticEvent) => event.stopPropagation();

interface RingProps {
  id: RingId; name: string; radius: number; value: number; count: number; months: string[];
  cx: number; cy: number; width: number; hoverX: number | null;
  register: (id: RingId, node: SVGGElement | null) => void;
}
/**
 * One ring: its arc, the values in view upright at their angle, the needle and the ring's name.
 * Redrawn only when it turns, when the pointer moves over it or when the size changes; its place,
 * dimming and closeness (`--near`) are set by the dial's `paint`.
 */
const Ring = memo(function Ring({ id, name, radius, value, count, months, cx, cy, width, hoverX, register }: RingProps) {
  const own = useCallback((node: SVGGElement | null) => register(id, node), [id, register]);
  const spacing = SPACING[id];
  const point = (theta: number, r: number) => [cx + r * Math.sin(theta), cy - r * Math.cos(theta)] as const;
  const half = Math.asin(Math.min(1, (width / 2 + 80) / radius));
  const reach = Math.ceil((half * radius) / spacing) + 1;
  const centre = Math.round(value);
  // Values fade out towards both edges: the names stand clear on the left
  const fadeIn = Math.min(150, width * 0.1), fadeOut = Math.min(300, width * 0.2);
  const items: ReactNode[] = [];
  for (let i = centre - reach; i <= centre + reach; i++) {
    if (id === "year" && (i < 0 || i >= count)) continue;
    const theta = ((i - value) * spacing) / radius;
    const [x, y] = point(theta, radius);
    const edge = clamp((Math.min(x, width - x) - fadeIn) / (fadeOut - fadeIn), 0, 1);
    if (edge <= 0) continue;
    const v = id === "year" ? i : mod(i, count);
    const near = hoverX === null ? 0 : Math.max(0, 1 - Math.abs(x - hoverX) / 120);
    // How much this is the chosen value: 1 under the needle, 0 a value away, in between while turning
    const chosen = Math.max(0, 1 - Math.abs(i - value));
    const major = id === "year" ? (YEAR0 + v) % 5 === 0 : id === "day" ? v === 0 || (v + 1) % 5 === 0 : id === "hour" ? v % 6 === 0 : true;
    // Years named every five, never touching the chosen one, which is always named
    const shown = id === "year" ? Math.max(chosen, major ? smoothstep(0, 1, (Math.abs(i - value) - 1) / 0.6) : 0) : 1;
    const tick = major ? 15 : 8;
    const [x2, y2] = point(theta, radius - (tick + (26 - tick) * chosen + near * 10));
    const [lx, ly] = point(theta, radius + LIFT + near * 4);
    const look = { "--c": chosen } as CSSProperties;
    items.push(
      <g key={i}>
        <line x1={x} y1={y} x2={x2} y2={y2} className="ows-dial-tick" data-major={major || undefined} style={look} strokeOpacity={edge} vectorEffect="non-scaling-stroke" />
        {shown > 0 && (
          <text x={lx} y={ly} className="ows-dial-label ows-num" data-major={major || undefined} style={look} fillOpacity={edge * shown} textAnchor="middle">
            {id === "year" ? String(YEAR0 + v) : id === "month" ? months[v] : pad(id === "day" ? v + 1 : v)}
          </text>
        )}
      </g>,
    );
  }
  // The name on top of the arc, along it, on the row of the values
  const tilt = Math.asin(clamp((NAME_X - cx) / radius, -1, 1));
  const [nx, ny] = point(tilt, radius + LIFT);
  const top = cy - radius;
  return (
    <g ref={own} className="ows-dial-ring">
      <circle cx={cx} cy={cy} r={radius} className="ows-dial-track" vectorEffect="non-scaling-stroke" />
      {items}
      <line x1={cx} x2={cx} y1={top - NEEDLE_TOP} y2={top + NEEDLE_FOOT} className="ows-dial-needle" vectorEffect="non-scaling-stroke" />
      <circle cx={cx} cy={top - NEEDLE_TOP} className="ows-dial-bead" />
      <text x={nx} y={ny} transform={`rotate(${(tilt * 180) / Math.PI} ${nx} ${ny})`} className="ows-dial-name">{name}</text>
    </g>
  );
});

function Dial({ value, from, onKeep, onLeave }: { value: Parts; from: DOMRect | null; onKeep: (p: Parts) => void; onLeave: () => void }) {
  const t = useT(messages);
  const { lang } = useLang();
  const reduced = useReducedMotion();
  const locale = lang === "fr" ? "fr-FR" : "en-GB";
  const months = useMemo(() => {
    const format = new Intl.DateTimeFormat(locale, { month: "short", timeZone: "UTC" });
    return Array.from({ length: 12 }, (_, m) => format.format(new Date(Date.UTC(2001, m, 1))).replace(".", ""));
  }, [locale]);
  const monthsLong = useMemo(() => {
    const format = new Intl.DateTimeFormat(locale, { month: "long", timeZone: "UTC" });
    return Array.from({ length: 12 }, (_, m) => format.format(new Date(Date.UTC(2001, m, 1))));
  }, [locale]);
  const dayFormat = useMemo(() => new Intl.DateTimeFormat(locale, { weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "UTC" }), [locale]);

  const [size, setSize] = useState(() => ({ width: window.innerWidth, height: window.innerHeight }));
  useEffect(() => {
    const onResize = () => setSize({ width: window.innerWidth, height: window.innerHeight });
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);
  const g = useMemo(() => geometry(size.width, size.height), [size]);

  // The ring in front, and the slide of the rings that brings it there
  const [active, setActive] = useState<RingId>("day");
  const activeNow = useRef<RingId>("day");
  const focus = useMotionValue(ORDER.indexOf("day"));
  const choose = (id: RingId) => {
    if (activeNow.current === id) return;
    activeNow.current = id;
    setActive(id);
  };
  const bring = (id: RingId, velocity = 0) => {
    choose(id);
    const target = ORDER.indexOf(id);
    if (reduced) focus.set(target);
    else animate(focus, target, { ...FRONT_SPRING, velocity });
  };

  // Where each ring stands (a value per unit, fractions while it moves)
  const values: Record<RingId, MotionValue<number>> = {
    year: useMotionValue(value.y - YEAR0),
    month: useMotionValue(value.mo),
    day: useMotionValue(value.d - 1),
    hour: useMotionValue(value.h),
  };
  const read = () => ({ year: values.year.get(), month: values.month.get(), day: values.day.get(), hour: values.hour.get() });
  const [pos, setPos] = useState(read);
  useEffect(() => {
    let frame = 0;
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(() => { frame = 0; setPos(read()); });
    };
    const offs = ORDER.map((id) => values[id].on("change", schedule));
    return () => { offs.forEach((off) => off()); cancelAnimationFrame(frame); };
    // The motion values live as long as the dial
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const parts = partsAt(pos, value.mi);

  // The zoom: from the small watch of the field to the rings across the screen, and back
  const zoom = useMotionValue(reduced ? 1 : 0);
  // Arrived: the watch's ticks are no longer drawn and the page behind needs no blur
  const [opened, setOpened] = useState(Boolean(reduced));
  useEffect(() => {
    if (reduced) return;
    let live = true;
    const run = animate(zoom, 1, { duration: 0.7, ease: EASE_OUT_POINTS });
    void run.then(() => { if (live) setOpened(true); });
    return () => { live = false; run.stop(); };
  }, [zoom, reduced]);
  const closing = useRef(false);
  const close = (then: () => void) => {
    if (closing.current) return;
    closing.current = true;
    if (reduced) return then();
    setOpened(false);
    void animate(zoom, 0, { duration: 0.42, ease: [0.7, 0, 0.84, 0] }).then(then);
  };
  const keep = () => close(() => onKeep(partsAt(read(), value.mi)));
  const leave = () => close(onLeave);

  // A ring under the pointer (not the one in front) comes up a little
  const [hover, setHover] = useState<{ ring: RingId; x: number } | null>(null);
  const lifts: Record<RingId, MotionValue<number>> = { year: useMotionValue(0), month: useMotionValue(0), day: useMotionValue(0), hour: useMotionValue(0) };
  const hovered = hover?.ring ?? null;
  useEffect(() => {
    for (const id of ORDER) {
      const target = id === hovered && id !== active ? 0.22 : 0;
      if (reduced) lifts[id].set(target);
      else if (lifts[id].get() !== target) animate(lifts[id], target, { duration: 0.16, ease: "linear" });
    }
    // The motion values live as long as the dial
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hovered, active, reduced]);
  const [held, setHeld] = useState<"x" | "y" | null>(null);

  /* Drawn without React at each image of the zoom, the slide and the lift: the transforms, the band
     of the front line, the dimming of each ring and how much it stands in front (`--near`) */
  const box = useRef<HTMLDivElement>(null);
  const svg = useRef<SVGSVGElement>(null);
  const zoomGroup = useRef<SVGGElement>(null), slideGroup = useRef<SVGGElement>(null), ghosts = useRef<SVGGElement>(null);
  const band = useRef<SVGCircleElement>(null), centre = useRef<HTMLDivElement>(null);
  const ringNodes = useRef<Partial<Record<RingId, SVGGElement | null>>>({});
  const register = useCallback((id: RingId, node: SVGGElement | null) => { ringNodes.current[id] = node; }, []);
  const paint = () => {
    const z = zoom.get(), f = focus.get();
    const detail = clamp((z - 0.55) / 0.45, 0, 1);
    const cy = g.cy - g.gap * f;
    // The zoom: scale and centre between the watch and the full rings
    const watch = from ? { x: from.left + from.width / 2, y: from.top + from.height / 2 } : { x: g.cx, y: g.front };
    const s0 = 10 / g.radius.year;
    const scale = Math.exp(Math.log(s0) * (1 - z));
    const w = (scale - s0) / (1 - s0);
    const ox = watch.x + (g.cx - watch.x) * w - g.cx * scale, oy = watch.y + (cy - watch.y) * w - cy * scale;
    zoomGroup.current?.setAttribute("transform", `translate(${ox} ${oy}) scale(${scale})`);
    slideGroup.current?.setAttribute("transform", `translate(0 ${-g.gap * f})`);
    ghosts.current?.setAttribute("opacity", String(Math.max(0, 1 - z * 1.25)));
    if (band.current) {
      band.current.setAttribute("cy", String(cy));
      band.current.setAttribute("r", String(Math.max(0, cy - g.front + MIDDLE)));
      band.current.setAttribute("opacity", String(detail));
    }
    ORDER.forEach((id, k) => {
      const node = ringNodes.current[id];
      if (!node) return;
      // Drawn back with the distance from the front
      const d = Math.abs(k - f);
      const dim = 1 - 0.58 * Math.min(1, d) - 0.28 * clamp(d - 1, 0, 1);
      node.setAttribute("opacity", String(detail * Math.min(1, dim + lifts[id].get())));
      node.style.setProperty("--near", String(1 - Math.min(1, d)));
    });
    box.current?.style.setProperty("--zoom", String(z));
    box.current?.style.setProperty("--detail", String(detail));
    if (centre.current) centre.current.style.opacity = String(detail);
  };
  const painter = useRef(paint);
  painter.current = paint;
  useLayoutEffect(() => painter.current());
  useEffect(() => {
    const repaint = () => painter.current();
    const offs = [zoom, focus, ...ORDER.map((id) => lifts[id])].map((motion) => motion.on("change", repaint));
    return () => offs.forEach((off) => off());
    // The motion values live as long as the dial
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => box.current?.focus(), []);

  const bound = (id: RingId, target: number) => (id === "year" ? clamp(target, 0, lastYear() - YEAR0) : target);
  const goTo = (id: RingId, target: number, velocity = 0) => {
    const end = bound(id, Math.round(target));
    if (reduced) values[id].set(end);
    else animate(values[id], end, { ...SPRING, velocity });
  };
  const step = (id: RingId, by: number) => goTo(id, Math.round(values[id].get()) + by);

  // Which ring is under a point, and the value there; and whether the point is on the front line
  const locate = (clientX: number, clientY: number) => {
    const cy = g.cy - g.gap * focus.get();
    const r = Math.hypot(clientX - g.cx, clientY - cy);
    const theta = Math.atan2(clientX - g.cx, cy - clientY);
    let ring: RingId | null = null;
    for (const id of ORDER) if (Math.abs(r - g.radius[id] - MIDDLE) <= g.gap / 2) ring = id;
    return { ring, theta, front: Math.abs(r - (cy - g.front) - MIDDLE) <= g.gap / 2 };
  };

  /* A press: sideways it turns a ring, up or down it slides the rings; without moving, it is a click */
  const drag = useRef<{ id: number; x: number; y: number; ring: RingId | null; axis: "x" | "y" | null; start: number; t: number; v: number } | null>(null);
  const down = (event: PointerEvent<SVGSVGElement>) => {
    if (event.button !== 0) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { id: event.pointerId, x: event.clientX, y: event.clientY, ring: locate(event.clientX, event.clientY).ring, axis: null, start: 0, t: performance.now(), v: 0 };
  };
  const over = (event: PointerEvent<SVGSVGElement>) => {
    const press = drag.current;
    if (press && press.id === event.pointerId) {
      const now = performance.now();
      if (!press.axis && Math.hypot(event.clientX - press.x, event.clientY - press.y) > 6) {
        press.axis = Math.abs(event.clientX - press.x) >= Math.abs(event.clientY - press.y) ? "x" : "y";
        press.x = event.clientX;
        press.y = event.clientY;
        press.t = now;
        if (press.axis === "x") {
          const id = press.ring ?? activeNow.current;
          press.ring = id;
          if (id !== activeNow.current) bring(id);
          values[id].stop();
          press.start = values[id].get();
        } else {
          focus.stop();
          press.start = focus.get();
        }
        setHeld(press.axis);
      }
      if (press.axis === "x" && press.ring) {
        const id = press.ring;
        const next = bound(id, press.start - (event.clientX - press.x) / SPACING[id]);
        press.v = press.v * 0.6 + ((next - values[id].get()) / Math.max(0.008, (now - press.t) / 1000)) * 0.4;
        press.t = now;
        values[id].set(next);
      } else if (press.axis === "y") {
        let next = press.start - (event.clientY - press.y) / g.gap;
        if (next < 0) next *= 0.3;
        else if (next > LAST) next = LAST + (next - LAST) * 0.3;
        press.v = press.v * 0.6 + ((next - focus.get()) / Math.max(0.008, (now - press.t) / 1000)) * 0.4;
        press.t = now;
        focus.set(next);
        choose(ORDER[clamp(Math.round(next), 0, LAST)]);
      }
    }
    const { ring } = locate(event.clientX, event.clientY);
    setHover(ring ? { ring, x: event.clientX } : null);
  };
  const up = (event: PointerEvent<SVGSVGElement>) => {
    const press = drag.current;
    if (!press || press.id !== event.pointerId) return;
    drag.current = null;
    setHeld(null);
    const fresh = performance.now() - press.t < 90 ? press.v : 0;
    if (press.axis === "x" && press.ring) {
      // Goes on a little, then settles on a value
      goTo(press.ring, values[press.ring].get() + clamp(fresh * 0.18, -12, 12), fresh);
    } else if (press.axis === "y") {
      bring(ORDER[clamp(Math.round(focus.get() + clamp(fresh * 0.12, -1, 1)), 0, LAST)], fresh);
    } else if (event.type === "pointerup") {
      // A click: another ring comes to the front; on the ring in front, the value clicked
      const { ring, theta } = locate(event.clientX, event.clientY);
      if (!ring) return;
      if (ring !== activeNow.current) bring(ring);
      else goTo(ring, values[ring].get() + (theta * g.radius[ring]) / SPACING[ring]);
    }
  };
  // The wheel (one listener for the dial's life: its settling survives the images drawn meanwhile)
  const settle = useRef(0);
  const onWheel = (event: WheelEvent) => {
    event.preventDefault();
    const delta = event.deltaMode === 1 ? event.deltaY * 40 : event.deltaMode === 2 ? event.deltaY * 400 : event.deltaY;
    const sideways = Math.abs(event.deltaX) > Math.abs(delta) ? event.deltaX : 0;
    window.clearTimeout(settle.current);
    if (!sideways && !locate(event.clientX, event.clientY).front) {
      // Away from the ring in front: from ring to ring (a notch, one ring; a touchpad, smoothly)
      if (Math.abs(delta) >= 50) bring(ORDER[clamp(ORDER.indexOf(activeNow.current) + Math.sign(delta), 0, LAST)]);
      else {
        focus.stop();
        const next = clamp(focus.get() + delta / g.gap, 0, LAST);
        focus.set(next);
        choose(ORDER[Math.round(next)]);
        settle.current = window.setTimeout(() => bring(ORDER[Math.round(focus.get())]), 140);
      }
      return;
    }
    const id = activeNow.current, across = sideways || delta;
    if (Math.abs(across) >= 50) {
      // A notch: one value
      const now = values[id].get();
      const target = (values[id].isAnimating() ? Math.round(now + Math.sign(values[id].getVelocity()) * 0.5) : Math.round(now)) + Math.sign(across);
      goTo(id, target);
    } else {
      // A touchpad: smoothly, then on the nearest value
      values[id].stop();
      values[id].set(bound(id, values[id].get() + across / SPACING[id]));
      settle.current = window.setTimeout(() => goTo(id, values[id].get()), 140);
    }
  };
  const wheel = useRef(onWheel);
  wheel.current = onWheel;
  useEffect(() => {
    const node = svg.current;
    if (!node) return;
    const listener = (event: WheelEvent) => wheel.current(event);
    node.addEventListener("wheel", listener, { passive: false });
    return () => { node.removeEventListener("wheel", listener); window.clearTimeout(settle.current); };
  }, []);
  const onKey = (event: KeyboardEvent) => {
    // Enter and Space on a button press that button
    if ((event.key === "Enter" || event.key === " ") && (event.target as HTMLElement).closest("button")) return;
    const k = ORDER.indexOf(activeNow.current);
    if (event.key === "Escape") leave();
    else if (event.key === "Enter") keep();
    else if (event.key === "ArrowRight" || event.key === "ArrowLeft") step(activeNow.current, (event.key === "ArrowRight" ? 1 : -1) * (event.shiftKey && activeNow.current === "year" ? 10 : 1));
    else if (event.key === "ArrowUp") bring(ORDER[Math.max(0, k - 1)]);
    else if (event.key === "ArrowDown") bring(ORDER[Math.min(LAST, k + 1)]);
    else return;
    event.preventDefault();
    event.stopPropagation();
  };

  const stamp = Date.UTC(parts.y, parts.mo, parts.d, parts.h, parts.mi);
  // The words of the date that change roll in, up when the date goes forward, down when it goes back
  const shownStamp = useRef(stamp);
  const way = stamp >= shownStamp.current ? "up" : "down";
  useEffect(() => { shownStamp.current = stamp; }, [stamp]);
  const line = `${dayFormat.format(new Date(stamp))} · ${pad(parts.h)}:${pad(parts.mi)} UTC`;
  const words = (line.charAt(0).toUpperCase() + line.slice(1)).split(" ");
  const point = (theta: number, r: number) => [g.cx + r * Math.sin(theta), g.cy - r * Math.cos(theta)] as const;
  // The four buttons change only with the date and the ring in front, not at each image of a turn
  const picker = useMemo(() => (
    <SegmentedControl
      className="ows-dial-rings"
      radius="xl"
      value={active}
      onChange={(id) => bring(id as RingId)}
      data={ORDER.map((id) => ({
        value: id,
        label: (
          <span className="ows-dial-pick">
            <span className="ows-dial-pick-name">{t(`rings.${id}`)}</span>
            <span className="ows-dial-pick-value ows-num">{id === "year" ? parts.y : id === "month" ? monthsLong[parts.mo] : id === "day" ? parts.d : `${pad(parts.h)} h`}</span>
          </span>
        ),
      }))}
    />
    // `bring` only reads refs and motion values
    // eslint-disable-next-line react-hooks/exhaustive-deps
  ), [active, parts.y, parts.mo, parts.d, parts.h, monthsLong, lang]);

  return (
    <div
      ref={box}
      className="ows-dial"
      data-open={opened || undefined}
      tabIndex={-1}
      role="dialog"
      aria-modal="true"
      aria-label={t("open")}
      onKeyDown={onKey}
      onMouseDown={keepInside}
      onClick={keepInside}
    >
      <svg
        ref={svg}
        className="ows-dial-face"
        width={g.width}
        height={g.height}
        data-held={held ?? undefined}
        data-other={hover && hover.ring !== active ? "" : undefined}
        onPointerDown={down}
        onPointerMove={over}
        onPointerUp={up}
        onPointerCancel={up}
        onPointerLeave={() => setHover(null)}
      >
        <g ref={zoomGroup}>
          {/* The band of the front line, where the ring in front stops */}
          <circle ref={band} cx={g.cx} className="ows-dial-band" strokeWidth={clamp(g.gap * 0.5, 110, 130)} />
          <g ref={slideGroup}>
            {/* The whole rings, as a watch, while it zooms */}
            {!opened && (
              <g ref={ghosts}>
                {ORDER.map((id) => Array.from({ length: 96 }, (_, k) => {
                  const theta = (k / 96) * Math.PI * 2, r = g.radius[id], long = k % 8 === 0 ? 0.12 : 0.06;
                  const [x1, y1] = point(theta, r), [x2, y2] = point(theta, r * (1 - long * (id === "year" ? 0.5 : 0.7)));
                  return <line key={`${id}-${k}`} x1={x1} y1={y1} x2={x2} y2={y2} className="ows-dial-ghost" vectorEffect="non-scaling-stroke" />;
                }))}
              </g>
            )}
            {ORDER.map((id) => (
              <Ring
                key={id}
                id={id}
                name={t(`rings.${id}`)}
                radius={g.radius[id]}
                value={pos[id]}
                count={id === "month" ? 12 : id === "hour" ? 24 : id === "day" ? daysIn(parts.y, parts.mo) : lastYear() - YEAR0 + 1}
                months={months}
                cx={g.cx}
                cy={g.cy}
                width={g.width}
                hoverX={hover?.ring === id ? hover.x : null}
                register={register}
              />
            ))}
          </g>
        </g>
      </svg>
      <div ref={centre} className="ows-dial-centre" aria-live="polite">
        <span className="ows-dial-day ows-num">
          {words.map((word, k) => <Fragment key={k}>{k > 0 && " "}<span className="ows-roll"><span key={word} data-way={way}>{word}</span></span></Fragment>)}
        </span>
        <span className="ows-dial-row">
          {picker}
          <span className="ows-dial-actions">
            <Tooltip label={t("leave")}><ActionIcon variant="default" radius="xl" size="xl" aria-label={t("leave")} onClick={leave}><IconX size={18} /></ActionIcon></Tooltip>
            <Tooltip label={t("keep")}><ActionIcon variant="filled" radius="xl" size="xl" aria-label={t("keep")} onClick={keep}><IconCheck size={18} /></ActionIcon></Tooltip>
          </span>
        </span>
      </div>
    </div>
  );
}

/** The small watch of the field: its hands at the hour of the date. */
function Watch({ parts }: { parts: Parts | null }) {
  const hour = parts ? ((parts.h % 12) + parts.mi / 60) * 30 : 300, minute = parts ? parts.mi * 6 : 60;
  return (
    <svg viewBox="0 0 20 20" width={20} height={20} aria-hidden="true">
      <circle cx={10} cy={10} r={8.2} className="ows-watch-case" />
      {[0, 90, 180, 270].map((a) => { const [x1, y1] = [10 + 6.6 * Math.sin((a * Math.PI) / 180), 10 - 6.6 * Math.cos((a * Math.PI) / 180)], [x2, y2] = [10 + 8 * Math.sin((a * Math.PI) / 180), 10 - 8 * Math.cos((a * Math.PI) / 180)]; return <line key={a} x1={x1} y1={y1} x2={x2} y2={y2} className="ows-watch-tick" />; })}
      <line x1={10} y1={10} x2={10 + 4 * Math.sin((hour * Math.PI) / 180)} y2={10 - 4 * Math.cos((hour * Math.PI) / 180)} className="ows-watch-hand" />
      <line x1={10} y1={10} x2={10 + 6 * Math.sin((minute * Math.PI) / 180)} y2={10 - 6 * Math.cos((minute * Math.PI) / 180)} className="ows-watch-hand ows-watch-minute" />
    </svg>
  );
}

/** A UTC date and hour field ("YYYY-MM-DDTHH:MM:SS") that opens its dial on a click. */
export function DateField({ label, error, value, onChange }: { label: string; error?: string; value: string; onChange: (value: string) => void }) {
  const t = useT(messages);
  const [open, setOpen] = useState(false);
  const watch = useRef<HTMLSpanElement>(null);
  const [from, setFrom] = useState<DOMRect | null>(null);
  const parts = toParts(value);
  // A click (not the keyboard) opens the dial; the field itself keeps the typing
  const openDial = (event: { preventDefault: () => void }) => {
    if (!parts) return;
    event.preventDefault();
    setFrom(watch.current?.getBoundingClientRect() ?? null);
    setOpen(true);
  };
  return (
    <>
      <TextInput
        type="datetime-local"
        label={label}
        error={error}
        value={toInput(value)}
        onChange={(e) => {
          const typed = e.currentTarget.value;
          onChange(typed.length === 16 ? `${typed}:00` : typed);
        }}
        onMouseDown={openDial}
        title={t("open")}
        rightSection={<span ref={watch} className="ows-watch" data-open={open || undefined}><Watch parts={parts} /></span>}
        classNames={{ input: "ows-date-input" }}
      />
      {open && parts && createPortal(
        <Dial value={parts} from={from} onLeave={() => setOpen(false)} onKeep={(p) => { onChange(write(p)); setOpen(false); }} />,
        document.body,
      )}
    </>
  );
}
