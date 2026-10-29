import type { Farm } from "../../../api/types";

/** Mirrors core.tslist.turbine_labels. Preserve unique labels and qualify collisions,
 * reserving unique original labels before generating any farm/label suffixes. */
export function turbineLabels(farms: readonly Farm[]): Map<string, string> {
  const entries = farms.flatMap((farm) =>
    farm.turbines.map((turbine, index) => ({
      key: `${farm.id}:${index + 1}`,
      farm: farm.id,
      label: turbine.id || `${farm.id}-${index + 1}`,
    })),
  );
  const counts = new Map<string, number>();
  for (const { label } of entries) counts.set(label, (counts.get(label) ?? 0) + 1);
  const used = new Set(entries.filter(({ label }) => counts.get(label) === 1).map(({ label }) => label));
  const labels = new Map<string, string>();
  for (const entry of entries) {
    if (counts.get(entry.label) === 1) {
      labels.set(entry.key, entry.label);
      continue;
    }
    const base = `${entry.farm}/${entry.label}`;
    let candidate = base;
    let suffix = 2;
    while (used.has(candidate)) candidate = `${base}#${suffix++}`;
    used.add(candidate);
    labels.set(entry.key, candidate);
  }
  return labels;
}
