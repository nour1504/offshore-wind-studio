import { post } from "./client";
export type AnalysisKind = "rose" | "weibull" | "histogram" | "grouped" | "aggregate" | "stability" | "profile" | "shear" | "veer" | "compare" | "bulk-richardson";
export interface AnalysisResult {
  kind: string; method: string; notes: string[]; inputs: Record<string, unknown>[]; tables: string[];
  [key: string]: unknown;
}
export const analysisApi = {
  run: (kind: AnalysisKind, body: unknown) => post<AnalysisResult>(`/api/analysis/${kind}`, body),
  csv: (kind: AnalysisKind, body: unknown, table: string) => post<string>(`/api/analysis/${kind}`, body, {format:"csv", table}),
};
