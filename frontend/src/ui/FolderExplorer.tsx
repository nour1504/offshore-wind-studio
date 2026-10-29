/**
 * Choosing a folder (or a file) by clicking. The folders of a machine are blocks linked from left to right (a
 * folder, then its subfolders), opened one level at a time with their chevron; the same tree as an
 * indented list (W3C tree view: arrows, Home, End, Enter). WRF, WPS, the geography, the engine and
 * an extracted project are told by their icon. Nothing is ever written.
 *
 * Motion (durations and curve of motion.ts, CSS variables --ows-dur-* and --ows-ease-out):
 * - opening: the subfolders come out of their parent, fading in from 6 px, one after the other;
 * - closing: they go back into it, shorter, and the parent stays where it was;
 * - blocks already shown slide to their new place, and their links follow them;
 * - a new link is drawn once, from the parent; the branch of the chosen folder changes colour;
 * - the view moves only as much as needed to show what was opened, never while it is held;
 * - far away, chevrons and icons fade and names stay.
 * Everything is immediate for people who ask Windows to reduce animations.
 */
import { ActionIcon, Breadcrumbs, Button, CopyButton, Group, Loader, Modal, SegmentedControl, Stack, Text, TextInput, Tooltip, UnstyledButton } from "@mantine/core";
import {
  IconArrowUp,
  IconCheck,
  IconChevronRight,
  IconCopy,
  IconCpu,
  IconDeviceDesktop,
  IconDots,
  IconFile,
  IconFiles,
  IconFocusCentered,
  IconFolder,
  IconFolderSymlink,
  IconListTree,
  IconLock,
  IconMountain,
  IconRefresh,
  IconSearch,
  IconServer,
  IconSitemap,
  IconWind,
  IconWorld,
  IconZoomIn,
  IconZoomOut,
} from "@tabler/icons-react";
import { type KeyboardEvent, type MouseEvent, type PointerEvent, type WheelEvent, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { type FolderEntry, type FolderListing, type FolderRole, listFolder, type Machine } from "../api/fs";
import { defineMessages, useT } from "../i18n";
import { DURATION, prefersReducedMotion } from "../motion";

const messages = defineMessages({
  en: {
    cancel: "Cancel",
    use: "Use this folder",
    useFile: "Use this file",
    parent: "Parent folder",
    recentre: "Recentre",
    zoomIn: "Zoom in",
    zoomOut: "Zoom out",
    graph: "Blocks",
    list: "List",
    more: "More",
    retry: "Retry",
    copy: "Copy",
    filter: "Filter",
    copied: "Copied",
    computer: "This computer",
    offline: "Unreachable",
    roles: { wrf: "WRF", wps: "WPS", geog: "Geography", engine: "Engine", run: "Project files" },
    wrong: { wrf: "Not WRF", wps: "Not WPS", geog: "Not a geography", engine: "Not an engine", run: "Not project files" },
    resolutions: { default: "High resolution", lowres: "Low resolution" },
    readOnly: "Read only",
    denied: "Access denied",
    empty: "Empty",
  },
  fr: {
    cancel: "Annuler",
    use: "Utiliser ce dossier",
    useFile: "Utiliser ce fichier",
    parent: "Dossier parent",
    recentre: "Recentrer",
    zoomIn: "Zoomer",
    zoomOut: "Dézoomer",
    graph: "Blocs",
    list: "Liste",
    more: "Plus",
    retry: "Réessayer",
    copy: "Copier",
    filter: "Filtrer",
    copied: "Copié",
    computer: "Cet ordinateur",
    offline: "Injoignable",
    roles: { wrf: "WRF", wps: "WPS", geog: "Géographie", engine: "Moteur", run: "Fichiers du projet" },
    wrong: { wrf: "Pas WRF", wps: "Pas WPS", geog: "Pas une géographie", engine: "Pas un moteur", run: "Pas des fichiers du projet" },
    resolutions: { default: "Haute résolution", lowres: "Basse résolution" },
    readOnly: "Lecture seule",
    denied: "Accès refusé",
    empty: "Vide",
  },
});

// Size of a block and gaps between columns and rows, in pixels at zoom 1
const W = 200;
const H = 38;
const GAP_X = 64;
const GAP_Y = 8;
const ZOOM = { min: 0.35, max: 1.6, far: 0.62 };
// Room kept around what is brought into view
const MARGIN = 28;

const ROLE_ICON: Record<FolderRole, typeof IconFolder> = { wrf: IconWind, wps: IconWorld, geog: IconMountain, engine: IconCpu, run: IconFiles };

// Folders already read, per machine: reopening the explorer shows them at once
const cache = new Map<string, FolderListing>();

interface Camera {
  x: number;
  y: number;
  k: number;
}

// The view of each machine when the explorer closed: found again when the same folder reopens it
const memory = new Map<string, { root: string; open: string[]; selected: string; camera: Camera; view: "graph" | "list" }>();

interface Item {
  path: string;
  name: string;
  depth: number;
  parent: string | null;
  entry: FolderEntry | null;
  /** A block that reads the next page of its parent */
  more?: boolean;
}

interface Placed extends Item {
  x: number;
  y: number;
  /** Rank among its siblings, for the order of arrival */
  rank: number;
}

const inside = (path: string, folder: string) => path === folder || path.startsWith(folder.endsWith("/") || folder.endsWith("\\") ? folder : `${folder}/`) || path.startsWith(`${folder}\\`);

/** The segments of a path, each with the path up to it (Linux, Windows drives, \\wsl.localhost). */
function crumbs(path: string): { label: string; path: string }[] {
  if (!path) return [];
  const out: { label: string; path: string }[] = [];
  if (path.startsWith("\\\\")) {
    const parts = path.slice(2).split("\\").filter(Boolean);
    let current = `\\\\${parts.slice(0, 2).join("\\")}`;
    out.push({ label: parts[1] ?? parts[0], path: current });
    for (const part of parts.slice(2)) out.push({ label: part, path: (current = `${current}\\${part}`) });
  } else if (/^[A-Za-z]:/.test(path)) {
    const parts = path.split("\\").filter(Boolean);
    let current = `${parts[0]}\\`;
    out.push({ label: parts[0], path: current });
    for (const part of parts.slice(1)) out.push({ label: part, path: (current = current.endsWith("\\") ? current + part : `${current}\\${part}`) });
  } else {
    let current = "";
    out.push({ label: "/", path: "/" });
    for (const part of path.split("/").filter(Boolean)) out.push({ label: part, path: (current = `${current}/${part}`) });
  }
  return out;
}

const windowsLike = (path: string) => path === "" || path.startsWith("\\\\") || /^[A-Za-z]:/.test(path);

/** The smallest move of the view that shows a box (world coordinates) with a margin. */
function reveal(camera: Camera, box: { x1: number; y1: number; x2: number; y2: number }, view: DOMRect): Camera {
  const fit = (start: number, end: number, size: number) => {
    let shift = 0;
    if (end > size - MARGIN) shift = size - MARGIN - end;
    if (start + shift < MARGIN) shift = MARGIN - start;
    return shift;
  };
  const { k } = camera;
  return {
    k,
    x: camera.x + fit(camera.x + box.x1 * k, camera.x + box.x2 * k, view.width),
    y: camera.y + fit(camera.y + box.y1 * k, camera.y + box.y2 * k, view.height),
  };
}

export interface FolderExplorerProps {
  opened: boolean;
  onClose: () => void;
  machine: Machine;
  /** The folder of the field: opened among its neighbours */
  value: string;
  onChoose: (path: string) => void;
  /** The role the field expects: its folders stand out, another choice is named */
  expect?: FolderRole;
  /** Paths chosen in the other fields, shown */
  marks?: string[];
  /** The folder must be writable (a destination) */
  writable?: boolean;
  /** The profile whose engine machine is shown, the default one otherwise */
  profile?: string;
  /** A file is chosen instead of a folder, or either ("any"): the files are shown too */
  pick?: "folder" | "file" | "any";
}

export function FolderExplorer(props: FolderExplorerProps) {
  return (
    <Modal opened={props.opened} onClose={props.onClose} size="min(1120px, 94vw)" padding="lg" withCloseButton={false} centered>
      {props.opened && <Explorer {...props} />}
    </Modal>
  );
}

function Explorer({ onClose, machine, value, onChoose, expect, marks = [], writable = false, profile, pick = "folder" }: FolderExplorerProps) {
  const t = useT(messages);
  const [folders, setFolders] = useState<Record<string, FolderListing | "loading">>({});
  const [root, setRoot] = useState<string | null>(null);
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState("");
  const [offline, setOffline] = useState(false);
  const [view, setView] = useState<"graph" | "list">("graph");
  const [camera, setCamera] = useState<Camera>({ x: MARGIN, y: MARGIN, k: 1 });
  // While the view is held or zoomed with the wheel it follows at once; otherwise it glides
  const [held, setHeld] = useState(false);
  // The first picture appears in place, without moving
  const [settled, setSettled] = useState(false);
  const [query, setQuery] = useState("");
  const [machineName, setMachineName] = useState("");
  const canvas = useRef<HTMLDivElement>(null);
  const nodes = useRef(new Map<string, HTMLElement>());
  const alive = useRef(true);
  // What the view must show once the layout is there: a folder (opening), or the folder opened
  const pending = useRef<{ centre?: string; anchor?: { path: string; x: number; y: number }; show?: string } | null>(null);
  const place = machine === "engine" && profile ? `engine:${profile}` : machine;
  const keyOf = (path: string) => `${place}|${path}`;
  const motion = !prefersReducedMotion();

  const read = useCallback(
    async (path: string, offset = 0): Promise<FolderListing | null> => {
      const cached = cache.get(keyOf(path));
      if (cached && offset === 0) {
        if (cached.machine) setMachineName(cached.machine);
        setFolders((all) => (all[path] === cached ? all : { ...all, [path]: cached }));
        return cached;
      }
      if (offset === 0) setFolders((all) => ({ ...all, [path]: "loading" }));
      try {
        const page = await listFolder(machine, path, offset, machine === "engine" ? profile : undefined);
        // An answer that arrives after the window closed is dropped
        if (!alive.current) return null;
        if (page.state === "offline") {
          setOffline(true);
          return null;
        }
        if (page.machine) setMachineName(page.machine);
        const before = offset > 0 ? cache.get(keyOf(path)) : undefined;
        const listing = before ? { ...page, entries: [...before.entries, ...page.entries] } : page;
        cache.set(keyOf(path), listing);
        setFolders((all) => ({ ...all, [path]: listing }));
        return listing;
      } catch {
        if (alive.current) setOffline(true);
        return null;
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [place],
  );

  // Opening: the view left on this folder, or the folder of the field among its neighbours (its
  // parent open), or the closest folder that exists
  const start = useCallback(async () => {
    setOffline(false);
    const wanted = value.trim();
    const kept = memory.get(place);
    if (kept && (!wanted || wanted === kept.selected)) {
      setRoot(kept.root);
      setOpen(new Set(kept.open));
      setSelected(kept.selected);
      setCamera(kept.camera);
      setView(kept.view);
      requestAnimationFrame(() => setSettled(true));
      await Promise.all([kept.root, ...kept.open, kept.selected].map((path) => read(path)));
      return;
    }
    let first = await read(wanted || "~");
    // The file of a file field: shown in its folder, opened
    const file = pick !== "folder" && first?.state === "file" ? first.path : null;
    if (first && (first.state === "missing" || first.state === "file")) first = await read(first.nearest ?? "~");
    if (!first) return;
    const top = file ? first.path : (first.parent ?? first.path);
    pending.current = { centre: file ?? first.path };
    setRoot(top);
    setOpen(new Set([top]));
    setSelected(file ?? first.path);
    if (top !== first.path) await read(top);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [read]);

  useEffect(() => {
    alive.current = true;
    void start();
    return () => {
      alive.current = false;
    };
  }, [start]);

  // The view is kept for the next opening
  const kept = useRef({ root, open, selected, camera, view });
  kept.current = { root, open, selected, camera, view };
  useEffect(
    () => () => {
      const last = kept.current;
      if (last.root !== null) memory.set(place, { root: last.root, open: [...last.open], selected: last.selected, camera: last.camera, view: last.view });
    },
    [place],
  );

  const listingOf = (path: string) => {
    const found = folders[path];
    return found && found !== "loading" ? found : null;
  };

  // The tree shown: subfolders of each open folder, hidden folders left out unless chosen
  const keep = useMemo(() => [selected, ...marks].filter(Boolean), [selected, marks]);
  const children = useCallback(
    (path: string, depth: number): Item[] => {
      const listing = folders[path];
      if (!listing || listing === "loading") return [];
      const dirs = listing.entries.filter((e) => (e.kind === "dir" || pick !== "folder") && (!e.name.startsWith(".") || keep.some((k) => inside(k, e.path))));
      const items: Item[] = dirs.map((entry) => ({ path: entry.path, name: entry.name, depth, parent: path, entry }));
      const last = listing.entries[listing.entries.length - 1];
      if (listing.total > listing.entries.length && (last?.kind === "dir" || pick !== "folder")) items.push({ path: `${path}\u0000more`, name: t("more"), depth, parent: path, entry: null, more: true });
      return items;
    },
    [folders, keep, t, pick],
  );

  // Tidy tree from left to right: each folder in the middle of its subfolders, rows never overlap
  const { placed, order, width, height } = useMemo(() => {
    const placed: Placed[] = [];
    const order: Item[] = [];
    if (root === null) return { placed, order, width: 0, height: 0 };
    let cursor = 0;
    let deepest = 0;
    const place = (item: Item, rank: number): number => {
      order.push(item);
      deepest = Math.max(deepest, item.depth);
      const kids = open.has(item.path) ? children(item.path, item.depth + 1) : [];
      const x = item.depth * (W + GAP_X);
      if (!kids.length) {
        const y = cursor;
        cursor += H + GAP_Y;
        placed.push({ ...item, x, y, rank });
        return y;
      }
      const ys = kids.map((kid, i) => place(kid, i));
      const y = (ys[0] + ys[ys.length - 1]) / 2;
      placed.push({ ...item, x, y, rank });
      return y;
    };
    const rootListing = listingOf(root);
    const name = root === "" ? t("computer") : (crumbs(root).pop()?.label ?? root);
    place({ path: root, name, depth: 0, parent: null, entry: rootListing ? { name, path: root, kind: "dir", link: false, readable: rootListing.state !== "denied", writable: rootListing.writable, role: rootListing.role } : null }, 0);
    return { placed, order, width: (deepest + 1) * (W + GAP_X), height: cursor };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [root, open, children, folders, t]);

  const byPath = useMemo(() => new Map(placed.map((p) => [p.path, p])), [placed]);

  // Blocks that just left (a closed folder): kept a moment to go back into their parent
  const [leaving, setLeaving] = useState<Placed[]>([]);
  const previous = useRef(new Map<string, Placed>());
  const timers = useRef<number[]>([]);
  useLayoutEffect(() => {
    const gone = [...previous.current.values()].filter((p) => !byPath.has(p.path));
    previous.current = new Map(byPath);
    if (!gone.length || !motion || view !== "graph") return;
    setLeaving((current) => [...current.filter((l) => !gone.some((g) => g.path === l.path)), ...gone]);
    timers.current.push(window.setTimeout(() => setLeaving((current) => current.filter((l) => !gone.includes(l))), DURATION.state + 40));
  }, [byPath, motion, view]);
  useEffect(() => () => timers.current.forEach((timer) => window.clearTimeout(timer)), []);

  // The chain from the root to the chosen folder: its links stand out
  const chain = useMemo(() => {
    const set = new Set<string>();
    let at = byPath.get(selected);
    while (at) {
      set.add(at.path);
      at = at.parent === null ? undefined : byPath.get(at.parent);
    }
    return set;
  }, [byPath, selected]);

  // After a change of layout: the folder opened stays where it was on screen, then its subfolders
  // are brought into view by the smallest move; at the opening, the folder of the field is centred
  useLayoutEffect(() => {
    const want = pending.current;
    const box = canvas.current?.getBoundingClientRect();
    if (!want || !box) return;
    if (want.centre !== undefined) {
      const node = byPath.get(want.centre);
      if (!node) return;
      pending.current = null;
      // The folder and its parent in the middle, the room on the right for what opens next
      const from = (node.parent !== null && byPath.get(node.parent)) || node;
      setCamera((c) => ({ k: c.k, x: box.width * 0.4 - ((from.x + node.x + W) / 2) * c.k, y: box.height / 2 - (node.y + H / 2) * c.k }));
      nodes.current.get(want.centre)?.focus({ preventScroll: true });
      requestAnimationFrame(() => setSettled(true));
      return;
    }
    const anchor = want.anchor;
    const node = anchor && byPath.get(anchor.path);
    if (!anchor || !node) return;
    const dx = node.x - anchor.x;
    const dy = node.y - anchor.y;
    anchor.x = node.x;
    anchor.y = node.y;
    const shown = want.show === undefined ? undefined : byPath.get(want.show);
    const loaded = folders[want.show ?? anchor.path] !== "loading" && (want.show === undefined || Boolean(shown));
    setCamera((c) => {
      const still = { k: c.k, x: c.x - dx * c.k, y: c.y - dy * c.k };
      if (!loaded) return still;
      // A folder higher up: brought in beside the folder that stayed in place
      if (shown) {
        const both = Math.abs(shown.y - node.y) + H <= box.height / c.k - 2 * MARGIN;
        return reveal(still, { x1: shown.x, y1: both ? Math.min(shown.y, node.y) : node.y, x2: node.x + W, y2: (both ? Math.max(shown.y, node.y) : node.y) + H }, box);
      }
      const kids = placed.filter((p) => p.parent === anchor.path);
      if (!kids.length) return still;
      // A long column: the first subfolders next to their parent, not its far end
      const visible = box.height / c.k - 2 * MARGIN;
      const top = Math.min(node.y, kids[0].y);
      const bottom = Math.min(Math.max(node.y + H, kids[kids.length - 1].y + H), top + visible);
      return reveal(still, { x1: node.x, y1: top, x2: kids[0].x + W, y2: bottom }, box);
    });
    if (loaded) pending.current = null;
  }, [byPath, placed, folders]);

  const toggle = async (path: string) => {
    const opening = !open.has(path);
    const node = byPath.get(path);
    if (node && view === "graph") pending.current = { anchor: { path, x: node.x, y: node.y } };
    setOpen((current) => {
      const next = new Set(current);
      if (opening) next.add(path);
      else for (const each of current) if (each !== root && inside(each, path)) next.delete(each);
      return next;
    });
    if (opening) await read(path);
  };

  const select = (path: string) => {
    setSelected(path);
    void read(path);
  };

  const moreOf = async (item: Item) => {
    if (item.parent === null) return;
    const listing = listingOf(item.parent);
    if (listing) await read(item.parent, listing.entries.length);
  };

  // A folder higher up becomes the first column: what was open stays open, one column further
  const reroot = async (path: string) => {
    if (path === root) return;
    const node = byPath.get(selected) ?? (root !== null ? byPath.get(root) : undefined);
    if (node) pending.current = { anchor: { path: node.path, x: node.x, y: node.y }, show: path };
    setRoot(path);
    setOpen((current) => new Set([...current, path]));
    await read(path);
  };

  const parentOfRoot = root === null ? null : (listingOf(root)?.parent ?? null);

  const showNode = (path: string) => {
    const node = byPath.get(path);
    const box = canvas.current?.getBoundingClientRect();
    if (node && box && view === "graph") setCamera((c) => reveal(c, { x1: node.x, y1: node.y, x2: node.x + W, y2: node.y + H }, box));
  };

  const choose = (path: string) => {
    onChoose(path);
    onClose();
  };

  const onKey = (event: KeyboardEvent, item: Item) => {
    const index = order.findIndex((o) => o.path === item.path);
    const move = (to: Item | undefined) => {
      if (!to) return;
      event.preventDefault();
      if (!to.more) select(to.path);
      nodes.current.get(to.path)?.focus({ preventScroll: view === "graph" });
      showNode(to.path);
    };
    const openable = item.entry?.readable !== false && !item.entry?.loop && !item.more && item.entry?.kind !== "file";
    if (event.key === "ArrowDown") move(order[index + 1]);
    else if (event.key === "ArrowUp") move(order[index - 1]);
    else if (event.key === "Home") move(order[0]);
    else if (event.key === "End") move(order[order.length - 1]);
    else if (event.key === "ArrowRight" && openable) {
      event.preventDefault();
      if (!open.has(item.path)) void toggle(item.path);
      else move(order[index + 1]?.parent === item.path ? order[index + 1] : undefined);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      if (open.has(item.path) && item.depth > 0) void toggle(item.path);
      else move(order.find((o) => o.path === item.parent));
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (item.more) void moreOf(item);
      else if (item.path === selected && usable) choose(item.path);
      else select(item.path);
    }
  };

  // Moving the view by dragging the background, zooming with the wheel around the pointer
  const drag = useRef<{ x: number; y: number; cx: number; cy: number } | null>(null);
  const wheelEnd = useRef(0);
  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if ((event.target as HTMLElement).closest("button, [role=treeitem]")) return;
    pending.current = null;
    drag.current = { x: event.clientX, y: event.clientY, cx: camera.x, cy: camera.y };
    event.currentTarget.setPointerCapture(event.pointerId);
    setHeld(true);
  };
  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const from = drag.current;
    if (from) setCamera((c) => ({ ...c, x: from.cx + event.clientX - from.x, y: from.cy + event.clientY - from.y }));
  };
  const onPointerUp = () => {
    drag.current = null;
    setHeld(false);
  };
  const zoomAt = (factor: number, px?: number, py?: number) => {
    const box = canvas.current?.getBoundingClientRect();
    if (!box) return;
    const mx = px ?? box.width / 2;
    const my = py ?? box.height / 2;
    setCamera((c) => {
      const k = Math.min(ZOOM.max, Math.max(ZOOM.min, c.k * factor));
      return { k, x: mx - ((mx - c.x) * k) / c.k, y: my - ((my - c.y) * k) / c.k };
    });
  };
  const onWheel = (event: WheelEvent<HTMLDivElement>) => {
    const box = canvas.current?.getBoundingClientRect();
    if (!box) return;
    pending.current = null;
    setHeld(true);
    zoomAt(Math.exp(-event.deltaY * 0.0015), event.clientX - box.left, event.clientY - box.top);
    window.clearTimeout(wheelEnd.current);
    wheelEnd.current = window.setTimeout(() => setHeld(false), 140);
  };

  const recentre = () => {
    const node = byPath.get(selected) ?? (root !== null ? byPath.get(root) : undefined);
    const box = canvas.current?.getBoundingClientRect();
    if (!node || !box) return;
    setCamera({ k: 1, x: box.width * 0.3 - (node.x + W / 2), y: box.height / 2 - (node.y + H / 2) });
  };

  const chosen = listingOf(selected);
  const chosenEntry = byPath.get(selected)?.entry ?? null;
  const role = chosen?.role ?? chosenEntry?.role ?? null;
  const readable = chosenEntry?.readable !== false && chosen?.state !== "denied";
  const isFile = chosenEntry?.kind === "file" || chosen?.state === "file";
  const usable = Boolean(selected) && readable && (pick === "file" ? isFile : pick === "any" || (!isFile && (!writable || chosen?.writable !== false)));
  const note = !readable ? t("denied") : writable && chosen && !chosen.writable ? t("readOnly") : expect && chosen && role !== expect ? t(`wrong.${expect}`) : "";
  const details = [role ? t(`roles.${role}`) : "", ...(role === "geog" ? (chosen?.resolutions ?? []).map((r) => t(`resolutions.${r}`)) : []), chosen?.state === "empty" ? t("empty") : ""].filter(Boolean);
  const trail = crumbs(selected);
  const MachineIcon = machine === "engine" ? IconServer : IconDeviceDesktop;
  const needle = query.trim().toLowerCase();

  const block = (item: Item, rank: number, gone = false) => {
    const entry = item.entry;
    const isOpen = open.has(item.path);
    const listing = listingOf(item.path);
    const loading = folders[item.path] === "loading";
    const leaf = listing !== null && !listing.entries.some((e) => e.kind === "dir");
    const canOpen = !item.more && entry?.kind !== "file" && entry?.readable !== false && !entry?.loop && !leaf;
    // Above the drives of Windows: this computer, and the WSL distributions
    const machineIcon = item.path === "" ? IconDeviceDesktop : /^\\\\wsl(\.localhost|\$)\\[^\\]+$/i.test(item.path) ? IconServer : null;
    const Icon = item.more ? IconDots : (machineIcon ?? (entry?.kind === "file" ? IconFile : entry?.role ? ROLE_ICON[entry.role] : entry?.readable === false ? IconLock : entry?.link ? IconFolderSymlink : IconFolder));
    const icon = <Icon size={16} stroke={1.7} className="ows-fx-icon" data-role={entry?.role ?? undefined} data-expected={(expect && entry?.role === expect) || undefined} />;
    return (
      <div
        ref={(el) => {
          if (gone) return;
          if (el) nodes.current.set(item.path, el);
          else nodes.current.delete(item.path);
        }}
        role={gone ? undefined : "treeitem"}
        aria-hidden={gone || undefined}
        tabIndex={gone ? undefined : item.path === selected ? 0 : -1}
        aria-level={gone ? undefined : item.depth + 1}
        aria-selected={gone ? undefined : item.path === selected}
        aria-expanded={!gone && canOpen ? isOpen : undefined}
        aria-label={item.name}
        className="ows-fx-block"
        data-selected={item.path === selected || undefined}
        data-marked={marks.includes(item.path) || undefined}
        data-disabled={entry?.readable === false || undefined}
        data-dim={(needle && !item.name.toLowerCase().includes(needle)) || undefined}
        data-leaving={gone || undefined}
        style={{ ["--ows-fx-delay" as string]: `${Math.min(rank, 10) * 22}ms` }}
        onClick={gone ? undefined : () => (item.more ? void moreOf(item) : select(item.path))}
        onDoubleClick={gone ? undefined : () => (canOpen ? void toggle(item.path) : item.path === selected && usable && choose(item.path))}
        onKeyDown={gone ? undefined : (e) => onKey(e, item)}
      >
        {entry?.role ? <Tooltip label={t(`roles.${entry.role}`)} openDelay={300}>{icon}</Tooltip> : icon}
        <span className="ows-fx-name" title={item.more ? undefined : item.path}>{item.name}</span>
        <span className="ows-fx-end">
          {loading ? (
            <Loader size={12} />
          ) : (
            canOpen && (
              <ActionIcon component="span" size="sm" variant="subtle" color="gray" tabIndex={-1} aria-hidden className="ows-fx-chevron" data-open={isOpen || undefined} onClick={(e: MouseEvent) => { e.stopPropagation(); void toggle(item.path); }}>
                <IconChevronRight size={14} />
              </ActionIcon>
            )
          )}
        </span>
      </div>
    );
  };

  const link = (p: Placed, gone = false) => {
    const from = p.parent === null ? undefined : byPath.get(p.parent);
    if (!from) return null;
    const x1 = from.x + W;
    const y1 = from.y + H / 2;
    const x2 = p.x;
    const y2 = p.y + H / 2;
    const bend = GAP_X * 0.55;
    return <path key={gone ? `${p.path}\u0000gone` : p.path} className="ows-fx-edge" data-active={(!gone && chain.has(p.path)) || undefined} data-leaving={gone || undefined} style={{ ["--ows-fx-delay" as string]: `${Math.min(p.rank, 10) * 22}ms` }} pathLength={1} d={`M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}`} />;
  };

  const gone = leaving.filter((l) => !byPath.has(l.path) && (l.parent === null || byPath.has(l.parent)));

  return (
    <Stack gap="md">
      <Group justify="space-between" wrap="nowrap" gap="md">
        <Group gap="xs" wrap="nowrap" miw={0}>
          <MachineIcon size={18} stroke={1.6} style={{ flex: "none", color: "var(--ows-muted)" }} />
          <Text fw={600} size="sm" style={{ flex: "none" }}>{machine === "here" && !machineName ? t("computer") : machineName}</Text>
          <Breadcrumbs separator={<IconChevronRight size={12} style={{ color: "var(--ows-muted)" }} />} separatorMargin={2} style={{ minWidth: 0, flexWrap: "wrap" }}>
            {(machine === "here" && windowsLike(selected) ? [{ label: "", path: "" }, ...trail] : trail).map((c) => (
              <UnstyledButton key={c.path || "root"} className="ows-fx-crumb" data-current={c.path === selected || undefined} aria-label={c.label || t("computer")} onClick={() => { select(c.path); if (root !== null && !inside(c.path, root)) void reroot(c.path); else showNode(c.path); }}>
                {c.label || <IconDeviceDesktop size={14} style={{ display: "block" }} />}
              </UnstyledButton>
            ))}
          </Breadcrumbs>
        </Group>
        <Group gap="sm" wrap="nowrap" style={{ flex: "none" }}>
          <TextInput size="xs" w={150} value={query} onChange={(e) => setQuery(e.currentTarget.value)} leftSection={<IconSearch size={14} />} aria-label={t("filter")} spellCheck={false} />
          <SegmentedControl size="xs" value={view} onChange={(v) => setView(v as "graph" | "list")} data={[
            { value: "graph", label: <Tooltip label={t("graph")}><IconSitemap size={16} style={{ display: "block", transform: "rotate(-90deg)" }} aria-label={t("graph")} /></Tooltip> },
            { value: "list", label: <Tooltip label={t("list")}><IconListTree size={16} style={{ display: "block" }} aria-label={t("list")} /></Tooltip> },
          ]} />
        </Group>
      </Group>

      {offline ? (
        <Stack className="ows-fx-canvas" align="center" justify="center" gap="sm" data-static>
          <MachineIcon size={28} stroke={1.4} style={{ color: "var(--ows-muted)" }} />
          <Text size="sm" c="dimmed">{t("offline")}</Text>
          <Button size="xs" variant="default" leftSection={<IconRefresh size={14} />} onClick={() => { cache.clear(); memory.delete(place); void start(); }}>{t("retry")}</Button>
        </Stack>
      ) : view === "graph" ? (
        <div ref={canvas} className="ows-fx-canvas" data-held={held || undefined} data-still={!settled || undefined} data-far={camera.k < ZOOM.far || undefined} onPointerDown={onPointerDown} onPointerMove={onPointerMove} onPointerUp={onPointerUp} onPointerCancel={onPointerUp} onWheel={onWheel}>
          {root === null && <Loader size="sm" className="ows-fx-wait" />}
          <div className="ows-fx-world" role="tree" aria-label={machineName} style={{ transform: `translate3d(${camera.x}px, ${camera.y}px, 0) scale(${camera.k})`, width, height }}>
            <svg className="ows-fx-links" width={Math.max(width, 1)} height={Math.max(height, 1)} aria-hidden>
              {gone.map((p) => link(p, true))}
              {placed.map((p) => link(p))}
            </svg>
            {gone.map((p) => (
              <div key={`${p.path}\u0000gone`} className="ows-fx-node" style={{ transform: `translate3d(${p.x}px, ${p.y}px, 0)`, width: W, height: H }}>
                {block(p, p.rank, true)}
              </div>
            ))}
            {placed.map((p) => (
              <div key={p.path} className="ows-fx-node" style={{ transform: `translate3d(${p.x}px, ${p.y}px, 0)`, width: W, height: H }}>
                {block(p, p.rank)}
              </div>
            ))}
          </div>
          <Group gap={4} className="ows-fx-tools">
            <Tooltip label={t("parent")}><ActionIcon variant="default" disabled={parentOfRoot === null} onClick={() => parentOfRoot !== null && void reroot(parentOfRoot)} aria-label={t("parent")}><IconArrowUp size={16} /></ActionIcon></Tooltip>
            <Tooltip label={t("recentre")}><ActionIcon variant="default" onClick={recentre} aria-label={t("recentre")}><IconFocusCentered size={16} /></ActionIcon></Tooltip>
            <Tooltip label={t("zoomOut")}><ActionIcon variant="default" onClick={() => zoomAt(1 / 1.25)} aria-label={t("zoomOut")}><IconZoomOut size={16} /></ActionIcon></Tooltip>
            <Tooltip label={t("zoomIn")}><ActionIcon variant="default" onClick={() => zoomAt(1.25)} aria-label={t("zoomIn")}><IconZoomIn size={16} /></ActionIcon></Tooltip>
          </Group>
        </div>
      ) : (
        <div className="ows-fx-canvas ows-fx-list" role="tree" aria-label={machineName} data-static>
          {order.map((item) => (
            <div key={item.path} className="ows-fx-row" style={{ ["--ows-fx-depth" as string]: item.depth }}>
              {block(item, byPath.get(item.path)?.rank ?? 0)}
            </div>
          ))}
        </div>
      )}

      <Group justify="space-between" wrap="nowrap" gap="md">
        <Group key={selected} gap="sm" wrap="nowrap" miw={0} className="ows-fx-detail">
          <Text size="sm" ff="monospace" truncate="start" title={selected}>{`\u200e${selected}\u200e`}</Text>
          {selected && (
            <CopyButton value={selected}>
              {({ copied, copy }) => (
                <Tooltip label={copied ? t("copied") : t("copy")}>
                  <ActionIcon variant="subtle" color="gray" size="sm" onClick={copy} aria-label={t("copy")}>{copied ? <IconCheck size={14} /> : <IconCopy size={14} />}</ActionIcon>
                </Tooltip>
              )}
            </CopyButton>
          )}
          {details.length > 0 && <Text size="sm" c="dimmed" style={{ flex: "none" }}>{details.join(" · ")}</Text>}
          {note && <Text size="sm" c="orange" style={{ flex: "none" }}>{note}</Text>}
        </Group>
        <Group gap="sm" wrap="nowrap" style={{ flex: "none" }}>
          <Button variant="default" onClick={onClose}>{t("cancel")}</Button>
          <Button disabled={!usable} onClick={() => choose(selected)}>{t(isFile ? "useFile" : "use")}</Button>
        </Group>
      </Group>
    </Stack>
  );
}
