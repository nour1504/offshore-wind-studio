/**
 * The geometry of the spiral staircase, half 3D, half 2D. The part of the period seen turns once
 * around an empty centre (a little less than a full turn: from the front left, rising to the
 * back), seen slightly from above, so that circles become ellipses. Each window, month or year
 * is a step: a slab between the inner and the outer edge, its top at the height of the instant
 * it ends (heights follow time, so a month and its windows end at the same height), carried by a
 * curved stringer whose top follows the steps and whose lower edge rises smoothly from the
 * ground, as in an architect's drawing. The pieces at the back are drawn first, then those in
 * front, each set from the lowest to the highest (a higher step is nearer the eye).
 * Coordinates are pixels, y downwards.
 */
import type { Range } from "./view";

export interface Piece {
  front: boolean;
  /** The stringer under the step, its outer face (in front), the face where it starts, its top, the light edge of its nose */
  stringer: string;
  /** Lower edge of the stringer */
  under: string;
  side?: string;
  riser?: string;
  top: string;
  nose?: string;
}

export interface Item {
  key: string;
  index: number;
  h0: number;
  h1: number;
  /** Start of the spin-up of a window */
  s0?: number;
}

export interface Shape {
  key: string;
  index: number;
  z: number;
  pieces: Piece[];
  spin?: { d: string; front: boolean };
  /** Middle of the top face, for the label; share of the part seen where it starts */
  anchor: [number, number];
  at: number;
}

export interface Geometry {
  cx: number;
  cy: number;
  rIn: number;
  rOut: number;
  rise: number;
  thickness: number;
  shadow: string;
  rail: { d: string; front: boolean; from: number; to: number }[];
  /** Length of the outer edge for the whole part seen, px */
  sweepLength: number;
}

const TILT = 0.42;
const START = 0.8 * Math.PI;
const SWEEP = 0.86 * 2 * Math.PI;
const BAND = 26;

const fmt = ([x, y]: [number, number]) => `${x.toFixed(1)} ${y.toFixed(1)}`;
const polygon = (points: [number, number][]) => `M ${points.map(fmt).join(" L ")} Z`;

export function frame(width: number, height: number): Geometry {
  let rOut = Math.min(width * 0.36, 215);
  let rise = height - 2 * rOut * TILT - 24;
  if (rise < 130) {
    rOut = Math.max(70, (height - 24 - 130) / (2 * TILT));
    rise = height - 2 * rOut * TILT - 24;
  }
  const cx = width / 2;
  const cy = height - rOut * TILT - 8;
  const thickness = 9;
  const point = (r: number, a: number, z: number): [number, number] => [cx + r * Math.cos(a), cy + r * Math.sin(a) * TILT - z];
  const shadowR = rOut * 1.08;
  const shadow = `M ${fmt([cx - shadowR, cy])} A ${shadowR} ${shadowR * TILT} 0 1 0 ${fmt([cx + shadowR, cy])} A ${shadowR} ${shadowR * TILT} 0 1 0 ${fmt([cx - shadowR, cy])} Z`;
  const rail: Geometry["rail"] = [];
  const parts = 48;
  for (let n = 0; n < parts; n++) {
    const f0 = n / parts;
    const f1 = (n + 1) / parts;
    const points = Array.from({ length: 5 }, (_, i) => {
      const f = f0 + ((f1 - f0) * i) / 4;
      return point(rOut + 7, START - SWEEP * f, rise * f + thickness + 3);
    });
    rail.push({ d: `M ${points.map(fmt).join(" L ")}`, front: Math.sin(START - SWEEP * ((f0 + f1) / 2)) > 0, from: f0, to: f1 });
  }
  return { cx, cy, rIn: rOut * 0.5, rOut, rise, thickness, shadow, rail, sweepLength: rOut * SWEEP };
}

/** The steps of `items` in the part seen (clipped to it). */
export function slabs(items: Item[], range: Range, g: Geometry): Shape[] {
  const length = range.t1 - range.t0;
  const share = (h: number) => (h - range.t0) / length;
  const angle = (h: number) => START - SWEEP * share(h);
  const height = (h: number) => g.rise * share(h);
  const point = (r: number, a: number, z: number): [number, number] => [g.cx + r * Math.cos(a), g.cy + r * Math.sin(a) * TILT - z];
  const samples = (a0: number, a1: number) => Math.max(2, Math.ceil(Math.abs(a1 - a0) / (Math.PI / 60)) + 1);
  const arc = (r: number, a0: number, a1: number, z: (a: number) => number) => {
    const n = samples(a0, a1);
    return Array.from({ length: n }, (_, i) => {
      const a = a0 + ((a1 - a0) * i) / (n - 1);
      return point(r, a, z(a));
    });
  };
  const flat = (z: number) => () => z;
  // The lower edge of the stringer: the helix of time, a band below the steps, never under the ground
  const hourOf = (a: number) => range.t0 + ((START - a) / SWEEP) * length;
  const lower = (a: number) => Math.max(0, height(hourOf(a)) - BAND);
  const shapes: Shape[] = [];
  for (const item of items) {
    const h0 = Math.max(item.h0, range.t0);
    const h1 = Math.min(item.h1, range.t1);
    if (h1 <= h0) continue;
    const z = height(h1);
    // A thin gap before each step, so that the steps read apart
    const a0 = angle(h0) - Math.min(0.012, (angle(h0) - angle(h1)) * 0.08);
    const a1 = angle(h1);
    const th = Math.min(g.thickness, Math.max(2.5, z * 0.5));
    const cuts = [a0];
    for (let k = Math.floor(a0 / Math.PI); k * Math.PI > a1; k--) if (k * Math.PI < a0) cuts.push(k * Math.PI);
    cuts.push(a1);
    const pieces: Piece[] = [];
    for (let n = 0; n < cuts.length - 1; n++) {
      const [p, q] = [cuts[n], cuts[n + 1]];
      const front = Math.sin((p + q) / 2) > 0;
      const outer = arc(g.rOut, p, q, flat(z));
      const r = front ? g.rOut : g.rIn;
      const bottom = arc(r, q, p, (a) => Math.min(z - th, lower(a)));
      const piece: Piece = {
        front,
        stringer: polygon([...arc(r, p, q, flat(z - th)), ...bottom]),
        under: `M ${bottom.map(fmt).join(" L ")}`,
        top: polygon([...outer, ...arc(g.rIn, q, p, flat(z))]),
      };
      if (front) {
        piece.side = polygon([...outer, ...arc(g.rOut, q, p, flat(z - th))]);
        piece.nose = `M ${outer.map(fmt).join(" L ")}`;
      }
      if (n === 0) piece.riser = polygon([point(g.rIn, p, z), point(g.rOut, p, z), point(g.rOut, p, z - th), point(g.rIn, p, z - th)]);
      pieces.push(piece);
    }
    let spin: Shape["spin"];
    if (item.s0 !== undefined && item.s0 < h0) {
      const s = angle(Math.max(item.s0, range.t0));
      if (s > a0) spin = { d: polygon([...arc(g.rOut * 1.02, s, a0, flat(z + 1)), ...arc(g.rOut * 0.8, a0, s, flat(z + 1))]), front: Math.sin((s + a0) / 2) > 0 };
    }
    shapes.push({ key: item.key, index: item.index, z, pieces, spin, anchor: point((g.rIn + g.rOut) / 2, (a0 + a1) / 2, z), at: share(h0) });
  }
  return shapes;
}

/** The part drawn around the turn for the part seen: itself, or, for a short period, a part long
    enough for eight usual windows with the period in its middle, in front, so that a single
    window is a single step and not a whole ring. */
export function drawn(range: Range, typical: number): Range {
  const length = range.t1 - range.t0;
  const least = 8 * typical;
  if (length >= least) return range;
  const front = (START - Math.PI / 2) / SWEEP;
  const t0 = (range.t0 + range.t1) / 2 - front * least;
  return { t0, t1: t0 + least };
}

/** The hour under a point: the nearest place of the steps' middle line, or null far from it. */
export function hourAt(sx: number, sy: number, range: Range, g: Geometry): number | null {
  let best = Infinity;
  let found: number | null = null;
  const r = (g.rIn + g.rOut) / 2;
  for (let n = 0; n <= 160; n++) {
    const f = n / 160;
    const a = START - SWEEP * f;
    const x = g.cx + r * Math.cos(a);
    const y = g.cy + r * Math.sin(a) * TILT - g.rise * f;
    const d = Math.hypot(x - sx, y - sy);
    if (d < best) {
      best = d;
      found = range.t0 + f * (range.t1 - range.t0);
    }
  }
  return best < g.rOut ? found : null;
}
