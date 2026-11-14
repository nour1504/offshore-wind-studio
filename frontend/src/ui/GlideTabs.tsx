/**
 * Tabs.List with a green pill that glides to the selected tab; the new panel comes in from the side
 * of the chosen tab. Follows the tab Mantine marks as selected, so keyboard and panels work as usual.
 */
import { Tabs, type TabsListProps } from "@mantine/core";
import { useLayoutEffect, useRef } from "react";

import { EASE_OUT, pillTransition, prefersReducedMotion } from "../motion";

/** The panel shown, copied just before another tab is chosen, to leave to the other side. */
function copyPanel(tabs: HTMLElement | null): { copy: HTMLElement; parent: HTMLElement } | null {
  if (!tabs || prefersReducedMotion()) return null;
  const panel = Array.from(tabs.querySelectorAll<HTMLElement>("[role='tabpanel']")).find((node) => node.offsetParent !== null && node.closest(".mantine-Tabs-root") === tabs);
  // A map or a 3D view cannot be copied (its canvas would be blank)
  if (!panel?.parentElement || panel.querySelector("canvas")) return null;
  const copy = panel.cloneNode(true) as HTMLElement;
  copy.removeAttribute("id");
  copy.removeAttribute("role");
  copy.setAttribute("aria-hidden", "true");
  copy.inert = true;
  Object.assign(copy.style, { position: "absolute", left: `${panel.offsetLeft}px`, top: `${panel.offsetTop}px`, width: `${panel.offsetWidth}px`, margin: "0", pointerEvents: "none", animation: "none" });
  return { copy, parent: panel.parentElement };
}

/** The copy leaves (blur and fade in 300 ms, slide in 420 ms) under the panel coming in. */
function leave({ copy, parent }: { copy: HTMLElement; parent: HTMLElement }, direction: number) {
  parent.insertBefore(copy, parent.querySelector(":scope > [role='tabpanel']"));
  copy.animate([{ opacity: 1, filter: "blur(0px)" }, { opacity: 0, filter: "blur(6px)" }], { duration: 300, easing: "ease", fill: "forwards" });
  copy.animate([{ transform: "none" }, { transform: `translateX(${-direction * 40}px)` }], { duration: 420, easing: EASE_OUT, fill: "forwards" }).finished.finally(() => copy.remove());
}

export function GlideTabsList({ children, className, ...props }: TabsListProps) {
  const list = useRef<HTMLDivElement>(null);
  const pill = useRef<HTMLSpanElement>(null);
  const flash = useRef<HTMLSpanElement>(null);

  useLayoutEffect(() => {
    const root = list.current;
    const shape = pill.current;
    if (!root || !shape) return;
    const tabs = root.closest<HTMLElement>(".mantine-Tabs-root");
    let at: number | null = null;
    let leaving: ReturnType<typeof copyPanel> = null;
    const place = (animate: boolean) => {
      const tab = root.querySelector<HTMLElement>('[role="tab"][aria-selected="true"]');
      if (!tab) {
        shape.style.opacity = "0";
        return;
      }
      const left = tab.offsetLeft, right = root.clientWidth - tab.offsetLeft - tab.offsetWidth;
      const forward = at === null || !animate ? 0 : Math.sign(left - at);
      shape.style.transition = forward === 0 || prefersReducedMotion() ? "opacity 160ms ease" : `${pillTransition(forward)}, opacity 160ms ease`;
      shape.style.opacity = "1";
      shape.style.left = `${left}px`;
      shape.style.right = `${right}px`;
      shape.style.top = `${tab.offsetTop}px`;
      shape.style.height = `${tab.offsetHeight}px`;
      at = left;
      if (forward === 0) return;
      tabs?.style.setProperty("--ows-tab-dir", String(forward));
      tabs?.setAttribute("data-tab-moved", "");
      tab.scrollIntoView({ block: "nearest", inline: "nearest", behavior: prefersReducedMotion() ? "auto" : "smooth" });
      if (leaving) leave(leaving, forward);
      leaving = null;
    };
    // Before a tab is chosen (pointer or arrows), the panel shown is copied to leave
    const ready = (event: Event) => {
      const tab = (event.target as HTMLElement).closest?.('[role="tab"]');
      const arrows = event instanceof KeyboardEvent && ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key);
      if (!arrows && (!tab || tab.getAttribute("aria-selected") === "true")) return;
      leaving = copyPanel(tabs);
      // A choice that did not happen leaves nothing behind
      window.setTimeout(() => (leaving = null), 300);
    };
    const halo = (event: PointerEvent) => {
      const box = root.getBoundingClientRect();
      flash.current?.style.setProperty("--fx", `${event.clientX - box.left}px`);
      flash.current?.style.setProperty("--sx", `${root.scrollLeft}px`);
    };
    place(false);
    root.addEventListener("pointerdown", ready, true);
    root.addEventListener("keydown", ready, true);
    root.addEventListener("pointermove", halo);
    const changes = new MutationObserver(() => place(true));
    changes.observe(root, { attributes: true, subtree: true, attributeFilter: ["aria-selected"], childList: true });
    const sizes = new ResizeObserver(() => place(false));
    sizes.observe(root);
    return () => {
      root.removeEventListener("pointerdown", ready, true);
      root.removeEventListener("keydown", ready, true);
      root.removeEventListener("pointermove", halo);
      changes.disconnect();
      sizes.disconnect();
    };
  }, []);

  return (
    <Tabs.List ref={list} className={className ? `${className} ows-glide-tabs` : "ows-glide-tabs"} {...props}>
      <span ref={flash} className="ows-tab-flash" aria-hidden="true" />
      {children}
      <span ref={pill} className="ows-tab-pill" aria-hidden="true" />
    </Tabs.List>
  );
}
