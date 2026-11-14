/**
 * Whether the projection of a project is to adjust: the outer domain changed (size, grid spacing,
 * centre) since the parameters of the projection were last set, and they are no longer those
 * fitted to it (grid.ts, projectionToFit). The outer domain the parameters were set for is kept
 * per project in the browser's storage: parameters typed on purpose are not flagged as long as
 * the domain stays what it was, and the flag stays after a save until they are set again.
 */
import type { Grid } from "../../../api/types";
import { projectionToFit } from "./grid";

const KEY = "ows-projection-set-for:";
/** The same answers when the storage is not available */
const memory = new Map<string, string>();

const outer = (grid: Grid) => [grid.dx, grid.domains[0]?.e_we, grid.domains[0]?.e_sn, grid.projection.ref_lat, grid.projection.ref_lon].join(" ");
const parameters = ({ projection: p }: Grid) => [p.map_proj, p.truelat1, p.truelat2, p.stand_lon].join(" ");

function kept(caseId: string): { outer: string; parameters: string } | null {
  try {
    return JSON.parse(localStorage.getItem(KEY + caseId) ?? memory.get(caseId) ?? "null");
  } catch {
    return null;
  }
}

function keep(caseId: string, value: { outer: string; parameters: string }): void {
  const text = JSON.stringify(value);
  memory.set(caseId, text);
  try {
    localStorage.setItem(KEY + caseId, text);
  } catch {
    // Storage refused: the memory of this session answers
  }
}

export function projectionToAdjust(caseId: string, grid: Grid): boolean {
  if (!grid.domains.length) return false;
  const now = { outer: outer(grid), parameters: parameters(grid) };
  const before = kept(caseId);
  // Seen for the first time, or parameters just set: they stand for the domain as it is
  if (!before || before.parameters !== now.parameters) {
    keep(caseId, now);
    return false;
  }
  return before.outer !== now.outer && projectionToFit(grid);
}
