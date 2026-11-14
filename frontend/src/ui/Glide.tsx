/**
 * A highlight that glides from item to item (menu entry, step, pill), stretching on the way.
 *
 *   const glide = useGlide();
 *   <Box ref={glide.parent} pos="relative">
 *     <Glide glide={glide} active={key} />
 *     {items.map((item) => <a ref={glide.item(item.key)} ... />)}
 *   </Box>
 */
import { useCallback, useLayoutEffect, useRef, useState } from "react";

import { DURATION, pillTransition, prefersReducedMotion } from "../motion";

interface GlideState {
  parent: (node: HTMLElement | null) => void;
  item: (key: string) => (node: HTMLElement | null) => void;
  parentNode: HTMLElement | null;
  nodes: Record<string, HTMLElement | null>;
}

export function useGlide(): GlideState {
  const [parentNode, setParentNode] = useState<HTMLElement | null>(null);
  const [nodes, setNodes] = useState<Record<string, HTMLElement | null>>({});
  // One stable ref callback per key, so that React does not detach and reattach them each render
  const callbacks = useRef(new Map<string, (node: HTMLElement | null) => void>());
  const item = useCallback((key: string) => {
    let callback = callbacks.current.get(key);
    if (!callback) {
      callback = (node: HTMLElement | null) => setNodes((previous) => (previous[key] === node ? previous : { ...previous, [key]: node }));
      callbacks.current.set(key, callback);
    }
    return callback;
  }, []);
  return { parent: setParentNode, item, parentNode, nodes };
}

/** `pill`: the timings of the tabs' pill (a little overshoot). */
export function Glide({ glide, active, className, duration = DURATION.large, pill = false }: { glide: GlideState; active: string | null | undefined; className?: string; duration?: number; pill?: boolean }) {
  const target = active ? glide.nodes[active] : null;
  const parent = glide.parentNode;
  const shape = useRef<HTMLSpanElement>(null);
  const last = useRef<{ x: number; y: number; r: number; b: number } | null>(null);
  useLayoutEffect(() => {
    const element = shape.current;
    if (!parent || !target || !element) return;
    const place = (animate: boolean) => {
      // Measured on screen, brought back to the parent's own scale (a dialog may be growing)
      const p = parent.getBoundingClientRect(), r = target.getBoundingClientRect();
      if (!parent.offsetWidth || !parent.offsetHeight) return;
      const sx = p.width / parent.offsetWidth || 1, sy = p.height / parent.offsetHeight || 1;
      const left = (r.left - p.left) / sx - parent.clientLeft, top = (r.top - p.top) / sy - parent.clientTop;
      const right = parent.clientWidth - left - r.width / sx, bottom = parent.clientHeight - top - r.height / sy;
      const was = last.current;
      // A resize that moves nothing (the observer's first call among them) leaves a glide running
      if (!animate && was && Math.abs(was.x - left) + Math.abs(was.y - top) + Math.abs(was.r - right) + Math.abs(was.b - bottom) < 1) return;
      if (!animate || !was || prefersReducedMotion()) element.style.transition = "none";
      else {
        const dx = Math.sign(Math.round(left - was.x)), dy = Math.sign(Math.round(top - was.y));
        const fast = `${Math.round(duration * 0.5)}ms cubic-bezier(0.2, 0.9, 0.3, 1)`, slow = `${duration}ms cubic-bezier(0.5, 0, 0.2, 1)`;
        element.style.transition = pill
          ? `${pillTransition(dx)}, ${pillTransition(dy, "top", "bottom")}`
          : `left ${dx > 0 ? slow : fast}, right ${dx < 0 ? slow : fast}, top ${dy > 0 ? slow : fast}, bottom ${dy < 0 ? slow : fast}`;
      }
      element.style.left = `${left}px`;
      element.style.right = `${right}px`;
      element.style.top = `${top}px`;
      element.style.bottom = `${bottom}px`;
      last.current = { x: left, y: top, r: right, b: bottom };
    };
    place(true);
    const sizes = new ResizeObserver(() => place(false));
    sizes.observe(parent);
    sizes.observe(target);
    return () => sizes.disconnect();
  }, [parent, target, duration, pill]);
  if (!target || !parent) return null;
  return <span ref={shape} className={className ?? "ows-glide"} style={{ position: "absolute", zIndex: 0 }} aria-hidden="true" />;
}
