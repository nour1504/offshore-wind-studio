/**
 * Turbine curves: derived quantities, consistency checks and reading curves pasted from a
 * spreadsheet or a WRF wind-turbine-N.tbl. Pure functions, no texts: pages translate the codes.
 */
import type { Case, CurvePoint, Farm, TurbineType } from "../../../api/types";

/** Standard sea-level air density (kg/m³), the one the server uses for Cp */
export const AIR_DENSITY = 1.225;
/** No rotor extracts more than 16/27 of the kinetic energy flowing through its disc */
export const BETZ_LIMIT = 16 / 27;
/** Tolerance of the server check "the power curve exceeds the rated power" */
const RATED_TOLERANCE = 0.05;
/** Fraction of the rated power counted as reaching it */
const RATED_FRACTION = 0.995;

export function sweptArea(t: Pick<TurbineType, "rotor_diameter_m">): number {
  return Math.PI * (t.rotor_diameter_m / 2) ** 2;
}

/** Cp = P / (½ ρ A U³) */
export function powerCoefficient(t: Pick<TurbineType, "rotor_diameter_m">, p: CurvePoint): number {
  const area = sweptArea(t);
  if (p.wind_speed <= 0 || area <= 0) return 0;
  return (p.power_kw * 1000) / (0.5 * AIR_DENSITY * area * p.wind_speed ** 3);
}

export interface TurbineMetrics {
  area: number;
  /** Rated power per swept area, W/m² */
  specificPower: number | null;
  maxCp: number | null;
  maxCpSpeed: number | null;
  maxPowerKw: number;
  /** First wind speed with power */
  cutIn: number | null;
  /** First wind speed reaching the rated power */
  rated: number | null;
  /** Last wind speed with power */
  cutOut: number | null;
}

export function metrics(t: TurbineType): TurbineMetrics {
  const area = sweptArea(t);
  const producing = t.curve.filter((p) => p.power_kw > 0);
  const ratedKw = t.rated_power_mw * 1000;
  const rated = ratedKw > 0 ? t.curve.find((p) => p.power_kw >= RATED_FRACTION * ratedKw) : undefined;
  let maxCp: number | null = null;
  let maxCpSpeed: number | null = null;
  for (const p of t.curve) {
    const cp = powerCoefficient(t, p);
    if (maxCp === null || cp > maxCp) {
      maxCp = cp;
      maxCpSpeed = p.wind_speed;
    }
  }
  return {
    area,
    specificPower: area > 0 ? (t.rated_power_mw * 1e6) / area : null,
    maxCp,
    maxCpSpeed,
    maxPowerKw: Math.max(0, ...t.curve.map((p) => p.power_kw)),
    cutIn: producing[0]?.wind_speed ?? null,
    rated: rated?.wind_speed ?? null,
    cutOut: producing.at(-1)?.wind_speed ?? null,
  };
}

// ------------------------------------------------------------------ checks

export type Problem =
  | { code: "tooFew"; severity: "error" }
  | { code: "notIncreasing"; severity: "error"; rows: number[] }
  | { code: "negative"; severity: "error"; rows: number[] }
  | { code: "notFinite"; severity: "error"; rows: number[] }
  | { code: "characteristics"; severity: "error"; fields: CharacteristicField[] }
  | { code: "betz"; severity: "warning"; speeds: number[] }
  | { code: "aboveRated"; severity: "warning"; maxKw: number }
  | { code: "belowRated"; severity: "warning"; maxKw: number; ratedKw: number }
  | { code: "ctBelowCp"; severity: "warning"; speeds: number[] };

export type CharacteristicField = "rated_power_mw" | "rotor_diameter_m" | "hub_height_m" | "standing_thrust_coefficient";

/** Rows whose wind speed does not exceed the previous one (1-based row numbers) */
export function unorderedRows(curve: CurvePoint[]): number[] {
  const rows: number[] = [];
  for (let i = 1; i < curve.length; i += 1) {
    if (!(curve[i].wind_speed > curve[i - 1].wind_speed)) rows.push(i + 1);
  }
  return rows;
}

/**
 * Errors are what the server refuses (the project cannot be checked or saved with them);
 * warnings are the server checks of a turbine type, and a few signs of swapped columns.
 */
export function checkTurbine(t: TurbineType): Problem[] {
  const problems: Problem[] = [];
  const fields: CharacteristicField[] = [];
  if (!(t.rated_power_mw > 0)) fields.push("rated_power_mw");
  if (!(t.rotor_diameter_m > 0)) fields.push("rotor_diameter_m");
  if (!(t.hub_height_m > 0)) fields.push("hub_height_m");
  if (!(t.standing_thrust_coefficient >= 0)) fields.push("standing_thrust_coefficient");
  if (fields.length) problems.push({ code: "characteristics", severity: "error", fields });

  if (t.curve.length < 2) problems.push({ code: "tooFew", severity: "error" });
  const notFinite = t.curve
    .map((p, i) => ([p.wind_speed, p.power_kw, p.thrust_coefficient].every(Number.isFinite) ? 0 : i + 1))
    .filter(Boolean);
  if (notFinite.length) problems.push({ code: "notFinite", severity: "error", rows: notFinite });
  const negative = t.curve
    .map((p, i) => (p.wind_speed < 0 || p.power_kw < 0 || p.thrust_coefficient < 0 ? i + 1 : 0))
    .filter(Boolean);
  if (negative.length) problems.push({ code: "negative", severity: "error", rows: negative });
  const unordered = unorderedRows(t.curve);
  if (unordered.length) problems.push({ code: "notIncreasing", severity: "error", rows: unordered });

  if (t.rotor_diameter_m > 0 && t.curve.length) {
    const betz = t.curve.filter((p) => powerCoefficient(t, p) > BETZ_LIMIT).map((p) => p.wind_speed);
    if (betz.length) problems.push({ code: "betz", severity: "warning", speeds: betz });
    const swapped = t.curve
      .filter((p) => p.power_kw > 0 && p.thrust_coefficient < powerCoefficient(t, p))
      .map((p) => p.wind_speed);
    if (swapped.length && !betz.length) problems.push({ code: "ctBelowCp", severity: "warning", speeds: swapped });
  }
  if (t.rated_power_mw > 0 && t.curve.length) {
    const ratedKw = t.rated_power_mw * 1000;
    const maxKw = Math.max(...t.curve.map((p) => p.power_kw));
    if (maxKw > (1 + RATED_TOLERANCE) * ratedKw) problems.push({ code: "aboveRated", severity: "warning", maxKw });
    else if (maxKw < (1 - RATED_TOLERANCE) * ratedKw) problems.push({ code: "belowRated", severity: "warning", maxKw, ratedKw });
  }
  return problems;
}

export const hasErrors = (problems: Problem[]) => problems.some((p) => p.severity === "error");

/** The curve sorted by wind speed, rows with the same wind speed kept once (the first). */
export function sortedCurve(curve: CurvePoint[]): CurvePoint[] {
  const sorted = [...curve].sort((a, b) => a.wind_speed - b.wind_speed);
  return sorted.filter((p, i) => i === 0 || p.wind_speed !== sorted[i - 1].wind_speed);
}

// ------------------------------------------------------------- type usage

export interface FarmUsage {
  farm: Farm;
  /** Position of the farm in the project, which gives its colour on maps */
  index: number;
  count: number;
}

/** Type numbers used by the farms, with the turbines of each farm using them. */
export function typeUsage(c: Case): Map<number, FarmUsage[]> {
  const usage = new Map<number, FarmUsage[]>();
  c.farms.forEach((farm, index) => {
    const counts = new Map<number, number>();
    for (const t of farm.turbines) counts.set(t.type, (counts.get(t.type) ?? 0) + 1);
    for (const [type, count] of counts) {
      const list = usage.get(type) ?? [];
      list.push({ farm, index, count });
      usage.set(type, list);
    }
  });
  return usage;
}

/** The smallest type number neither defined nor used, from 2 (1 is WRF's own table). */
export function nextTypeNumber(c: Case, extra: number[] = []): number {
  // Type 1 is free unless defined or used (turbines of type 1 without a definition use WRF's table)
  const taken = new Set<number>([...Object.keys(c.turbine_types).map(Number), ...extra]);
  for (const farm of c.farms) for (const t of farm.turbines) taken.add(t.type);
  let n = 1;
  while (taken.has(n)) n += 1;
  return n;
}

/** Grid spacing (m) of each domain, from the parent ratios */
export function domainSpacing(c: Case): number[] {
  const dx: number[] = [];
  c.grid.domains.forEach((d, i) => {
    dx.push(i === 0 ? c.grid.dx : dx[d.parent_id - 1] / d.parent_grid_ratio);
  });
  return dx;
}

/** The finest grid where the wind farm scheme runs, or null without a scheme */
export function farmGrid(c: Case): { domain: number; dx: number } | null {
  if (!c.farm_scheme || c.farm_scheme.domains.length === 0) return null;
  const dx = domainSpacing(c);
  let best: { domain: number; dx: number } | null = null;
  for (const domain of c.farm_scheme.domains) {
    const spacing = dx[domain - 1];
    if (spacing !== undefined && (best === null || spacing < best.dx)) best = { domain, dx: spacing };
  }
  return best;
}

export function blankTurbine(name: string): TurbineType {
  return {
    name,
    hub_height_m: 120,
    rotor_diameter_m: 180,
    standing_thrust_coefficient: 0.1,
    rated_power_mw: 10,
    curve: [
      { wind_speed: 3, power_kw: 0, thrust_coefficient: 0.8 },
      { wind_speed: 11, power_kw: 10000, thrust_coefficient: 0.75 },
      { wind_speed: 25, power_kw: 10000, thrust_coefficient: 0.1 },
    ],
  };
}

// ---------------------------------------------------------- pasted curves

export type PowerUnit = "kW" | "MW" | "W";
const TO_KW: Record<PowerUnit, number> = { kW: 1, MW: 1000, W: 0.001 };
export type Column = "speed" | "power" | "ct";
/** A row read from a text, power still in the unit of the text */
export type Row = { wind_speed: number; power: number; thrust_coefficient: number };

export type ParsedCurve =
  | {
      ok: true;
      /** "table": columns from a spreadsheet or a CSV; "wrf": a wind-turbine-N.tbl */
      format: "table" | "wrf";
      rows: Row[];
      /** Column order found from a header line */
      header: Column[] | null;
      /** Unit of the power column named in the header, e.g. "Power (MW)" */
      headerUnit: PowerUnit | null;
      /** Turbine characteristics, given by a WRF table */
      characteristics?: Pick<TurbineType, "hub_height_m" | "rotor_diameter_m" | "standing_thrust_coefficient" | "rated_power_mw">;
    }
  | { ok: false; error: "empty" }
  | { ok: false; error: "tooFew" }
  | { ok: false; error: "line"; line: number; text: string };

interface Line {
  number: number;
  text: string;
}

function splitter(lines: Line[]): (text: string) => string[] {
  const sample = lines.slice(0, 20).map((l) => l.text);
  if (sample.some((l) => l.includes("\t"))) return (l) => l.split("\t");
  if (sample.some((l) => l.includes(";"))) return (l) => l.split(";");
  const numeric = sample.filter((l) => /\d/.test(l));
  // "3.5,120,0.8" separates with commas; "3,5 120 0,8" uses decimal commas
  if (numeric.length && numeric.every((l) => l.includes(",")) && (numeric.some((l) => /\d\.\d/.test(l)) || !numeric.some((l) => /\S\s+\S/.test(l)))) {
    return (l) => l.split(",");
  }
  return (l) => l.trim().split(/\s+/);
}

function toNumber(token: string): number | null {
  const text = token.trim().replace(/^["']|["']$/g, "").replace(/[\s  ]/g, "").replace(",", ".");
  if (text === "") return null;
  const value = Number(text);
  return Number.isFinite(value) ? value : null;
}

function columnOf(name: string): Column | null {
  const key = name.toLowerCase().trim();
  if (/(^|[^a-z])c_?t([^a-z]|$)|thrust|pouss/.test(key)) return "ct";
  // The power coefficient Cp, sometimes given, is not read
  if (/(^|[^a-z])c_?p([^a-z]|$)|coef/.test(key)) return null;
  if (/power|puiss|(^|[^a-z])(k|m)?w([^a-z/]|$)|^p([^a-z]|$)/.test(key)) return "power";
  if (/speed|wind|vitesse|vent|(^|[^a-z])(ws|u|v)([^a-z]|$)|m\/s/.test(key)) return "speed";
  return null;
}

function unitOf(name: string): PowerUnit | null {
  const key = name.toLowerCase();
  if (/(^|[^a-z])mw([^a-z]|$)/.test(key)) return "MW";
  if (/(^|[^a-z])kw([^a-z]|$)/.test(key)) return "kW";
  if (/[([]\s*w\s*[)\]]/.test(key)) return "W";
  return null;
}

/**
 * Reads columns pasted from a spreadsheet or a CSV: wind speed, power, Ct in that order, or in
 * any order with a header naming them; tab, semicolon, comma or space separated; decimal commas
 * accepted. Also reads a WRF wind-turbine-N.tbl (count, characteristics, then speed, Ct, kW).
 */
export function parseCurve(text: string): ParsedCurve {
  const lines: Line[] = text
    .split(/\r?\n/)
    .map((t, i) => ({ number: i + 1, text: t }))
    .filter((l) => l.text.trim() !== "" && !l.text.trim().startsWith("#"));
  if (lines.length === 0) return { ok: false, error: "empty" };
  const split = splitter(lines);
  const values = (l: Line) => split(l.text).filter((t) => t.trim() !== "").map(toNumber);

  // WRF table: one integer, then hub height, diameter, standing Ct and rated power
  const first = values(lines[0]);
  const second = lines[1] ? values(lines[1]) : [];
  if (
    first.length === 1 &&
    first[0] !== null &&
    Number.isInteger(first[0]) &&
    first[0] >= 2 &&
    second.length === 4 &&
    second.every((v) => v !== null)
  ) {
    const count = first[0];
    const body = lines.slice(2, 2 + count);
    const rows: Row[] = [];
    for (const line of body) {
      const [ws, ct, kw] = values(line);
      if (ws === null || ws === undefined || ct === null || ct === undefined || kw === null || kw === undefined) {
        return { ok: false, error: "line", line: line.number, text: line.text.trim() };
      }
      rows.push({ wind_speed: ws, power: kw, thrust_coefficient: ct });
    }
    if (rows.length < 2) return { ok: false, error: "tooFew" };
    const [hub, diameter, standing, rated] = second as number[];
    return {
      ok: true,
      format: "wrf",
      rows,
      header: null,
      headerUnit: "kW",
      characteristics: {
        hub_height_m: hub,
        rotor_diameter_m: diameter,
        standing_thrust_coefficient: standing,
        rated_power_mw: rated,
      },
    };
  }

  // Header: a first line with words; its column names give the order
  let header: Column[] | null = null;
  let headerUnit: PowerUnit | null = null;
  let order: [number, number, number] = [0, 1, 2];
  let body = lines;
  const firstTokens = split(lines[0].text).filter((t) => t.trim() !== "");
  if (firstTokens.some((t) => toNumber(t) === null)) {
    body = lines.slice(1);
    const columns = firstTokens.map(columnOf);
    const speed = columns.indexOf("speed");
    const power = columns.indexOf("power");
    const ct = columns.indexOf("ct");
    if (speed >= 0 && power >= 0 && ct >= 0) {
      order = [speed, power, ct];
      header = (["speed", "power", "ct"] as Column[]).sort((a, b) => columns.indexOf(a) - columns.indexOf(b));
      headerUnit = unitOf(firstTokens[power]);
    }
  }

  const rows: Row[] = [];
  for (const line of body) {
    const tokens = split(line.text).filter((t) => t.trim() !== "");
    const picked = order.map((i) => (i < tokens.length ? toNumber(tokens[i]) : null));
    if (picked.some((v) => v === null)) return { ok: false, error: "line", line: line.number, text: line.text.trim() };
    const [ws, power, ct] = picked as number[];
    rows.push({ wind_speed: ws, power, thrust_coefficient: ct });
  }
  if (rows.length < 2) return { ok: false, error: "tooFew" };
  return { ok: true, format: "table", rows, header, headerUnit };
}

/** Rows of a parsed text as curve points, power converted to kW. */
export function toCurve(rows: Row[], unit: PowerUnit): CurvePoint[] {
  return rows.map((r) => ({
    wind_speed: r.wind_speed,
    power_kw: Number((r.power * TO_KW[unit]).toPrecision(10)),
    thrust_coefficient: r.thrust_coefficient,
  }));
}
