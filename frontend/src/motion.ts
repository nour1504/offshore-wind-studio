/**
 * The motion system: one set of durations and curves for the whole interface, the transitions of
 * floating layers (menus, lists, tooltips, dialogs) and the page and theme transitions.
 *
 * Rules: movement explains a change (where something came from, where it went), it never delays
 * a result, and it is short. Only transform and opacity are animated where possible. Everything
 * stops for people who ask Windows to reduce animations (prefers-reduced-motion).
 * The same values exist as CSS variables in styles.css (--ows-ease-*, --ows-dur-*).
 */
import type { MantineTransition } from "@mantine/core";
import { flushSync } from "react-dom";

/** Durations in ms: micro-interactions, state changes, menus, dialogs and panels, larger moves. */
export const DURATION = { micro: 120, state: 160, menu: 190, dialog: 240, large: 320 } as const;

/** Fast start, long soft landing: objects arriving. */
export const EASE_OUT = "cubic-bezier(0.16, 1, 0.3, 1)";
/** Symmetric: objects moving from one place to another. */
/** A hint of overshoot, for small things that settle (indicators, toggles). */

/** The same curve for MapLibre camera moves (fitBounds, flyTo): t in [0, 1]. */
export const easeOutMap = (t: number) => 1 - Math.pow(1 - t, 4);

/** Menus and lists: a short drop from their trigger, slightly scaled. */
export const dropIn: MantineTransition = {
  in: { opacity: 1, transform: "translateY(0) scale(1)" },
  out: { opacity: 0, transform: "translateY(-4px) scale(0.97)" },
  common: { transformOrigin: "top" },
  transitionProperty: "transform, opacity",
};

/** Dialogs: rise and settle in the middle of the screen. */
export const dialogIn: MantineTransition = {
  in: { opacity: 1, transform: "translateY(0) scale(1)" },
  out: { opacity: 0, transform: "translateY(10px) scale(0.97)" },
  transitionProperty: "transform, opacity",
};

/** Bars that come from the bottom of the window (the save bar). */
export const barIn: MantineTransition = {
  in: { opacity: 1, transform: "translate(-50%, 0)" },
  out: { opacity: 0, transform: "translate(-50%, 16px)" },
  transitionProperty: "transform, opacity",
};

export function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
}

/** Navigation direction is visual only; it never chooses or postpones a destination. */
export function setNavigationMotion(before: string, after: string): void {
  const a = before.split("?")[0].split("/");
  const b = after.split("?")[0].split("/");
  const order = ["overview", "data", "domains", "turbines", "farms", "physics", "outputs", "run", "results", "explorer", "analyses", "media"];
  const from = order.indexOf(a[2]);
  const to = order.indexOf(b[2]);
  const direction = a[0] === "projects" && b[0] === "projects" && a[1] === b[1] && from >= 0 && to >= 0 ? Math.sign(to - from) : 0;
  const root = document.documentElement.style;
  root.setProperty("--ows-page-in-x", `${direction * 20}px`);
  root.setProperty("--ows-page-out-x", `${direction * -10}px`);
}

type ViewTransitionDocument = Document & {
  startViewTransition?: (update: () => void | Promise<void>) => { finished: Promise<void>; ready: Promise<void>; skipTransition?: () => void };
};

/**
 * Runs a DOM change as a view transition when the browser can (WebView2 and Edge can), with a
 * class on <html> naming its kind so that styles.css animates it; otherwise applies it at once.
 * The change itself is never delayed: the browser captures the old picture, applies the change
 * immediately, then animates between the two.
 */
export function withViewTransition(
  kind: "page" | "theme" | "morph",
  update: () => void,
  options: {
    /** Wait a moment after the change before the new picture is taken (dialogs mount in two steps) */
    settle?: boolean;
    /** Called when the transition is over (or at once without one) */
    done?: () => void;
  } = {},
): void {
  const doc = document as ViewTransitionDocument;
  if (!canViewTransition()) {
    update();
    options.done?.();
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
    options.done?.();
  };
  try {
    const transition = doc.startViewTransition!(() => {
      const late = applied;
      apply();
      if (options.settle && !late) return new Promise<void>((resolve) => window.setTimeout(resolve, 20));
    });
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

/** True when page, theme and dialog transitions can play (supported, motion not reduced, page visible). */
export function canViewTransition(): boolean {
  const doc = document as ViewTransitionDocument;
  return Boolean(doc.startViewTransition) && !prefersReducedMotion() && document.visibilityState === "visible";
}
