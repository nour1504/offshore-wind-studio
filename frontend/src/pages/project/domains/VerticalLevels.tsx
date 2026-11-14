/**
 * The vertical grid: real.exe's automatic levels (auto_levels_opt = 2) or typed eta_levels, the
 * levels they give (server, as real.exe: core/method/vertical.py), the rotors and tslist profiles.
 * The checks (core/method/vertical_advice.py) advise, with reason, source and a verified correction
 * when there is one.
 */
import { Button, Group, SegmentedControl, Stack, Table, Text, Textarea } from "@mantine/core";
import { IconAlertTriangle } from "@tabler/icons-react";
import { useDebouncedValue, useElementSize } from "@mantine/hooks";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { type PointerEvent, type ReactNode, useEffect, useId, useState, useSyncExternalStore } from "react";

import { post } from "../../../api/client";
import type { Case } from "../../../api/types";
import { defineMessages, useFormat, useT } from "../../../i18n";
import { Fold } from "../../../ui/Fold";
import { ExampleFile } from "../../../ui/ExampleFile";
import { FieldLabel, NumberField } from "../../../ui/Inputs";
import { Stat, StatGrid } from "../../../ui/Stat";
import { QueryView } from "../../../ui/States";
import { levelColour } from "./levelColour";
import { levelHover } from "./levelHover";

export interface VerticalAnswer {
  error: string | null;
  levels: { number: number; eta: number; height_m: number; dz_m: number }[];
  mass_heights_m: number[];
  top_m?: number;
  turbines: { type: number; name: string; count: number; hub_height_m: number; rotor_diameter_m: number; levels_in_rotor: number }[];
  time_series_levels?: number | null;
  time_series_top_m?: number | null;
  /** Checks of the settings (core/method/vertical_advice.py): why, the source, a verified correction */
  checks?: Check[];
}

interface Check {
  key: "real" | "rotor";
  ok: boolean;
  message: string;
  source: string;
  detail: string;
  changes: Partial<Record<"e_vert" | "p_top_requested" | "dzbot" | "dzstretch_s" | "dzstretch_u" | "max_dz", number>> | null;
}

const messages = defineMessages({
  en: {
    title: "Vertical levels",
    levels: "Levels",
    levelsInfo: "e_vert: number of full levels.",
    top: "Top",
    topInfo: "p_top_requested: pressure at the top of the model. The input data must reach it.",
    dzbot: "1st layer thickness",
    dzbotInfo: "dzbot: between the ground and the 2nd full level.",
    stretchS: "Stretching",
    stretchSInfo: "dzstretch_s: thickness ratio between two successive layers near the ground.",
    stretchU: "Stretching aloft",
    stretchUInfo: "dzstretch_u: same ratio higher up, above max_dz / 2.",
    maxDz: "Thickest layer",
    maxDzInfo: "max_dz: real.exe stops if an upper layer exceeds 1.5 times this value.",
    whole: "Column",
    upTo: "Up to",
    table: "Levels",
    number: "Level",
    eta: "eta",
    height: "Height (m)",
    dz: "Thickness (m)",
    summary: "{n} levels · {p} hPa",
    column: "Vertical levels and turbine rotor heights",
    firstLevel: "1st mass level",
    firstLevelInfo: "Wind, temperature",
    inRotor: "Levels in the rotor",
    reading: "level {n} · {h} m",
    shown: "Whole column",
    groupTop: "Top of the column",
    groupAloft: "Aloft",
    groupGround: "Near the ground",
    scale: "Pressure and height of the top",
    apply: "Apply",
    source: "Source: {source}",
    mode: "Levels computed",
    automatic: "Automatic",
    byHand: "By hand",
    modeInfo: "Automatic: real.exe computes the levels (auto_levels_opt = 2). Manual: full eta levels typed in, from 1 at the ground to 0 at the top.",
    etaLevels: "Levels (eta)",
    etaInfo: "One value per line, or separated by commas or spaces. From 1 (ground) to 0 (top), strictly decreasing.",
    fromAutomatic: "Start from the automatic levels",
    etaCount: "{n|# level|# levels}",
  },
  fr: {
    title: "Niveaux verticaux",
    levels: "Niveaux",
    levelsInfo: "e_vert : nombre de niveaux pleins.",
    top: "Sommet",
    topInfo: "p_top_requested : pression au sommet du modèle. Les données d'entrée doivent l'atteindre.",
    dzbot: "Épaisseur 1re couche",
    dzbotInfo: "dzbot : du sol au 2e niveau complet.",
    stretchS: "Étirement",
    stretchSInfo: "dzstretch_s : rapport d'épaisseur entre deux couches successives près du sol.",
    stretchU: "Étirement en altitude",
    stretchUInfo: "dzstretch_u : même rapport plus haut, au-delà de max_dz / 2.",
    maxDz: "Couche la plus épaisse",
    maxDzInfo: "max_dz : real.exe s'arrête si une couche haute dépasse 1,5 fois cette valeur.",
    whole: "Colonne",
    upTo: "Jusqu'à",
    table: "Niveaux",
    number: "Niveau",
    eta: "eta",
    height: "Hauteur (m)",
    dz: "Épaisseur (m)",
    summary: "{n} niveaux · {p} hPa",
    column: "Niveaux verticaux et hauteurs des rotors",
    firstLevel: "1er niveau de masse",
    firstLevelInfo: "Vent, température",
    inRotor: "Niveaux dans le rotor",
    reading: "niveau {n} · {h} m",
    shown: "Colonne entière",
    groupTop: "Haut de la colonne",
    groupAloft: "En altitude",
    groupGround: "Près du sol",
    scale: "Pression et altitude du sommet",
    apply: "Appliquer",
    source: "Source : {source}",
    mode: "Calcul des niveaux",
    automatic: "Automatiques",
    byHand: "À la main",
    modeInfo: "Automatique : real.exe calcule les niveaux (auto_levels_opt = 2). Manuel : niveaux eta pleins saisis, de 1 au sol à 0 au sommet.",
    etaLevels: "Niveaux (eta)",
    etaInfo: "Une valeur par ligne, ou séparées par des virgules ou des espaces. De 1 (sol) à 0 (sommet), strictement décroissantes.",
    fromAutomatic: "Partir des niveaux automatiques",
    etaCount: "{n|# niveau|# niveaux}",
  },
});

export function useVertical(draft: Case) {
  const [debounced] = useDebouncedValue(draft, 300);
  return useQuery({
    queryKey: ["method-vertical", debounced.grid, debounced.dynamics, debounced.namelist_input, debounced.turbine_types, debounced.farms, debounced.time_series],
    queryFn: () => post<VerticalAnswer>("/api/method/vertical", debounced),
    retry: false,
    placeholderData: keepPreviousData,
  });
}

const PROFILE_WIDTH = 340;
// Pressure (hPa) and height (km) of the standard atmosphere, for the scale of the top: marks at
// even steps of the logarithm of the pressure
const SCALE_TICKS: [number, number][] = [[1000, 0], [300, 9.2], [100, 16.2], [30, 23.8], [10, 31.1], [3, 39.7], [1, 48]];

/** Height (km) of a pressure (hPa) in the standard atmosphere, between the marks of the scale. */
function standardHeight(hpa: number): number {
  const p = Math.min(1000, Math.max(1, hpa));
  const n = Math.max(1, SCALE_TICKS.findIndex(([mark]) => mark <= p));
  const [p0, h0] = SCALE_TICKS[n - 1], [p1, h1] = SCALE_TICKS[n];
  return h0 + ((h1 - h0) * Math.log(p0 / p)) / Math.log(p0 / p1);
}

/** A scale of the top: pressures above the line, heights under it, higher pressure on the left
    being lower in the air (positions by the logarithm of the pressure, as heights nearly are), the
    same room left on both sides. The chosen top is marked, its pressure and its height written at
    its mark with their units, which name the two lines. */
function TopScale({ hpa, width = PROFILE_WIDTH }: { hpa: number; width?: number }) {
  const t = useT(messages);
  const f = useFormat();
  const inset = 26;
  const x = (p: number) => inset + (Math.log(1000 / Math.min(1000, Math.max(1, p))) / Math.log(1000)) * (width - 2 * inset);
  const marker = x(hpa);
  // A mark too close to the chosen value leaves its place to it
  const clear = (p: number) => Math.abs(x(p) - marker) > 42;
  return (
    <svg width={width} height={80} role="img" aria-label={t("scale")} className="ows-num" fontSize={12} style={{ display: "block", overflow: "visible" }}>
      <line x1={inset} x2={width - inset} y1={40} y2={40} stroke="var(--mantine-color-dimmed)" strokeOpacity={0.6} />
      <rect x={inset} y={37} width={Math.max(0, marker - inset)} height={6} rx={3} fill="var(--mantine-primary-color-filled)" opacity={0.35} />
      {SCALE_TICKS.map(([p, km]) => (
        <g key={p} fill="var(--mantine-color-dimmed)" textAnchor="middle">
          <line x1={x(p)} x2={x(p)} y1={34} y2={46} stroke="var(--mantine-color-dimmed)" strokeOpacity={0.7} />
          {clear(p) && <text x={x(p)} y={16}>{f.number(p, 0)}</text>}
          {clear(p) && <text x={x(p)} y={72}>{f.number(km, 0)}</text>}
        </g>
      ))}
      <g fill="var(--mantine-color-text)" fontWeight={700} textAnchor="middle">
        <line x1={marker} x2={marker} y1={26} y2={54} stroke="var(--mantine-primary-color-filled)" strokeWidth={2.4} strokeLinecap="round" />
        <text x={marker} y={16}>{`${f.number(hpa, hpa < 10 ? 1 : 0)} hPa`}</text>
        <text x={marker} y={72}>{`${f.number(standardHeight(hpa), 1)} km`}</text>
      </g>
    </svg>
  );
}

type Changes = NonNullable<Check["changes"]>;

/** The problems only (nothing when all is well): why, its source in the tooltip, and a verified correction to apply. */
function Problems({ checks, onApply }: { checks: Check[]; onApply: (changes: Changes) => void }) {
  const t = useT(messages);
  const f = useFormat();
  // The correction in keywords: "33 niveaux", "1re couche 10 m · étirement 1,15"
  const values: Record<string, (v: number) => string> = {
    e_vert: (v) => `${f.number(v, 0)} ${t("levels").toLowerCase()}`,
    p_top_requested: (v) => `${t("top").toLowerCase()} ${f.number(v / 100, 0)} hPa`,
    dzbot: (v) => `${t("dzbot").toLowerCase()} ${f.number(v, 0)} m`,
    dzstretch_s: (v) => `${t("stretchS").toLowerCase()} ${f.number(v, 2)}`,
    dzstretch_u: (v) => `${t("stretchU").toLowerCase()} ${f.number(v, 2)}`,
    max_dz: (v) => `${t("maxDz").toLowerCase()} ${f.number(v, 0)} m`,
  };
  const correction = (changes: Changes) => Object.entries(changes).map(([key, value]) => values[key]?.(value as number) ?? key).join(" · ");
  const problems = checks.filter((c) => !c.ok);
  if (!problems.length) return null;
  return (
    <Stack gap="sm">
      {problems.map((check) => (
        <Group key={check.key} gap={8} wrap="nowrap" align="flex-start">
          {check.key === "real" && <IconAlertTriangle size={18} color="var(--mantine-color-red-6)" style={{ flexShrink: 0, marginTop: 1 }} />}
          <Text size="sm" style={{ flex: 1, minWidth: 0 }} c={check.key === "real" ? "red" : undefined}>
            <FieldLabel label={check.changes ? `${check.message} → ${correction(check.changes)}` : check.message} info={[check.detail, t("source", { source: check.source })].filter(Boolean).join(" — ")} />
          </Text>
          {check.changes && <Button size="compact-xs" variant="default" onClick={() => onApply(check.changes!)} style={{ flexShrink: 0 }}>{t("apply")}</Button>}
        </Group>
      ))}
    </Stack>
  );
}

/** Levels typed by hand: the eta values, read when the field is left. */
function TypedLevels({ levels, automatic, onLevels }: { levels: number[]; automatic: number[]; onLevels: (levels: number[]) => void }) {
  const t = useT(messages);
  const [text, setText] = useState(levels.join("\n"));
  useEffect(() => setText(levels.join("\n")), [levels]);
  const read = (value: string) => value.split(/\r?\n/).filter((line) => !line.trim().startsWith("#")).join(" ").split(/[\s,;]+/).filter(Boolean).map(Number).filter(Number.isFinite);
  return (
    <Stack gap={6}>
      <Textarea label={<FieldLabel label={t("etaLevels")} info={t("etaInfo")} />} autosize minRows={6} maxRows={14} value={text} onChange={(e) => setText(e.currentTarget.value)} onBlur={() => { const values = read(text); if (values.length >= 3) onLevels(values); }} styles={{ input: { fontFamily: "var(--mantine-font-family-monospace)", fontSize: 13 } }} />
      <Group gap="xs" justify="space-between">
        <Text size="xs" c="dimmed">{t("etaCount", { n: levels.length })}</Text>
        <Group gap="xs">
          {automatic.length > 2 && <Button size="compact-xs" variant="default" onClick={() => onLevels(automatic)}>{t("fromAutomatic")}</Button>}
          <ExampleFile files={["niveaux-eta.txt"]} onUse={(value) => { const values = read(value); if (values.length >= 3) onLevels(values); }} />
        </Group>
      </Group>
    </Stack>
  );
}

/** Settings that act on the same part of the column, side by side under its name, and what
    shows them (`under`) as wide as the two. */
function Settings({ title, children, under }: { title: string; children: ReactNode; under?: ReactNode }) {
  return (
    <div className="ows-vertical-group">
      <span className="ows-vertical-title">{title}</span>
      <div className="ows-vertical-pair">{children}</div>
      {under}
    </div>
  );
}

/** The setting being typed, and the layers it acts on (a layer by its place from the ground and
    its thickness, in metres). */
type Setting = "top" | "maxDz" | "stretchU" | "dzbot" | "stretchS";
const ACTS: Record<Setting, (layer: number, dz: number, maxDz: number, last: number) => boolean> = {
  top: (layer, _dz, _maxDz, last) => layer === last,
  maxDz: (_layer, dz, maxDz) => dz >= maxDz * 0.999,
  stretchU: (_layer, dz, maxDz) => dz >= maxDz / 2 && dz < maxDz * 0.999,
  dzbot: (layer) => layer === 0,
  stretchS: (_layer, dz, maxDz) => dz < maxDz / 2,
};
/** The height shown that suits a setting: the whole column for those of the top, the first kilometre for those of the ground. */
const RANGE_OF: Record<Setting, string> = { top: "all", maxDz: "all", stretchU: "all", dzbot: "1000", stretchS: "1000" };

/** Heights offered for the drawing besides the whole column, in metres */
const RANGES = ["1000", "5000"];

/** The levels to scale: one line per level (low to high as in the 3D views, those crossed by a
 * rotor in orange), round heights on the left up to the height shown, which is the top of the
 * drawing, each turbine model at its height, and on the right the whole column with the part
 * shown. The level nearest the pointer is read anywhere on the drawing; the layers a setting acts
 * on (`acts`) light up. Another height shown slides everything to its new place. */
function Profile({ data, ceiling, modelTop, acts, width, height }: { data: VerticalAnswer; ceiling: number; modelTop: number; acts: ((layer: number, dz: number) => boolean) | null; width: number; height: number }) {
  const f = useFormat();
  const t = useT(messages);
  const clip = useId();
  const hovered = useSyncExternalStore(levelHover.subscribe, levelHover.get);
  const left = 52;
  // The whole column stands on the right, a gap away from the levels
  const column = { x: width - 12, width: 10 };
  const right = column.x - 16;
  const top = 10;
  // The ground on the bottom edge, level with the last field beside it
  const bottom = height - 1;
  const scale = (bottom - top) / ceiling;
  const y = (z: number) => bottom - z * scale;
  const at = (z: number) => ({ transform: `translateY(${y(z)}px)` });
  const levels = data.levels;
  const rotors = data.turbines.map((turbine) => ({ ...turbine, low: turbine.hub_height_m - turbine.rotor_diameter_m / 2, high: turbine.hub_height_m + turbine.rotor_diameter_m / 2 }));
  const inRotor = (z: number) => rotors.some((r) => z >= r.low && z <= r.high);
  // A level just above or below a rotor bounds a layer crossed by it: orange too
  const crossed = new Set<number>();
  levels.forEach((level, n) => {
    const above = levels[n + 1]?.height_m ?? Infinity;
    if (rotors.some((r) => level.height_m < r.high && above > r.low)) {
      crossed.add(level.number);
      if (levels[n + 1]) crossed.add(levels[n + 1].number);
    }
  });
  // Round heights, then the top of the drawing: exactly the height shown
  const step = ceiling <= 1000 ? 250 : ceiling <= 5000 ? 1000 : 5000;
  const ticks: number[] = [];
  for (let z = 0; z < ceiling - 0.4 * step; z += step) ticks.push(z);
  ticks.push(ceiling);
  const label = (z: number) => (z >= 1000 && step >= 1000 ? `${f.number(z / 1000, Number.isInteger(z / 1000) ? 0 : 1)} km` : `${f.number(z, 0)} m`);
  // The level nearest the pointer, among those shown
  const read = (event: PointerEvent<SVGSVGElement>) => {
    const z = (bottom - (event.clientY - event.currentTarget.getBoundingClientRect().top)) / scale;
    let nearest = levels[0];
    for (const level of levels) if (level.height_m <= ceiling && Math.abs(level.height_m - z) < Math.abs(nearest.height_m - z)) nearest = level;
    levelHover.set(nearest ? nearest.number - 1 : null);
  };
  const lit = levels.find((level) => level.number - 1 === hovered && level.height_m <= ceiling);
  const last = Math.max(1, levels.length - 1);
  const columnY = (z: number) => bottom - (z / modelTop) * (bottom - top);
  return (
    <svg width={width} height={height} role="img" aria-label={t("column")} className="ows-profile" onPointerMove={read} onPointerLeave={() => levelHover.set(null)}>
      <defs>
        <clipPath id={clip}><rect x={0} y={top - 9} width={width} height={bottom - top + 18} /></clipPath>
      </defs>
      <line x1={left} x2={left} y1={top} y2={bottom} stroke="var(--mantine-color-dimmed)" strokeOpacity={0.5} />
      <g clipPath={`url(#${clip})`}>
        {rotors.map((r) => (
          <rect key={`band-${r.type}`} x={left} y={0} width={right - left} height={1} className="ows-profile-move" style={{ transform: `translateY(${y(r.high)}px) scaleY(${Math.max(1, (r.high - r.low) * scale)})` }} fill="var(--ows-stack-rotor)" opacity={0.1} />
        ))}
        {/* The layers the setting being typed acts on */}
        {acts && levels.slice(0, -1).map((level, n) => acts(n, levels[n + 1].dz_m) && (
          <rect key={`acts-${level.number}`} x={left} y={0} width={right - left} height={1} className="ows-profile-move" style={{ transform: `translateY(${y(levels[n + 1].height_m)}px) scaleY(${Math.max(1, levels[n + 1].dz_m * scale)})`, opacity: level.height_m > ceiling ? 0 : 0.14 }} fill="var(--mantine-color-text)" />
        ))}
        {ticks.map((z) => (
          <g key={z} className="ows-profile-move ows-profile-tick" style={at(z)}>
            <line x1={left - 4} x2={left} y1={0} y2={0} stroke="var(--mantine-color-dimmed)" strokeOpacity={0.7} />
            <text x={left - 8} y={4} fontSize={12} textAnchor="end" fill="var(--mantine-color-dimmed)">{label(z)}</text>
          </g>
        ))}
        {/* Every level, those above the height shown out of the drawing: they slide in and out */}
        {levels.map((level, n) => {
          const rotor = crossed.has(level.number) || inRotor(level.height_m);
          const on = level === lit;
          const colour = on ? "var(--mantine-color-text)" : levelColour(n / last, rotor);
          return (
            <g key={level.number} className="ows-profile-move" style={{ ...at(level.height_m), opacity: level.height_m > ceiling ? 0 : 1 }}>
              <line x1={left} x2={right} y1={0} y2={0} stroke={colour} strokeOpacity={on ? 1 : lit ? 0.35 : 0.9} strokeWidth={on ? 2.2 : rotor ? 1.4 : 1} style={{ transition: "stroke-width 120ms, stroke-opacity 120ms" }} />
            </g>
          );
        })}
        {rotors.map((r, n) => {
          const radius = Math.max(2, (r.rotor_diameter_m / 2) * scale);
          const cx = right - 14 - radius - n * (2 * radius + 14);
          // Drawn in metres, then scaled: it grows and shrinks with the levels
          const reach = radius / scale;
          const hub = -r.hub_height_m;
          return (
            <g key={`turbine-${r.type}`}>
              <title>{`${r.name} · ${f.number(r.hub_height_m, 0)} m · ${f.number(r.rotor_diameter_m, 0)} m`}</title>
              <g className="ows-profile-move" style={{ transform: `translate(${cx}px, ${bottom}px) scale(${scale})` }}>
                <line x1={0} x2={0} y1={0} y2={hub} stroke="var(--mantine-color-text)" strokeWidth={2} strokeLinecap="round" vectorEffect="non-scaling-stroke" />
                <circle cx={0} cy={hub} r={reach} fill="var(--ows-stack-rotor)" fillOpacity={0.1} stroke="var(--ows-stack-rotor)" strokeWidth={1.2} vectorEffect="non-scaling-stroke" />
                {[Math.PI / 2, Math.PI / 2 + (2 * Math.PI) / 3, Math.PI / 2 + (4 * Math.PI) / 3].map((angle) => (
                  <line key={angle} x1={0} y1={hub} x2={reach * Math.cos(angle)} y2={hub - reach * Math.sin(angle)} stroke="var(--mantine-color-text)" strokeWidth={1.8} strokeLinecap="round" vectorEffect="non-scaling-stroke" />
                ))}
              </g>
              <circle cx={0} cy={0} r={3} className="ows-profile-move" style={{ transform: `translate(${cx}px, ${y(r.hub_height_m)}px)` }} fill="var(--mantine-color-text)" />
            </g>
          );
        })}
      </g>
      <line x1={left} x2={right} y1={bottom} y2={bottom} stroke="var(--mantine-color-text)" strokeOpacity={0.6} />
      {/* The level read: its number and height on its line, under it near the top of the drawing */}
      {lit && (
        <text x={right - 4} y={y(lit.height_m) + (y(lit.height_m) < top + 18 ? 15 : -6)} fontSize={12} fontWeight={600} textAnchor="end" fill="var(--mantine-color-text)" className="ows-num" pointerEvents="none">
          {t("reading", { n: lit.number, h: f.number(lit.height_m, lit.height_m < 100 ? 1 : 0) })}
        </text>
      )}
      {/* The whole column: every level, and the part shown beside it */}
      <g aria-label={t("shown")} pointerEvents="none">
        <rect x={column.x} y={top} width={column.width} height={bottom - top} fill="none" stroke="var(--mantine-color-dimmed)" strokeOpacity={0.5} />
        {levels.map((level) => <line key={level.number} x1={column.x} x2={column.x + column.width} y1={columnY(level.height_m)} y2={columnY(level.height_m)} stroke="var(--mantine-color-dimmed)" strokeOpacity={0.55} strokeWidth={0.5} />)}
        <rect x={column.x - 3} y={0} width={column.width + 6} height={1} className="ows-profile-move" style={{ transform: `translateY(${columnY(Math.min(ceiling, modelTop))}px) scaleY(${Math.max(3, bottom - columnY(Math.min(ceiling, modelTop)))})` }} fill="var(--mantine-color-text)" fillOpacity={0.28} />
      </g>
    </svg>
  );
}

export function VerticalLevels({ draft, update }: { draft: Case; update: (change: (c: Case) => void) => void }) {
  const t = useT(messages);
  const f = useFormat();
  const grid = draft.grid;
  const vertical = useVertical(draft);
  const [range, setRange] = useState(RANGES[0]);
  // The drawing is as tall as the settings beside it, whatever the height shown
  const { ref: plot, width: plotWidth, height: plotHeight } = useElementSize();
  const { ref: fields, width: fieldsWidth } = useElementSize();
  const answer = vertical.data && !vertical.data.error ? vertical.data : null;
  const checks = vertical.data?.checks ?? [];
  const typed = grid.eta_levels ?? null;
  // The automatic levels last computed, to start typing from them
  const [automatic, setAutomatic] = useState<number[]>([]);
  useEffect(() => { if (!typed && answer) setAutomatic(answer.levels.map((level) => Number(level.eta.toFixed(6)))); }, [typed, answer]);
  // Heights offered for the drawing: those under the top of the model, then the whole column, up to the top exactly
  const modelTop = answer?.top_m ?? answer?.levels.at(-1)?.height_m;
  const ranges = RANGES.filter((value) => modelTop === undefined || Number(value) < modelTop);
  const shown = ranges.includes(range) ? range : "all";
  const ceiling = shown === "all" ? (modelTop ?? 20000) : Number(shown);
  const setLevels = (levels: number[] | null) => update((c) => {
    c.grid.eta_levels = levels;
    if (levels) c.grid.e_vert = levels.length;
  });
  const apply = (changes: Changes) => update((c) => {
    for (const [key, value] of Object.entries(changes)) {
      if (value === undefined) continue;
      if (key === "e_vert") c.grid.e_vert = Math.round(value);
      else (c.grid as unknown as Record<string, number>)[key] = value;
    }
  });
  // The setting being typed: the drawing shows the height it acts at and lights its layers
  const [setting, setSetting] = useState<Setting | null>(null);
  const typing = (name: Setting) => ({
    onFocus: () => {
      setSetting(name);
      setRange(RANGE_OF[name]);
    },
    onBlur: () => setSetting(null),
  });
  const lastLayer = (answer?.levels.length ?? 2) - 2;
  const acts = setting ? (layer: number, dz: number) => ACTS[setting](layer, dz, grid.max_dz, lastLayer) : null;
  const firstMass = answer?.mass_heights_m[0];
  return (
    <Fold title={t("title")} aside={t("summary", { n: grid.e_vert, p: f.number(grid.p_top_requested / 100, 0) })} lazy>
      <Stack gap="xl">
        {/* Two columns of the same width and height: the settings, and the levels they give */}
        <div className="ows-vertical">
          <Stack gap={10} className="ows-vertical-mode">
            <Text size="sm" fw={500}><FieldLabel label={t("mode")} info={t("modeInfo")} /></Text>
            <SegmentedControl value={typed ? "hand" : "auto"} onChange={(value) => setLevels(value === "hand" ? (automatic.length > 2 ? automatic : [1, 0.5, 0]) : null)} data={[{ value: "auto", label: t("automatic") }, { value: "hand", label: t("byHand") }]} />
          </Stack>
          <Stack gap={10} className="ows-vertical-range">
            <Text size="sm" fw={500}>{t("upTo")}</Text>
            <SegmentedControl aria-label={t("upTo")} value={shown} onChange={setRange} data={[...ranges.map((value) => ({ value, label: `${Number(value) / 1000} km` })), { value: "all", label: t("whole") }]} />
          </Stack>
          {/* The settings from the top of the column down to the ground, as on the drawing */}
          <div ref={fields} className="ows-vertical-fields">
            <Settings title={t("groupTop")} under={<TopScale hpa={grid.p_top_requested / 100} width={fieldsWidth || PROFILE_WIDTH} />}>
              <NumberField label={t("top")} info={t("topInfo")} unit="hPa" min={1} max={300} decimalScale={1} commitOnBlur value={grid.p_top_requested / 100} onValue={(v) => update((c) => void (c.grid.p_top_requested = v * 100))} {...typing("top")} />
              {!typed && <NumberField label={t("levels")} info={t("levelsInfo")} min={3} allowDecimal={false} commitOnBlur value={grid.e_vert} onValue={(v) => update((c) => void (c.grid.e_vert = v))} />}
            </Settings>
            {typed ? <TypedLevels levels={typed} automatic={automatic} onLevels={setLevels} /> : (
              <>
                <Settings title={t("groupAloft")}>
                  <NumberField label={t("maxDz")} info={t("maxDzInfo")} unit="m" min={1} commitOnBlur value={grid.max_dz} onValue={(v) => update((c) => void (c.grid.max_dz = v))} {...typing("maxDz")} />
                  <NumberField label={t("stretchU")} info={t("stretchUInfo")} min={1} decimalScale={3} step={0.05} commitOnBlur value={grid.dzstretch_u} onValue={(v) => update((c) => void (c.grid.dzstretch_u = v))} {...typing("stretchU")} />
                </Settings>
                <Settings title={t("groupGround")}>
                  <NumberField label={t("dzbot")} info={t("dzbotInfo")} unit="m" min={1} commitOnBlur value={grid.dzbot} onValue={(v) => update((c) => void (c.grid.dzbot = v))} {...typing("dzbot")} />
                  <NumberField label={t("stretchS")} info={t("stretchSInfo")} min={1} decimalScale={3} step={0.05} commitOnBlur value={grid.dzstretch_s} onValue={(v) => update((c) => void (c.grid.dzstretch_s = v))} {...typing("stretchS")} />
                </Settings>
              </>
            )}
            <Problems checks={checks} onApply={apply} />
          </div>
          <div ref={plot} className="ows-vertical-plot">
            <QueryView query={vertical}>
              {(data) => (data.error || !plotWidth || !plotHeight ? null : <Profile data={data} ceiling={ceiling} modelTop={modelTop ?? ceiling} acts={acts} width={plotWidth} height={plotHeight} />)}
            </QueryView>
          </div>
        </div>
        {/* What the settings give, under both columns */}
        {answer && (
          <StatGrid cols={{ base: 1, xs: Math.min(4, 2 + answer.turbines.length) }}>
            <Stat label={t("levels")} value={f.number(answer.levels.length, 0)} />
            {firstMass !== undefined && <Stat label={t("firstLevel")} info={t("firstLevelInfo")} unit="m" value={f.number(firstMass, firstMass < 10 ? 1 : 0)} order={1} />}
            {answer.turbines.map((turbine, n) => <Stat key={turbine.type} label={answer.turbines.length > 1 ? turbine.name : t("inRotor")} info={answer.turbines.length > 1 ? t("inRotor") : undefined} value={f.number(turbine.levels_in_rotor, 0)} order={2 + n} />)}
          </StatGrid>
        )}
        {vertical.data && !vertical.data.error && (
          <Fold title={t("table")} aside={String(vertical.data.levels.length)}>
            <Table.ScrollContainer minWidth={420}><Table striped withTableBorder fz="xs">
              <Table.Thead><Table.Tr><Table.Th>{t("number")}</Table.Th><Table.Th>{t("eta")}</Table.Th><Table.Th>{t("height")}</Table.Th><Table.Th>{t("dz")}</Table.Th></Table.Tr></Table.Thead>
              <Table.Tbody>{vertical.data.levels.map((level) => <Table.Tr key={level.number}><Table.Td>{level.number}</Table.Td><Table.Td ff="monospace">{level.eta.toFixed(4)}</Table.Td><Table.Td>{f.number(level.height_m, 1)}</Table.Td><Table.Td>{level.number > 1 ? f.number(level.dz_m, 1) : "–"}</Table.Td></Table.Tr>)}</Table.Tbody>
            </Table></Table.ScrollContainer>
          </Fold>
        )}
      </Stack>
    </Fold>
  );
}
