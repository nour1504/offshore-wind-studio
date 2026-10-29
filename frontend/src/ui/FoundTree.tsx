/**
 * What a search found in a folder given by the user, drawn like the folder explorer: the folder,
 * then its subfolders, then their files, linked from left to right. It stays short whatever the
 * number of files: a folder with one subfolder and nothing else is one block (a/b), a folder with
 * many files shows them as one block (how many, the first and the last), and a folder with many
 * subfolders shows the first and last ones around a block that opens the others.
 */
import { Tooltip } from "@mantine/core";
import { IconDots, IconFile, IconFiles, IconFolder } from "@tabler/icons-react";
import { useMemo, useState } from "react";

import { defineMessages, useFormat, useT } from "../i18n";

export interface FoundFolder {
  /** Path from the root, with / ("" for the root itself) */
  path: string;
  files: number;
  bytes: number;
  /** Every name when they are few, else empty */
  names: string[];
  first: string;
  last: string;
}

export interface FoundSummary {
  root: string;
  files: number;
  bytes: number;
  folders: FoundFolder[];
}

const messages = defineMessages({
  en: {
    found: "Files found",
    files: "{n|# file|# files} · {size}",
    others: "{n|# other folder|# other folders}",
  },
  fr: {
    found: "Fichiers trouvés",
    files: "{n|# fichier|# fichiers} · {size}",
    others: "{n|# autre dossier|# autres dossiers}",
  },
});

// Sizes of the blocks and gaps, in pixels
const FOLDER_W = 190;
const FILE_W = 300;
const COLUMN = FILE_W + 48;
const H = 34;
const H_GROUP = 50;
const GAP_Y = 8;
// Subfolders shown before the others are gathered: the first ones, then the last ones
const SHOWN = { first: 3, last: 2 };

interface Folder {
  name: string;
  path: string;
  own: FoundFolder | null;
  children: Folder[];
}

type Item =
  | { kind: "folder"; key: string; folder: Folder }
  | { kind: "file"; key: string; name: string }
  | { kind: "group"; key: string; own: FoundFolder }
  | { kind: "others"; key: string; parent: string; count: number };

interface Placed {
  item: Item;
  x: number;
  y: number;
  w: number;
  h: number;
  parent: Placed | null;
}

/** The first and last names written once around what differs: gfs.{2025100100 → 2025100718}.f000.grib2 */
export function range(first: string, last: string): string {
  if (first === last) return first;
  let start = 0;
  while (start < first.length && first[start] === last[start]) start += 1;
  while (start > 0 && /[A-Za-z0-9]/.test(first[start - 1])) start -= 1;
  let end = 0;
  while (end < first.length - start && end < last.length - start && first[first.length - 1 - end] === last[last.length - 1 - end]) end += 1;
  while (end > 0 && /[A-Za-z0-9]/.test(first[first.length - end])) end -= 1;
  const middle = (name: string) => name.slice(start, name.length - end);
  return `${first.slice(0, start)}{${middle(first)} → ${middle(last)}}${first.slice(first.length - end)}`;
}

/** The folders as a hierarchy; a folder holding only one subfolder is merged with it (a/b). */
function hierarchy(summary: FoundSummary, unnamed: string): Folder {
  // No common folder (files on several Windows drives): the root is named by the caller
  const root: Folder = { name: summary.root.split(/[\\/]/).filter(Boolean).pop() || unnamed, path: "", own: null, children: [] };
  const byPath = new Map<string, Folder>([["", root]]);
  const folderOf = (path: string): Folder => {
    const known = byPath.get(path);
    if (known) return known;
    const cut = path.lastIndexOf("/");
    const parent = folderOf(cut < 0 ? "" : path.slice(0, cut));
    const made: Folder = { name: path.slice(cut + 1), path, own: null, children: [] };
    parent.children.push(made);
    byPath.set(path, made);
    return made;
  };
  for (const own of summary.folders) folderOf(own.path).own = own;
  const merge = (folder: Folder): Folder => {
    folder.children = folder.children.sort((a, b) => a.name.localeCompare(b.name)).map(merge);
    if (!folder.own && folder.children.length === 1) {
      const only = folder.children[0];
      return { ...only, name: `${folder.name}/${only.name}` };
    }
    return folder;
  };
  return merge(root);
}

export function FoundTree({ summary }: { summary: FoundSummary }) {
  const t = useT(messages);
  const f = useFormat();
  // Folders whose subfolders are all shown
  const [opened, setOpened] = useState<Set<string>>(() => new Set());

  const { placed, width, height } = useMemo(() => {
    const placed: Placed[] = [];
    let cursor = 0;
    let deepest = 0;
    const sizeOf = (item: Item) => ({ w: item.kind === "folder" || item.kind === "others" ? FOLDER_W : FILE_W, h: item.kind === "group" ? H_GROUP : H });
    const itemsOf = (folder: Folder): Item[] => {
      let children: Item[] = folder.children.map((child) => ({ kind: "folder", key: child.path, folder: child }));
      const hidden = children.length - SHOWN.first - SHOWN.last;
      if (hidden > 1 && !opened.has(folder.path)) {
        children = [...children.slice(0, SHOWN.first), { kind: "others", key: `${folder.path}\u0000others`, parent: folder.path, count: hidden }, ...children.slice(-SHOWN.last)];
      }
      const own = folder.own;
      const files: Item[] = !own ? [] : own.names.length ? own.names.map((name) => ({ kind: "file", key: `${folder.path}/${name}`, name })) : [{ kind: "group", key: `${folder.path}\u0000files`, own }];
      return [...children, ...files];
    };
    const place = (item: Item, depth: number, parent: Placed | null): Placed => {
      deepest = Math.max(deepest, depth);
      const { w, h } = sizeOf(item);
      const node: Placed = { item, x: depth * COLUMN, y: 0, w, h, parent };
      placed.push(node);
      const kids = item.kind === "folder" ? itemsOf(item.folder) : [];
      if (!kids.length) {
        node.y = cursor;
        cursor += h + GAP_Y;
        return node;
      }
      const placedKids = kids.map((kid) => place(kid, depth + 1, node));
      const top = placedKids[0].y + placedKids[0].h / 2;
      const last = placedKids[placedKids.length - 1];
      node.y = (top + last.y + last.h / 2) / 2 - h / 2;
      return node;
    };
    place({ kind: "folder", key: "", folder: hierarchy(summary, t("found")) }, 0, null);
    const top = Math.min(...placed.map((p) => p.y));
    for (const p of placed) p.y -= top;
    return { placed, width: deepest * COLUMN + FILE_W, height: Math.max(...placed.map((p) => p.y + p.h)) };
  }, [summary, opened, t]);

  const block = ({ item }: Placed) => {
    if (item.kind === "folder") {
      return (
        <div className="ows-fx-block" title={item.folder.path ? `${summary.root}/${item.folder.path}` : summary.root}>
          <IconFolder size={16} stroke={1.7} className="ows-fx-icon" />
          <span className="ows-fx-name">{item.folder.name}</span>
        </div>
      );
    }
    if (item.kind === "file") {
      return (
        <div className="ows-fx-block">
          <IconFile size={16} stroke={1.7} className="ows-fx-icon" />
          <span className="ows-fx-name ows-found-mono" title={item.name}>{item.name}</span>
        </div>
      );
    }
    if (item.kind === "group") {
      return (
        <Tooltip label={`${item.own.first} → ${item.own.last}`} openDelay={300} multiline maw={420}>
          <div className="ows-fx-block">
            <IconFiles size={16} stroke={1.7} className="ows-fx-icon" />
            <span className="ows-found-lines">
              <span className="ows-fx-name ows-num">{t("files", { n: item.own.files, size: f.bytes(item.own.bytes) })}</span>
              <span className="ows-fx-name ows-found-mono ows-found-range">{range(item.own.first, item.own.last)}</span>
            </span>
          </div>
        </Tooltip>
      );
    }
    const open = () => setOpened((current) => new Set(current).add(item.parent));
    return (
      <div className="ows-fx-block" role="button" tabIndex={0} data-action onClick={open} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), open())}>
        <IconDots size={16} stroke={1.7} className="ows-fx-icon" />
        <span className="ows-fx-name">{t("others", { n: item.count })}</span>
      </div>
    );
  };

  return (
    <div className="ows-found" aria-label={t("found")}>
      <div className="ows-found-world" style={{ width, height }}>
        <svg className="ows-fx-links" width={width} height={height} aria-hidden>
          {placed.map((p) => {
            if (!p.parent) return null;
            const x1 = p.parent.x + p.parent.w;
            const y1 = p.parent.y + p.parent.h / 2;
            const x2 = p.x;
            const y2 = p.y + p.h / 2;
            const bend = (x2 - x1) * 0.55;
            return <path key={p.item.key} className="ows-fx-edge" pathLength={1} d={`M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}`} />;
          })}
        </svg>
        {placed.map((p) => (
          <div key={p.item.key} className="ows-fx-node" style={{ transform: `translate3d(${p.x}px, ${p.y}px, 0)`, width: p.w, height: p.h }}>
            {block(p)}
          </div>
        ))}
      </div>
    </div>
  );
}
