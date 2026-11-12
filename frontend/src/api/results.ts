import { useQuery } from "@tanstack/react-query";

import { get, withQuery } from "./client";
import type { FieldMeta, ResultsSummary, TimeRecord, TsIndex } from "./types";

// Every call takes an optional run id; without it the latest run with results is used
export const resultsApi = {
  summary: (caseId: string, run?: string | null) => get<ResultsSummary>(`/api/cases/${caseId}/results`, { run }),
  fieldMeta: (caseId: string, variable: string, domain: number, run?: string | null) =>
    get<FieldMeta>(`/api/cases/${caseId}/results/field`, { variable, domain, run }),
  point: (caseId: string, domain: number, lat: number, lon: number, run?: string | null) =>
    get<TimeRecord[]>(`/api/cases/${caseId}/results/point`, { domain, lat, lon, run }),
  tslistIndex: (caseId: string, run?: string | null) => get<TsIndex>(`/api/cases/${caseId}/results/tslist`, { run }),
  tslistSeries: (caseId: string, prefix: string, domain: number, height: number, average_s: number, run?: string | null) =>
    get<TimeRecord[]>(`/api/cases/${caseId}/results/tslist/${prefix}`, { domain, height, average_s, run }),
};

export const resultUrls = {
  fieldPng: (caseId: string, variable: string, domain: number, time: number | null, version: number, run?: string | null) =>
    withQuery(`/api/cases/${caseId}/results/field.png`, { variable, domain, time, run, v: version }),
};

export const resultKeys = {
  every: ["results"] as const,
  project: (caseId: string) => ["results", caseId] as const,
  summary: (caseId: string, run?: string | null) => ["results", caseId, run ?? "latest"] as const,
};

export function useResultsSummary(caseId: string, run: string | null | undefined, enabled: boolean) {
  return useQuery({
    queryKey: resultKeys.summary(caseId, run),
    queryFn: () => resultsApi.summary(caseId, run),
    enabled,
    retry: false,
  });
}
