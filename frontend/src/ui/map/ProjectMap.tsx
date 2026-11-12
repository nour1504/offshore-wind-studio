/**
 * The map of a project: domains, farms (disabled ones hollow), tslist points, an optional result
 * field and clickable points. Base map and relief come from public servers; offline, the copy kept
 * on disk (api/routes_map.py) or a plain background, with a note.
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
  type MapSourceDataEvent,
  NavigationControl,
  ScaleControl,
  setWorkerUrl,
  Popup,
} from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?url";
import manropeFile from "../../assets/fonts/manrope-variable.ttf?url";
import { IconLasso, IconRuler2, IconSunMoon, IconWorld } from "@tabler/icons-react";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import type { FeatureCollection, GeoFeature } from "../../api/types";
import { defineMessages, useLang, useT } from "../../i18n";
import { easeOutMap, prefersReducedMotion } from "../../motion";
import { collection, farmDisplay, markerImage, SYMBOL_PATHS } from "./farms";
import { ToolBar, ToolChoice, ToolGroup, ToolToggle } from "../ToolBar";

/** Camera moves glide with the application's landing curve, or jump when animations are reduced. */
/** A ring that spreads from a point of the map and fades: a turbine placed or clicked. */
function ripple(m: MapLibreMap, lng: number, lat: number) {
  if (prefersReducedMotion()) return;
  // MapLibre places the marker with a transform: the ring scales inside it
  const host = document.createElement("span");
  const ring = document.createElement("span");
  ring.className = "ows-map-ripple";
  host.append(ring);
  const marker = new Marker({ element: host }).setLngLat([lng, lat]).addTo(m);
  window.setTimeout(() => marker.remove(), 760);
}

/** A wave over features through their feature state (ids promoted from "uid"): the state of each
    one follows `write` from 0 to 1 after its own delay, and is removed at the end. Returns a stop. */
type WaveItem = { id: number; delay: number; amp: number };
function featureWave(m: MapLibreMap, source: string, items: WaveItem[], span: number, write: (k: number, amp: number) => Record<string, number>, alive: () => boolean): () => void {
  const end = items.reduce((last, item) => Math.max(last, item.delay), 0) + span;
  const reached = new Float64Array(items.length);
  const keys = Object.keys(write(0, 1));
  // Timed from the first frame drawn: a page busy with the click does not eat the start of the wave
  let start = -1;
  const set = (id: number, state: Record<string, number>) => { try { m.setFeatureState({ source, id }, state); } catch { /* style being replaced */ } };
  let frame = 0, over = false;
  const stop = () => {
    if (over) return;
    over = true;
    cancelAnimationFrame(frame);
    window.clearTimeout(safety);
    if (alive()) for (const item of items) for (const key of keys) try { m.removeFeatureState({ source, id: item.id }, key); } catch { /* idem */ }
  };
  const step = (now: number) => {
    if (!alive()) return stop();
    if (start < 0) start = now;
    const t = now - start;
    items.forEach((item, n) => {
      const k = Math.min(1, Math.max(0, (t - item.delay) / span));
      if (k !== reached[n]) { reached[n] = k; set(item.id, write(k, item.amp)); }
    });
    if (t < end) frame = requestAnimationFrame(step);
    else stop();
  };
  for (const item of items) set(item.id, write(0, item.amp));
  frame = requestAnimationFrame(step);
  // A hidden window draws no frame: the states are cleared all the same
  const safety = window.setTimeout(stop, end + 1500);
  return stop;
}

const turbineKey = (feature: GeoFeature) => {
  const [lng, lat] = (feature.geometry as { coordinates: [number, number] }).coordinates;
  return `t:${feature.properties.farm}:${feature.properties.number}@${lng.toFixed(5)},${lat.toFixed(5)}`;
};

/** How far a feature has come in (feature state "in", set by a wave): 1 outside waves */
const COMING: ExpressionSpecification = ["coalesce", ["feature-state", "in"], 1];

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
    hub: "hub", rotor: "rotor", lasso: "Lasso", lassoHint: "Draw around · Ctrl: add · Esc: stop",
    measure: "Measure", measureHint: "Click point after point · Esc to end",
    base: "Base map", baseAuto: "Theme base map", baseReal: "Color base map",
  },
  fr: {
    kept: "Fond de carte hors ligne", none: "Fond de carte indisponible", tools: "Outils de la carte",
    hub: "moyeu", rotor: "rotor", lasso: "Lasso", lassoHint: "Entourer · Ctrl : ajouter · Échap : arrêter",
    measure: "Mesurer", measureHint: "Cliquer point après point · Échap pour finir",
    base: "Fond de carte", baseAuto: "Fond du thème", baseReal: "Fond en couleurs",
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
// --ows-danger of the light theme: the map keeps its light colours in both themes
const MIXED_CELL = "#c6382e";
// A cell mixing turbine types is refused (core/case/checks.py): red, whatever the theme
const MIXED: ExpressionSpecification = ["==", ["get", "mixed"], true];

// The project's labels in the application's typeface, drawn from the bundled file (online or not)
const LABEL_FONT = ["Manrope Regular"];
const LABEL_FACES = { "Manrope Regular": [{ url: new URL(manropeFile, window.location.href).href }] };

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
const DOMAIN_COLOR: ExpressionSpecification = [
  "match", ["get", "number"], 1, DOMAIN_COLORS[0], 2, DOMAIN_COLORS[1], 3, DOMAIN_COLORS[2], 4, DOMAIN_COLORS[3], DOMAIN_COLORS[4],
];

/** The colours of the maps in the theme shown (styles.css, --ows-map-*), read when it changes; on
    the coloured base map the marks keep dark greens, read on land and sea alike. */
function mapTokens(natural = false) {
  const tokens = getComputedStyle(document.documentElement);
  const read = (name: string) => tokens.getPropertyValue(`--ows-map-${name}`).trim() || "#888888";
  const mark = (name: string) => read(natural ? `natural-${name}` : name);
  return {
    water: read("water"), land: read("land"), line: read("line"), text: read("text"), halo: read("halo"), accent: mark("accent"),
    mark: mark("mark"), ink: mark("ink"), relief: [0, 1, 2, 3].map((k) => read(`relief-${k}`)), deep: read("deep"), shelf: read("shelf"), shade: read("shade"),
    ripple: read("ripple"), domain: tokens.getPropertyValue("--ows-map-domain").trim(),
  };
}

/** Restyle only geography and UI markers. Scientific raster fields are never filtered or recoloured. */
type MapBase = "auto" | "real";
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
  const theme = mapTokens(real);
  const water = real ? WATER_COLOR : theme.water;
  const land = real ? "#e4eed6" : theme.land;
  const text = real ? "#33402f" : theme.text;
  const halo = real ? "#ffffff" : theme.halo;
  const accent = theme.accent;
  for (const layer of m.getStyle().layers) {
    // Project layers have no source-layer; leave their data and result rasters alone.
    const source = (layer as { "source-layer"?: string })["source-layer"];
    if (layer.type === "background") m.setPaintProperty(layer.id, "background-color", water);
    else if (source && layer.type === "fill") m.setPaintProperty(layer.id, "fill-color", /water/.test(source) ? water : land);
    else if (source && layer.type === "line") m.setPaintProperty(layer.id, "line-color", real ? (/water/.test(source) ? "#7fb1d8" : "#c7bfa8") : theme.line);
    else if (source && layer.type === "symbol") {
      m.setPaintProperty(layer.id, "text-color", text);
      m.setPaintProperty(layer.id, "text-halo-color", halo);
    }
  }
  if (m.getLayer("relief-land")) m.setPaintProperty("relief-land", "color-relief-color", real ? LAND_COLORS : [
    "interpolate", ["linear"], ["elevation"], -0.5, "rgba(0,0,0,0)",
    0, theme.relief[0], 500, theme.relief[1], 2000, theme.relief[2], 3500, theme.relief[3],
  ]);
  if (m.getLayer("relief-depth")) m.setPaintProperty("relief-depth", "color-relief-color", real ? DEPTH_COLORS : [
    "interpolate", ["linear"], ["elevation"], -6000, theme.deep,
    -500, theme.shelf, 0, "rgba(0,0,0,0)",
  ]);
  if (m.getLayer("measure-line")) {
    m.setPaintProperty("measure-line", "line-color", accent);
    m.setPaintProperty("measure-point", "circle-stroke-color", accent);
    m.setPaintProperty("measure-point", "circle-color", halo);
  }
  if (m.getLayer("relief-shade")) {
    m.setPaintProperty("relief-shade", "hillshade-shadow-color", real ? "#1d2b22" : theme.shade);
    // In colours: the shading of the relief stands out
    m.setPaintProperty("relief-shade", "hillshade-exaggeration", real ? 0.6 : 0.3);
  }
  if (m.getLayer("relief-land")) m.setPaintProperty("relief-land", "color-relief-opacity", real ? 0.9 : 0.5);
  // Domains: a colour each, dark greens then greys, read on the sea and on the land alike; on the
  // dark map, all in its mark (--ows-map-domain) with their names in the text colour
  const single = real ? "" : theme.domain;
  const domainColor = single || DOMAIN_COLOR;
  for (const [id, property] of [["domain-fill", "fill-color"], ["domain-line", "line-color"]] as const) {
    if (m.getLayer(id)) m.setPaintProperty(id, property, domainColor);
  }
  if (m.getLayer("domain-label")) {
    m.setPaintProperty("domain-label", "text-color", single ? text : domainColor);
    m.setPaintProperty("domain-label", "text-halo-color", halo);
  }
  if (m.getLayer("domain-casing")) m.setPaintProperty("domain-casing", "line-color", halo);
  for (const id of ["marker", "points", "probes"]) {
    if (m.getLayer(id)) m.setPaintProperty(id, "circle-color", accent);
  }
  if (m.getLayer("selected")) m.setPaintProperty("selected", "circle-color", theme.mark);
  // The glow under the turbines in the green of the theme
  for (const id of ["turbine-glow", "turbine-wave"]) {
    if (m.getLayer(id)) m.setPaintProperty(id, "circle-color", theme.ripple);
  }
  // The grid of the farm domain in the accent of the theme, a cell mixing turbine types in red
  for (const [id, property] of [["cell-line", "line-color"], ["cell-fill", "fill-color"], ["cell-edge", "line-color"], ["cell-count", "text-color"]] as const) {
    if (!m.getLayer(id)) continue;
    const colour = id === "cell-count" ? theme.ink : accent;
    m.setPaintProperty(id, property, id === "cell-fill" || id === "cell-edge" ? ["case", MIXED, MIXED_CELL, colour] : colour);
  }
  // What is being selected (cells lit, lasso, polygons): filled with the mark, outlined in the accent
  for (const [id, property] of [["cell-lit", "fill-color"], ["lasso-fill", "fill-color"], ["polygon-fill", "fill-color"], ["lasso-line", "line-color"], ["polygon-line", "line-color"]] as const) {
    if (m.getLayer(id)) m.setPaintProperty(id, property, property === "fill-color" ? theme.mark : accent);
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

interface MapOverlay {
  url: string;
  coordinates: [number, number][];
  opacity: number;
}

interface MapPoint {
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
  /** Choices of the page in the top left of the map (what to frame...), the icon bar being in the
      top right, over the zoom */
  lead?: ReactNode;
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
  /** What to frame: "all" turbines, "farm:<id>", "domain" (the outer domain), "domain:<n>" or
      "point:<lat>,<lon>". A new key frames again, even the same target (the map may have been
      moved since). */
  frame?: { target: string; key: number };
}

const empty: FeatureCollection = { type: "FeatureCollection", features: [] };

function split(geometry: FeatureCollection) {
  return {
    domains: collection(geometry.features.filter((f) => f.properties.kind === "domain")),
    turbines: collection(geometry.features.filter((f) => f.properties.kind === "turbine")),
    probes: collection(geometry.features.filter((f) => f.properties.kind === "probe")),
  };
}

/** The name and grid spacing of each domain, at its corner, with the decimal mark of the language
 * ("d02 · 1,5 km", "d04 · 333 m"). */
function domainLabels(geometry: FeatureCollection, lang: string): FeatureCollection {
  const km = new Intl.NumberFormat(lang, { maximumFractionDigits: 2 });
  const metres = new Intl.NumberFormat(lang, { maximumFractionDigits: 0 });
  const labels: GeoFeature[] = geometry.features.filter((f) => f.properties.kind === "domain").map((d) => {
    const ring = (d.geometry as { coordinates: [number, number][][] }).coordinates[0];
    const dx = d.properties.dx ?? 0;
    return {
      type: "Feature",
      geometry: { type: "Point", coordinates: ring[3 * POINTS_PER_EDGE] ?? ring[0] },
      properties: {
        kind: "domain",
        number: d.properties.number,
        label: `d${String(d.properties.number).padStart(2, "0")} · ${dx >= 1000 ? `${km.format(dx / 1000)} km` : `${metres.format(dx)} m`}`,
      },
    };
  });
  return collection(labels);
}

function pointCollection(points: MapPoint[], ids?: number[]): FeatureCollection {
  return collection(
    points.map((p, n) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [p.lon, p.lat] },
      properties: { kind: "probe", label: p.label, ...(ids ? { uid: ids[n] } : {}) },
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
  lead,
  onLasso,
}: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<MapLibreMap | null>(null);
  const fitted = useRef(false);
  const ready = useRef(false);
  // The result picture: two layers taking turns, the next one fading in as the one shown fades out
  const overlayFront = useRef<"result" | "result-b">("result");
  const overlayUrl = useRef<string | null>(null);
  const overlayTurn = useRef(0);
  const savedView = useRef<{ center: [number, number]; zoom: number } | null>(null);
  const farmMarkers = useRef(new Map<string, Marker>());
  const iconColors = useRef(new Map<string, string>());
  const displayedFarms = useRef<{ geometry: FeatureCollection; key: string } | null>(null);
  // Waves over the turbines and the extra points: one id per turbine and per point, kept
  const featureIds = useRef(new Map<string, number>());
  const lastId = useRef(0);
  const turbineKeys = useRef<{ geometry: FeatureCollection; keys: Set<string> } | null>(null);
  const pointKeys = useRef<string[] | null>(null);
  const shownTurbines = useRef<{ id: number; key: string; lng: number; lat: number }[]>([]);
  const running = useRef(new Map<string, () => void>());
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

  /** Frames a target ("all" turbines, "farm:<id>", "domain" for the outer domain, "domain:<n>" or
      one point), close enough to see each turbine but with their surroundings; false when there
      is nothing to frame. */
  const frameTarget = (m: MapLibreMap, target: string, animate: boolean): boolean => {
    if (target.startsWith("point:")) {
      const [lat, lon] = target.slice(6).split(",").map(Number);
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) return false;
      m.easeTo({ center: [lon, lat], zoom: Math.max(m.getZoom(), 13), ...glideTo(animate) });
      return true;
    }
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
    (m.getSource("labels") as GeoJSONSource).setData(domainLabels(data, langRef.current));
    (m.getSource("probes") as GeoJSONSource).setData(parts.probes);
    m.setLayoutProperty("probes", "visibility", props.current.showProbes ? "visible" : "none");
    m.setLayoutProperty("probe-labels", "visibility", props.current.showProbes && !props.current.points?.some((p) => p.label) ? "visible" : "none");
    showFarms(m);
    if (fitted.current) return;
    const first = props.current.frame?.target ?? (props.current.fit === "turbines" ? "all" : null);
    if (first && frameTarget(m, first, false)) fitted.current = true;
    else if (frameDomain(m, parts.domains, false)) fitted.current = true;
  };

  const idFor = (key: string) => {
    let id = featureIds.current.get(key);
    if (id === undefined) { id = ++lastId.current; featureIds.current.set(key, id); }
    return id;
  };
  /** One wave at a time over a source: a new one ends the one running */
  const wave = (m: MapLibreMap, source: string, items: WaveItem[], span: number, write: (k: number, amp: number) => Record<string, number>) => {
    running.current.get(source)?.();
    if (!items.length || prefersReducedMotion()) return;
    running.current.set(source, featureWave(m, source, items, span, write, () => ready.current && map.current === m));
  };
  /** Things added come in by a wave from a point, the nearest first */
  const comeIn = (m: MapLibreMap, source: string, items: { id: number; lng: number; lat: number }[], from: { x: number; y: number } | null, write: (k: number) => Record<string, number>) => {
    if (!items.length) return;
    const at = items.map((item) => m.project([item.lng, item.lat]));
    const o = from ?? { x: at.reduce((sum, p) => sum + p.x, 0) / at.length, y: at.reduce((sum, p) => sum + p.y, 0) / at.length };
    const r = at.map((p) => Math.hypot(p.x - o.x, p.y - o.y));
    const near = Math.min(...r);
    wave(m, source, items.map((item, n) => ({ id: item.id, delay: Math.min(480, (r[n] - near) * 1.3), amp: 1 })), 380, write);
  };
  /** From a turbine clicked, a wave of light runs through its neighbours */
  const spread = (m: MapLibreMap, lng: number, lat: number) => {
    const o = m.project([lng, lat]);
    const reach = 300;
    wave(m, "turbines", shownTurbines.current.flatMap((turbine) => {
      const p = m.project([turbine.lng, turbine.lat]);
      const r = Math.hypot(p.x - o.x, p.y - o.y);
      return r > reach ? [] : [{ id: turbine.id, delay: r * 1.4, amp: 0.3 + 0.7 * (1 - r / reach) }];
    }), 420, (k, amp) => ({ w: Math.sin(Math.PI * k) * amp }));
  };
  /** Turbines of the farms that were not there before (none the first time: the map sweeps in) */
  const arrivals = (data: FeatureCollection): Set<string> => {
    const known = turbineKeys.current;
    if (known?.geometry === data) return new Set();
    const keys = new Set(data.features.filter((feature) => feature.properties.kind === "turbine").map(turbineKey));
    turbineKeys.current = { geometry: data, keys };
    return known ? new Set([...keys].filter((key) => !known.keys.has(key))) : new Set();
  };

  const showFarms = (m: MapLibreMap) => {
    const data = props.current.geometry;
    if (!data) return;
    const dots = props.current.farms === "dots";
    const fresh = arrivals(data);
    m.setLayoutProperty("turbines", "visibility", dots ? "none" : "visible");
    m.setLayoutProperty("turbine-wave", "visibility", dots ? "none" : "visible");
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
    const halo = mapTokens().halo;
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
        return { ...feature, properties: { ...feature.properties, icon, uid: idFor(turbineKey(feature)) } };
      });
      (m.getSource("turbines") as GeoJSONSource).setData(collection(features));
      displayedFarms.current = { geometry: data, key };
      shownTurbines.current = features.map((feature) => {
        const [lng, lat] = (feature.geometry as { coordinates: [number, number] }).coordinates;
        return { id: feature.properties.uid, key: turbineKey(feature), lng, lat };
      });
      if (featureIds.current.size > 2 * features.length + 500) {
        const kept = new Set(shownTurbines.current.map((turbine) => turbine.key));
        for (const key of featureIds.current.keys()) if (key.startsWith("t:") && !kept.has(key)) featureIds.current.delete(key);
      }
      // Turbines added to the farms come in by a wave from their middle, a light passing under them
      if (fresh.size) comeIn(m, "turbines", shownTurbines.current.filter((turbine) => fresh.has(turbine.key)), null, (k) => ({ in: 1 - (1 - k) ** 3, w: Math.sin(Math.PI * k) * 0.9 }));
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
    if (!value) {
      for (const id of ["result", "result-b"]) {
        if (m.getLayer(id)) m.removeLayer(id);
        if (m.getSource(id)) m.removeSource(id);
      }
      overlayUrl.current = null;
      return;
    }
    const coordinates = value.coordinates as Coordinates;
    const add = (id: string, opacity: number) => {
      m.addSource(id, { type: "image", url: value.url, coordinates });
      // One pixel per grid cell: nearest resampling shows the model's actual cells
      m.addLayer(
        { id, type: "raster", source: id, paint: { "raster-opacity": opacity, "raster-opacity-transition": { duration: 280, delay: 0 }, "raster-resampling": "nearest" } },
        "domain-fill",
      );
    };
    // After a change of base map the layers are gone: start again with one
    if (!m.getSource(overlayFront.current)) overlayFront.current = m.getSource("result-b") ? "result-b" : "result";
    const front = overlayFront.current;
    const shown = m.getSource(front) as ImageSource | undefined;
    if (!shown) {
      add(front, value.opacity);
      overlayUrl.current = value.url;
      return;
    }
    if (overlayUrl.current === value.url) {
      m.setPaintProperty(front, "raster-opacity", value.opacity);
      return;
    }
    overlayUrl.current = value.url;
    if (prefersReducedMotion()) {
      shown.updateImage({ url: value.url, coordinates });
      m.setPaintProperty(front, "raster-opacity", value.opacity);
      return;
    }
    // The next picture loads in the other layer, then the two cross-fade (only the latest one)
    const back = front === "result" ? "result-b" : "result";
    const turn = ++overlayTurn.current;
    const loaded = (event: MapSourceDataEvent) => {
      if (event.sourceId !== back || !event.isSourceLoaded) return;
      m.off("sourcedata", loaded);
      if (turn !== overlayTurn.current || !m.getLayer(back)) return;
      m.setPaintProperty(back, "raster-opacity", value.opacity);
      if (m.getLayer(front)) m.setPaintProperty(front, "raster-opacity", 0);
      overlayFront.current = back;
    };
    m.on("sourcedata", loaded);
    const next = m.getSource(back) as ImageSource | undefined;
    if (next) next.updateImage({ url: value.url, coordinates });
    else add(back, 0);
  };

  const showExtras = (m: MapLibreMap) => {
    const { marker: mark, points: extra, polygons: zones, cells: grid, cellSize: size } = props.current;
    (m.getSource("cells") as GeoJSONSource).setData(grid ?? empty);
    if (grid && size) showGrid(m, grid, size);
    // The cells of the farm just chosen light up, fading in (a mixed cell stays red)
    const lit = props.current.litFarm;
    m.setFilter("cell-lit", ["all", ["==", ["get", "kind"], "cell"], ["!", MIXED], ["in", `, ${lit ?? "\u0000"},`, ["concat", ", ", ["get", "farms"], ","]]]);
    m.setPaintProperty("cell-lit", "fill-opacity", 0);
    if (lit) requestAnimationFrame(() => { if (m.getLayer("cell-lit")) m.setPaintProperty("cell-lit", "fill-opacity", 0.38); });
    (m.getSource("marker") as GeoJSONSource).setData(mark ? pointCollection([mark]) : empty);
    const chosen = props.current.selected ?? [];
    (m.getSource("selected") as GeoJSONSource).setData(pointCollection(chosen));
    // While turbines are selected, the others step back
    const keys = chosen.map((p) => `${p.farm}:${p.number}`);
    const others: ExpressionSpecification = ["!", ["in", ["concat", ["get", "farm"], ":", ["to-string", ["get", "number"]]], ["literal", keys]]];
    m.setPaintProperty("turbines", "icon-opacity", ["*", COMING, keys.length
      ? ["case", others, 0.22, ["==", ["get", "enabled"], false], 0.42, 1]
      : ["case", ["==", ["get", "enabled"], false], 0.42, 1]]);
    const listed = (extra ?? []).map((point) => `p:${point.lon.toFixed(6)},${point.lat.toFixed(6)}`);
    (m.getSource("points") as GeoJSONSource).setData(pointCollection(extra ?? [], listed.map(idFor)));
    (m.getSource("polygons") as GeoJSONSource).setData(zones ?? empty);
    m.setLayoutProperty("probe-labels", "visibility", props.current.showProbes && !extra?.some((point) => point.label) ? "visible" : "none");
    showFarms(m);
    if (props.current.fitPoints && extra?.length) {
      const bounds = new LngLatBounds();
      extra.forEach((point) => bounds.extend([point.lon, point.lat]));
      m.fitBounds(bounds, { padding: 50, maxZoom: 12, duration: 0 });
      fitted.current = true;
    }
    // Points added (one placed, a list pasted, a new layout) come in by a wave from the middle of the map
    const before = pointKeys.current;
    pointKeys.current = listed;
    if (before && before.length !== listed.length) {
      const known = new Set(before);
      const centre = m.project(m.getCenter());
      comeIn(m, "points", (extra ?? []).flatMap((point, n) => (known.has(listed[n]) ? [] : [{ id: idFor(listed[n]), lng: point.lon, lat: point.lat }])), centre, (k) => ({ in: k }));
    }
  };

  const addLayers = (m: MapLibreMap) => {
    for (const id of ["domains", "labels", "turbines", "turbine-glow", "probes", "marker", "selected", "points", "polygons", "cells", "measure", "lasso"]) {
      if (!m.getSource(id)) m.addSource(id, { type: "geojson", data: empty, ...(id === "turbines" || id === "points" ? { promoteId: "uid" } : {}) });
    }
    m.addLayer({ id: "domain-fill", type: "fill", source: "domains", paint: { "fill-color": DOMAIN_COLOR, "fill-opacity": 0.05 } });
    m.addLayer({ id: "domain-casing", type: "line", source: "domains", paint: { "line-color": "#ffffff", "line-width": 5, "line-opacity": 0.7 } });
    m.addLayer({ id: "domain-line", type: "line", source: "domains", paint: { "line-color": DOMAIN_COLOR, "line-width": 2.5 } });
    m.addLayer({
      id: "domain-label",
      type: "symbol",
      source: "labels",
      layout: { "text-font": LABEL_FONT, "text-field": ["get", "label"], "text-size": 12, "text-anchor": "top-left", "text-offset": [0.4, 0.4] },
      paint: { "text-color": DOMAIN_COLOR, "text-halo-color": "#fff", "text-halo-width": 1.5 },
    });
    // The grid of the farm domain (one source): fine lines thinned out when zoomed out, the cells
    // holding turbines filled by their number, the number written once a cell is large enough
    m.addLayer({ id: "cell-line", type: "line", source: "cells", filter: ["==", ["get", "kind"], "line"], paint: { "line-color": "#1f7f48", "line-width": 0.6, "line-opacity": 0.3 } });
    // A cell mixing turbine types is refused: red, whatever its number (styleMapTheme keeps it)
    m.addLayer({ id: "cell-fill", type: "fill", source: "cells", filter: ["==", ["get", "kind"], "cell"], paint: {
      "fill-color": ["case", MIXED, MIXED_CELL, "#1f7f48"],
      "fill-opacity": ["case", MIXED, 0.45, ["interpolate", ["linear"], ["get", "count"], 1, 0.08, 4, 0.14, 12, 0.22, 40, 0.32]],
    } });
    m.addLayer({ id: "cell-edge", type: "line", source: "cells", filter: ["==", ["get", "kind"], "cell"], paint: { "line-color": ["case", MIXED, MIXED_CELL, "#1f7f48"], "line-width": ["case", MIXED, 2, 1], "line-opacity": ["case", MIXED, 1, 0.55] } });
    m.addLayer({ id: "cell-lit", type: "fill", source: "cells", filter: ["==", ["get", "kind"], "none"], paint: { "fill-color": "#3aad66", "fill-opacity": 0, "fill-opacity-transition": { duration: 450, delay: 0 } } });
    m.addLayer({
      id: "cell-count",
      type: "symbol",
      source: "cells",
      minzoom: 10,
      filter: ["==", ["get", "kind"], "cell"],
      layout: { "text-font": LABEL_FONT, "text-field": ["to-string", ["get", "count"]], "text-size": 12, "text-allow-overlap": false },
      paint: { "text-color": "#0e4d2c", "text-opacity": 0.85 },
    });
    // The distance being measured: a dashed line and its points
    m.addLayer({ id: "measure-line", type: "line", source: "measure", filter: ["==", ["geometry-type"], "LineString"], paint: { "line-color": "#176743", "line-width": 2, "line-dasharray": [3, 2] } });
    m.addLayer({ id: "measure-point", type: "circle", source: "measure", filter: ["==", ["geometry-type"], "Point"], paint: { "circle-radius": 4, "circle-color": "#fff", "circle-stroke-color": "#176743", "circle-stroke-width": 2 } });
    m.addLayer({ id: "lasso-fill", type: "fill", source: "lasso", paint: { "fill-color": "#3aad66", "fill-opacity": 0.12 } });
    m.addLayer({ id: "lasso-line", type: "line", source: "lasso", paint: { "line-color": "#176743", "line-width": 1.5, "line-dasharray": [2, 2] } });
    m.addLayer({ id: "polygon-fill", type: "fill", source: "polygons", paint: { "fill-color": "#3aad66", "fill-opacity": 0.14 } });
    m.addLayer({ id: "polygon-line", type: "line", source: "polygons", paint: { "line-color": "#1f7f48", "line-width": 1.5, "line-dasharray": [2, 1] } });
    // Under the turbine pointed at, a green glow, softer on its neighbours
    m.addLayer({ id: "turbine-glow", type: "circle", source: "turbine-glow", paint: {
      "circle-radius": ["*", ["get", "w"], ["interpolate", ["linear"], ["zoom"], 8, 9, 14, 18]],
      "circle-color": "#46d483",
      "circle-opacity": ["*", ["get", "w"], 0.55],
      "circle-blur": 0.7,
    } });
    // The wave of light under the turbines: from the one clicked, or under those coming in
    m.addLayer({ id: "turbine-wave", type: "circle", source: "turbines", paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 8, 10, 14, 20],
      "circle-color": "#46d483",
      "circle-opacity": ["*", 0.5, ["coalesce", ["feature-state", "w"], 0]],
      "circle-blur": 0.75,
    } });
    m.addLayer({ id: "turbines", type: "symbol", source: "turbines", layout: {
      "icon-image": ["get", "icon"], "icon-size": ["interpolate", ["linear"], ["zoom"], 5, 0.34, 12, 0.5, 16, 0.65],
      "icon-allow-overlap": true, "icon-ignore-placement": true,
    }, paint: { "icon-opacity": ["*", COMING, ["case", ["==", ["get", "enabled"], false], 0.42, 1]] } });
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
      layout: { "text-font": LABEL_FONT, "text-field": ["get", "label"], "text-size": 12, "text-anchor": "left", "text-offset": [0.7, 0] },
      paint: { "text-color": "#343a40", "text-halo-color": "#fff", "text-halo-width": 1.2, "text-opacity": COMING },
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
      layout: { "text-font": LABEL_FONT, "text-field": ["coalesce", ["get", "prefix"], ["get", "label"]], "text-size": 12, "text-anchor": "left", "text-offset": [0.8, 0] },
      paint: { "text-color": "#0e4d2c", "text-halo-color": "#fff", "text-halo-width": 1.5 },
    });
    m.addLayer({
      id: "points",
      type: "circle",
      source: "points",
      // Coming in, a point swells a little past its size before settling
      paint: {
        "circle-radius": ["*", 3.5, ["interpolate", ["linear"], COMING, 0, 0, 0.6, 1.35, 1, 1]],
        "circle-opacity": ["interpolate", ["linear"], COMING, 0, 0, 0.3, 1],
        "circle-stroke-opacity": ["interpolate", ["linear"], COMING, 0, 0, 0.3, 1],
        "circle-color": "#7ac996", "circle-stroke-color": "#0e4d2c", "circle-stroke-width": 1,
      },
    });
    m.addLayer({
      id: "point-labels",
      type: "symbol",
      source: "points",
      filter: ["has", "label"],
      layout: { "text-font": LABEL_FONT, "text-field": ["get", "label"], "text-size": 12, "text-anchor": "left", "text-offset": [0.9, 0], "text-optional": true },
      paint: { "text-color": "#193126", "text-halo-color": "#ffffff", "text-halo-width": 1.4, "text-opacity": ["interpolate", ["linear"], COMING, 0.4, 0, 1, 1] },
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
  const [leadBox, setLeadBox] = useState<HTMLDivElement | null>(null);
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
    let swept = false;
    // Map load times, exposed on window.__owsMapTimings for performance checks
    let styled = 0;
    m.once("idle", () => {
      const timings = window as unknown as { __owsMapTimings?: object[] };
      timings.__owsMapTimings = [...(timings.__owsMapTimings ?? []), { page: location.hash, style_ms: Math.round(styled - started), idle_ms: Math.round(performance.now() - started) }];
    });
    // The icon bar in the top right, the zoom under it; the page's choices in the top left
    const toolsElement = document.createElement("div");
    toolsElement.className = "maplibregl-ctrl ows-map-tools";
    m.addControl({ onAdd: () => toolsElement, onRemove: () => toolsElement.remove() }, "top-right");
    setTools(toolsElement);
    m.addControl(new NavigationControl({ showCompass: false }), "top-right");
    m.addControl(new ScaleControl({ unit: "metric" }), "bottom-left");
    const leadElement = document.createElement("div");
    leadElement.className = "maplibregl-ctrl ows-map-lead";
    m.addControl({ onAdd: () => leadElement, onRemove: () => leadElement.remove() }, "top-left");
    setLeadBox(leadElement);
    const noteElement = document.createElement("div");
    noteElement.className = "maplibregl-ctrl ows-map-note";
    noteElement.hidden = true;
    note.current = noteElement;
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
      m.setFontFaces(LABEL_FACES);
      addLayers(m);
      styleMapTheme(m, baseRef.current);
      // The first time only: the map is revealed by a light band sweeping across it
      const box = container.current;
      if (!swept && box && !prefersReducedMotion()) {
        swept = true;
        box.setAttribute("data-reveal", "");
        window.setTimeout(() => box.removeAttribute("data-reveal"), 1000);
      }
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
      if (p.picking) {
        p.onPick?.(e.lngLat.lat, e.lngLat.lng);
        ripple(m, e.lngLat.lng, e.lngLat.lat);
      }
      // A click on a turbine is its own (handled below), not a click on the map
      else if (!(p.onTurbineClick && m.getLayer("turbines") && m.queryRenderedFeatures(e.point, { layers: ["turbines"] }).length)) p.onMapClick?.(e.lngLat.lat, e.lngLat.lng);
    });
    m.on("click", "turbines", (e: MapLayerMouseEvent) => {
      const p = props.current;
      const feature = e.features?.[0];
      if (!p.picking && feature) {
        p.onTurbineClick?.(feature.properties as GeoFeature["properties"], e.originalEvent.ctrlKey || e.originalEvent.shiftKey || e.originalEvent.metaKey);
        const [lng, lat] = (feature.geometry as { coordinates: [number, number] }).coordinates;
        ripple(m, lng, lat);
        spread(m, lng, lat);
      }
    });
    // The glow follows the pointer from turbine to turbine (once an image)
    let glowAt = 0;
    const glow = (point: { x: number; y: number } | null) => {
      cancelAnimationFrame(glowAt);
      glowAt = requestAnimationFrame(() => {
        const source = m.getSource("turbine-glow") as GeoJSONSource | undefined;
        if (!source) return;
        if (!point || props.current.picking) return source.setData(empty);
        const reach = 46;
        const near = m.queryRenderedFeatures([[point.x - reach, point.y - reach], [point.x + reach, point.y + reach]], { layers: ["turbines"] });
        const features = near.map((feature) => {
          const [lng, lat] = (feature.geometry as { coordinates: [number, number] }).coordinates;
          const at = m.project([lng, lat]);
          return { d: Math.hypot(at.x - point.x, at.y - point.y), lng, lat };
        }).filter((n) => n.d <= reach).sort((a, b) => a.d - b.d).slice(0, 14);
        source.setData({
          type: "FeatureCollection",
          features: features.map((n, k) => ({ type: "Feature", properties: { w: k === 0 ? 1 : Math.max(0.15, 0.6 * (1 - n.d / reach)) }, geometry: { type: "Point", coordinates: [n.lng, n.lat] } })),
        });
      });
    };
    m.on("mousemove", "turbines", (e: MapLayerMouseEvent) => glow(e.point));
    m.on("mouseleave", "turbines", () => glow(null));
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
      running.current.forEach((stop) => stop()); running.current.clear();
      turbineKeys.current = null; pointKeys.current = null; shownTurbines.current = [];
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

  // The place names follow the language of the interface, and so do the numbers of the domain labels
  useEffect(() => {
    if (!map.current || !ready.current) return;
    localizeLabels(map.current, lang);
    const data = props.current.geometry;
    if (data) (map.current.getSource("labels") as GeoJSONSource).setData(domainLabels(data, lang));
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
      {leadBox && lead && createPortal(lead, leadBox)}
    </div>
  );
}
