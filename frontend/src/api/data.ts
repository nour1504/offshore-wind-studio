import { useQuery } from "@tanstack/react-query";

import { get, post } from "./client";
import type { FoundSummary } from "../ui/FoundTree";
import type { Case } from "./types";

export type FileRole = "atmosphere" | "sst";
export type LevelKind = "pressure" | "surface" | "sea level" | "model level" | "soil" | "other";

export interface Finding {
  severity: "error" | "warning" | "info";
  message: string;
}

/** What ungrib (or the NetCDF conversion) will find in the case's own files. */
export interface Examination {
  role: FileRole;
  folder: string;
  pattern: string;
  vtable: string;
  format: "grib" | "netcdf";
  files: number;
  grib_files: number;
  messages: number;
  editions: number[];
  centres: string[];
  grids: string[];
  first: string | null;
  last: string | null;
  times: number;
  step_hours: number | null;
  fields: { name: string; kind: LevelKind; levels: number; times: number; output: boolean }[];
  unused_messages: number;
  pressure_levels_hpa: number[];
  soil_fields: string[];
  window: [string, string] | null;
  suggestions: { vtable: string; fields: number; required_ok: boolean; used_share: number }[];
  findings: Finding[];
  errors: string[];
}

export interface FileListing {
  folder: string;
  count: number;
  total_bytes: number;
  formats: Partial<Record<"grib1" | "grib2" | "netcdf" | "unknown", number>>;
  problems: string[];
  files: { name: string; bytes: number; format: "grib1" | "grib2" | "netcdf" | "unknown" }[];
  truncated: boolean;
  /** The folders the files are in, the chosen one and its subfolders */
  tree: FoundSummary;
}

export interface VtableInfo {
  name: string;
  description: string;
  recommended: boolean;
  fields: string[];
}

export const dataApi = {
  files: (folder: string, pattern: string) => get<FileListing>("/api/data/files", { folder, pattern }),
  vtables: () => get<VtableInfo[]>("/api/data/vtables"),
  vtable: (name: string) => get<string>(`/api/data/vtables/${encodeURIComponent(name)}`),
  validateVtable: (text: string) => post<{ problems: string[]; fields: string[] }>("/api/data/vtables/validate", { text }),
  examine: (c: Case, role: FileRole) => post<Examination>("/api/data/examine", { case: c, role }),
};

/**
 * The examination of the case's own files for a role, once asked for (``enabled``); it follows
 * the parts of the case it depends on (files, table, period, domains, physics).
 */
export function useExamination(c: Case, role: FileRole, enabled: boolean) {
  const files = role === "atmosphere" ? c.grib : c.sea_surface.grib;
  return useQuery({
    queryKey: ["examine", role, files, c.period, c.grid, c.physics, c.namelist_input.domains],
    queryFn: () => dataApi.examine(c, role),
    enabled: enabled && Boolean(files?.folder),
    retry: false,
    staleTime: 30_000,
    placeholderData: (previous) => previous,
  });
}

/** Files matching a folder and pattern; refreshed when either changes. */
export function useFileListing(folder: string, pattern: string) {
  return useQuery({
    queryKey: ["input-files", folder, pattern],
    queryFn: () => dataApi.files(folder, pattern),
    enabled: folder.trim().length > 2,
    retry: false,
    staleTime: 10_000,
  });
}

export function useVtables() {
  return useQuery({ queryKey: ["vtables"], queryFn: dataApi.vtables, staleTime: Infinity });
}
