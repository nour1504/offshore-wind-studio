/**
 * What is done and what comes next in a project, in the order of the guide: a vertical list of the
 * steps, ticked as they are done, the first one left to do standing out. Each step leads to its page.
 */
import { Paper, Text, VisuallyHidden } from "@mantine/core";
import type { CSSProperties } from "react";

import type { Case } from "../../../api/types";
import { defineMessages, useT } from "../../../i18n";
import { href } from "../../../router";
import { DrawnCheck } from "../../../ui/DrawnCheck";
import { Spec } from "../../../ui/Fold";

const messages = defineMessages({
  en: {
    title: "Next steps",
    done: "done",
    steps: {
      domains: "Place the area to simulate",
      turbines: "Choose the turbine type",
      farms: "Place the wind farms",
      run: "Export the WRF files",
      results: "Look at the results",
    },
  },
  fr: {
    title: "Prochaines étapes",
    done: "fait",
    steps: {
      domains: "Placer la zone à simuler",
      turbines: "Choisir le type d'éolienne",
      farms: "Placer les parcs éoliens",
      run: "Exporter les fichiers WRF",
      results: "Regarder les résultats",
    },
  },
});

type Step = keyof typeof messages.en.steps;
const ORDER: Step[] = ["domains", "turbines", "farms", "run", "results"];

export function NextSteps({ caseId, draft, runs }: { caseId: string; draft: Case; runs: number }) {
  const t = useT(messages);
  const turbines = draft.farms.reduce((n, farm) => n + farm.turbines.length, 0);
  const done: Record<Step, boolean> = {
    domains: draft.grid.domains.length > 0,
    // Turbines already placed use a model (WRF's built-in one when the project defines none)
    turbines: Object.keys(draft.turbine_types).length > 0 || turbines > 0,
    farms: turbines > 0,
    run: runs > 0,
    results: false,
  };
  const next = ORDER.find((step) => !done[step]) ?? "results";
  const count = ORDER.filter((step) => done[step]).length;
  const path = (step: Step) => `projects/${encodeURIComponent(caseId)}/${step}`;
  return (
    <Paper component="section" withBorder radius="lg" className="ows-next-steps" aria-label={t("title")}>
      <Text fw={600} className="ows-next-steps-title">{t("title")}</Text>
      <Spec value={count} unit={`/ ${ORDER.length}`}>
        <ol className="ows-checklist">
          {ORDER.map((step, index) => {
            const state = done[step] ? "done" : step === next ? "current" : "next";
            return (
              <li key={step} className="ows-check" data-state={state} data-after={index > 0 && done[ORDER[index - 1]] ? "done" : undefined} style={{ "--k": index } as CSSProperties}>
                <span className="ows-check-dot" aria-hidden="true">{done[step] && <DrawnCheck size={14} />}</span>
                <a href={href(path(step))} className="ows-check-link" aria-current={state === "current" ? "step" : undefined}>
                  {t(`steps.${step}`)}
                  {done[step] && <VisuallyHidden> ({t("done")})</VisuallyHidden>}
                </a>
              </li>
            );
          })}
        </ol>
      </Spec>
    </Paper>
  );
}
