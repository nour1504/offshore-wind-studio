/**
 * Navigation in the staircase, as pure functions. What is seen is a part of the period, in hours
 * from the first simulated instant: zooming in narrows it (it then fills the whole turn of the
 * spiral, so the windows become large steps), moving shifts it. It never leaves the period and
 * never becomes shorter than a few windows.
 */

export interface Range {
  t0: number;
  t1: number;
}

export interface Limits {
  span: number;
  /** The shortest part that can be seen, hours */
  shortest: number;
}

export const whole = (limits: Limits): Range => ({ t0: 0, t1: limits.span });

export function clampRange(range: Range, limits: Limits): Range {
  const length = Math.min(limits.span, Math.max(limits.shortest, range.t1 - range.t0));
  const t0 = Math.min(limits.span - length, Math.max(0, range.t0));
  return { t0, t1: t0 + length };
}

/** Narrow (factor > 1) or widen the part seen, keeping the hour `around` where it is. */
export function zoomRange(range: Range, factor: number, around: number, limits: Limits): Range {
  const share = (around - range.t0) / (range.t1 - range.t0);
  const length = Math.min(limits.span, Math.max(limits.shortest, (range.t1 - range.t0) / factor));
  return clampRange({ t0: around - share * length, t1: around - share * length + length }, limits);
}

/** Move by a share of the part seen (positive: later). */
export function shiftRange(range: Range, share: number, limits: Limits): Range {
  const by = share * (range.t1 - range.t0);
  return clampRange({ t0: range.t0 + by, t1: range.t1 + by }, limits);
}

/** The part that frames [h0, h1] with a margin on each side. */
export function frameHours(h0: number, h1: number, limits: Limits, margin = 0.08): Range {
  const pad = (h1 - h0) * margin;
  return clampRange({ t0: h0 - pad, t1: h1 + pad }, limits);
}

/** In between two parts: the length changes geometrically, the middle linearly. */
export function mixRange(a: Range, b: Range, t: number): Range {
  const la = a.t1 - a.t0;
  const lb = b.t1 - b.t0;
  const length = la * Math.pow(lb / la, t);
  const middle = (a.t0 + la / 2) + ((b.t0 + lb / 2) - (a.t0 + la / 2)) * t;
  return { t0: middle - length / 2, t1: middle + length / 2 };
}
