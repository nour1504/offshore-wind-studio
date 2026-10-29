/**
 * The navigation of the staircase over the period: wheel zoom around the hour under the pointer,
 * drag along the steps to move in time, pinch on a touch screen, keyboard (+, −, 0, arrows), and
 * smooth moves to a framed part (buttons, click on a step). Moves are instant when animations are
 * reduced. A click (a press that does not move) is reported apart from a drag.
 */
import { useReducedMotion } from "@mantine/hooks";
import { useCallback, useEffect, useRef, useState } from "react";

import { clampRange, type Limits, mixRange, type Range, shiftRange, whole, zoomRange } from "./view";

const STEP = 1.8;

export interface Pointing {
  /** The hour under a point of the drawing, or null */
  hourAt: (sx: number, sy: number) => number | null;
  /** Pixels of drag along the steps that move by the whole part seen */
  dragSpan: number;
  onClick: (sx: number, sy: number) => void;
}

export function useStairsView(svg: SVGSVGElement | null, limits: Limits, pointing: Pointing) {
  const reduced = useReducedMotion();
  const [range, setRange] = useState<Range>(() => whole(limits));
  const current = useRef(range);
  const tween = useRef(0);
  const limitsRef = useRef(limits);
  limitsRef.current = limits;
  const pointingRef = useRef(pointing);
  pointingRef.current = pointing;
  const canZoom = limits.shortest < limits.span;

  const show = useCallback((next: Range) => {
    current.current = next;
    setRange(next);
  }, []);

  /** A smooth move to `to` (ease-out), or at once. */
  const animateTo = useCallback((to: Range, duration = 520) => {
    cancelAnimationFrame(tween.current);
    const goal = clampRange(to, limitsRef.current);
    if (reduced || duration <= 0) return show(goal);
    const from = current.current;
    const start = performance.now();
    const step = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      show(clampRange(mixRange(from, goal, 1 - Math.pow(1 - t, 3)), limitsRef.current));
      if (t < 1) tween.current = requestAnimationFrame(step);
    };
    tween.current = requestAnimationFrame(step);
  }, [reduced, show]);

  // A new period: the whole of it again
  useEffect(() => {
    show(whole(limits));
  }, [limits.span, limits.shortest, show]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => cancelAnimationFrame(tween.current), []);

  const zoomBy = useCallback((factor: number) => {
    const r = current.current;
    animateTo(zoomRange(r, factor, (r.t0 + r.t1) / 2, limitsRef.current), 320);
  }, [animateTo]);

  useEffect(() => {
    if (!svg) return;
    const local = (event: { clientX: number; clientY: number }) => {
      const box = svg.getBoundingClientRect();
      return [event.clientX - box.left, event.clientY - box.top] as const;
    };
    const around = (sx: number, sy: number) => {
      const r = current.current;
      return pointingRef.current.hourAt(sx, sy) ?? (r.t0 + r.t1) / 2;
    };
    const wheel = (event: WheelEvent) => {
      if (!canZoom) return;
      event.preventDefault();
      cancelAnimationFrame(tween.current);
      const [sx, sy] = local(event);
      show(zoomRange(current.current, Math.exp(-event.deltaY * 0.0016), around(sx, sy), limitsRef.current));
    };
    // Pointers down: one drags, two pinch
    const pointers = new Map<number, { x: number; y: number }>();
    let moved = false;
    let pinch = 0;
    const down = (event: PointerEvent) => {
      pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
      moved = false;
      if (pointers.size === 2) {
        const [a, b] = [...pointers.values()];
        pinch = Math.hypot(a.x - b.x, a.y - b.y);
      }
      try { svg.setPointerCapture(event.pointerId); } catch { /* a pointer that is gone */ }
    };
    const move = (event: PointerEvent) => {
      const last = pointers.get(event.pointerId);
      if (!last) return;
      if (pointers.size === 1) {
        const dx = event.clientX - last.x;
        if (!moved && Math.hypot(dx, event.clientY - last.y) < 4) return;
        moved = true;
        cancelAnimationFrame(tween.current);
        // Dragging to the right brings earlier hours (the steps rise from left to right in front)
        show(shiftRange(current.current, -dx / pointingRef.current.dragSpan, limitsRef.current));
        pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
        return;
      }
      pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
      const [a, b] = [...pointers.values()];
      const distance = Math.hypot(a.x - b.x, a.y - b.y);
      if (pinch > 0 && distance > 0 && canZoom) {
        moved = true;
        const [sx, sy] = local({ clientX: (a.x + b.x) / 2, clientY: (a.y + b.y) / 2 });
        show(zoomRange(current.current, distance / pinch, around(sx, sy), limitsRef.current));
      }
      pinch = distance;
    };
    const up = (event: PointerEvent) => {
      const was = pointers.size;
      pointers.delete(event.pointerId);
      if (was === 1 && !moved) {
        const [sx, sy] = local(event);
        pointingRef.current.onClick(sx, sy);
      }
      if (pointers.size < 2) pinch = 0;
    };
    svg.addEventListener("wheel", wheel, { passive: false });
    svg.addEventListener("pointerdown", down);
    svg.addEventListener("pointermove", move);
    svg.addEventListener("pointerup", up);
    svg.addEventListener("pointercancel", up);
    return () => {
      svg.removeEventListener("wheel", wheel);
      svg.removeEventListener("pointerdown", down);
      svg.removeEventListener("pointermove", move);
      svg.removeEventListener("pointerup", up);
      svg.removeEventListener("pointercancel", up);
    };
  }, [svg, canZoom, show]);

  const onKeyDown = useCallback((event: React.KeyboardEvent) => {
    if (!canZoom) return;
    const actions: Record<string, () => void> = {
      "+": () => zoomBy(STEP),
      "=": () => zoomBy(STEP),
      "-": () => zoomBy(1 / STEP),
      "0": () => animateTo(whole(limitsRef.current)),
      Home: () => animateTo(whole(limitsRef.current)),
      ArrowLeft: () => animateTo(shiftRange(current.current, -0.2, limitsRef.current), 260),
      ArrowRight: () => animateTo(shiftRange(current.current, 0.2, limitsRef.current), 260),
      ArrowDown: () => zoomBy(1 / STEP),
      ArrowUp: () => zoomBy(STEP),
    };
    const action = actions[event.key];
    if (action) {
      event.preventDefault();
      action();
    }
  }, [animateTo, zoomBy, canZoom]);

  /** At once, for a drag on the period bar. */
  const jumpTo = useCallback((to: Range) => {
    cancelAnimationFrame(tween.current);
    show(clampRange(to, limitsRef.current));
  }, [show]);

  return { range, animateTo, jumpTo, zoomBy, onKeyDown, canZoom };
}
