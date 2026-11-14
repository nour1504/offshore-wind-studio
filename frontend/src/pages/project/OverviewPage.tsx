import { List, Stack, Text, Textarea, TextInput } from "@mantine/core";
import { IconAlertTriangle, IconCircleX } from "@tabler/icons-react";

import { useRunHistory } from "../../api/runs";

import { useLoadedDraft } from "../../app/CaseDraft";
import { NextSteps } from "./overview/NextSteps";
import { common } from "../../i18n/common";
import { defineMessages, hoursBetween, useFormat, useT } from "../../i18n";
import { href } from "../../router";
import { DataTable } from "../../ui/DataTable";
import { Page } from "../../ui/Page";
import { Fold } from "../../ui/Fold";
import { StateLine, Stat, StatGrid } from "../../ui/Stat";

const messages = defineMessages({
  en: {
    project: "Project",
    name: "Name",
    notes: "Description",
    notesPlaceholder: "Purpose of the study, sources, assumptions…",
    period: "Period",
    domains: "Domains",
    finest: "Finest grid spacing",
    farms: "Wind farms",
    turbines: "Turbines",
    scheme: "Parameterization",
    lastRun: "Last run",
    checks: "Checks",
    errors: "To fix before running",
    warnings: "To review",
    runs: "Imported results",
    noRuns: "No results",
    when: "Imported on",
    label: "Label",
  },
  fr: {
    project: "Projet",
    name: "Nom",
    notes: "Description",
    notesPlaceholder: "Objet de l'étude, sources, hypothèses…",
    period: "Période",
    domains: "Domaines",
    finest: "Maille la plus fine",
    farms: "Parcs",
    turbines: "Éoliennes",
    scheme: "Paramétrisation",
    lastRun: "Dernier calcul",
    checks: "Vérifications",
    errors: "À corriger avant de lancer",
    warnings: "À vérifier",
    runs: "Résultats importés",
    noRuns: "Aucun résultat",
    when: "Importé le",
    label: "Libellé",
  },
});

export default function OverviewPage() {
  const t = useT(messages);
  const tc = useT(common);
  const f = useFormat();
  const { caseId, draft, update, issues } = useLoadedDraft();
  const history = useRunHistory(caseId);

  const hours = hoursBetween(draft.period.start, draft.period.end);
  const dx: number[] = [];
  draft.grid.domains.forEach((d, i) => {
    dx.push(i === 0 ? draft.grid.dx : dx[d.parent_id - 1] / d.parent_grid_ratio);
  });
  const enabled = draft.farms.filter((farm) => farm.enabled);
  const turbines = enabled.reduce((n, farm) => n + farm.turbines.length, 0);
  const scheme = draft.farm_scheme ? (draft.farm_scheme.scheme === "mav" ? "MAV" : "Fitch") : null;
  const errors = issues.filter((i) => i.severity === "error");
  const warnings = issues.filter((i) => i.severity === "warning");
  const last = history.data?.[0];

  return (
    <Page title={draft.name} help="project-overview" className="ows-overview">
      <StatGrid cols={{ base: 2, sm: 4, lg: 7 }}>
        <Stat label={t("period")} filled={hours > 0} value={hours > 0 ? f.number(hours, 0) : "–"} unit={hours > 0 ? "h" : undefined} />
        <Stat label={t("domains")} filled={dx.length > 0} order={1} value={dx.length || "–"} />
        <Stat label={t("finest")} filled={dx.length > 0} order={2} value={dx.length ? f.number(Math.min(...dx) / 1000, 2) : "–"} unit={dx.length ? "km" : undefined} />
        <Stat label={t("farms")} filled={draft.farms.length > 0} order={3} value={!draft.farms.length ? "–" : enabled.length === draft.farms.length ? draft.farms.length : `${enabled.length}/${draft.farms.length}`} />
        <Stat label={t("turbines")} filled={turbines > 0} order={4} value={turbines ? f.number(turbines, 0) : "–"} />
        <Stat label={t("scheme")} filled={Boolean(scheme)} order={5} value={scheme ?? "–"} />
        <Stat label={t("lastRun")} filled={Boolean(last)} order={6} value={last ? <StateLine state={last.state} size="md" /> : "–"} />
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
