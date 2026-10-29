/** Server helpers used by the wind farms page: coordinate import and WRF's built-in turbine. */
import { useMutation } from "@tanstack/react-query";
import { useMemo } from "react";

import { casesApi, useTurbineCatalog } from "./cases";
import { post } from "./client";
import type { CoordinateOptions, FeatureCollection, ParsedCoordinates, Turbine, TurbineType } from "./types";

/** Catalogue entry describing the table shipped with WRF (run/wind-turbine-1.tbl). */
export const WRF_GENERIC_ID = "wrf-generic-2mw";
/** WRF type number that works without a definition: the table shipped with WRF. */
export const WRF_GENERIC_TYPE = 1;

/** Used until the catalogue has loaded, and if it cannot be read: values of wind-turbine-1.tbl. */
const GENERIC_FALLBACK: Pick<TurbineType, "name" | "rated_power_mw" | "rotor_diameter_m" | "hub_height_m"> = {
  name: "WRF generic 2 MW",
  rated_power_mw: 2,
  rotor_diameter_m: 85,
  hub_height_m: 75,
};

export type GenericTurbine = typeof GENERIC_FALLBACK;

/** WRF's generic turbine (type 1 when the project does not define it). */
export function useWrfGenericTurbine(): GenericTurbine {
  const catalog = useTurbineCatalog();
  return useMemo(() => {
    const entry = catalog.data?.find((e) => e.id === WRF_GENERIC_ID)?.turbine;
    return entry
      ? {
          name: entry.name,
          rated_power_mw: entry.rated_power_mw,
          rotor_diameter_m: entry.rotor_diameter_m,
          hub_height_m: entry.hub_height_m,
        }
      : GENERIC_FALLBACK;
  }, [catalog.data]);
}

export interface ParseRequest {
  text: string;
  options: CoordinateOptions;
  /** Centre of the domain: chooses between latitude/longitude and longitude/latitude */
  near?: { lat: number; lon: number };
}

/** Reads pasted coordinates (degrees, UTM or any EPSG) on the server: POST /api/coordinates/parse. */
export function useParseCoordinates() {
  return useMutation<ParsedCoordinates, Error, ParseRequest>({
    mutationFn: ({ text, options, near }) => casesApi.parseCoordinates(text, options, near),
  });
}

export interface ImportedPolygon { id: string; name: string; rings: [number, number][][] }
export interface GeoImport {
  collection: FeatureCollection;
  points: Turbine[];
  polygons: ImportedPolygon[];
  warnings: string[];
  crs: string;
}
export interface GeoLayoutRequest { polygon: [number, number][]; holes: [number, number][][]; spacing_m: number; rotation_deg: number; turbine_type: number; spacing_across_m?: number; stagger?: number; setback_m?: number }
export interface GeoLayout { points: Turbine[]; count: number; collection: FeatureCollection; spacing_m: number; spacing_across_m: number; area_km2: number; rotation_deg: number; projection: string; warnings: string[] }
export function useGeoImport() { return useMutation({ mutationFn: (body: { path: string; crs: string | null }) => post<GeoImport>("/api/geo/import", body) }); }
export function useGeoLayout() { return useMutation({ mutationFn: (body: GeoLayoutRequest) => post<GeoLayout>("/api/geo/layout", body) }); }
