import { post } from "./client";
export type AnalysisKind = "rose" | "weibull" | "histogram" | "grouped" | "aggregate" | "stability" | "profile" | "shear" | "veer" | "compare" | "bulk-richardson";
export interface AnalysisResult {
  kind: string; method: string; notes: string[]; inputs: Record<string, unknown>[]; tables: string[];
  [key: string]: unknown;
}
/** One row of a result table (a sector, a class, a group…), as the server sends it. */
export type ResultRow = Record<string, unknown>;
/** The rows of a result table: the objects of a list, nothing else. */
export const records = (value: unknown): ResultRow[] => (Array.isArray(value) ? (value.filter((v) => v && typeof v === "object") as ResultRow[]) : []);
export const analysisApi = {
  run: (kind: AnalysisKind, body: unknown) => post<AnalysisResult>(`/api/analysis/${kind}`, body),
};
