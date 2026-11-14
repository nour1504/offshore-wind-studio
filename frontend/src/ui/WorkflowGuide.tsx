import { Box, Button, Collapse, Group, Text } from "@mantine/core";
import { useLocalStorage } from "@mantine/hooks";
import { IconArrowRight, IconChevronDown, IconChevronUp, IconRoute } from "@tabler/icons-react";
import { useId } from "react";

import { sectionMessages } from "../app/sections";
import { defineMessages, useFormat, useT } from "../i18n";
import { href } from "../router";
import { Glide, useGlide } from "./Glide";

// Turbine models come before the farms: a farm places turbines of a model already defined
const steps = ["data", "domains", "turbines", "farms", "physics", "outputs", "run"] as const;
type Step = (typeof steps)[number];

const messages = defineMessages({
  en: {
    title: "Preparation guide",
    show: "Show guide",
    hide: "Hide guide",
    navigation: "Suggested preparation steps",
    position: "Step {current} of {total}",
    next: "Next: {step}",
    labels: { data: "Period & data", domains: "Domains", farms: "Wind farms", turbines: "Turbines", physics: "Physics", outputs: "Outputs", run: "WRF files" },
  },
  fr: {
    title: "Guide de préparation",
    show: "Afficher le guide",
    hide: "Masquer le guide",
    navigation: "Étapes de préparation suggérées",
    position: "Étape {current} sur {total}",
    next: "Suite : {step}",
    labels: { data: "Période et données", domains: "Domaines", farms: "Parcs", turbines: "Éoliennes", physics: "Physique", outputs: "Sorties", run: "Fichiers WRF" },
  },
});

/** A navigation aid, never a readiness indicator: visiting a step does not validate it. */
export function WorkflowGuide({ caseId, section }: { caseId: string; section: string }) {
  const t = useT(messages);
  const ts = useT(sectionMessages);
  const f = useFormat();
  const contentId = useId();
  const glide = useGlide();
  const [expanded, setExpanded] = useLocalStorage<boolean>({
    key: "ows-preparation-guide-visible",
    defaultValue: true,
    getInitialValueInEffect: false,
  });
  const index = steps.findIndex((step) => step === section);
  if (section !== "overview" && index < 0) return null;
  const current: Step | undefined = index >= 0 ? steps[index] : undefined;
  const next = steps[index + 1];
  const projectPath = (step: Step) => href(`projects/${encodeURIComponent(caseId)}/${step}`);

  return (
    <Box className="ows-workflow" maw="var(--ows-page-max)" mx="auto" mb={32} data-expanded={expanded || undefined}>
      <Group justify="space-between" gap="xs" className="ows-workflow-heading" wrap="nowrap">
        <Group gap="xs" wrap="nowrap" style={{ minWidth: 0 }}>
          <IconRoute size={16} stroke={1.7} aria-hidden="true" />
          <Text size="sm" fw={600}>{t("title")}</Text>
          {current && <Text size="xs" c="dimmed" className="ows-num" key={current}>{t("position", { current: f.number(index + 1, 0), total: f.number(steps.length, 0) })}</Text>}
        </Group>
        <Group gap="xs" wrap="nowrap">
          {/* The overview has its own next steps: no second, different suggestion here */}
          {next && current && (
            <Button component="a" href={projectPath(next)} variant="light" size="compact-sm" rightSection={<IconArrowRight size={15} aria-hidden="true" />} className="ows-next">
              {t("next", { step: ts(`project.${next}`) })}
            </Button>
          )}
          <Button
            variant="subtle"
            color="gray"
            size="compact-xs"
            aria-expanded={expanded}
            aria-controls={contentId}
            onClick={() => setExpanded((value) => !value)}
            rightSection={expanded ? <IconChevronUp size={14} aria-hidden="true" /> : <IconChevronDown size={14} aria-hidden="true" />}
          >
            {t(expanded ? "hide" : "show")}
          </Button>
        </Group>
      </Group>
      <Collapse expanded={expanded} id={contentId}>
        <nav aria-label={t("navigation")}>
          {/* A rail: numbered stops joined by a line; the marker slides to the current stop */}
          <ol className="ows-rail" ref={glide.parent}>
            <Glide glide={glide} active={current} className="ows-rail-glide" />
            {steps.map((step, stepIndex) => (
              <li key={step} className="ows-rail-stop" style={{ "--ows-i": stepIndex } as never}>
                <a ref={glide.item(step)} className="ows-workflow-step" href={projectPath(step)} aria-current={step === current ? "step" : undefined}>
                  <span className="ows-workflow-number" aria-hidden="true">{f.number(stepIndex + 1, 0)}</span>
                  <span className="ows-workflow-label">{t(`labels.${step}`)}</span>
                </a>
              </li>
            ))}
          </ol>
        </nav>
      </Collapse>
    </Box>
  );
}
