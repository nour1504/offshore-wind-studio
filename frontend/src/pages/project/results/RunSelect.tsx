/**
 * Choice of the run whose results are shown: the finished runs of the project, newest first,
 * by date.
 */
import { Select } from "@mantine/core";
import { useMemo } from "react";

import type { RunStatus } from "../../../api/types";
import { defineMessages, useFormat, useT } from "../../../i18n";
import { runIdTime } from "./shared";

const messages = defineMessages({
  en: { noFarm: "without turbines" },
  fr: { noFarm: "sans éoliennes" },
});

interface Props {
  /** Run history of the project, newest first */
  runs: RunStatus[];
  /** Run shown on the page */
  value: string;
  onChange: (runId: string) => void;
  /** Farm names by id, to describe scenario runs */
  farmNames: Record<string, string>;
  label: string;
}

export function RunSelect({ runs, value, onChange, farmNames, label }: Props) {
  const t = useT(messages);
  const f = useFormat();

  const options = useMemo(() => {
    const done = runs.filter((r): r is RunStatus & { run_id: string } => r.state === "succeeded" && Boolean(r.run_id));
    const list = done.map((r) => {
      const farms = r.farms.map((id) => farmNames[id] ?? id).join(" + ");
      // The date alone; "without turbines" tells apart an import of the run without turbines
      const detail = r.tags.source === "import" ? (r.farms.length ? "" : t("noFarm")) : r.label || farms || t("noFarm");
      const date = f.dateTime(r.finished_at ?? r.started_at ?? runIdTime(r.run_id));
      return { value: r.run_id, label: detail ? `${date} · ${detail}` : date };
    });
    // Results imported into a run folder have no run status: still offer the one shown
    if (!list.some((o) => o.value === value)) list.unshift({ value, label: f.dateTime(runIdTime(value)) });
    return list;
  }, [runs, value, farmNames, f, t]);

  return (
    <Select
      label={label}
      w={{ base: "100%", sm: 240 }}
      data={options}
      value={value}
      onChange={(next) => next && onChange(next)}
      allowDeselect={false}
      checkIconPosition="right"
    />
  );
}
