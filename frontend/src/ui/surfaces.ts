/**
 * Motion shared by every surface, attached once to the document: dialogs grow out of their button,
 * notifications leave from it, selector pills and table highlights glide, focus rings show for the
 * keyboard only. Behaviour never changes; with reduced motion, only the rings and a still pill.
 */
import { EASE_GROW, PILL, pillTransition, prefersReducedMotion } from "../motion";

const SOURCE = "button, a[href], [role='button'], [role='menuitem'], [role='tab'], [role='option'], label, input[type='checkbox'], input[type='radio']";
const SEGMENTED = ".mantine-SegmentedControl-root";
const CONTROL = "mantine-SegmentedControl-control";

/* --------------------------------------------------------------------------------------- sources */
let last: { rect: DOMRect; at: number; element: Element } | null = null;
const remember = (element: Element | null) => {
  const source = element?.closest?.(SOURCE);
  if (!source) return;
  const rect = source.getBoundingClientRect();
  if (rect.width && rect.height) last = { rect, at: performance.now(), element: source };
};
const recent = (within: number) => (last && performance.now() - last.at < within ? last : null);

/* --------------------------------------------------------------------------------------- dialogs */
function growFrom(content: HTMLElement, from: DOMRect) {
  const inner = content.offsetParent as HTMLElement | null;
  if (!inner) return;
  const box = inner.getBoundingClientRect();
  const x = box.left + content.offsetLeft, y = box.top + content.offsetTop, w = content.offsetWidth, h = content.offsetHeight;
  if (!w || !h) return;
  content.animate(
    [
      { transformOrigin: "0 0", transform: `translate(${from.left - x}px, ${from.top - y}px) scale(${from.width / w}, ${from.height / h})`, opacity: 0.9 },
      { transformOrigin: "0 0", transform: "none", opacity: 1 },
    ],
    { duration: 440, easing: EASE_GROW },
  );
  // The content shows once the panel has taken shape
  content.querySelectorAll<HTMLElement>(":scope > .mantine-Modal-header, :scope > .mantine-Modal-body").forEach((part) =>
    part.animate([{ opacity: 0 }, { opacity: 0, offset: 0.3 }, { opacity: 1 }], { duration: 440, easing: "ease-out" }),
  );
}

/* --------------------------------------------------------------------------------------- notifications */
function flyFrom(note: HTMLElement, from: DOMRect) {
  const to = note.getBoundingClientRect();
  if (!to.width) return;
  const dx = from.left + from.width / 2 - (to.left + to.width / 2), dy = from.top + from.height / 2 - (to.top + to.height / 2);
  if (Math.hypot(dx, dy) < 40) return;
  note.animate(
    [
      { transform: `translate(${dx}px, ${dy}px) scale(0.35)`, opacity: 0, filter: "blur(4px)" },
      { transform: `translate(${dx * 0.35}px, ${dy * 0.35}px) scale(0.8)`, opacity: 1, filter: "blur(1px)", offset: 0.45 },
      { transform: "none", opacity: 1, filter: "blur(0px)" },
    ],
    { duration: 560, easing: "cubic-bezier(0.3, 0.8, 0.25, 1)" },
  );
}

/* --------------------------------------------------------------------------------------- selectors */
function placePill(root: HTMLElement, animate: boolean) {
  let pill = root.querySelector<HTMLElement>(":scope > .ows-seg-pill");
  if (!pill) {
    pill = document.createElement("span");
    pill.className = "ows-seg-pill";
    pill.setAttribute("aria-hidden", "true");
    root.appendChild(pill);
    root.setAttribute("data-glide", "");
  }
  const label = root.querySelector<HTMLElement>(".mantine-SegmentedControl-label[data-active]");
  if (!label) {
    pill.style.opacity = "0";
    return;
  }
  // Measured on screen, then brought back to the selector's own scale: a dialog growing out of its
  // button scales everything inside it for a moment
  const r = label.getBoundingClientRect(), b = root.getBoundingClientRect();
  if (!b.width || !root.offsetWidth) return;
  const sx = b.width / root.offsetWidth, sy = b.height / root.offsetHeight || 1;
  const left = (r.left - b.left) / sx - root.clientLeft, top = (r.top - b.top) / sy - root.clientTop;
  const width = r.width / sx, height = r.height / sy;
  const right = root.clientWidth - left - width;
  if (root.hasAttribute("data-stacked")) {
    // Choices one under the other: the pill glides down and up the same way
    const bottom = root.clientHeight - top - height;
    const above = pill.dataset.top === undefined ? null : Number(pill.dataset.top);
    const down = above === null || !animate || prefersReducedMotion() ? 0 : Math.sign(Math.round(top - above));
    pill.style.transition = down === 0 ? "opacity 160ms ease" : `${pillTransition(down, "top", "bottom")}, left ${PILL.fast}, right ${PILL.fast}, opacity 160ms ease`;
    pill.style.opacity = "1";
    pill.style.left = `${left}px`;
    pill.style.right = `${right}px`;
    pill.style.top = `${top}px`;
    pill.style.bottom = `${bottom}px`;
    pill.style.height = "";
    pill.dataset.top = String(top);
    delete pill.dataset.left;
    return;
  }
  const was = pill.dataset.left === undefined ? null : Number(pill.dataset.left);
  const forward = was === null || !animate || prefersReducedMotion() ? 0 : Math.sign(Math.round(left - was));
  pill.style.transition = forward === 0 ? "opacity 160ms ease" : `${pillTransition(forward)}, top ${PILL.fast}, height ${PILL.fast}, opacity 160ms ease`;
  pill.style.opacity = "1";
  pill.style.left = `${left}px`;
  pill.style.right = `${right}px`;
  pill.style.top = `${top}px`;
  pill.style.height = `${height}px`;
  pill.style.bottom = "";
  pill.dataset.left = String(left);
  delete pill.dataset.top;
}
/**
 * Choices that overflow the selector come closer (data-tight), then stack (data-stacked). Only the
 * choices are measured: the pill and Mantine's indicator lag behind. A selector without room (closed
 * section, full-page capture) keeps its state.
 */
function fit(root: HTMLElement): boolean {
  const style = getComputedStyle(root);
  if (root.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight) < 1) return false;
  const was = root.hasAttribute("data-stacked") ? "stacked" : root.hasAttribute("data-tight") ? "tight" : "";
  root.removeAttribute("data-stacked");
  root.removeAttribute("data-tight");
  const controls = root.getElementsByClassName(CONTROL) as HTMLCollectionOf<HTMLElement>;
  const over = () => {
    let end = 0;
    for (const control of controls) end = Math.max(end, control.offsetLeft + control.offsetWidth);
    return end > root.clientWidth + 0.5;
  };
  let way = "";
  if (over()) {
    root.setAttribute("data-tight", "");
    way = "tight";
    if (over()) {
      root.removeAttribute("data-tight");
      root.setAttribute("data-stacked", "");
      way = "stacked";
    }
  }
  return way !== was;
}
let refitting = 0;
/** Every selector fitted again right after the size observer's call (a change of size made inside
 * it would be reported again in a loop), before the next frame: a section that opens measures its
 * height with its selectors already fitted */
function refit() {
  if (refitting) return;
  refitting = window.setTimeout(() => {
    refitting = 0;
    document.querySelectorAll<HTMLElement>(SEGMENTED).forEach((root) => {
      if (fit(root)) placePill(root, false);
    });
  });
}
// Watched for size: each selector (the pill follows), its choices (their text, its font) and the
// box it sits in (its room), that box counted once for the selectors it holds
const sizes = typeof ResizeObserver === "undefined" ? null : new ResizeObserver((entries) => {
  const roots = new Set<HTMLElement>();
  for (const entry of entries) {
    const root = (entry.target as HTMLElement).closest<HTMLElement>(SEGMENTED);
    if (root) roots.add(root);
  }
  roots.forEach((root) => placePill(root, false));
  refit();
});
const known = new WeakSet<Element>();
const rooms = new Map<Element, number>();
const roomOf = new WeakMap<Element, Element>();
/** The selectors in a node, itself included */
const segmentsIn = (node: HTMLElement) => [...(node.matches(SEGMENTED) ? [node] : []), ...Array.from(node.getElementsByClassName("mantine-SegmentedControl-root") as HTMLCollectionOf<HTMLElement>)];
const firstOf = (node: HTMLElement, name: string) => (node.classList.contains(name) ? node : (node.getElementsByClassName(name)[0] as HTMLElement | undefined) ?? null);
function adopt(root: HTMLElement) {
  fit(root);
  placePill(root, false);
  if (known.has(root) || !sizes) return;
  known.add(root);
  sizes.observe(root);
  for (const control of root.getElementsByClassName(CONTROL)) sizes.observe(control);
  const room = root.parentElement;
  if (!room) return;
  roomOf.set(root, room);
  const count = rooms.get(room) ?? 0;
  rooms.set(room, count + 1);
  if (!count) sizes.observe(room);
}
function forget(root: HTMLElement) {
  known.delete(root);
  if (!sizes) return;
  sizes.unobserve(root);
  for (const control of root.getElementsByClassName(CONTROL)) sizes.unobserve(control);
  const room = roomOf.get(root);
  if (!room) return;
  const count = (rooms.get(room) ?? 1) - 1;
  if (count > 0) rooms.set(room, count);
  else {
    rooms.delete(room);
    sizes.unobserve(room);
  }
}

/* --------------------------------------------------------------------------------------- tables */
function glideRow(row: HTMLElement) {
  const table = row.closest<HTMLElement>(".mantine-Table-table");
  if (!table || !row.closest(".mantine-Table-tbody")) return;
  const first = !table.hasAttribute("data-row-glide") || table.hasAttribute("data-row-off");
  if (first) table.setAttribute("data-row-instant", "");
  table.setAttribute("data-row-glide", "");
  table.removeAttribute("data-row-off");
  table.style.setProperty("--row-y", `${row.offsetTop}px`);
  table.style.setProperty("--row-h", `${row.offsetHeight}px`);
  if (first) requestAnimationFrame(() => table.removeAttribute("data-row-instant"));
}

/* --------------------------------------------------------------------------------------- focus between headers */
function ringTo(control: HTMLElement | null) {
  const rings = document.querySelectorAll<HTMLElement>(".ows-focus-glide");
  if (!control) {
    rings.forEach((ring) => (ring.style.opacity = "0"));
    return;
  }
  const host = control.closest<HTMLElement>(".ows-page-content, .mantine-Modal-body");
  if (!host) return;
  let ring = host.querySelector<HTMLElement>(":scope > .ows-focus-glide");
  if (!ring) {
    ring = document.createElement("span");
    ring.className = "ows-focus-glide";
    ring.setAttribute("aria-hidden", "true");
    host.appendChild(ring);
  }
  rings.forEach((other) => {
    if (other !== ring) other.style.opacity = "0";
  });
  const parent = (ring.offsetParent as HTMLElement | null) ?? document.body;
  const r = control.getBoundingClientRect(), b = parent.getBoundingClientRect();
  const x = r.left - b.left - parent.clientLeft + parent.scrollLeft, y = r.top - b.top - parent.clientTop + parent.scrollTop;
  const first = ring.style.opacity !== "1";
  ring.style.transition = first || prefersReducedMotion() ? "opacity 140ms ease" : "transform 260ms cubic-bezier(0.2, 0.9, 0.3, 1), width 260ms ease, height 260ms ease, opacity 140ms ease";
  ring.style.transform = `translate(${x}px, ${y}px)`;
  ring.style.width = `${r.width}px`;
  ring.style.height = `${r.height}px`;
  ring.style.opacity = "1";
}

/* --------------------------------------------------------------------------------------- install */
export function installSurfaces(): () => void {
  const html = document.documentElement;
  const onPointerDown = (event: PointerEvent) => {
    html.dataset.input = "pointer";
    ringTo(null);
    remember(event.target as Element);
  };
  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key === "Tab" || event.key.startsWith("Arrow") || ["Enter", " ", "Escape", "Home", "End", "PageUp", "PageDown"].includes(event.key)) html.dataset.input = "keyboard";
    if (event.key === "Enter" || event.key === " ") remember(document.activeElement);
  };
  const onFocusIn = (event: FocusEvent) => {
    const control = (event.target as Element | null)?.closest?.<HTMLElement>(".mantine-Accordion-control");
    ringTo(html.dataset.input === "keyboard" && control ? control : null);
  };
  const onPointerOver = (event: PointerEvent) => {
    const row = (event.target as Element | null)?.closest?.<HTMLElement>(".mantine-Table-tbody .mantine-Table-tr");
    if (row) glideRow(row);
  };
  const onPointerOut = (event: PointerEvent) => {
    const from = (event.target as Element | null)?.closest?.(".mantine-Table-table");
    const to = (event.relatedTarget as Element | null)?.closest?.(".mantine-Table-table");
    if (from && from !== to) from.setAttribute("data-row-off", "");
  };

  const added = new MutationObserver((records) => {
    const reduced = prefersReducedMotion();
    for (const record of records) {
      if (record.type === "attributes") {
        const label = record.target as HTMLElement;
        if (label.classList?.contains("mantine-SegmentedControl-label") && label.hasAttribute("data-active")) {
          const root = label.closest<HTMLElement>(SEGMENTED);
          if (root) placePill(root, true);
        }
        continue;
      }
      // Selectors gone: no longer watched; a choice gone or come: its selector fitted again
      record.removedNodes.forEach((node) => {
        if (!(node instanceof HTMLElement) || node.isConnected) return;
        segmentsIn(node).forEach(forget);
        if (node.classList.contains(CONTROL)) {
          sizes?.unobserve(node);
          refit();
        }
      });
      record.addedNodes.forEach((node) => {
        if (!(node instanceof HTMLElement)) return;
        segmentsIn(node).forEach(adopt);
        if (node.classList.contains(CONTROL) && known.has(node.parentElement as Element)) {
          sizes?.observe(node);
          refit();
        }
        if (reduced) return;
        // Dialogs of ui/Morph grow out of their button on their own
        const content = firstOf(node, "mantine-Modal-content");
        const source = recent(800);
        if (content && source && !content.closest(".ows-palette, [data-morph]")) growFrom(content, source.rect);
        const note = firstOf(node, "mantine-Notification-root");
        const cause = recent(2500);
        if (note && cause && cause.element.isConnected) requestAnimationFrame(() => flyFrom(note, cause.element.getBoundingClientRect()));
      });
    }
  });
  document.addEventListener("pointerdown", onPointerDown, true);
  document.addEventListener("keydown", onKeyDown, true);
  document.addEventListener("pointerover", onPointerOver, true);
  document.addEventListener("pointerout", onPointerOut, true);
  document.addEventListener("focusin", onFocusIn, true);
  added.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["data-active"] });
  document.querySelectorAll<HTMLElement>(SEGMENTED).forEach(adopt);
  // A font arriving changes the width of the choices without always changing their boxes
  document.fonts.addEventListener("loadingdone", refit);
  return () => {
    document.removeEventListener("pointerdown", onPointerDown, true);
    document.removeEventListener("keydown", onKeyDown, true);
    document.removeEventListener("pointerover", onPointerOver, true);
    document.removeEventListener("pointerout", onPointerOut, true);
    document.removeEventListener("focusin", onFocusIn, true);
    document.fonts.removeEventListener("loadingdone", refit);
    added.disconnect();
    sizes?.disconnect();
    rooms.clear();
    window.clearTimeout(refitting);
    refitting = 0;
  };
}
