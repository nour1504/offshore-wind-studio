/**
 * The tslist series of the run (every model time step at the measurement points): wind speed and
 * direction at a chosen height, averaged over a chosen period. Hidden when the run wrote none.
 * The point's series are exported from the Exporter tab, opened with the point, the height and
 * the average chosen here.
 */
import { Select, SimpleGrid, Stack } from "@mantine/core";
import { IconTableExport } from "@tabler/icons-react";
import { useState } from "react";

import { defineMessages, useT } from "../../../i18n";
import { Fold } from "../../../ui/Fold";
import { NumberField } from "../../../ui/Inputs";
import { ErrorState, LoadingState } from "../../../ui/States";
import { ToolBar, ToolLink } from "../../../ui/ToolBar";
import { exportHref } from "../export/link";
import { useTsIndex, useTsSeries } from "./queries";
import { type ResultsSectionProps, sharedMessages } from "./shared";
import { CHART_COLORS } from "../../../ui/chart";
import { SourceLine } from "./SourceLine";
import { TimeChart } from "./TimeChart";

const messages = defineMessages({
  en: { title: "Measurement points", location: "Point", height: "Height", average: "Average", speed: "Wind speed", direction: "Wind direction", export: "Export" },
  fr: { title: "Points de mesure", location: "Point", height: "Hauteur", average: "Moyenne", speed: "Vitesse du vent", direction: "Direction du vent", export: "Exporter" },
});

export function LocationsSection({ caseId, runId, summary }: ResultsSectionProps) {
  const t = useT(messages);
  const ts = useT(sharedMessages);
  const index = useTsIndex(caseId, runId, summary.version, summary.tslist);
  const [key, setKey] = useState<string | null>(null);
  // The height is the hub of the point's turbines until another one is typed
  const [typed, setHeight] = useState<number | null>(null);
  const [average, setAverage] = useState(600);
  // Nothing of the series is fetched before the section is opened
  const [opened, setOpened] = useState(false);
  // WRF writes each point in every domain that holds it: the finest domain only
  const all = index.data?.locations ?? [];
  const locations = all.filter((l) => !all.some((other) => other.prefix === l.prefix && other.domain > l.domain));
  const location = locations.find((l) => `${l.domain}:${l.prefix}` === key) ?? locations[0] ?? null;
  const height = typed ?? location?.hub_height_m ?? summary.hub_height_m;
  const series = useTsSeries(caseId, runId, summary.version, location, height, average, opened);
  if (!location) return null;

  const tools = (
    <ToolBar label={t("title")}>
      <ToolLink icon={IconTableExport} label={t("export")}
        href={exportHref(caseId, runId, { panel: "tslist", points: [location.prefix], quantities: ["wind_speed", "wind_direction"], heights: [height], average })} />
    </ToolBar>
  );
  return (
    <Fold lazy title={t("title")} aside={String(locations.length)} actions={tools} help="tslist" onOpenChange={(open) => { if (open) setOpened(true); }}>
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
              { name: "wind_direction_hub", label: ts("withFarm"), color: CHART_COLORS.main },
              { name: "wind_direction_hub_no_farm", label: ts("withoutFarm"), color: CHART_COLORS.reference, dashed: true },
            ]} />
            <SourceLine source="tslist" seconds={average} />
          </>
        )}
      </Stack>
    </Fold>
  );
}
