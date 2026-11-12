/**
 * The run without turbines compared with the run shown, for the wake losses: none, the one
 * imported with it, or any run without turbines on the same grid, of this project or another.
 */
import { Select } from "@mantine/core";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { get, put } from "../../../api/client";
import { defineMessages, useFormat, useT } from "../../../i18n";
import { sharedMessages } from "./shared";

const messages = defineMessages({
  en: { none: "None", included: "Imported with this run" },
  fr: { none: "Aucun", included: "Importé avec ce calcul" },
});

interface Choice { kind: "run" | "included" | "none"; case_id?: string; run_id?: string }
interface Options {
  current: Choice;
  included: boolean;
  options: { case_id: string; case_name: string; run_id: string; finished_at: string | null }[];
}

const value = (choice: Choice) => (choice.kind === "run" ? `run:${choice.case_id}:${choice.run_id}` : choice.kind);

export function ReferenceSelect({ caseId, runId }: { caseId: string; runId: string }) {
  const t = useT(messages);
  const ts = useT(sharedMessages);
  const f = useFormat();
  const client = useQueryClient();
  const url = `/api/cases/${encodeURIComponent(caseId)}/runs/${encodeURIComponent(runId)}/reference`;
  const query = useQuery({ queryKey: ["reference", caseId, runId], queryFn: () => get<Options>(url) });
  const choose = useMutation({
    mutationFn: (next: string) => {
      const [kind, otherCase = "", otherRun = ""] = next.split(":");
      return put<Options>(url, { kind, case_id: otherCase, run_id: otherRun });
    },
    // Every result of the run depends on it: energy, losses, maps, analyses
    onSuccess: () => void client.invalidateQueries(),
  });
  const data = query.data;
  // No run without turbines to choose from: no choice at all
  if (data && !data.included && !data.options.length && data.current.kind === "none") return null;
  const options = [
    { value: "none", label: t("none") },
    ...(data?.included ? [{ value: "included", label: t("included") }] : []),
    ...(data?.options ?? []).map((o) => ({
      value: `run:${o.case_id}:${o.run_id}`,
      // The project is named only when it is another one
      label: `${o.finished_at ? f.dateTime(o.finished_at) : o.run_id}${o.case_id === caseId ? "" : ` · ${o.case_name}`}`,
    })),
  ];
  return (
    <Select
      label={ts("withoutFarm")}
      w={{ base: "100%", sm: 240 }}
      data={options}
      value={data ? value(data.current) : null}
      onChange={(next) => next && choose.mutate(next)}
      disabled={!data || choose.isPending}
      allowDeselect={false}
      checkIconPosition="right"
      error={choose.error ? String(choose.error.message) : undefined}
    />
  );
}
