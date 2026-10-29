/** Folders of the engine machine and of this computer, one at a time (backend core/engine/browse.py). */
import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";

import { del, get, post } from "./client";

/** "engine": where WPS and WRF run (WSL or this Linux computer); "here": where the application runs. */
export type Machine = "engine" | "here";
export type FolderRole = "wrf" | "wps" | "geog" | "engine" | "run";

export interface FolderEntry {
  name: string;
  path: string;
  kind: "dir" | "file";
  link: boolean;
  readable: boolean;
  writable: boolean;
  role: FolderRole | null;
  target?: string;
  loop?: boolean;
}

export interface FolderListing {
  path: string;
  parent: string | null;
  state: "ok" | "empty" | "missing" | "file" | "denied" | "offline";
  role: FolderRole | null;
  resolutions: ("default" | "lowres")[];
  writable: boolean;
  entries: FolderEntry[];
  total: number;
  nearest?: string;
  machine?: string;
}

/** `profile`: the engine machine of that profile instead of the default one. */
export const listFolder = (machine: Machine, path: string, offset = 0, profile?: string) =>
  get<FolderListing>("/api/fs/list", profile ? { machine, path, offset, profile } : { machine, path, offset });

export interface FolderCheck {
  issues: Record<string, string>;
  /** The right folder found below one given (whatever the names), which the scripts take */
  found: Record<string, string>;
  blocking: boolean;
}

/** Words for each wrong folder of the engine machine (WRF, WPS, geography with its resolution). */
export function useFolderCheck(folders: Record<string, string> | null, geogDataRes: string[], destination: string) {
  const body = folders ? { folders, geog_data_res: geogDataRes, destination } : null;
  return useQuery({
    queryKey: ["fs-check", body],
    queryFn: () => post<FolderCheck>("/api/fs/check", body),
    enabled: Boolean(body),
    staleTime: 10_000,
    retry: false,
    placeholderData: keepPreviousData,
  });
}

export interface ExtractedFolder {
  folder: string;
  exists: boolean;
  ours: boolean;
}

/** Whether the files of the project were already extracted in a folder. */
export function useExtractedFolder(caseId: string, folder: string) {
  return useQuery({
    queryKey: ["extracted", caseId, folder],
    queryFn: () => get<ExtractedFolder>(`/api/cases/${encodeURIComponent(caseId)}/method/folder`, { folder }),
    enabled: Boolean(folder.trim()),
    retry: false,
  });
}

export function useDeleteExtracted(caseId: string) {
  return useMutation({
    mutationFn: (folder: string) => del<{ folder: string; deleted: boolean }>(`/api/cases/${encodeURIComponent(caseId)}/method/folder`, { folder }),
  });
}
