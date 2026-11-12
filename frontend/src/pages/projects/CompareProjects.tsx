/**
 * Two projects side by side, only what differs: their settings (period, domains, farms, physics,
 * outputs...) and the namelists they generate, in keywords ("d02 · dx: 3000 / 1000"). Choosing
 * another project slides its column into place; the table stays, dimmed, while it is read.
 */
import { Button, Group, ScrollArea, Select, Stack, Table, Text } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import { IconArrowsLeftRight } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { type CSSProperties, useState } from "react";

import { casesApi } from "../../api/cases";
import type { Case, CaseSummary } from "../../api/types";
import { defineMessages, useT } from "../../i18n";
import { QueryView } from "../../ui/States";
import { Window } from "../../ui/Window";
import { domainName } from "../project/domains/grid";

const messages = defineMessages({
  en: { open: "Compare", title: "Compare two projects", setting: "Setting", same: "Same settings and namelists", pick: "Choose two projects" },
  fr: { open: "Comparer", title: "Comparer deux projets", setting: "Réglage", same: "Mêmes réglages et namelists", pick: "Choisir deux projets" },
});

// Not settings: names, identifiers, the format of the file
const SKIPPED = new Set(["id", "name", "description", "format_version", "appearance"]);

type Flat = Map<string, string>;

const DATES = /^(start|end)_(year|month|day|hour|minute|second|date)$|^run_(days|hours|minutes|seconds)$|^restart_interval$/;

const show = (value: unknown): string => (Array.isArray(value) ? value.map(show).join(", ") : value === null || value === undefined ? "—" : String(value));

/** Every setting of a project as "path → value", farms summed up, domains named d01, d02... */
function flatten(value: unknown, path: string[], out: Flat) {
  if (value === null || typeof value !== "object" || (Array.isArray(value) && value.every((item) => item === null || typeof item !== "object"))) {
    out.set(path.join(" · "), show(value));
    return;
  }
  if (Array.isArray(value)) {
    value.forEach((item, index) => {
      const record = item as Record<string, unknown>;
      const last = path[path.length - 1];
      const key = last === "domains" ? domainName(index) : typeof record.name === "string" ? record.name : String(index + 1);
      if (last === "farms") {
        const turbines = Array.isArray(record.turbines) ? record.turbines.length : 0;
        out.set([...path, key, "turbines"].join(" · "), String(turbines));
        flatten({ ...record, turbines: undefined, properties: undefined }, [...path, key], out);
      } else flatten(item, [...path, key], out);
    });
    return;
  }
  for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
    if (SKIPPED.has(key) || item === undefined) continue;
    if (path.length === 0 && key === "time_series" && item && typeof item === "object") {
      const series = item as { points?: unknown[] };
      out.set("time_series · points", String(series.points?.length ?? 0));
      flatten({ ...series, points: undefined }, ["time_series"], out);
      continue;
    }
    flatten(item, [...path, key], out);
  }
}

/** The namelists' options as "file · group · option → value". */
function namelistLines(files: Record<string, string>, out: Flat) {
  for (const [file, text] of Object.entries(files)) {
    if (!file.startsWith("namelist")) continue;
    let group = "";
    for (const line of text.split("\n")) {
      const header = /^\s*&(\w+)/.exec(line);
      if (header) group = header[1];
      const option = /^\s*([\w()%:]+)\s*=\s*(.*?),?\s*$/.exec(line);
      // The dates follow from the period, already compared
      if (option && group && !DATES.test(option[1])) out.set(`${file} · ${group} · ${option[1]}`, option[2]);
    }
  }
}

async function settings(id: string): Promise<Flat> {
  const project: Case = await casesApi.get(id);
  const out: Flat = new Map();
  flatten(project, [], out);
  try {
    namelistLines(await casesApi.namelists(project), out);
  } catch {
    // A project that cannot generate its namelists yet: its settings only
  }
  return out;
}

export function CompareProjects({ projects }: { projects: CaseSummary[] }) {
  const t = useT(messages);
  const [opened, { open, close }] = useDisclosure(false);
  const [a, setA] = useState<string | null>(projects[0]?.id ?? null);
  const [b, setB] = useState<string | null>(projects[1]?.id ?? null);
  // The column whose project was just chosen: it slides in when its values arrive
  const [entering, setEntering] = useState<"a" | "b" | null>(null);
  const diff = useQuery({
    placeholderData: (previous) => previous,
    queryKey: ["compare", a, b],
    enabled: opened && Boolean(a && b && a !== b),
    queryFn: async () => {
      const [left, right] = await Promise.all([settings(a!), settings(b!)]);
      const keys = [...new Set([...left.keys(), ...right.keys()])].sort();
      // Compared as shown: a setting absent from one project and empty in the other is the same "—"
      return keys.map((key) => ({ key, a: left.get(key) ?? "—", b: right.get(key) ?? "—" })).filter((row) => row.a !== row.b);
    },
  });
  if (projects.length < 2) return null;
  const data = projects.map((project) => ({ value: project.id, label: project.name }));
  const nameOf = (id: string | null) => projects.find((project) => project.id === id)?.name ?? "";
  return (
    <>
      <Button variant="default" leftSection={<IconArrowsLeftRight size={18} />} onClick={open}>{t("open")}</Button>
      <Window opened={opened} onClose={close} title={<Text fw={600}>{t("title")}</Text>} size="min(1000px, 94vw)">
        <Stack gap="md">
          <Group grow>
            <Select aria-label="A" data={data} value={a} onChange={(value) => { setA(value); setEntering("a"); }} allowDeselect={false} />
            <Select aria-label="B" data={data} value={b} onChange={(value) => { setB(value); setEntering("b"); }} allowDeselect={false} />
          </Group>
          {!a || !b || a === b ? <Text size="sm" c="dimmed">{t("pick")}</Text> : (
            <QueryView query={diff}>
              {(rows) => rows.length === 0 ? <Text size="sm" c="dimmed">{t("same")}</Text> : (
                <ScrollArea.Autosize mah="62vh" type="auto" offsetScrollbars>
                  <Table striped highlightOnHover stickyHeader className="ows-compare" data-reading={diff.isPlaceholderData || undefined}>
                    <Table.Thead><Table.Tr><Table.Th>{t("setting")}</Table.Th><Table.Th>{nameOf(a)}</Table.Th><Table.Th>{nameOf(b)}</Table.Th></Table.Tr></Table.Thead>
                    <Table.Tbody>
                      {rows.map((row, index) => (
                        <Table.Tr key={row.key}>
                          <Table.Td><Text size="sm" c="dimmed">{row.key}</Text></Table.Td>
                          {(["a", "b"] as const).map((side) => (
                            <Table.Td
                              key={side === entering ? `${side}-${diff.dataUpdatedAt}` : side}
                              className="ows-compare-col"
                              data-side={side}
                              data-enter={side === entering && !diff.isPlaceholderData ? "" : undefined}
                              style={{ "--row": Math.min(index, 14) } as CSSProperties}
                            >
                              <Text size="sm" className="ows-num" lineClamp={2}>{row[side]}</Text>
                            </Table.Td>
                          ))}
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                </ScrollArea.Autosize>
              )}
            </QueryView>
          )}
        </Stack>
      </Window>
    </>
  );
}
