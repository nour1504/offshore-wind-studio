import { useQuery } from "@tanstack/react-query";

import { get } from "./client";
import type { RunStatus } from "./types";

/** The runs of a project: its imported outputs (and older records of runs launched by the application). */
export const runsApi = {
  history: (caseId: string) => get<RunStatus[]>(`/api/cases/${caseId}/runs`),
};

export const runKeys = {
  history: (caseId: string) => ["runs", caseId] as const,
};

const active = (state: string | undefined) => state === "running" || state === "queued";

export function useRunHistory(caseId: string | null) {
  return useQuery({
    queryKey: runKeys.history(caseId ?? ""),
    queryFn: () => runsApi.history(caseId!),
    enabled: Boolean(caseId),
    refetchInterval: (query) => (query.state.data?.some((r) => active(r.state)) ? 2000 : false),
  });
}
