/**
 * The vertical grid: the options of real.exe's automatic levels (auto_levels_opt = 2), or the
 * levels typed by hand (eta_levels), and the levels they give, computed by the server exactly as
 * real.exe does (core/method/vertical.py), with each turbine model's rotor and the time series
 * profiles. The checks (core/method/vertical_advice.py) guide without imposing: each says why,
 * gives its source, and offers a verified correction when there is one.
 */
import { Button, Group, SegmentedControl, SimpleGrid, Stack, Table, Text, Textarea } from "@mantine/core";
import { IconAlertTriangle } from "@tabler/icons-react";
import { useDebouncedValue, useElementSize } from "@mantine/hooks";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useEffect, useState, useSyncExternalStore } from "react";

import { post } from "../../../api/client";
import type { Case } from "../../../api/types";
import { defineMessages, useFormat, useT } from "../../../i18n";
import { Fold } from "../../../ui/Fold";
import { ExampleFile } from "../../../ui/ExampleFile";
import { FieldLabel, NumberField } from "../../../ui/Inputs";
import { QueryView } from "../../../ui/States";
import { levelHover } from "./levelHover";

interface VerticalAnswer {
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
    title: "Vertical grid",
    levels: "Levels",
    levelsInfo: "e_vert: number of full levels.",
    top: "Top",
    topInfo: "p_top_requested: pressure at the top of the model. The input data must reach it.",
    dzbot: "1st layer thickness",
    dzbotInfo: "dzbot: between the ground and the 2nd full level.",
    stretchS: "Stretching",
    stretchSInfo: "dzstretch_s: thickness ratio between two successive layers near the ground.",
    advanced: "Advanced",
    stretchU: "Stretching aloft",
    stretchUInfo: "dzstretch_u: same ratio higher up, above max_dz / 2.",
    maxDz: "Thickest layer",
    maxDzInfo: "max_dz: real.exe stops if an upper layer exceeds 1.5 times this value.",
    whole: "Column",
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
    title: "Grille verticale",
    levels: "Niveaux",
    levelsInfo: "e_vert : nombre de niveaux pleins.",
    top: "Sommet",
    topInfo: "p_top_requested : pression au sommet du modèle. Les données d'entrée doivent l'atteindre.",
    dzbot: "Épaisseur 1re couche",
    dzbotInfo: "dzbot : du sol au 2e niveau complet.",
    stretchS: "Étirement",
    stretchSInfo: "dzstretch_s : rapport d'épaisseur entre deux couches successives près du sol.",
    advanced: "Avancé",
    stretchU: "Étirement en altitude",
    stretchUInfo: "dzstretch_u : même rapport plus haut, au-delà de max_dz / 2.",
    maxDz: "Couche la plus épaisse",
    maxDzInfo: "max_dz : real.exe s'arrête si une couche haute dépasse 1,5 fois cette valeur.",
    whole: "Colonne",
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

function useVertical(draft: Case) {
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
        <g key={p} fontSize={10.5} fill="var(--mantine-color-dimmed)" textAnchor="middle">
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

/** A short grey hint under a field. */
function Hint({ children }: { children: string }) {
  return <Text size="xs" c="dimmed" mt={-10}>{children}</Text>;
}
const PROFILE_HEIGHT = 480;

/** The levels to scale, taller than wide: one line per level (those crossed by a rotor in green),
 * a few heights on the left, and each turbine model drawn at its height on the right. */
function Profile({ data, ceiling, height }: { data: VerticalAnswer; ceiling: number; height: number }) {
  const f = useFormat();
  const t = useT(messages);
  const width = PROFILE_WIDTH;
  const hovered = useSyncExternalStore(levelHover.subscribe, levelHover.get);
  const left = 52;
  const right = width - 8;
  const top = 10;
  const bottom = height - 14;
  const scale = (bottom - top) / ceiling;
  const y = (z: number) => bottom - Math.min(z, ceiling) * scale;
  const shown = data.levels.filter((level) => level.height_m <= ceiling);
  const rotors = data.turbines.map((turbine) => ({ ...turbine, low: turbine.hub_height_m - turbine.rotor_diameter_m / 2, high: turbine.hub_height_m + turbine.rotor_diameter_m / 2 }));
  const inRotor = (z: number) => rotors.some((r) => z >= r.low && z <= r.high);
  // A level just above or below a rotor bounds a layer crossed by it: green too
  const crossed = new Set<number>();
  shown.forEach((level, n) => {
    const above = shown[n + 1]?.height_m ?? Infinity;
    if (rotors.some((r) => level.height_m < r.high && above > r.low)) {
      crossed.add(level.number);
      if (shown[n + 1]) crossed.add(shown[n + 1].number);
    }
  });
  const step = ceiling <= 1000 ? 250 : ceiling <= 5000 ? 1000 : 5000;
  const ticks = Array.from({ length: Math.floor(ceiling / step) + 1 }, (_, n) => n * step);
  const label = (z: number) => (z >= 1000 && step >= 1000 ? `${f.number(z / 1000, 0)} km` : `${f.number(z, 0)} m`);
  return (
    <svg width={width} height={height} role="img" aria-label={t("column")} style={{ display: "block" }}>
      {rotors.map((r) => (
        <rect key={`band-${r.type}`} x={left} y={y(r.high)} width={right - left} height={Math.max(1, y(r.low) - y(r.high))} fill="var(--mantine-primary-color-filled)" opacity={0.08} />
      ))}
      <line x1={left} x2={left} y1={top} y2={bottom} stroke="var(--mantine-color-dimmed)" strokeOpacity={0.5} />
      {ticks.map((z) => (
        <g key={z}>
          <line x1={left - 4} x2={left} y1={y(z)} y2={y(z)} stroke="var(--mantine-color-dimmed)" strokeOpacity={0.7} />
          <text x={left - 8} y={y(z) + 4} fontSize={11} textAnchor="end" fill="var(--mantine-color-dimmed)">{label(z)}</text>
        </g>
      ))}
      {shown.map((level) => {
        const green = crossed.has(level.number) || inRotor(level.height_m);
        const lit = hovered === level.number - 1;
        return (
          <g key={level.number} onMouseEnter={() => levelHover.set(level.number - 1)} onMouseLeave={() => levelHover.set(null)}>
            <line x1={left} x2={right} y1={y(level.height_m)} y2={y(level.height_m)} stroke={lit || green ? "var(--mantine-primary-color-filled)" : "var(--mantine-color-dimmed)"} strokeOpacity={lit ? 1 : green ? 0.9 : 0.45} strokeWidth={lit ? 2.6 : green ? 1.4 : 1} style={{ transition: "stroke-width 120ms, stroke-opacity 120ms" }} />
            <line x1={left} x2={right} y1={y(level.height_m)} y2={y(level.height_m)} stroke="transparent" strokeWidth={Math.max(4, Math.min(10, scale * 40))} pointerEvents="stroke" />
          </g>
        );
      })}
      {rotors.map((r, n) => {
        const radius = Math.max(2, (r.rotor_diameter_m / 2) * scale);
        const cx = right - 14 - radius - n * (2 * radius + 14);
        const cy = y(r.hub_height_m);
        const blade = (angle: number) => [cx + radius * Math.cos(angle), cy - radius * Math.sin(angle)];
        return (
          <g key={`turbine-${r.type}`}>
            <title>{`${r.name} · ${f.number(r.hub_height_m, 0)} m · ${f.number(r.rotor_diameter_m, 0)} m`}</title>
            <line x1={cx} x2={cx} y1={y(0)} y2={cy} stroke="var(--mantine-color-text)" strokeWidth={2} strokeLinecap="round" />
            <circle cx={cx} cy={cy} r={radius} fill="var(--mantine-primary-color-filled)" fillOpacity={0.1} stroke="var(--mantine-primary-color-filled)" strokeWidth={1.2} />
            {[Math.PI / 2, Math.PI / 2 + (2 * Math.PI) / 3, Math.PI / 2 + (4 * Math.PI) / 3].map((angle) => {
              const [x2, y2] = blade(angle);
              return <line key={angle} x1={cx} y1={cy} x2={x2} y2={y2} stroke="var(--mantine-primary-color-filled)" strokeWidth={1.8} strokeLinecap="round" />;
            })}
            <circle cx={cx} cy={cy} r={3} fill="var(--mantine-color-text)" />
          </g>
        );
      })}
      <line x1={left} x2={right} y1={y(0)} y2={y(0)} stroke="var(--mantine-color-text)" strokeOpacity={0.6} />
    </svg>
  );
}

export function VerticalLevels({ draft, update }: { draft: Case; update: (change: (c: Case) => void) => void }) {
  const t = useT(messages);
  const f = useFormat();
  const grid = draft.grid;
  const vertical = useVertical(draft);
  const [range, setRange] = useState<"1000" | "5000" | "all">("1000");
  // The column of the levels takes exactly the height of the settings column
  const { ref: settingsColumn, height: settingsHeight } = useElementSize();
  const columnHeight = Math.max(PROFILE_HEIGHT + 48, Math.round(settingsHeight));
  const answer = vertical.data && !vertical.data.error ? vertical.data : null;
  const checks = vertical.data?.checks ?? [];
  const typed = grid.eta_levels ?? null;
  // The automatic levels last computed, to start typing from them
  const [automatic, setAutomatic] = useState<number[]>([]);
  useEffect(() => { if (!typed && answer) setAutomatic(answer.levels.map((level) => Number(level.eta.toFixed(6)))); }, [typed, answer]);
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
  return (
    <Fold title={t("title")} aside={t("summary", { n: grid.e_vert, p: f.number(grid.p_top_requested / 100, 0) })} lazy>
      <Stack gap="xl">
        {/* Two equal columns: the settings and the profile, each centred, each ending with a control */}
        <SimpleGrid cols={{ base: 1, md: 2 }} spacing={48}>
          <Stack ref={settingsColumn} justify="space-between" w="100%" maw={PROFILE_WIDTH} mx="auto" style={{ minHeight: PROFILE_HEIGHT + 48 }}>
            <Stack gap="lg">
              <Stack gap={6}>
                <Text size="sm" fw={500}><FieldLabel label={t("mode")} info={t("modeInfo")} /></Text>
                <SegmentedControl value={typed ? "hand" : "auto"} onChange={(value) => setLevels(value === "hand" ? (automatic.length > 2 ? automatic : [1, 0.5, 0]) : null)} data={[{ value: "auto", label: t("automatic") }, { value: "hand", label: t("byHand") }]} />
              </Stack>
              {!typed && <NumberField label={t("levels")} info={t("levelsInfo")} min={3} allowDecimal={false} commitOnBlur value={grid.e_vert} onValue={(v) => update((c) => void (c.grid.e_vert = v))} />}
              <NumberField label={t("top")} info={t("topInfo")} unit="hPa" min={1} max={300} decimalScale={1} commitOnBlur value={grid.p_top_requested / 100} onValue={(v) => update((c) => void (c.grid.p_top_requested = v * 100))} />
              <TopScale hpa={grid.p_top_requested / 100} />
              {typed ? <TypedLevels levels={typed} automatic={automatic} onLevels={setLevels} /> : <NumberField label={t("dzbot")} info={t("dzbotInfo")} unit="m" min={1} commitOnBlur value={grid.dzbot} onValue={(v) => update((c) => void (c.grid.dzbot = v))} />}
              {answer && answer.mass_heights_m.length > 0 && <Hint>{t("firstLevel", { m: f.number(answer.mass_heights_m[0], answer.mass_heights_m[0] < 10 ? 1 : 0) })}</Hint>}
              {!typed && <NumberField label={t("stretchS")} info={t("stretchSInfo")} min={1} decimalScale={3} step={0.05} commitOnBlur value={grid.dzstretch_s} onValue={(v) => update((c) => void (c.grid.dzstretch_s = v))} />}
              <Problems checks={checks} onApply={apply} />
            </Stack>
            {!typed && <Fold title={t("advanced")}>
              <Stack gap="lg">
                <NumberField label={t("stretchU")} info={t("stretchUInfo")} min={1} decimalScale={3} step={0.05} commitOnBlur value={grid.dzstretch_u} onValue={(v) => update((c) => void (c.grid.dzstretch_u = v))} />
                <NumberField label={t("maxDz")} info={t("maxDzInfo")} unit="m" min={1} commitOnBlur value={grid.max_dz} onValue={(v) => update((c) => void (c.grid.max_dz = v))} />
              </Stack>
            </Fold>}
          </Stack>
          <Stack justify="space-between" align="center" style={{ height: columnHeight }}>
            <QueryView query={vertical}>
              {(data) => data.error ? null : (
                <Stack gap={6} align="center">
                  <Profile data={data} height={columnHeight - 48 - data.turbines.length * 24} ceiling={range === "all" ? Math.ceil((data.top_m ?? 20000) / 1000) * 1000 : Number(range)} />
                  {data.turbines.map((turbine) => <Text key={turbine.type} size="xs" c="dimmed">{t("rotor", { name: turbine.name, n: turbine.levels_in_rotor })}</Text>)}
                </Stack>
              )}
            </QueryView>
            <SegmentedControl size="xs" value={range} onChange={(value) => setRange(value as "1000" | "5000" | "all")} data={[{ value: "1000", label: "1 km" }, { value: "5000", label: "5 km" }, { value: "all", label: t("whole") }]} />
          </Stack>
        </SimpleGrid>
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
