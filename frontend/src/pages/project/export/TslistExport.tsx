/**
 * The tslist fold of the Exporter tab: the grid cells holding tslist points (each cell read once,
 * its points and turbines named), every quantity the files hold at the heights asked for,
 * averaged or at each model step, in rows or in columns, over the period chosen. The preview
 * reads the first cell only, so that it answers at once.
 */
import { Button, Checkbox, Group, RangeSlider, ScrollArea, SegmentedControl, SimpleGrid, Stack, Text, TextInput, Tooltip } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { IconDownload, IconInfoCircle } from "@tabler/icons-react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { exportApi, type ExportPlace, type ExportQuantity, type TslistChoice } from "../../../api/export";
import type { ResultsSummary } from "../../../api/types";
import { parseUtc, useLang, useT } from "../../../i18n";
import { FlipRow, useRunningNumber } from "../../../ui/Motion";
import { parseHeights, writeHeights } from "../../../ui/heights";
import { ErrorState, LoadingState } from "../../../ui/States";
import { isNotFound } from "../results/queries";
import { sharedMessages } from "../results/shared";
import type { ExportInitial } from "./link";
import { exportMessages, isQuantityKey, type QuantityKey } from "./messages";

const AVERAGES = [0, 600, 3600, 86400];
const POWER: readonly string[] = ["power_turbine", "power_cell"];
const ABOUT = ["power_turbine", "power_cell", "tke", "turbulence_intensity", "shear_exponent", "wind_veer"] as const satisfies readonly QuantityKey[];
const isAbout = (key: string): key is (typeof ABOUT)[number] => (ABOUT as readonly string[]).includes(key);
const UNITS: Record<string, string> = { deg: "°", degC: "°C", "m2/s2": "m²/s²", "W/m2": "W/m²", "kg/m2": "kg/m²", "-": "" };

/** 600 as "10 min", 3600 as "1 h", 86400 as the day's word ("1 d"), 45 as "45 s". */
function duration(seconds: number, day: string): string {
  if (seconds === 86400) return day;
  if (seconds % 3600 === 0) return `${seconds / 3600} h`;
  if (seconds % 60 === 0) return `${seconds / 60} min`;
  return `${seconds} s`;
}

/** The cells a link names by turbine label or tslist prefix (or by key). */
function named(places: ExportPlace[], names: string[]): string[] {
  return places.filter((p) => names.some((name) => p.key === name || p.turbines.includes(name) || p.prefixes.includes(name))).map((p) => p.key);
}

export function TslistExport({ caseId, summary, initial }: { caseId: string; summary: ResultsSummary; initial: ExportInitial["tslist"] }) {
  const t = useT(exportMessages);
  const ts = useT(sharedMessages);
  const { lang } = useLang();
  const run = summary.run_id;
  // Not asked for when the run wrote no tslist output (the summary says so)
  const index = useQuery({ queryKey: ["export-tslist", caseId, run], queryFn: () => exportApi.tslist(caseId, run), enabled: summary.tslist, retry: false, staleTime: Infinity });
  const [pickedPoints, setPoints] = useState<string[] | null>(null);
  const [pickedQuantities, setQuantities] = useState<string[] | null>(initial.quantities);
  const [typedHeights, setHeights] = useState<string | null>(initial.heights.length ? writeHeights(initial.heights, lang) : null);
  // A link may ask for another average (the one typed in the measurement points): offered too
  const averages = [...new Set([...AVERAGES, ...(initial.average !== null && initial.average >= 0 ? [Math.round(initial.average)] : [])])].sort((a, b) => a - b);
  const [average, setAverage] = useState(initial.average !== null && initial.average >= 0 ? Math.round(initial.average) : 600);
  const [layout, setLayout] = useState<"long" | "wide">(initial.layout ?? "long");
  const [both, setBoth] = useState(true);
  const [range, setRange] = useState<[number, number] | null>(null);
  const short = useMemo(() => new Intl.DateTimeFormat(lang === "fr" ? "fr-FR" : "en-GB", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: "UTC" }), [lang]);
  // The preview shows the values as the file writes them: five significant digits
  const significant = useMemo(() => new Intl.NumberFormat(lang === "fr" ? "fr-FR" : "en-GB", { maximumSignificantDigits: 5 }), [lang]);

  const places = index.data?.places ?? [];
  const quantities = (index.data?.quantities ?? []).filter((q) => isQuantityKey(q.key));
  const keys = pickedPoints ?? (initial.points ? named(places, initial.points) : places.map((p) => p.key));
  const chosen = (pickedQuantities ?? quantities.map((q) => q.key)).filter((key) => quantities.some((q) => q.key === key));
  const hubs = index.data?.hub_heights_m.length ? index.data.hub_heights_m : [summary.hub_height_m];
  const heightsText = typedHeights ?? writeHeights(hubs, lang);
  const heights = parseHeights(heightsText, lang);
  const reference = both && Boolean(index.data?.reference);

  // The period: from one time of the files to another, in steps of the average (all at first);
  // the server keeps ]start, end], so the start sent is just before the first time kept
  const choiceBase = { points: keys, quantities: chosen, heights: heights.map(String), average_s: average, layout, reference };
  const [period, setPeriod] = useState<{ first: number; last: number } | null>(null);
  const step = (average || 600) * 1000;
  const last = period ? Math.max(0, Math.floor((period.last - period.first) / step)) : 0;
  const [from, to] = range && range[1] <= last ? range : [0, last];
  const whole = !period || (from === 0 && to === last);
  const choice: TslistChoice = {
    ...choiceBase,
    start: whole || !period ? undefined : new Date(period.first + from * step - 1000).toISOString(),
    end: whole || !period ? undefined : new Date(Math.min(period.last, period.first + to * step)).toISOString(),
  };
  const ready = keys.length > 0 && chosen.length > 0;
  const choiceText = JSON.stringify(choice);
  const [askedText] = useDebouncedValue(choiceText, 350);
  const asked = useMemo(() => JSON.parse(askedText) as TslistChoice, [askedText]);
  const preview = useQuery({
    queryKey: ["export-preview", caseId, run, asked],
    queryFn: () => exportApi.preview(caseId, run, asked),
    enabled: ready && asked.points.length > 0 && asked.quantities.length > 0,
    retry: false, staleTime: Infinity, placeholderData: keepPreviousData,
  });
  // The span of the files does not depend on the period asked: taken from each fresh answer
  const fresh = preview.data && !preview.isPlaceholderData ? preview.data : null;
  const span = fresh?.first && fresh.last ? { first: parseUtc(fresh.first).getTime(), last: parseUtc(fresh.last).getTime() } : null;
  if (span && (!period || span.first !== period.first || span.last !== period.last)) setPeriod(span);
  const count = useRunningNumber(preview.data?.times ?? 0);

  if (!summary.tslist || isNotFound(index.error)) return <Text size="sm" fw={600} c="dimmed" ta="center" py="lg">{t("noTslist")}</Text>;
  if (index.isLoading) return <LoadingState rows={4} />;
  if (index.error) return <ErrorState error={index.error} />;

  const label = (q: ExportQuantity) => (isQuantityKey(q.key) ? t(`quantity.${q.key}`) : q.key);
  const unit = (q: ExportQuantity) => UNITS[q.unit] ?? q.unit;
  const pick = (q: ExportQuantity) => (
    <Checkbox.Card key={q.key} value={q.key} radius="sm" className="ows-pick">
      <Group justify="space-between" wrap="nowrap" gap="xs">
        <Group gap={5} wrap="nowrap" style={{ minWidth: 0 }}>
          <Text size="sm" className="ows-pick-name">{label(q)}</Text>
          {isAbout(q.key) && (
            <Tooltip label={t(`about.${q.key}`)} multiline w={300} withArrow>
              <IconInfoCircle size={14} className="ows-info-icon" aria-label={t(`about.${q.key}`)} />
            </Tooltip>
          )}
        </Group>
        <Group gap={8} wrap="nowrap">
          {unit(q) && <Text size="xs" c="dimmed">{unit(q)}</Text>}
          <Checkbox.Indicator size="xs" radius="xs" iconColor="var(--ows-on-accent)" />
        </Group>
      </Group>
    </Checkbox.Card>
  );
  const groups: { title: string; items: ExportQuantity[] }[] = [
    { title: t("profiles"), items: quantities.filter((q) => (q.profile || q.between)) },
    { title: t("power"), items: quantities.filter((q) => POWER.includes(q.key)) },
    { title: t("surface"), items: quantities.filter((q) => !q.profile && !q.between && !POWER.includes(q.key)) },
  ];
  const allPoints = keys.length === places.length;
  const allQuantities = chosen.length === quantities.length;
  const cell = (column: string, row: Record<string, unknown>, k: number) => {
    const value = k === 0 ? row.time : row[column];
    if (k === 0) return short.format(parseUtc(String(value)));
    if (typeof value === "number") return Number.isFinite(value) ? significant.format(value) : "–";
    return value === null || value === undefined || value === "" ? "–" : String(value);
  };
  const columns = preview.data?.columns ?? [];
  const rows = preview.data?.rows ?? [];
  // What is missing, one line per reason, the columns it concerns before it
  const missing = new Map<string, string[]>();
  for (const [name, why] of Object.entries(preview.data?.missing ?? {})) missing.set(why, [...(missing.get(why) ?? []), name]);

  return (
    <Stack gap="xl">
      <SimpleGrid cols={{ base: 1, sm: 2, lg: index.data?.reference ? 4 : 3 }} spacing="md">
        <TextInput label={t("heights")} value={heightsText} onChange={(event) => setHeights(event.currentTarget.value)} />
        <Stack gap={6}>
          <Text size="sm" fw={500}>{t("average")}</Text>
          <SegmentedControl fullWidth value={String(average)} onChange={(value) => { setAverage(Number(value)); setRange(null); }}
            data={averages.map((s) => ({ value: String(s), label: s === 0 ? t("each") : duration(s, t("day")) }))} />
        </Stack>
        <Stack gap={6}>
          <Group gap={5} wrap="nowrap">
            <Text size="sm" fw={500}>{t("layout")}</Text>
            <Tooltip label={t("layoutAbout")} multiline w={340} withArrow><IconInfoCircle size={14} className="ows-info-icon" aria-label={t("layoutAbout")} /></Tooltip>
          </Group>
          <SegmentedControl fullWidth value={layout} onChange={(value) => setLayout(value as "long" | "wide")} data={[{ value: "long", label: t("long") }, { value: "wide", label: t("wide") }]} />
        </Stack>
        {index.data?.reference && (
          <Stack gap={6}>
            <Text size="sm" fw={500}>{t("runs")}</Text>
            <SegmentedControl fullWidth value={both ? "both" : "main"} onChange={(value) => setBoth(value === "both")}
              data={[{ value: "main", label: ts("withFarm") }, { value: "both", label: t("both") }]} />
          </Stack>
        )}
      </SimpleGrid>

      <Stack gap={10}>
        <Group justify="space-between" gap="xs">
          <Text size="sm" fw={500}>{t("points")}</Text>
          <Checkbox size="xs" label={t("all")} checked={allPoints} indeterminate={!allPoints && keys.length > 0}
            onChange={() => setPoints(allPoints ? [] : places.map((p) => p.key))} />
        </Group>
        <ScrollArea.Autosize mah={232} type="auto" offsetScrollbars>
          <Checkbox.Group value={keys} onChange={setPoints}>
            <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing={8} verticalSpacing={8}>
              {places.map((place) => (
                <Checkbox.Card key={place.key} value={place.key} radius="sm" className="ows-pick">
                  <Group justify="space-between" wrap="nowrap" gap="xs">
                    <Stack gap={0} style={{ minWidth: 0 }}>
                      <Text size="sm" truncate>{(place.turbines.length ? place.turbines : place.points).join(" ")}</Text>
                      <Text size="xs" c="dimmed" className="ows-num">{t("cell", { d: `d${String(place.domain).padStart(2, "0")}`, i: place.i, j: place.j })}</Text>
                    </Stack>
                    <Checkbox.Indicator size="xs" radius="xs" iconColor="var(--ows-on-accent)" />
                  </Group>
                </Checkbox.Card>
              ))}
            </SimpleGrid>
          </Checkbox.Group>
        </ScrollArea.Autosize>
      </Stack>

      <Stack gap={10}>
        <Group justify="space-between" gap="xs">
          <Text size="sm" fw={500}>{t("quantities")}</Text>
          <Checkbox size="xs" label={t("all")} checked={allQuantities} indeterminate={!allQuantities && chosen.length > 0}
            onChange={() => setQuantities(allQuantities ? [] : quantities.map((q) => q.key))} />
        </Group>
        <Checkbox.Group value={chosen} onChange={setQuantities}>
          <Stack gap="md">
            {groups.map((group) => group.items.length > 0 && (
              <Stack key={group.title} gap={8}>
                <Text size="xs" c="dimmed" fw={600}>{group.title}</Text>
                <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }} spacing={8} verticalSpacing={8}>{group.items.map(pick)}</SimpleGrid>
              </Stack>
            ))}
          </Stack>
        </Checkbox.Group>
      </Stack>

      {period && last > 0 && (
        <Stack gap={10}>
          <Group justify="space-between" gap="xs">
            <Text size="sm" fw={500}>{t("period")}</Text>
            <Text size="sm" c="dimmed" className="ows-num">{`${short.format(period.first + from * step)} → ${short.format(Math.min(period.last, period.first + to * step))}`}</Text>
          </Group>
          <RangeSlider min={0} max={last} step={1} minRange={0} value={[from, to]} onChange={setRange} label={null} />
        </Stack>
      )}

      {!ready ? <Text size="sm" fw={600} c="dimmed" ta="center" py="lg">{t("noChoice")}</Text>
        : preview.error ? <ErrorState error={preview.error} />
          : !preview.data ? <LoadingState rows={3} />
            : (
              <Stack gap={10}>
                <Group justify="space-between" gap="xs">
                  <Text size="sm" fw={500}>{t("preview")}</Text>
                  <Text size="sm" c="dimmed" className="ows-num">
                    {[t("times", { n: Math.round(count) }), layout === "wide" && keys.length > 1 ? t("perCell", { n: keys.length }) : null].filter(Boolean).join(" · ")}
                  </Text>
                </Group>
                <ScrollArea type="auto" offsetScrollbars>
                  <FlipRow className="ows-preview" items={columns.map((name, k) => ({ name, k }))} keyOf={(column) => column.name} render={(column) => (
                    <>
                      <div className="ows-preview-head" title={column.name}><span>{column.name}</span></div>
                      {rows.map((row, r) => <div key={r} className="ows-preview-cell">{cell(column.name, row, column.k)}</div>)}
                    </>
                  )} />
                </ScrollArea>
                {missing.size > 0 && (
                  <Stack gap={2}>
                    <Text size="xs" fw={600} c="dimmed">{t("missing")}</Text>
                    {[...missing].map(([why, names]) => <Text key={why} size="xs" c="dimmed">{`${names.join(", ")}${lang === "fr" ? " : " : ": "}${why}`}</Text>)}
                  </Stack>
                )}
              </Stack>
            )}

      <Group justify="flex-end">
        <Button component="a" href={ready ? exportApi.tslistCsv(caseId, run, choice) : undefined} download="" leftSection={<IconDownload size={18} />}
          data-disabled={!ready || undefined} onClick={(event) => { if (!ready) event.preventDefault(); }}>
          {t("download")}
        </Button>
      </Group>
    </Stack>
  );
}
