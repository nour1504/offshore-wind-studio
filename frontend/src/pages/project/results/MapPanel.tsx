/**
 * The fields of the run on the map, frame by frame: the field and the domain in the map's icon
 * bar, the time under it with a play button. Every frame is loaded ahead, and playing waits for
 * the next one, so that the animation moves at an even pace. A click on the map gives the wind
 * at that point over the run, under the map.
 */
import { ActionIcon, Box, Group, SegmentedControl, Slider, Stack, Text } from "@mantine/core";
import { IconArrowsDiff, IconBolt, IconFlag, IconPlayerPauseFilled, IconPlayerPlayFilled, IconStack2, IconTemperature, IconWind, type Icon } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { exploreApi } from "../../../api/explore";
import { resultUrls } from "../../../api/results";
import type { FieldMeta, ResultsSummary } from "../../../api/types";
import { useLoadedDraft } from "../../../app/CaseDraft";
import { defineMessages, useFormat, useT } from "../../../i18n";
import { Fold } from "../../../ui/Fold";
import { ErrorState } from "../../../ui/States";
import { ToolChoice } from "../../../ui/ToolBar";
import { ProjectMap } from "../../../ui/map/ProjectMap";
import { PointSeries } from "./PointSeries";
import { type MapPoint, useFieldMeta } from "./queries";

const messages = defineMessages({
  en: {
    title: "Map",
    field: "Field",
    domain: "Domain",
    play: "Play",
    pause: "Pause",
    time: "Time",
    fields: { hub_wind: "Wind at hub height", wake: "Change due to the farms", wind10: "Wind at 10 m", power: "Turbine power", pblh: "Boundary layer height", t2: "Temperature at 2 m" },
  },
  fr: {
    title: "Carte",
    field: "Champ",
    domain: "Domaine",
    play: "Lire",
    pause: "Pause",
    time: "Instant",
    fields: { hub_wind: "Vent à hauteur de moyeu", wake: "Effet des parcs sur le vent", wind10: "Vent à 10 m", power: "Puissance des éoliennes", pblh: "Hauteur de couche limite", t2: "Température à 2 m" },
  },
});

type Field = "hub_wind" | "wake" | "wind10" | "power" | "pblh" | "t2";
const ICONS: Record<Field, Icon> = { hub_wind: IconWind, wake: IconArrowsDiff, wind10: IconFlag, power: IconBolt, pblh: IconStack2, t2: IconTemperature };
// Time on each frame while playing (a frame not loaded yet is waited for)
const FRAME_MS = 650;

function Legend({ meta, label }: { meta: FieldMeta; label: string }) {
  const f = useFormat();
  const span = Math.abs(meta.vmax - meta.vmin);
  const digits = span < 2 ? 2 : span < 30 ? 1 : 0;
  return (
    <Group gap={10} wrap="nowrap" className="ows-map-legend" role="img" aria-label={`${label}: ${f.number(meta.vmin, digits)} – ${f.number(meta.vmax, digits)} ${meta.units}`}>
      <Text size="sm" className="ows-num">{f.number(meta.vmin, digits)}</Text>
      <Box className="ows-map-legend-bar" style={{ background: `linear-gradient(to right, ${meta.colors.join(", ")})` }} />
      <Text size="sm" className="ows-num">{f.number(meta.vmax, digits)}</Text>
      <Text size="sm" fw={600} c="dimmed">{meta.units}</Text>
    </Group>
  );
}

export function MapPanel({ caseId, summary }: { caseId: string; summary: ResultsSummary }) {
  const t = useT(messages);
  const f = useFormat();
  const { draft } = useLoadedDraft();
  const run = summary.run_id;
  const [domain, setDomain] = useState(summary.farm_domain ?? summary.domains.at(-1) ?? 1);
  const offered = (summary.fields?.[String(domain)] ?? Object.keys(summary.variables)) as Field[];
  const [wanted, setWanted] = useState<Field>("hub_wind");
  const field = offered.includes(wanted) ? wanted : offered[0];
  const [time, setTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [point, setPoint] = useState<MapPoint | null>(null);
  const times = summary.times[String(domain)] ?? [];
  const shown = Math.min(time, Math.max(0, times.length - 1));
  const meta = useFieldMeta(caseId, run, summary.version, field, domain);
  const geometry = useQuery({ queryKey: ["run-geometry", caseId, run], queryFn: () => exploreApi.geometry(caseId, run), retry: false });
  const urls = useMemo(() => times.map((_, k) => resultUrls.fieldPng(caseId, field, domain, k, summary.version, run)), [times, caseId, field, domain, summary.version, run]);

  // Every frame is fetched ahead (the server keeps them once computed)
  const [loaded, setLoaded] = useState<Set<string>>(new Set());
  useEffect(() => {
    let alive = true;
    const images = urls.map((url) => {
      const image = new Image();
      image.onload = () => { if (alive) setLoaded((now) => new Set(now).add(url)); };
      image.src = url;
      return image;
    });
    return () => { alive = false; images.forEach((image) => { image.onload = null; }); };
  }, [urls]);

  // Playing moves on only once the next frame is there
  useEffect(() => {
    if (!playing || times.length < 2) return;
    const next = (shown + 1) % times.length;
    if (!loaded.has(urls[next])) return;
    const id = window.setTimeout(() => setTime(next), FRAME_MS);
    return () => window.clearTimeout(id);
  }, [playing, shown, loaded, urls, times.length]);
  useEffect(() => { setTime(0); setPlaying(false); setPoint(null); }, [run, domain]);

  const tools = (
    <Group gap={10} wrap="nowrap">
      {summary.domains.length > 1 && (
        <SegmentedControl size="xs" aria-label={t("domain")} value={String(domain)} onChange={(value) => setDomain(Number(value))}
          data={summary.domains.map((d) => ({ value: String(d), label: `d${String(d).padStart(2, "0")}` }))} />
      )}
      <ToolChoice label={t("field")} value={field} onChange={(value) => setWanted(value)}
        options={offered.map((value) => ({ value, icon: ICONS[value], label: t(`fields.${value}`) }))} />
    </Group>
  );

  return (
    <Fold lazy title={t("title")} aside={t(`fields.${field}`)} actions={tools}>
      <Stack gap="md">
        {meta.error ? <ErrorState error={meta.error} onRetry={() => void meta.refetch()} /> : (
          <ProjectMap geometry={geometry.data} farmOrder={draft.farms.map((farm) => farm.id)} farms="dots" height={500} ariaLabel={t("title")}
            marker={point} onMapClick={(lat, lon) => setPoint({ lat, lon })} showProbes={false} frame={{ target: `domain:${domain}`, key: domain }}
            overlay={meta.data && urls[shown] ? { url: urls[shown], coordinates: meta.data.coordinates, opacity: 0.85 } : null} />
        )}
        <Group gap="md" wrap="nowrap" className="ows-map-timeline">
          <ActionIcon size={34} radius="xl" variant="filled" aria-label={playing ? t("pause") : t("play")} disabled={times.length < 2} onClick={() => setPlaying((now) => !now)}>
            {playing ? <IconPlayerPauseFilled size={16} /> : <IconPlayerPlayFilled size={16} />}
          </ActionIcon>
          <Slider style={{ flex: 1 }} min={0} max={Math.max(1, times.length - 1)} step={1} value={shown} onChange={(value) => { setPlaying(false); setTime(value); }}
            disabled={times.length < 2} aria-label={t("time")} label={(value) => f.dateTime(times[value])} />
          <Text size="sm" fw={600} className="ows-num" style={{ whiteSpace: "nowrap" }}>{times[shown] ? f.dateTime(times[shown]) : "–"}</Text>
        </Group>
        {meta.data && <Legend meta={meta.data} label={t(`fields.${field}`)} />}
        <PointSeries caseId={caseId} runId={run} version={summary.version} domain={domain} hubHeight={summary.hub_height_m} hasControl={summary.has_control} point={point} onPoint={setPoint} markTime={times[shown] ?? null} />
      </Stack>
    </Fold>
  );
}
