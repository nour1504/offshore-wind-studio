/**
 * The run whose results a page shows (every result page follows the same chosen run), with the
 * choice of run, of the run without turbines compared with it, and the import above the content, and an empty state when nothing is imported.
 */
import { Button, Group } from "@mantine/core";
import { IconChartLine, IconFileCode } from "@tabler/icons-react";
import type { ReactNode } from "react";

import { useResultsSummary } from "../../../api/results";
import { useRunHistory } from "../../../api/runs";
import type { ResultsSummary } from "../../../api/types";
import { useLoadedDraft } from "../../../app/CaseDraft";
import { defineMessages, useT } from "../../../i18n";
import { href, setParams, useRoute } from "../../../router";
import { EmptyState, ErrorState, LoadingState } from "../../../ui/States";
import { ImportOutputs } from "./ImportOutputs";
import { isNotFound } from "./queries";
import { ReferenceSelect } from "./ReferenceSelect";
import { RunSelect } from "./RunSelect";
import { sharedMessages } from "./shared";

const messages = defineMessages({
  en: { empty: "No outputs", files: "WRF files", run: "Run" },
  fr: { empty: "Aucune sortie", files: "Fichiers WRF", run: "Calcul" },
});

export function ResultContext({ children }: { children: (summary: ResultsSummary) => ReactNode }) {
  const { caseId, draft } = useLoadedDraft();
  const t = useT(messages);
  const ts = useT(sharedMessages);
  const route = useRoute();
  const history = useRunHistory(caseId);
  const query = useResultsSummary(caseId, route.params.get("run"));
  if (query.isLoading) return <LoadingState rows={5} />;
  if (query.error) {
    return isNotFound(query.error) ? (
      <EmptyState icon={<IconChartLine size={26} stroke={1.5} />} title={t("empty")}
        action={<Group gap="xs"><ImportOutputs /><Button component="a" variant="default" leftSection={<IconFileCode size={16} />} href={href(`projects/${caseId}/run`)}>{t("files")}</Button></Group>} />
    ) : (
      <ErrorState error={query.error} onRetry={() => void query.refetch()} />
    );
  }
  if (!query.data) return null;
  const summary = query.data;
  // The comparison without turbines is offered when the run has turbine power
  const turbinePower = summary.turbines > 0 && summary.mean_power_mw !== null;
  return (
    <>
      <Group justify="space-between" align="flex-end" gap="md" wrap="wrap" className="ows-results-head">
        <Group gap="md" wrap="wrap" align="flex-end" style={{ flex: "1 1 auto", minWidth: 0 }}>
          <RunSelect label={turbinePower ? ts("withFarm") : t("run")} runs={history.data ?? []} value={summary.run_id} onChange={(run) => setParams({ run })} farmNames={Object.fromEntries(draft.farms.map((farm) => [farm.id, farm.name]))} />
          {turbinePower && <ReferenceSelect caseId={caseId} runId={summary.run_id} />}
        </Group>
        <ImportOutputs compact />
      </Group>
      {children(summary)}
    </>
  );
}
