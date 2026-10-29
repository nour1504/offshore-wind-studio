/**
 * Energy per hour, day or month as bars, however long the run: one slot per period, the axis of
 * values fixed on the left and the bars scrolling under it (drag, shift + wheel, scrollbar), the
 * edges fading where there is more to see. With a run without wakes, each bar stands in front of
 * its pale twin: the pale top is the energy the wakes took. The bars rise once, from left to
 * right, when the period changes; the bar under the pointer stands out with its values.
 */
import { Box, Group, Text } from "@mantine/core";
import { useElementSize } from "@mantine/hooks";
import { useEffect, useMemo, useRef, useState } from "react";

import { parseUtc, useFormat, useLang } from "../../../i18n";
import { decimals, niceStep } from "../analyses/Charts";
import { cssColor, CHART_COLORS } from "./TimeChart";

export interface EnergyRow {
  time: string;
  main: number | null;
  reference?: number | null;
}

type Period = "hour" | "day" | "month";

// Width of one bar's slot (px): narrow for hours, wider for days and months
const SLOT: Record<Period, number> = { hour: 12, day: 26, month: 60 };
const HEIGHT = 300;
const TOP = 12;
const BOTTOM = 44;
const AXIS = 52;

export function EnergyBars({ rows, period, unit, labels }: { rows: EnergyRow[]; period: Period; unit: string; labels: { main: string; reference: string } }) {
  const f = useFormat();
  const { lang } = useLang();
  const { ref: box, width } = useElementSize();
  const scroller = useRef<HTMLDivElement>(null);
  const [hovered, setHovered] = useState<number | null>(null);
  const [edges, setEdges] = useState({ start: true, end: true });
  const withReference = rows.some((row) => typeof row.reference === "number");

  const view = Math.max(0, width - AXIS);
  const step = rows.length ? Math.max(SLOT[period], view / rows.length) : SLOT[period];
  const inner = Math.max(view, rows.length * step);
  const top = useMemo(() => Math.max(1e-9, ...rows.flatMap((row) => [row.main ?? 0, row.reference ?? 0])), [rows]);
  const tick = niceStep(top);
  const ceiling = Math.ceil(top / tick) * tick;
  const y = (value: number) => TOP + (HEIGHT - TOP - BOTTOM) * (1 - value / ceiling);
  const ticks = Array.from({ length: Math.round(ceiling / tick) + 1 }, (_, k) => k * tick);
  const bar = Math.max(3, Math.min(step * 0.62, 34));

  const locale = lang === "fr" ? "fr-FR" : "en-GB";
  const formats = useMemo(() => ({
    day: new Intl.DateTimeFormat(locale, { day: "numeric", month: "short", timeZone: "UTC" }),
    month: new Intl.DateTimeFormat(locale, { month: "short", year: "numeric", timeZone: "UTC" }),
    full: new Intl.DateTimeFormat(locale, period === "month" ? { month: "long", year: "numeric", timeZone: "UTC" } : period === "day" ? { weekday: "short", day: "numeric", month: "long", year: "numeric", timeZone: "UTC" } : { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: "UTC" }),
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
    if (el) setEdges({ start: el.scrollLeft <= 1, end: el.scrollLeft + el.clientWidth >= el.scrollWidth - 1 });
  };
  useEffect(() => {
    scroller.current?.scrollTo({ left: 0 });
    measure();
  }, [rows, period, width]);

  // A mouse drags the bars sideways
  const drag = useRef<{ x: number; left: number } | null>(null);

  const shown = hovered === null ? null : rows[hovered];
  const tipX = hovered === null ? 0 : AXIS + (hovered + 0.5) * step - (scroller.current?.scrollLeft ?? 0);
  const tipLeft = Math.min(Math.max(tipX, AXIS + 90), Math.max(AXIS + 90, width - 90));

  return (
    <Box ref={box} className="ows-bars" role="figure" aria-label={labels.main}>
      {withReference && (
        <Group justify="flex-end" gap="lg" mb={8}>
          <Group gap={6}><span className="ows-bars-key" style={{ background: cssColor(CHART_COLORS.main) }} /><Text size="xs" fw={600}>{labels.main}</Text></Group>
          <Group gap={6}><span className="ows-bars-key ows-bars-key-pale" style={{ background: cssColor(CHART_COLORS.reference) }} /><Text size="xs" fw={600}>{labels.reference}</Text></Group>
        </Group>
      )}
      <Box pos="relative" style={{ display: "flex" }}>
        <svg width={AXIS} height={HEIGHT} aria-hidden style={{ flex: "none", display: "block" }}>
          {ticks.map((value) => (
            <text key={value} x={AXIS - 8} y={y(value) + 4} textAnchor="end" fontSize={12} fill="var(--ows-muted)" className="ows-num">{f.number(value, decimals(tick))}</text>
          ))}
          <text transform={`translate(12 ${(HEIGHT - BOTTOM) / 2}) rotate(-90)`} textAnchor="middle" fontSize={12} fill="var(--ows-muted)">{unit}</text>
        </svg>
        <div ref={scroller} className="ows-bars-scroll" data-start={edges.start || undefined} data-end={edges.end || undefined}
          onScroll={() => { measure(); setHovered(null); }}
          onPointerDown={(event) => { if (event.pointerType === "mouse" && scroller.current) { drag.current = { x: event.clientX, left: scroller.current.scrollLeft }; } }}
          onPointerMove={(event) => { if (drag.current && scroller.current && event.buttons === 1) scroller.current.scrollLeft = drag.current.left - (event.clientX - drag.current.x); }}
          onPointerUp={() => { drag.current = null; }} onPointerLeave={() => { drag.current = null; setHovered(null); }}>
          <svg width={inner} height={HEIGHT} style={{ display: "block" }}>
            {ticks.map((value) => <line key={value} x1={0} x2={inner} y1={y(value)} y2={y(value)} stroke="var(--ows-border)" />)}
            <g key={`${period}:${rows.length}`} className="ows-bars-grow" data-hovering={hovered !== null || undefined}>
              {rows.map((row, k) => {
                const x = (k + 0.5) * step - bar / 2;
                const delay = `${Math.round(Math.min(1, ((k + 0.5) * step) / Math.max(1, view)) * 380)}ms`;
                return (
                  <g key={row.time} data-lit={hovered === k || undefined} style={{ animationDelay: delay }} onPointerEnter={() => setHovered(k)}>
                    <rect x={(k * step)} y={TOP} width={step} height={HEIGHT - TOP - BOTTOM} fill="transparent" />
                    {typeof row.reference === "number" && row.reference > 0 && (
                      <rect x={x} y={y(row.reference)} width={bar} height={y(0) - y(row.reference)} rx={Math.min(3, bar / 3)} fill={cssColor(CHART_COLORS.reference)} opacity={0.32} />
                    )}
                    {typeof row.main === "number" && row.main > 0 && (
                      <rect x={x} y={y(row.main)} width={bar} height={y(0) - y(row.main)} rx={Math.min(3, bar / 3)} fill={cssColor(CHART_COLORS.main)} />
                    )}
                  </g>
                );
              })}
            </g>
            <line x1={0} x2={inner} y1={y(0)} y2={y(0)} stroke="var(--ows-border-strong)" />
            {marks.map((mark) => (
              <text key={`${mark.x}`} x={mark.x} y={HEIGHT - BOTTOM + (mark.strong ? 30 : 16)} textAnchor="middle" fontSize={mark.strong ? 12 : 11} fontWeight={mark.strong ? 600 : 400} fill={mark.strong ? "currentColor" : "var(--ows-muted)"} className="ows-num">{mark.text}</text>
            ))}
          </svg>
        </div>
        {shown && (
          <div className="ows-bars-tip" style={{ left: tipLeft }}>
            <Text size="xs" fw={600} mb={4}>{formats.full.format(dates[hovered as number])} UTC</Text>
            <Group justify="space-between" gap="md" wrap="nowrap"><Text size="xs" c="dimmed">{labels.main}</Text><Text size="xs" fw={600} className="ows-num">{shown.main === null ? "–" : `${f.number(shown.main, 1)} ${unit}`}</Text></Group>
            {withReference && <Group justify="space-between" gap="md" wrap="nowrap"><Text size="xs" c="dimmed">{labels.reference}</Text><Text size="xs" fw={600} className="ows-num">{typeof shown.reference === "number" ? `${f.number(shown.reference, 1)} ${unit}` : "–"}</Text></Group>}
          </div>
        )}
      </Box>
    </Box>
  );
}
