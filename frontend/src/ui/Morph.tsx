/**
 * A dialog that grows out of its button and shrinks back into it; the usual short entrance when the
 * button is out of sight, none with reduced motion. The dialog takes input at once.
 *
 *   const morph = useMorphingDialog();
 *   <Button ref={morph.trigger} onClick={morph.open}>…</Button>
 *   <Modal {...morph.modalProps} title="…">…</Modal>
 *
 * Opened by the page's own state: `const morph = useMorph(opened)`, then `{...morph.dialog}`.
 */
import type { MantineTransition } from "@mantine/core";
import { useCallback, useLayoutEffect, useMemo, useRef, useState } from "react";

import { DURATION, EASE_GROW, EASE_OUT, prefersReducedMotion } from "../motion";

const GROW = 340;
const SHRINK = DURATION.state;
const LEAVE = "cubic-bezier(0.45, 0, 0.9, 0.55)";
/** Room left around the dialog, at the end of the growth, for its shadow */
const ROOM = 64;
// Mantine keeps the dialog hidden until the movement starts, then shown: the movement is played here
const HELD: MantineTransition = { in: { opacity: 1 }, out: { opacity: 0 }, transitionProperty: "none" };

type Box = { left: number; top: number; width: number; height: number; radius: number };

const radiusOf = (node: HTMLElement) => parseFloat(getComputedStyle(node).borderTopLeftRadius) || 0;

/** The button's box, if it can be seen */
function boxOf(node: HTMLElement | null): Box | null {
  if (!node?.isConnected) return null;
  const r = node.getBoundingClientRect();
  if (r.width < 1 || r.height < 1 || r.bottom < 0 || r.right < 0 || r.top > window.innerHeight || r.left > window.innerWidth) return null;
  return { left: r.left, top: r.top, width: r.width, height: r.height, radius: radiusOf(node) };
}

/** The part of the dialog shown over the button: its corner, the button's size, moved onto it */
function overButton(end: DOMRect, button: Box) {
  const width = Math.min(button.width, end.width);
  const height = Math.min(button.height, end.height);
  return {
    clipPath: `inset(0px ${end.width - width}px ${end.height - height}px 0px round ${button.radius}px)`,
    transform: `translate(${button.left - end.left}px, ${button.top - end.top}px)`,
  };
}

const surfaceOf = (root: HTMLElement | null) => root?.querySelector<HTMLElement>(".mantine-Modal-content") ?? null;
const layersOf = (root: HTMLElement | null) => Array.from(root?.querySelectorAll<HTMLElement>(".mantine-Modal-content, .mantine-Modal-overlay") ?? []);

const whole = (surface: HTMLElement) => `inset(${-ROOM}px round ${radiusOf(surface) + ROOM}px)`;

function grow(surface: HTMLElement, button: Box | null): Animation[] {
  if (!button) {
    return [surface.animate([
      { opacity: 0, transform: "translateY(8px) scale(0.98)", filter: "blur(6px)" },
      { opacity: 1, transform: "none", filter: "none" },
    ], { duration: DURATION.dialog, easing: EASE_OUT })];
  }
  const start = overButton(surface.getBoundingClientRect(), button);
  return [
    surface.animate([
      { opacity: 0, ...start },
      { opacity: 1, offset: 0.25 },
      { opacity: 1, clipPath: whole(surface), transform: "none" },
    ], { duration: GROW, easing: EASE_GROW }),
    ...Array.from(surface.children, (node) => node.animate(
      [{ opacity: 0 }, { opacity: 0, offset: 0.15 }, { opacity: 1, offset: 0.7 }, { opacity: 1 }],
      { duration: GROW, easing: "linear" },
    )),
  ];
}

function shrink(surface: HTMLElement, button: Box | null, playing: Animation[]): Animation[] {
  // From where the dialog stands, even halfway through its growth
  const now = getComputedStyle(surface);
  const from = { opacity: now.opacity, transform: now.transform, clipPath: now.clipPath === "none" ? whole(surface) : now.clipPath };
  const inside = Array.from(surface.children, (node) => ({ node, opacity: getComputedStyle(node).opacity }));
  for (const animation of playing) animation.cancel();
  if (!button) {
    return [surface.animate([
      { opacity: from.opacity, transform: from.transform, filter: "none" },
      { opacity: 0, transform: "translateY(8px) scale(0.98)", filter: "blur(6px)" },
    ], { duration: SHRINK, easing: "ease-in", fill: "forwards" })];
  }
  return [
    surface.animate([
      from,
      { opacity: from.opacity, offset: 0.55 },
      { opacity: 0, ...overButton(surface.getBoundingClientRect(), button) },
    ], { duration: SHRINK, easing: LEAVE, fill: "forwards" }),
    ...inside.map(({ node, opacity }) => node.animate(
      [{ opacity }, { opacity: 0, offset: 0.45 }, { opacity: 0 }],
      { duration: SHRINK, easing: "linear", fill: "forwards" },
    )),
  ];
}

/** The movement alone, for a dialog whose `opened` is decided elsewhere */
export function useMorph(opened: boolean) {
  const button = useRef<HTMLElement | null>(null);
  const root = useRef<HTMLDivElement | null>(null);
  const playing = useRef<Animation[]>([]);
  // Opened and not grown yet; closed at once (nothing to play)
  const waiting = useRef(false);
  const gone = useRef(false);
  const was = useRef(opened);

  const trigger = useCallback((node: HTMLElement | null) => { button.current = node; }, []);
  const ref = useCallback((node: HTMLDivElement | null) => { root.current = node; node?.setAttribute("data-morph", ""); }, []);

  // Called by the overlay and by the dialog as they come in: played once
  const onEnter = useCallback(() => {
    const node = waiting.current ? surfaceOf(root.current) : null;
    if (!node) return;
    waiting.current = false;
    for (const animation of playing.current) animation.cancel();
    playing.current = prefersReducedMotion() ? [] : grow(node, boxOf(button.current));
  }, []);

  useLayoutEffect(() => {
    if (opened === was.current) return;
    was.current = opened;
    if (opened) {
      waiting.current = true;
      gone.current = false;
      for (const node of layersOf(root.current)) node.style.visibility = "";
      return;
    }
    waiting.current = false;
    const node = surfaceOf(root.current);
    if (node && !gone.current && !prefersReducedMotion()) playing.current = shrink(node, boxOf(button.current), playing.current);
  }, [opened]);

  /** Hides the dialog at once, before it closes (the page changes right after) */
  const hide = useCallback(() => {
    gone.current = true;
    for (const animation of playing.current) animation.cancel();
    playing.current = [];
    for (const node of layersOf(root.current)) node.style.visibility = "hidden";
  }, []);

  const dialog = useMemo(() => ({
    ref,
    transitionProps: { transition: HELD, duration: DURATION.dialog, exitDuration: SHRINK, timingFunction: EASE_OUT, onEnter },
  }), [ref, onEnter]);
  return { trigger, hide, dialog };
}

export function useMorphingDialog() {
  const [opened, setOpened] = useState(false);
  const [instant, setInstant] = useState(false);
  const morph = useMorph(opened);
  const { hide } = morph;

  const open = useCallback(() => {
    setInstant(false);
    setOpened(true);
  }, []);

  const close = useCallback(() => setOpened(false), []);

  /** Closes at once, without any animation (before going to another page). */
  const dismiss = useCallback(() => {
    hide();
    setInstant(true);
    setOpened(false);
  }, [hide]);

  // At once: the page scrolls again right away (no zero exit, so the next opening still grows)
  const transitionProps = instant ? { ...morph.dialog.transitionProps, duration: 0, exitDuration: 1 } : morph.dialog.transitionProps;
  const modalProps = { opened, onClose: close, ref: morph.dialog.ref, transitionProps };
  return { opened, open, close, dismiss, trigger: morph.trigger, modalProps };
}
