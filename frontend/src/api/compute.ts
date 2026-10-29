/**
 * Compute profiles (where the WRF/WPS engine of this computer is), for the Compute page.
 *
 * Verification runs commands on the engine: it is a mutation, started only by a click.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { del, patch, post, put } from "./client";
import { keys } from "./system";
import type { ComputeProfile, ProfilesResponse, Settings, VerifyResponse } from "./types";

export const computeApi = {
  save: (profile: ComputeProfile) => put<ProfilesResponse>(`/api/profiles/${encodeURIComponent(profile.id)}`, profile),
  remove: (id: string) => del<ProfilesResponse>(`/api/profiles/${encodeURIComponent(id)}`),
  setDefault: (id: string) => patch<Settings>("/api/settings", { default_profile: id }),
  verify: (profile: ComputeProfile) => post<VerifyResponse>("/api/profiles/verify", profile),
};

function useProfilesChanged() {
  const client = useQueryClient();
  return (data: ProfilesResponse) => {
    client.setQueryData(keys.profiles, data);
    // The default profile and the engine readiness can change with the list
    void client.invalidateQueries({ queryKey: keys.settings });
    void client.invalidateQueries({ queryKey: keys.health });
    // The cleanup reads the data folder of the default engine
    void client.invalidateQueries({ queryKey: keys.storage });
  };
}

export function useSaveProfile() {
  const changed = useProfilesChanged();
  return useMutation({ mutationFn: computeApi.save, onSuccess: changed });
}

export function useDeleteProfile() {
  const changed = useProfilesChanged();
  return useMutation({ mutationFn: computeApi.remove, onSuccess: changed });
}

export function useSetDefaultProfile() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: computeApi.setDefault,
    onSuccess: (settings) => {
      client.setQueryData(keys.settings, settings);
      void client.invalidateQueries({ queryKey: keys.profiles });
      void client.invalidateQueries({ queryKey: keys.health });
      void client.invalidateQueries({ queryKey: keys.storage });
    },
  });
}

/** Connects to the engine and runs the read-only installation check (up to a few minutes). */
export function useVerifyProfile() {
  return useMutation({ mutationFn: computeApi.verify });
}
