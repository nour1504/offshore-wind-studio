/**
 * The data of the staircase, from the server's plan (core/method/plan.py), the only source of
 * truth: one step per calculation window, rising one unit per window in chronological order,
 * and the visual groups (calendar months and years) of the far views. Positions are in hours
 * from the first simulated instant (D − S); nothing here changes the plan.
 */
import type { PlannedWindow, WindowPlan } from "../../../../api/method";
import { parseUtc } from "../../../../i18n";

const HOUR = 3.6e6;

export interface Step {
  window: PlannedWindow;
  /** Chronological position, 0 = earliest */
  index: number;
  /** Simulation start (spin-up), useful start and useful end, hours from the origin */
  s0: number;
  x0: number;
  x1: number;
  /** Height of the step: index + 1 */
  y: number;
}

export interface Group {
  key: string;
  kind: "month" | "year";
  /** UTC start of the month or year, ms */
  time: number;
  /** Steps first..last (chronological indexes) */
  first: number;
  last: number;
  x0: number;
  x1: number;
  /** From the height before its first step to the height of its last one */
  y0: number;
  y1: number;
}

export interface Stairs {
  /** First simulated instant (D − S), ms */
  origin: number;
  /** Hours from the origin to the end F */
  span: number;
  spinUp: number;
  count: number;
  steps: Step[];
  months: Group[];
  years: Group[];
  /** Usual useful length of a window (the longest), hours */
  typical: number;
}

const ms = (iso: string) => parseUtc(iso).getTime();

function groups(steps: Step[], origin: number, kind: Group["kind"]): Group[] {
  const out: Group[] = [];
  for (const step of steps) {
    const date = new Date(origin + step.x0 * HOUR);
    const time = kind === "month" ? Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), 1) : Date.UTC(date.getUTCFullYear(), 0, 1);
    const last = out[out.length - 1];
    if (last && last.time === time) {
      last.last = step.index;
      last.x1 = step.x1;
      last.y1 = step.y;
    } else {
      out.push({ key: `${kind}-${time}`, kind, time, first: step.index, last: step.index, x0: step.x0, x1: step.x1, y0: step.y - 1, y1: step.y });
    }
  }
  return out;
}

export function buildStairs(plan: WindowPlan): Stairs {
  const origin = ms(plan.start) - plan.spin_up_hours * HOUR;
  const hours = (iso: string) => (ms(iso) - origin) / HOUR;
  const steps = plan.windows.map((window, index) => ({
    window,
    index,
    s0: hours(window.simulation_start),
    x0: hours(window.useful_start),
    x1: hours(window.useful_end),
    y: index + 1,
  }));
  return {
    origin,
    span: hours(plan.end),
    spinUp: plan.spin_up_hours,
    count: steps.length,
    steps,
    months: groups(steps, origin, "month"),
    years: groups(steps, origin, "year"),
    typical: Math.max(...steps.map((s) => s.x1 - s.x0)),
  };
}

/** The steps whose useful hours meet [from, to] (hours), by bisection: the steps are sorted. */
export function visibleRange(steps: { x0: number; x1: number }[], from: number, to: number): [number, number] {
  let lo = 0;
  let hi = steps.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (steps[mid].x1 < from) lo = mid + 1;
    else hi = mid;
  }
  let end = lo;
  while (end < steps.length && steps[end].x0 <= to) end++;
  return [lo, end];
}
