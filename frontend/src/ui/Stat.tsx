import { Group, SimpleGrid, Text, Tooltip } from "@mantine/core";
import { IconInfoCircle } from "@tabler/icons-react";
import { type CSSProperties, type ReactNode, useEffect, useLayoutEffect, useRef } from "react";

import type { RunState } from "../api/types";
import { common } from "../i18n/common";
import { useT } from "../i18n";
import { SwapText } from "./Motion";

interface StatProps {
  label: ReactNode;
  value: ReactNode;
  /** Written after the label ("Energy · MWh"), or after the value when it is not a text */
  unit?: ReactNode;
  /** One line under the value: reference, method, caveat */
  hint?: ReactNode;
  /** Longer explanation in a tooltip */
  info?: ReactNode;
  tone?: "default" | "good" | "bad" | "muted";
  /** A step of the work done: a line fills under the tile, in the order of the work (`order`) */
  filled?: boolean;
  /** Place of the tile in its band: the fill and the change of value follow it */
  order?: number;
}

const toneColor = { default: undefined, good: "teal.7", bad: "ember.7", muted: "dimmed" } as const;

/**
 * A key figure, one cell of its band: the label and its unit in small type, the value in large
 * type, swapped character by character when it changes; how to read it under it.
 */
export function Stat({ label, value, unit, hint, info, tone = "default", filled, order = 0 }: StatProps) {
  const textUnit = typeof unit === "string" || typeof unit === "number";
  const text = typeof value === "string" || typeof value === "number";
  return (
    <div className="ows-stat" data-filled={filled || undefined} style={{ "--k": order } as CSSProperties}>
      <Group gap={4} wrap="nowrap" className="ows-stat-head">
        <Text component="span" className="ows-stat-label">
          {label}
          {textUnit && ` ·\u00a0${unit}`}
        </Text>
        {info && (
          <Tooltip label={info}>
            <IconInfoCircle size={13} className="ows-info-icon" {...(typeof info === "string" ? { "aria-label": info } : { "aria-hidden": true })} />
          </Tooltip>
        )}
      </Group>
      <Group gap={6} align="baseline" wrap="nowrap">
        <Text component="div" c={toneColor[tone]} className="ows-num ows-stat-value" data-text={text || undefined}>
          {text ? <SwapText text={String(value)} delay={order * 60} /> : value}
        </Text>
        {unit && !textUnit && unit}
      </Group>
      {hint && (
        <Text size="xs" c="dimmed" className="ows-stat-hint">
          {hint}
        </Text>
      )}
    </div>
  );
}

/** Sizes of the values of a band, the type scale from the key figure down to the text (styles.css). */
const FIT = ["20", "17", "14.5"] as const;

/** A value of the band has a word wider than its tile (the words of a value otherwise go on
 * several lines); its characters measured, not the value leaving (ui/Motion.tsx). A value that
 * is not a text (a switch, a run state) keeps its own size. */
function tooWide(band: HTMLElement): boolean {
  for (const value of band.querySelectorAll<HTMLElement>(".ows-stat-value")) {
    const chars = value.querySelector<HTMLElement>(".ows-swap-in");
    if (chars && chars.getBoundingClientRect().width > value.getBoundingClientRect().width + 0.5) return true;
  }
  return false;
}

/** Every value of the band at the largest size where each word fits its tile; a band out of sight
 * (a closed fold) keeps its size until it is seen. Gives the width it was fitted to. */
function fit(band: HTMLElement): number {
  const width = band.clientWidth;
  if (!width) return 0;
  delete band.dataset.fit;
  for (const size of FIT) {
    if (!tooWide(band)) break;
    band.dataset.fit = size;
  }
  return width;
}

/** Figures in one band; `cols` as many on wide screens, or a column count per breakpoint */
export function StatGrid({ children, cols = 4 }: { children: ReactNode; cols?: number | Partial<Record<"base" | "xs" | "sm" | "md" | "lg" | "xl", number>> }) {
  const band = useRef<HTMLDivElement>(null);
  const shown = useRef<string | null>(null);
  const fitted = useRef(0);
  // New values: fitted before they are drawn
  useLayoutEffect(() => {
    const node = band.current;
    if (!node || node.textContent === shown.current) return;
    shown.current = node.textContent;
    fitted.current = fit(node);
  });
  // The band narrowed or widened (window, column, fold) or a font arrived: fitted again after the
  // observer's turn, a value going on more lines changing the band's height
  useEffect(() => {
    const node = band.current;
    if (!node || typeof ResizeObserver === "undefined") return;
    let later = 0;
    const again = () => {
      window.clearTimeout(later);
      later = window.setTimeout(() => { fitted.current = fit(node); });
    };
    const sizes = new ResizeObserver(([entry]) => { if (Math.abs(entry.contentRect.width - fitted.current) >= 1) again(); });
    sizes.observe(node);
    document.fonts.addEventListener("loadingdone", again);
    return () => { sizes.disconnect(); window.clearTimeout(later); document.fonts.removeEventListener("loadingdone", again); };
  }, []);
  return (
    <SimpleGrid ref={band} cols={typeof cols === "number" ? { base: 1, xs: 2, md: cols } : cols} spacing={0} className="ows-stat-grid">
      {children}
    </SimpleGrid>
  );
}

/** The state of a run as a word after a dot (green, beating while it runs; red when it failed). */
export function StateLine({ state, size = "sm" }: { state: RunState; size?: "xs" | "sm" | "md" }) {
  const t = useT(common);
  return (
    <span className="ows-state-line" data-size={size} data-state={state}>
      <span className="ows-state-dot" data-state={state} aria-hidden="true" />
      {t(`state.${state}`)}
    </span>
  );
}
