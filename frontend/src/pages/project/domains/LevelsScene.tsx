/**
 * 3D view of the vertical levels over a domain, in a gridded box on a dark background: a smooth
 * shaded terrain (the finest source the server found), a sea coloured by its depth, the model
 * levels as fine grids of lines and as bands on a curtain that moves across the domain, and
 * the turbines at their true height and rotor diameter.
 *
 * The levels are real.exe's, computed by the server over the model terrain (core/method/scene.py).
 * On the finer terrain drawn here, each level moves by B(eta) times the difference of ground (the
 * share of the terrain the hybrid coordinate gives it): the lowest ones follow the visible ground,
 * those above etac stay flat, and over the sea nothing moves. The vertical exaggeration is a GPU
 * scale: changing it rebuilds nothing.
 */
import { Box, Group, SegmentedControl, Select, Slider, Stack, Text, Tooltip } from "@mantine/core";
import { useDebouncedValue, useLocalStorage } from "@mantine/hooks";
import { type Icon, IconArrowAutofitHeight, IconChartArea, IconCylinder, IconGrid4x4, IconMountain, IconPropeller, IconRotate360, IconSquareOff, IconStack2, IconStack3, IconWindmill } from "@tabler/icons-react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";

import { post } from "../../../api/client";
import type { Case } from "../../../api/types";
import { defineMessages, useFormat, useT } from "../../../i18n";
import { Fold } from "../../../ui/Fold";
import { ToolBar, ToolChoice, ToolGroup, ToolToggle } from "../../../ui/ToolBar";
import { FieldLabel } from "../../../ui/Inputs";
import { PathInput } from "../../../ui/PathInput";
import { type Camera, MeshBuilder, type Mesh, mix, project, type Rgba, SceneRenderer } from "../../../ui/scene3d";
import { ErrorState, LoadingState } from "../../../ui/States";
import { levelHover } from "./levelHover";

type Source = "geo_em" | "wps_geog" | "tiles" | "flat";

interface SceneData {
  domain: number;
  source: Source;
  source_detail: string;
  problems: string[];
  nx: number;
  ny: number;
  xs_km: number[];
  ys_km: number[];
  terrain_m: string;
  display: { source: Source; factor: number; nx: number; ny: number; terrain_m: string };
  b_full: number[];
  levels: number;
  heights_m: string;
  sea_level_heights_m: number[];
  hybrid_opt: number;
  /** Every domain: its extent in the plane of the domain shown (km), its real cells and its parent */
  domains: { number: number; west: number; south: number; east: number; north: number; dx_km: number; cells_x: number; cells_y: number; parent: number }[];
  turbines: { x: number; y: number; farm: string; hub_m: number | null; rotor_m: number | null }[];
  farms: { id: string; name: string }[];
}

type Layer = "terrain" | "sheets" | "curtain" | "rotor" | "turbines" | "air";
type Cells = "none" | "ground" | "levels";
const LAYER_ICONS: Record<Layer, Icon> = { terrain: IconMountain, sheets: IconStack2, curtain: IconChartArea, rotor: IconPropeller, turbines: IconWindmill, air: IconCylinder };
const CELL_ICONS: Record<Cells, Icon> = { none: IconSquareOff, ground: IconGrid4x4, levels: IconStack3 };

const messages = defineMessages({
  en: {
    sources: "Terrain",
    used: { geo_em: "geo_em file", wps_geog: "WPS_GEOG", tiles: "Public elevation tiles", flat: "Flat" },
    relief: "geo_em file or geography folder",
    reliefInfo: "A parent folder is accepted, subfolders are searched.",
    reliefEmpty: "Empty: engine geography",
    usedPath: "Used:",
    reliefModes: { geography: "Geography", tiles: "Public tiles" },
    tilesInfo: "Terrain downloaded from the Internet, with bathymetry. Without Internet access, the geography is used.",
    domain: "Domain",
    orbit: "Turn around",
    layers: { terrain: "Terrain", sheets: "Levels", curtain: "Curtain", rotor: "Rotor layers", turbines: "Turbines", air: "Farm air" },
    hints: {
      terrain: "Model terrain and sea floor",
      sheets: "Outline of each level",
      curtain: "The layers on a vertical cut, from green near the sea to blue aloft",
      rotor: "Layers crossed by the blades, in orange on the curtain",
      turbines: "At their hub height and rotor diameter",
      air: "Over each farm, from the sea to the top of the blades",
    },
    tools: "Display",
    cells: "Grid cells",
    cellsModes: { none: "No grid cells", ground: "Grid cells on the ground", levels: "Grid cells on the levels" },
    cellsInfo: "Model cells: d{n} {dx} km{every}",
    every: " (one line in {k})",
    ceiling: "Up to",
    all: "Top",
    exaggeration: "Vertical exaggeration",
    curtain: "Curtain position",
    westEast: "W–E",
    farm: "Frame a farm",
    southNorth: "S–N",
  },
  fr: {
    sources: "Relief",
    used: { geo_em: "Fichier geo_em", wps_geog: "WPS_GEOG", tiles: "Tuiles d'altitude publiques", flat: "Plat" },
    relief: "Fichier geo_em ou dossier de géographie",
    reliefInfo: "Un dossier parent est accepté, les sous-dossiers sont parcourus.",
    reliefEmpty: "Vide : géographie du moteur",
    usedPath: "Utilisé :",
    reliefModes: { geography: "Géographie", tiles: "Tuiles publiques" },
    tilesInfo: "Relief téléchargé sur Internet, avec la bathymétrie. Sans accès Internet, la géographie est utilisée.",
    domain: "Domaine",
    orbit: "Tourner autour",
    layers: { terrain: "Relief", sheets: "Niveaux", curtain: "Rideau", rotor: "Couches des rotors", turbines: "Éoliennes", air: "Air des parcs" },
    hints: {
      terrain: "Relief du modèle et fond de la mer",
      sheets: "Contour de chaque niveau",
      curtain: "Position de la coupe verticale",
      rotor: "Couches traversées par les pales, en orange sur le rideau",
      turbines: "À leur hauteur de moyeu et leur diamètre de rotor",
      air: "Au-dessus de chaque parc, de la mer au haut des pales",
    },
    tools: "Affichage",
    cells: "Mailles",
    cellsModes: { none: "Sans mailles", ground: "Mailles au sol", levels: "Mailles sur les niveaux" },
    cellsInfo: "Mailles du modèle : d{n} {dx} km{every}",
    every: " (une ligne sur {k})",
    ceiling: "Jusqu'à",
    all: "Sommet",
    exaggeration: "Exagération verticale",
    curtain: "Position du rideau",
    westEast: "O–E",
    farm: "Cadrer un parc",
    southNorth: "S–N",
  },
});

// ------------------------------------------------------------------ colours (0 to 1)
const BACKGROUND: [number, number, number] = [0.071, 0.078, 0.086];
// Muted hypsometric tints: green lowlands, ochre hills, grey and light grey heights
const LAND: [number, Rgba][] = [
  [0, [0.4, 0.53, 0.39, 1]],
  [200, [0.53, 0.6, 0.43, 1]],
  [600, [0.69, 0.65, 0.47, 1]],
  [1200, [0.62, 0.55, 0.45, 1]],
  [2000, [0.73, 0.72, 0.69, 1]],
  [3200, [0.9, 0.9, 0.89, 1]],
];
// The sea darkens gently with depth
const SEA: [number, Rgba][] = [
  [0, [0.21, 0.37, 0.43, 1]],
  [-30, [0.16, 0.3, 0.37, 1]],
  [-150, [0.12, 0.23, 0.31, 1]],
  [-1000, [0.08, 0.16, 0.23, 1]],
];
const SEA_FLAT: Rgba = [0.15, 0.28, 0.35, 1];
const SKIRT: Rgba = [0.12, 0.135, 0.15, 1];
const COAST: Rgba = [0.86, 0.9, 0.88, 0.55];
const GRID: Rgba = [0.6, 0.66, 0.7, 0.16];
const EDGE: Rgba = [0.7, 0.76, 0.8, 0.42];
const WALL: Rgba = [0.6, 0.66, 0.7, 0.035];
// The level under the pointer in the profile of the levels
const LEVEL_LIT: Rgba = [0.36, 0.78, 0.55, 0.32];
const LEVEL_EDGE: Rgba = [0.55, 0.92, 0.7, 0.9];
// Each level is a fine grid of lines (no sheet veiling the relief from above), with its outline
// The real cells: those of the domain shown, and brighter those of the domains nested in it
const CELLS: Rgba = [0.86, 0.92, 0.9, 0.3];
const CELLS_NESTED: Rgba = [0.45, 0.88, 0.62, 0.6];
// Lines of cells drawn along a side at most: beyond, one line in `every`
const MOST_CELL_LINES = 120;
const SHEET_EDGE: Rgba = [0.7, 0.93, 0.82, 0.5];
const CURTAIN_LINE: Rgba = [0.92, 0.98, 0.95, 0.9];
const ROTOR_A: Rgba = [0.98, 0.72, 0.32, 0.62];
const ROTOR_B: Rgba = [0.99, 0.84, 0.55, 0.42];
const GRADIENT_LOW: Rgba = [0.3, 0.78, 0.53, 0.62];
const GRADIENT_HIGH: Rgba = [0.4, 0.62, 0.95, 0.4];
const COLUMN: Rgba = [0.98, 0.72, 0.32, 0.13];
const COLUMN_EDGE: Rgba = [0.99, 0.8, 0.45, 0.75];

/** Convex hull of points (monotone chain), counter-clockwise. */
function convexHull(points: [number, number][]): [number, number][] {
  const sorted = [...points].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  if (sorted.length < 3) return sorted;
  const cross = (o: [number, number], a: [number, number], b: [number, number]) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const half = (list: [number, number][]) => {
    const out: [number, number][] = [];
    for (const p of list) {
      while (out.length >= 2 && cross(out[out.length - 2], out[out.length - 1], p) <= 0) out.pop();
      out.push(p);
    }
    out.pop();
    return out;
  };
  return [...half(sorted), ...half([...sorted].reverse())];
}
const LABEL = "rgba(205, 214, 220, 0.72)";
const TURBINE_BODY: Rgba = [0.92, 0.94, 0.93, 1];
const BLADE: Rgba = [0.97, 0.98, 0.97, 1];
const TURBINE_LINE: Rgba = [0.94, 0.96, 0.95, 0.8];
// Light from the north-west, low over the horizon: it brings out the relief
const LIGHT = (() => {
  const elevation = (25 * Math.PI) / 180;
  const v = [-Math.cos(elevation) * Math.SQRT1_2, Math.cos(elevation) * Math.SQRT1_2, Math.sin(elevation)];
  return v;
})();
// Exaggerations offered: round values only, ×100 at most (beyond, the view says nothing more);
// ×10 at first, where the turbines keep their shape
const EXAGGERATIONS = [1, 2, 3, 5, 10, 15, 20, 30, 50, 75, 100];
const DEFAULT_EXAGGERATION = 10;

function ramp(stops: [number, Rgba][], value: number): Rgba {
  const descending = stops[0][0] > stops[stops.length - 1][0];
  const ordered = descending ? [...stops].reverse() : stops;
  if (value <= ordered[0][0]) return ordered[0][1];
  for (let i = 1; i < ordered.length; i++) {
    if (value <= ordered[i][0]) return mix(ordered[i - 1][1], ordered[i][1], (value - ordered[i - 1][0]) / (ordered[i][0] - ordered[i - 1][0]));
  }
  return ordered[ordered.length - 1][1];
}

/** The domain shown and the domains nested in it (at any depth). */
function cellDomains(data: SceneData): SceneData["domains"] {
  const inside = (d: SceneData["domains"][number]): boolean => d.number === data.domain || (d.parent > 0 && inside(data.domains[d.parent - 1]));
  return data.domains.filter(inside);
}

/** One line in how many, so that a domain shows at most MOST_CELL_LINES lines a side. */
function cellsEvery(d: SceneData["domains"][number]): number {
  return Math.max(1, Math.ceil(Math.max(d.cells_x, d.cells_y) / MOST_CELL_LINES));
}

function decode(text: string): Float32Array {
  const binary = atob(text);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  return new Float32Array(bytes.buffer);
}

function niceStep(span: number, parts = 5): number {
  const raw = span / parts;
  const power = 10 ** Math.floor(Math.log10(raw));
  return [1, 2, 5, 10].map((m) => m * power).find((s) => s >= raw) ?? raw;
}

/** A model field (cell centres) on the display grid, bilinear: as the server's `upsample`. */
function upsample(model: Float32Array, nx: number, ny: number, factor: number, out = new Float32Array(nx * ny * factor * factor)): Float32Array {
  const nxd = nx * factor;
  for (let jd = 0; jd < ny * factor; jd++) {
    const y = Math.min(Math.max((jd + 0.5) / factor - 0.5, 0), ny - 1);
    const j0 = Math.floor(y);
    const j1 = Math.min(j0 + 1, ny - 1);
    const fy = y - j0;
    for (let id = 0; id < nxd; id++) {
      const x = Math.min(Math.max((id + 0.5) / factor - 0.5, 0), nx - 1);
      const i0 = Math.floor(x);
      const i1 = Math.min(i0 + 1, nx - 1);
      const fx = x - i0;
      const top = model[j0 * nx + i0] * (1 - fx) + model[j0 * nx + i1] * fx;
      const bottom = model[j1 * nx + i0] * (1 - fx) + model[j1 * nx + i1] * fx;
      out[jd * nxd + id] = top * (1 - fy) + bottom * fy;
    }
  }
  return out;
}

/** Everything the meshes need, computed once per scene. */
interface Prepared {
  data: SceneData;
  nxd: number;
  nyd: number;
  xd: number[];
  yd: number[];
  ground: Float32Array;
  land: Float32Array;
  modelGround: Float32Array;
  levels: Map<number, Float32Array>;
}

function prepare(data: SceneData): Prepared {
  const own = data.domains[data.domain - 1];
  const { nx: nxd, ny: nyd, factor } = data.display;
  const xd = Array.from({ length: nxd }, (_, i) => own.west + ((i + 0.5) * (own.east - own.west)) / nxd);
  const yd = Array.from({ length: nyd }, (_, j) => own.south + ((j + 0.5) * (own.north - own.south)) / nyd);
  const ground = decode(data.display.terrain_m);
  const land = ground.map((h) => Math.max(h, 0));
  const modelGround = upsample(decode(data.terrain_m), data.nx, data.ny, factor);
  return { data, nxd, nyd, xd, yd, ground, land, modelGround, levels: new Map() };
}

/** Heights (m) of full level k on the display grid, laid on the visible terrain by B(eta). */
function levelOnDisplay(p: Prepared, heights: Float32Array, k: number): Float32Array {
  const found = p.levels.get(k);
  if (found) return found;
  const { nx, ny } = p.data;
  const b = p.data.b_full[k] ?? 0;
  const out = upsample(heights.subarray(k * nx * ny, (k + 1) * nx * ny), nx, ny, p.data.display.factor);
  for (let i = 0; i < out.length; i++) out[i] += b * (p.land[i] - p.modelGround[i]);
  p.levels.set(k, out);
  return out;
}

interface Options {
  layers: Set<Layer>;
  cells: Cells;
  ceiling: number;
  curtainAxis: "x" | "y";
  curtainShare: number;
  shadeScale: number;
}

interface Built {
  meshes: Mesh[];
  // Walls in the order west, east, south, north: only the two far ones are drawn
  walls: Mesh[];
  box: { west: number; east: number; south: number; north: number; floor: number; top: number };
}

/** Every mesh of the scene, in km (heights unscaled: the renderer applies the exaggeration). */
function build(p: Prepared, heights: Float32Array, o: Options): Built {
  const { data, nxd, nyd, xd, yd, ground, land } = p;
  const own = data.domains[data.domain - 1];
  const top = o.ceiling / 1000;
  const floor = -0.05 * top;
  const z = (metres: number) => Math.min(metres, o.ceiling) / 1000;
  const meshes: Mesh[] = [];
  // Heights swept by the rotors of the turbine models in use, metres
  const rotors = [...new Set(data.turbines.filter((t) => t.hub_m && t.rotor_m).map((t) => `${t.hub_m}:${t.rotor_m}`))].map((key) => {
    const [hub, rotor] = key.split(":").map(Number);
    return [hub - rotor / 2, hub + rotor / 2] as const;
  });
  const shown = data.sea_level_heights_m.map((h, k) => ({ h, k })).filter(({ h, k }) => k > 0 && h <= o.ceiling).map(({ k }) => k);
  const hasDepth = data.display.source === "tiles";

  if (o.layers.has("terrain")) {
    const mesh = new MeshBuilder("triangles");
    const dx = (own.east - own.west) / nxd;
    const dy = (own.north - own.south) / nyd;
    const colors: Rgba[] = new Array(nxd * nyd);
    const heightAt = (i: number, j: number) => z(land[Math.min(Math.max(j, 0), nyd - 1) * nxd + Math.min(Math.max(i, 0), nxd - 1)]);
    for (let j = 0; j < nyd; j++) {
      for (let i = 0; i < nxd; i++) {
        const g = ground[j * nxd + i];
        if (g <= 0) {
          colors[j * nxd + i] = hasDepth ? ramp(SEA, g) : SEA_FLAT;
          continue;
        }
        const gx = ((heightAt(i + 1, j) - heightAt(i - 1, j)) * o.shadeScale) / (2 * dx);
        const gy = ((heightAt(i, j + 1) - heightAt(i, j - 1)) * o.shadeScale) / (2 * dy);
        const norm = Math.hypot(gx, gy, 1);
        const lambert = Math.max(0, (-gx * LIGHT[0] - gy * LIGHT[1] + LIGHT[2]) / norm);
        const f = Math.min(1.12, 0.5 + 0.75 * lambert);
        const base = ramp(LAND, g);
        colors[j * nxd + i] = [base[0] * f, base[1] * f, base[2] * f, 1];
      }
    }
    for (let j = 0; j < nyd - 1; j++) {
      for (let i = 0; i < nxd - 1; i++) {
        const corners: [number, number][] = [[i, j], [i + 1, j], [i + 1, j + 1], [i, j + 1]];
        for (const index of [0, 1, 2, 0, 2, 3]) {
          const [ci, cj] = corners[index];
          mesh.vertex(xd[ci], yd[cj], z(land[cj * nxd + ci]), colors[cj * nxd + ci]);
        }
      }
    }
    // The sides of the terrain, down to the floor of the box
    const side = (points: [number, number][]) => {
      for (let n = 0; n < points.length - 1; n++) {
        const [i0, j0] = points[n];
        const [i1, j1] = points[n + 1];
        const a: [number, number, number] = [xd[i0], yd[j0], z(land[j0 * nxd + i0])];
        const b: [number, number, number] = [xd[i1], yd[j1], z(land[j1 * nxd + i1])];
        const quad: [number, number, number][] = [a, b, [b[0], b[1], floor], [a[0], a[1], floor]];
        for (const index of [0, 1, 2, 0, 2, 3]) mesh.vertex(...quad[index], SKIRT);
      }
    };
    side(Array.from({ length: nxd }, (_, i) => [i, 0]));
    side(Array.from({ length: nxd }, (_, i) => [i, nyd - 1]));
    side(Array.from({ length: nyd }, (_, j) => [0, j]));
    side(Array.from({ length: nyd }, (_, j) => [nxd - 1, j]));
    meshes.push(mesh.build());

    // The coast: where the ground crosses 0 m, between the points of the grid
    const coast = new MeshBuilder("lines");
    const lift = top * 0.002;
    for (let j = 0; j < nyd - 1; j++) {
      for (let i = 0; i < nxd - 1; i++) {
        const corners: [number, number][] = [[i, j], [i + 1, j], [i + 1, j + 1], [i, j + 1]];
        const crossings: [number, number][] = [];
        for (let e = 0; e < 4; e++) {
          const [ia, ja] = corners[e];
          const [ib, jb] = corners[(e + 1) % 4];
          const ga = ground[ja * nxd + ia];
          const gb = ground[jb * nxd + ib];
          if ((ga > 0) !== (gb > 0)) {
            const f = ga / (ga - gb);
            crossings.push([xd[ia] + (xd[ib] - xd[ia]) * f, yd[ja] + (yd[jb] - yd[ja]) * f]);
          }
        }
        for (let c = 0; c + 1 < crossings.length; c += 2) coast.line([...crossings[c], lift], [...crossings[c + 1], lift], COAST);
      }
    }
    meshes.push(coast.build());
  }

  // The levels, by their outline (the real cells are the layer "cells")
  if (o.layers.has("sheets")) {
    const step = Math.max(1, Math.round(Math.max(nxd, nyd) / 60));
    const columns = Array.from({ length: Math.ceil(nxd / step) }, (_, n) => Math.min(n * step, nxd - 1));
    const rows = Array.from({ length: Math.ceil(nyd / step) }, (_, n) => Math.min(n * step, nyd - 1));
    if (columns[columns.length - 1] !== nxd - 1) columns.push(nxd - 1);
    if (rows[rows.length - 1] !== nyd - 1) rows.push(nyd - 1);
    const outline = new MeshBuilder("lines");
    for (const k of shown) {
      const h = levelOnDisplay(p, heights, k);
      const edge = (points: [number, number][]) => {
        for (let n = 0; n < points.length - 1; n++) {
          const [i0, j0] = points[n];
          const [i1, j1] = points[n + 1];
          if (h[j0 * nxd + i0] > o.ceiling || h[j1 * nxd + i1] > o.ceiling) continue;
          outline.line([xd[i0], yd[j0], z(h[j0 * nxd + i0])], [xd[i1], yd[j1], z(h[j1 * nxd + i1])], SHEET_EDGE);
        }
      };
      edge(columns.map((i) => [i, 0]));
      edge(columns.map((i) => [i, nyd - 1]));
      edge(rows.map((j) => [0, j]));
      edge(rows.map((j) => [nxd - 1, j]));
    }
    meshes.push(outline.build());
  }

  // The real cells of the domain shown and of the domains nested in it, each domain with its own
  // spacing (one line in `every` when they are too many to read): on the ground, or on every
  // level shown, following it over the relief (never both)
  if (o.cells !== "none") {
    const lines = new MeshBuilder("lines");
    const lift = top * 0.004;
    const width = own.east - own.west;
    const depth = own.north - own.south;
    const surfaces = o.cells === "ground" ? [land] : shown.map((k) => levelOnDisplay(p, heights, k));
    const fade = o.cells === "ground" ? 1 : 0.55;
    const step = width / nxd;
    for (const surface of surfaces) {
      const heightAt = (x: number, y: number) => {
        const i = Math.min(nxd - 1, Math.max(0, Math.floor(((x - own.west) / width) * nxd)));
        const j = Math.min(nyd - 1, Math.max(0, Math.floor(((y - own.south) / depth) * nyd)));
        return surface[j * nxd + i];
      };
      for (const d of cellDomains(data)) {
        const every = cellsEvery(d);
        const [r, g, b, a] = d.number === data.domain ? CELLS : CELLS_NESTED;
        const colour: Rgba = [r, g, b, a * fade];
        const along = (x0: number, y0: number, x1: number, y1: number) => {
          const n = Math.max(1, Math.ceil(Math.hypot(x1 - x0, y1 - y0) / step));
          for (let k = 0; k < n; k++) {
            const [ax, ay] = [x0 + ((x1 - x0) * k) / n, y0 + ((y1 - y0) * k) / n];
            const [bx, by] = [x0 + ((x1 - x0) * (k + 1)) / n, y0 + ((y1 - y0) * (k + 1)) / n];
            const [ha, hb] = [heightAt(ax, ay), heightAt(bx, by)];
            if (ha > o.ceiling || hb > o.ceiling) continue;
            lines.line([ax, ay, z(ha) + lift], [bx, by, z(hb) + lift], colour);
          }
        };
        for (let i = 0; i <= d.cells_x; i += every) along(d.west + i * d.dx_km, d.south, d.west + i * d.dx_km, d.north);
        for (let j = 0; j <= d.cells_y; j += every) along(d.west, d.south + j * d.dx_km, d.east, d.south + j * d.dx_km);
        if (d.cells_x % every) along(d.east, d.south, d.east, d.north);
        if (d.cells_y % every) along(d.west, d.north, d.east, d.north);
      }
    }
    meshes.push(lines.build());
  }

  // The curtain: the layers as bands along one line of the grid, which the slider moves
  if (o.layers.has("curtain") && shown.length) {
    const along = o.curtainAxis === "x" ? nxd : nyd;
    const fixed = Math.round(((o.curtainAxis === "x" ? nyd : nxd) - 1) * o.curtainShare / 100);
    const index = (n: number) => (o.curtainAxis === "x" ? fixed * nxd + n : n * nxd + fixed);
    const at = (n: number): [number, number] => (o.curtainAxis === "x" ? [xd[n], yd[fixed]] : [xd[fixed], yd[n]]);
    const bands = new MeshBuilder("triangles", true, 10_000);
    const lines = new MeshBuilder("lines");
    const last = shown[shown.length - 1];
    const level = (k: number) => (k === 0 ? land : levelOnDisplay(p, heights, k));
    for (let k = 0; k < last; k++) {
      const below = level(k);
      const above = level(k + 1);
      for (let n = 0; n < along - 1; n++) {
        if (Math.max(above[index(n)], above[index(n + 1)]) > o.ceiling) continue;
        const quad: [number, number, number][] = [
          [...at(n), z(below[index(n)])], [...at(n + 1), z(below[index(n + 1)])],
          [...at(n + 1), z(above[index(n + 1)])], [...at(n), z(above[index(n)])],
        ];
        const low = Math.min(below[index(n)], below[index(n + 1)]);
        const high = Math.max(above[index(n)], above[index(n + 1)]);
        // From green near the sea to blue aloft, every other layer lighter; orange where the blades pass
        const tint = mix(GRADIENT_LOW, GRADIENT_HIGH, Math.min(1, k / Math.max(1, last - 1)));
        let colour: Rgba = k % 2 ? tint : [tint[0], tint[1], tint[2], tint[3] * 0.55];
        if (o.layers.has("rotor") && rotors.some(([a, b]) => low < b && high > a)) colour = k % 2 ? ROTOR_A : ROTOR_B;
        for (const v of [0, 1, 2, 0, 2, 3]) bands.vertex(...quad[v], colour);
      }
    }
    for (let k = 1; k <= last; k++) {
      const h = level(k);
      for (let n = 0; n < along - 1; n++) {
        if (Math.max(h[index(n)], h[index(n + 1)]) > o.ceiling) continue;
        lines.line([...at(n), z(h[index(n)])], [...at(n + 1), z(h[index(n + 1)])], CURTAIN_LINE);
      }
    }
    meshes.push(bands.build(), lines.build());
  }

  // The air of each farm: a column over its turbines, from the sea to the top of the blades
  if (o.layers.has("air")) {
    const fill = new MeshBuilder("triangles", true, 5_000);
    const edges = new MeshBuilder("lines");
    for (const farm of data.farms) {
      const own = data.turbines.filter((t) => t.farm === farm.id);
      const hull = convexHull(own.map((t) => [t.x, t.y]));
      const tip = Math.max(0, ...own.map((t) => (t.hub_m ?? 0) + (t.rotor_m ?? 0) / 2));
      if (hull.length < 3 || !tip) continue;
      const h = z(tip);
      hull.forEach(([x0, y0], n) => {
        const [x1, y1] = hull[(n + 1) % hull.length];
        const quad: [number, number, number][] = [[x0, y0, 0], [x1, y1, 0], [x1, y1, h], [x0, y0, h]];
        for (const v of [0, 1, 2, 0, 2, 3]) fill.vertex(...quad[v], COLUMN);
        edges.line([x0, y0, h], [x1, y1, h], COLUMN_EDGE);
        edges.line([x0, y0, 0], [x0, y0, h], COLUMN_EDGE);
      });
    }
    meshes.push(fill.build(), edges.build());
  }


  // The box: a gridded floor larger than the domain, and four walls (two are drawn)
  const marginX = (own.east - own.west) * 0.04;
  const marginY = (own.north - own.south) * 0.04;
  const box = { west: own.west - marginX, east: own.east + marginX, south: own.south - marginY, north: own.north + marginY, floor, top };
  const step = niceStep(Math.max(box.east - box.west, box.north - box.south), 6);
  const heightStep = niceStep(o.ceiling, 4) / 1000;
  const floorLines = new MeshBuilder("lines");
  // Grid lines every `step` km from the south-west corner, as the distances written along the edges
  for (let x = box.west + step; x < box.east; x += step) floorLines.line([x, box.south, floor], [x, box.north, floor], GRID);
  for (let y = box.south + step; y < box.north; y += step) floorLines.line([box.west, y, floor], [box.east, y, floor], GRID);
  const corners: [number, number][] = [[box.west, box.south], [box.east, box.south], [box.east, box.north], [box.west, box.north]];
  corners.forEach(([x, y], n) => floorLines.line([x, y, floor], [...corners[(n + 1) % 4], floor], EDGE));
  meshes.push(floorLines.build());
  {
    // The ground around the box: the same grid, on two box widths around it, fading outwards
    const ground = new MeshBuilder("lines");
    const size = Math.max(box.east - box.west, box.north - box.south);
    const reach = 2 * size;
    const fadeAt = (d: number): Rgba => [GRID[0], GRID[1], GRID[2], GRID[3] * Math.max(0, 1 - d / reach)];
    const first = (v: number) => Math.floor(v / step) * step;
    for (let x = first(box.west - reach); x <= box.east + reach; x += step) {
      const d = Math.max(0, box.west - x, x - box.east);
      if (d <= 0) continue;
      ground.line([x, box.south - reach + d, floor], [x, box.north + reach - d, floor], fadeAt(d));
    }
    for (let y = first(box.south - reach); y <= box.north + reach; y += step) {
      const d = Math.max(0, box.south - y, y - box.north);
      if (d <= 0) continue;
      ground.line([box.west - reach + d, y, floor], [box.east + reach - d, y, floor], fadeAt(d));
    }
    // Inside the width of the box, the lines that continue its own grid beyond its edges
    for (let x = box.west + step; x < box.east; x += step) {
      for (const [from, to] of [[box.south - reach, box.south], [box.north, box.north + reach]] as const) {
        const parts = 8;
        for (let n = 0; n < parts; n++) {
          const a = from + ((to - from) * n) / parts;
          const b = from + ((to - from) * (n + 1)) / parts;
          const d = Math.min(Math.abs((a + b) / 2 - box.south), Math.abs((a + b) / 2 - box.north));
          ground.line([x, a, floor], [x, b, floor], fadeAt(d));
        }
      }
    }
    for (let y = box.south + step; y < box.north; y += step) {
      for (const [from, to] of [[box.west - reach, box.west], [box.east, box.east + reach]] as const) {
        const parts = 8;
        for (let n = 0; n < parts; n++) {
          const a = from + ((to - from) * n) / parts;
          const b = from + ((to - from) * (n + 1)) / parts;
          const d = Math.min(Math.abs((a + b) / 2 - box.west), Math.abs((a + b) / 2 - box.east));
          ground.line([a, y, floor], [b, y, floor], fadeAt(d));
        }
      }
    }
    meshes.push(ground.build());
  }
  const wall = (x0: number, y0: number, x1: number, y1: number): Mesh[] => {
    const fill = new MeshBuilder("triangles", true, -1);
    const quad: [number, number, number][] = [[x0, y0, floor], [x1, y1, floor], [x1, y1, top], [x0, y0, top]];
    for (const v of [0, 1, 2, 0, 2, 3]) fill.vertex(...quad[v], WALL);
    const grid = new MeshBuilder("lines");
    const length = Math.hypot(x1 - x0, y1 - y0);
    const start = x0 !== x1 ? Math.min(x0, x1) : Math.min(y0, y1);
    for (let s = start + step; s < start + length; s += step) {
      const t = (s - start) / length;
      const px = x0 !== x1 ? Math.min(x0, x1) + (Math.abs(x1 - x0)) * t : x0;
      const py = x0 !== x1 ? y0 : Math.min(y0, y1) + Math.abs(y1 - y0) * t;
      grid.line([px, py, floor], [px, py, top], GRID);
    }
    for (let h = 0; h <= top + 1e-9; h += heightStep) grid.line([x0, y0, h], [x1, y1, h], GRID);
    grid.line([x0, y0, top], [x1, y1, top], EDGE);
    grid.line([x0, y0, floor], [x0, y0, top], EDGE);
    grid.line([x1, y1, floor], [x1, y1, top], EDGE);
    return [fill.build(), grid.build()];
  };
  const walls = [
    ...wall(box.west, box.south, box.west, box.north),
    ...wall(box.east, box.south, box.east, box.north),
    ...wall(box.west, box.south, box.east, box.south),
    ...wall(box.west, box.north, box.east, box.north),
  ];
  return { meshes: [...walls, ...meshes], walls, box };
}

// The rotors face the south-west, the prevailing wind of north-western Europe: AHEAD points
// upwind, ACROSS lies in the rotor plane (x east, y north)
const FACING = (225 * Math.PI) / 180;
const AHEAD: [number, number] = [Math.sin(FACING), Math.cos(FACING)];
const ACROSS: [number, number] = [-AHEAD[1], AHEAD[0]];
const SUN = ((v: number[]) => v.map((c) => c / Math.hypot(...v)))([-0.45, 0.55, 0.7]);

function shade(color: Rgba, across: number, ahead: number, up: number): Rgba {
  const n = [across * ACROSS[0] + ahead * AHEAD[0], across * ACROSS[1] + ahead * AHEAD[1], up];
  const light = Math.max(0, (n[0] * SUN[0] + n[1] * SUN[1] + n[2] * SUN[2]) / (Math.hypot(n[0], n[1], n[2]) || 1));
  const f = 0.6 + 0.4 * light;
  return [color[0] * f, color[1] * f, color[2] * f, color[3]];
}

/** Median distance from a turbine to its nearest neighbour (km); 0 for a single turbine. */
function typicalSpacing(points: { x: number; y: number }[]): number {
  const every = Math.ceil(points.length / 2000);
  const nearest: number[] = [];
  points.forEach((a, n) => {
    if (n % every) return;
    let best = Infinity;
    for (const b of points) {
      const d = Math.hypot(a.x - b.x, a.y - b.y);
      if (d > 1e-6 && d < best) best = d;
    }
    if (Number.isFinite(best)) nearest.push(best);
  });
  nearest.sort((a, b) => a - b);
  return nearest.length ? nearest[Math.floor(nearest.length / 2)] : 0;
}

/**
 * The turbines: a tapered tower, a nacelle, a hub and three blades, all facing the same way. Hub height and rotor diameter are exact on the scale of the levels
 * (heights are stretched on the GPU like everything else); the widths follow the same stretch, so
 * that a turbine looks like one, unless neighbours would overlap: the rotor is then narrower (its
 * radius at most 0.42 x the usual spacing), which happens beyond about ×15. One line along the
 * tower and each blade keeps them visible from afar. One geometry, repeated for every turbine.
 */
function turbineMeshes(p: Prepared, o: Options, scale: number): Mesh[] {
  const { data, nxd, nyd, land } = p;
  const own = data.domains[data.domain - 1];
  const z = (metres: number) => Math.min(metres, o.ceiling) / 1000;
  const sites = data.turbines.filter((t) => t.hub_m != null);
  if (!sites.length) return [];
  const spacing = typicalSpacing(sites);
  const solid = new MeshBuilder("triangles");
  const lines = new MeshBuilder("lines");
  for (const t of sites) {
    const hub = t.hub_m!;
    const radius = (t.rotor_m ?? 0) / 2;
    const size = 2 * radius || hub;
    const i = Math.min(nxd - 1, Math.max(0, Math.floor(((t.x - own.west) / (own.east - own.west)) * nxd)));
    const j = Math.min(nyd - 1, Math.max(0, Math.floor(((t.y - own.south) / (own.north - own.south)) * nyd)));
    const base = land[j * nxd + i];
    const stretch = spacing > 0 && radius > 0 ? Math.min(scale, (0.42 * spacing * 1000) / radius) : scale;
    // A point of the turbine: metres across the rotor plane, ahead (upwind) and above the base
    const at = (across: number, ahead: number, height: number): [number, number, number] => [
      t.x + ((across * ACROSS[0] + ahead * AHEAD[0]) * stretch) / 1000,
      t.y + ((across * ACROSS[1] + ahead * AHEAD[1]) * stretch) / 1000,
      z(base + height),
    ];
    const quad = (a: [number, number, number], b: [number, number, number], c: [number, number, number], d: [number, number, number], color: Rgba, target = solid) => {
      for (const v of [a, b, c, a, c, d]) target.vertex(...v, color);
    };

    // Tower: six faces, narrowing to the top
    const bottom = 0.032 * size;
    const top = 0.02 * size;
    const towerTop = hub - 0.022 * size;
    for (let s = 0; s < 6; s++) {
      const a0 = (s * Math.PI) / 3;
      const a1 = ((s + 1) * Math.PI) / 3;
      const mid = (a0 + a1) / 2;
      const color = shade(TURBINE_BODY, Math.cos(mid), Math.sin(mid), 0);
      quad(at(bottom * Math.cos(a0), bottom * Math.sin(a0), 0), at(bottom * Math.cos(a1), bottom * Math.sin(a1), 0),
        at(top * Math.cos(a1), top * Math.sin(a1), towerTop), at(top * Math.cos(a0), top * Math.sin(a0), towerTop), color);
    }
    lines.line(at(0, 0, 0), at(0, 0, hub), TURBINE_LINE);

    // Nacelle: a box behind the rotor, then the hub in front
    const box = (back: number, front: number, half: number, color: Rgba) => {
      const corner = (x: number, y: number, h: number) => at(x * half, y, hub + h * half);
      quad(corner(-1, back, -1), corner(1, back, -1), corner(1, front, -1), corner(-1, front, -1), shade(color, 0, 0, -1));
      quad(corner(-1, back, 1), corner(1, back, 1), corner(1, front, 1), corner(-1, front, 1), shade(color, 0, 0, 1));
      quad(corner(-1, back, -1), corner(-1, front, -1), corner(-1, front, 1), corner(-1, back, 1), shade(color, -1, 0, 0));
      quad(corner(1, back, -1), corner(1, front, -1), corner(1, front, 1), corner(1, back, 1), shade(color, 1, 0, 0));
      quad(corner(-1, back, -1), corner(1, back, -1), corner(1, back, 1), corner(-1, back, 1), shade(color, 0, -1, 0));
      quad(corner(-1, front, -1), corner(1, front, -1), corner(1, front, 1), corner(-1, front, 1), shade(color, 0, 1, 0));
    };
    box(-0.09 * size, 0.03 * size, 0.022 * size, TURBINE_BODY);
    box(0.03 * size, 0.055 * size, 0.014 * size, TURBINE_BODY);
    if (radius <= 0) continue;
    const plane = 0.05 * size;

    // Three blades, one pointing up: wider near the root, thin at the tip
    const stations = [[0.05, 0.05], [0.22, 0.085], [0.6, 0.05], [1, 0.016]];
    for (const angle of [90, 210, 330]) {
      const a = (angle * Math.PI) / 180;
      const dir = [Math.cos(a), Math.sin(a)];
      const side = [-Math.sin(a), Math.cos(a)];
      const edge = (r: number, chord: number, k: number) =>
        at((r * dir[0] + k * chord * side[0]) * radius, plane, hub + (r * dir[1] + k * chord * side[1]) * radius);
      const color = shade(BLADE, 0, 1, 0.3);
      for (let s = 0; s < stations.length - 1; s++) {
        const [r0, c0] = stations[s];
        const [r1, c1] = stations[s + 1];
        quad(edge(r0, c0, 0.35), edge(r1, c1, 0.35), edge(r1, c1, -0.65), edge(r0, c0, -0.65), color);
      }
      lines.line(at(0, plane, hub), at(dir[0] * radius, plane, hub + dir[1] * radius), TURBINE_LINE);
    }
  }
  return [solid.build(), lines.build()];
}

type ReliefMode = "geography" | "tiles";

function useScene(draft: Case, domain: number, mode: ReliefMode, relief: string) {
  // One path for the relief, searched by the server (empty: the engine's geography, else the
  // tiles); or the public tiles first, the geography when they cannot be had
  const request = useMemo(() => ({
    case: draft,
    domain,
    relief: mode === "geography" ? relief.trim() || null : null,
    tiles_first: mode === "tiles",
  }), [draft, domain, mode, relief]);
  const [body] = useDebouncedValue(request, 500);
  return useQuery({
    queryKey: ["method-scene", body.domain, body.relief, body.tiles_first, body.case.grid, body.case.dynamics, body.case.namelist_input, body.case.farms, body.case.turbine_types],
    queryFn: () => post<SceneData>("/api/method/scene", body),
    retry: false,
    placeholderData: keepPreviousData,
    staleTime: Infinity,
    gcTime: 30 * 60_000,
  });
}

/** The area of the turbines (km), of one farm or of all, or null when there are none. */
function farmArea(data: SceneData, farm?: string | null): { west: number; east: number; south: number; north: number } | null {
  const sites = data.turbines.filter((t) => t.hub_m != null && (!farm || t.farm === farm));
  if (!sites.length) return null;
  const xs = sites.map((t) => t.x);
  const ys = sites.map((t) => t.y);
  return { west: Math.min(...xs), east: Math.max(...xs), south: Math.min(...ys), north: Math.max(...ys) };
}

/** The first view, seen from the south-west and a little above: the farms and their surroundings
    (twice their size, 8 km at least) with the levels above them, so that turbines, levels
    and curtain read together at ×10 (a whole domain is often 30 times wider than its 1 km of
    height); without turbines, the whole box. Zooming out shows the rest. */
/** The level ``k`` (0: the ground) as a light sheet over the domain, with its outline. */
function levelSheet(p: Prepared, heights: Float32Array, k: number, ceiling: number): Mesh[] {
  const { nxd, nyd, xd, yd, land } = p;
  const h = k === 0 ? land : levelOnDisplay(p, heights, k);
  let lowest = Infinity;
  for (let n = 0; n < h.length; n++) lowest = Math.min(lowest, h[n]);
  if (!(lowest <= ceiling)) return [];
  const z = (metres: number) => Math.min(metres, ceiling) / 1000;
  const sheet = new MeshBuilder("triangles", true, 20_000);
  const outline = new MeshBuilder("lines");
  const at = (i: number, j: number): [number, number, number] => [xd[i], yd[j], z(h[j * nxd + i])];
  for (let j = 0; j < nyd - 1; j++) {
    for (let i = 0; i < nxd - 1; i++) {
      const quad = [at(i, j), at(i + 1, j), at(i + 1, j + 1), at(i, j + 1)];
      for (const v of [0, 1, 2, 0, 2, 3]) sheet.vertex(...quad[v], LEVEL_LIT);
    }
  }
  for (let i = 0; i < nxd - 1; i++) {
    outline.line(at(i, 0), at(i + 1, 0), LEVEL_EDGE);
    outline.line(at(i, nyd - 1), at(i + 1, nyd - 1), LEVEL_EDGE);
  }
  for (let j = 0; j < nyd - 1; j++) {
    outline.line(at(0, j), at(0, j + 1), LEVEL_EDGE);
    outline.line(at(nxd - 1, j), at(nxd - 1, j + 1), LEVEL_EDGE);
  }
  return [sheet.build(), outline.build()];
}

function framing(box: Built["box"], scale: number, data: SceneData, farm?: string | null): Camera {
  const height = (box.top - box.floor) * scale;
  const area = farmArea(data, farm);
  if (area) {
    // One farm: closer (4 km at least); all the farms: 8 km at least
    const span = Math.max(2 * Math.max(area.east - area.west, area.north - area.south), farm ? 4 : 8);
    const radius = 0.5 * Math.hypot(span, span, height);
    return { azimuth: -0.62, elevation: 0.26, distance: radius * 1.5, target: [(area.west + area.east) / 2, (area.south + area.north) / 2, height * 0.14] };
  }
  return wholeBox(box, scale);
}

/** The whole box, seen from the south-west and above: also the farthest the wheel zooms out
    (a little beyond). */
function wholeBox(box: Built["box"], scale: number): Camera {
  const height = (box.top - box.floor) * scale;
  const width = box.east - box.west;
  const depth = box.north - box.south;
  const radius = 0.5 * Math.hypot(width, depth, height);
  return { azimuth: -0.62, elevation: 0.44, distance: radius * 2.05, target: [(box.west + box.east) / 2, (box.south + box.north) / 2, height * 0.18] };
}

/** Where the label of each farm points: the middle of its turbines, above the highest rotor (km, m). */
function farmAnchors(data: SceneData): { id: string; name: string; x: number; y: number; top_m: number }[] {
  return data.farms.flatMap((farm) => {
    const sites = data.turbines.filter((t) => t.farm === farm.id);
    if (!sites.length) return [];
    const x = sites.reduce((sum, t) => sum + t.x, 0) / sites.length;
    const y = sites.reduce((sum, t) => sum + t.y, 0) / sites.length;
    const top_m = Math.max(...sites.map((t) => (t.hub_m ?? 0) + (t.rotor_m ?? 0) / 2));
    return [{ id: farm.id, name: farm.name, x, y, top_m }];
  });
}

/** The farm to frame, and a counter so that choosing it again frames it again. */
export interface Focus { farm: string | null; n: number }

function Canvas({ data, options, scale, focus, orbit, onFarm }: { data: SceneData; options: Options; scale: number; focus: Focus; orbit: boolean; onFarm: (farm: string) => void }) {
  const f = useFormat();
  const canvas = useRef<HTMLCanvasElement>(null);
  const overlay = useRef<HTMLDivElement>(null);
  const farmLabels = useRef<HTMLDivElement>(null);
  const anchors = useMemo(() => farmAnchors(data), [data]);
  const onFarmRef = useRef(onFarm);
  onFarmRef.current = onFarm;
  const renderer = useRef<SceneRenderer | null>(null);
  const prepared = useMemo(() => prepare(data), [data]);
  const heights = useMemo(() => decode(data.heights_m), [data.heights_m]);
  const built = useMemo(() => build(prepared, heights, options), [prepared, heights, options]);
  // The turbines' widths follow the exaggeration: rebuilt with it (the rest is not)
  const turbines = useMemo(
    () => (options.layers.has("turbines") ? turbineMeshes(prepared, options, scale) : []),
    [prepared, options, scale],
  );
  const [error, setError] = useState<unknown>(null);
  const framed = useRef("");
  const hovered = useSyncExternalStore(levelHover.subscribe, levelHover.get);
  const lit = useMemo(() => (hovered === null ? [] : levelSheet(prepared, heights, hovered, options.ceiling)), [prepared, heights, hovered, options.ceiling]);

  // A farm chosen (in the list or on its label): the camera glides to it; none: all the farms
  useEffect(() => {
    if (focus.n > 0) renderer.current?.animateTo(framing(built.box, scale, data, focus.farm));
    // Only when a farm is chosen
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus]);

  useEffect(() => { renderer.current?.orbit(orbit); }, [orbit]);

  // One label per farm: its name above it, on a thin line down to it; a click frames the farm
  useEffect(() => {
    const layer = farmLabels.current;
    if (!layer) return;
    layer.replaceChildren(...anchors.map((anchor) => {
      const label = document.createElement("div");
      label.style.cssText = "position:absolute;left:0;top:0;display:none;flex-direction:column;align-items:center;pointer-events:none;transform-origin:50% 100%";
      const name = document.createElement("button");
      name.type = "button";
      name.textContent = anchor.name;
      name.title = anchor.name;
      name.style.cssText = "pointer-events:auto;cursor:pointer;font:600 11.5px/1.2 var(--mantine-font-family);color:rgb(232,238,235);background:rgba(16,18,20,0.82);border:1px solid rgba(232,238,235,0.28);border-radius:7px;padding:3px 8px;white-space:nowrap";
      name.addEventListener("click", () => onFarmRef.current(anchor.id));
      const line = document.createElement("div");
      line.style.cssText = "width:1px;height:30px;background:rgba(232,238,235,0.55)";
      label.append(name, line);
      return label;
    }));
  }, [anchors]);

  useEffect(() => {
    if (!canvas.current) return;
    try {
      // At opening the box turns a slow quarter turn into place (animateTo skips it for people
      // who ask to reduce animations)
      const end = framing(built.box, scale, data);
      const view = new SceneRenderer(canvas.current, { ...end, azimuth: end.azimuth + Math.PI / 2 });
      view.background = BACKGROUND;
      renderer.current = view;
      view.animateTo(end, 2400);
    } catch (problem) {
      setError(problem);
    }
    return () => { renderer.current?.destroy(); renderer.current = null; };
    // One renderer for the life of the view
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const view = renderer.current;
    const box = overlay.current;
    if (!view || !box) return;
    view.zScale = scale;
    view.maxDistance = wholeBox(built.box, scale).distance * 1.35;
    view.minDistance = 0.002 * view.maxDistance;
    view.camera.distance = Math.min(view.camera.distance, view.maxDistance);
    view.setMeshes([...built.meshes, ...turbines, ...lit]);
    // A new domain or height range: the camera glides to frame it
    const key = `${data.domain}:${options.ceiling}`;
    if (framed.current !== key) {
      if (framed.current) view.animateTo(framing(built.box, scale, data));
      framed.current = key;
    }
    // Labels of the box: altitudes on the far vertical edge, distances along the two near edges
    const { west, east, south, north, floor } = built.box;
    const step = niceStep(Math.max(east - west, north - south), 6);
    const heightStep = niceStep(options.ceiling, 4);
    view.onFrame = (matrix, width, height) => {
      const eastSide = Math.sin(view.camera.azimuth) > 0;
      const northSide = -Math.cos(view.camera.azimuth) > 0;
      const farX = eastSide ? west : east;
      const farY = northSide ? south : north;
      const nearX = eastSide ? east : west;
      const nearY = northSide ? north : south;
      built.walls[0].hidden = built.walls[1].hidden = farX !== west;
      built.walls[2].hidden = built.walls[3].hidden = farX !== east;
      built.walls[4].hidden = built.walls[5].hidden = farY !== south;
      built.walls[6].hidden = built.walls[7].hidden = farY !== north;
      const labels: { at: [number, number, number]; text: string }[] = [];
      for (let h = heightStep; h <= options.ceiling + 1e-6; h += heightStep) labels.push({ at: [farX, nearY, h / 1000], text: `${f.number(h, 0)} m` });
      // Distances from the south-west corner of the box, the last one with its unit
      const along = (from: number, to: number) => {
        const values: number[] = [];
        for (let v = step; v <= to - from + 1e-9; v += step) values.push(v);
        return values;
      };
      const xs = along(west, east);
      const ys = along(south, north);
      xs.forEach((v, n) => labels.push({ at: [west + v, nearY, floor], text: n === xs.length - 1 ? `${f.number(v, 0)} km` : f.number(v, 0) }));
      ys.forEach((v, n) => labels.push({ at: [nearX, south + v, floor], text: n === ys.length - 1 ? `${f.number(v, 0)} km` : f.number(v, 0) }));
      while (box.children.length < labels.length) {
        const span = document.createElement("span");
        span.style.cssText = `position:absolute;left:0;top:0;font-size:10.5px;line-height:1;color:${LABEL};white-space:nowrap;pointer-events:none;font-variant-numeric:tabular-nums`;
        box.appendChild(span);
      }
      labels.forEach((label, n) => {
        const span = box.children[n] as HTMLElement;
        const point = project(matrix, [label.at[0], label.at[1], label.at[2] * view.zScale], width, height);
        span.textContent = label.text;
        span.style.display = point ? "block" : "none";
        if (point) span.style.transform = `translate(${Math.round(point[0]) + 6}px, ${Math.round(point[1]) - 6}px)`;
      });
      for (let n = labels.length; n < box.children.length; n++) (box.children[n] as HTMLElement).style.display = "none";
      // The farms' labels, with the turbines only
      const layer = farmLabels.current;
      if (layer) {
        // Labels that would overlap climb on a longer line, one above the other
        const placed: { left: number; right: number; top: number; bottom: number }[] = [];
        anchors.forEach((anchor, n) => {
          const label = layer.children[n] as HTMLElement | undefined;
          if (!label) return;
          const point = options.layers.has("turbines") ? project(matrix, [anchor.x, anchor.y, (anchor.top_m / 1000) * view.zScale], width, height) : null;
          const inside = point && point[0] > -40 && point[0] < width + 40 && point[1] > 0 && point[1] < height + 40;
          label.style.display = inside ? "flex" : "none";
          if (!inside) return;
          const name = label.firstElementChild as HTMLElement;
          const line = label.lastElementChild as HTMLElement;
          const half = name.offsetWidth / 2 + 4;
          const tall = name.offsetHeight + 4;
          let rise = 30;
          const overlaps = () => placed.some((r) => point[0] - half < r.right && point[0] + half > r.left && point[1] - rise - tall < r.bottom && point[1] - rise > r.top);
          while (overlaps() && rise < 30 + 8 * tall) rise += tall;
          placed.push({ left: point[0] - half, right: point[0] + half, top: point[1] - rise - tall, bottom: point[1] - rise });
          line.style.height = `${rise}px`;
          label.style.transform = `translate(${Math.round(point[0])}px, ${Math.round(point[1])}px) translate(-50%, -100%)`;
        });
      }
    };
    view.request();
  }, [built, turbines, lit, scale, data.domain, options.ceiling, options.layers, anchors, f]);

  if (error) return <ErrorState error={error} />;
  return (
    <Box style={{ position: "relative", height: "clamp(380px, 62vh, 640px)", borderRadius: 12, overflow: "hidden", background: "rgb(18, 20, 22)" }}>
      <canvas ref={canvas} style={{ width: "100%", height: "100%", display: "block", touchAction: "none", cursor: "grab" }} />
      <div ref={overlay} style={{ position: "absolute", inset: 0, pointerEvents: "none", overflow: "hidden" }} />
      <div ref={farmLabels} style={{ position: "absolute", inset: 0, pointerEvents: "none", overflow: "hidden" }} />
    </Box>
  );
}

export function SceneControls({ draft }: { draft: Case }) {
  const t = useT(messages);
  const f = useFormat();
  // The innermost domain first: the one of the farms
  const [domain, setDomain] = useState(Math.max(1, draft.grid.domains.length));
  const [relief, setRelief] = useState("");
  // Kept from one opening to the next
  const [mode, setMode] = useLocalStorage<ReliefMode>({ key: "ows-scene-relief", defaultValue: "geography", getInitialValueInEffect: false });
  const [layers, setLayers] = useState<Layer[]>(["terrain", "sheets", "curtain", "rotor", "turbines"]);
  const [cells, setCells] = useState<Cells>("none");
  const [focus, setFocus] = useState<Focus>({ farm: null, n: 0 });
  const [orbit, setOrbit] = useState(false);
  const [ceiling, setCeiling] = useState("1000");
  const [exaggeration, setExaggeration] = useState<number | null>(null);
  const [curtainAxis, setCurtainAxis] = useState<"x" | "y">("x");
  const [curtainShare, setCurtainShare] = useState(50);
  const selectedDomain = Math.min(domain, Math.max(1, draft.grid.domains.length));
  const scene = useScene(draft, selectedDomain, mode, relief);
  const data = scene.data;
  // At first the curtain stands just behind the farms, as seen from the south-west: the turbines
  // read against the levels (once per domain; the slider moves it after)
  const placed = useRef<number | null>(null);
  useEffect(() => {
    if (!data || placed.current === data.domain) return;
    placed.current = data.domain;
    const area = farmArea(data);
    const box = data.domains[data.domain - 1];
    if (!area) return;
    const margin = 0.15 * Math.max(area.east - area.west, area.north - area.south, 2);
    const share = curtainAxis === "x"
      ? (area.north + margin - box.south) / (box.north - box.south)
      : (area.east + margin - box.west) / (box.east - box.west);
    setCurtainShare(Math.round(Math.min(1, Math.max(0, share)) * 100));
    // Only when another domain's scene arrives
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);
  const own = data?.domains[data.domain - 1];
  const width = own ? Math.max(own.east - own.west, own.north - own.south) : 100;
  const ceilingMetres = ceiling === "all" ? (data?.sea_level_heights_m.at(-1) ?? 20000) : Number(ceiling);
  // The shading of the relief follows the exaggeration that would make the box about a sixth as
  // high as it is wide (the view itself starts at ×10)
  const wanted = (0.16 * width) / (ceilingMetres / 1000);
  const automatic = EXAGGERATIONS.reduce((best, value) => (Math.abs(Math.log(value / wanted)) < Math.abs(Math.log(best / wanted)) ? value : best), EXAGGERATIONS[0]);
  const factor = exaggeration ?? DEFAULT_EXAGGERATION;
  const options = useMemo<Options>(() => ({
    layers: new Set(layers),
    cells,
    ceiling: ceilingMetres,
    curtainAxis,
    curtainShare,
    shadeScale: automatic,
  }), [layers, cells, ceilingMetres, curtainAxis, curtainShare, automatic]);
  const position = EXAGGERATIONS.indexOf(factor);

  return (
    <Stack gap="sm">
      <Group justify="space-between" align="center" gap="sm">
        <Group gap="sm">
          {draft.grid.domains.length > 1 && (
            <SegmentedControl aria-label={t("domain")} size="xs" value={String(selectedDomain)} onChange={(value) => { setDomain(Number(value)); setExaggeration(null); }} data={draft.grid.domains.map((_, index) => ({ value: String(index + 1), label: `d${String(index + 1).padStart(2, "0")}` }))} />
          )}
          {data && farmAnchors(data).length > 0 && (
            <Select aria-label={t("farm")} placeholder={t("farm")} size="xs" w={190} clearable searchable data={farmAnchors(data).map((anchor) => ({ value: anchor.id, label: anchor.name }))} value={focus.farm} onChange={(farm) => setFocus((now) => ({ farm, n: now.n + 1 }))} comboboxProps={{ withinPortal: true }} />
          )}
          <SegmentedControl aria-label={t("ceiling")} size="xs" value={ceiling} onChange={(value) => { setCeiling(value); setExaggeration(null); }} data={[{ value: "300", label: "300 m" }, { value: "1000", label: "1 km" }, { value: "3000", label: "3 km" }, { value: "10000", label: "10 km" }, { value: "all", label: t("all") }]} />
        </Group>
        <Group gap={8}>
          <ToolBar label={t("tools")}>
            {([["terrain", "sheets", "curtain", "rotor"], ["turbines", "air"]] as Layer[][]).map((group) => (
              <ToolGroup key={group[0]}>
                {group.map((layer) => (
                  <ToolToggle key={layer} icon={LAYER_ICONS[layer]} label={t(`layers.${layer}`)} hint={t(`hints.${layer}`)} active={layers.includes(layer)}
                    onChange={(on) => setLayers((now) => (on ? [...now, layer] : now.filter((item) => item !== layer)))} />
                ))}
              </ToolGroup>
            ))}
            <ToolGroup>
              <ToolToggle icon={IconRotate360} label={t("orbit")} active={orbit} onChange={setOrbit} />
            </ToolGroup>
            <ToolChoice label={t("cells")} value={cells} onChange={setCells}
              options={(["none", "ground", "levels"] as const).map((value) => ({ value, icon: CELL_ICONS[value], label: t(`cellsModes.${value}`), hint: value === "none" || !data ? undefined : cellDomains(data).map((d) => t("cellsInfo", { n: String(d.number).padStart(2, "0"), dx: f.number(d.dx_km, d.dx_km < 10 ? 1 : 0), every: cellsEvery(d) > 1 ? t("every", { k: cellsEvery(d) }) : "" })).join(" · ") }))} />
          </ToolBar>
        </Group>
      </Group>
      {scene.error ? <ErrorState error={scene.error} onRetry={() => void scene.refetch()} /> : !data ? <LoadingState rows={6} /> : <Canvas data={data} options={options} scale={factor} focus={focus} orbit={orbit} onFarm={(farm) => setFocus((now) => ({ farm, n: now.n + 1 }))} />}
      {data && (
        <Group gap="lg" wrap="nowrap" align="center">
          <Tooltip label={t("curtain")} withArrow><span className="ows-slider-icon"><IconChartArea size={17} stroke={1.6} /></span></Tooltip>
          <SegmentedControl aria-label={t("curtain")} size="xs" value={curtainAxis} onChange={(value) => setCurtainAxis(value as "x" | "y")} data={[{ value: "x", label: t("westEast") }, { value: "y", label: t("southNorth") }]} />
          <Slider style={{ flex: 1 }} aria-label={t("curtain")} size="sm" value={curtainShare} onChange={setCurtainShare} label={null} />
          <Tooltip label={t("exaggeration")} withArrow><span className="ows-slider-icon"><IconArrowAutofitHeight size={17} stroke={1.6} /></span></Tooltip>
          <Text size="xs" fw={600} w={36} className="ows-num">{`×${factor}`}</Text>
          <Slider style={{ flex: 1 }} aria-label={t("exaggeration")} size="sm" min={0} max={EXAGGERATIONS.length - 1} step={1} value={position >= 0 ? position : 0} onChange={(v) => setExaggeration(EXAGGERATIONS[v])} label={null} />
        </Group>
      )}
      <Fold title={t("sources")} aside={data && <Text size="sm" c={data.source === "flat" ? "red" : "dimmed"}>{t(`used.${data.source}`)}</Text>}>
        <Stack gap="sm">
          <SegmentedControl value={mode} onChange={(value) => setMode(value as ReliefMode)} style={{ alignSelf: "flex-start" }}
            data={(["geography", "tiles"] as const).map((value) => ({ value, label: value === "tiles" ? <Tooltip label={t("tilesInfo")} multiline w={300} withArrow><span>{t(`reliefModes.${value}`)}</span></Tooltip> : t(`reliefModes.${value}`) }))} />
          {mode === "geography" && <PathInput label={<FieldLabel label={t("relief")} info={t("reliefInfo")} />} kind="any" placeholder={t("reliefEmpty")} value={relief} onChange={setRelief} />}
          {data && data.source !== "flat" && data.source !== "tiles" && <Text size="sm" c="dimmed">{t("usedPath")} <Text span ff="monospace" size="sm" c="var(--mantine-color-text)" style={{ overflowWrap: "anywhere" }}>{data.source_detail}</Text></Text>}
          {data?.problems.map((problem) => <Text key={problem} size="sm" c={data.source === "flat" ? "red" : "dimmed"}>{problem}</Text>)}
        </Stack>
      </Fold>
    </Stack>
  );
}
