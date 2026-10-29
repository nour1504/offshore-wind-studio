/**
 * Farm power over the useful period, or the energy per hour, day or month: one chart, the choice
 * in an icon bar, the table of values to download next to it.
 */
import { IconCalendar, IconCalendarMonth, IconClockHour4, IconDownload, IconWaveSine } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { energyApi, type EnergyPeriod } from "../../../api/energy";
import type { ResultsSummary } from "../../../api/types";
import { defineMessages, parseUtc, useFormat, useT } from "../../../i18n";
import { Fold } from "../../../ui/Fold";
import { QueryView } from "../../../ui/States";
import { ToolBar, ToolChoice, ToolGroup, ToolLink } from "../../../ui/ToolBar";
import { sharedMessages } from "./shared";
import { EnergyBars } from "./EnergyBars";
import { CHART_COLORS, TimeChart } from "./TimeChart";

const messages = defineMessages({
  en: {
    title: "Farm power",
    tools: "Farm power tools",
    raw: "Power", hour: "Energy per hour", day: "Energy per day", month: "Energy per month",
    installed: "{mw} MW installed",
    csv: "Download the table (CSV)",
  },
  fr: {
    title: "Puissance des parcs",
    tools: "Outils de la puissance des parcs",
    raw: "Puissance", hour: "Énergie par heure", day: "Énergie par jour", month: "Énergie par mois",
    installed: "{mw} MW installés",
    csv: "Télécharger le tableau (CSV)",
  },
});

const ICONS = { raw: IconWaveSine, hour: IconClockHour4, day: IconCalendar, month: IconCalendarMonth } as const;

/** Periods worth offering for a run of this length: at least two bars (the bars scroll). */
function periods(hours: number): EnergyPeriod[] {
  const chosen: EnergyPeriod[] = ["raw"];
  if (hours >= 2) chosen.push("hour");
  if (hours >= 48) chosen.push("day");
  if (hours >= 24 * 60) chosen.push("month");
  return chosen;
}

export function PowerPanel({ caseId, summary }: { caseId: string; summary: ResultsSummary }) {
  const t = useT(messages);
  const ts = useT(sharedMessages);
  const f = useFormat();
  const hours = (parseUtc(summary.end).getTime() - parseUtc(summary.start).getTime()) / 3.6e6;
  const offered = periods(hours);
  const [wanted, setPeriod] = useState<EnergyPeriod>("raw");
  const period = offered.includes(wanted) ? wanted : "raw";
  const run = summary.run_id;
  const series = useQuery({
    queryKey: ["energy-series", caseId, run, "auto", period],
    queryFn: () => energyApi.series(caseId, run, "auto", period),
    retry: false,
    staleTime: Infinity,
  });
  const lines = useMemo(() => [
    { name: "main", label: ts("withWakes"), color: CHART_COLORS.main },
    ...(summary.has_control ? [{ name: "reference", label: ts("withoutWakes"), color: CHART_COLORS.reference, dashed: true }] : []),
  ], [summary.has_control, ts]);

  const tools = (
    <ToolBar label={t("tools")}>
      <ToolChoice label={t("title")} value={period} onChange={setPeriod} options={offered.map((value) => ({ value, icon: ICONS[value], label: t(value) }))} />
      <ToolGroup>
        <ToolLink icon={IconDownload} label={t("csv")} href={energyApi.csvUrl(caseId, run, "auto", period)} />
      </ToolGroup>
    </ToolBar>
  );

  return (
    <Fold lazy title={t("title")} aside={`${f.number(summary.installed_mw, 0)} MW`} actions={tools} help="results">
      <QueryView query={series}>{(data) => {
        // One column per farm (and per farm without wakes): the chart shows the total of all farms
        const total = (keys: string[], k: number) => {
          const values = keys.map((key) => data.series[key][k]).filter((v): v is number => typeof v === "number");
          return values.length ? values.reduce((a, b) => a + b, 0) : null;
        };
        const reference = Object.keys(data.series).filter((key) => key.endsWith("_without_wakes"));
        const farms = Object.keys(data.series).filter((key) => !key.endsWith("_without_wakes"));
        const rows = data.times.map((time, k) => ({ time, main: total(farms, k), ...(reference.length ? { reference: total(reference, k) } : {}) }));
        if (period === "raw") {
          return (
            <TimeChart rows={rows} series={lines} unit="MW" title={t("title")} height={300}
              referenceLines={[{ y: summary.installed_mw, color: CHART_COLORS.limit, label: t("installed", { mw: f.number(summary.installed_mw, 0) }), labelPosition: "insideTopLeft" }]} />
          );
        }
        return <EnergyBars rows={rows} period={period} unit={data.unit} labels={{ main: ts("withWakes"), reference: ts("withoutWakes") }} />;
      }}</QueryView>
    </Fold>
  );
}
