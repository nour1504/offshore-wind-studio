/**
 * Adding and deleting nests. Per-domain namelist options (physics, dynamics and raw overrides
 * written as one value per domain) follow: a new nest copies its parent's values, a deleted
 * domain loses its own; the wind farm scheme keeps pointing at the same domains.
 */
import type { Case, NamelistSchema, NamelistValue } from "../../../api/types";
import { CUMULUS_OFF_AT_M, descendants, domainDx, newNest } from "./grid";

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
