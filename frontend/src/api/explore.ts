import { get, post, withQuery } from "./client";
import type { FeatureCollection } from "./types";
import type { FoundSummary } from "../ui/FoundTree";

export interface SeriesRef {
  kind: string; variable: string; case_id?: string; run_id?: string; stage?: "main" | "control";
  domain?: number; reader?: string; dataset?: string; location?: string;
  lat?: number | null; lon?: number | null; height_m?: number | null;
  height_ref?: "agl" | "asl" | "surface"; options?: Record<string, unknown>;
}
export interface SeriesData {
  meta: { key: string; variable: string; unit: string; method?: string; flags?: string[]; height_m?: number | null; [key: string]: unknown };
  times: string[]; values: (number | null)[];
}
export interface RunVariable { name: string; units: string; description: string; dims: string[]; vertical: boolean; stagger: string }
export interface RunVariables {
  run_id: string; domains: Record<string, RunVariable[]>; times: Record<string, string[]>;
  tslist: { prefix: string; name: string; domain: number; lat: number; lon: number }[];
}
export interface Diagnostic { key: string; title?: string; description?: string; unit?: string; status?: string; available?: boolean; [key: string]: unknown }
export interface ExploreMap { unit: string; method: string; time: string; colors: string[]; coordinates: [number, number][]; vmin: number; vmax: number }
const path = (c: string, r: string) => `/api/cases/${encodeURIComponent(c)}/runs/${encodeURIComponent(r || "latest")}`;
export const exploreApi = {
  geometry: (c: string, r: string) => get<FeatureCollection>(`${path(c,r)}/geometry`),
  previewImport: (c: string, body: {folder:string;control_folder:string|null;mode:"link"|"copy"}) => post<{files:number;bytes:number;mode:string;warnings:string[];domains:Record<string,number[]>;folder:string;tree:FoundSummary}>(`/api/cases/${c}/results/import/preview`,body),
  importOutputs: (c: string, body: {folder:string;control_folder:string|null;mode:"link"|"copy"}) => post<{job_id:string}>(`/api/cases/${c}/results/import`,body),
  variables: (c: string, r: string, stage = "main") => get<RunVariables>(`${path(c,r)}/variables`, { stage }),
  diagnostics: (c: string, r: string, domain: number, stage = "main") => get<{ diagnostics: Diagnostic[] }>(`${path(c,r)}/diagnostics`, { domain, stage }),
  fiche: (name: string) => get<Record<string, unknown>>(`/api/variables/${encodeURIComponent(name)}`),
  series: (refs: SeriesRef[]) => post<{ series: SeriesData[] }>("/api/explore/series", { refs }),
  csv: (refs: SeriesRef[]) => post<string>("/api/explore/series", { refs }, { format: "csv" }),
  map: (c: string, r: string, query: { variable: string; domain: number; time: number; height?: number; stage: string; height_ref?: string }) => get<ExploreMap>(`${path(c,r)}/map`, query),
  mapUrl: (c: string, r: string, query: { variable: string; domain: number; time: number; height?: number; stage: string; height_ref?: string; vmin?: number; vmax?: number }) => withQuery(`${path(c,r)}/map.png`, query),
};
