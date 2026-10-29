import { get, withLanguage, withQuery } from "./client";
export type EnergyMethod = "auto" | "wrf" | "curve";
export interface EnergyRow {
  id?: string; name?: string; label?: string; farm?: string; type?: number; turbines?: number;
  energy_mwh: number; mean_power_mw: number | null; capacity_factor: number | null; covered_h: number;
  installed_mw?: number; reference_energy_mwh?: number | null; loss_mwh?: number; loss_pct?: number | null;
  domain?: number; i?: number; j?: number; farms?: string[]; shared?: boolean;
}
export interface EnergySummary {
  run_id: string; method: string; method_text: string; turbines_approximate: boolean; spin_up_end: string;
  covered_h: number; total: EnergyRow; farms: EnergyRow[]; turbines: EnergyRow[]; cells: EnergyRow[]; notes: string[];
  aep_mwh: number | null; aep_note: string;
}
export interface EnergySeries { run_id: string; unit: string; times: string[]; series: Record<string, (number | null)[]>; method?: string; notes?: string[]; turbines_approximate?: boolean }
export type EnergyPeriod = "raw" | "hour" | "day" | "month";
export interface EnergySector { sector: number; centre_deg: number; hours: number; energy_mwh: number; reference_mwh: number | null; loss_pct: number | null }
export interface EnergySectors { run_id: string; method_text: string; turbines_approximate: boolean; direction: string; sectors: EnergySector[]; energy_mwh: number; reference_mwh: number | null; unclassified_mwh: number }
export interface PowerCurveRow { speed_ms: number; power_mw: number; cp: number | null }
export interface PowerCurve {
  run_id: string; method_text: string; wind: string; air_density: number; rotor_diameter_m: number; hub_height_m: number; rated_mw: number; bin_width_ms: number;
  points: { time: string; speed_ms: number; power_mw: number }[]; bins: (PowerCurveRow & { centre_ms: number; count: number })[]; table: PowerCurveRow[];
}
export const energyApi = {
  summary: (c: string, run: string, method: EnergyMethod) => get<EnergySummary>(`/api/cases/${c}/energy`, {run, method}),
  series: (c: string, run: string, method: EnergyMethod, period: EnergyPeriod, turbine?: string, cell?: string, farm?: string) => get<EnergySeries>(`/api/cases/${c}/energy/series`, {run, method, period, turbine, cell, farm}),
  sectors: (c: string, run: string, sectors: number, turbine: string) => get<EnergySectors>(`/api/cases/${c}/energy/sectors`, {run, sectors, turbine}),
  curve: (c: string, run: string, turbine: string) => get<PowerCurve>(`/api/cases/${c}/energy/curve`, {run, turbine}),
  csvUrl: (c: string, run: string, method: EnergyMethod, period: EnergyPeriod, turbine?: string, cell?: string, farm?: string) => withLanguage(withQuery(`/api/cases/${c}/energy/series`, {run, method, period, turbine, cell, farm, format:"csv"})),
};
