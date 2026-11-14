/**
 * The Exporter tab of a run with its choice already made: the pages that draw a series link to it
 * (their own download buttons are gone), so that every file comes from one place, named by its
 * source.
 */
import { href } from "../../../router";
import { parseHeights } from "../../../ui/heights";

export interface ExportTarget {
  panel: "tslist" | "wrfout";
  /** tslist: turbine labels or tslist prefixes (every point when left out) */
  points?: string[];
  quantities?: string[];
  heights?: number[];
  average?: number;
  layout?: "long" | "wide";
  /** wrfout: one variable at one point */
  variable?: string;
  domain?: number;
  height?: number | null;
  stage?: "main" | "control";
  location?: string;
  lat?: number | null;
  lon?: number | null;
}

/** The run is the latest with outputs when none is given. */
export function exportHref(caseId: string, run: string | null, target: ExportTarget): string {
  const params = new URLSearchParams();
  const put = (key: string, value: string | number | null | undefined) => {
    if (value !== undefined && value !== null && value !== "") params.set(key, String(value));
  };
  put("run", run);
  put("panel", target.panel);
  put("points", target.points?.join(","));
  put("quantities", target.quantities?.join(","));
  put("heights", target.heights?.map((h) => Math.round(h * 10) / 10).join(","));
  put("average", target.average);
  put("layout", target.layout);
  put("variable", target.variable);
  put("domain", target.domain);
  put("height", target.height);
  put("stage", target.stage);
  put("location", target.location);
  put("lat", target.lat);
  put("lon", target.lon);
  return href(`projects/${encodeURIComponent(caseId)}/export?${params.toString()}`);
}

/** What a link asked for, read once when the tab opens. */
export function readTarget(params: URLSearchParams) {
  const list = (key: string) => params.get(key)?.split(",").map((v) => v.trim()).filter(Boolean) ?? null;
  const number = (key: string) => {
    const value = params.get(key);
    return value === null || value === "" || !Number.isFinite(Number(value)) ? null : Number(value);
  };
  const panel = params.get("panel");
  const layout = params.get("layout");
  const stage = params.get("stage");
  return {
    panel: panel === "tslist" || panel === "wrfout" ? panel : null,
    tslist: {
      points: list("points"),
      quantities: list("quantities"),
      // The numbers of a link are written with a point
      heights: parseHeights(list("heights")?.join(" ") ?? "", "en"),
      average: number("average"),
      layout: layout === "long" || layout === "wide" ? (layout as "long" | "wide") : null,
    },
    wrfout: {
      variable: params.get("variable"),
      domain: number("domain"),
      height: number("height"),
      stage: stage === "control" ? ("control" as const) : ("main" as const),
      location: params.get("location"),
      lat: number("lat"),
      lon: number("lon"),
    },
  };
}

export type ExportInitial = ReturnType<typeof readTarget>;
