import { Stack } from "@mantine/core";

import { useLoadedDraft } from "../../app/CaseDraft";
import { sectionMessages } from "../../app/sections";
import { useT } from "../../i18n";
import { Page } from "../../ui/Page";
import { BreakdownPanel } from "./results/BreakdownPanel";
import { Kpis } from "./results/Kpis";
import { LocationsSection } from "./results/LocationsSection";
import { MapPanel } from "./results/MapPanel";
import { PowerPanel } from "./results/PowerPanel";
import { ResultContext } from "./results/ResultContext";

/**
 * Results of a run: four key figures, then the farm power, the energy of each farm, the map of
 * the fields and the measurement points, each in its own block.
 */
export default function ResultsPage() {
  const t = useT(sectionMessages);
  const { caseId } = useLoadedDraft();
  return (
    <Page title={t("project.results")} help="results" fluid>
      <ResultContext>{(summary) => {
        const power = summary.turbines > 0 && summary.farm_domain !== null && summary.mean_power_mw !== null;
        return (
          <Stack gap={32}>
            {power && <Kpis summary={summary} />}
            {power && <PowerPanel caseId={caseId} summary={summary} />}
            {power && <BreakdownPanel caseId={caseId} summary={summary} />}
            <MapPanel caseId={caseId} summary={summary} />
            <LocationsSection caseId={caseId} runId={summary.run_id} summary={summary} />
          </Stack>
        );
      }}</ResultContext>
    </Page>
  );
}
