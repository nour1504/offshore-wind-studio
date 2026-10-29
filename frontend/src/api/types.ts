// Mirrors of the backend models (owstudio.core.case.model, owstudio.api.runs, settings, profiles)

export type Scalar = number | string | boolean;
/** f90nml JSON: sparse indexed arrays use null blanks, multidimensional arrays and
 * _start_index dictionaries preserve their shape and Fortran indexing. */
export type NamelistValue = Scalar | null | NamelistValue[] | { [key: string]: NamelistValue };
export type NamelistGroups = Record<string, Record<string, NamelistValue>>;

export interface Period {
  start: string;
  end: string;
  interval_seconds: number;
}

export type MapProj = "lambert" | "mercator" | "polar" | "lat-lon";

export interface Projection {
  map_proj: MapProj;
  ref_lat: number;
  ref_lon: number;
  truelat1?: number | null;
  truelat2?: number | null;
  stand_lon?: number | null;
}

export interface Domain {
  e_we: number;
  e_sn: number;
  parent_id: number;
  parent_grid_ratio: number;
  i_parent_start: number;
  j_parent_start: number;
  geog_data_res: string;
}

export interface Grid {
  projection: Projection;
  dx: number;
  domains: Domain[];
  e_vert: number;
  p_top_requested: number;
  dzbot: number;
  dzstretch_s: number;
  dzstretch_u: number;
  max_dz: number;
  /** Full eta levels typed by hand (1 at the ground to 0 at the top); null: automatic levels */
  eta_levels?: number[] | null;
  /** Explicit full eta levels (1 to 0); the automatic options then no longer apply */
}

export interface CurvePoint {
  wind_speed: number;
  thrust_coefficient: number;
  power_kw: number;
}

export interface TurbineType {
  name: string;
  hub_height_m: number;
  rotor_diameter_m: number;
  standing_thrust_coefficient: number;
  rated_power_mw: number;
  curve: CurvePoint[];
}

export interface Turbine {
  lat: number;
  lon: number;
  type: number;
  id?: string | null;
}

export type FarmSymbol = "circle" | "cross" | "plus" | "square" | "diamond" | "triangle";
export interface FarmAppearance {
  color: string | null;
  symbol: FarmSymbol | "auto";
}

export interface Farm {
  id: string;
  name: string;
  enabled: boolean;
  properties: Record<string, string>;
  appearance?: FarmAppearance;
  turbines: Turbine[];
}

export type WakeModel = 1 | 2 | 3 | 4 | 5;
export type OverlapMethod = 1 | 2 | 3 | 4;

export interface FarmScheme {
  scheme: "fitch" | "mav";
  domains: number[];
  tke_factor: number;
  induction: boolean;
  wake_model: WakeModel;
  overlap_method: OverlapMethod;
}

export interface TimeSeriesPoint {
  name: string;
  prefix: string;
  lat: number;
  lon: number;
}

export interface TimeSeries {
  turbines: "none" | "each" | "cells";
  points: TimeSeriesPoint[];
  max_levels: number;
}

export interface GribInput {
  folder: string;
  pattern: string;
  vtable: string;
  custom_vtable: string;
}

export interface SeaSurface {
  source: "input" | "grib";
  grib: GribInput | null;
  update: boolean;
  update_interval_minutes: number | null;
}

export interface Outputs {
  add: string[];
  remove: string[];
}

export type InputSource = "gfs" | "era5" | "grib";

/** Land-surface source read by metgrid after the atmosphere (ERA5-Land...). */
export interface LandInput extends GribInput {
  prefix: string;
}

export type Grouping = "month" | "quarter" | "week" | "window";

/** Windows of a period longer than useful_hours (core/method/plan.py). */
export interface Windows {
  useful_hours: number;
  grouping: Grouping;
  /** One continuous simulation: each window starts from the restart file of the previous one */
  restart?: boolean;
}

export interface Case {
  format_version: number;
  name: string;
  description: string;
  period: Period;
  grid: Grid;
  physics: Record<string, NamelistValue>;
  dynamics: Record<string, NamelistValue>;
  turbine_types: Record<string, TurbineType>;
  farms: Farm[];
  farm_scheme: FarmScheme | null;
  history_interval_minutes: number;
  input_source: InputSource;
  grib: GribInput | null;
  sea_surface: SeaSurface;
  land: LandInput | null;
  outputs: Outputs;
  time_series: TimeSeries | null;
  /** Spin-up S before every window, always applied; period is the useful interval [D, F]. */
  spin_up_hours: number;
  windows: Windows;
  namelist_wps: NamelistGroups;
  namelist_input: NamelistGroups;
}

export interface CaseSummary {
  id: string;
  name: string;
  description: string;
  start: string;
  end: string;
  domains: number;
  turbines: number;
  farms: number;
  farm_scheme: "fitch" | "mav" | null;
  last_run_state: RunState;
  last_run_id: string | null;
}

export interface Issue {
  severity: "error" | "warning" | "info";
  /** In the language of the interface */
  message: string;
  /** The field it is about, and the reason in a few words to show next to it */
  field?: string | null;
  short?: string | null;
  /** The project page it belongs to: data, domains, turbines, farms, physics, outputs */
  page?: string | null;
}

// ------------------------------------------------------------------ runs

export type RunState = "idle" | "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface RunStatus {
  run_id: string | null;
  state: RunState;
  stage: "main" | "control";
  with_control: boolean;
  profile: string | null;
  profile_name: string | null;
  mpi_ranks: number | null;
  step: string | null;
  fraction: number;
  model_time: string | null;
  seconds_per_step: number | null;
  queued_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  engine: Record<string, unknown>;
  label: string;
  tags: Record<string, string>;
  farms: string[];
  fingerprint: string;
}

// ------------------------------------------------------- compute profiles

export type ProfileKind = "wsl" | "local";

export interface EngineInstall {
  wrf_dir: string;
  wps_dir: string;
  geog_dir: string;
  env_setup: string;
  work_dir: string;
  input_dir: string;
}

export interface Resources {
  /** How MPI programs are launched; {ranks} is replaced by the number of processes */
  mpi_command: string;
}

/** What a profile keeps of an engine installed and verified by the application. */
export interface EngineManifest {
  id?: string;
  wrf_version?: string;
  wps_version?: string;
  wrf_commit?: string;
  wps_commit?: string;
  dependency_mode?: "managed" | "system";
  versions?: Record<string, string>;
  packages?: Record<string, string>;
  package_count?: number;
  geography?: { id: string; path: string; datasets: string[]; complements: string[] };
  platform?: string;
  created_at?: string;
  verified_at?: string;
  root?: string;
  kit?: string;
  installation_id?: string;
  build_adaptations?: string[];
}

export interface ComputeProfile {
  id: string;
  name: string;
  kind: ProfileKind;
  install: EngineInstall;
  resources: Resources;
  wsl_distro: string;
  /** Linux user for WSL commands (the managed engine's non-root user); empty: the default user */
  wsl_user: string;
  notes: string;
  /** Empty for an engine configured by hand */
  engine_manifest: EngineManifest;
}

export interface ProfileWithStatus extends ComputeProfile {
  missing: string[];
  default: boolean;
}

export interface ProfilesResponse {
  profiles: ProfileWithStatus[];
  physical_cores: number;
}

export interface VerifyCheck {
  status: "ok" | "warn" | "fail";
  label: string;
  detail: string;
}

export interface VerifyResponse {
  reachable: boolean;
  checks: VerifyCheck[];
  error?: string;
  missing?: string[];
}

// --------------------------------------------------------------- settings

export interface Folders {
  input: string;
  observations: string;
  videos: string;
  reports: string;
  exports: string;
}

export interface Settings {
  data_root: string;
  folders: Folders;
  default_profile: string | null;
  language: "en" | "fr";
  cds_key_configured: boolean;
  cds_url: string;
  physical_cores: number;
}

export interface Health {
  status: string;
  version: string;
  profiles: number;
  default_profile: string | null;
  engine_ready: boolean;
  /** windows, linux or another system's name */
  platform?: string;
  /** window (own window), browser (Linux without a window toolkit) or server (owstudio serve) */
  mode?: "window" | "browser" | "server";
}

export interface StorageLocation {
  key: string;
  label: string;
  path: string;
  bytes: number;
}

export interface StorageRun {
  case: string;
  run: string;
  path: string;
  bytes: number;
  outputs_bytes: number;
  state: RunState;
}

export interface StorageUsage {
  data_root: string;
  /** Where the downloaded input data are: the engine's shared data folder when this computer sees it */
  downloads_root: string;
  free_bytes: number;
  folders: Folders;
  locations: StorageLocation[];
  runs: StorageRun[];
  settings_file: string;
}

export interface Job<R = unknown> {
  id: string;
  title: string;
  state: "running" | "succeeded" | "failed" | "cancelled";
  error: string | null;
  progress: number;
  started_at: string;
  finished_at: string | null;
  log: string;
  result: R | null;
}

// ------------------------------------------------------- map and helpers

export interface GeoFeature {
  type: "Feature";
  geometry:
    | { type: "Polygon"; coordinates: [number, number][][] }
    | { type: "Point"; coordinates: [number, number] }
    | { type: "LineString"; coordinates: [number, number][] };
  properties: {
    kind: "domain" | "turbine" | "probe";
    number?: number;
    dx?: number;
    farm?: string;
    farm_name?: string;
    farm_color?: string | null;
    farm_symbol?: FarmSymbol | "auto";
    color?: string;
    symbol?: FarmSymbol;
    icon?: string;
    count?: number;
    enabled?: boolean;
    label?: string;
    showLabel?: boolean;
    type?: number;
    name?: string;
    prefix?: string;
  };
}

export interface FeatureCollection {
  type: "FeatureCollection";
  features: GeoFeature[];
}

export interface CatalogEntry {
  id: string;
  name: string;
  origin: string | null;
  power_curve_type: string | null;
  cut_in_wind_speed: number | null;
  rated_wind_speed: number | null;
  cut_out_wind_speed: number | null;
  source: string;
  license: string;
  turbine: TurbineType;
  specific_power: number;
  max_cp: number;
}

export interface ParsedPoint {
  lat: number;
  lon: number;
  type: number | null;
  name: string | null;
}

export interface ParsedCoordinates {
  points: ParsedPoint[];
  skipped: number[];
  detected: string;
}

export interface CoordinateOptions {
  crs: "auto" | "latlon" | "lonlat" | "projected";
  epsg?: number | null;
  utm_zone?: number | null;
  southern?: boolean;
}

export interface OptionSchema {
  type: string;
  per_domain: boolean;
  dimension: string;
  default: Scalar;
  description: string;
  units: string;
}

export interface NamelistSchema {
  wrf_version: string;
  groups: Record<string, Record<string, OptionSchema>>;
}

export type NamelistFile = "namelist.input" | "namelist.wps";
export type StructuredNamelists = Record<NamelistFile, { generated: NamelistGroups; final: NamelistGroups }>;

// ---------------------------------------------------------------- results

export interface VariableInfo {
  label: string;
  units: string;
  colormap: string;
  diverging: boolean;
}

export interface ResultsSummary {
  run_id: string;
  /** True only when this run has a retained-time manifest, independent of migrated settings. */
  windowed?: boolean;
  name: string;
  start: string;
  end: string;
  domains: number[];
  farm_domain: number | null;
  has_control: boolean;
  hub_height_m: number;
  installed_mw: number;
  turbines: number;
  mean_power_mw: number | null;
  max_power_mw: number | null;
  energy_mwh: number | null;
  capacity_factor: number | null;
  ideal_mean_power_mw: number | null;
  wake_efficiency: number | null;
  version: number;
  times: Record<string, string[]>;
  variables: Record<string, VariableInfo>;
  /** Map fields available on each domain (the power only where the farm scheme ran) */
  fields?: Record<string, string[]>;
}

export interface FieldMeta extends VariableInfo {
  vmin: number;
  vmax: number;
  colors: string[];
  coordinates: [number, number][];
}

export type TimeRecord = { time: string } & Record<string, number | null | string>;

export interface TsLocation {
  name: string;
  prefix: string;
  domain: number;
  lat: number;
  lon: number;
  i: number;
  j: number;
  elevation: number;
  /** Hub height of the turbines it stands for (their mean when models differ) */
  hub_height_m?: number;
  has_control: boolean;
  /** Every location of the grid cell this series stands for (same series in WRF) */
  members?: { prefix: string; name: string; turbines?: number }[];
}

export interface TsIndex {
  hub_height_m: number;
  locations: TsLocation[];
}
