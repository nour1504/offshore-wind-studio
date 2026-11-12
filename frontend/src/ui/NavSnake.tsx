/**
 * The hover highlight of the menu: it follows the pointer from entry to entry like a snake, its
 * leading edge reaching the new entry first and the trailing edge catching up, so it stretches
 * and then gathers. It only marks the hovered entry; the active one keeps its own highlight.
 */
import { animate, motion, useMotionValue, useReducedMotion, useTransform } from "motion/react";
import { useEffect } from "react";

const LEAD = { type: "spring", stiffness: 560, damping: 40, mass: 0.6 } as const;
const TAIL = { type: "spring", stiffness: 190, damping: 24, mass: 0.9 } as const;

export function NavSnake({ parent }: { parent: HTMLElement | null }) {
  const reduced = useReducedMotion();
  const top = useMotionValue(0), bottom = useMotionValue(0), left = useMotionValue(0), width = useMotionValue(0), opacity = useMotionValue(0);
  const height = useTransform(() => Math.max(0, bottom.get() - top.get()));

  useEffect(() => {
    if (!parent) return;
    let last: HTMLElement | null = null;
    const over = (event: PointerEvent) => {
      const link = (event.target as Element | null)?.closest<HTMLElement>(".ows-nav-link");
      if (!link || link === last || !parent.contains(link)) return;
      const box = parent.getBoundingClientRect(), r = link.getBoundingClientRect();
      const t = r.top - box.top, b = r.bottom - box.top;
      if (!last || reduced) {
        top.jump(t);
        bottom.jump(b);
        left.jump(r.left - box.left);
        width.jump(r.width);
      } else {
        const down = t > top.get();
        animate(top, t, down ? TAIL : LEAD);
        animate(bottom, b, down ? LEAD : TAIL);
        animate(left, r.left - box.left, LEAD);
        animate(width, r.width, LEAD);
      }
      animate(opacity, 1, { duration: reduced ? 0 : 0.18 });
      last = link;
    };
    const leave = () => {
      last = null;
      animate(opacity, 0, { duration: reduced ? 0 : 0.25 });
    };
    parent.addEventListener("pointerover", over);
    parent.addEventListener("pointerleave", leave);
    return () => {
      parent.removeEventListener("pointerover", over);
      parent.removeEventListener("pointerleave", leave);
    };
  }, [parent, reduced, top, bottom, left, width, opacity]);

  return <motion.span className="ows-nav-snake" aria-hidden="true" style={{ top, height, left, width, opacity }} />;
}
