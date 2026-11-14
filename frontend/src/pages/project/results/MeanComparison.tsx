/**
 * One line under a chart: the mean with the farms, without them, and the relative change,
 * computed over the times where both values exist.
 */
import { Group, Text } from "@mantine/core";

import { useFormat, useT } from "../../../i18n";
import { meanOf, pairedMeans, sharedMessages } from "./shared";

interface Props {
  rows: readonly object[];
  withKey: string;
  withoutKey: string;
  unit: string;
  digits?: number;
  /** "farms": with and without the farms (wind); "wakes": with and without wakes (power) */
  kind?: "farms" | "wakes";
}

export function MeanComparison({ rows, withKey, withoutKey, unit, digits = 2, kind = "farms" }: Props) {
  const t = useT(sharedMessages);
  const f = useFormat();
  const paired = pairedMeans(rows, withKey, withoutKey);

  if (!paired) {
    const mean = meanOf(rows, withKey);
    if (mean === null) return null;
    return (
      <Text size="sm" c="dimmed">
        {t("meanOnly")}{" "}
        <Text span fw={600} c="var(--mantine-color-text)" className="ows-num">
          {f.number(mean, digits)} {unit}
        </Text>
      </Text>
    );
  }

  const change = paired.b !== 0 ? paired.a / paired.b - 1 : null;
  const sign = change !== null && change > 0 ? "+" : "";
  return (
    <Group gap="md" wrap="wrap">
      <Text size="sm" c="dimmed">
        {t(kind === "wakes" ? "meanWithWakes" : "meanWith")}{" "}
        <Text span fw={600} c="var(--mantine-color-text)" className="ows-num">
          {f.number(paired.a, digits)} {unit}
        </Text>
      </Text>
      <Text size="sm" c="dimmed">
        {t(kind === "wakes" ? "meanWithoutWakes" : "meanWithout")}{" "}
        <Text span fw={600} c="var(--mantine-color-text)" className="ows-num">
          {f.number(paired.b, digits)} {unit}
        </Text>
      </Text>
      {change !== null && (
        <Text size="sm" c="dimmed">
          {t("change")}{" "}
          <Text span fw={600} c={change < 0 ? "var(--ows-loss)" : "var(--mantine-color-text)"} className="ows-num">
            {sign}
            {f.percent(change, 1)}
          </Text>
        </Text>
      )}
    </Group>
  );
}
