/**
 * Where the part seen lies in the period: a thin time line from D to F with its months (or its
 * years over a long period), the part seen drawn on it as a window that can be dragged; a click
 * elsewhere on the line moves there, keeping the length seen.
 */
import { Box } from "@mantine/core";
import { useElementSize } from "@mantine/hooks";
import { useRef } from "react";

import { useLang } from "../../../../i18n";
import type { Stairs } from "./model";
import type { Limits, Range } from "./view";

const TRACK = 8;
const HEIGHT = 34;

export function PeriodBar({ stairs, range, limits, onJump, onMove, label }: { stairs: Stairs; range: Range; limits: Limits; onJump: (range: Range) => void; onMove: (range: Range) => void; label: string }) {
  const { lang } = useLang();
  const { ref, width } = useElementSize();
  const drag = useRef<{ x: number; range: Range } | null>(null);
  const x = (hours: number) => (hours / limits.span) * width;
  const hours = (px: number) => (px / Math.max(1, width)) * limits.span;
  const marks = stairs.months.length <= 36 ? stairs.months : stairs.years;
  const monthly = marks === stairs.months;
  const name = (time: number) => monthly
    ? new Intl.DateTimeFormat(lang, { month: "short", timeZone: "UTC" }).format(new Date(time)).replace(".", "")
    : String(new Date(time).getUTCFullYear());
  // Labels only where they fit
  const every = Math.max(1, Math.ceil(34 / Math.max(1, width / Math.max(1, marks.length))));
  const length = range.t1 - range.t0;
  const whole = length >= limits.span - 1e-6;
  const left = x(range.t0);
  const seen = Math.max(6, x(range.t1) - left);
  const top = 4;

  const down = (event: React.PointerEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const px = event.clientX - rect.left;
    event.currentTarget.setPointerCapture(event.pointerId);
    if (px >= left - 4 && px <= left + seen + 4) {
      drag.current = { x: px, range };
      return;
    }
    const middle = hours(px);
    onMove({ t0: middle - length / 2, t1: middle + length / 2 });
  };
  const move = (event: React.PointerEvent<SVGSVGElement>) => {
    if (!drag.current) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const by = hours(event.clientX - rect.left - drag.current.x);
    onJump({ t0: drag.current.range.t0 + by, t1: drag.current.range.t1 + by });
  };
  const up = () => { drag.current = null; };

  return (
    <Box ref={ref} className="ows-period-bar" style={{ width: "100%", height: HEIGHT }}>
      {width > 0 && (
        <svg width={width} height={HEIGHT} role="slider" aria-label={label} aria-valuemin={0} aria-valuemax={Math.round(limits.span)} aria-valuenow={Math.round(range.t0)}
          onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}
          style={{ display: "block", touchAction: "none", cursor: whole ? "default" : "pointer", overflow: "visible" }}>
          <rect x={0} y={top} width={width} height={TRACK} rx={TRACK / 2} fill="var(--ows-subtle)" stroke="var(--ows-border)" />
          {marks.map((mark, n) => {
            const at = x(mark.x0);
            return (
              <g key={mark.key}>
                {n > 0 && <line x1={at} x2={at} y1={top} y2={top + TRACK} stroke="var(--ows-border-strong)" strokeWidth={1} />}
                {n % every === 0 && <text x={(at + x(mark.x1)) / 2} y={top + TRACK + 15} fontSize={10.5} textAnchor="middle" fill="var(--ows-muted)">{name(mark.time)}</text>}
              </g>
            );
          })}
          {!whole && (
            <rect className="ows-period-seen" x={left} y={top - 3} width={seen} height={TRACK + 6} rx={4}
              fill="color-mix(in srgb, var(--mantine-primary-color-filled) 22%, transparent)" stroke="var(--mantine-primary-color-filled)" strokeWidth={1.5} style={{ cursor: "grab" }} />
          )}
        </svg>
      )}
    </Box>
  );
}
