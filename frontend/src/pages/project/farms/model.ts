/** Pure helpers of the wind farms page: identifiers, colours, capacities, spacing, layouts. */
import { type GenericTurbine, WRF_GENERIC_TYPE } from "../../../api/farms";
import type { Case, Farm, FarmScheme, FeatureCollection, Issue, Turbine } from "../../../api/types";
import { farmAppearance } from "../../../ui/map/farms";

export const FARM_ID_PATTERN = /^[A-Za-z0-9_-]{1,32}$/;
export const FARM_NAME_MAX = 80;
const EARTH_RADIUS_M = 6_371_000;

/** Defaults of WRF 4.8 (Registry.EM_COMMON) for the wind farm options. */
export const SCHEME_DEFAULTS = {
  tke_factor: 0.25,
  induction: true,
  wake_model: 2,
  overlap_method: 4,
} as const satisfies Partial<FarmScheme>;

export function farmColor(index: number, farm?: Farm): string {
  return farmAppearance(farm ?? {}, index).color;
}

/** Label shown on maps and in results; the server names unlabelled turbines "<farm>-<n>". */
export function turbineLabel(farm: Farm, index: number): string {
  return farm.turbines[index]?.id || `${farm.id}-${index + 1}`;
}

/** An identifier derived from a name, unique among the given ones. */
export function idFromName(name: string, taken: string[]): string {
  const base =
    name
      .normalize("NFD")
      .replace(/[̀-ͯ]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9_-]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 32) || "farm";
  if (!taken.includes(base)) return base;
  for (let n = 2; ; n += 1) {
    const suffix = `-${n}`;
    const candidate = `${base.slice(0, 32 - suffix.length)}${suffix}`;
    if (!taken.includes(candidate)) return candidate;
  }
}

/** The value of a namelist option on one domain: lists are per domain, scalars apply to all. */
export function valueForDomain(value: unknown, domain: number): unknown {
  if (Array.isArray(value)) return domain <= value.length ? value[domain - 1] : undefined;
  return value;
}

export function newScheme(kind: FarmScheme["scheme"], c: Case, previous: FarmScheme | null): FarmScheme {
  const count = c.grid.domains.length;
  const domains = previous?.domains.filter((n) => n >= 1 && n <= count) ?? [];
  return {
    scheme: kind,
    domains: domains.length ? domains : [count],
    tke_factor: previous?.tke_factor ?? SCHEME_DEFAULTS.tke_factor,
    // Options of the other scheme go back to their defaults: WRF would ignore them anyway
    induction: kind === "fitch" ? (previous?.induction ?? SCHEME_DEFAULTS.induction) : SCHEME_DEFAULTS.induction,
    wake_model: kind === "mav" ? (previous?.wake_model ?? SCHEME_DEFAULTS.wake_model) : SCHEME_DEFAULTS.wake_model,
    overlap_method:
      kind === "mav" ? (previous?.overlap_method ?? SCHEME_DEFAULTS.overlap_method) : SCHEME_DEFAULTS.overlap_method,
  };
}

export interface TypeInfo {
  number: number;
  name: string;
  ratedMw: number | null;
  rotorM: number | null;
  /** Defined in the project (false for WRF's generic table and for unknown types) */
  custom: boolean;
  known: boolean;
}

/** Turbine models a turbine can use: those of the project, WRF's generic type 1 when turbines use it, and any unknown type in use. */
export function turbineTypes(c: Case, generic: GenericTurbine): Map<number, TypeInfo> {
  const types = new Map<number, TypeInfo>();
  for (const [key, t] of Object.entries(c.turbine_types)) {
    const number = Number(key);
    types.set(number, {
      number,
      name: t.name,
      ratedMw: t.rated_power_mw,
      rotorM: t.rotor_diameter_m,
      custom: true,
      known: true,
    });
  }
  if (!types.has(WRF_GENERIC_TYPE) && c.farms.some((farm) => farm.turbines.some((t) => t.type === WRF_GENERIC_TYPE))) {
    types.set(WRF_GENERIC_TYPE, {
      number: WRF_GENERIC_TYPE,
      name: generic.name,
      ratedMw: generic.rated_power_mw,
      rotorM: generic.rotor_diameter_m,
      custom: false,
      known: true,
    });
  }
  for (const farm of c.farms) {
    for (const t of farm.turbines) {
      if (!types.has(t.type)) {
        types.set(t.type, { number: t.type, name: "", ratedMw: null, rotorM: null, custom: false, known: false });
      }
    }
  }
  return new Map([...types.entries()].sort((a, b) => a[0] - b[0]));
}

export interface FarmSummary {
  turbines: number;
  installedMw: number;
  /** Turbines whose model is not defined: not counted in the capacity */
  unknown: number;
  /** Count of turbines per model number, most used first */
  types: [number, number][];
}

export function summarize(farm: Farm, types: Map<number, TypeInfo>): FarmSummary {
  let installedMw = 0;
  let unknown = 0;
  const counts = new Map<number, number>();
  for (const t of farm.turbines) {
    counts.set(t.type, (counts.get(t.type) ?? 0) + 1);
    const rated = types.get(t.type)?.ratedMw;
    if (rated === null || rated === undefined) unknown += 1;
    else installedMw += rated;
  }
  return {
    turbines: farm.turbines.length,
    installedMw,
    unknown,
    types: [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0] - b[0]),
  };
}

/** The model most used in a farm, for new turbines. */
export function usualType(farm: Farm | undefined, types: Map<number, TypeInfo>): number {
  const counts = new Map<number, number>();
  for (const t of farm?.turbines ?? []) counts.set(t.type, (counts.get(t.type) ?? 0) + 1);
  const best = [...counts.entries()].sort((a, b) => b[1] - a[1])[0];
  if (best) return best[0];
  const known = [...types.values()].find((t) => t.known);
  return known?.number ?? WRF_GENERIC_TYPE;
}

export function centroid(points: { lat: number; lon: number }[]): { lat: number; lon: number } | null {
  if (!points.length) return null;
  return {
    lat: points.reduce((s, p) => s + p.lat, 0) / points.length,
    lon: points.reduce((s, p) => s + p.lon, 0) / points.length,
  };
}

/** Centre of the innermost domain, from the map geometry; the projection centre otherwise. */
export function innermostCentre(c: Case, geometry: FeatureCollection | undefined): { lat: number; lon: number } {
  const domains = (geometry?.features ?? []).filter((f) => f.properties.kind === "domain" && f.geometry.type === "Polygon");
  const inner = domains.sort((a, b) => (b.properties.number ?? 0) - (a.properties.number ?? 0))[0];
  if (inner && inner.geometry.type === "Polygon") {
    const ring = inner.geometry.coordinates[0];
    const centre = centroid(ring.map(([lon, lat]) => ({ lat, lon })));
    if (centre) return centre;
  }
  return { lat: c.grid.projection.ref_lat, lon: c.grid.projection.ref_lon };
}

/** A point moved by a distance east and north, metres. */
export function offset(point: { lat: number; lon: number }, east: number, north: number): { lat: number; lon: number } {
  const lat = point.lat + ((north / EARTH_RADIUS_M) * 180) / Math.PI;
  const lon = point.lon + ((east / (EARTH_RADIUS_M * Math.cos((point.lat * Math.PI) / 180))) * 180) / Math.PI;
  return { lat: round6(lat), lon: round6(lon) };
}

export function round6(value: number): number {
  return Math.round(value * 1e6) / 1e6;
}

/** Where a new turbine goes: next to the last one of the farm, or at the centre of the innermost domain. */
export function nextPosition(farm: Farm, fallback: { lat: number; lon: number }, spacingM: number | null): { lat: number; lon: number } {
  const last = farm.turbines.at(-1);
  if (!last) return { lat: round6(fallback.lat), lon: round6(fallback.lon) };
  return offset(last, spacingM && Number.isFinite(spacingM) ? spacingM : 800, 0);
}

export interface GridSpec {
  lat: number;
  lon: number;
  rows: number;
  columns: number;
  /** Distance between neighbouring turbines of a row, metres */
  spacing: number;
  /** Distance between neighbouring rows, metres (the spacing by default) */
  across?: number;
  /** Orientation of the rows, degrees clockwise from east (as the server's zone layouts) */
  rotation: number;
  /** Every other row shifted by this share of the spacing (0.5: staggered) */
  stagger?: number;
}

/** A regular layout of rows and columns centred on a point. */
export function gridLayout(spec: GridSpec): { lat: number; lon: number }[] {
  const rot = (-spec.rotation * Math.PI) / 180;
  const across = spec.across ?? spec.spacing;
  const shift = (spec.stagger ?? 0) * spec.spacing;
  const points: { lat: number; lon: number }[] = [];
  for (let r = 0; r < spec.rows; r += 1) {
    for (let col = 0; col < spec.columns; col += 1) {
      const x = (col - (spec.columns - 1) / 2) * spec.spacing + (r % 2) * shift - (spec.rows > 1 ? shift / 2 : 0);
      const y = ((spec.rows - 1) / 2 - r) * across;
      points.push(offset(spec, x * Math.cos(rot) - y * Math.sin(rot), x * Math.sin(rot) + y * Math.cos(rot)));
    }
  }
  return points;
}

export function newTurbine(lat: number, lon: number, type: number, id: string | null = null): Turbine {
  return { lat: round6(lat), lon: round6(lon), type, id };
}

/** What the server would refuse when saving (it then checks nothing): found here first. */
export type LocalProblem =
  | { kind: "emptyFarm"; farm: Farm }
  | { kind: "badId"; farm: Farm }
  | { kind: "duplicateId"; id: string }
  | { kind: "noName"; farm: Farm }
  | { kind: "noDomain" };

export function localProblems(c: Case): LocalProblem[] {
  const problems: LocalProblem[] = [];
  const ids = c.farms.map((f) => f.id);
  for (const farm of c.farms) {
    if (!FARM_ID_PATTERN.test(farm.id)) problems.push({ kind: "badId", farm });
    if (!farm.name.trim() || farm.name.length > FARM_NAME_MAX) problems.push({ kind: "noName", farm });
    if (farm.turbines.length === 0) problems.push({ kind: "emptyFarm", farm });
  }
  for (const id of new Set(ids.filter((id, i) => ids.indexOf(id) !== i))) problems.push({ kind: "duplicateId", id });
  if (c.farm_scheme && c.farm_scheme.domains.length === 0) problems.push({ kind: "noDomain" });
  return problems;
}

/**
 * A copy the server accepts while the farms are being edited (a new farm without turbines yet,
 * an identifier being typed), so that the map keeps following the edits.
 */
export function forMap(c: Case): Case {
  const seen = new Set<string>();
  const farms = c.farms.filter((farm) => {
    const ok = farm.turbines.length > 0 && FARM_ID_PATTERN.test(farm.id) && !seen.has(farm.id);
    seen.add(farm.id);
    return ok;
  });
  const count = c.grid.domains.length;
  let scheme = c.farm_scheme;
  if (scheme) {
    const domains = scheme.domains.filter((n) => n >= 1 && n <= count);
    scheme = { ...scheme, domains: domains.length ? domains : [count] };
  }
  return {
    ...c,
    farms: farms.map((farm) => ({
      ...farm,
      name: farm.name.trim() ? farm.name.slice(0, FARM_NAME_MAX) : farm.id,
    })),
    farm_scheme: scheme,
  };
}

// Messages of the server's checks that concern this page (they are written in English)
const FARM_WORDS = [
  "farm",
  "Farm",
  "turbine",
  "Turbine",
  "rotor",
  "bl_pbl_physics",
  "bl_mynn_tkeadvect",
  "induction",
  "wake",
  "superposition",
  "Fitch",
  "MAV",
];

export function farmIssues(issues: Issue[]): Issue[] {
  return issues.filter((i) => !i.message.startsWith("Time series") && FARM_WORDS.some((w) => i.message.includes(w)));
}

