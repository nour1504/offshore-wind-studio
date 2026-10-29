/**
 * WRF grid geometry in the browser, following owstudio.core.domains.geometry (itself following
 * WPS geogrid): Lambert conformal and Mercator projections on a sphere of 6370 km, domain
 * extents in projection-plane metres, and the placement of nests from a clicked point.
 *
 * The outer domain is centred on (ref_lat, ref_lon); a nest's south-west corner lies on the
 * corner of parent cell (i_parent_start, j_parent_start), counted from 1.
 */
import type { Grid, MapProj, NamelistGroups, NamelistValue, Projection } from "../../../api/types";

export const EARTH_RADIUS_M = 6_370_000;
/** Cells kept between a nest and its parent's edges when placing it: WRF's boundary zone (spec_bdy_width) */
export const NEST_MARGIN = 5;
/** Smallest domain: the boundary zone takes five cells on each side */
export const MIN_POINTS = 10;
/** Below this, a domain is mostly boundary zone */
export const SMALL_POINTS = 30;
/** WRF two-digit domain file names d01…d99. */
export const MAX_DOMAINS = 99;
/** Nests finer than this resolve convection: the cumulus scheme is switched off */
export const CUMULUS_OFF_AT_M = 4000;
/** Projections the browser can draw and place domains with */
export const PLACEABLE: MapProj[] = ["lambert", "mercator"];
/** Map scale factors further than this from 1 waste resolution */
export const MAP_FACTOR_TOLERANCE = 0.1;
/** WRF's rule for real-data cases: at most about 6 s of time step per km of grid spacing
    (reasonable_time_step_ratio stops d01 above it); the server checks the same rule */
export const MAX_TIME_STEP_S_PER_KM = 6;
/** The time step written when the project leaves it automatic (owstudio.core.namelist.generate) */
export const AUTO_TIME_STEP_S_PER_KM = 5;
/** Below this the computation takes at least twice as long as needed */
export const SLOW_TIME_STEP_S_PER_KM = 3;

export const domainName = (index: number) => `d${String(index + 1).padStart(2, "0")}`;

const rad = (d: number) => (d * Math.PI) / 180;
const deg = (r: number) => (r * 180) / Math.PI;
/** An angle in radians wrapped to [-π, π) */
const wrap = (a: number) => ((((a + Math.PI) % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI)) - Math.PI;
const round = (value: number, digits: number) => Number(value.toFixed(digits));

export interface PlaneProjection {
  /** (x, y) in metres on the projection plane */
  forward(lat: number, lon: number): [number, number];
  /** (lat, lon) in degrees */
  inverse(x: number, y: number): [number, number];
  /** Grid distance divided by the true distance at a latitude (map scale factor) */
  scale(lat: number): number;
}

function lambert(truelat1: number, truelat2: number, standLon: number): PlaneProjection | null {
  // Southern hemisphere cones are the mirror image of northern ones
  const hemi = truelat1 >= 0 ? 1 : -1;
  const phi1 = rad(hemi * truelat1);
  const phi2 = rad(hemi * truelat2);
  const n =
    Math.abs(phi1 - phi2) < 1e-6
      ? Math.sin(phi1)
      : Math.log(Math.cos(phi1) / Math.cos(phi2)) / Math.log(Math.tan(Math.PI / 4 + phi2 / 2) / Math.tan(Math.PI / 4 + phi1 / 2));
  if (!Number.isFinite(n) || Math.abs(n) < 1e-6) return null;
  const f = (Math.cos(phi1) * Math.tan(Math.PI / 4 + phi1 / 2) ** n) / n;
  if (!Number.isFinite(f)) return null;
  const lon0 = rad(standLon);
  return {
    forward(lat, lon) {
      const phi = rad(hemi * lat);
      const rho = (EARTH_RADIUS_M * f) / Math.tan(Math.PI / 4 + phi / 2) ** n;
      const theta = n * wrap(rad(lon) - lon0);
      return [rho * Math.sin(theta), -hemi * rho * Math.cos(theta)];
    },
    inverse(x, y) {
      const yy = hemi * y;
      const rho = Math.hypot(x, yy);
      const theta = Math.atan2(x, -yy);
      const phi = 2 * Math.atan(((EARTH_RADIUS_M * f) / rho) ** (1 / n)) - Math.PI / 2;
      return [hemi * deg(phi), deg(wrap(lon0 + theta / n))];
    },
    scale(lat) {
      const phi = rad(hemi * lat);
      return (n * f) / (Math.cos(phi) * Math.tan(Math.PI / 4 + phi / 2) ** n);
    },
  };
}

function mercator(truelat1: number, refLon: number): PlaneProjection | null {
  const k = EARTH_RADIUS_M * Math.cos(rad(truelat1));
  if (!(k > 0)) return null;
  const lon0 = rad(refLon);
  return {
    forward: (lat, lon) => [k * wrap(rad(lon) - lon0), k * Math.log(Math.tan(Math.PI / 4 + rad(lat) / 2))],
    inverse: (x, y) => [deg(2 * Math.atan(Math.exp(y / k)) - Math.PI / 2), deg(wrap(lon0 + x / k))],
    scale: (lat) => Math.cos(rad(truelat1)) / Math.cos(rad(lat)),
  };
}

/** The plane projection of the grid, with the same defaults as the server; null when not drawable. */
export function projectionFor(p: Projection): PlaneProjection | null {
  if (p.map_proj === "lambert") {
    const truelat1 = p.truelat1 ?? p.ref_lat;
    return lambert(truelat1, p.truelat2 ?? truelat1, p.stand_lon ?? p.ref_lon);
  }
  if (p.map_proj === "mercator") return mercator(p.truelat1 ?? 0, p.ref_lon);
  return null;
}

/** Grid spacing of every domain, metres (NaN when a parent is invalid). */
export function domainDx(grid: Grid): number[] {
  const spacing: number[] = [];
  grid.domains.forEach((d, i) => {
    if (i === 0) spacing.push(grid.dx);
    else spacing.push(d.parent_id >= 1 && d.parent_id <= i ? spacing[d.parent_id - 1] / d.parent_grid_ratio : NaN);
  });
  return spacing;
}

export interface TimeSteps {
  /** Seconds per step of d01, as written in namelist.input */
  value: number;
  /** The project sets it (namelist.input); otherwise it follows the grid spacing of d01 */
  chosen: boolean;
  /** The automatic value: AUTO_TIME_STEP_S_PER_KM per km of d01, in whole seconds */
  automatic: number;
  /** WRF chooses the step itself during the run (use_adaptive_time_step): the rules do not apply */
  adaptive: boolean;
  /** The step of every domain: its parent's divided by parent_time_step_ratio (null when unknown) */
  domains: (number | null)[];
  /** Domains whose step exceeds MAX_TIME_STEP_S_PER_KM per km of their grid spacing */
  tooLarge: number[];
  /** d01's step is under SLOW_TIME_STEP_S_PER_KM per km: the computation is needlessly long */
  tooSmall: boolean;
}

const numberAt = (value: NamelistValue | undefined, index: number): number | undefined => {
  const item = Array.isArray(value) ? value[index] : value;
  return typeof item === "number" && Number.isFinite(item) ? item : undefined;
};

/** The time step of each domain, following owstudio.core.namelist.validate.check_time_steps. */
export function timeSteps(grid: Grid, namelistInput: NamelistGroups): TimeSteps {
  const options = namelistInput.domains ?? {};
  const spacing = domainDx(grid);
  const automatic = Math.trunc((AUTO_TIME_STEP_S_PER_KM * grid.dx) / 1000);
  const numerator = numberAt(options.time_step_fract_num, 0) ?? 0;
  const denominator = numberAt(options.time_step_fract_den, 0) ?? 1;
  const value = (numberAt(options.time_step, 0) ?? automatic) + (denominator > 0 ? numerator / denominator : 0);
  const domains: (number | null)[] = [];
  grid.domains.forEach((d, i) => {
    // The namelist is written with parent_time_step_ratio equal to the refinement, unless the project sets it
    const ratio = numberAt(options.parent_time_step_ratio, i) ?? d.parent_grid_ratio;
    const parent = i === 0 ? null : d.parent_id >= 1 && d.parent_id <= i ? domains[d.parent_id - 1] : null;
    domains.push(i === 0 ? value : parent !== null && ratio > 0 ? parent / ratio : null);
  });
  const adaptive = options.use_adaptive_time_step === true;
  return {
    value,
    chosen: "time_step" in options,
    automatic,
    adaptive,
    domains,
    tooLarge: adaptive ? [] : domains.flatMap((dt, i) => (dt !== null && dt > (MAX_TIME_STEP_S_PER_KM * spacing[i]) / 1000 + 1e-9 ? [i] : [])),
    tooSmall: !adaptive && value > 0 && value < (SLOW_TIME_STEP_S_PER_KM * grid.dx) / 1000,
  };
}

export interface Extent {
  west: number;
  east: number;
  south: number;
  north: number;
  dx: number;
}

/** Edges of every domain's staggered grid in the projection plane, or null when they cannot be computed. */
export function extents(grid: Grid, proj = projectionFor(grid.projection)): Extent[] | null {
  if (!proj) return null;
  const [xc, yc] = proj.forward(grid.projection.ref_lat, grid.projection.ref_lon);
  if (!Number.isFinite(xc) || !Number.isFinite(yc)) return null;
  const spacing = domainDx(grid);
  const result: Extent[] = [];
  for (const [i, d] of grid.domains.entries()) {
    const dx = spacing[i];
    if (!(dx > 0)) return null;
    const width = (d.e_we - 1) * dx;
    const height = (d.e_sn - 1) * dx;
    let west: number;
    let south: number;
    if (i === 0) {
      west = xc - width / 2;
      south = yc - height / 2;
    } else {
      const parent = result[d.parent_id - 1];
      west = parent.west + (d.i_parent_start - 1) * parent.dx;
      south = parent.south + (d.j_parent_start - 1) * parent.dx;
    }
    result.push({ west, east: west + width, south, north: south + height, dx });
  }
  return result;
}

export interface LatLon {
  lat: number;
  lon: number;
}

/** Geographic centre of a domain, or null when the projection is not drawable. */
export function centreOf(grid: Grid, index: number): LatLon | null {
  const proj = projectionFor(grid.projection);
  const e = extents(grid, proj);
  if (!proj || !e) return null;
  const box = e[index];
  const [lat, lon] = proj.inverse((box.west + box.east) / 2, (box.south + box.north) / 2);
  return Number.isFinite(lat) && Number.isFinite(lon) ? { lat, lon } : null;
}

/** Whole parent cells covered by a nest along each axis. */
export function nestCells(grid: Grid, index: number): { we: number; sn: number } {
  const d = grid.domains[index];
  return { we: (d.e_we - 1) / d.parent_grid_ratio, sn: (d.e_sn - 1) / d.parent_grid_ratio };
}

/** Cells between a nest and its parent's west, east, south and north edges. */
export function nestMargins(grid: Grid, index: number): { w: number; e: number; s: number; n: number } | null {
  const d = grid.domains[index];
  const parent = grid.domains[d.parent_id - 1];
  if (index === 0 || !parent || d.parent_id > index) return null;
  const cells = nestCells(grid, index);
  return {
    w: d.i_parent_start - 1,
    e: parent.e_we - 1 - (d.i_parent_start - 1 + cells.we),
    s: d.j_parent_start - 1,
    n: parent.e_sn - 1 - (d.j_parent_start - 1 + cells.sn),
  };
}

/**
 * A start index kept inside the parent, as the server requires (start + cells < parent points),
 * and at least `margin` cells from the edges when the nest is small enough.
 */
function clampStart(want: number, parentPoints: number, cells: number, margin: number): number {
  const strictMax = parentPoints - Math.floor(cells) - 1;
  const lo = 1 + margin;
  const hi = strictMax - margin;
  if (lo <= hi) return Math.min(hi, Math.max(lo, want));
  return strictMax >= 1 ? Math.min(strictMax, Math.max(1, want)) : 1;
}

export interface Placement {
  /** The point lies inside the parent */
  inside: boolean;
  /** The nest could not be centred exactly on the point (edge of the parent) */
  clamped: boolean;
}

/**
 * Places a nest so that its centre is as close as possible to a point: the point is projected
 * to the plane, converted to parent cells, and the south-west corner snapped to a whole cell.
 */
export function placeCentre(grid: Grid, index: number, lat: number, lon: number, margin = 0): Placement | null {
  if (index === 0) return null;
  const proj = projectionFor(grid.projection);
  const e = extents(grid, proj);
  const d = grid.domains[index];
  const parent = grid.domains[d.parent_id - 1];
  if (!proj || !e || !parent) return null;
  const box = e[d.parent_id - 1];
  const [x, y] = proj.forward(lat, lon);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
  const cells = nestCells(grid, index);
  const wantI = Math.round((x - box.west) / box.dx - cells.we / 2) + 1;
  const wantJ = Math.round((y - box.south) / box.dx - cells.sn / 2) + 1;
  d.i_parent_start = clampStart(wantI, parent.e_we, cells.we, margin);
  d.j_parent_start = clampStart(wantJ, parent.e_sn, cells.sn, margin);
  return {
    inside: x >= box.west && x <= box.east && y >= box.south && y <= box.north,
    clamped: d.i_parent_start !== wantI || d.j_parent_start !== wantJ,
  };
}

/** Centres a nest in its parent (whole cells; the extra cell goes to the east and north). */
export function centreInParent(grid: Grid, index: number): void {
  const d = grid.domains[index];
  const parent = grid.domains[d.parent_id - 1];
  if (index === 0 || !parent) return;
  const cells = nestCells(grid, index);
  d.i_parent_start = Math.max(1, Math.floor((parent.e_we - 1 - cells.we) / 2) + 1);
  d.j_parent_start = Math.max(1, Math.floor((parent.e_sn - 1 - cells.sn) / 2) + 1);
}

/**
 * Applies a change to the grid, then puts every nest not listed in `moved` back over the place
 * it covered (same geographic centre, snapped to whole parent cells, kept inside its parent);
 * a nest whose former centre falls outside its new parent is centred in it. Without a drawable
 * projection the change is applied as is.
 */
export function editGrid(grid: Grid, change: (g: Grid) => void, moved: number[] = []): void {
  const centres = grid.domains.map((_, i) => (i === 0 ? null : centreOf(grid, i)));
  change(grid);
  for (let i = 1; i < grid.domains.length; i++) {
    const centre = centres[i];
    if (moved.includes(i) || !centre) continue;
    const placed = placeCentre(grid, i, centre.lat, centre.lon);
    if (placed && !placed.inside) centreInParent(grid, i);
  }
}

/** Projection parameters suited to the outer domain: true latitudes inside it, no rotation. */
export function suggestedProjection(grid: Grid): Pick<Projection, "truelat1" | "truelat2" | "stand_lon"> {
  const p = grid.projection;
  if (p.map_proj === "lambert") {
    // Standard parallels at one sixth of the latitude range from each edge
    const span = ((grid.domains[0].e_sn - 1) * grid.dx) / ((EARTH_RADIUS_M * Math.PI) / 180);
    const hemi = p.ref_lat >= 0 ? 1 : -1;
    const keep = (lat: number) => hemi * Math.min(89, Math.max(1, hemi * lat));
    return {
      truelat1: round(keep(p.ref_lat - span / 3), 1),
      truelat2: round(keep(p.ref_lat + span / 3), 1),
      stand_lon: round(p.ref_lon, 2),
    };
  }
  if (p.map_proj === "mercator") return { truelat1: round(p.ref_lat, 1), truelat2: null, stand_lon: null };
  if (p.map_proj === "polar") return { truelat1: round(p.ref_lat, 1), truelat2: null, stand_lon: round(p.ref_lon, 2) };
  return { truelat1: null, truelat2: null, stand_lon: null };
}

/** Moves the outer domain's centre; the projection follows it and the nests stay over the same places. */
export function centreOuter(grid: Grid, lat: number, lon: number): void {
  editGrid(grid, (g) => {
    g.projection.ref_lat = round(Math.max(-89.9, Math.min(89.9, lat)), 4);
    g.projection.ref_lon = round(wrapLon(lon), 4);
    Object.assign(g.projection, suggestedProjection(g));
  });
}

export const wrapLon = (lon: number) => deg(wrap(rad(lon)));

/** Smallest and largest map scale factor over the outer domain. */
export function mapFactorRange(grid: Grid): { min: number; max: number } | null {
  const proj = projectionFor(grid.projection);
  const e = extents(grid, proj);
  if (!proj || !e) return null;
  const box = e[0];
  let min = Infinity;
  let max = -Infinity;
  const steps = 8;
  for (let a = 0; a <= steps; a++) {
    for (let b = 0; b <= steps; b++) {
      const [lat] = proj.inverse(box.west + ((box.east - box.west) * a) / steps, box.south + ((box.north - box.south) * b) / steps);
      const m = proj.scale(lat);
      if (Number.isFinite(m)) {
        min = Math.min(min, m);
        max = Math.max(max, m);
      }
    }
  }
  return Number.isFinite(min) ? { min, max } : null;
}

/** A size in grid points snapped to a valid value: (points − 1) a multiple of the ratio, inside the parent. */
export function snapPoints(grid: Grid, index: number, axis: "we" | "sn", points: number): number {
  const d = grid.domains[index];
  if (index === 0) return Math.max(MIN_POINTS, Math.round(points));
  const ratio = d.parent_grid_ratio;
  const parent = grid.domains[d.parent_id - 1];
  let cells = Math.max(Math.ceil((MIN_POINTS - 1) / ratio), Math.round((points - 1) / ratio));
  if (parent) cells = Math.min(cells, Math.max(1, (axis === "we" ? parent.e_we : parent.e_sn) - 2));
  return cells * ratio + 1;
}

/** The nearest valid sizes below and above a size, for a ratio. */
export function validNeighbours(points: number, ratio: number): [number, number] {
  const below = Math.floor((points - 1) / ratio) * ratio + 1;
  return [below, below + ratio];
}

/** A nest of the given ratio covering about a third of its parent, centred in it. */
export function newNest(grid: Grid, parentIndex: number, ratio = 3) {
  const parent = grid.domains[parentIndex];
  const cellsWe = Math.max(3, Math.floor((parent.e_we - 1) / 3));
  const cellsSn = Math.max(3, Math.floor((parent.e_sn - 1) / 3));
  return {
    e_we: cellsWe * ratio + 1,
    e_sn: cellsSn * ratio + 1,
    parent_id: parentIndex + 1,
    parent_grid_ratio: ratio,
    i_parent_start: Math.max(1, Math.floor((parent.e_we - 1 - cellsWe) / 2) + 1),
    j_parent_start: Math.max(1, Math.floor((parent.e_sn - 1 - cellsSn) / 2) + 1),
    geog_data_res: parent.geog_data_res || "default",
  };
}

/** Domains nested, directly or not, in a domain. */
export function descendants(grid: Grid, index: number): number[] {
  const result: number[] = [];
  grid.domains.forEach((d, i) => {
    if (i > 0 && (d.parent_id - 1 === index || result.includes(d.parent_id - 1))) result.push(i);
  });
  return result;
}

// ------------------------------------------------------------------- checks of the grid

export type ProblemKey =
  | "parent"
  | "sizeMin"
  | "multiple"
  | "beyond"
  | "dx"
  | "levels"
  | "top"
  | "lambertZero"
  | "lambertHemisphere"
  | "farmDomain"
  | "margin"
  | "evenRatio"
  | "bigRatio"
  | "overlap"
  | "small"
  | "mapFactor";

export interface Problem {
  severity: "error" | "warning";
  key: ProblemKey;
  /** Domain the problem is about (index), to highlight its card */
  domain?: number;
  vars: Record<string, string | number>;
}

/**
 * The rules the server applies when it reads the grid (an invalid grid cannot be saved, checked
 * or drawn), plus the usual good practice of nesting.
 */
export function gridProblems(grid: Grid, farmDomains: number[] = []): Problem[] {
  const problems: Problem[] = [];
  const error = (key: ProblemKey, vars: Problem["vars"] = {}, domain?: number) => problems.push({ severity: "error", key, vars, domain });
  const warning = (key: ProblemKey, vars: Problem["vars"] = {}, domain?: number) =>
    problems.push({ severity: "warning", key, vars, domain });

  if (!(grid.dx > 0)) error("dx");
  if (!(grid.e_vert > 2)) error("levels");
  if (!(grid.p_top_requested > 0)) error("top");
  const p = grid.projection;
  if (p.map_proj === "lambert") {
    const t1 = p.truelat1 ?? p.ref_lat;
    const t2 = p.truelat2 ?? t1;
    if (Math.abs(t1) < 0.5 && Math.abs(t2) < 0.5) error("lambertZero");
    else if (t1 * t2 < 0) error("lambertHemisphere");
  }

  grid.domains.forEach((d, i) => {
    const name = domainName(i);
    for (const axis of ["we", "sn"] as const) {
      const points = axis === "we" ? d.e_we : d.e_sn;
      if (points < MIN_POINTS) error("sizeMin", { name, axis, min: MIN_POINTS }, i);
      else if (points < SMALL_POINTS) warning("small", { name, axis, points }, i);
    }
    if (i === 0) return;
    if (d.parent_id < 1 || d.parent_id > i) {
      error("parent", { name }, i);
      return;
    }
    const parent = grid.domains[d.parent_id - 1];
    const parentName = domainName(d.parent_id - 1);
    const ratio = d.parent_grid_ratio;
    for (const axis of ["we", "sn"] as const) {
      const size = axis === "we" ? d.e_we : d.e_sn;
      const start = axis === "we" ? d.i_parent_start : d.j_parent_start;
      const parentSize = axis === "we" ? parent.e_we : parent.e_sn;
      if ((size - 1) % ratio) {
        const [below, above] = validNeighbours(size, ratio);
        error("multiple", { name, axis, points: size, ratio, below, above }, i);
      } else if (start + Math.floor((size - 1) / ratio) >= parentSize || start < 1) {
        error("beyond", { name, parent: parentName, axis }, i);
      }
    }
    if (ratio % 2 === 0) warning("evenRatio", { name, ratio }, i);
    else if (ratio > 5) warning("bigRatio", { name, ratio }, i);
    const margins = nestMargins(grid, i);
    if (margins) {
      const closest = Math.min(margins.w, margins.e, margins.s, margins.n);
      if (closest >= 0 && closest < NEST_MARGIN) warning("margin", { name, parent: parentName, cells: closest, margin: NEST_MARGIN }, i);
    }
  });

  // Nests of the same parent must not overlap
  for (let a = 1; a < grid.domains.length; a++) {
    for (let b = a + 1; b < grid.domains.length; b++) {
      const da = grid.domains[a];
      const db = grid.domains[b];
      if (da.parent_id !== db.parent_id) continue;
      const ca = nestCells(grid, a);
      const cb = nestCells(grid, b);
      const apart =
        da.i_parent_start + ca.we <= db.i_parent_start ||
        db.i_parent_start + cb.we <= da.i_parent_start ||
        da.j_parent_start + ca.sn <= db.j_parent_start ||
        db.j_parent_start + cb.sn <= da.j_parent_start;
      if (!apart) warning("overlap", { a: domainName(a), b: domainName(b) }, b);
    }
  }

  for (const number of farmDomains) {
    if (number < 1 || number > grid.domains.length) error("farmDomain", { name: domainName(number - 1) });
  }

  if (!problems.some((x) => x.severity === "error")) {
    const factors = mapFactorRange(grid);
    if (factors && Math.max(Math.abs(1 - factors.min), Math.abs(factors.max - 1)) > MAP_FACTOR_TOLERANCE) {
      warning("mapFactor", { min: round(factors.min, 2), max: round(factors.max, 2) });
    }
  }
  return problems;
}
