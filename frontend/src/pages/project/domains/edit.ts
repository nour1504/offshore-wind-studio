/**
 * Adding and deleting nests. Per-domain namelist options (physics, dynamics and raw overrides
 * written as one value per domain) follow: a new nest copies its parent's values, a deleted
 * domain loses its own. The wind farm scheme follows the turbines (followingTurbines).
 */
import type { Case, NamelistSchema, NamelistValue } from "../../../api/types";
import { CUMULUS_OFF_AT_M, descendants, domainDx, extents, newNest, projectionFor } from "./grid";

type Options = Record<string, NamelistValue>;

const WPS_PER_DOMAIN = new Set(["start_date", "end_date", "geog_data_res", "parent_id", "parent_grid_ratio", "i_parent_start", "j_parent_start", "e_we", "e_sn", "active_grid", "input_from_file"]);
function eachPerDomainList(c: Case, count: number, schema: NamelistSchema | undefined, change: (list: NamelistValue[], option: string) => NamelistValue[]): void {
  const groups: [string, Options, boolean][] = [["physics", c.physics, false], ["dynamics", c.dynamics, false], ...Object.entries(c.namelist_input).map(([group, values]): [string, Options, boolean] => [group, values, false]), ...Object.entries(c.namelist_wps).map(([group, values]): [string, Options, boolean] => [group, values, true])];
  for (const [group, options, wps] of groups) {
    for (const [option, value] of Object.entries(options)) {
      // Length alone does not identify a domain dimension: e.g. eta_levels is vertical.
      const perDomain = wps ? WPS_PER_DOMAIN.has(option) : schema?.groups[group]?.[option]?.per_domain === true;
      if (perDomain && Array.isArray(value) && value.length === count) options[option] = change(value, option) as NamelistValue;
    }
  }
}

/** Adds a nest inside a domain, with the parent's per-domain options; returns its index. */
export function addNest(c: Case, parentIndex: number, ratio = 3, schema?: NamelistSchema): number {
  const count = c.grid.domains.length;
  c.grid.domains.push(newNest(c.grid, parentIndex, ratio));
  const index = count;
  const dx = domainDx(c.grid)[index];
  eachPerDomainList(c, count, schema, (list, option) => {
    let value = list[parentIndex];
    // Grids finer than about 4 km resolve convection: no cumulus scheme there
    if (option === "cu_physics" && dx < CUMULUS_OFF_AT_M) value = 0;
    return [...list, value];
  });
  return index;
}

/** Deletes domains and every nest inside them; returns the deleted indices. */
export function removeDomains(c: Case, index: number, schema?: NamelistSchema): number[] {
  if (index === 0) return [];
  const removed = [index, ...descendants(c.grid, index)].sort((a, b) => a - b);
  const gone = new Set(removed);
  const count = c.grid.domains.length;
  const newIndex: number[] = [];
  let next = 0;
  for (let i = 0; i < count; i++) newIndex.push(gone.has(i) ? -1 : next++);
  c.grid.domains = c.grid.domains
    .filter((_, i) => !gone.has(i))
    .map((d, i) => (i === 0 ? d : { ...d, parent_id: newIndex[d.parent_id - 1] + 1 }));
  eachPerDomainList(c, count, schema, (list) => list.filter((_, i) => !gone.has(i)));
  if (c.farm_scheme) {
    const kept = c.farm_scheme.domains.filter((n) => !gone.has(n - 1)).map((n) => newIndex[n - 1] + 1);
    c.farm_scheme.domains = kept.length ? kept : [c.grid.domains.length];
  }
  return removed;
}

/**
 * For each turbine of the enabled farms, the finest domain that holds it (numbers from 1, sorted);
 * empty without turbines or when the grid cannot be drawn.
 */
function turbineDomains(c: Case): number[] {
  const turbines = c.farms.filter((farm) => farm.enabled).flatMap((farm) => farm.turbines);
  const proj = projectionFor(c.grid.projection);
  const boxes = turbines.length ? extents(c.grid, proj) : null;
  if (!proj || !boxes) return [];
  const depth: number[] = [];
  c.grid.domains.forEach((d, i) => depth.push(i === 0 ? 0 : (depth[d.parent_id - 1] ?? 0) + 1));
  const found = new Set<number>();
  for (const turbine of turbines) {
    const [x, y] = proj.forward(turbine.lat, turbine.lon);
    let best = -1;
    boxes.forEach((box, i) => {
      if (!(x >= box.west && x <= box.east && y >= box.south && y <= box.north)) return;
      if (best < 0 || depth[i] > depth[best] || (depth[i] === depth[best] && box.dx < boxes[best].dx)) best = i;
    });
    if (best >= 0) found.add(best + 1);
  }
  return [...found].sort((a, b) => a - b);
}

/**
 * A domain change after which the wind farm scheme follows the turbines, as in the WI WRF
 * (windfarm_opt = 0, 0, 1): a nest added or moved over the farms takes the scheme and gives it back
 * when it leaves them. Only when the scheme runs in one domain or in those that held the turbines;
 * another choice of several domains made on Wind farms stays.
 */
export function followingTurbines(change: (c: Case) => void): (c: Case) => void {
  return (c) => {
    const scheme = c.farm_scheme;
    const follows = !!scheme && (scheme.domains.length === 1 || scheme.domains.join() === turbineDomains(c).join());
    const grid = JSON.stringify(c.grid);
    change(c);
    if (!follows || !c.farm_scheme || JSON.stringify(c.grid) === grid) return;
    const finest = turbineDomains(c);
    if (finest.length) c.farm_scheme.domains = finest;
  };
}
