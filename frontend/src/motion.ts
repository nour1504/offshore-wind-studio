/**
 * Shared durations and curves, and the transitions of floating layers (menus, lists, tooltips,
 * dialogs), pages and theme: short, never delaying a result, transform and opacity where possible,
 * nothing with prefers-reduced-motion. Same values in styles.css (--ows-ease-*, --ows-dur-*).
 */
import type { MantineTransition } from "@mantine/core";
import { flushSync } from "react-dom";

/** Durations in ms: micro-interactions, state changes, menus, dialogs and panels, larger moves. */
export const DURATION = { micro: 120, state: 160, menu: 190, dialog: 240, large: 320 } as const;

/** Fast start, long soft landing: objects arriving (the curve's points, for motion/react, then as CSS). */
export const EASE_OUT_POINTS = [0.16, 1, 0.3, 1] as const;
export const EASE_OUT = `cubic-bezier(${EASE_OUT_POINTS.join(", ")})`;

/** A surface growing out of what opened it (a window from its button, a value from its summary). */
export const EASE_GROW = "cubic-bezier(0.2, 0.9, 0.25, 1)";

/** The pill of tabs and selectors: the edge on the side of the move leaves first and overshoots a
    little, the other one follows late. */
export const PILL = { slow: "460ms cubic-bezier(0.3, 1.25, 0.4, 1)", fast: "260ms cubic-bezier(0.3, 1.3, 0.5, 1)" } as const;

/** Transition of a pill whose edges `start` and `end` move `forward` (> 0: right or down). */
export const pillTransition = (forward: number, start = "left", end = "right") =>
  forward > 0 ? `${start} ${PILL.slow}, ${end} ${PILL.fast}` : `${start} ${PILL.fast}, ${end} ${PILL.slow}`;

/** The same curve for MapLibre camera moves (fitBounds, flyTo): t in [0, 1]. */
export const easeOutMap = (t: number) => 1 - Math.pow(1 - t, 4);

/** A value kept between two bounds. */
export const clamp = (v: number, lo: number, hi: number) => (v < lo ? lo : v > hi ? hi : v);

/** 0 before a, 1 after b, a smooth S between them. */
export const smoothstep = (a: number, b: number, v: number) => {
  const t = clamp((v - a) / (b - a), 0, 1);
  return t * t * (3 - 2 * t);
};

/** Springs of the `motion` library: soft for large objects (cards, panels), snappy for small
    ones (indicators, pills), bouncy for what arrives and settles (the card in the centre). */
export const SPRING = {
  soft: { type: "spring", stiffness: 170, damping: 26, mass: 1 },
  snappy: { type: "spring", stiffness: 420, damping: 34, mass: 0.7 },
  bouncy: { type: "spring", stiffness: 260, damping: 17, mass: 0.9 },
} as const;

/** True while the page is shown and the element is on screen: backgrounds pause otherwise. */
export function watchVisible(element: Element, change: (visible: boolean) => void): () => void {
  let onScreen = true;
  const update = () => change(onScreen && document.visibilityState === "visible");
  const observer = new IntersectionObserver((entries) => {
    onScreen = entries.some((entry) => entry.isIntersecting);
    update();
  });
  observer.observe(element);
  document.addEventListener("visibilitychange", update);
  return () => {
    observer.disconnect();
    document.removeEventListener("visibilitychange", update);
  };
}

/** Menus and lists: a short drop from their trigger, slightly scaled. */
export const dropIn: MantineTransition = {
  in: { opacity: 1, transform: "translateY(0) scale(1)" },
  out: { opacity: 0, transform: "translateY(-4px) scale(0.97)" },
  common: { transformOrigin: "top" },
  transitionProperty: "transform, opacity",
};

/** Menus open as a circle spreading from their top edge, under the button that opened them. */
export const radialIn: MantineTransition = {
  in: { opacity: 1, clipPath: "circle(150% at 50% 0)" },
  out: { opacity: 0, clipPath: "circle(0% at 50% 0)" },
  transitionProperty: "clip-path, opacity",
};

/** Dialogs: rise and settle in the middle of the screen. */
// Dialogs come out of a blur and close into it (opened from a button, they grow out of it: ui/surfaces.ts)
export const dialogIn: MantineTransition = {
  in: { opacity: 1, transform: "translateY(0) scale(1)", filter: "blur(0px)" },
  out: { opacity: 0, transform: "translateY(8px) scale(0.98)", filter: "blur(6px)" },
  transitionProperty: "transform, opacity, filter",
};

export function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
}

/** Navigation direction is visual only; it never chooses or postpones a destination. */
export function setNavigationMotion(before: string, after: string): void {
  const a = before.split("?")[0].split("/");
  const b = after.split("?")[0].split("/");
  const order = ["overview", "data", "domains", "turbines", "farms", "physics", "outputs", "run", "results", "explorer", "analyses", "export", "media"];
  const from = order.indexOf(a[2]);
  const to = order.indexOf(b[2]);
  const direction = a[0] === "projects" && b[0] === "projects" && a[1] === b[1] && from >= 0 && to >= 0 ? Math.sign(to - from) : 0;
  const root = document.documentElement.style;
  root.setProperty("--ows-page-in-x", `${direction * 20}px`);
  root.setProperty("--ows-page-out-x", `${direction * -10}px`);
}

type ViewTransitionDocument = Document & {
  startViewTransition?: (update: () => void) => { finished: Promise<void>; ready: Promise<void>; skipTransition?: () => void };
};

/**
 * Runs a DOM change as a view transition when the browser can (WebView2 and Edge can), with a
 * class on <html> naming its kind so that styles.css animates it; otherwise applies it at once.
 * The change itself is never delayed: the browser captures the old picture, applies the change
 * immediately, then animates between the two.
 */
export function withViewTransition(kind: "page" | "theme", update: () => void): void {
  const doc = document as ViewTransitionDocument;
  if (!canViewTransition()) {
    update();
    return;
  }
  const root = document.documentElement;
  root.classList.add(`ows-vt-${kind}`);
  // The browser applies the change only once it has drawn the old picture. A window that draws
  // nothing (hidden behind another one, being restored...) would leave the change pending: after
  // a short wait it is applied without animation. The change never depends on the animation.
  let applied = false;
  const apply = () => {
    if (applied) return;
    applied = true;
    flushSync(update);
  };
  let guard = 0;
  let finished = false;
  const finish = () => {
    if (finished) return;
    finished = true;
    window.clearTimeout(guard);
    root.classList.remove(`ows-vt-${kind}`);
  };
  try {
    const transition = doc.startViewTransition!(apply);
    guard = window.setTimeout(() => {
      if (applied) return;
      transition.skipTransition?.();
      apply();
      finish();
    }, 200);
    // A skipped transition rejects ready: nothing to do, the change is applied anyway
    transition.ready.catch(() => undefined);
    void transition.finished.then(finish, finish);
  } catch {
    apply();
    finish();
  }
}

/** True when page and theme transitions can play (supported, motion not reduced, page visible). */
export function canViewTransition(): boolean {
  const doc = document as ViewTransitionDocument;
  return Boolean(doc.startViewTransition) && !prefersReducedMotion() && document.visibilityState === "visible";
}
