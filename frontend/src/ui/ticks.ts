/** Round steps and ticks for the axes of the charts and the grids of the 3D views. */

/** A round step (1, 2, 2.5 or 5 × 10ⁿ) that cuts a span in about ``parts`` pieces. */
export function niceStep(span: number, parts = 4): number {
  const raw = span / parts;
  const power = 10 ** Math.floor(Math.log10(raw || 1));
  return [1, 2, 2.5, 5, 10].map((m) => m * power).find((s) => s >= raw) ?? 10 * power;
}

/** Decimals needed to write a step exactly (2.5 → 1, 0.25 → 2, 5 → 0). */
export function decimals(step: number): number {
  let digits = 0;
  while (digits < 6 && Math.abs(step * 10 ** digits - Math.round(step * 10 ** digits)) > 1e-6) digits += 1;
  return digits;
}

/** Round ticks covering [min, max]. */
export function niceAxis(min: number, max: number, parts = 4) {
  const span = max - min || Math.abs(max) || 1;
  const step = niceStep(span, parts);
  const lo = Math.floor(min / step) * step;
  const hi = Math.ceil(max / step) * step || step;
  const ticks = Array.from({ length: Math.round((hi - lo) / step) + 1 }, (_, k) => lo + k * step);
  return { lo, hi, step, ticks, digits: decimals(step) };
}
