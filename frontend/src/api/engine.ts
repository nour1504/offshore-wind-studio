/**
 * Automatic engine installation (WRF 4.8.0 + WPS 4.7.0): catalogue, local WSL
 * preparation, checks of a target, installation, follow-up, resumption and verification.
 * Every call that changes a machine is a mutation started by an explicit click.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { get, post, withLanguage } from "./client";
import { keys } from "./system";
import type { ComputeProfile, EngineManifest, ProfilesResponse } from "./types";

export type { EngineManifest };

export interface GeographyChoice {
  id: "mandatory-high" | "mandatory-low" | "existing";
  url: string | null;
  download_bytes: number;
  unpacked_gb: number;
  minimum_free_gb: number;
  description: string;
}

export interface Complement {
  id: string;
  url: string;
  when: [string, string][];
  description: string;
  download_bytes: number;
}

export interface EngineCatalog {
  id: string;
  wrf: { version: string; tag: string; commit: string; url: string; build: string };
  wps: { version: string; tag: string; commit: string; url: string; build: string };
  platform: string;
  micromamba: { version: string; url: string; sha256: string };
  dependencies: Record<string, string>;
  bundled_by_wps: Record<string, string>;
  geography: GeographyChoice[];
  complements: Complement[];
  notes: string[];
  references: string[];
  kit_bytes: number;
  local_folder: string;
  host_platform: string;
  native_root: string;
}

export interface WslStatus {
  platform: string;
  available: boolean;
  ready: boolean;
  version: string | null;
  version_ok: boolean;
  distributions: string[];
  managed_distro: string;
  managed_user: string;
  managed_exists: boolean;
  /** Windows folder of the dedicated Linux's virtual disk */
  managed_folder: string | null;
  error: string | null;
  /** Linux: this computer is the Linux itself; nothing to prepare, no WSL */
  native?: boolean;
}

export interface InstallRequest {
  profile: ComputeProfile;
  root: string;
  jobs: number;
  dependency_mode: "managed" | "system";
  geography: GeographyChoice["id"];
  geog_path: string;
  extras: string[];
}

export interface PreflightCheck {
  status: "ok" | "warn" | "fail";
  key: "system" | "tools" | "python" | "site_libraries" | "folder" | "space" | "network";
  detail: string;
}

export interface Preflight {
  root: string;
  checks: PreflightCheck[];
  ready: boolean;
  free_bytes: number;
  needed_bytes: number;
  cpus: number;
  memory_bytes: number;
  glibc: string;
  present: string[];
  suggested_jobs: number;
  /** Addresses the target cannot download from (network check) */
  blocked?: string[];
}

/** A WPS_GEOG folder already on the target, with its resolutions (30 s "default", 5 min "lowres"). */
export interface FoundGeography {
  path: string;
  resolutions: ("default" | "lowres")[];
}

export interface ResumeChanges {
  geography?: GeographyChoice["id"];
  geog_path?: string;
  extras?: string[];
}

/** Sends the NCAR archive of a geography from this computer, with its progress (0 to 1). */
export function uploadGeography(geography: GeographyChoice["id"], file: File, onProgress: (fraction: number) => void): Promise<Record<string, number>> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", withLanguage(`/api/engine/geography/${geography}`));
    xhr.upload.onprogress = (event) => event.lengthComputable && onProgress(event.loaded / event.total);
    xhr.onload = () => {
      let body: { detail?: string } & Record<string, number> = {} as never;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        // no JSON: the status says enough
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body);
      else reject(new Error(typeof body.detail === "string" ? body.detail : `HTTP ${xhr.status}`));
    };
    xhr.onerror = () => reject(new Error("The application server is not responding."));
    xhr.send(file);
  });
}

export interface Installation {
  id: string;
  engine: string;
  root: string;
  profile: ComputeProfile;
  options: Omit<InstallRequest, "profile">;
  state: "preparing" | "queued" | "running" | "fetched" | "monitor-interrupted" | "succeeded" | "failed" | "cancelled" | "resumed";
  progress: number;
  stage: string;
  detail: string;
  phase: string;
  error: string | null;
  started_at: string;
  finished_at?: string;
  slurm_job_id: string | null;
  job_id: string | null;
  followed: boolean;
}

export const engineApi = {
  catalog: () => get<EngineCatalog>("/api/engine/catalog"),
  wsl: () => get<WslStatus>("/api/engine/wsl"),
  prepareWsl: (folder: string) => post<{ job_id: string }>("/api/engine/wsl/prepare", { folder }),
  preflight: (body: InstallRequest) => post<Preflight>("/api/engine/preflight", body),
  install: (body: InstallRequest) => post<{ job_id: string }>("/api/engine/install", body),
  installations: () => get<Installation[]>("/api/engine/installations"),
  follow: (id: string) => post<{ job_id: string }>(`/api/engine/installations/${id}/follow`),
  resume: (id: string, changes?: ResumeChanges) => post<{ job_id: string }>(`/api/engine/installations/${id}/resume`, changes),
  findGeography: (target: "wsl" | "local") => post<FoundGeography[]>("/api/engine/geography/find", { target }),
  uploads: () => get<Record<string, number>>("/api/engine/geography/uploads"),
  cancel: (id: string) => post<{ cancelled: boolean }>(`/api/engine/installations/${id}/cancel`),
  verify: (profileId: string) => post<{ ok: boolean; error?: string; manifest?: EngineManifest }>("/api/engine/verify", { profile_id: profileId }),
  dataFolder: (profileId: string) => post<ProfilesResponse>("/api/engine/data-folder", { profile_id: profileId }),
  complements: (physics: Record<string, unknown>) => post<{ complements: string[] }>("/api/engine/complements", { physics }),
  kitUrl: "/api/engine/kit",
};

export const engineKeys = {
  catalog: ["engine-catalog"] as const,
  wsl: ["engine-wsl"] as const,
  installations: ["engine-installations"] as const,
};

export function useEngineCatalog() {
  return useQuery({ queryKey: engineKeys.catalog, queryFn: engineApi.catalog, staleTime: Infinity });
}

/** WSL on this computer; asked only when the local target is chosen. */
export function useWslStatus(enabled: boolean) {
  return useQuery({ queryKey: engineKeys.wsl, queryFn: engineApi.wsl, enabled, staleTime: 30_000, retry: false });
}

/** Installations of this computer's receipts, refreshed while one is active. */
export function useInstallations() {
  return useQuery({
    queryKey: engineKeys.installations,
    queryFn: engineApi.installations,
    refetchInterval: (query) =>
      query.state.data?.some((i) => ["preparing", "queued", "running", "fetched"].includes(i.state)) ? 5000 : 30_000,
  });
}

function useInstallationsChanged() {
  const client = useQueryClient();
  return () => {
    void client.invalidateQueries({ queryKey: engineKeys.installations });
    void client.invalidateQueries({ queryKey: keys.profiles });
    void client.invalidateQueries({ queryKey: keys.storage });
  };
}

export function usePrepareWsl() {
  return useMutation({ mutationFn: engineApi.prepareWsl });
}

export function useInstallEngine() {
  const changed = useInstallationsChanged();
  return useMutation({ mutationFn: engineApi.install, onSuccess: changed });
}

export function useInstallationAction(action: "follow" | "resume" | "cancel") {
  const changed = useInstallationsChanged();
  return useMutation<unknown, Error, string>({
    mutationFn: (id: string) => (action === "cancel" ? engineApi.cancel(id) : action === "follow" ? engineApi.follow(id) : engineApi.resume(id)),
    onSuccess: changed,
  });
}

/** Moves the data of an engine from before 0.6.2 into the shared folder next to it. */
export function useUpdateDataFolder() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: engineApi.dataFolder,
    onSuccess: (data) => {
      client.setQueryData(keys.profiles, data);
      void client.invalidateQueries({ queryKey: keys.storage });
    },
  });
}

export function useVerifyEngine() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: engineApi.verify,
    onSuccess: () => void client.invalidateQueries({ queryKey: keys.profiles }),
  });
}

/** The installation of a stopped one again, with the geography chosen again. */
export function useResumeEngine() {
  const changed = useInstallationsChanged();
  return useMutation({ mutationFn: ({ id, changes }: { id: string; changes: ResumeChanges }) => engineApi.resume(id, changes), onSuccess: changed });
}

/** WPS_GEOG folders already on the target; nothing asked before the target exists. */
export function useFoundGeography(target: "wsl" | "local", enabled: boolean) {
  return useQuery({ queryKey: ["engine-geography-found", target], queryFn: () => engineApi.findGeography(target), enabled, staleTime: 60_000, retry: false });
}

export function useGeographyUploads() {
  return useQuery({ queryKey: ["engine-geography-uploads"], queryFn: engineApi.uploads, staleTime: 10_000 });
}
