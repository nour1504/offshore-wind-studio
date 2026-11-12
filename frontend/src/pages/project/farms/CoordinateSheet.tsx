/**
 * Turbine positions as a spreadsheet, one numbered row per turbine (name, latitude, longitude,
 * model; WGS 84). A pasted block is read by the server in the chosen coordinate system and written
 * here in degrees; a last empty row takes typing; only rows in view are drawn. The sheet keeps one
 * height, filled with blank rows; read only, it lists positions made another way.
 */
import { useElementSize } from "@mantine/hooks";
import { type ClipboardEvent, type KeyboardEvent } from "react";

import { useT } from "../../../i18n";
import { useRowsInView } from "../../../ui/rows";
import { farmMessages } from "./messages";

export type SheetRow = [string, string, string, string];
const EMPTY_ROW: SheetRow = ["", "", "", ""];

const ROW = 32;
const VIEW = 416;
const MARGIN = 8;

/** A number typed with a point or a comma */
const read = (text: string) => {
  const value = Number(text.trim().replace(/\s/g, "").replace(",", "."));
  return text.trim() && Number.isFinite(value) ? value : null;
};

/** What a row holds: a turbine, nothing, or something that is not one */
export function readRow(row: SheetRow, model: number): { lat: number; lon: number; type: number; name: string | null } | "empty" | "invalid" {
  if (row.every((cell) => !cell.trim())) return "empty";
  const lat = read(row[1]);
  const lon = read(row[2]);
  const type = row[3].trim() ? read(row[3]) : model;
  if (lat === null || lon === null || Math.abs(lat) > 90 || Math.abs(lon) > 180 || type === null || !Number.isInteger(type) || type < 1) return "invalid";
  return { lat, lon, type, name: row[0].trim().slice(0, 32) || null };
}

export function CoordinateSheet({ rows, model, onChange, onPasteBlock, readOnly = false }: {
  rows: SheetRow[];
  model: number;
  onChange?: (rows: SheetRow[]) => void;
  /** A block of several cells pasted at a row: the text to read, from that row on */
  onPasteBlock?: (text: string, row: number) => void;
  /** Positions shown, not typed, in the height left in the column */
  readOnly?: boolean;
}) {
  const t = useT(farmMessages);
  const { ref: scroll, height } = useElementSize();
  const view = readOnly && height > 0 ? height : VIEW;
  // Always one empty row at the end to type into
  const shown = readOnly || (rows.length && rows[rows.length - 1].every((cell) => !cell)) ? rows : [...rows, EMPTY_ROW];
  const count = shown.length;
  const { first, last, before, after, onScroll } = useRowsInView(count, ROW, view, MARGIN);
  const blank = Math.max(0, Math.floor(view / ROW) - count);

  const set = (r: number, c: number, value: string) => {
    const next = shown.map((row) => [...row] as SheetRow);
    next[r][c] = value;
    while (next.length && next[next.length - 1].every((cell) => !cell)) next.pop();
    onChange?.(next);
  };
  const focus = (r: number, c: number, sheet: HTMLElement | null) => {
    sheet?.querySelector<HTMLInputElement>(`input[data-cell="${r}:${c}"]`)?.focus();
  };
  const onKey = (event: KeyboardEvent<HTMLInputElement>, r: number, c: number) => {
    const sheet = event.currentTarget.closest<HTMLElement>(".ows-coords-scroll");
    const move = event.key === "Enter" || event.key === "ArrowDown" ? 1 : event.key === "ArrowUp" ? -1 : 0;
    if (!move) return;
    event.preventDefault();
    const target = Math.min(count - 1, Math.max(0, r + move));
    // A row out of view is drawn once scrolled to
    if (sheet && (target * ROW < sheet.scrollTop || (target + 1) * ROW > sheet.scrollTop + sheet.clientHeight - ROW)) sheet.scrollTop = Math.max(0, (target - 3) * ROW);
    requestAnimationFrame(() => focus(target, c, sheet));
  };
  const onPaste = (event: ClipboardEvent<HTMLInputElement>, r: number) => {
    const text = event.clipboardData.getData("text/plain");
    if (!/[\t\n;]/.test(text.trim())) return;
    event.preventDefault();
    onPasteBlock?.(text, r);
  };

  const heads = [t("sheet.name"), t("sheet.lat"), t("sheet.lon"), t("sheet.model")];
  return (
    <div className="ows-coords" data-read-only={readOnly || undefined}>
      <div className="ows-coords-row ows-coords-head" role="row">
        <span role="columnheader" aria-label="#" />
        {heads.map((head) => <span key={head} role="columnheader">{head}</span>)}
      </div>
      <div ref={scroll} className="ows-coords-scroll" style={readOnly ? undefined : { maxHeight: VIEW }} onScroll={onScroll} role="grid" aria-readonly={readOnly || undefined} aria-rowcount={count} aria-colcount={5}>
        {before > 0 && <div aria-hidden="true" style={{ height: before }} />}
        {shown.slice(first, last).map((row, k) => {
          const r = first + k;
          const state = readOnly ? "read" : readRow(row, model);
          return (
            <div key={r} className="ows-coords-row" role="row" aria-rowindex={r + 1} data-invalid={state === "invalid" || undefined}>
              <span className="ows-coords-number ows-num">{r + 1}</span>
              {row.map((cell, c) => readOnly ? <span key={c} role="gridcell" className="ows-coords-cell">{cell}</span> : (
                <input
                  key={c}
                  data-cell={`${r}:${c}`}
                  className="ows-coords-cell"
                  value={cell}
                  inputMode={c === 0 ? "text" : c === 3 ? "numeric" : "decimal"}
                  placeholder={c === 3 && r < count - 1 ? String(model) : undefined}
                  aria-label={`${heads[c]} ${r + 1}`}
                  spellCheck={false}
                  onChange={(event) => set(r, c, event.currentTarget.value)}
                  onKeyDown={(event) => onKey(event, r, c)}
                  onPaste={(event) => onPaste(event, r)}
                />
              ))}
            </div>
          );
        })}
        {after > 0 && <div aria-hidden="true" style={{ height: after }} />}
        {Array.from({ length: blank }, (_, k) => (
          <div
            key={`blank-${k}`}
            className="ows-coords-row"
            data-blank
            aria-hidden="true"
            onMouseDown={readOnly ? undefined : (event) => {
              event.preventDefault();
              const column = Number((event.target as HTMLElement).dataset.column ?? 0);
              focus(count - 1, column, event.currentTarget.parentElement);
            }}
          >
            <span />
            {EMPTY_ROW.map((_, c) => <span key={c} data-column={c} />)}
          </div>
        ))}
      </div>
    </div>
  );
}
