/**
 * Rules of the outputs of a case, mirrored from the backend so that the page can explain them
 * while typing: Registry names of iofields.txt, the tslist file and its locations.
 *
 * Backend references: owstudio.core.case.model (Outputs, TimeSeriesPoint), owstudio.core.tslist,
 * owstudio.core.namelist.generate (iofields_text).
 */
import type { Case, Outputs, TimeSeries, TimeSeriesPoint } from "../../../api/types";
import { parseUtc } from "../../../i18n";

/** A WRF Registry variable name, as written in iofields files (REGISTRY_NAME). */
export const REGISTRY_NAME = /^[A-Za-z0-9_]{1,40}$/;
export const NAME_MAX = 25;
export const PREFIX_PATTERN = /^[A-Za-z0-9_]{1,5}$/;
/** Prefixes generated for the locations at the turbines (T0001…) and at their cells (C0001…). */
export const GENERATED_PREFIX = /^[TC]\d{4}$/;
/** Variables the Results pages read from the history files (owstudio.core.postproc). */
export const READ_BY_RESULTS = ["Times", "XLAT", "XLONG", "HGT", "U", "V", "PH", "PHB", "U10", "V10", "T2", "PBLH", "POWER"];

export const sameName = (a: string, b: string) => a.toLowerCase() === b.toLowerCase();
export const hasName = (list: string[], name: string) => list.some((n) => sameName(n, name));

/** Contents of iofields.txt, exactly as the backend writes it. */
export function iofieldsText(outputs: Outputs): string {
  const lines: string[] = [];
  if (outputs.add.length) lines.push(`+:h:0:${outputs.add.join(",")}`);
  if (outputs.remove.length) lines.push(`-:h:0:${outputs.remove.join(",")}`);
  return lines.map((line) => `${line}\n`).join("");
}

/** Hours between the start and the end of the period. */
export function simulatedHours(c: Case): number {
  const hours = (parseUtc(c.period.end).getTime() - parseUtc(c.period.start).getTime()) / 3.6e6;
  return Number.isFinite(hours) && hours > 0 ? hours : 0;
}

/** Output times of one domain over the period: the start, then every interval. */
export function historyTimes(c: Case): number {
  const hours = simulatedHours(c);
  if (!hours || c.history_interval_minutes <= 0) return 0;
  return Math.floor((hours * 60) / c.history_interval_minutes) + 1;
}

export const defaultTimeSeries = (c: Case): TimeSeries => ({
  turbines: c.farms.some((farm) => farm.turbines.length > 0) ? "cells" : "none",
  points: [],
  max_levels: 15,
});

export type PointProblem =
  | "nameRequired"
  | "nameTooLong"
  | "prefixInvalid"
  | "prefixTaken"
  | "prefixReserved"
  | "latInvalid"
  | "lonInvalid";

export interface PointProblems {
  name?: PointProblem;
  prefix?: PointProblem;
  lat?: PointProblem;
  lon?: PointProblem;
}

/**
 * What is wrong with a location, field by field. `others` are the prefixes of the other
 * locations: file names are compared without case, as on Windows.
 */
export function pointProblems(
  point: { name: string; prefix: string; lat: number | string; lon: number | string },
  others: string[],
): PointProblems {
  const problems: PointProblems = {};
  const name = point.name.trim();
  if (!name) problems.name = "nameRequired";
  else if (name.length > NAME_MAX) problems.name = "nameTooLong";
  if (!PREFIX_PATTERN.test(point.prefix)) problems.prefix = "prefixInvalid";
  else if (GENERATED_PREFIX.test(point.prefix)) problems.prefix = "prefixReserved";
  else if (others.some((p) => sameName(p, point.prefix))) problems.prefix = "prefixTaken";
  const lat = typeof point.lat === "number" ? point.lat : Number.parseFloat(point.lat);
  const lon = typeof point.lon === "number" ? point.lon : Number.parseFloat(point.lon);
  if (point.lat === "" || !Number.isFinite(lat) || lat < -90 || lat > 90) problems.lat = "latInvalid";
  if (point.lon === "" || !Number.isFinite(lon) || lon < -180 || lon > 180) problems.lon = "lonInvalid";
  return problems;
}

export const isValid = (problems: PointProblems) => Object.keys(problems).length === 0;

/**
 * A five-character prefix made from a name, not used yet. `taken` holds the prefixes in lower
 * case and receives the new one, so that a list of names gets distinct prefixes.
 */
export function prefixFor(name: string, taken: Set<string>): string {
  const base = (name.toUpperCase().replace(/[^A-Z0-9_]/g, "") || "P").slice(0, 5);
  let prefix = base;
  for (let n = 1; taken.has(prefix.toLowerCase()) || GENERATED_PREFIX.test(prefix); n++) {
    const suffix = String(n);
    prefix = `${base.slice(0, 5 - suffix.length)}${suffix}`;
  }
  taken.add(prefix.toLowerCase());
  return prefix;
}

/** One line of the tslist file. */
export interface TslistLocation {
  name: string;
  prefix: string;
  lat: number;
  lon: number;
}

/**
 * Reads the tslist text built by the server: three header lines, then name (25 characters),
 * prefix, latitude and longitude separated by spaces.
 */
export function parseTslist(text: string | undefined): TslistLocation[] {
  if (!text) return [];
  return text
    .split("\n")
    .filter((line) => line.trim() && !line.startsWith("#"))
    .map((line) => {
      const [prefix = "", lat = "", lon = ""] = line.slice(26).trim().split(/\s+/);
      return { name: line.slice(0, 25).trim(), prefix, lat: Number(lat), lon: Number(lon) };
    });
}

/** Prefixes that appear more than once, in lower case. */
export function duplicatePrefixes(prefixes: string[]): Set<string> {
  const seen = new Set<string>();
  const duplicates = new Set<string>();
  for (const prefix of prefixes) {
    const key = prefix.toLowerCase();
    if (seen.has(key)) duplicates.add(key);
    seen.add(key);
  }
  return duplicates;
}

/** Turbines of every farm, enabled or not: the backend writes a location for each of them. */
export const turbineCount = (c: Case) => c.farms.reduce((n, farm) => n + farm.turbines.length, 0);

/** Rounds coordinates picked on the map to about one metre. */
export const roundCoordinate = (value: number) => Math.round(value * 1e5) / 1e5;

export type NewPoint = Omit<TimeSeriesPoint, "lat" | "lon"> & { lat: number | string; lon: number | string };
