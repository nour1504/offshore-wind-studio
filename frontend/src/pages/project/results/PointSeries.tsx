/**
 * Hub-height wind over the run at a point chosen on the map (or typed), with and without the
 * farms when the reference run exists.
 */
import { Alert, Button, Group, Stack, Text, Title } from "@mantine/core";
import { IconMapPin, IconX } from "@tabler/icons-react";
import { useState } from "react";

import { common } from "../../../i18n/common";
import { defineMessages, useFormat, useT } from "../../../i18n";
import { UnitInput } from "../../../ui/Inputs";
import { ErrorState, LoadingState } from "../../../ui/States";
import { MeanComparison } from "./MeanComparison";
import { isNotFound, type MapPoint, usePointSeries } from "./queries";
import { formatCoordinates, sharedMessages } from "./shared";
import { CHART_COLORS, TimeChart } from "./TimeChart";

const messages = defineMessages({
  en: {
    title: "Wind at a point",
    chart: "Wind at {h} m · {where} · d0{d}",
    clear: "Clear the point",
    latitude: "Latitude",
    longitude: "Longitude",
    show: "Show",
    outside: "Outside d0{d}",
  },
  fr: {
    title: "Vent en un point",
    chart: "Vent à {h} m · {where} · d0{d}",
    clear: "Effacer le point",
    latitude: "Latitude",
    longitude: "Longitude",
    show: "Afficher",
    outside: "Hors de d0{d}",
  },
});

interface Props {
  caseId: string;
  runId: string;
  version: number;
  domain: number;
  hubHeight: number;
  hasControl: boolean;
  point: MapPoint | null;
  onPoint: (point: MapPoint | null) => void;
  /** Time shown on the map, marked on the chart */
  markTime: string | null;
}

export function PointSeries({ caseId, runId, version, domain, hubHeight, point, onPoint, markTime }: Props) {
  const t = useT(messages);
  const ts = useT(sharedMessages);
  const tc = useT(common);
  const f = useFormat();
  const series = usePointSeries(caseId, runId, version, domain, point);
  const [lat, setLat] = useState<number | string>("");
  const [lon, setLon] = useState<number | string>("");

  const typed = typeof lat === "number" && typeof lon === "number" && Math.abs(lat) <= 90 && Math.abs(lon) <= 180;
  const where = point ? formatCoordinates(ts, f, point.lat, point.lon) : "";
  const title = t("chart", { h: f.number(hubHeight, 0), where, d: domain });

  return (
    <Stack gap="sm">
      <Group justify="space-between" align="center" gap="xs">
        <Group gap={6} wrap="nowrap">
          <IconMapPin size={18} stroke={1.6} aria-hidden />
          <Title order={4}>{t("title")}</Title>
        </Group>
        {point && (
          <Button variant="subtle" size="xs" color="gray" leftSection={<IconX size={14} />} onClick={() => onPoint(null)}>
            {t("clear")}
          </Button>
        )}
      </Group>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (typed) onPoint({ lat: lat as number, lon: lon as number });
        }}
      >
        <Group align="flex-end" gap="xs" wrap="wrap">
          <UnitInput
            label={t("latitude")}
            unit="°"
            w={150}
            size="xs"
            min={-90}
            max={90}
            decimalScale={5}
            value={lat}
            onChange={setLat}
          />
          <UnitInput
            label={t("longitude")}
            unit="°"
            w={150}
            size="xs"
            min={-180}
            max={180}
            decimalScale={5}
            value={lon}
            onChange={setLon}
          />
          <Button type="submit" size="xs" variant="default" disabled={!typed}>
            {t("show")}
          </Button>
        </Group>
      </form>

      {point && (
        <>
          {series.isLoading ? (
            <LoadingState rows={4} height={24} />
          ) : series.error ? (
            isNotFound(series.error) ? (
              <Alert variant="light" color="gray">
                <Text size="sm">{t("outside", { d: domain })}</Text>
              </Alert>
            ) : (
              <ErrorState error={series.error} onRetry={() => void series.refetch()} />
            )
          ) : series.data ? (
            <Stack gap="xs">
              <Text size="sm" fw={500}>
                {title}
              </Text>
              <TimeChart
                rows={series.data}
                title={title}
                unit={tc("units.ms")}
                height={240}
                series={[
                  { name: "hub_wind", label: ts("withFarm"), color: CHART_COLORS.main },
                  { name: "hub_wind_control", label: ts("withoutFarm"), color: CHART_COLORS.reference, dashed: true },
                ]}
                markTime={markTime}
                markLabel={ts("mapTime")}
                yDomain={[0, "auto"]}
              />
              <MeanComparison rows={series.data} withKey="hub_wind" withoutKey="hub_wind_control" unit={tc("units.ms")} />
            </Stack>
          ) : null}
        </>
      )}
    </Stack>
  );
}
