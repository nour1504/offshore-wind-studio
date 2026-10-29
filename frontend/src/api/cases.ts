import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { del, get, post, put, request } from "./client";
import type {
  Case,
  CaseSummary,
  CatalogEntry,
  CoordinateOptions,
  FeatureCollection,
  Issue,
  NamelistSchema,
  ParsedCoordinates,
  StructuredNamelists,
  TurbineType,
} from "./types";

export const casesApi = {
  list: () => get<CaseSummary[]>("/api/cases"),
  get: (id: string) => get<Case>(`/api/cases/${id}`),
  /** A new project to fill in step by step: no farm, the standard windows */
  blank: () => get<Case>("/api/blank-case"),
  create: (c: Case) => post<{ id: string }>("/api/cases", c),
  save: (id: string, c: Case) => put<Case>(`/api/cases/${id}`, c),
  remove: (id: string) => del(`/api/cases/${id}`),
  checks: (c: Case) => post<Issue[]>("/api/checks", c),
  geometry: (c: Case) => post<FeatureCollection>("/api/geometry", c),
  namelists: (c: Case) => post<Record<string, string>>("/api/namelists", c),
  structuredNamelists: (c: Case) => post<StructuredNamelists>("/api/namelists/structured", c),
  namelistSchema: () => get<NamelistSchema>("/api/namelist/schema"),
  offshorePreset: (c: Case) => post<Pick<Case, "physics" | "dynamics">>("/api/presets/offshore-wind", c),
  turbineCatalog: () => get<CatalogEntry[]>("/api/turbines/catalog"),
  wrfTurbineTable: (t: TurbineType) => request<string>("POST", "/api/turbines/wrf-table", t),
  parseCoordinates: (text: string, options: CoordinateOptions, near?: { lat: number; lon: number }) =>
    post<ParsedCoordinates>("/api/coordinates/parse", { text, ...options, near_lat: near?.lat, near_lon: near?.lon }),
};

export const caseKeys = {
  list: ["cases"] as const,
  one: (id: string) => ["case", id] as const,
  schema: ["namelist-schema"] as const,
  catalog: ["turbine-catalog"] as const,
};

export function useCases() {
  return useQuery({ queryKey: caseKeys.list, queryFn: casesApi.list });
}

export function useCase(id: string | null) {
  return useQuery({ queryKey: caseKeys.one(id ?? ""), queryFn: () => casesApi.get(id!), enabled: Boolean(id) });
}

export function useSaveCase(id: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (c: Case) => casesApi.save(id, c),
    onSuccess: (saved) => {
      client.setQueryData(caseKeys.one(id), saved);
      void client.invalidateQueries({ queryKey: caseKeys.list });
    },
  });
}

export function useCreateCase() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: casesApi.create,
    onSuccess: () => void client.invalidateQueries({ queryKey: caseKeys.list }),
  });
}

export function useDeleteCase() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: casesApi.remove,
    onSuccess: () => void client.invalidateQueries({ queryKey: caseKeys.list }),
  });
}

/** Checks of the case being edited (saved or not), refreshed as it changes. */
export function useChecks(c: Case | undefined) {
  return useQuery({
    queryKey: ["checks", c],
    queryFn: () => casesApi.checks(c!),
    enabled: Boolean(c),
    placeholderData: (previous) => previous,
  });
}

export function useGeometry(c: Case | undefined) {
  return useQuery({
    queryKey: ["geometry", c?.grid, c?.farms, c?.farm_scheme, c?.time_series],
    queryFn: () => casesApi.geometry(c!),
    enabled: Boolean(c),
    placeholderData: (previous) => previous,
  });
}

export function useNamelistSchema() {
  return useQuery({ queryKey: caseKeys.schema, queryFn: casesApi.namelistSchema, staleTime: Infinity });
}

export function useTurbineCatalog() {
  return useQuery({ queryKey: caseKeys.catalog, queryFn: casesApi.turbineCatalog, staleTime: Infinity });
}
