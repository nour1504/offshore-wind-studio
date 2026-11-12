/**
 * Where the calculation of the extracted files stands: step, window n/N, instant reached, time
 * left. Read from the files the scripts write (backend core/method/progress.py); nothing is
 * launched from here. Read again every 10 s while it runs.
 */
import { Stack, Text } from "@mantine/core";
import { motion } from "motion/react";

import { type RunProgress as Progress, useRunProgress } from "../../../api/method";
import { defineMessages, parseUtc, useFormat, useT } from "../../../i18n";
import { Fold } from "../../../ui/Fold";
import { Stat, StatGrid } from "../../../ui/Stat";

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

/** The share of the calculation done, as a ring that closes. */
function Ring({ share }: { share: number }) {
  return (
    <svg width={16} height={16} viewBox="0 0 16 16" className="ows-run-ring" aria-hidden="true">
      <circle cx={8} cy={8} r={6.2} className="ows-run-ring-track" />
      <motion.circle cx={8} cy={8} r={6.2} className="ows-run-ring-done" transform="rotate(-90 8 8)" initial={false} animate={{ pathLength: share }} transition={{ type: "spring", stiffness: 90, damping: 20 }} />
    </svg>
  );
}

export function RunProgress({ caseId, folder }: { caseId: string; folder: string }) {
  const t = useT(messages);
  const f = useFormat();
  const query = useRunProgress(caseId, folder, true);
  const p: Progress | undefined = query.data;
  if (!p || p.state === "none") return null;
  const step = p.step === "download" ? (p.download?.expected ? `${t("download")} ${p.download.done}/${p.download.expected}` : t("download")) : p.step ? `${p.step}.exe` : "–";
  const reached = p.reached ? parseUtc(p.reached) : null;
  const instant = reached ? `${String(reached.getUTCDate()).padStart(2, "0")}/${String(reached.getUTCMonth() + 1).padStart(2, "0")} ${String(reached.getUTCHours()).padStart(2, "0")}:${String(reached.getUTCMinutes()).padStart(2, "0")}` : "–";
  const left = p.left_s === null || p.left_s === undefined ? "–" : `≈ ${f.duration(p.left_s)}`;
  // Share done: the windows finished, plus the part of the current one reached
  const span = p.start && p.end && reached ? (reached.getTime() - parseUtc(p.start).getTime()) / Math.max(1, parseUtc(p.end).getTime() - parseUtc(p.start).getTime()) : 0;
  const share = p.state === "done" ? 1 : p.windows ? Math.min(1, ((p.done ?? Math.max(0, (p.window ?? 1) - 1)) + Math.min(1, Math.max(0, span))) / p.windows) : null;
  // Closed, its state and the time left stay in view
  const aside = (
    <span className="ows-run-state" data-state={p.state}>
      {share === null ? <span className="ows-run-dot" /> : <Ring share={share} />}
      <span className={p.state === "running" ? "ows-running" : undefined}>{t(`states.${p.state}`)}{left !== "–" && ` · ${left}`}</span>
    </span>
  );
  return (
    <Fold title={t("title")} aside={aside}>
      <Stack gap="sm">
        <StatGrid cols={{ base: 2, md: 4 }}>
          <Stat label={t("step")} value={p.state === "done" ? "–" : step} />
          <Stat label={t("window")} order={1} value={p.windows ? `${p.state === "done" ? p.windows : p.window} / ${p.windows}` : "–"} />
          <Stat label={t("reached")} order={2} value={instant} />
          <Stat label={t("left")} order={3} value={left} />
        </StatGrid>
        {p.state === "error" && p.error && <Text size="sm" c="red" ff="monospace">{p.error}</Text>}
      </Stack>
    </Fold>
  );
}
