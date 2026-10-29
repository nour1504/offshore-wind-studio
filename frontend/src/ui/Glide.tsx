/**
 * A highlight that glides from one item to another (the active menu entry, the current step,
 * the chosen pill) instead of jumping: the eye follows where the selection went.
 *
 *   const glide = useGlide();
 *   <Box ref={glide.parent} pos="relative">
 *     <Glide glide={glide} active={key} />
 *     {items.map((item) => <a ref={glide.item(item.key)} ... />)}
 *   </Box>
 */
import { FloatingIndicator } from "@mantine/core";
import { useCallback, useRef, useState } from "react";

import { DURATION } from "../motion";

export interface GlideState {
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

export function Glide({ glide, active, className, duration = DURATION.large }: { glide: GlideState; active: string | null | undefined; className?: string; duration?: number }) {
  const target = active ? glide.nodes[active] : null;
  if (!target || !glide.parentNode) return null;
  return (
    <FloatingIndicator
      target={target}
      parent={glide.parentNode}
      transitionDuration={duration}
      className={className ?? "ows-glide"}
      aria-hidden="true"
    />
  );
}
