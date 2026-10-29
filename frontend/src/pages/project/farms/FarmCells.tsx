/**
 * Turbines per grid cell of the farm domain: WRF's schemes and time series work per cell, so
 * several turbines of a cell share its POWER and its time series.
 */
import { ScrollArea, Table, Text } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { post } from "../../../api/client";
import type { Case } from "../../../api/types";
import type { FeatureCollection } from "../../../api/types";
import { defineMessages, useT } from "../../../i18n";
import { Fold } from "../../../ui/Fold";

export interface CellRow {
  i: number;
  j: number;
  count: number;
  turbines: string[];
  farms: string[];
  prefix: string | null;
  prefixes: string[];
}

interface CellsAnswer {
  domain: number | null;
  dx_m: number | null;
  geojson: FeatureCollection;
  cells: CellRow[];
}

export const cellMessages = defineMessages({
  en: {
    grid: "Cells",
    title: "Turbines per grid cell",
    aside: "{cells|# cell|# cells} · d{domain}",
    cell: "Cell",
    count: "Turbines",
    turbines: "Which",
    farms: "Farms",
    series: "Time series",
  },
  fr: {
    grid: "Mailles",
    title: "Éoliennes par maille",
    aside: "{cells|# maille|# mailles} · d{domain}",
    cell: "Maille",
    count: "Éoliennes",
    turbines: "Lesquelles",
    farms: "Parcs",
    series: "Série temporelle",
  },
});

export function useFarmCells(draft: Case) {
  const [debounced] = useDebouncedValue(draft, 400);
  const key = useMemo(() => [debounced.grid, debounced.farms, debounced.farm_scheme, debounced.time_series], [debounced]);
  return useQuery({
    queryKey: ["method-cells", ...key],
    queryFn: () => post<CellsAnswer>("/api/method/cells", debounced),
    retry: false,
    placeholderData: keepPreviousData,
  });
}

export function CellsSummary({ cells, domain }: { cells: CellRow[]; domain: number | null }) {
  const t = useT(cellMessages);
  if (!cells.length || domain === null) return null;
  const rows = [...cells].sort((a, b) => b.count - a.count || a.j - b.j || a.i - b.i);
  return (
    <Fold title={t("title")} aside={t("aside", { cells: cells.length, domain: String(domain).padStart(2, "0") })}>
      <ScrollArea.Autosize mah={440} type="auto" offsetScrollbars>
        <Table striped fz="sm" stickyHeader miw={600}>
          <Table.Thead><Table.Tr><Table.Th>{t("cell")}</Table.Th><Table.Th>{t("count")}</Table.Th><Table.Th>{t("turbines")}</Table.Th><Table.Th>{t("farms")}</Table.Th><Table.Th>{t("series")}</Table.Th></Table.Tr></Table.Thead>
          <Table.Tbody>{rows.map((row) => (
            <Table.Tr key={`${row.i},${row.j}`}>
              <Table.Td ff="monospace">{row.i},{row.j}</Table.Td>
              <Table.Td>{row.count}</Table.Td>
              <Table.Td><Text size="xs">{row.turbines.join(", ")}</Text></Table.Td>
              <Table.Td>{row.farms.join(", ")}</Table.Td>
              <Table.Td ff="monospace">{row.prefix ?? row.prefixes.join(" ")}</Table.Td>
            </Table.Tr>
          ))}</Table.Tbody>
        </Table>
      </ScrollArea.Autosize>
    </Fold>
  );
}
