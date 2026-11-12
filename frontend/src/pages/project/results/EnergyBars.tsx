/**
 * Energy per hour, day or month as bars, one slot per period, scrolling under a fixed value axis
 * (drag, shift + wheel, scrollbar). Against a run without wakes, the pale twin behind each bar
 * shows the energy the wakes took. The bar under the pointer turns into a pill with its reading;
 * arrow keys move it.
 */
import { Box } from "@mantine/core";
import { useElementSize } from "@mantine/hooks";
import { type KeyboardEvent, type PointerEvent, useEffect, useMemo, useRef, useState } from "react";

import { parseUtc, useFormat, useLang } from "../../../i18n";
import { CHART_COLORS, CHART_MS, cssColor, Legend, type ReadPart, Readout, readText, stepReading, useMorph, useSeen } from "../../../ui/chart";
import { decimals, niceStep } from "../../../ui/ticks";

interface EnergyRow {
  time: string;
  main: number | null;
  reference?: number | null;
}

type Period = "hour" | "day" | "month";

// Width of one bar's slot (px): narrow for hours, wider for days and months
const SLOT: Record<Period, number> = { hour: 12, day: 26, month: 60 };
const HEIGHT = 300;
const TOP = 22;
const BOTTOM = 44;
const AXIS = 52;

export function EnergyBars({ rows, period, unit, labels }: { rows: EnergyRow[]; period: Period; unit: string; labels: { main: string; reference: string } }) {
  const f = useFormat();
  const { lang } = useLang();
  const { ref: box, width } = useElementSize();
  const [seenRef, seen] = useSeen<HTMLDivElement>();
  const scroller = useRef<HTMLDivElement>(null);
  const [hovered, setHovered] = useState<number | null>(null);
  const [scroll, setScroll] = useState({ left: 0, start: true, end: true });
  const withReference = rows.some((row) => typeof row.reference === "number");

  const view = Math.max(0, width - AXIS);
  const step = rows.length ? Math.max(SLOT[period], view / rows.length) : SLOT[period];
  const inner = Math.max(view, rows.length * step);
  const top = useMemo(() => Math.max(1e-9, ...rows.flatMap((row) => [row.main ?? 0, row.reference ?? 0])), [rows]);
  const tick = niceStep(top);
  const ceiling = Math.ceil(top / tick) * tick;
  const base = HEIGHT - BOTTOM;
  const plot = base - TOP;
  const y = (value: number) => base - (plot * value) / ceiling;
  const ticks = Array.from({ length: Math.round(ceiling / tick) + 1 }, (_, k) => k * tick);
  const bar = Math.max(3, Math.min(step * 0.64, 34));

  // Heights (px) grow from zero once in view, then morph towards other values
  const target = useMemo(() => rows.flatMap((row) => [(plot * Math.max(0, row.main ?? 0)) / ceiling, (plot * Math.max(0, row.reference ?? 0)) / ceiling]), [rows, plot, ceiling]);
  const morphed = useMorph(target, CHART_MS.bars, { grow: true, ready: seen });
  const heights = morphed.length === target.length ? morphed : target;

  const locale = lang === "fr" ? "fr-FR" : "en-GB";
  const formats = useMemo(() => ({
    day: new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", timeZone: "UTC" }),
    month: new Intl.DateTimeFormat(locale, { month: "short", year: "numeric", timeZone: "UTC" }),
    read: new Intl.DateTimeFormat(locale, period === "month" ? { month: "long", year: "numeric", timeZone: "UTC" } : { day: "numeric", month: "short", year: period === "day" ? "numeric" : undefined, timeZone: "UTC" }),
    clock: new Intl.DateTimeFormat(locale, { hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: "UTC" }),
  }), [locale, period]);
  const dates = useMemo(() => rows.map((row) => parseUtc(row.time)), [rows]);

  // Labels under the bars: days (and every 6 h) for hours, days (and months) for days, months
  const marks = dates.flatMap((date, k) => {
    const x = (k + 0.5) * step;
    if (period === "month") return [{ x, text: formats.month.format(date), strong: true }];
    if (period === "day") {
      const first = k === 0 || date.getUTCDate() === 1;
      if (first) return [{ x, text: formats.day.format(date), strong: true }];
      return step >= 22 ? [{ x, text: String(date.getUTCDate()), strong: false }] : [];
    }
    const hour = date.getUTCHours();
    if (hour === 0 || k === 0) return [{ x, text: formats.day.format(date), strong: true }];
    return hour % 6 === 0 && step * 6 >= 26 ? [{ x, text: String(hour).padStart(2, "0"), strong: false }] : [];
  });

  // Fading edges where there is more to see; the view starts at the beginning of the run
  const measure = () => {
    const el = scroller.current;
    if (el) setScroll({ left: el.scrollLeft, start: el.scrollLeft <= 1, end: el.scrollLeft + el.clientWidth >= el.scrollWidth - 1 });
  };
  useEffect(() => {
    scroller.current?.scrollTo({ left: 0 });
    measure();
  }, [rows, period, width]);

  // A mouse drags the bars sideways
  const drag = useRef<{ x: number; left: number } | null>(null);
  const onMove = (event: PointerEvent<SVGSVGElement>) => {
    if (drag.current || !rows.length) return;
    const x = event.clientX - event.currentTarget.getBoundingClientRect().left;
    setHovered(Math.max(0, Math.min(rows.length - 1, Math.floor(x / step))));
  };
  const onKey = (event: KeyboardEvent<SVGSVGElement>) => {
    if (!rows.length) return;
    const from = hovered ?? -1;
    const next = stepReading(event.key, from, rows.length);
    if (next === undefined) return;
    event.preventDefault();
    setHovered(next);
    // The bar read stays in view
    if (next !== null && scroller.current) {
      const el = scroller.current;
      const x = (next + 0.5) * step;
      if (x < el.scrollLeft + step || x > el.scrollLeft + el.clientWidth - step) el.scrollLeft = x - el.clientWidth / 2;
    }
  };

  // Under the pointer: the period, then the value (and the value without wakes), the unit once
  const reading = (k: number): ReadPart[] => {
    const row = rows[k];
    const when = period === "hour" ? `${formats.read.format(dates[k])} ${formats.clock.format(dates[k])}` : formats.read.format(dates[k]);
    const value = (v: number | null | undefined, last: boolean) => `${f.number(v ?? null, 1)}${last ? ` ${unit}` : ""}`;
    return [
      { text: `${when} ·` },
      { text: value(row.main, !withReference), dot: withReference ? cssColor(CHART_COLORS.main) : undefined },
      ...(withReference ? [{ text: value(row.reference, true), dot: cssColor(CHART_COLORS.reference) }] : []),
    ];
  };
  const read = hovered === null || hovered >= rows.length ? null : { k: hovered, parts: reading(hovered) };

  return (
    <Box ref={seenRef} className="ows-chart ows-bars" role="figure" aria-label={labels.main}>
      {withReference && <Legend keys={[{ label: labels.main, color: cssColor(CHART_COLORS.main) }, { label: labels.reference, color: cssColor(CHART_COLORS.reference), pale: true }]} />}
      <Box ref={box} pos="relative" style={{ display: "flex" }}>
        <svg width={AXIS} height={HEIGHT} aria-hidden className="ows-axis" style={{ flex: "none", display: "block" }}>
          <text x={AXIS - 6} y={TOP - 10} textAnchor="end">{unit}</text>
          {ticks.map((value) => (
            <text key={value} x={AXIS - 6} y={y(value) + 3} textAnchor="end">{f.number(value, decimals(tick))}</text>
          ))}
        </svg>
        <div ref={scroller} className="ows-bars-scroll" data-start={scroll.start || undefined} data-end={scroll.end || undefined}
          onScroll={() => { measure(); setHovered(null); }}
          onPointerDown={(event) => { if (event.pointerType === "mouse" && scroller.current) { drag.current = { x: event.clientX, left: scroller.current.scrollLeft }; } }}
          onPointerMove={(event) => { if (drag.current && scroller.current && event.buttons === 1) scroller.current.scrollLeft = drag.current.left - (event.clientX - drag.current.x); }}
          onPointerUp={() => { drag.current = null; }} onPointerLeave={() => { drag.current = null; setHovered(null); }}>
          <svg width={inner} height={HEIGHT} style={{ display: "block" }} tabIndex={0} aria-label={read ? readText(read.parts) : labels.main}
            onPointerMove={onMove} onKeyDown={onKey} onBlur={() => setHovered(null)}>
            <g className="ows-axis">
              {ticks.map((value) => <line key={value} x1={0} x2={inner} y1={y(value)} y2={y(value)} />)}
              {marks.map((mark) => (
                <text key={`${mark.x}`} x={mark.x} y={HEIGHT - BOTTOM + (mark.strong ? 30 : 16)} textAnchor="middle" fontWeight={mark.strong ? 700 : undefined}>{mark.text}</text>
              ))}
            </g>
            {rows.map((row, k) => {
              const main = heights[2 * k] ?? 0;
              const reference = heights[2 * k + 1] ?? 0;
              const x = (k + 0.5) * step - bar / 2;
              const hot = k === hovered;
              return (
                <g key={row.time}>
                  {withReference && reference > 0 && <rect className="ows-bar-pale" x={x} y={base - reference} width={bar} height={reference} rx={2} />}
                  {main > 0 && <rect className="ows-bar" data-hot={hot || undefined} x={x} y={base - main} width={bar} height={main} rx={hot ? bar * 0.32 : 2} />}
                </g>
              );
            })}
            {read && (
              <Readout x={(read.k + 0.5) * step} y={y(Math.max(rows[read.k].main ?? 0, rows[read.k].reference ?? 0)) + 4} parts={read.parts}
                left={Math.max(0, scroll.left)} right={Math.min(inner, scroll.left + view)} />
            )}
          </svg>
        </div>
      </Box>
    </Box>
  );
}
