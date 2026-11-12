import type { NamelistFile } from "../../../api/types";
import type { ProjectSection } from "../../../app/sections";

export const PHYSICS = ["mp_physics", "ra_lw_physics", "ra_sw_physics", "sf_sfclay_physics", "sf_surface_physics", "bl_pbl_physics", "cu_physics", "radt", "bl_mynn_tkeadvect"] as const;
/** Main settings of the flow dynamics, named and shown first in the editor's &dynamics block */
export const DYNAMICS = ["diff_opt", "km_opt", "damp_opt", "zdamp", "dampcoef", "w_damping", "non_hydrostatic"] as const;
export type ChoiceName = (typeof PHYSICS)[number] | (typeof DYNAMICS)[number];

// Options another page controls: locked in the full editor, which says where to change them,
// so that a value typed here can never silently replace what a page sets
const TIME = /^(?:(?:start|end)_(?:year|month|day|hour|minute|second)|run_(?:days|hours|minutes|seconds)|restart|restart_interval|interval_seconds)$/i;
export function managedBy(file: NamelistFile, group: string, name: string): ProjectSection | "above" | null {
  const g = group.toLowerCase(); const n = name.toLowerCase();
  if (file === "namelist.wps") {
    if (g === "share") return /^(?:max_dom|start_date|end_date|interval_seconds)$/.test(n) ? "data" : null;
    if (g === "geogrid") return n === "geog_data_path" ? null : "domains";
    if (g === "ungrib" && n === "prefix") return "data";
    if (g === "metgrid" && n === "fg_name") return "data";
    return null;
  }
  if (g === "time_control") {
    if (TIME.test(n) || /^(?:auxinput4_inname|auxinput4_interval|io_form_auxinput4)$/.test(n)) return "data";
    if (/^(?:history_interval(?:_[dhms])?|iofields_filename|ignore_iofields_warning)$/.test(n)) return "outputs";
    return null;
  }
  if (g === "domains") {
    if (/^(?:max_dom|e_we|e_sn|e_vert|dx|dy|grid_id|parent_id|i_parent_start|j_parent_start|parent_grid_ratio|p_top_requested|time_step|auto_levels_opt|dzbot|dzstretch_s|dzstretch_u|max_dz|eta_levels)$/.test(n)) return "domains";
    if (/^(?:max_ts_locs|max_ts_level|tslist_unstagger_winds)$/.test(n)) return "outputs";
    return null;
  }
  if (g === "physics") {
    if (n.startsWith("windfarm_")) return "farms";
    if (n === "sst_update") return "data";
    return (PHYSICS as readonly string[]).includes(n) ? "above" : null;
  }
  return null;
}
