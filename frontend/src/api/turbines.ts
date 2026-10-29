/**
 * Turbine models: the catalogue of published reference turbines and the WRF table
 * (wind-turbine-N.tbl) written by the server for a turbine type.
 */
import { useDebouncedValue } from "@mantine/hooks";
import { useQuery } from "@tanstack/react-query";

import { caseKeys, casesApi } from "./cases";
import type { CatalogEntry, TurbineType } from "./types";

/** Catalogue entry holding the table WRF ships in its run directory for type 1 */
export const BUILT_IN_CATALOG_ID = "wrf-generic-2mw";
export const turbinesApi = {
  catalog: (): Promise<CatalogEntry[]> => casesApi.turbineCatalog(),
  wrfTable: (turbine: TurbineType): Promise<string> => casesApi.wrfTurbineTable(turbine),
};

/** Published reference turbines (IEA, DTU, NREL…), with source and licence; never changes. */
export function useTurbineCatalog() {
  return useQuery({ queryKey: caseKeys.catalog, queryFn: turbinesApi.catalog, staleTime: Infinity });
}

/** The built-in WRF table of type 1, as described by the catalogue. */
export function useBuiltInTurbine() {
  const catalog = useTurbineCatalog();
  return { ...catalog, data: catalog.data?.find((e) => e.id === BUILT_IN_CATALOG_ID) };
}

/**
 * The text of wind-turbine-N.tbl for a turbine type, as the server writes it for a run.
 * Requests wait for typing to pause; pass null to skip (curve not valid yet, panel closed).
 */
export function useWrfTable(turbine: TurbineType | null) {
  const [debounced] = useDebouncedValue(turbine, 400);
  const awaitingDraft = JSON.stringify(turbine) !== JSON.stringify(debounced);
  const query = useQuery({
    queryKey: ["wrf-turbine-table", debounced],
    queryFn: () => turbinesApi.wrfTable(debounced!),
    enabled: Boolean(turbine && debounced),
    staleTime: Infinity,
  });
  return { ...query, data: awaitingDraft ? undefined : query.data, isLoading: awaitingDraft || query.isLoading };
}
