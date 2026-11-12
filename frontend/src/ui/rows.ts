import { type UIEvent, useEffect, useState } from "react";

/**
 * The rows of a long list drawn at a time: those in view and a few around them; the others stand
 * as empty space above (`before`) and below (`after`), in pixels. `onScroll` goes on the scrolling
 * element.
 */
export function useRowsInView(count: number, row: number, view: number, margin: number) {
  const [top, setTop] = useState(0);
  const first = Math.max(0, Math.floor(top / row) - margin);
  const last = Math.min(count, Math.ceil((top + view) / row) + margin);
  return {
    first,
    last,
    before: first * row,
    after: Math.max(0, count - last) * row,
    onScroll: (event: UIEvent<HTMLElement>) => setTop(event.currentTarget.scrollTop),
  };
}

/**
 * The rows of a long list in the page drawn so far: the first ones, then more each time the end of
 * those comes near the view, so a list of thousands opens at once whatever the height of its rows.
 * `end` goes on an element after the list.
 */
export function useRowsAsScrolled(count: number, step = 120) {
  const [shown, setShown] = useState(step);
  const [end, setEnd] = useState<Element | null>(null);
  useEffect(() => {
    if (!end || shown >= count) return;
    const seen = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) setShown((n) => n + step);
    }, { rootMargin: "0px 0px 1200px 0px" });
    seen.observe(end);
    return () => seen.disconnect();
  }, [end, shown, count, step]);
  return { shown: Math.min(shown, count), end: setEnd };
}
