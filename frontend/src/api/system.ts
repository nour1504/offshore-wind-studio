import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { del, get, patch, post, put } from "./client";
import type {
  ComputeProfile,
  Folders,
  Health,
  Job,
  ProfilesResponse,
  Settings,
  StorageUsage,
  VerifyResponse,
} from "./types";

export const systemApi = {
  health: () => get<Health>("/api/health"),
  settings: () => get<Settings>("/api/settings"),
  patchSettings: (changes: Partial<Pick<Settings, "language" | "default_profile">>) =>
    patch<Settings>("/api/settings", changes),
  setCdsKey: (key: string) => put<void>("/api/settings/cds-key", { key }),
  profiles: () => get<ProfilesResponse>("/api/profiles"),
  profileSuggestions: () => get<{ suggestions: ComputeProfile[] }>("/api/profiles/suggestions"),
  saveProfile: (profile: ComputeProfile) => put<ProfilesResponse>(`/api/profiles/${profile.id}`, profile),
  deleteProfile: (id: string) => del<ProfilesResponse>(`/api/profiles/${id}`),
  verifyProfile: (profile: ComputeProfile) => post<VerifyResponse>("/api/profiles/verify", profile),
  previewProfile: (profile: ComputeProfile, caseData?: unknown) =>
    post<{ files: Record<string, string> }>("/api/profiles/preview", { profile, case: caseData }),
  storage: () => get<StorageUsage>("/api/storage"),
  setDataRoot: (path: string, move: boolean) => put<StorageUsage>("/api/storage/data-root", { path, move }),
  setFolders: (folders: Folders) => put<StorageUsage>("/api/storage/folders", folders),
  cleanup: (body: { runs?: string[]; intermediates?: string[]; inputs?: string[] }) =>
    post<StorageUsage & { done: string[] }>("/api/storage/cleanup", body),
  job: <R>(id: string) => get<Job<R>>(`/api/jobs/${id}`),
  cancelJob: (id: string) => post<{ cancelled: boolean }>(`/api/jobs/${id}/cancel`),
};

export const keys = {
  health: ["health"] as const,
  settings: ["settings"] as const,
  profiles: ["profiles"] as const,
  storage: ["storage"] as const,
  job: (id: string) => ["job", id] as const,
};

export function useHealth() {
  return useQuery({ queryKey: keys.health, queryFn: systemApi.health, refetchInterval: 30_000 });
}

export function useSettings() {
  return useQuery({ queryKey: keys.settings, queryFn: systemApi.settings, staleTime: 60_000 });
}

export function usePatchSettings() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: systemApi.patchSettings,
    onSuccess: (settings) => client.setQueryData(keys.settings, settings),
  });
}

export function useProfiles() {
  return useQuery({ queryKey: keys.profiles, queryFn: systemApi.profiles });
}

export function useStorage() {
  return useQuery({ queryKey: keys.storage, queryFn: systemApi.storage });
}

/** Follows a background job until it ends. */
export function useJob<R>(id: string | null) {
  return useQuery({
    queryKey: keys.job(id ?? ""),
    queryFn: () => systemApi.job<R>(id!),
    enabled: Boolean(id),
    refetchInterval: (query) => (query.state.data && query.state.data.state !== "running" ? false : 1000),
  });
}
