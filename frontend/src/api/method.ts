import { useDebouncedValue } from "@mantine/hooks";
import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";

import { get, post, withLanguage, withQuery } from "./client";
import type { Case, Grouping, Issue } from "./types";

/** The windows of a project as the server plans them (core/method/plan.py), chronological. */
export interface PlannedWindow {
  id: string;
  /** 1 = computed first (the latest window; the earliest with restart) */
  order: number;
  block: string;
  simulation_start: string;
  simulation_end: string;
  useful_start: string;
  useful_end: string;
  /** Starts from the restart file of the previous window */
  restart?: boolean;
}

export interface WindowPlan {
  start: string;
  end: string;
  spin_up_hours: number;
  useful_hours: number;
  grouping: Grouping;
  single: boolean;
  /** Windows chained by restart files: one spin-up, chronological order */
  restart?: boolean;
  simulated_hours: number;
  blocks: { id: string; start: string; end: string }[];
  windows: PlannedWindow[];
  wps_passes: { year: number; start: string; end: string }[];
}

/** The plan of the draft, debounced; the previous plan stays shown while typing. */
export function useWindowPlan(draft: Case | undefined) {
  const [debounced] = useDebouncedValue(draft, 300);
  return useQuery({
    queryKey: ["method-plan", debounced?.period, debounced?.spin_up_hours, debounced?.windows],
    queryFn: () => post<WindowPlan>("/api/method/plan", debounced),
    enabled: Boolean(debounced),
    retry: false,
    placeholderData: keepPreviousData,
  });
}

export interface SlurmOptions {
  nodes: number;
  ntasks_per_node: number | null;
  time: string;
  partition: string;
  exclusive: boolean;
  enable_turbo: boolean;
  wckey: string;
  /** Editor mode: the raw #SBATCH header ({job}: name of each job) */
  raw: string | null;
}

export interface ExportOptions {
  target: "cluster" | "local";
  cores: number;
  wps_cores: number;
  slurm: SlurmOptions;
  environment: string[];
  wrf_dir: string;
  wps_dir: string;
  geog_dir: string;
  /** Shared folder of the downloaded input data on a Linux computer; empty: the package's data folder */
  data_dir: string;
  inputs: Record<string, string>;
}

export const DEFAULT_EXPORT: ExportOptions = {
  target: "cluster",
  cores: 96,
  wps_cores: 12,
  slurm: { nodes: 2, ntasks_per_node: null, time: "72:00:00", partition: "cn", exclusive: true, enable_turbo: true, wckey: "", raw: null },
  environment: [],
  wrf_dir: "/chemin/vers/WRF",
  wps_dir: "/chemin/vers/WPS",
  geog_dir: "/chemin/vers/WPS_GEOG",
  data_dir: "",
  inputs: {},
};

export interface ExportedFile {
  path: string;
  text: string;
  executable: boolean;
}

export interface ExportPreview {
  files: ExportedFile[];
  issues: Issue[];
}

/** Every exported file of the draft with the given options, debounced. */
export function useExportPreview(draft: Case | undefined, options: ExportOptions) {
  const [body] = useDebouncedValue(draft ? { case: draft, options } : undefined, 400);
  return useQuery({
    queryKey: ["method-files", body],
    queryFn: () => post<ExportPreview>("/api/method/files", body),
    enabled: Boolean(body),
    retry: false,
    placeholderData: keepPreviousData,
  });
}

/** Address of the ZIP of the saved project, for the browser's or the window's download. */
export function exportZipUrl(caseId: string, options: ExportOptions): string {
  return withLanguage(withQuery(`/api/cases/${encodeURIComponent(caseId)}/method/files.zip`, { options: JSON.stringify(options) }));
}

export function useExportToFolder(caseId: string) {
  return useMutation({
    mutationFn: (body: { options: ExportOptions; folder: string; replace?: boolean }) =>
      post<{ folder: string; files: string[] }>(`/api/cases/${encodeURIComponent(caseId)}/method/folder`, body),
  });
}

/** Where the calculation of an extraction stands (backend core/method/progress.py). */
export interface RunProgress {
  state: "none" | "running" | "stopped" | "done" | "error";
  /** Program of the step (geogrid, ungrib, metgrid, real, wrf) or "download" */
  step?: string;
  error?: string;
  /** Window being computed, in the order of computation, and their number */
  window?: number;
  windows?: number;
  done?: number;
  start?: string | null;
  end?: string | null;
  /** Instant reached by the window being computed (UTC) */
  reached?: string | null;
  left_s?: number | null;
  download?: { done: number; expected: number } | null;
}

/** Read again every 10 s while the calculation runs, every minute otherwise. */
export function useRunProgress(caseId: string, folder: string, enabled: boolean) {
  return useQuery({
    queryKey: ["run-progress", caseId, folder],
    queryFn: () => get<RunProgress>(`/api/cases/${encodeURIComponent(caseId)}/method/progress`, { folder }),
    enabled: enabled && Boolean(folder),
    retry: false,
    refetchInterval: (query) => (query.state.data?.state === "running" ? 10_000 : 60_000),
  });
}

/** Order of magnitude of WRF's computing time and memory (backend core/method/estimate.py). */
export interface ComputingEstimate {
  /** CPU time of the whole calculation, to divide by the cores used (up to the physical ones) */
  core_seconds: number;
  memory_bytes: number;
  process_bytes: number;
  simulated_seconds: number;
  physical_cores: number;
  memory_total: number;
}

export function useComputingEstimate(draft: Case | undefined) {
  const [debounced] = useDebouncedValue(draft, 400);
  return useQuery({
    queryKey: ["computing-estimate", debounced],
    queryFn: () => post<ComputingEstimate>("/api/method/estimate", debounced),
    enabled: Boolean(debounced),
    retry: false,
    placeholderData: keepPreviousData,
  });
}
