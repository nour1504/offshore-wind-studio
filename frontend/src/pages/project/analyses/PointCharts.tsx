/**
 * The charts of one turbine: its energy per wind direction sector, with and without the farms
 * (hence the wake loss per sector), and its power curve rebuilt from the run.
 */
import type { EnergySectors, PowerCurve } from "../../../api/energy";
import { defineMessages, useFormat, useT } from "../../../i18n";
import { CHART_COLORS, cssColor } from "../results/TimeChart";
import { sharedMessages } from "../results/shared";
import { Curves, Rose } from "./Charts";

const messages = defineMessages({
  en: {
    loss: "Wake loss", energy: "Energy", hours: "Hours", speed: "Wind speed", power: "Power", cp: "Power coefficient Cp",
    values: "Values", bins: "Mean per 0.5 m/s bin", table: "Turbine table",
  },
  fr: {
    loss: "Pertes de sillage", energy: "Énergie", hours: "Heures", speed: "Vitesse du vent", power: "Puissance", cp: "Coefficient de puissance Cp",
    values: "Valeurs", bins: "Moyenne par classe de 0,5 m/s", table: "Table de l'éolienne",
  },
});

export interface SectorEnergy {
  sector: number;
  energy_mwh: number | null;
  energy_control_mwh: number | null;
  loss_pct: number | null;
  share_pct: number | null;
  hours: number;
}

/** The energy of each direction sector, as the server gives it (the hours of the results page,
    each in the sector of its mean wind direction), with its share of the whole. */
export function sectorEnergy(data: EnergySectors): SectorEnergy[] {
  return data.sectors.map((row) => ({
    sector: row.centre_deg,
    energy_mwh: row.energy_mwh,
    energy_control_mwh: row.reference_mwh,
    loss_pct: row.loss_pct,
    share_pct: data.energy_mwh > 0 ? (100 * row.energy_mwh) / data.energy_mwh : null,
    hours: row.hours,
  }));
}

export function ProductionChart({ rows, control }: { rows: SectorEnergy[]; control: boolean }) {
  const t = useT(messages);
  const ts = useT(sharedMessages);
  const f = useFormat();
  const main = cssColor(CHART_COLORS.main);
  return (
    <Rose label={t("energy")} unit="MWh"
      keys={[{ label: ts("withFarm"), color: main }, ...(control ? [{ label: ts("withoutFarm"), color: cssColor(CHART_COLORS.reference), pale: true }] : [])]}
      sectors={rows.map((row) => ({ centre: row.sector, parts: [{ value: row.energy_mwh ?? 0, color: main }], reference: control ? row.energy_control_mwh : undefined }))}
      tip={(sector) => {
        const row = rows.find((r) => r.sector === sector.centre);
        return [
          { label: ts("withFarm"), value: `${f.number(row?.energy_mwh ?? 0, 1)} MWh` },
          ...(control ? [{ label: ts("withoutFarm"), value: `${f.number(row?.energy_control_mwh ?? 0, 1)} MWh` }] : []),
          ...(row?.loss_pct != null ? [{ label: t("loss"), value: `${f.number(row.loss_pct, 1)} %` }] : []),
          { label: t("hours"), value: f.number(row?.hours ?? 0, 1) },
        ];
      }} />
  );
}

/** The power (or Cp) of the turbine against the wind: every output time, the mean per bin, and
    the table of the turbine. */
export function PowerCurveChart({ curve, show }: { curve: PowerCurve; show: "power" | "cp" }) {
  const t = useT(messages);
  const y = (row: { power_mw: number; cp: number | null }) => (show === "power" ? row.power_mw : row.cp ?? NaN);
  const swept = 0.5 * curve.air_density * Math.PI * curve.rotor_diameter_m ** 2 / 4;
  return (
    <Curves label={t(show === "power" ? "power" : "cp")}
      x={{ label: t("speed"), unit: "m/s", digits: 1, from0: true }}
      y={show === "power" ? { label: t("power"), unit: "MW", digits: 2, from0: true } : { label: "Cp", unit: "", digits: 3, from0: true }}
      curves={[
        { key: "values", label: t("values"), color: cssColor(CHART_COLORS.reference), kind: "dots", cloud: true,
          points: curve.points.map((p) => ({ x: p.speed_ms, y: show === "power" ? p.power_mw : p.speed_ms > 0 ? (p.power_mw * 1e6) / (swept * p.speed_ms ** 3) : NaN })) },
        { key: "table", label: t("table"), color: cssColor(CHART_COLORS.reference), kind: "line", dashed: true,
          points: curve.table.filter((row) => show === "power" || row.speed_ms > 0).map((row) => ({ x: row.speed_ms, y: y(row) })) },
        { key: "bins", label: t("bins"), color: cssColor(CHART_COLORS.main), kind: "both", points: curve.bins.map((b) => ({ x: b.speed_ms, y: y(b) })) },
      ]} />
  );
}
