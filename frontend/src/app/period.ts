import type { Case, NamelistGroups } from "../api/types";

const WRF_DATES = new Set([...(["start", "end"] as const).flatMap(which => ["year", "month", "day", "hour", "minute", "second"].map(part => `${which}_${part}`)), "run_days", "run_hours", "run_minutes", "run_seconds"]);
const WPS_DATES = new Set(["start_date", "end_date"]);

/** Clear only settings now managed by the edited GUI period, including their indexed metadata. */
function clearOptions(groups: NamelistGroups, groupName: string, names: Set<string>) {
  for (const [group, options] of Object.entries(groups)) {
    if (group.toLowerCase() !== groupName) continue;
    for (const name of Object.keys(options)) {
      if (names.has(name.toLowerCase())) delete options[name];
      else if (["_start_index", "_complex"].includes(name.toLowerCase())) {
        const metadata = options[name];
        if (metadata && typeof metadata === "object" && !Array.isArray(metadata)) {
          for (const key of Object.keys(metadata)) if (names.has(key.toLowerCase())) delete metadata[key];
          if (!Object.keys(metadata).length) delete options[name];
        }
      }
    }
    if (!Object.keys(options).length) delete groups[group];
  }
}

/** Clears the imported dates and boundary interval that the edited period now manages. */
export function synchronizePeriod(previous: Case, next: Case): void {
  const datesChanged = previous.period.start !== next.period.start || previous.period.end !== next.period.end;
  const intervalChanged = previous.period.interval_seconds !== next.period.interval_seconds;
  if (datesChanged) {
    clearOptions(next.namelist_input, "time_control", WRF_DATES);
    clearOptions(next.namelist_wps, "share", WPS_DATES);
  }
  if (intervalChanged) {
    clearOptions(next.namelist_input, "time_control", new Set(["interval_seconds"]));
    clearOptions(next.namelist_wps, "share", new Set(["interval_seconds"]));
  }
}
