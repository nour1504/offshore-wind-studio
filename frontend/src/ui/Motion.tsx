/**
 * Small pieces of motion used across the interface: a number that runs to its new value instead
 * of jumping (key figures), a row whose items glide to their new places, with the same curve as
 * the rest (motion.ts). Lists that arrive one item after the other use the CSS class
 * "ows-stagger" (styles.css).
 */
import { VisuallyHidden } from "@mantine/core";
import { type CSSProperties, type ReactNode, useEffect, useLayoutEffect, useRef, useState } from "react";

import { DURATION, EASE_OUT, easeOutMap, prefersReducedMotion } from "../motion";

/** Characters of a value, each in its own span (a long text stays whole), those of a word held
 * together with the space after it: a value too wide for its tile goes on several lines between
 * its words only (ui/Stat.tsx). */
function Chars({ text, className, after }: { text: string; className: string; after?: number }) {
  const whole = text.length > 24;
  const words = whole ? [text] : (text.match(/[^ ]+ *| +/g) ?? []);
  let at = 0;
  return (
    <span className={className} aria-hidden="true" style={after === undefined ? undefined : ({ "--after": `${after}ms` } as CSSProperties)}>
      {words.map((word, w) => (
        <span key={w} className="ows-swap-word">
          {(whole ? [word] : [...word]).map((part) => {
            const i = at++;
            return <span key={i} style={{ "--i": i } as CSSProperties}>{part}</span>;
          })}
        </span>
      ))}
    </span>
  );
}

/**
 * A value that changes character by character (motion book): the old characters leave upwards
 * into a blur one after the other, then the new ones come up into focus (240 ms later, plus
 * `delay` to stagger several values). The first value comes in the same way. Screen readers read
 * the value once.
 */
export function SwapText({ text, delay = 0 }: { text: string; delay?: number }) {
  const [state, setState] = useState({ text, old: "", n: 0 });
  if (state.text !== text) setState({ text, old: state.text, n: state.n + 1 });
  return (
    <span className="ows-swap">
      <VisuallyHidden>{text}</VisuallyHidden>
      {state.n > 0 && <Chars key={`o${state.n}`} text={state.old} className="ows-swap-out" after={delay} />}
      <Chars key={`n${state.n}`} text={text} className="ows-swap-in" after={state.n > 0 ? delay + 240 : 0} />
    </span>
  );
}

/** The value shown while it runs from the previous one to `value` (about 400 ms). */
export function useRunningNumber(value: number, duration = DURATION.large + 80): number {
  const [shown, setShown] = useState(value);
  const from = useRef(value);
  useEffect(() => {
    const start = from.current;
    if (start === value || prefersReducedMotion() || !Number.isFinite(start) || !Number.isFinite(value)) {
      from.current = value;
      setShown(value);
      return;
    }
    const began = performance.now();
    let frame = 0;
    const step = (now: number) => {
      const t = Math.min(1, (now - began) / duration);
      const current = start + (value - start) * easeOutMap(t);
      from.current = current;
      setShown(current);
      if (t < 1) frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [value, duration]);
  return shown;
}

/**
 * A row of items that keeps its continuity when the items change: the items still there glide
 * to their new place (layout animation), new ones arrive with a short fade, removed ones fade
 * out before they leave (presence). Nothing moves for people who reduce animations.
 */
export function FlipRow<T>({ items, keyOf, render, className }: { items: readonly T[]; keyOf: (item: T) => string; render: (item: T) => ReactNode; className?: string }) {
  const [shown, setShown] = useState(() => items.map((item) => ({ item, leaving: false })));
  const signature = items.map(keyOf).join("|");
  // Removed items stay in place while they fade out, then the others close the gap
  useEffect(() => {
    setShown((before) => {
      const kept = new Set(items.map(keyOf));
      const next = items.map((item) => ({ item, leaving: false }));
      before.forEach((entry, index) => {
        if (!kept.has(keyOf(entry.item))) next.splice(Math.min(index, next.length), 0, { item: entry.item, leaving: true });
      });
      return next;
    });
    const id = window.setTimeout(() => setShown((now) => now.filter((entry) => !entry.leaving)), prefersReducedMotion() ? 0 : DURATION.state);
    return () => window.clearTimeout(id);
    // The keys say when the items changed
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature]);
  const row = useRef<HTMLDivElement>(null);
  const places = useRef(new Map<string, number>());
  const layout = shown.map((entry) => `${keyOf(entry.item)}${entry.leaving ? "-" : ""}`).join("|");
  useLayoutEffect(() => {
    const box = row.current;
    if (!box) return;
    const reduced = prefersReducedMotion();
    const origin = box.getBoundingClientRect().left - box.scrollLeft;
    for (const child of Array.from(box.children) as HTMLElement[]) {
      const key = child.dataset.key ?? "";
      const left = child.getBoundingClientRect().left - origin;
      const before = places.current.get(key);
      if (!reduced && child.dataset.leaving === undefined) {
        if (before === undefined) child.animate([{ opacity: 0, transform: "scale(0.94)" }, { opacity: 1, transform: "none" }], { duration: DURATION.state, easing: EASE_OUT });
        else if (Math.abs(before - left) > 0.5) child.animate([{ transform: `translateX(${before - left}px)` }, { transform: "none" }], { duration: DURATION.large, easing: EASE_OUT });
      }
      places.current.set(key, left);
    }
    // Only when the items or their order changed
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [layout]);
  return (
    <div ref={row} className={className}>
      {shown.map(({ item, leaving }) => (
        <div key={keyOf(item)} data-key={keyOf(item)} data-leaving={leaving || undefined} className="ows-flip-item">{render(item)}</div>
      ))}
    </div>
  );
}
