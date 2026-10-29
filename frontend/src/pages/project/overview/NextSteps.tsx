/**
 * What is done and what comes next in a project, in the order of the guide: the first step not
 * done is highlighted with a button to continue there.
 */
import { Box, Button, Group, Stack, Text, ThemeIcon } from "@mantine/core";
import { IconArrowRight, IconCheck } from "@tabler/icons-react";

import type { Case } from "../../../api/types";
import { defineMessages, useT } from "../../../i18n";
import { href } from "../../../router";

const messages = defineMessages({
  en: {
    title: "Next steps",
    continue: "Continue: {step}",
    steps: {
      domains: "Place the area to simulate",
      turbines: "Choose the turbine model",
      farms: "Place the wind farms",
      run: "Export the WRF files",
      results: "Look at the results",
    },
    hints: {
      domains: "One click on the map, at the centre of your study area.",
      turbines: "Size, power and curves of your turbines.",
      farms: "Where the turbines stand, on the map.",
      run: "Files and scripts for the cluster or a Linux computer.",
      results: "Production, wind at the points, maps.",
    },
  },
  fr: {
    title: "Prochaines étapes",
    continue: "Continuer : {step}",
    steps: {
      domains: "Placer la zone à simuler",
      turbines: "Choisir le modèle d'éolienne",
      farms: "Placer les parcs éoliens",
      run: "Exporter les fichiers WRF",
      results: "Regarder les résultats",
    },
    hints: {
      domains: "Un clic sur la carte, au centre de votre zone d'étude.",
      turbines: "Taille, puissance et courbes de vos éoliennes.",
      farms: "L'emplacement des éoliennes, sur la carte.",
      run: "Fichiers et scripts pour le cluster ou un ordinateur Linux.",
      results: "Production, vent aux points, cartes.",
    },
  },
});

type Step = keyof typeof messages.en.steps;

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
  const order: Step[] = ["domains", "turbines", "farms", "run", "results"];
  const next = order.find((step) => !done[step]) ?? "results";
  const path = (step: Step) => `projects/${encodeURIComponent(caseId)}/${step}`;
  return (
    <Box component="section" className="ows-next-steps">
      <Stack gap="md">
        <Group justify="space-between" wrap="wrap" gap="sm">
          <Text fw={600} size="md">{t("title")}</Text>
          <Button component="a" href={href(path(next))} variant="light" size="sm" rightSection={<IconArrowRight size={16} />}>
            {t("continue", { step: t(`steps.${next}`) })}
          </Button>
        </Group>
        <Box className="ows-next-steps-list">
          {order.map((step, index) => {
            const current = step === next;
            return (
              <Group key={step} gap="sm" wrap="nowrap" className="ows-step" data-state={done[step] ? "done" : current ? "current" : "next"}>
                <ThemeIcon size={26} radius="xl" className="ows-step-icon" variant={done[step] ? "light" : current ? "light" : "default"}>
                  {done[step] ? <IconCheck size={16} /> : <Text size="sm" fw={600}>{index + 1}</Text>}
                </ThemeIcon>
                <Stack gap={0}>
                  <Text size="sm" fw={current ? 650 : 500}>
                    <a href={href(path(step))} style={{ color: "inherit", textDecoration: "none" }}>{t(`steps.${step}`)}</a>
                  </Text>
                </Stack>
              </Group>
            );
          })}
        </Box>
      </Stack>
    </Box>
  );
}
