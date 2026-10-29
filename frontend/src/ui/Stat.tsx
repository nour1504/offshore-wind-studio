import { Badge, Group, Paper, SimpleGrid, Stack, Text, Tooltip } from "@mantine/core";
import { IconInfoCircle } from "@tabler/icons-react";
import type { ReactNode } from "react";

import type { RunState } from "../api/types";
import { common } from "../i18n/common";
import { useT } from "../i18n";

interface StatProps {
  label: ReactNode;
  value: ReactNode;
  unit?: ReactNode;
  /** One line under the value: reference, method, caveat */
  hint?: ReactNode;
  /** Longer explanation in a tooltip */
  info?: ReactNode;
  tone?: "default" | "good" | "bad" | "muted";
}

const toneColor = { default: undefined, good: "teal.7", bad: "ember.7", muted: "dimmed" } as const;

/** A key figure: label, value with its unit, and how to read it. */
export function Stat({ label, value, unit, hint, info, tone = "default" }: StatProps) {
  return (
    <Paper p="md" radius={0} className="ows-stat">
      <Stack gap={4}>
        <Group gap={4} wrap="nowrap">
          <Text size="xs" c="dimmed" fw={500} className="ows-stat-label">
            {label}
          </Text>
          {info && (
            <Tooltip label={info}>
              <IconInfoCircle size={14} style={{ color: "var(--ows-muted)" }} aria-label="info" />
            </Tooltip>
          )}
        </Group>
        <Group gap={6} align="baseline" wrap="nowrap">
          <Text fz={28} fw={600} lh={1.1} c={toneColor[tone]} className="ows-num ows-stat-value">
            {value}
          </Text>
          {unit && (
            <Text size="sm" c="dimmed">
              {unit}
            </Text>
          )}
        </Group>
        {hint && (
          <Text size="xs" c="dimmed" className="ows-stat-hint">
            {hint}
          </Text>
        )}
      </Stack>
    </Paper>
  );
}

export function StatGrid({ children, cols = 4 }: { children: ReactNode; cols?: number }) {
  return (
    <SimpleGrid cols={{ base: 1, xs: 2, md: cols }} spacing={0} className="ows-stat-grid">
      {children}
    </SimpleGrid>
  );
}

const stateColor: Record<RunState, string> = {
  idle: "gray",
  queued: "gray",
  running: "forest",
  succeeded: "teal",
  failed: "red",
  cancelled: "gray",
};

export function StateBadge({ state, size = "sm" }: { state: RunState; size?: "xs" | "sm" | "md" }) {
  const t = useT(common);
  return (
    <Badge
      color={stateColor[state]}
      size={size}
      variant={state === "running" ? "filled" : "light"}
      leftSection={state === "running" ? <span className="ows-live-dot" aria-hidden="true" /> : undefined}
    >
      {t(`state.${state}`)}
    </Badge>
  );
}

/** Label/value pairs in two aligned columns. */
export function KeyValues({ items }: { items: [ReactNode, ReactNode][] }) {
  return (
    <Stack gap={6}>
      {items.map(([k, v], i) => (
        <Group key={i} gap="md" wrap="nowrap" align="flex-start">
          <Text size="sm" c="dimmed" w={180} style={{ flexShrink: 0 }}>
            {k}
          </Text>
          <Text size="sm" style={{ minWidth: 0, overflowWrap: "anywhere" }}>
            {v}
          </Text>
        </Group>
      ))}
    </Stack>
  );
}
