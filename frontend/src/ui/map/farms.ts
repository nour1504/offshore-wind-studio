/** Display-only farm markers. This module never changes the input geometry or turbine count. */
import type { Farm, FarmSymbol, FeatureCollection, GeoFeature } from "../../api/types";

export const FARM_COLORS = ["#21845a", "#438ac1", "#b68b36", "#9870bb", "#d47751", "#55a6a4", "#8a9c49", "#bb6e96"];
export const FARM_SYMBOLS: FarmSymbol[] = ["cross", "circle", "diamond", "triangle", "square", "plus"];
export const SYMBOL_PATHS: Record<FarmSymbol, string> = {
  circle: "M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18Z",
  cross: "m5 2 7 7 7-7 3 3-7 7 7 7-3 3-7-7-7 7-3-3 7-7-7-7Z",
  plus: "M9 2h6v7h7v6h-7v7H9v-7H2V9h7Z",
  square: "M3 3h18v18H3Z",
  diamond: "M12 1 23 12 12 23 1 12Z",
  triangle: "M12 2 23 22H1Z",
};

export function farmAppearance(farm: Pick<Farm, "appearance">, index: number) {
  return {
    color: farm.appearance?.color ?? FARM_COLORS[index % FARM_COLORS.length],
    symbol: !farm.appearance?.symbol || farm.appearance.symbol === "auto" ? FARM_SYMBOLS[index % FARM_SYMBOLS.length] : farm.appearance.symbol,
  };
}

type Position = [number, number];
type Point = { x: number; y: number };
const position = (feature: GeoFeature): Position => (feature.geometry as { coordinates: Position }).coordinates;
export const collection = (features: GeoFeature[]): FeatureCollection => ({ type: "FeatureCollection", features });

/** Screen-space collisions, in linear time for a regular farm: true when more than an eighth of
    the points have a neighbour closer than `gap` pixels. Two neighbouring farms remain separate. */
function crowded(points: Point[], gap: number): boolean {
  if (points.length < 3) return false;
  const cells = new Map<string, { x: number; y: number; index: number }[]>();
  const touching = new Set<number>();
  for (const [index, point] of points.entries()) {
    const x = Math.floor(point.x / gap), y = Math.floor(point.y / gap);
    for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) {
      for (const other of cells.get(`${x + dx}:${y + dy}`) ?? []) {
        if (Math.hypot(point.x - other.x, point.y - other.y) < gap) { touching.add(index); touching.add(other.index); }
      }
    }
    const key = `${x}:${y}`;
    const cell = cells.get(key) ?? [];
    cell.push({ ...point, index });
    cells.set(key, cell);
    if (touching.size > points.length * 0.12) return true;
  }
  return false;
}

/**
 * How much of a farm the map shows at the current zoom:
 * - "icon": seen from afar, a small mark with the farm's symbol and colour, no name;
 * - "name": closer, the same mark with the farm's name;
 * - "turbines": closer still, every turbine with its symbol, the name above the farm, and the
 *   turbines' own names once they have room.
 */
export type FarmLevel = "icon" | "name" | "turbines";
export interface FarmTag { id: string; name: string; count: number; color: string; symbol: FarmSymbol; center: Position; top: Position; enabled: boolean; level: FarmLevel }

/** Farms are named once they span this many pixels on screen. */
const NAME_EXTENT = 36;
/** Turbines are drawn once the farm spans this many pixels, or once they stand apart enough. */
const TURBINE_EXTENT = 80;
const TURBINE_GAP = 6;

export function farmDisplay(data: FeatureCollection, order: string[], project: (point: Position) => Point, mode: "auto" | "all" = "auto") {
  const farms = new Map<string, GeoFeature[]>();
  for (const feature of data.features) {
    if (feature.properties.kind !== "turbine" || !feature.properties.farm) continue;
    const id = feature.properties.farm;
    const list = farms.get(id) ?? [];
    list.push(feature); farms.set(id, list);
  }
  const details: GeoFeature[] = [], tags: FarmTag[] = [];
  for (const [id, features] of farms) {
    const properties = features[0].properties;
    const index = Math.max(0, order.indexOf(id) >= 0 ? order.indexOf(id) : [...farms.keys()].indexOf(id));
    const appearance = farmAppearance({ appearance: { color: properties.farm_color ?? null, symbol: properties.farm_symbol ?? "auto" } }, index);
    // Longitudes unwrapped around the first turbine, so that a farm across the date line stays local
    const origin = position(features[0])[0];
    const coordinates = features.map((feature): Position => { const [lon, lat] = position(feature); return [origin + ((((lon - origin) % 360) + 540) % 360 - 180), lat]; });
    const lons = coordinates.map((p) => p[0]), lats = coordinates.map((p) => p[1]);
    const west = Math.min(...lons), east = Math.max(...lons), south = Math.min(...lats), north = Math.max(...lats);
    const center: Position = [(west + east) / 2, (south + north) / 2];
    const points = features.map((feature) => project(position(feature)));
    const xs = points.map((p) => p.x), ys = points.map((p) => p.y);
    const extent = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys));
    const level: FarmLevel = mode === "all" || extent >= TURBINE_EXTENT || !crowded(points, TURBINE_GAP) ? "turbines" : extent >= NAME_EXTENT ? "name" : "icon";
    if (level === "turbines") {
      // Names need room: about the width of the longest one, between neighbouring turbines
      const longest = Math.max(...features.map((feature) => String(feature.properties.label ?? "").length));
      const showLabel = !crowded(points, Math.min(140, Math.max(36, longest * 6 + 14)));
      details.push(...features.map((feature) => ({ ...feature, properties: { ...feature.properties, ...appearance, showLabel } })));
    }
    tags.push({ id, name: properties.farm_name ?? id, count: features.length, ...appearance, center, top: [center[0], north], enabled: properties.enabled !== false, level });
  }
  return { details: collection(details), tags };
}

/** Code-native symbol atlas; no remote font or bitmap asset needed. */
export function markerImage(symbol: FarmSymbol, color: string, halo: string): ImageData {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 64;
  const ctx = canvas.getContext("2d")!;
  ctx.translate(8, 8); ctx.scale(2, 2);
  const path = new Path2D(SYMBOL_PATHS[symbol]);
  ctx.lineJoin = "round"; ctx.lineWidth = 1.8; ctx.strokeStyle = halo; ctx.stroke(path);
  ctx.fillStyle = color; ctx.fill(path);
  return ctx.getImageData(0, 0, 64, 64);
}
