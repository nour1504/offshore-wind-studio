/**
 * The domains taken by hand on the map. A click in a domain chooses it (the innermost one there):
 * its boundary band, its handles, its size and its margins then show. Chosen, the handle on its
 * north side moves it (the outer one re-centres the grid; a nest goes by whole cells of its parent,
 * with the nests inside it) and a corner resizes it by whole cells, the opposite corner staying in
 * place. While it follows the pointer the outlines are drawn here, from the same projection as the
 * server (grid.ts); the project changes once, at the release.
 */
import type { Grid } from "../../../api/types";
import { clamp } from "../../../motion";
import type { HandView, MapHand } from "../../../ui/map/ProjectMap";
import { centreOuter, descendants, editGrid, extents, NEST_MARGIN, nestMargins, placeCentre, projectionFor, snapPoints } from "./grid";

type Ring = [number, number][];
interface Box { west: number; east: number; south: number; north: number }

/** Points drawn along each side of an outline (a side is curved on the map) */
const SIDE_POINTS = 16;
/** The corners by their two sides: "sw" is the south and west sides */
const CORNERS = ["sw", "se", "ne", "nw"];
/** The handle that moves a domain, in the middle of its north side */
const MOVE = "move";

/** What the map lets take by hand for a grid, and what it draws meanwhile; null when its projection cannot be drawn. */
export function domainHand(grid: Grid, number: (value: number, digits: number) => string, commit: (grid: Grid) => void): MapHand | null {
  const proj = projectionFor(grid.projection);
  const boxes = extents(grid, proj);
  if (!proj || !boxes) return null;

  /** The marks of a domain of a grid: its band and corners, its size and margins; while it
      follows the pointer, the outlines of what moves with it (every domain with the outer one,
      a nest and the nests inside it), and for the outer domain its centre. */
  const view = (g: Grid, index: number, moving: boolean): HandView | null => {
    const plane = projectionFor(g.projection);
    const all = extents(g, plane);
    const box = all?.[index], d = g.domains[index];
    if (!plane || !all || !box || !d) return null;
    const at = (x: number, y: number): [number, number] => {
      const [lat, lon] = plane.inverse(x, y);
      return [lon, lat];
    };
    const ring = (b: Box): Ring => {
      const corners: [number, number][] = [[b.west, b.south], [b.east, b.south], [b.east, b.north], [b.west, b.north]];
      const points = corners.flatMap(([x0, y0], n) => {
        const [x1, y1] = corners[(n + 1) % 4];
        return Array.from({ length: SIDE_POINTS }, (_, k) => at(x0 + ((x1 - x0) * k) / SIDE_POINTS, y0 + ((y1 - y0) * k) / SIDE_POINTS));
      });
      return [...points, points[0]];
    };
    const x = (box.west + box.east) / 2, y = (box.south + box.north) / 2;
    const km = (metres: number) => number(metres / 1000, metres < 100_000 ? 1 : 0);
    const labels: HandView["labels"] = [{ at: at(x, box.north), text: `${d.e_we} × ${d.e_sn} · ${km(box.east - box.west)} × ${km(box.north - box.south)} km`, above: true }];
    if (index === 0 && moving) labels.push({ at: at(x, y), text: `${number(g.projection.ref_lat, 2)}° · ${number(g.projection.ref_lon, 2)}°` });
    const margins = nestMargins(g, index), parent = all[d.parent_id - 1];
    if (margins && parent) {
      const sides: [number, number, number][] = [[margins.w, (parent.west + box.west) / 2, y], [margins.e, (box.east + parent.east) / 2, y], [margins.s, x, (parent.south + box.south) / 2], [margins.n, x, (box.north + parent.north) / 2]];
      for (const [cells, px, py] of sides) labels.push({ at: at(px, py), text: number(cells, 0), bad: cells < NEST_MARGIN });
    }
    // The band where the domain is driven by its boundary values: its own cells along each edge
    const inset = NEST_MARGIN * box.dx;
    const banded = box.east - box.west > 2 * inset && box.north - box.south > 2 * inset;
    return {
      outlines: moving ? (index === 0 ? all : [index, ...descendants(g, index)].map((n) => all[n])).map(ring) : [],
      bands: banded ? [[ring(box), ring({ west: box.west + inset, east: box.east - inset, south: box.south + inset, north: box.north - inset })]] : [],
      handles: [
        ...CORNERS.map((corner) => ({ id: corner, at: at(corner[1] === "w" ? box.west : box.east, corner[0] === "s" ? box.south : box.north) })),
        { id: MOVE, at: at(x, box.north), move: true },
      ],
      labels,
    };
  };

  /** The grid after a pull of (dx, dy) metres on the plane, on the handle that moves the domain or on a corner. */
  const pulled = (index: number, corner: string): ((g: Grid, dx: number, dy: number) => void) => {
    const box = boxes[index], d = grid.domains[index];
    const middle = (dx: number, dy: number) => proj.inverse((box.west + box.east) / 2 + dx, (box.south + box.north) / 2 + dy);
    // The outer domain centred there, with a new size if given; nothing for a point off the projection
    const centre = (g: Grid, [lat, lon]: [number, number], points?: { we: number; sn: number }) => {
      if (Number.isFinite(lat) && Number.isFinite(lon)) centreOuter(g, lat, lon, points);
    };
    if (corner === MOVE) {
      if (index === 0) return (g, dx, dy) => centre(g, middle(dx, dy));
      // The nest moves with the nests inside it; a point outside its parent leaves it where it was
      return (g, dx, dy) => editGrid(g, (edited) => {
        const placed = placeCentre(edited, index, ...middle(dx, dy), NEST_MARGIN);
        if (placed && !placed.inside) Object.assign(edited.domains[index], { i_parent_start: d.i_parent_start, j_parent_start: d.j_parent_start });
      }, [index, ...descendants(grid, index)]);
    }
    // Whole cells of the parent (of the domain itself for the outer one), the opposite sides in place
    const ratio = index === 0 ? 1 : d.parent_grid_ratio;
    const step = index === 0 ? box.dx : boxes[d.parent_id - 1].dx;
    const cells = { we: (d.e_we - 1) / ratio, sn: (d.e_sn - 1) / ratio };
    const least = { we: (snapPoints(grid, index, "we", 1) - 1) / ratio, sn: (snapPoints(grid, index, "sn", 1) - 1) / ratio };
    // Along an axis: how many cells the low side moves and how many the domain keeps, within the room given
    const pull = (axis: "we" | "sn", low: boolean, moved: number, roomLow: number, roomHigh: number) => {
      const shift = low ? clamp(moved, -roomLow, cells[axis] - least[axis]) : 0;
      return { shift, cells: low ? cells[axis] - shift : clamp(cells[axis] + moved, least[axis], cells[axis] + roomHigh) };
    };
    const west = corner[1] === "w", south = corner[0] === "s";
    if (index === 0) {
      return (g, dx, dy) => {
        const we = pull("we", west, Math.round(dx / step), Infinity, Infinity), sn = pull("sn", south, Math.round(dy / step), Infinity, Infinity);
        // The middle of the new box, on the plane of the grid as it was
        centre(g, middle((we.shift + (we.cells - cells.we) / 2) * step, (sn.shift + (sn.cells - cells.sn) / 2) * step), { we: we.cells + 1, sn: sn.cells + 1 });
      };
    }
    const room = nestMargins(grid, index) ?? { w: 0, e: 0, s: 0, n: 0 };
    return (g, dx, dy) => editGrid(g, (edited) => {
      // The server wants a nest strictly inside its parent: one cell kept on the east and north
      const we = pull("we", west, Math.round(dx / step), room.w, Math.max(0, room.e - 1)), sn = pull("sn", south, Math.round(dy / step), room.s, Math.max(0, room.n - 1));
      Object.assign(edited.domains[index], { i_parent_start: d.i_parent_start + we.shift, j_parent_start: d.j_parent_start + sn.shift, e_we: we.cells * ratio + 1, e_sn: sn.cells * ratio + 1 });
    }, [index]);
  };

  const inside = (index: number, x: number, y: number) => x >= boxes[index].west && x <= boxes[index].east && y >= boxes[index].south && y <= boxes[index].north;
  return {
    // The innermost domain there: a nest comes after its parent, and nests of one parent do not overlap
    pick: ([lon, lat]) => {
      const [x, y] = proj.forward(lat, lon);
      for (let index = boxes.length - 1; index >= 0; index--) if (inside(index, x, y)) return String(index);
      return null;
    },
    marks: (shape) => view(grid, Number(shape), false),
    take: (shape, handle, from) => {
      const index = Number(shape);
      if (!boxes[index]) return null;
      const [x0, y0] = proj.forward(from[1], from[0]);
      const change = pulled(index, handle);
      let latest: Grid | null = null;
      return {
        move: (to) => {
          const [x, y] = proj.forward(to[1], to[0]);
          const next = structuredClone(grid);
          change(next, x - x0, y - y0);
          latest = next;
          return view(next, index, true);
        },
        release: () => {
          const changed = latest !== null && JSON.stringify(latest) !== JSON.stringify(grid);
          if (changed) commit(latest!);
          return changed;
        },
      };
    },
  };
}
