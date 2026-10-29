/**
 * The map of a project: WRF domains, wind farms (one colour per farm, disabled farms hollow),
 * time series locations, an optional result field and clickable points.
 *
 * The base map and the relief are loaded by the window straight from their public servers. The
 * application keeps a copy of what was seen on disk (api/routes_map.py), used only
 * when the network is not there; without a copy, domains, turbines and results show on a plain
 * background. Either way a discreet note says so and the cause goes to the application's log.
 */
import type { ExpressionSpecification, StyleSpecification } from "@maplibre/maplibre-gl-style-spec";
import {
  type Coordinates,
  type GeoJSONSource,
  type ImageSource,
  LngLatBounds,
  Map as MapLibreMap,
  Marker,
  type MapLayerMouseEvent,
  type MapMouseEvent,
  NavigationControl,
  ScaleControl,
  setWorkerUrl,
  Popup,
} from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import { IconLasso, IconRuler2, IconSunMoon, IconWorld } from "@tabler/icons-react";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import type { FeatureCollection, GeoFeature } from "../../api/types";
import { defineMessages, useLang, useT } from "../../i18n";
import { easeOutMap, prefersReducedMotion } from "../../motion";
import { collection, farmDisplay, markerImage, SYMBOL_PATHS } from "./farms";
import { ToolBar, ToolChoice, ToolGroup, ToolToggle } from "../ToolBar";
export { FARM_COLORS } from "./farms";

/** Camera moves glide with the application's landing curve, or jump when animations are reduced. */
const glideTo = (animate: boolean) => ({ duration: animate && !prefersReducedMotion() ? 850 : 0, easing: easeOutMap });

// MapLibre 6 loads its worker from a separate module that the bundler has to emit
setWorkerUrl(workerUrl);

// OpenFreeMap "Positron" and the Terrarium elevation tiles (AWS open data), loaded by the window
const UPSTREAM = "https://tiles.openfreemap.org/";
const ONLINE_STYLE = `${UPSTREAM}styles/positron`;
const ELEVATION_TILES = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png";
const ELEVATION_SERVER = ELEVATION_TILES.split("{z}")[0];
// The copy kept on disk by the application, for when the network is not there
const KEPT_STYLE = `${window.location.origin}/api/map/style.json`;
const KEPT_ELEVATION = `${window.location.origin}/api/map/elevation/{z}/{x}/{y}.png`;

const messages = defineMessages({
  en: {
    kept: "Offline base map", none: "Base map unavailable", tools: "Map tools",
    hub: "hub", rotor: "rotor", lasso: "Select with a lasso", lassoHint: "Draw around · Ctrl: add · Esc: stop",
    measure: "Measure a distance", measureHint: "Click point after point · Esc to end",
    base: "Base map", baseAuto: "Base map: theme", baseReal: "Base map: colours (land, sea, relief)",
  },
  fr: {
    kept: "Fond de carte hors ligne", none: "Fond de carte indisponible", tools: "Outils de la carte",
    hub: "moyeu", rotor: "rotor", lasso: "Sélectionner au lasso", lassoHint: "Entourer · Ctrl : ajouter · Échap : arrêter",
    measure: "Mesurer une distance", measureHint: "Cliquer point après point · Échap pour finir",
    base: "Fond de carte", baseAuto: "Fond : selon le thème", baseReal: "Fond : en couleurs (terre, mer, relief)",
  },
});

/** Sends to the application, a few at a time, the base map addresses the window loads, so that
    it keeps a copy of them in the background. Never in the way: a failure only goes unkept. */
const toKeep = new Set<string>();
const keptAlready = new Set<string>();
let keepTimer = 0;
function keepCopy(url: string) {
  if (keptAlready.has(url) || !(url.startsWith(UPSTREAM) || url.startsWith(ELEVATION_SERVER))) return;
  keptAlready.add(url);
  toKeep.add(url);
  if (!keepTimer) keepTimer = window.setTimeout(sendToKeep, 1500);
}
function sendToKeep() {
  window.clearTimeout(keepTimer);
  keepTimer = 0;
  const urls = [...toKeep].slice(0, 1000);
  if (!urls.length) return;
  urls.forEach((u) => toKeep.delete(u));
  const body = new Blob([JSON.stringify({ urls })], { type: "application/json" });
  // A beacon still leaves when the window closes
  if (!navigator.sendBeacon?.("/api/map/keep", body)) void fetch("/api/map/keep", { method: "POST", body }).catch(() => undefined);
  if (toKeep.size) keepTimer = window.setTimeout(sendToKeep, 1500);
}
window.addEventListener("pagehide", sendToKeep);

type Basemap = "online" | "kept" | "none";

/** Writes a problem of the base map in the application's log (once per cause, whatever the tile). */
const reported = new Set<string>();
function reportProblem(message: string) {
  const cause = message.replace(/https?:\/\/\S+/g, "").replace(/\d+/g, "#");
  if (reported.has(cause) || reported.size > 50) return;
  reported.add(cause);
  void fetch("/api/map/problem", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: message.slice(0, 2000) }) }).catch(() => undefined);
}
// Land from green lowlands to brown mountains and white peaks. Nothing below sea level: the
// elevation model cannot tell the sea from land below it (Dutch polders), which keep the base
// map's own colours, and the sea stays neutral until the base map's water is drawn.
const LAND_COLORS: ExpressionSpecification = [
  "interpolate", ["linear"], ["elevation"],
  -0.5, "rgba(143,191,115,0)", 0, "#8fbf73", 150, "#b2cf84", 500, "#ddd395", 1000, "#cfa979", 2000, "#a8825f", 3500, "#f4f4f4",
];
// Sea floor: the deeper, the darker the blue over the water; shallow seas stay as they are
const DEPTH_COLORS: ExpressionSpecification = [
  "interpolate", ["linear"], ["elevation"],
  -6000, "rgba(8,42,92,0.62)", -2000, "rgba(16,60,118,0.48)", -500, "rgba(28,82,146,0.34)",
  -100, "rgba(40,100,165,0.18)", -30, "rgba(40,100,165,0)", 0, "rgba(40,100,165,0)",
];
const WATER_COLOR = "#a6cbe6";

// A font served with the base map's glyphs (MapLibre's default one is not)
const LABEL_FONT = ["Noto Sans Regular"];

/** Relief colours and shading, and a calmer base map (fainter roads, no shops or road shields). */
/** The place names of the base map in the language of the interface, else the local name. */
function localizeLabels(m: MapLibreMap, lang: string) {
  for (const layer of m.getStyle().layers) {
    if (layer.type !== "symbol") continue;
    const field = m.getLayoutProperty(layer.id, "text-field");
    if (field === undefined || !JSON.stringify(field).includes("name")) continue;
    m.setLayoutProperty(layer.id, "text-field", ["coalesce", ["get", `name:${lang}`], ["get", "name:latin"], ["get", "name"]]);
  }
}

function styleBaseMap(m: MapLibreMap, kept: boolean) {
  const layers = m.getStyle().layers;
  // The shaded Natural Earth picture of the style: the relief comes from the elevation tiles
  for (const layer of layers) if (layer.type === "raster") m.setLayoutProperty(layer.id, "visibility", "none");
  const sourceLayer = (layer: (typeof layers)[number]) => (layer as { "source-layer"?: string })["source-layer"];
  const water = layers.findIndex((layer) => layer.id === "water");
  const beforeWater = layers.find((layer) => layer.id.startsWith("waterway"))?.id ?? layers[water]?.id;
  const afterWater = water >= 0 ? layers[water + 1]?.id : undefined;
  const beforeRoads = layers.find((layer) => sourceLayer(layer) === "transportation")?.id;
  m.addSource("elevation", {
    type: "raster-dem", tiles: [kept ? KEPT_ELEVATION : ELEVATION_TILES], tileSize: 256, maxzoom: 15, encoding: "terrarium",
    attribution: "Relief: Mapzen Terrain Tiles (AWS Open Data)",
  });
  m.addLayer({ id: "relief-land", type: "color-relief", source: "elevation", paint: { "color-relief-color": LAND_COLORS, "color-relief-opacity": 0.5 } }, beforeWater);
  m.addLayer({ id: "relief-depth", type: "color-relief", source: "elevation", paint: { "color-relief-color": DEPTH_COLORS } }, afterWater);
  m.addLayer({
    id: "relief-shade", type: "hillshade", source: "elevation",
    paint: { "hillshade-exaggeration": 0.3, "hillshade-shadow-color": "#1d2b22", "hillshade-highlight-color": "#ffffff" },
  }, beforeRoads);
  if (water >= 0) m.setPaintProperty("water", "fill-color", WATER_COLOR);
  for (const layer of layers) {
    const source = sourceLayer(layer);
    if (layer.type === "line" && source === "transportation") m.setPaintProperty(layer.id, "line-opacity", 0.5);
    else if (layer.id === "building") m.setPaintProperty(layer.id, "fill-opacity", 0.45);
    else if (layer.id === "building-3d" || source === "poi" || /^(highway-shield|road_shield|road_one_way)/.test(layer.id)) m.setLayoutProperty(layer.id, "visibility", "none");
  }
}
/** Fits the grid of the farm domain to the zoom: every line once a cell spans 7 pixels, every
    fifth line 2.3 zoom levels before, every tenth 3.3 before; the numbers from 34 pixels. */
function showGrid(m: MapLibreMap, grid: FeatureCollection, size: number) {
  const first = grid.features.find((f) => f.geometry.type === "LineString");
  const latitude = first ? (first.geometry as { coordinates: [number, number][] }).coordinates[0][1] : 0;
  const metresPerPixel0 = 156543.03392 * Math.cos((latitude * Math.PI) / 180);
  const zoomFor = (pixels: number) => Math.log2((pixels * metresPerPixel0) / size);
  const all = zoomFor(7);
  const opacity = (rank0: number, rank1: number, rank2: number): ExpressionSpecification => ["match", ["get", "rank"], 0, rank0, 1, rank1, rank2];
  m.setPaintProperty("cell-line", "line-opacity", [
    "interpolate", ["linear"], ["zoom"],
    all - 3.6, opacity(0, 0, 0), all - 3.3, opacity(0.32, 0, 0),
    all - 2.6, opacity(0.32, 0, 0), all - 2.3, opacity(0.32, 0.24, 0),
    all - 0.3, opacity(0.34, 0.26, 0), all, opacity(0.36, 0.28, 0.18),
  ]);
  m.setLayerZoomRange("cell-count", Math.max(0, zoomFor(34)), 24);
}

const OFFLINE_STYLE: StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{ id: "background", type: "background", paint: { "background-color": "#dfe9ef" } }],
};
// Only green and greys: outer domain dark green, nests lighter, then greys
const DOMAIN_COLORS = ["#0e4d2c", "#1f7f48", "#3aad66", "#495057", "#868e96"];

function palette(kind: "farm" | "domain", fallback: string[]): string[] {
  const tokens = getComputedStyle(document.documentElement);
  return fallback.map((color, index) => tokens.getPropertyValue(`--ows-${kind}-${index}`).trim() || color);
}

/** Restyle only geography and UI markers. Scientific raster fields are never filtered or recoloured. */
export type MapBase = "auto" | "real";
const BASE_KEY = "ows.map.base";

function savedBase(): MapBase {
  try {
    const value = window.localStorage.getItem(BASE_KEY);
    if (value === "real") return value;
  } catch {
    // Storage blocked: the theme decides
  }
  return "auto";
}

/** Great-circle distance between two points, km. */
function distanceKm([lon1, lat1]: [number, number], [lon2, lat2]: [number, number]): number {
  const r = Math.PI / 180;
  const a = Math.sin(((lat2 - lat1) * r) / 2) ** 2 + Math.cos(lat1 * r) * Math.cos(lat2 * r) * Math.sin(((lon2 - lon1) * r) / 2) ** 2;
  return 2 * 6371.0088 * Math.asin(Math.min(1, Math.sqrt(a)));
}

function styleMapTheme(m: MapLibreMap, base: MapBase = "auto") {
  // In colours: a map as on paper, green land and blue sea, whatever the theme
  const real = base === "real";
  const dark = !real && document.documentElement.dataset.mantineColorScheme === "dark";
  const water = real ? WATER_COLOR : dark ? "#191919" : "#edf3ef";
  const land = real ? "#e4eed6" : dark ? "#303030" : "#e0e9df";
  const text = real ? "#33402f" : dark ? "#ddd" : "#405449";
  const halo = dark ? "#191919" : "#fff";
  const accent = dark ? "#f1f1f1" : "#176743";
  for (const layer of m.getStyle().layers) {
    // Project layers have no source-layer; leave their data and result rasters alone.
    const source = (layer as { "source-layer"?: string })["source-layer"];
    if (layer.type === "background") m.setPaintProperty(layer.id, "background-color", water);
    else if (source && layer.type === "fill") m.setPaintProperty(layer.id, "fill-color", /water/.test(source) ? water : land);
    else if (source && layer.type === "line") m.setPaintProperty(layer.id, "line-color", real ? (/water/.test(source) ? "#7fb1d8" : "#c7bfa8") : dark ? "#555" : "#b4c6b8");
    else if (source && layer.type === "symbol") {
      m.setPaintProperty(layer.id, "text-color", text);
      m.setPaintProperty(layer.id, "text-halo-color", halo);
    }
  }
  if (m.getLayer("relief-land")) m.setPaintProperty("relief-land", "color-relief-color", real ? LAND_COLORS : [
    "interpolate", ["linear"], ["elevation"], -0.5, "rgba(0,0,0,0)",
    0, dark ? "#333" : "#cfdfcf", 500, dark ? "#555" : "#b9cfb8", 2000, dark ? "#888" : "#d9e2d7", 3500, "#eee",
  ]);
  if (m.getLayer("relief-depth")) m.setPaintProperty("relief-depth", "color-relief-color", real ? DEPTH_COLORS : [
    "interpolate", ["linear"], ["elevation"], -6000, dark ? "rgba(0,0,0,0.65)" : "rgba(42,78,57,0.35)",
    -500, dark ? "rgba(0,0,0,0.3)" : "rgba(42,78,57,0.12)", 0, "rgba(0,0,0,0)",
  ]);
  if (m.getLayer("measure-line")) {
    m.setPaintProperty("measure-line", "line-color", accent);
    m.setPaintProperty("measure-point", "circle-stroke-color", accent);
    m.setPaintProperty("measure-point", "circle-color", halo);
  }
  if (m.getLayer("relief-shade")) {
    m.setPaintProperty("relief-shade", "hillshade-shadow-color", real ? "#1d2b22" : dark ? "#080808" : "#526656");
    // In colours: the shading of the relief stands out
    m.setPaintProperty("relief-shade", "hillshade-exaggeration", real ? 0.6 : 0.3);
  }
  if (m.getLayer("relief-land")) m.setPaintProperty("relief-land", "color-relief-opacity", real ? 0.9 : 0.5);
  // In colours, the dark greens of the light theme: read on the sea and on the land alike
  const domains = real ? DOMAIN_COLORS : palette("domain", DOMAIN_COLORS);
  const domainColor: ExpressionSpecification = ["match", ["get", "number"], 1, domains[0], 2, domains[1], 3, domains[2], 4, domains[3], domains[4]];
  for (const [id, property] of [["domain-fill", "fill-color"], ["domain-line", "line-color"], ["domain-label", "text-color"]] as const) {
    if (m.getLayer(id)) m.setPaintProperty(id, property, domainColor);
  }
  if (m.getLayer("domain-label")) m.setPaintProperty("domain-label", "text-halo-color", halo);
  for (const id of ["marker", "points", "probes"]) {
    if (m.getLayer(id)) m.setPaintProperty(id, "circle-color", accent);
  }
  if (m.getLayer("selected")) m.setPaintProperty("selected", "circle-color", dark ? "#ffffff" : "#3aad66");
  // The grid of the farm domain in the accent of the theme
  for (const [id, property] of [["cell-line", "line-color"], ["cell-fill", "fill-color"], ["cell-edge", "line-color"], ["cell-count", "text-color"]] as const) {
    if (m.getLayer(id)) m.setPaintProperty(id, property, id === "cell-count" ? (dark ? "#f1f1f1" : "#0e4d2c") : accent);
  }
  for (const id of ["turbine-labels", "probe-labels", "point-labels"]) {
    if (m.getLayer(id)) {
      m.setPaintProperty(id, "text-color", text);
      m.setPaintProperty(id, "text-halo-color", halo);
    }
  }
}
// The backend samples each outline edge with this many points: index 3 × N is the upper-left corner
const POINTS_PER_EDGE = 24;

export interface MapOverlay {
  url: string;
  coordinates: [number, number][];
  opacity: number;
}

export interface MapPoint {
  lat: number;
  lon: number;
  label?: string;
}

interface Props {
  geometry: FeatureCollection | undefined;
  /** Farm ids in display order, for automatic colours and symbols. Explicit appearance wins. */
  farmOrder?: string[];
  markerMode?: "auto" | "all";
  /** How the farms are drawn: their marks (symbol, name, turbine symbols), or only a small dot
      per turbine, for maps of results where the marks would hide the field under them */
  farms?: "marks" | "dots";
  /** Hide generated tslist probes where the task is editing farms or custom measurement points. */
  showProbes?: boolean;
  onFarmClick?: (id: string) => void;
  /** Clicking places a point (domain centre, new turbine, mast...) instead of selecting */
  picking?: boolean;
  onPick?: (lat: number, lon: number) => void;
  onMapClick?: (lat: number, lon: number) => void;
  /** A click on a turbine; `adding` when Ctrl or Shift was held (add to the selection) */
  onTurbineClick?: (properties: GeoFeature["properties"], adding: boolean) => void;
  overlay?: MapOverlay | null;
  marker?: MapPoint | null;
  /** Selected turbines (farm id and number in the farm, from 1): ringed, the others dimmed */
  selected?: { farm: string; number: number; lat: number; lon: number }[];
  /** Extra points drawn on top (draft turbines of a zone, observation stations...) */
  points?: MapPoint[];
  /** Frame the extra points whenever they change (previews of turbines about to be added) */
  fitPoints?: boolean;
  /** Tools of the page, first in the map's icon bar (ToolToggle...) */
  extraTools?: ReactNode;
  /** With it, a lasso tool: the outline drawn (lon, lat), once the mouse is released; `adding`
      when Ctrl or Shift was held. The tool stays on until clicked again or Escape. */
  onLasso?: (outline: [number, number][], adding: boolean) => void;
  /** Extra polygons (placement zone, imported layers) */
  polygons?: FeatureCollection;
  /** Grid of the farm domain: its lines (kind "line", rank 0/1/2) and the cells holding turbines
      (kind "cell", with "count" and "turbines") */
  cells?: FeatureCollection;
  /** The farm whose cells light up (a farm just chosen) */
  litFarm?: string | null;
  /** Size of a grid cell (m): the map thins the grid out and writes the numbers by it */
  cellSize?: number;
  onCellClick?: (properties: Record<string, unknown>) => void;
  height?: number | string;
  ariaLabel?: string;
  /** What the map frames when it opens: the outer domain (default) or the turbines */
  fit?: "domains" | "turbines";
  /** What to frame: "all" turbines, "farm:<id>", "domain" (the outer domain) or "domain:<n>". A new key frames
      again, even the same target (the map may have been moved since). */
  frame?: { target: string; key: number };
}

const empty: FeatureCollection = { type: "FeatureCollection", features: [] };

function split(geometry: FeatureCollection) {
  const domains = geometry.features.filter((f) => f.properties.kind === "domain");
  const labels: GeoFeature[] = domains.map((d) => {
    const ring = (d.geometry as { coordinates: [number, number][][] }).coordinates[0];
    const dx = d.properties.dx ?? 0;
    return {
      type: "Feature",
      geometry: { type: "Point", coordinates: ring[3 * POINTS_PER_EDGE] ?? ring[0] },
      properties: {
        kind: "domain",
        number: d.properties.number,
        label: `d${String(d.properties.number).padStart(2, "0")} · ${dx >= 1000 ? `${dx / 1000} km` : `${dx} m`}`,
      },
    };
  });
  return {
    domains: collection(domains),
    labels: collection(labels),
    turbines: collection(geometry.features.filter((f) => f.properties.kind === "turbine")),
    probes: collection(geometry.features.filter((f) => f.properties.kind === "probe")),
  };
}

function pointCollection(points: MapPoint[]): FeatureCollection {
  return collection(
    points.map((p) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [p.lon, p.lat] },
      properties: { kind: "probe", label: p.label },
    })),
  );
}

export function ProjectMap({
  geometry,
  farmOrder = [],
  markerMode = "auto",
  farms = "marks",
  litFarm = null,
  showProbes = true,
  onFarmClick,
  picking = false,
  onPick,
  onMapClick,
  onTurbineClick,
  overlay,
  marker,
  points,
  selected,
  polygons,
  cells,
  cellSize,
  onCellClick,
  height = 480,
  ariaLabel,
  fit = "domains",
  frame,
  fitPoints = false,
  extraTools,
  onLasso,
}: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const fitted = useRef(false);
  const ready = useRef(false);
  const savedView = useRef<{ center: [number, number]; zoom: number } | null>(null);
  const farmMarkers = useRef(new Map<string, Marker>());
  const iconColors = useRef(new Map<string, string>());
  const displayedFarms = useRef<{ geometry: FeatureCollection; key: string } | null>(null);
  const props = useRef({ geometry, farmOrder, markerMode, farms, litFarm, showProbes, onFarmClick, picking, onPick, onMapClick, onTurbineClick, overlay, marker, selected, points, polygons, cells, cellSize, onCellClick, fit, frame, fitPoints });
  props.current = { geometry, farmOrder, markerMode, farms, litFarm, showProbes, onFarmClick, picking, onPick, onMapClick, onTurbineClick, overlay, marker, selected, points, polygons, cells, cellSize, onCellClick, fit, frame, fitPoints };
  const { lang } = useLang();
  const langRef = useRef(lang);
  langRef.current = lang;

  /** Frames a domain (number 1 = the outer one). */
  const frameDomain = (m: MapLibreMap, domains: FeatureCollection, animate: boolean, number = 1): boolean => {
    const domain = domains.features.find((d) => d.properties.number === number) ?? (number === 1 ? domains.features[0] : undefined);
    if (!domain) return false;
    const bounds = new LngLatBounds();
    (domain.geometry as { coordinates: [number, number][][] }).coordinates[0].forEach((p) => bounds.extend(p));
    m.fitBounds(bounds, { padding: 40, ...glideTo(animate) });
    return true;
  };

  /** Frames a target ("all" turbines, "farm:<id>", "domain" for the outer domain or "domain:<n>"),
      close enough to see each turbine but with their surroundings; false when there is nothing
      to frame. */
  const frameTarget = (m: MapLibreMap, target: string, animate: boolean): boolean => {
    const data = props.current.geometry;
    if (!data) return false;
    const parts = split(data);
    if (target === "domain") return frameDomain(m, parts.domains, animate);
    if (target.startsWith("domain:")) return frameDomain(m, parts.domains, animate, Number(target.slice(7)));
    const farm = target.startsWith("farm:") ? target.slice(5) : null;
    const own = farm ? parts.turbines.features.filter((f) => f.properties.farm === farm) : [];
    const chosen = own.length ? own : parts.turbines.features;
    if (!chosen.length) return false;
    const bounds = new LngLatBounds();
    chosen.forEach((f) => bounds.extend((f.geometry as { coordinates: [number, number] }).coordinates));
    m.fitBounds(bounds, { padding: 70, maxZoom: 12, ...glideTo(animate) });
    return true;
  };

  const showGeometry = (m: MapLibreMap) => {
    const data = props.current.geometry;
    if (!data) return;
    const parts = split(data);
    (m.getSource("domains") as GeoJSONSource).setData(parts.domains);
    (m.getSource("labels") as GeoJSONSource).setData(parts.labels);
    (m.getSource("probes") as GeoJSONSource).setData(parts.probes);
    m.setLayoutProperty("probes", "visibility", props.current.showProbes ? "visible" : "none");
    m.setLayoutProperty("probe-labels", "visibility", props.current.showProbes && !props.current.points?.some((p) => p.label) ? "visible" : "none");
    showFarms(m);
    if (fitted.current) return;
    const first = props.current.frame?.target ?? (props.current.fit === "turbines" ? "all" : null);
    if (first && frameTarget(m, first, false)) fitted.current = true;
    else if (frameDomain(m, parts.domains, false)) fitted.current = true;
  };

  const showFarms = (m: MapLibreMap) => {
    const data = props.current.geometry;
    if (!data) return;
    const dots = props.current.farms === "dots";
    m.setLayoutProperty("turbines", "visibility", dots ? "none" : "visible");
    m.setLayoutProperty("turbine-labels", "visibility", dots ? "none" : "visible");
    m.setLayoutProperty("turbine-dots", "visibility", dots ? "visible" : "none");
    if (dots) {
      for (const marker of farmMarkers.current.values()) marker.remove();
      farmMarkers.current.clear();
      if (displayedFarms.current?.geometry !== data || displayedFarms.current.key !== "dots") {
        (m.getSource("turbines") as GeoJSONSource).setData(split(data).turbines);
        displayedFarms.current = { geometry: data, key: "dots" };
      }
      return;
    }
    const display = farmDisplay(data, props.current.farmOrder, (p) => m.project(p), props.current.markerMode);
    const halo = document.documentElement.dataset.mantineColorScheme === "dark" ? "#171717" : "#ffffff";
    const key = `${props.current.farmOrder.join("|")}:${props.current.markerMode}:${halo}:${display.tags.map((farm) => `${farm.id}=${farm.level}`).join("|")}:${display.details.features.filter((feature) => feature.properties.showLabel).length}`;
    const previous = displayedFarms.current;
    if (!previous || previous.geometry !== data || previous.key !== key) {
      const prepared = new Set<string>();
      const features = display.details.features.map((feature) => {
        const { color = "#21845a", symbol = "circle" } = feature.properties;
        const icon = `farm-${feature.properties.farm}-${symbol}`;
        if (!prepared.has(icon)) {
          if (!m.hasImage(icon)) m.addImage(icon, markerImage(symbol, color, halo), { pixelRatio: 2 });
          else if (iconColors.current.get(icon) !== color + halo) m.updateImage(icon, markerImage(symbol, color, halo));
          iconColors.current.set(icon, color + halo); prepared.add(icon);
        }
        return { ...feature, properties: { ...feature.properties, icon } };
      });
      (m.getSource("turbines") as GeoJSONSource).setData(collection(features));
      displayedFarms.current = { geometry: data, key };
    }
    const kept = new Set(display.tags.map((farm) => farm.id));
    for (const [id, marker] of farmMarkers.current) if (!kept.has(id)) { marker.remove(); farmMarkers.current.delete(id); }
    // From afar, farm marks that would cover each other stand side by side around their middle
    const shifts = new Map<string, [number, number]>();
    const icons = display.tags.filter((farm) => farm.level === "icon").map((farm) => ({ id: farm.id, p: m.project(farm.center) }));
    const clusters: (typeof icons)[] = [];
    for (const icon of icons) {
      const cluster = clusters.find((group) => group.some((other) => Math.hypot(other.p.x - icon.p.x, other.p.y - icon.p.y) < 26));
      if (cluster) cluster.push(icon);
      else clusters.push([icon]);
    }
    for (const cluster of clusters) {
      const mx = cluster.reduce((sum, icon) => sum + icon.p.x, 0) / cluster.length;
      const my = cluster.reduce((sum, icon) => sum + icon.p.y, 0) / cluster.length;
      cluster.forEach((icon, k) => shifts.set(icon.id, cluster.length > 1 ? [mx + (k - (cluster.length - 1) / 2) * 28 - icon.p.x, my - icon.p.y] : [0, 0]));
    }
    const labels = (props.current.points ?? []).filter((point) => point.label).map((point) => {
      const p = m.project([point.lon, point.lat]), width = point.label!.length * 7 + 14;
      return { x: p.x + 10 + width / 2, y: p.y, width };
    });
    for (const farm of display.tags) {
      let marker = farmMarkers.current.get(farm.id);
      if (!marker) {
        const button = document.createElement("button");
        button.type = "button"; button.className = "ows-map-farm-summary";
        button.addEventListener("click", (event) => {
          event.stopPropagation();
          if (props.current.picking) return;
          if (props.current.onFarmClick) props.current.onFarmClick(farm.id);
          else frameTarget(m, `farm:${farm.id}`, true);
        });
        marker = new Marker({ element: button, anchor: "center" }).setLngLat(farm.center).addTo(m);
        farmMarkers.current.set(farm.id, marker);
      }
      const button = marker.getElement();
      // From afar only the farm's symbol; its name once the farm is large enough on screen
      const content = `${farm.symbol}:${farm.color}:${farm.name}:${farm.count}:${farm.enabled}:${farm.level === "icon"}`;
      if (button.dataset.content !== content) {
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("viewBox", "0 0 24 24"); svg.setAttribute("aria-hidden", "true");
        const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
        path.setAttribute("d", SYMBOL_PATHS[farm.symbol]); path.setAttribute("fill", "currentColor"); svg.append(path);
        if (farm.level === "icon") button.replaceChildren(svg);
        else { const label = document.createElement("span"); label.textContent = farm.name; button.replaceChildren(svg, label); }
        button.style.setProperty("--farm-color", farm.color);
        button.dataset.disabled = String(!farm.enabled);
        button.setAttribute("aria-label", `${farm.name} · ${farm.count}`);
        button.title = `${farm.name} · ${farm.count}`;
        button.dataset.content = content;
      }
      button.dataset.level = farm.level;
      // With its turbines drawn, the name sits just above the farm instead of over them
      const anchor = farm.level === "turbines" ? farm.top : farm.center;
      const lift = farm.level === "turbines" ? -22 : 0;
      const p = m.project(anchor), width = farm.level === "icon" ? 26 : farm.name.length * 7 + 36;
      // From afar the mark sits exactly on its farm, even over another one; names step aside
      let offset = 0;
      while (farm.level !== "icon" && labels.some((other) => Math.abs(p.x - other.x) < (width + other.width) / 2 + 6 && Math.abs(p.y + lift + offset - other.y) < 30)) offset += 32;
      labels.push({ x: p.x, y: p.y + lift + offset, width });
      marker.setLngLat(anchor).setOffset(farm.level === "icon" ? shifts.get(farm.id) ?? [0, 0] : [0, lift + offset]);
    }
  };

  const showOverlay = (m: MapLibreMap) => {
    const value = props.current.overlay;
    const source = m.getSource("result") as ImageSource | undefined;
    if (!value) {
      if (m.getLayer("result")) m.removeLayer("result");
      if (source) m.removeSource("result");
      return;
    }
    const coordinates = value.coordinates as Coordinates;
    if (source) {
      source.updateImage({ url: value.url, coordinates });
      m.setPaintProperty("result", "raster-opacity", value.opacity);
    } else {
      m.addSource("result", { type: "image", url: value.url, coordinates });
      // One pixel per grid cell: nearest resampling shows the model's actual cells
      m.addLayer(
        { id: "result", type: "raster", source: "result", paint: { "raster-opacity": value.opacity, "raster-resampling": "nearest" } },
        "domain-fill",
      );
    }
  };

  const showExtras = (m: MapLibreMap) => {
    const { marker: mark, points: extra, polygons: zones, cells: grid, cellSize: size } = props.current;
    (m.getSource("cells") as GeoJSONSource).setData(grid ?? empty);
    if (grid && size) showGrid(m, grid, size);
    // The cells of the farm just chosen light up, fading in
    const lit = props.current.litFarm;
    m.setFilter("cell-lit", ["all", ["==", ["get", "kind"], "cell"], ["in", `, ${lit ?? "\u0000"},`, ["concat", ", ", ["get", "farms"], ","]]]);
    m.setPaintProperty("cell-lit", "fill-opacity", 0);
    if (lit) requestAnimationFrame(() => { if (m.getLayer("cell-lit")) m.setPaintProperty("cell-lit", "fill-opacity", 0.38); });
    (m.getSource("marker") as GeoJSONSource).setData(mark ? pointCollection([mark]) : empty);
    const chosen = props.current.selected ?? [];
    (m.getSource("selected") as GeoJSONSource).setData(pointCollection(chosen));
    // While turbines are selected, the others step back
    const keys = chosen.map((p) => `${p.farm}:${p.number}`);
    const others: ExpressionSpecification = ["!", ["in", ["concat", ["get", "farm"], ":", ["to-string", ["get", "number"]]], ["literal", keys]]];
    m.setPaintProperty("turbines", "icon-opacity", keys.length
      ? ["case", others, 0.22, ["==", ["get", "enabled"], false], 0.42, 1]
      : ["case", ["==", ["get", "enabled"], false], 0.42, 1]);
    (m.getSource("points") as GeoJSONSource).setData(pointCollection(extra ?? []));
    (m.getSource("polygons") as GeoJSONSource).setData(zones ?? empty);
    m.setLayoutProperty("probe-labels", "visibility", props.current.showProbes && !extra?.some((point) => point.label) ? "visible" : "none");
    showFarms(m);
    if (props.current.fitPoints && extra?.length) {
      const bounds = new LngLatBounds();
      extra.forEach((point) => bounds.extend([point.lon, point.lat]));
      m.fitBounds(bounds, { padding: 50, maxZoom: 12, duration: 0 });
      fitted.current = true;
    }
  };

  const addLayers = (m: MapLibreMap) => {
    for (const id of ["domains", "labels", "turbines", "probes", "marker", "selected", "points", "polygons", "cells", "measure", "lasso"]) {
      if (!m.getSource(id)) m.addSource(id, { type: "geojson", data: empty });
    }
    const color: ExpressionSpecification = [
      "match", ["get", "number"], 1, DOMAIN_COLORS[0], 2, DOMAIN_COLORS[1], 3, DOMAIN_COLORS[2], 4, DOMAIN_COLORS[3], DOMAIN_COLORS[4],
    ];
    m.addLayer({ id: "domain-fill", type: "fill", source: "domains", paint: { "fill-color": color, "fill-opacity": 0.05 } });
    m.addLayer({ id: "domain-casing", type: "line", source: "domains", paint: { "line-color": "#ffffff", "line-width": 5, "line-opacity": 0.7 } });
    m.addLayer({ id: "domain-line", type: "line", source: "domains", paint: { "line-color": color, "line-width": 2.5 } });
    m.addLayer({
      id: "domain-label",
      type: "symbol",
      source: "labels",
      layout: { "text-font": LABEL_FONT, "text-field": ["get", "label"], "text-size": 12, "text-anchor": "top-left", "text-offset": [0.4, 0.4] },
      paint: { "text-color": color, "text-halo-color": "#fff", "text-halo-width": 1.5 },
    });
    // The grid of the farm domain (one source): fine lines thinned out when zoomed out, the cells
    // holding turbines filled by their number, the number written once a cell is large enough
    m.addLayer({ id: "cell-line", type: "line", source: "cells", filter: ["==", ["get", "kind"], "line"], paint: { "line-color": "#1f7f48", "line-width": 0.6, "line-opacity": 0.3 } });
    m.addLayer({ id: "cell-fill", type: "fill", source: "cells", filter: ["==", ["get", "kind"], "cell"], paint: {
      "fill-color": "#1f7f48",
      "fill-opacity": ["interpolate", ["linear"], ["get", "count"], 1, 0.08, 4, 0.14, 12, 0.22, 40, 0.32],
    } });
    m.addLayer({ id: "cell-edge", type: "line", source: "cells", filter: ["==", ["get", "kind"], "cell"], paint: { "line-color": "#1f7f48", "line-width": 1, "line-opacity": 0.55 } });
    m.addLayer({ id: "cell-lit", type: "fill", source: "cells", filter: ["==", ["get", "kind"], "none"], paint: { "fill-color": "#3aad66", "fill-opacity": 0, "fill-opacity-transition": { duration: 450, delay: 0 } } });
    m.addLayer({
      id: "cell-count",
      type: "symbol",
      source: "cells",
      minzoom: 10,
      filter: ["==", ["get", "kind"], "cell"],
      layout: { "text-font": LABEL_FONT, "text-field": ["to-string", ["get", "count"]], "text-size": 10.5, "text-allow-overlap": false },
      paint: { "text-color": "#0e4d2c", "text-opacity": 0.85 },
    });
    // The distance being measured: a dashed line and its points
    m.addLayer({ id: "measure-line", type: "line", source: "measure", filter: ["==", ["geometry-type"], "LineString"], paint: { "line-color": "#176743", "line-width": 2, "line-dasharray": [3, 2] } });
    m.addLayer({ id: "measure-point", type: "circle", source: "measure", filter: ["==", ["geometry-type"], "Point"], paint: { "circle-radius": 4, "circle-color": "#fff", "circle-stroke-color": "#176743", "circle-stroke-width": 2 } });
    m.addLayer({ id: "lasso-fill", type: "fill", source: "lasso", paint: { "fill-color": "#3aad66", "fill-opacity": 0.12 } });
    m.addLayer({ id: "lasso-line", type: "line", source: "lasso", paint: { "line-color": "#176743", "line-width": 1.5, "line-dasharray": [2, 2] } });
    m.addLayer({ id: "polygon-fill", type: "fill", source: "polygons", paint: { "fill-color": "#3aad66", "fill-opacity": 0.14 } });
    m.addLayer({ id: "polygon-line", type: "line", source: "polygons", paint: { "line-color": "#1f7f48", "line-width": 1.5, "line-dasharray": [2, 1] } });
    m.addLayer({ id: "turbines", type: "symbol", source: "turbines", layout: {
      "icon-image": ["get", "icon"], "icon-size": ["interpolate", ["linear"], ["zoom"], 5, 0.34, 12, 0.5, 16, 0.65],
      "icon-allow-overlap": true, "icon-ignore-placement": true,
    }, paint: { "icon-opacity": ["case", ["==", ["get", "enabled"], false], 0.42, 1] } });
    // The farm drawn lightly on maps of results: one small dot per turbine, at every zoom
    m.addLayer({ id: "turbine-dots", type: "circle", source: "turbines", layout: { visibility: "none" }, paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 5, 1, 9, 1.8, 12, 3, 15, 4.5],
      "circle-color": "#1d1d1d", "circle-opacity": 0.75,
      "circle-stroke-color": "#ffffff", "circle-stroke-width": 0.6, "circle-stroke-opacity": 0.75,
    } });
    m.addLayer({
      id: "turbine-labels",
      type: "symbol",
      source: "turbines",
      // Only where the farm leaves room for them; overlapping names are left out by MapLibre
      filter: ["==", ["get", "showLabel"], true],
      layout: { "text-font": LABEL_FONT, "text-field": ["get", "label"], "text-size": 10, "text-anchor": "left", "text-offset": [0.7, 0] },
      paint: { "text-color": "#343a40", "text-halo-color": "#fff", "text-halo-width": 1.2 },
    });
    m.addLayer({
      id: "probes",
      type: "circle",
      source: "probes",
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 5, 2.5, 10, 6],
        "circle-color": "#ffffff",
        "circle-stroke-color": "#0e4d2c",
        "circle-stroke-width": 2,
      },
    });
    m.addLayer({
      id: "probe-labels",
      type: "symbol",
      source: "probes",
      minzoom: 8,
      layout: { "text-font": LABEL_FONT, "text-field": ["coalesce", ["get", "prefix"], ["get", "label"]], "text-size": 11, "text-anchor": "left", "text-offset": [0.8, 0] },
      paint: { "text-color": "#0e4d2c", "text-halo-color": "#fff", "text-halo-width": 1.5 },
    });
    m.addLayer({
      id: "points",
      type: "circle",
      source: "points",
      paint: { "circle-radius": 3.5, "circle-color": "#7ac996", "circle-stroke-color": "#0e4d2c", "circle-stroke-width": 1 },
    });
    m.addLayer({
      id: "point-labels",
      type: "symbol",
      source: "points",
      filter: ["has", "label"],
      layout: { "text-font": LABEL_FONT, "text-field": ["get", "label"], "text-size": 11.5, "text-anchor": "left", "text-offset": [0.9, 0], "text-optional": true },
      paint: { "text-color": "#193126", "text-halo-color": "#ffffff", "text-halo-width": 1.4 },
    });
    m.addLayer({
      id: "marker",
      type: "circle",
      source: "marker",
      paint: { "circle-radius": 6, "circle-color": "#dc4a4a", "circle-stroke-color": "#fff", "circle-stroke-width": 2 },
    });
    // Selected turbines: a soft glow under each symbol, in the colour of the theme (set by
    // styleMapTheme); the symbols stay on top, readable, and the others are dimmed
    m.addLayer({
      id: "selected",
      type: "circle",
      source: "selected",
      paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 7, 4, 11, 6, 13, 9, 15, 13], "circle-color": "#3aad66", "circle-opacity": 0.45, "circle-blur": 0.6 },
    }, "turbines");
    ready.current = true;
    showGeometry(m);
    showOverlay(m);
    showExtras(m);
  };

  // Which base map shows, and the discreet note saying so when it is not the online one
  const t = useT(messages);
  const tipText = (key: "hub" | "rotor") => tRef.current(key);
  const tRef = useRef(t);
  tRef.current = t;
  const [basemap, setBasemap] = useState<Basemap>("online");
  const note = useRef<HTMLDivElement | null>(null);

  // The tools of every map (top left): measure a distance, choose the base map
  const [tools, setTools] = useState<HTMLDivElement | null>(null);
  const [base, setBase] = useState<MapBase>(savedBase);
  const baseRef = useRef(base);
  baseRef.current = base;
  const [measuring, setMeasuring] = useState(false);
  const measuringRef = useRef(false);
  measuringRef.current = measuring;
  const measurePoints = useRef<[number, number][]>([]);
  const measureLabel = useRef<Marker | null>(null);
  const showMeasure = (m: MapLibreMap) => {
    const points = measurePoints.current;
    const features = [
      ...points.map((p) => ({ type: "Feature" as const, properties: {}, geometry: { type: "Point" as const, coordinates: p } })),
      ...(points.length > 1 ? [{ type: "Feature" as const, properties: {}, geometry: { type: "LineString" as const, coordinates: points } }] : []),
    ];
    (m.getSource("measure") as GeoJSONSource | undefined)?.setData({ type: "FeatureCollection", features } as never);
    measureLabel.current?.remove();
    measureLabel.current = null;
    if (points.length > 1) {
      let km = 0;
      for (let n = 1; n < points.length; n++) km += distanceKm(points[n - 1], points[n]);
      // MapLibre places the marker with a transform: the look goes on an inner element
      const element = document.createElement("div");
      const label = document.createElement("span");
      label.className = "ows-measure-label";
      label.textContent = `${new Intl.NumberFormat(lang, { maximumFractionDigits: km < 10 ? 2 : 1 }).format(km)} km`;
      element.append(label);
      measureLabel.current = new Marker({ element, anchor: "bottom", offset: [0, -8] }).setLngLat(points[points.length - 1]).addTo(m);
    }
  };
  // Lasso: while on, a drag draws an outline instead of moving the map; it stays on for several
  // outlines, until its button is clicked again or Escape
  const [lassoing, setLassoing] = useState(false);
  const onLassoRef = useRef(onLasso);
  onLassoRef.current = onLasso;
  useEffect(() => {
    const m = map.current;
    if (!lassoing || !m) return;
    m.dragPan.disable();
    let outline: [number, number][] | null = null;
    let adding = false;
    const show = () => (m.getSource("lasso") as GeoJSONSource | undefined)?.setData(
      outline && outline.length > 2 ? ({ type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [[...outline, outline[0]]] } } as never) : (empty as never),
    );
    const down = (e: MapMouseEvent) => {
      outline = [[e.lngLat.lng, e.lngLat.lat]];
      adding = e.originalEvent.ctrlKey || e.originalEvent.shiftKey || e.originalEvent.metaKey;
    };
    const move = (e: MapMouseEvent) => { if (outline) { outline.push([e.lngLat.lng, e.lngLat.lat]); show(); } };
    const up = () => {
      if (outline && outline.length > 2) onLassoRef.current?.(outline, adding);
      outline = null;
      show();
    };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") setLassoing(false); };
    m.on("mousedown", down);
    m.on("mousemove", move);
    m.on("mouseup", up);
    window.addEventListener("keydown", escape);
    return () => {
      m.off("mousedown", down);
      m.off("mousemove", move);
      m.off("mouseup", up);
      window.removeEventListener("keydown", escape);
      m.dragPan.enable();
      show();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lassoing]);
  const stopMeasure = () => {
    measurePoints.current = [];
    if (map.current && ready.current) showMeasure(map.current);
    setMeasuring(false);
  };
  useEffect(() => {
    if (!measuring) return;
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") stopMeasure(); };
    window.addEventListener("keydown", escape);
    if (map.current) map.current.getCanvas().style.cursor = "crosshair";
    return () => {
      window.removeEventListener("keydown", escape);
      if (map.current) map.current.getCanvas().style.cursor = props.current.picking ? "crosshair" : "";
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [measuring]);
  useEffect(() => {
    try { window.localStorage.setItem(BASE_KEY, base); } catch { /* not remembered */ }
    if (map.current && ready.current) styleMapTheme(map.current, base);
  }, [base]);

  // Created only once the map is on screen (a closed fold, a hidden tab or a page further down
  // costs nothing)
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const element = container.current;
    if (!element || visible) return;
    const watcher = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) setVisible(true);
    }, { rootMargin: "200px" });
    watcher.observe(element);
    return () => watcher.disconnect();
  }, [visible]);

  useEffect(() => {
    if (!visible) return;
    // React Activity suspends effects for a hidden tab while retaining component state.
    // A recreated map has no sources until load, even if the previous map was ready.
    ready.current = false;
    displayedFarms.current = null;
    fitted.current = savedView.current !== null;
    const view = savedView.current ?? { center: [5, 55] as [number, number], zoom: 3.5 };
    const started = performance.now();
    // The base map: online first; the copy kept on disk when the style cannot be
    // had or when every tile fails; a plain background when there is no copy either
    let stage: Basemap = "online";
    setBasemap("online");
    const m = new MapLibreMap({
      container: container.current!, style: ONLINE_STYLE, ...view, attributionControl: { compact: true },
      // Only looks at the addresses (never changes them), to keep a copy of what was loaded
      transformRequest: (url) => {
        if (stage === "online") keepCopy(url);
        return { url };
      },
    });
    let loaded = false;
    // Map load times, exposed on window.__owsMapTimings for performance checks
    let styled = 0;
    m.once("idle", () => {
      const timings = window as unknown as { __owsMapTimings?: object[] };
      timings.__owsMapTimings = [...(timings.__owsMapTimings ?? []), { page: location.hash, style_ms: Math.round(styled - started), idle_ms: Math.round(performance.now() - started) }];
    });
    m.addControl(new NavigationControl({ showCompass: false }), "top-right");
    m.addControl(new ScaleControl({ unit: "metric" }), "bottom-left");
    const noteElement = document.createElement("div");
    noteElement.className = "maplibregl-ctrl ows-map-note";
    noteElement.hidden = true;
    note.current = noteElement;
    // The tools, drawn by React into a control of the map
    const toolsElement = document.createElement("div");
    toolsElement.className = "maplibregl-ctrl ows-map-tools";
    m.addControl({ onAdd: () => toolsElement, onRemove: () => toolsElement.remove() }, "top-left");
    setTools(toolsElement);
    m.addControl({ onAdd: () => noteElement, onRemove: () => noteElement.remove() }, "top-left");
    // As soon as the base map's style is in (tiles come later, even while the window is hidden
    // and draws nothing): restyle it and add the project's layers
    m.on("style.load", () => {
      loaded = true;
      styled = performance.now();
      window.clearTimeout(fallback);
      if (stage !== "none") {
        styleBaseMap(m, stage === "kept");
        localizeLabels(m, langRef.current);
      }
      addLayers(m);
      styleMapTheme(m, baseRef.current);
    });
    // The next way of showing the base map, the cause written in the application's log
    const fallBack = (cause: string) => {
      if (stage === "none") return;
      reportProblem(stage === "online"
        ? `online base map not shown, the copy kept on disk is used: ${cause}`
        : `no copy of the base map, plain background: ${cause}`);
      stage = stage === "online" ? "kept" : "none";
      setBasemap(stage);
      loaded = false;
      ready.current = false;
      displayedFarms.current = null;
      m.setStyle(stage === "kept" ? KEPT_STYLE : OFFLINE_STYLE, { diff: false });
      window.clearTimeout(fallback);
      fallback = window.setTimeout(() => { if (!loaded) fallBack("no answer within 10 s"); }, 10000);
    };
    // The credits open over the bottom of the map at first: keep them folded behind their "i"
    // (MapLibre unfolds them when the first credits arrive with the data; fold them right after)
    const fold = () => {
      const credits = container.current?.querySelector(".maplibregl-ctrl-attrib");
      if (!credits?.classList.contains("maplibregl-compact")) return;
      credits.classList.remove("maplibregl-compact-show");
      m.off("styledata", fold);
      m.off("sourcedata", fold);
    };
    m.on("styledata", fold);
    m.on("sourcedata", fold);
    let fallback = window.setTimeout(() => {
      if (!loaded) fallBack("no answer within 10 s");
    }, 10000);
    // Tiles of the online base map: if every one fails, the map would stay blank
    let baseTiles = 0;
    let baseErrors = 0;
    m.on("data", (event) => {
      if (event.dataType === "source" && "tile" in event && event.tile && "sourceId" in event && event.sourceId === "openmaptiles") baseTiles += 1;
    });
    m.on("error", (event) => {
      const message = String(event.error?.message ?? event.error ?? "unknown error");
      const source = (event as { sourceId?: string }).sourceId;
      if (!loaded && !source) { fallBack(message); return; }
      if (stage !== "online" || (source !== "openmaptiles" && source !== "elevation")) return;
      reportProblem(`${source} tiles: ${message}`);
      if (source === "openmaptiles" && ++baseErrors >= 4 && baseTiles === 0) fallBack(`every tile failed (${message})`);
    });
    m.on("click", (e: MapMouseEvent) => {
      const p = props.current;
      if (measuringRef.current) {
        measurePoints.current = [...measurePoints.current, [e.lngLat.lng, e.lngLat.lat]];
        showMeasure(m);
        return;
      }
      if (p.picking) p.onPick?.(e.lngLat.lat, e.lngLat.lng);
      // A click on a turbine is its own (handled below), not a click on the map
      else if (!(p.onTurbineClick && m.getLayer("turbines") && m.queryRenderedFeatures(e.point, { layers: ["turbines"] }).length)) p.onMapClick?.(e.lngLat.lat, e.lngLat.lng);
    });
    m.on("click", "turbines", (e: MapLayerMouseEvent) => {
      const p = props.current;
      const feature = e.features?.[0];
      if (!p.picking && feature) p.onTurbineClick?.(feature.properties as GeoFeature["properties"], e.originalEvent.ctrlKey || e.originalEvent.shiftKey || e.originalEvent.metaKey);
    });
    // Hovering a cell lists its turbines
    const cellTip = new Popup({ closeButton: false, closeOnClick: false, className: "ows-cell-tip", offset: 10, maxWidth: "280px" });
    m.on("mousemove", "cell-fill", (e: MapLayerMouseEvent) => {
      const names = String(e.features?.[0]?.properties?.turbines ?? "").split(", ").filter(Boolean);
      if (!names.length || props.current.picking) { cellTip.remove(); return; }
      cellTip.setLngLat(e.lngLat).setText(names.length > 24 ? `${names.slice(0, 24).join(", ")}, …` : names.join(", ")).addTo(m);
    });
    m.on("mouseleave", "cell-fill", () => cellTip.remove());
    // Resting on a turbine: its card (name, farm, model, hub height, rotor, power)
    const turbineTip = new Popup({ closeButton: false, closeOnClick: false, className: "ows-turbine-tip", offset: 12, maxWidth: "260px" });
    m.on("mousemove", "turbines", (e: MapLayerMouseEvent) => {
      const p = e.features?.[0]?.properties as Record<string, unknown> | undefined;
      if (!p || props.current.picking || measuringRef.current) { turbineTip.remove(); return; }
      const number = new Intl.NumberFormat(lang, { maximumFractionDigits: 1 });
      const card = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = `${p.label} · ${p.farm_name}`;
      const line = document.createElement("div");
      line.textContent = [
        p.model ? String(p.model) : null,
        typeof p.hub_m === "number" ? `${tipText("hub")} ${number.format(p.hub_m)} m` : null,
        typeof p.rotor_m === "number" ? `${tipText("rotor")} ${number.format(p.rotor_m)} m` : null,
        typeof p.power_mw === "number" ? `${number.format(p.power_mw)} MW` : null,
      ].filter(Boolean).join(" · ");
      card.append(title, line);
      turbineTip.setLngLat(e.lngLat).setDOMContent(card).addTo(m);
    });
    m.on("mouseleave", "turbines", () => turbineTip.remove());
    m.on("click", "cell-fill", (e: MapLayerMouseEvent) => {
      const p = props.current;
      const feature = e.features?.[0];
      if (!p.picking && feature) p.onCellClick?.(feature.properties as Record<string, unknown>);
    });
    m.on("mouseenter", "cell-fill", () => {
      if (props.current.onCellClick && !props.current.picking) m.getCanvas().style.cursor = "pointer";
    });
    m.on("mouseleave", "cell-fill", () => {
      m.getCanvas().style.cursor = props.current.picking ? "crosshair" : "";
    });
    m.on("mouseenter", "turbines", () => {
      if (props.current.onTurbineClick) m.getCanvas().style.cursor = "pointer";
    });
    m.on("mouseleave", "turbines", () => {
      m.getCanvas().style.cursor = props.current.picking ? "crosshair" : "";
    });
    map.current = m;
    const appearance = new MutationObserver(() => {
      if (!ready.current) return;
      styleMapTheme(m, baseRef.current);
      showFarms(m);
    });
    appearance.observe(document.documentElement, { attributes: true, attributeFilter: ["data-mantine-color-scheme"] });
    let scheduled = 0;
    const displayFarms = () => {
      if (scheduled || !ready.current) return;
      scheduled = requestAnimationFrame(() => { scheduled = 0; if (ready.current) showFarms(m); });
    };
    m.on("zoom", displayFarms); m.on("moveend", displayFarms); m.on("resize", displayFarms);
    const resize = new ResizeObserver(() => m.resize());
    resize.observe(container.current!);
    return () => {
      window.clearTimeout(fallback);
      resize.disconnect();
      appearance.disconnect();
      cancelAnimationFrame(scheduled);
      farmMarkers.current.forEach((marker) => marker.remove()); farmMarkers.current.clear();
      iconColors.current.clear();
      displayedFarms.current = null;
      const centre = m.getCenter();
      savedView.current = { center: [centre.lng, centre.lat], zoom: m.getZoom() };
      ready.current = false;
      map.current = null;
      m.remove();
    };
    // The map is created once, when it shows; later changes go through the effects below
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible]);

  useEffect(() => {
    if (map.current && ready.current) showGeometry(map.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [geometry, farmOrder.join("|"), markerMode, showProbes]);

  // The place names follow the language of the interface
  useEffect(() => {
    if (map.current && ready.current) localizeLabels(map.current, lang);
  }, [lang]);

  // Framing asked for (a farm chosen above the map or in the list)
  useEffect(() => {
    if (frame && map.current && ready.current) frameTarget(map.current, frame.target, true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [frame?.key]);

  useEffect(() => {
    if (map.current && ready.current) showOverlay(map.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [overlay]);

  useEffect(() => {
    if (map.current && ready.current) showExtras(map.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [marker, selected, points, polygons, cells, litFarm]);

  useEffect(() => {
    if (map.current) map.current.getCanvas().style.cursor = picking ? "crosshair" : "";
  }, [picking]);

  useEffect(() => {
    if (!note.current) return;
    note.current.hidden = basemap === "online";
    note.current.textContent = basemap === "online" ? "" : t(basemap);
  }, [basemap, t, visible]);

  return (
    <div ref={container} className="ows-map" style={{ height }} data-picking={picking || undefined} data-lasso={lassoing || undefined} role="region" aria-label={ariaLabel}>
      {tools && createPortal(
        <ToolBar label={t("tools")}>
          {(extraTools || onLasso) && <ToolGroup>{extraTools}{onLasso && <ToolToggle icon={IconLasso} label={t("lasso")} hint={t("lassoHint")} active={lassoing} onChange={setLassoing} />}</ToolGroup>}
          <ToolGroup>
            <ToolToggle icon={IconRuler2} label={t("measure")} hint={t("measureHint")} active={measuring} onChange={(on) => (on ? setMeasuring(true) : stopMeasure())} />
          </ToolGroup>
          <ToolChoice label={t("base")} value={base} onChange={setBase} options={[
            { value: "auto", icon: IconSunMoon, label: t("baseAuto") },
            { value: "real", icon: IconWorld, label: t("baseReal") },
          ]} />
        </ToolBar>,
        tools,
      )}
    </div>
  );
}
