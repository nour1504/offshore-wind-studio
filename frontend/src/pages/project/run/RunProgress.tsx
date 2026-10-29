/**
 * Where the calculation of the extracted files stands: step, window n/N, instant reached, time
 * left. Read from the files the scripts write (backend core/method/progress.py); nothing is
 * launched from here. Read again every 10 s while it runs.
 */
import { SimpleGrid, Stack, Text } from "@mantine/core";

import { type RunProgress as Progress, useRunProgress } from "../../../api/method";
import { defineMessages, useFormat, useT } from "../../../i18n";
import { Fold } from "../../../ui/Fold";

const messages = defineMessages({
  en: {
    title: "Calculation",
    step: "Step",
    window: "Window",
    reached: "Simulated",
    left: "Time left",
    states: { running: "Running", stopped: "Stopped", done: "Done", error: "Error" },
    download: "Download",
  },
  fr: {
    title: "Calcul",
    step: "Étape",
    window: "Fenêtre",
    reached: "Simulé",
    left: "Restant",
    states: { running: "En cours", stopped: "Arrêté", done: "Terminé", error: "Erreur" },
    download: "Téléchargement",
  },
});

function Figure({ label, value }: { label: string; value: string }) {
  return (
    <Stack gap={6} className="ows-kpi">
      <Text size="xs" c="dimmed" fw={500}>{label}</Text>
      <Text className="ows-num ows-run-value">{value}</Text>
    </Stack>
  );
}

export function RunProgress({ caseId, folder }: { caseId: string; folder: string }) {
  const t = useT(messages);
  const f = useFormat();
  const query = useRunProgress(caseId, folder, true);
  const p: Progress | undefined = query.data;
  if (!p || p.state === "none") return null;
  const step = p.step === "download" ? (p.download?.expected ? `${t("download")} ${p.download.done}/${p.download.expected}` : t("download")) : p.step ? `${p.step}.exe` : "–";
  const reached = p.reached ? new Date(p.reached) : null;
  const instant = reached ? `${String(reached.getUTCDate()).padStart(2, "0")}/${String(reached.getUTCMonth() + 1).padStart(2, "0")} ${String(reached.getUTCHours()).padStart(2, "0")}:${String(reached.getUTCMinutes()).padStart(2, "0")}` : "–";
  const left = p.left_s === null || p.left_s === undefined ? "–" : `≈ ${f.duration(p.left_s)}`;
  // Closed, its state and the time left stay in view
  const aside = (
    <span className="ows-run-state" data-state={p.state}>
      <span className="ows-run-dot" />
      {t(`states.${p.state}`)}
      {left !== "–" && ` · ${left}`}
    </span>
  );
  return (
    <Fold title={t("title")} aside={aside}>
      <Stack gap="sm">
        <SimpleGrid cols={{ base: 2, md: 4 }} spacing={0} className="ows-kpis">
          <Figure label={t("step")} value={p.state === "done" ? "–" : step} />
          <Figure label={t("window")} value={p.windows ? `${p.state === "done" ? p.windows : p.window} / ${p.windows}` : "–"} />
          <Figure label={t("reached")} value={instant} />
          <Figure label={t("left")} value={left} />
        </SimpleGrid>
        {p.state === "error" && p.error && <Text size="sm" c="red" ff="monospace">{p.error}</Text>}
      </Stack>
    </Fold>
  );
}
