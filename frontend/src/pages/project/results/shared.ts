/**
 * What every section of the results page receives, and the words and helpers they share.
 *
 * Sections are independent: each one loads its own data from the run it is given, so that
 * other modules (energy, explorer, analyses) can add their own sections to the page.
 */
import type { ResultsSummary } from "../../../api/types";
import { defineMessages, type useFormat } from "../../../i18n";

export interface ResultsSectionProps {
  caseId: string;
  /** The run shown, as returned by the summary (never "latest") */
  runId: string;
  summary: ResultsSummary;
}

export const sharedMessages = defineMessages({
  en: {
    withFarm: "With turbines",
    withoutFarm: "Without turbines",
    withWakes: "With wakes",
    withoutWakes: "Without wakes",
    csv: "CSV",
    north: "N",
    south: "S",
    east: "E",
    west: "W",
    coordinates: "{lat} {ns}, {lon} {ew}",
    mapTime: "Map time",
    meanWith: "Mean with the farms:",
    meanWithout: "without:",
    change: "change:",
    meanOnly: "Mean:",
    meanWithWakes: "Mean with wakes:",
    meanWithoutWakes: "without wakes:",
  },
  fr: {
    withFarm: "Avec éoliennes",
    withoutFarm: "Sans éoliennes",
    withWakes: "Avec sillages",
    withoutWakes: "Sans sillages",
    csv: "CSV",
    north: "N",
    south: "S",
    east: "E",
    west: "O",
    coordinates: "{lat} {ns}, {lon} {ew}",
    mapTime: "Heure de la carte",
    meanWith: "Moyenne avec les parcs :",
    meanWithout: "sans :",
    change: "écart :",
    meanOnly: "Moyenne :",
    meanWithWakes: "Moyenne avec sillages :",
    meanWithoutWakes: "sans sillages :",
  },
});

type Format = ReturnType<typeof useFormat>;
type SharedT = (key: "coordinates" | "north" | "south" | "east" | "west", vars?: Record<string, string | number>) => string;

/** "55.4867° N, 7.8445° E" in the language of the interface. */
export function formatCoordinates(t: SharedT, f: Format, lat: number, lon: number, digits = 4): string {
  return t("coordinates", {
    lat: `${f.number(Math.abs(lat), digits)}°`,
    ns: lat < 0 ? t("south") : t("north"),
    lon: `${f.number(Math.abs(lon), digits)}°`,
    ew: lon < 0 ? t("west") : t("east"),
  });
}

/** Mean of the finite values of one column, or null when there is none. */
export function meanOf(rows: readonly object[], key: string): number | null {
  let sum = 0;
  let count = 0;
  for (const row of rows) {
    const value = (row as Record<string, unknown>)[key];
    if (typeof value === "number" && Number.isFinite(value)) {
      sum += value;
      count += 1;
    }
  }
  return count ? sum / count : null;
}

/** Mean over the rows where both columns have a value, so that the two means are comparable. */
export function pairedMeans(rows: readonly object[], a: string, b: string): { a: number; b: number } | null {
  let sumA = 0;
  let sumB = 0;
  let count = 0;
  for (const row of rows) {
    const r = row as Record<string, unknown>;
    const va = r[a];
    const vb = r[b];
    if (typeof va === "number" && typeof vb === "number" && Number.isFinite(va) && Number.isFinite(vb)) {
      sumA += va;
      sumB += vb;
      count += 1;
    }
  }
  return count ? { a: sumA / count, b: sumB / count } : null;
}

/** Times of a run id ("20251014-093000") as an ISO string in UTC, for runs without a status file. */
export function runIdTime(runId: string): string | null {
  const match = /^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})(\d{2})/.exec(runId);
  return match ? `${match[1]}-${match[2]}-${match[3]}T${match[4]}:${match[5]}:${match[6]}Z` : null;
}
