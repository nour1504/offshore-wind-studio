/**
 * The four figures of a run, always in view at the top of the results: energy, mean power,
 * capacity factor, and the wake loss (or the peak power when there is no run without turbines).
 * The values come in character by character; how each is computed is in the "i" tooltip.
 */
import type { ResultsSummary } from "../../../api/types";
import { defineMessages, useFormat, useT } from "../../../i18n";
import { Stat, StatGrid } from "../../../ui/Stat";

const messages = defineMessages({
  en: {
    energy: "Energy",
    mean: "Mean power",
    factor: "Capacity factor",
    loss: "Wake losses",
    peak: "Peak power",
    energyInfo: "Over the useful period, before electrical losses and availability",
    meanInfo: "Farm power computed by WRF (POWER), spin-up left out",
    factorInfo: "Mean power ÷ installed capacity",
    lossInfo: "1 − farm power ÷ power of the same turbines in the run without turbines",
    peakInfo: "Highest farm power of the useful period",
  },
  fr: {
    energy: "Énergie",
    mean: "Puissance moyenne",
    factor: "Facteur de charge",
    loss: "Pertes par sillage",
    peak: "Puissance maximale",
    energyInfo: "Sur la période utile, avant pertes électriques et disponibilité",
    meanInfo: "Puissance des parcs calculée par WRF (POWER), spin-up exclu",
    factorInfo: "Puissance moyenne ÷ puissance installée",
    lossInfo: "1 − puissance des parcs ÷ puissance des mêmes éoliennes dans le calcul sans éoliennes",
    peakInfo: "Plus forte puissance des parcs sur la période utile",
  },
});

export function Kpis({ summary }: { summary: ResultsSummary }) {
  const t = useT(messages);
  const f = useFormat();
  const energy = summary.energy_mwh;
  const inGwh = energy !== null && Math.abs(energy) >= 10_000;
  const loss = summary.wake_efficiency !== null ? (1 - summary.wake_efficiency) * 100 : null;
  const figure = (key: "energy" | "mean" | "factor" | "loss" | "peak", value: number | null, digits: number, unit: string, order: number) => (
    <Stat key={key} label={t(key)} info={t(`${key}Info`)} value={value === null ? "–" : f.number(value, digits)} unit={value === null ? undefined : unit} order={order} />
  );
  return (
    <StatGrid cols={{ base: 2, md: 4 }}>
      {figure("energy", energy === null ? null : inGwh ? energy / 1000 : energy, inGwh ? 2 : 0, inGwh ? "GWh" : "MWh", 0)}
      {figure("mean", summary.mean_power_mw, 1, "MW", 1)}
      {figure("factor", summary.capacity_factor === null ? null : summary.capacity_factor * 100, 1, "%", 2)}
      {summary.has_control ? figure("loss", loss, 1, "%", 3) : figure("peak", summary.max_power_mw, 1, "MW", 3)}
    </StatGrid>
  );
}
