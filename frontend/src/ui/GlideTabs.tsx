/**
 * Tabs.List with an underline that glides to the selected tab (instead of jumping from one tab's
 * border to the next). It follows whichever tab Mantine marks as selected, so the tabs keep all
 * their behaviour (keyboard, values, panels).
 */
import { Tabs, type TabsListProps } from "@mantine/core";
import { useLayoutEffect, useRef } from "react";

export function GlideTabsList({ children, className, ...props }: TabsListProps) {
  const list = useRef<HTMLDivElement>(null);
  const bar = useRef<HTMLSpanElement>(null);

  useLayoutEffect(() => {
    const root = list.current;
    const line = bar.current;
    if (!root || !line) return;
    let first = true;
    const place = () => {
      const tab = root.querySelector<HTMLElement>('[role="tab"][aria-selected="true"]');
      if (!tab) {
        line.style.opacity = "0";
        return;
      }
      const box = root.getBoundingClientRect();
      const own = tab.getBoundingClientRect();
      // No glide the first time: the line starts under the selected tab
      line.style.transitionDuration = first ? "0ms" : "";
      line.style.opacity = "1";
      line.style.width = `${own.width}px`;
      line.style.transform = `translateX(${own.left - box.left + root.scrollLeft}px)`;
      first = false;
    };
    place();
    const changes = new MutationObserver(place);
    changes.observe(root, { attributes: true, subtree: true, attributeFilter: ["aria-selected"], childList: true });
    const sizes = new ResizeObserver(place);
    sizes.observe(root);
    return () => {
      changes.disconnect();
      sizes.disconnect();
    };
  }, []);

  return (
    <Tabs.List ref={list} className={className ? `${className} ows-glide-tabs` : "ows-glide-tabs"} {...props}>
      {children}
      <span ref={bar} className="ows-tab-line" aria-hidden="true" />
    </Tabs.List>
  );
}
