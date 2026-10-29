/** Changes made from the Settings page, and small helpers about paths and runs. */
import { useMutation, useQueries, useQueryClient } from "@tanstack/react-query";

import { ApiError } from "../../api/client";
import { dataApi } from "../../api/data";
import { keys, systemApi } from "../../api/system";
import type { Folders, StorageUsage } from "../../api/types";
import type { FoundSummary } from "../../ui/FoundTree";

export type InputFolder = "gfs" | "era5" | "sst";
export const INPUT_FOLDERS: InputFolder[] = ["gfs", "era5", "sst"];

export interface CleanupRequest {
  /** Runs deleted entirely, as "case/run" */
  runs: string[];
  /** Runs whose prepared files are deleted, results and logs kept */
  intermediates: string[];
  /** Download folders emptied */
  inputs: InputFolder[];
}

const INPUT_SIZES = "settings-input-sizes";

/** Moves (or only switches) the data folder; every project and run then comes from the new place. */
export function useSetDataRoot() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ path, move }: { path: string; move: boolean }) => systemApi.setDataRoot(path, move),
    onSuccess: (storage) => {
      client.setQueryData(keys.storage, storage);
      void client.invalidateQueries({ predicate: (query) => query.queryKey[0] !== keys.storage[0] });
    },
    // A move that stops half-way may have moved some folders already
    onError: () => void client.invalidateQueries({ queryKey: keys.storage }),
  });
}

export function useSetFolders() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (folders: Folders) => systemApi.setFolders(folders),
    onSuccess: (storage) => {
      client.setQueryData(keys.storage, storage);
      void client.invalidateQueries({ queryKey: keys.settings });
      void client.invalidateQueries({ queryKey: [INPUT_SIZES] });
      void client.invalidateQueries({ queryKey: ["input-files"] });
    },
  });
}

export function useCleanup() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: CleanupRequest) => systemApi.cleanup(body),
    onSuccess: ({ done: _done, ...storage }) => {
      client.setQueryData<StorageUsage>(keys.storage, storage);
    },
    onSettled: (_data, error) => {
      // Even a refused or interrupted cleanup may have deleted the first items
      if (error) void client.invalidateQueries({ queryKey: keys.storage });
      // Run lists, project cards and results show the deleted runs
      for (const key of ["cases", "case", "runs", "results", INPUT_SIZES]) {
        void client.invalidateQueries({ queryKey: [key] });
      }
    },
  });
}

export function useSetCdsKey() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (key: string) => systemApi.setCdsKey(key.trim()),
    onSuccess: () => void client.invalidateQueries({ queryKey: keys.settings }),
  });
}

export interface InputFolderSize {
  source: InputFolder;
  path: string;
  /** null while loading or when the folder could not be read */
  bytes: number | null;
  files: number | null;
  /** The folders the files are in, by year for the downloads */
  tree: FoundSummary | null;
  loading: boolean;
  error: string | null;
}

/** Size of the download folders (gfs, era5, sst) with their subfolders; a missing folder is empty. */
export function useInputFolderSizes(inputRoot: string | undefined): InputFolderSize[] {
  const results = useQueries({
    queries: INPUT_FOLDERS.map((source) => {
      const path = inputRoot ? joinPath(inputRoot, source) : "";
      return {
        queryKey: [INPUT_SIZES, path],
        enabled: Boolean(inputRoot),
        retry: false,
        staleTime: 30_000,
        queryFn: async () => {
          try {
            const listing = await dataApi.files(path, "*");
            return { bytes: listing.total_bytes, files: listing.count, tree: listing.tree as FoundSummary | null };
          } catch (error) {
            if (error instanceof ApiError && error.status === 404) return { bytes: 0, files: 0, tree: null };
            throw error;
          }
        },
      };
    }),
  });
  return INPUT_FOLDERS.map((source, i) => {
    const query = results[i];
    return {
      source,
      path: inputRoot ? joinPath(inputRoot, source) : "",
      bytes: query.data?.bytes ?? null,
      files: query.data?.files ?? null,
      tree: query.data?.tree ?? null,
      loading: query.isLoading,
      error: query.error ? (query.error as Error).message : null,
    };
  });
}

// ------------------------------------------------------------------ helpers

/** "C:\Data" + "input" with the separator of the path. */
export function joinPath(root: string, ...names: string[]): string {
  const sep = root.includes("\\") ? "\\" : "/";
  return [root.replace(/[\\/]+$/, ""), ...names].join(sep);
}

const normalise = (p: string) => p.trim().replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase();

/** Comparable form of a path: same separators, no trailing separator, case ignored (Windows). */
export function samePath(a: string, b: string): boolean {
  return normalise(a) === normalise(b);
}

/** True when `inner` is below `outer` (not equal). */
export function isInside(inner: string, outer: string): boolean {
  return normalise(inner).startsWith(`${normalise(outer)}/`);
}

/** The server needs a full path: a drive (D:\), a network share (\\server), a Unix path or ~. */
export function isAbsolutePath(path: string): boolean {
  const p = path.trim();
  return /^[a-zA-Z]:[\\/]/.test(p) || p.startsWith("\\\\") || p.startsWith("/") || p.startsWith("~");
}

/** Run folders are named by their start time in UTC: 20251001-064500 → 2025-10-01T06:45:00. */
export function runStart(runId: string): string | null {
  const m = /^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})/.exec(runId);
  return m ? `${m[1]}-${m[2]}-${m[3]}T${m[4]}:${m[5]}:${m[6]}` : null;
}

export const runKey = (run: { case: string; run: string }) => `${run.case}/${run.run}`;

/** Runs whose outputs are being imported cannot be deleted (the server refuses). */
export const isActive = (state: string) => state === "running" || state === "queued";
