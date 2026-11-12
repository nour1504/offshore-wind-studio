/**
 * Rows that move when a list is filtered or sorted: each row kept slides from where it was to its
 * new place (FLIP), each new one comes out of a light scatter and a blur. Rows carry their key in
 * data-flip; only the first sixty move, so that long lists stay light. Nothing on first display.
 */
import { type RefObject, useLayoutEffect, useRef } from "react";

import { prefersReducedMotion } from "../motion";

const LIMIT = 60;
const EASE = "cubic-bezier(0.2, 0.9, 0.3, 1)";

export function useFlip(root: RefObject<HTMLElement | null>, signature: unknown) {
  const last = useRef<Map<string, { x: number; y: number }>>(new Map());
  useLayoutEffect(() => {
    const box = root.current;
    if (!box) return;
    const origin = box.getBoundingClientRect();
    const before = last.current;
    const animate = before.size > 0 && !prefersReducedMotion();
    const next = new Map<string, { x: number; y: number }>();
    let fresh = 0;
    for (const item of Array.from(box.querySelectorAll<HTMLElement>("[data-flip]")).slice(0, LIMIT)) {
      const r = item.getBoundingClientRect();
      const at = { x: r.left - origin.left, y: r.top - origin.top };
      const key = item.dataset.flip ?? "";
      next.set(key, at);
      if (!animate) continue;
      const was = before.get(key);
      if (was) {
        const dx = was.x - at.x, dy = was.y - at.y;
        if (Math.abs(dx) + Math.abs(dy) > 1) item.animate([{ transform: `translate(${dx}px, ${dy}px)` }, { transform: "none" }], { duration: 320, easing: EASE });
      } else {
        // Scattered a little, then in its place
        const k = fresh++;
        const sx = ((k * 37) % 17) - 8, sy = 6 + ((k * 23) % 7);
        item.animate(
          [{ opacity: 0, filter: "blur(4px)", transform: `translate(${sx}px, ${sy}px)` }, { opacity: 1, filter: "blur(0px)", transform: "none" }],
          { duration: 320, delay: Math.min(k, 12) * 16, easing: EASE, fill: "backwards" },
        );
      }
    }
    last.current = next;
  }, [root, signature]);
}
