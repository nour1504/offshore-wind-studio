/**
 * Where the values of a chart come from, in the same words under every chart: « tslist, 10 min »
 * (means of every model time step) or « wrfout, 60 min » (the output interval of the history
 * files); the method, when there is one, in the bubble.
 */
import { Group, Text, Tooltip } from "@mantine/core";
import { IconInfoCircle } from "@tabler/icons-react";

import type { DataSource } from "../../../api/types";
import { defineMessages, parseUtc, useT } from "../../../i18n";

const messages = defineMessages({
  en: { each: "each model step", day: "{n} d", hour: "{n} h", minute: "{n} min", second: "{n} s" },
  fr: { each: "chaque pas du modèle", day: "{n} j", hour: "{n} h", minute: "{n} min", second: "{n} s" },
});

/** The interval of history files from their times (ISO), in seconds; null with fewer than two. */
export function intervalOf(times: readonly string[] | undefined): number | null {
  if (!times || times.length < 2) return null;
  const seconds = Math.round((parseUtc(times[1]).getTime() - parseUtc(times[0]).getTime()) / 1000);
  return seconds > 0 ? seconds : null;
}

export function SourceLine({ source, seconds, method, mt }: { source: DataSource; seconds: number | null | undefined; method?: string | null; mt?: string }) {
  const t = useT(messages);
  const s = seconds ?? 0;
  const step = s <= 0 ? (source === "tslist" ? t("each") : null)
    : s % 86400 === 0 ? t("day", { n: s / 86400 })
      : s >= 7200 && s % 3600 === 0 ? t("hour", { n: s / 3600 })
        : s % 60 === 0 ? t("minute", { n: s / 60 })
          : t("second", { n: s });
  return (
    <Group gap={5} wrap="nowrap" mt={mt} className="ows-source-line">
      <Text size="xs" c="dimmed">{step ? `${source}, ${step}` : source}</Text>
      {method && <Tooltip label={method} multiline w={340} withArrow><IconInfoCircle size={13} className="ows-info-icon" aria-label={method} /></Tooltip>}
    </Group>
  );
}
