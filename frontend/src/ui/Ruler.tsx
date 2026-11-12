/**
 * A ruler of ticks under a chart or a time slider: the ticks near the pointer swell, as through a
 * lens, and the tick of the step shown stays marked. It lines up under the element named by
 * `under` (the chart's plot, the slider's track), measured again when the host resizes.
 */
import { type RefObject, useEffect, useRef } from "react";

const TICKS = 72;

export function Ruler({ host, under, at = null }: { host: RefObject<HTMLElement | null>; under: string; at?: number | null }) {
  const ruler = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const box = host.current, line = ruler.current;
    if (!box || !line) return;
    const ticks = Array.from(line.children) as HTMLElement[];
    let frame = 0;
    const align = () => {
      const target = box.querySelector(under)?.getBoundingClientRect();
      const parent = line.parentElement?.getBoundingClientRect();
      if (!target?.width || !parent) return;
      line.style.marginLeft = `${target.left - parent.left}px`;
      line.style.width = `${target.width}px`;
    };
    const set = (x: number | null) => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        const r = line.getBoundingClientRect();
        ticks.forEach((tick, k) => {
          const near = x === null ? 0 : Math.max(0, 1 - Math.abs(r.left + ((k + 0.5) / ticks.length) * r.width - x) / 64);
          tick.style.setProperty("--near", near.toFixed(3));
        });
      });
    };
    const move = (event: PointerEvent) => set(event.clientX);
    const leave = () => set(null);
    const sizes = new ResizeObserver(() => requestAnimationFrame(align));
    sizes.observe(box);
    box.addEventListener("pointermove", move);
    box.addEventListener("pointerleave", leave);
    return () => {
      cancelAnimationFrame(frame);
      sizes.disconnect();
      box.removeEventListener("pointermove", move);
      box.removeEventListener("pointerleave", leave);
    };
  }, [host, under]);
  const current = at === null || !Number.isFinite(at) ? -1 : Math.round(Math.min(1, Math.max(0, at)) * (TICKS - 1));
  return (
    <div ref={ruler} className="ows-ruler" aria-hidden="true">
      {Array.from({ length: TICKS }, (_, k) => <span key={k} data-major={k % 6 === 0 || undefined} data-current={k === current || undefined} />)}
    </div>
  );
}
