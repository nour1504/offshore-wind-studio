/** The Exporter tab: the tslist outputs of a run in one CSV, or one wrfout variable at a point. */
import { get, withLanguage, withQuery } from "./client";

/** A grid cell holding tslist points: its points share one series. */
export interface ExportPlace { key: string; domain: number; i: number; j: number; points: string[]; prefixes: string[]; turbines: string[] }
export interface ExportQuantity { key: string; unit: string; profile: boolean; between: boolean; height_m: number | null }
export interface TslistIndex { run_id: string; reference: boolean; hub_heights_m: number[]; places: ExportPlace[]; quantities: ExportQuantity[] }
export interface TslistChoice {
  points: string[]; quantities: string[]; heights: string[]; average_s: number; layout: "long" | "wide"; reference: boolean;
  start?: string; end?: string;
}
/** Read at the first point only: its columns and first rows, its times in the period, the first
 * and last times of the files, what the files cannot give */
export interface TslistPreview {
  columns: string[]; rows: Record<string, unknown>[]; times: number; first: string | null; last: string | null; missing: Record<string, string>;
}
export interface WrfoutChoice {
  variable: string; domain?: number; height?: number | null; stage: "main" | "control";
  location?: string; lat?: number | null; lon?: number | null; start?: string; end?: string;
}

const base = (caseId: string) => `/api/cases/${encodeURIComponent(caseId)}/export`;

export const exportApi = {
  tslist: (caseId: string, run: string) => get<TslistIndex>(`${base(caseId)}/tslist`, { run }),
  preview: (caseId: string, run: string, choice: TslistChoice) => get<TslistPreview>(`${base(caseId)}/tslist/preview`, { run, ...choice }),
  tslistCsv: (caseId: string, run: string, choice: TslistChoice) => withLanguage(withQuery(`${base(caseId)}/tslist.csv`, { run, ...choice })),
  /** Fetched rather than opened, so that a point outside the domain is said on the page */
  wrfoutCsv: (caseId: string, run: string, choice: WrfoutChoice) => get<string>(`${base(caseId)}/wrfout.csv`, { run, ...choice }),
};
