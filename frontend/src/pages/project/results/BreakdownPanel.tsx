/**
 * Energy of each farm, grid cell or turbine over the useful period: one sortable table, the
 * level chosen in an icon bar. The figures per turbine share the power WRF gives per grid cell.
 */
import { Box } from "@mantine/core";
import { IconGrid4x4, IconWindmill, IconBuildingWindTurbine } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { energyApi, type EnergyRow } from "../../../api/energy";
import type { ResultsSummary } from "../../../api/types";
import { defineMessages, useFormat, useT } from "../../../i18n";
import { DataTable, type Column } from "../../../ui/DataTable";
import { Fold } from "../../../ui/Fold";
import { QueryView } from "../../../ui/States";
import { ToolBar, ToolChoice } from "../../../ui/ToolBar";

const messages = defineMessages({
  en: {
    title: "Energy by farm",
    tools: "Level of detail",
    farms: "Farms", cells: "Grid cells", turbines: "Turbines",
    name: "Name", count: "Turbines", energy: "Energy (MWh)", mean: "Mean (MW)", factor: "Capacity factor", loss: "Wake losses",
    turbinesInfo: "Per turbine: the power of each grid cell shared between its turbines",
  },
  fr: {
    title: "Énergie par parc",
    tools: "Niveau de détail",
    farms: "Parcs", cells: "Mailles", turbines: "Éoliennes",
    name: "Nom", count: "Éoliennes", energy: "Énergie (MWh)", mean: "Moyenne (MW)", factor: "Facteur de charge", loss: "Pertes par sillage",
    turbinesInfo: "Par éolienne : la puissance de chaque maille partagée entre ses éoliennes",
  },
});

type Level = "farms" | "cells" | "turbines";
const ICONS = { farms: IconWindmill, cells: IconGrid4x4, turbines: IconBuildingWindTurbine } as const;

export function BreakdownPanel({ caseId, summary }: { caseId: string; summary: ResultsSummary }) {
  const t = useT(messages);
  const f = useFormat();
  const [level, setLevel] = useState<Level>("farms");
  const energy = useQuery({
    queryKey: ["energy", caseId, summary.run_id, "auto"],
    queryFn: () => energyApi.summary(caseId, summary.run_id, "auto"),
    retry: false,
    staleTime: Infinity,
  });
  const farmName = (id?: string) => energy.data?.farms.find((farm) => farm.id === id)?.name ?? id ?? "";
  const name = (row: EnergyRow) =>
    level === "cells" ? `d${String(row.domain).padStart(2, "0")} · ${row.i}, ${row.j}`
      : level === "turbines" ? `${farmName(row.farm)} · ${row.label ?? row.id}`
        : row.name ?? row.id ?? "";
  const columns: Column<EnergyRow>[] = [
    { key: "name", header: t("name"), render: name, sortValue: name },
    ...(level === "farms" ? [{ key: "turbines", header: t("count"), render: (r: EnergyRow) => f.number(r.turbines, 0), sortValue: (r: EnergyRow) => r.turbines, align: "right" as const }] : []),
    { key: "energy_mwh", header: t("energy"), render: (r) => f.number(r.energy_mwh, 1), sortValue: (r) => r.energy_mwh, align: "right" },
    { key: "mean_power_mw", header: t("mean"), render: (r) => f.number(r.mean_power_mw, 2), sortValue: (r) => r.mean_power_mw, align: "right" },
    { key: "capacity_factor", header: t("factor"), render: (r) => f.percent(r.capacity_factor), sortValue: (r) => r.capacity_factor, align: "right" },
    ...(summary.has_control ? [{ key: "loss_pct", header: t("loss"), render: (r: EnergyRow) => (r.loss_pct === null || r.loss_pct === undefined ? "–" : `${f.number(r.loss_pct, 1)} %`), sortValue: (r: EnergyRow) => r.loss_pct, align: "right" as const }] : []),
  ];
  const tools = (
    <ToolBar label={t("tools")}>
      <ToolChoice label={t("tools")} value={level} onChange={setLevel}
        options={(["farms", "cells", "turbines"] as const).map((value) => ({ value, icon: ICONS[value], label: t(value), hint: value === "turbines" ? t("turbinesInfo") : undefined }))} />
    </ToolBar>
  );
  return (
    <Fold lazy title={t("title")} aside={energy.data ? String(energy.data.farms.length) : undefined} actions={tools}>
      <QueryView query={energy}>{(data) => {
        const rows = level === "cells" ? data.cells : level === "turbines" ? data.turbines : data.farms;
        return (
          <Box className="ows-stagger">
            <DataTable columns={columns} rows={rows} rowKey={(row) => `${row.id ?? row.label ?? ""}-${row.domain ?? ""}-${row.i ?? ""}-${row.j ?? ""}`} maxHeight={420} caption={t("title")} />
          </Box>
        );
      }}</QueryView>
    </Fold>
  );
}
