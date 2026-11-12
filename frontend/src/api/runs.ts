import { useQuery } from "@tanstack/react-query";

import { get } from "./client";
import type { RunStatus } from "./types";

/** The runs of a project: its imported outputs (and older records of runs launched by the application). */
const runsApi = {
  history: (caseId: string) => get<RunStatus[]>(`/api/cases/${caseId}/runs`),
};

export const runKeys = {
  every: ["runs"] as const,
  history: (caseId: string) => ["runs", caseId] as const,
};

/** A run being computed or waiting for its turn (its outputs cannot be deleted meanwhile). */
export const isActive = (state: string | undefined) => state === "running" || state === "queued";

export function useRunHistory(caseId: string | null) {
  return useQuery({
    queryKey: runKeys.history(caseId ?? ""),
    queryFn: () => runsApi.history(caseId!),
    enabled: Boolean(caseId),
    refetchInterval: (query) => (query.state.data?.some((r) => isActive(r.state)) ? 2000 : false),
  });
}
