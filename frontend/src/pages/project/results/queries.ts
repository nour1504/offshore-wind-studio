/**
 * React Query hooks of the results page, on top of resultsApi (src/api/results.ts).
 *
 * Every key holds the run id and the results version, so that a new run never shows cached
 * data of an older one.
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { ApiError } from "../../../api/client";
import { resultsApi } from "../../../api/results";
import type { TsLocation } from "../../../api/types";

export interface MapPoint {
  lat: number;
  lon: number;
}

/** A missing result (404) is a normal state of the page, shown as an explanation, not an error. */
export const isNotFound = (error: unknown) => error instanceof ApiError && error.status === 404;

export function useFieldMeta(caseId: string, runId: string, version: number, variable: string, domain: number) {
  return useQuery({
    queryKey: ["results-field", caseId, runId, version, variable, domain],
    queryFn: () => resultsApi.fieldMeta(caseId, variable, domain, runId),
    retry: false,
    staleTime: Infinity,
  });
}

export function usePointSeries(caseId: string, runId: string, version: number, domain: number, point: MapPoint | null) {
  return useQuery({
    queryKey: ["results-point", caseId, runId, version, domain, point?.lat, point?.lon],
    queryFn: () => resultsApi.point(caseId, domain, point!.lat, point!.lon, runId),
    enabled: point !== null,
    retry: false,
    staleTime: Infinity,
  });
}

export function useTsIndex(caseId: string, runId: string, version: number) {
  return useQuery({
    queryKey: ["results-tslist", caseId, runId, version],
    queryFn: () => resultsApi.tslistIndex(caseId, runId),
    retry: false,
    staleTime: Infinity,
  });
}

export function useTsSeries(
  caseId: string,
  runId: string,
  version: number,
  location: TsLocation | null,
  height: number,
  averageSeconds: number,
) {
  return useQuery({
    queryKey: ["results-tslist-series", caseId, runId, version, location?.prefix, location?.domain, height, averageSeconds],
    queryFn: () => resultsApi.tslistSeries(caseId, location!.prefix, location!.domain, height, averageSeconds, runId),
    enabled: location !== null,
    retry: false,
    staleTime: Infinity,
    // Changing the height or the averaging keeps the previous curve until the new one arrives
    placeholderData: keepPreviousData,
  });
}
