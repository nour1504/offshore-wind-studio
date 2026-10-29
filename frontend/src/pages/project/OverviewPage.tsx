import { List, Stack, Text, Textarea, TextInput } from "@mantine/core";
import { IconAlertTriangle, IconCircleX } from "@tabler/icons-react";

import { useRunHistory } from "../../api/runs";

import { useLoadedDraft } from "../../app/CaseDraft";
import { NextSteps } from "./overview/NextSteps";
import { common } from "../../i18n/common";
import { defineMessages, useFormat, useT } from "../../i18n";
import { href } from "../../router";
import { DataTable } from "../../ui/DataTable";
import { Page } from "../../ui/Page";
import { Fold } from "../../ui/Fold";
import { StateBadge, Stat, StatGrid } from "../../ui/Stat";

const messages = defineMessages({
  en: {
    description: "Project status, remaining steps and latest runs.",
    project: "Project",
    name: "Name",
    notes: "Description",
    notesPlaceholder: "Purpose of the study, sources, assumptions…",
    period: "Period",
    spinUp: "plus {n} h of spin-up before each window",
    domains: "Domains",
    finest: "finest grid {dx} km",
    farms: "Wind farms",
    farmsValue: "{on} of {all}",
    noFarms: "None",
    turbines: "{n} turbines simulated",
    noScheme: "no farm parameterization",
    lastRun: "Last run",
    checks: "Checks",
    errors: "To fix before running",
    warnings: "To review",
    steps: "Before running",
    runs: "Imported results",
    noRuns: "No results",
    when: "Imported on",
    label: "Label",
    state: "State",
    profile: "Compute profile",
  },
  fr: {
    description: "État du projet, étapes restantes et derniers calculs.",
    project: "Projet",
    name: "Nom",
    notes: "Description",
    notesPlaceholder: "Objet de l'étude, sources, hypothèses…",
    period: "Période",
    spinUp: "plus {n} h de mise en route avant chaque fenêtre",
    domains: "Domaines",
    finest: "maille la plus fine {dx} km",
    farms: "Parcs éoliens",
    farmsValue: "{on} sur {all}",
    noFarms: "Aucun",
    turbines: "{n} éoliennes simulées",
    noScheme: "pas de paramétrisation de parc",
    lastRun: "Dernier calcul",
    checks: "Vérifications",
    errors: "À corriger avant de lancer",
    warnings: "À vérifier",
    steps: "Avant de lancer",
    runs: "Résultats importés",
    noRuns: "Aucun résultat",
    when: "Importé le",
    label: "Libellé",
    state: "État",
    profile: "Profil de calcul",
  },
});

export default function OverviewPage() {
  const t = useT(messages);
  const tc = useT(common);
  const f = useFormat();
  const { caseId, draft, update, issues } = useLoadedDraft();
  const history = useRunHistory(caseId);

  const hours = (new Date(draft.period.end).getTime() - new Date(draft.period.start).getTime()) / 3.6e6;
  const dx: number[] = [];
  draft.grid.domains.forEach((d, i) => {
    dx.push(i === 0 ? draft.grid.dx : dx[d.parent_id - 1] / d.parent_grid_ratio);
  });
  const enabled = draft.farms.filter((farm) => farm.enabled);
  const simulated = draft.farm_scheme ? enabled.reduce((n, farm) => n + farm.turbines.length, 0) : 0;
  const errors = issues.filter((i) => i.severity === "error");
  const warnings = issues.filter((i) => i.severity === "warning");
  const last = history.data?.[0];

  return (
    <Page title={draft.name} help="project-overview" className="ows-overview">
      <StatGrid>
        <Stat
          label={t("period")}
          value={`${f.number(hours, 0)} h`}
          hint={`${f.dateTime(draft.period.start)} → ${f.dateTime(draft.period.end)} · ${t("spinUp", { n: draft.spin_up_hours })}`}
        />
        <Stat
          label={t("domains")}
          value={draft.grid.domains.length || t("noFarms")}
          hint={draft.grid.domains.length ? t("finest", { dx: f.number(Math.min(...dx) / 1000, 2) }) : undefined}
        />
        <Stat
          label={t("farms")}
          value={draft.farms.length ? (enabled.length === draft.farms.length ? String(draft.farms.length) : t("farmsValue", { on: enabled.length, all: draft.farms.length })) : t("noFarms")}
          hint={draft.farm_scheme ? `${draft.farm_scheme.scheme === "mav" ? "MAV" : "Fitch"} · ${t("turbines", { n: simulated })}` : t("noScheme")}
        />
        <Stat
          label={t("lastRun")}
          value={last ? <StateBadge state={last.state} size="md" /> : "–"}
          hint={last?.started_at ? f.dateTime(last.started_at) : undefined}
        />
      </StatGrid>

      <NextSteps caseId={caseId} draft={draft} runs={history.data?.length ?? 0} />

      <Fold title={t("project")}>
          <Stack>
            <TextInput
              label={t("name")}
              value={draft.name}
              onChange={(e) => {
                const value = e.currentTarget.value;
                update((c) => {
                  c.name = value;
                });
              }}
            />
            <Textarea
              label={t("notes")}
              placeholder={t("notesPlaceholder")}
              autosize
              minRows={3}
              value={draft.description}
              onChange={(e) => {
                const value = e.currentTarget.value;
                update((c) => {
                  c.description = value;
                });
              }}
            />
          </Stack>
      </Fold>

      {/* Nothing to say when nothing is wrong (the engine is asked for in Compute only) */}
      {issues.length > 0 && <Fold title={t("checks")} aside={issues.length ? String(issues.length) : undefined}>
          <Stack gap="md">
            {errors.length > 0 && (
              <Stack gap={4}>
                <Text size="sm" fw={600} c="dimmed">
                  {t("errors")}
                </Text>
                <List spacing={4} size="sm" icon={<IconCircleX size={16} color="var(--ows-muted)" />}>
                  {errors.map((issue, i) => (
                    <List.Item key={i}>{issue.message}</List.Item>
                  ))}
                </List>
              </Stack>
            )}
            {warnings.length > 0 && (
              <Stack gap={4}>
                <Text size="sm" fw={600} c="dimmed">
                  {t("warnings")}
                </Text>
                <List spacing={4} size="sm" icon={<IconAlertTriangle size={16} color="var(--ows-muted)" />}>
                  {warnings.map((issue, i) => (
                    <List.Item key={i}>{issue.message}</List.Item>
                  ))}
                </List>
              </Stack>
            )}
          </Stack>
      </Fold>}

      {(history.data?.length ?? 0) > 0 && <Fold title={t("runs")} aside={String(history.data?.length ?? 0)}>
        <DataTable
          caption={t("runs")}
          rows={(history.data ?? []).slice(0, 5)}
          rowKey={(r) => r.run_id ?? ""}
          empty={history.isLoading ? tc("loading") : t("noRuns")}
          columns={[
            { key: "when", header: t("when"), render: (r) => f.dateTime(r.started_at ?? r.queued_at) },
            { key: "label", header: t("label"), render: (r) => r.label || (r.farms.length ? r.farms.join(" + ") : "–") },
          ]}
          onRowClick={(r) => {
            window.location.hash = href(`projects/${caseId}/results?run=${r.run_id}`);
          }}
        />
      </Fold>}
    </Page>
  );
}
