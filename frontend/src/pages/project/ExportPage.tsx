/**
 * Every file of the run's outputs from one place, named by its source: the tslist points (every
 * model time step, averaged or not) and the wrfout grid (one variable at a point, at each output
 * time). The pages that draw a series link here with their choice made (export/link.ts); the fold
 * of that choice is then open.
 */
import { Stack } from "@mantine/core";
import { useState } from "react";

import type { ResultsSummary } from "../../api/types";
import { useLoadedDraft } from "../../app/CaseDraft";
import { sectionMessages } from "../../app/sections";
import { useT } from "../../i18n";
import { useRoute } from "../../router";
import { Fold } from "../../ui/Fold";
import { Page } from "../../ui/Page";
import { readTarget } from "./export/link";
import { exportMessages } from "./export/messages";
import { TslistExport } from "./export/TslistExport";
import { WrfoutExport } from "./export/WrfoutExport";
import { ResultContext } from "./results/ResultContext";

function Exporter({ summary }: { summary: ResultsSummary }) {
  const { caseId } = useLoadedDraft();
  const t = useT(exportMessages);
  const route = useRoute();
  const [initial] = useState(() => readTarget(route.params));
  return (
    <Stack gap={32}>
      <Fold lazy title={t("tslist")} aside={t("tslistAside")} help="tslist" defaultOpen={initial.panel === "tslist"}>
        <TslistExport caseId={caseId} summary={summary} initial={initial.tslist} />
      </Fold>
      <Fold lazy title={t("wrfout")} aside={t("wrfoutAside")} defaultOpen={initial.panel === "wrfout"}>
        <WrfoutExport caseId={caseId} summary={summary} initial={initial.wrfout} />
      </Fold>
    </Stack>
  );
}

export default function ExportPage() {
  const t = useT(sectionMessages);
  return (
    <Page title={t("project.export")} help="data-export" fluid>
      <ResultContext>{(summary) => <Exporter key={summary.run_id} summary={summary} />}</ResultContext>
    </Page>
  );
}
