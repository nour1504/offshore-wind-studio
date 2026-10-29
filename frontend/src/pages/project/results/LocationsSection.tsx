/**
 * The tslist series of the run (every model time step at the measurement points): wind speed and
 * direction at a chosen height, averaged over a chosen period. Hidden when the run wrote none.
 * The table of the point is exported as CSV with the quantities and the times chosen.
 */
import { Button, Checkbox, Group, Modal, RangeSlider, SegmentedControl, Select, SimpleGrid, Stack, Text } from "@mantine/core";
import { IconDownload } from "@tabler/icons-react";
import { useState } from "react";

import { resultUrls } from "../../../api/results";
import { defineMessages, parseUtc, useFormat, useLang, useT } from "../../../i18n";
import { Fold } from "../../../ui/Fold";
import { NumberField } from "../../../ui/Inputs";
import { ErrorState, LoadingState } from "../../../ui/States";
import { FlipRow, useRunningNumber } from "../../../ui/Motion";
import { ToolBar, ToolButton } from "../../../ui/ToolBar";
import { useTsIndex, useTsSeries } from "./queries";
import { type ResultsSectionProps, sharedMessages } from "./shared";
import { CHART_COLORS, TimeChart } from "./TimeChart";

const messages = defineMessages({
  en: {
    title: "Measurement points", location: "Point", height: "Height", average: "Average", speed: "Wind speed", direction: "Wind direction",
    export: "Export as CSV", columns: "Quantities", runs: "Runs", both: "With and without turbines", period: "Period · UTC", download: "Download",
    preview: "Preview", rows: "{n|# row|# rows}", time: "End · UTC",
    quantities: {
      wind_speed_hub: "Wind speed · {h} m", wind_direction_hub: "Wind direction · {h} m", temperature_hub: "Temperature · {h} m", power_mw: "Turbine power",
      wind_speed_10m: "Wind speed · 10 m", wind_direction_10m: "Wind direction · 10 m", temperature_2m: "Temperature · 2 m", pressure_surface_hpa: "Surface pressure",
      sensible_heat_flux: "Sensible heat flux", latent_heat_flux: "Latent heat flux",
    },
  },
  fr: {
    title: "Points de mesure", location: "Point", height: "Hauteur", average: "Moyenne", speed: "Vitesse du vent", direction: "Direction du vent",
    export: "Exporter en CSV", columns: "Grandeurs", runs: "Calculs", both: "Avec et sans éoliennes", period: "Période · UTC", download: "Télécharger",
    preview: "Aperçu", rows: "{n|# ligne|# lignes}", time: "Fin · UTC",
    quantities: {
      wind_speed_hub: "Vitesse du vent · {h} m", wind_direction_hub: "Direction du vent · {h} m", temperature_hub: "Température · {h} m", power_mw: "Puissance des éoliennes",
      wind_speed_10m: "Vitesse du vent · 10 m", wind_direction_10m: "Direction du vent · 10 m", temperature_2m: "Température · 2 m", pressure_surface_hpa: "Pression en surface",
      sensible_heat_flux: "Flux de chaleur sensible", latent_heat_flux: "Flux de chaleur latente",
    },
  },
});

// The columns of the point's table, in the order of the export; the first ones checked at first
const ORDER = ["wind_speed_hub", "wind_direction_hub", "temperature_hub", "power_mw", "wind_speed_10m", "wind_direction_10m", "temperature_2m", "pressure_surface_hpa", "sensible_heat_flux", "latent_heat_flux"] as const;
type Quantity = (typeof ORDER)[number];
const FIRST: readonly string[] = ["wind_speed_hub", "wind_direction_hub", "power_mw"];
const NO_FARM = "_no_farm";

export function LocationsSection({ caseId, runId, summary }: ResultsSectionProps) {
  const t = useT(messages);
  const ts = useT(sharedMessages);
  const f = useFormat();
  const { lang } = useLang();
  // Times of the export, short: the titles already say UTC
  const short = new Intl.DateTimeFormat(lang === "fr" ? "fr-FR" : "en-GB", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: "UTC" });
  const index = useTsIndex(caseId, runId, summary.version);
  const [key, setKey] = useState<string | null>(null);
  // The height is the hub of the point's turbines until another one is typed
  const [typed, setHeight] = useState<number | null>(null);
  const [average, setAverage] = useState(600);
  const [exporting, setExporting] = useState(false);
  const [chosen, setChosen] = useState<string[] | null>(null);
  const [control, setControl] = useState(true);
  const [range, setRange] = useState<[number, number] | null>(null);
  // WRF writes each point in every domain that holds it: the finest domain only
  const all = index.data?.locations ?? [];
  const locations = all.filter((l) => !all.some((other) => other.prefix === l.prefix && other.domain > l.domain));
  const location = locations.find((l) => `${l.domain}:${l.prefix}` === key) ?? locations[0] ?? null;
  const height = typed ?? location?.hub_height_m ?? summary.hub_height_m;
  const series = useTsSeries(caseId, runId, summary.version, location, height, average);
  // The period: from one time of the table to another (all of them at first); the server keeps
  // ]start, end], so the start sent is just before the first time kept
  const times = (series.data ?? []).map((row) => parseUtc(String(row.time)).getTime());
  const last = Math.max(0, times.length - 1);
  const [from, to] = range && range[1] <= last ? range : [0, last];
  const whole = from === 0 && to === last;
  const count = useRunningNumber(times.length ? to - from + 1 : 0);
  if (!location) return null;

  // The quantities the table holds, in a fixed order; the values without the farms go with them
  const keys = Object.keys(series.data?.[0] ?? {});
  const available = ORDER.filter((name) => keys.includes(name));
  const picked = (chosen ?? FIRST).filter((name) => available.some((other) => other === name));
  const withControl = control && location.has_control;
  const columns = picked.flatMap((name) => (withControl && keys.includes(name + NO_FARM) ? [name, name + NO_FARM] : [name]));
  const label = (name: Quantity) => t(`quantities.${name}`, { h: Math.round(height) });
  // The file as it will be: its columns, and the first two rows of the period
  const sample = (series.data ?? []).slice(from, Math.min(to + 1, from + 2));
  const heading = (column: string) => {
    if (column === "time") return t("time");
    const base = column.replace(NO_FARM, "") as Quantity;
    return column.endsWith(NO_FARM) ? `${label(base)} · ${ts("withoutFarm")}` : label(base);
  };
  const cell = (column: string, row: Record<string, unknown>) => {
    const value = row[column];
    if (column === "time") return short.format(parseUtc(String(value)));
    return typeof value === "number" ? f.number(value, 2) : "–";
  };
  const url = resultUrls.tslistCsv(caseId, location.prefix, location.domain, height, average, runId, columns,
    whole || !times.length ? undefined : new Date(times[from] - 1000).toISOString(), whole || !times.length ? undefined : new Date(times[to]).toISOString());

  const tools = (
    <ToolBar label={t("title")}>
      <ToolButton icon={IconDownload} label={t("export")} onClick={() => setExporting(true)} />
    </ToolBar>
  );
  return (
    <Fold lazy title={t("title")} aside={String(locations.length)} actions={tools} help="tslist">
      <Stack gap="md">
        <SimpleGrid cols={{ base: 1, sm: 3 }} spacing="md">
          <Select label={t("location")} value={`${location.domain}:${location.prefix}`} onChange={(value) => { setKey(value); setHeight(null); }} allowDeselect={false}
            data={locations.map((l) => ({ value: `${l.domain}:${l.prefix}`, label: l.name }))} />
          <NumberField label={t("height")} unit="m" min={1} value={height} onValue={setHeight} />
          <NumberField label={t("average")} unit="s" min={1} value={average} onValue={setAverage} />
        </SimpleGrid>
        {series.isLoading ? <LoadingState /> : series.error ? <ErrorState error={series.error} /> : series.data && (
          <>
            <TimeChart rows={series.data} title={t("speed")} unit="m/s" series={[
              { name: "wind_speed_hub", label: ts("withFarm"), color: CHART_COLORS.main },
              { name: "wind_speed_hub_no_farm", label: ts("withoutFarm"), color: CHART_COLORS.reference, dashed: true },
            ]} />
            <TimeChart rows={series.data} title={t("direction")} unit="°" dotsOnly compass series={[
              { name: "wind_direction_hub", label: ts("withFarm"), color: CHART_COLORS.direction },
              { name: "wind_direction_hub_no_farm", label: ts("withoutFarm"), color: CHART_COLORS.reference, dashed: true },
            ]} />
          </>
        )}
      </Stack>

      <Modal opened={exporting} onClose={() => setExporting(false)} title={<Text fw={600}>{t("export")}</Text>} size={560} centered>
        <Stack gap="xl">
          <Checkbox.Group label={t("columns")} value={picked} onChange={setChosen}>
            <SimpleGrid cols={2} spacing={8} verticalSpacing={8} mt={10}>
              {available.map((name) => (
                <Checkbox.Card key={name} value={name} radius="sm" className="ows-pick">
                  <Group justify="space-between" wrap="nowrap" gap="xs">
                    <Text size="sm" truncate>{label(name)}</Text>
                    <Checkbox.Indicator size="xs" radius="xs" iconColor="var(--ows-on-accent)" />
                  </Group>
                </Checkbox.Card>
              ))}
            </SimpleGrid>
          </Checkbox.Group>
          {location.has_control && (
            <Stack gap={10}>
              <Text size="sm" fw={500}>{t("runs")}</Text>
              <SegmentedControl fullWidth value={control ? "both" : "main"} onChange={(value) => setControl(value === "both")}
                data={[{ value: "main", label: ts("withFarm") }, { value: "both", label: t("both") }]} />
            </Stack>
          )}
          {times.length > 1 && (
            <Stack gap={10}>
              <Group justify="space-between" gap="xs">
                <Text size="sm" fw={500}>{t("period")}</Text>
                <Text size="sm" c="dimmed" className="ows-num">{`${short.format(times[from])} → ${short.format(times[to])}`}</Text>
              </Group>
              <RangeSlider min={0} max={last} step={1} minRange={0} value={[from, to]} onChange={setRange} label={null} />
            </Stack>
          )}
          {columns.length > 0 && (
            <Stack gap={10}>
              <Group justify="space-between" gap="xs">
                <Text size="sm" fw={500}>{t("preview")}</Text>
                <Text size="sm" c="dimmed" className="ows-num">{t("rows", { n: Math.round(count) })}</Text>
              </Group>
              <FlipRow className="ows-preview" items={["time", ...columns]} keyOf={(column) => column} render={(column) => (
                <>
                  <div className="ows-preview-head">{heading(column)}</div>
                  {sample.map((row, k) => <div key={k} className="ows-preview-cell">{cell(column, row)}</div>)}
                </>
              )} />
            </Stack>
          )}
          <Button fullWidth component="a" href={columns.length ? url : undefined} download="" leftSection={<IconDownload size={18} />} data-disabled={!columns.length || undefined}
            onClick={(event) => { if (!columns.length) event.preventDefault(); else setExporting(false); }}>
            {t("download")}
          </Button>
        </Stack>
      </Modal>
    </Fold>
  );
}
