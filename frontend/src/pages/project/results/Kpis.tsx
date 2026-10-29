/**
 * The four figures of a run, always in view at the top of the results: energy, mean power,
 * capacity factor, and the wake loss (or the peak power when there is no run without turbines).
 * The values run up from zero when they appear; how each is computed is in the "i" tooltip.
 */
import { Group, SimpleGrid, Stack, Text, Tooltip } from "@mantine/core";
import { IconInfoCircle } from "@tabler/icons-react";
import { useEffect, useState } from "react";

import type { ResultsSummary } from "../../../api/types";
import { defineMessages, useFormat, useT } from "../../../i18n";
import { useRunningNumber } from "../../../ui/Motion";

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
    meanInfo: "Puissance des parcs calculée par WRF (POWER), mise en route exclue",
    factorInfo: "Puissance moyenne ÷ puissance installée",
    lossInfo: "1 − puissance des parcs ÷ puissance des mêmes éoliennes dans le calcul sans éoliennes",
    peakInfo: "Plus forte puissance des parcs sur la période utile",
  },
});

function Figure({ label, info, value, digits, unit }: { label: string; info: string; value: number | null; digits: number; unit: string }) {
  const f = useFormat();
  // From zero when the figure appears, then from value to value
  const [target, setTarget] = useState(0);
  useEffect(() => setTarget(value ?? 0), [value]);
  const shown = useRunningNumber(target);
  return (
    <Stack gap={6} className="ows-kpi">
      <Group gap={5} wrap="nowrap">
        <Text size="sm" fw={600} c="dimmed">{label}</Text>
        <Tooltip label={info} multiline w={260} withArrow>
          <IconInfoCircle size={14} className="ows-kpi-info" aria-label={info} />
        </Tooltip>
      </Group>
      <Group gap={6} align="baseline" wrap="nowrap">
        <Text className="ows-num ows-kpi-value">{value === null ? "–" : f.number(shown, digits)}</Text>
        {value !== null && <Text size="sm" fw={600} c="dimmed">{unit}</Text>}
      </Group>
    </Stack>
  );
}

export function Kpis({ summary }: { summary: ResultsSummary }) {
  const t = useT(messages);
  const energy = summary.energy_mwh;
  const inGwh = energy !== null && Math.abs(energy) >= 10_000;
  const loss = summary.wake_efficiency !== null ? (1 - summary.wake_efficiency) * 100 : null;
  return (
    <SimpleGrid cols={{ base: 2, md: 4 }} spacing={0} className="ows-kpis">
      <Figure label={t("energy")} info={t("energyInfo")} value={energy === null ? null : inGwh ? energy / 1000 : energy} digits={inGwh ? 2 : 0} unit={inGwh ? "GWh" : "MWh"} />
      <Figure label={t("mean")} info={t("meanInfo")} value={summary.mean_power_mw} digits={1} unit="MW" />
      <Figure label={t("factor")} info={t("factorInfo")} value={summary.capacity_factor === null ? null : summary.capacity_factor * 100} digits={1} unit="%" />
      {summary.has_control
        ? <Figure label={t("loss")} info={t("lossInfo")} value={loss} digits={1} unit="%" />
        : <Figure label={t("peak")} info={t("peakInfo")} value={summary.max_power_mw} digits={1} unit="MW" />}
    </SimpleGrid>
  );
}
