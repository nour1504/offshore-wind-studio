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
import { useEffect, useId, useState, useSyncExternalStore } from "react";

import { post } from "../../../api/client";
import type { Case } from "../../../api/types";
import { defineMessages, useFormat, useT } from "../../../i18n";
import { Fold } from "../../../ui/Fold";
import { ExampleFile } from "../../../ui/ExampleFile";
import { FieldLabel, NumberField } from "../../../ui/Inputs";
import { QueryView } from "../../../ui/States";
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
    firstLevel: "1st mass level (wind, temperature): {m} m",
    rotor: "{name}: {n|# level|# levels} in the rotor",
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
    firstLevel: "1er niveau de masse (vent, température) : {m} m",
    rotor: "{name} : {n|# niveau|# niveaux} dans le rotor",
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
// Pressure (hPa) and height (km) of the standard atmosphere, for the scale of the top
const SCALE_TICKS: [number, number][] = [[1000, 0], [300, 9.2], [100, 16.2], [50, 20.6], [10, 31.1], [1, 48]];

/** A scale of the top: higher pressure on the left is lower in the air; the chosen top is
    marked. Positions by the logarithm of the pressure, as heights nearly are. */
function TopScale({ hpa, width = PROFILE_WIDTH }: { hpa: number; width?: number }) {
  const t = useT(messages);
  const f = useFormat();
  const left = 14;
  const right = width - 14;
  const x = (p: number) => left + (Math.log(1000 / Math.min(1000, Math.max(1, p))) / Math.log(1000)) * (right - left);
  const marker = x(hpa);
  return (
    <svg width={width} height={50} role="img" aria-label={t("scale")} style={{ display: "block", overflow: "visible" }}>
      <line x1={left} x2={right} y1={24} y2={24} stroke="var(--mantine-color-dimmed)" strokeOpacity={0.6} />
      <rect x={left} y={21} width={Math.max(0, marker - left)} height={6} rx={3} fill="var(--mantine-primary-color-filled)" opacity={0.35} />
      {SCALE_TICKS.map(([p, km], n) => (
        <g key={p} fontSize={12} fill="var(--mantine-color-dimmed)" textAnchor="middle">
          <line x1={x(p)} x2={x(p)} y1={20} y2={28} stroke="var(--mantine-color-dimmed)" strokeOpacity={0.7} />
          <text x={x(p)} y={13}>{n === SCALE_TICKS.length - 1 ? `${f.number(p, 0)} hPa` : f.number(p, 0)}</text>
          <text x={x(p)} y={42}>{n === SCALE_TICKS.length - 1 ? `${f.number(km, 0)} km` : f.number(km, 0)}</text>
        </g>
      ))}
      <path d={`M ${marker - 6} 16 L ${marker + 6} 16 L ${marker} 24 Z`} fill="var(--mantine-primary-color-filled)" />
      <path d={`M ${marker - 6} 32 L ${marker + 6} 32 L ${marker} 24 Z`} fill="var(--mantine-primary-color-filled)" />
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

/** Heights given by the settings, under the field they follow. */
function Hints({ lines }: { lines: string[] }) {
  if (!lines.length) return null;
  return <Stack gap={2} mt={-10}>{lines.map((line) => <Text key={line} size="xs" c="dimmed">{line}</Text>)}</Stack>;
}

/** Heights offered for the drawing besides the whole column, in metres */
const RANGES = ["1000", "5000"];

/** The levels to scale: one line per level (those crossed by a rotor in green), round heights on
 * the left up to the height shown, which is the top of the drawing, and each turbine model drawn
 * at its height on the right. Another height shown slides everything to its new place. */
function Profile({ data, ceiling, width, height }: { data: VerticalAnswer; ceiling: number; width: number; height: number }) {
  const f = useFormat();
  const t = useT(messages);
  const clip = useId();
  const hovered = useSyncExternalStore(levelHover.subscribe, levelHover.get);
  const left = 52;
  const right = width - 8;
  const top = 10;
  // The ground on the bottom edge, level with the last field beside it
  const bottom = height - 1;
  const scale = (bottom - top) / ceiling;
  const y = (z: number) => bottom - z * scale;
  const at = (z: number) => ({ transform: `translateY(${y(z)}px)` });
  const levels = data.levels;
  const rotors = data.turbines.map((turbine) => ({ ...turbine, low: turbine.hub_height_m - turbine.rotor_diameter_m / 2, high: turbine.hub_height_m + turbine.rotor_diameter_m / 2 }));
  const inRotor = (z: number) => rotors.some((r) => z >= r.low && z <= r.high);
  // A level just above or below a rotor bounds a layer crossed by it: green too
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
  return (
    <svg width={width} height={height} role="img" aria-label={t("column")} className="ows-profile">
      <defs>
        <clipPath id={clip}><rect x={0} y={top - 9} width={width} height={bottom - top + 18} /></clipPath>
      </defs>
      <line x1={left} x2={left} y1={top} y2={bottom} stroke="var(--mantine-color-dimmed)" strokeOpacity={0.5} />
      <g clipPath={`url(#${clip})`}>
        {rotors.map((r) => (
          <rect key={`band-${r.type}`} x={left} y={0} width={right - left} height={1} className="ows-profile-move" style={{ transform: `translateY(${y(r.high)}px) scaleY(${Math.max(1, (r.high - r.low) * scale)})` }} fill="var(--mantine-primary-color-filled)" opacity={0.08} />
        ))}
        {ticks.map((z) => (
          <g key={z} className="ows-profile-move ows-profile-tick" style={at(z)}>
            <line x1={left - 4} x2={left} y1={0} y2={0} stroke="var(--mantine-color-dimmed)" strokeOpacity={0.7} />
            <text x={left - 8} y={4} fontSize={12} textAnchor="end" fill="var(--mantine-color-dimmed)">{label(z)}</text>
          </g>
        ))}
        {/* Every level, those above the height shown out of the drawing: they slide in and out */}
        {levels.map((level) => {
          const green = crossed.has(level.number) || inRotor(level.height_m);
          const lit = hovered === level.number - 1;
          return (
            <g key={level.number} className="ows-profile-move" style={{ ...at(level.height_m), opacity: level.height_m > ceiling ? 0 : 1 }} onMouseEnter={() => levelHover.set(level.number - 1)} onMouseLeave={() => levelHover.set(null)}>
              <line x1={left} x2={right} y1={0} y2={0} stroke={lit || green ? "var(--mantine-primary-color-filled)" : "var(--mantine-color-dimmed)"} strokeOpacity={lit ? 1 : green ? 0.9 : 0.45} strokeWidth={lit ? 2.6 : green ? 1.4 : 1} style={{ transition: "stroke-width 120ms, stroke-opacity 120ms" }} />
              <line x1={left} x2={right} y1={0} y2={0} stroke="transparent" strokeWidth={Math.max(4, Math.min(10, scale * 40))} pointerEvents="stroke" />
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
                <circle cx={0} cy={hub} r={reach} fill="var(--mantine-primary-color-filled)" fillOpacity={0.1} stroke="var(--mantine-primary-color-filled)" strokeWidth={1.2} vectorEffect="non-scaling-stroke" />
                {[Math.PI / 2, Math.PI / 2 + (2 * Math.PI) / 3, Math.PI / 2 + (4 * Math.PI) / 3].map((angle) => (
                  <line key={angle} x1={0} y1={hub} x2={reach * Math.cos(angle)} y2={hub - reach * Math.sin(angle)} stroke="var(--mantine-primary-color-filled)" strokeWidth={1.8} strokeLinecap="round" vectorEffect="non-scaling-stroke" />
                ))}
              </g>
              <circle cx={0} cy={0} r={3} className="ows-profile-move" style={{ transform: `translate(${cx}px, ${y(r.hub_height_m)}px)` }} fill="var(--mantine-color-text)" />
            </g>
          );
        })}
      </g>
      <line x1={left} x2={right} y1={bottom} y2={bottom} stroke="var(--mantine-color-text)" strokeOpacity={0.6} />
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
  const hints = answer ? [
    ...(answer.mass_heights_m.length > 0 ? [t("firstLevel", { m: f.number(answer.mass_heights_m[0], answer.mass_heights_m[0] < 10 ? 1 : 0) })] : []),
    ...answer.turbines.map((turbine) => t("rotor", { name: turbine.name, n: turbine.levels_in_rotor })),
  ] : [];
  return (
    <Fold title={t("title")} aside={t("summary", { n: grid.e_vert, p: f.number(grid.p_top_requested / 100, 0) })} lazy>
      <Stack gap="xl">
        {/* Two columns of the same width and height: the settings, and the levels they give */}
        <div className="ows-vertical">
          <Stack gap={6} className="ows-vertical-mode">
            <Text size="sm" fw={500}><FieldLabel label={t("mode")} info={t("modeInfo")} /></Text>
            <SegmentedControl value={typed ? "hand" : "auto"} onChange={(value) => setLevels(value === "hand" ? (automatic.length > 2 ? automatic : [1, 0.5, 0]) : null)} data={[{ value: "auto", label: t("automatic") }, { value: "hand", label: t("byHand") }]} />
          </Stack>
          <Stack gap={6} className="ows-vertical-range">
            <Text size="sm" fw={500}>{t("upTo")}</Text>
            <SegmentedControl aria-label={t("upTo")} value={shown} onChange={setRange} data={[...ranges.map((value) => ({ value, label: `${Number(value) / 1000} km` })), { value: "all", label: t("whole") }]} />
          </Stack>
          <Stack gap="lg" className="ows-vertical-fields">
            {!typed && <NumberField label={t("levels")} info={t("levelsInfo")} min={3} allowDecimal={false} commitOnBlur value={grid.e_vert} onValue={(v) => update((c) => void (c.grid.e_vert = v))} />}
            <NumberField label={t("top")} info={t("topInfo")} unit="hPa" min={1} max={300} decimalScale={1} commitOnBlur value={grid.p_top_requested / 100} onValue={(v) => update((c) => void (c.grid.p_top_requested = v * 100))} />
            <TopScale hpa={grid.p_top_requested / 100} />
            {typed ? <TypedLevels levels={typed} automatic={automatic} onLevels={setLevels} /> : <NumberField label={t("dzbot")} info={t("dzbotInfo")} unit="m" min={1} commitOnBlur value={grid.dzbot} onValue={(v) => update((c) => void (c.grid.dzbot = v))} />}
            <Hints lines={hints} />
            {!typed && (
              <>
                <NumberField label={t("stretchS")} info={t("stretchSInfo")} min={1} decimalScale={3} step={0.05} commitOnBlur value={grid.dzstretch_s} onValue={(v) => update((c) => void (c.grid.dzstretch_s = v))} />
                <NumberField label={t("stretchU")} info={t("stretchUInfo")} min={1} decimalScale={3} step={0.05} commitOnBlur value={grid.dzstretch_u} onValue={(v) => update((c) => void (c.grid.dzstretch_u = v))} />
                <NumberField label={t("maxDz")} info={t("maxDzInfo")} unit="m" min={1} commitOnBlur value={grid.max_dz} onValue={(v) => update((c) => void (c.grid.max_dz = v))} />
              </>
            )}
            <Problems checks={checks} onApply={apply} />
          </Stack>
          <div ref={plot} className="ows-vertical-plot">
            <QueryView query={vertical}>
              {(data) => (data.error || !plotWidth || !plotHeight ? null : <Profile data={data} ceiling={ceiling} width={plotWidth} height={plotHeight} />)}
            </QueryView>
          </div>
        </div>
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
