/**
 * The top of the Compute page, as technical sheets: the engine in service (or the installation in
 * progress, or none), then where an engine can be installed. Every action opens the same
 * installation wizard.
 */
import { Progress, Stack } from "@mantine/core";
import { useState } from "react";

import { type Installation, useInstallationAction, useInstallations, useUpdateDataFolder, useWslStatus } from "../../api/engine";
import type { ProfileWithStatus } from "../../api/types";
import { defineMessages, useT } from "../../i18n";
import { Sheet, SheetDot, SheetLink, SheetRow, SheetRows } from "../../ui/Sheet";
import { ErrorState } from "../../ui/States";
import { EngineWizard, type Target } from "./EngineWizard";
import { engineMessages } from "./engineMessages";
import { installedEngine, localProfile, oldDataFolder, target as where } from "./profile";

const ACTIVE = ["preparing", "queued", "running", "fetched"];

const messages = defineMessages({
  en: {
    engine: "Engine",
    install: "Install",
    change: "Change",
    machine: "Machine",
    programs: "Programs",
    geography: "Geography",
    location: "Location",
    state: "State",
    ready: "Ready",
    none: "No engine",
    installing: "Installing · {percent} %",
    stopped: "Installation stopped",
    step: "Step",
    resume: "Resume",
    follow: "Follow",
    installHere: "Install · ≈ 45 GB",
    useExisting: "Use the engine already installed",
    wsl: "This PC (WSL)",
    local: "Linux",
    unavailable: "Not available on this computer",
    data: "Input data",
    oldData: "Inside the engine (before 0.6.2)",
    moveData: "Move to {folder}",
  },
  fr: {
    engine: "Moteur",
    install: "Installer",
    change: "Changer",
    machine: "Machine",
    programs: "Programmes",
    geography: "Géographie",
    location: "Emplacement",
    state: "État",
    ready: "Prêt",
    none: "Aucun moteur",
    installing: "Installation en cours · {percent} %",
    stopped: "Installation interrompue",
    step: "Étape",
    resume: "Reprendre",
    follow: "Suivre",
    installHere: "Installer · ≈ 45 Go",
    useExisting: "Utiliser le moteur déjà installé",
    wsl: "Ce PC (WSL)",
    local: "Linux",
    unavailable: "Indisponible sur cet ordinateur",
    data: "Données d'entrée",
    oldData: "Dans le moteur (avant 0.6.2)",
    moveData: "Déplacer vers {folder}",
  },
});

export function EngineHome({ profiles, taken }: { profiles: ProfileWithStatus[]; taken: string[] }) {
  const t = useT(messages);
  const te = useT(engineMessages);
  const installations = useInstallations();
  const follow = useInstallationAction("follow");
  const moveData = useUpdateDataFolder();
  const wsl = useWslStatus(true);
  const [wizard, setWizard] = useState<Target | true | null>(null);
  // A stopped installation is resumed from the window, where its geography can be chosen again
  const [resuming, setResuming] = useState<Installation | null>(null);
  const rows = (installations.data ?? []).filter((row) => localProfile(row.profile));
  const active = rows.find((row) => ACTIVE.includes(row.state) || row.state === "monitor-interrupted");
  const stopped = !active ? rows.find((row) => row.state === "failed" || row.state === "cancelled") : undefined;
  const ready = profiles.filter((profile) => installedEngine(profile));
  const main = ready.find((p) => p.default) ?? ready[0];
  const manifest = main?.engine_manifest ?? {};
  const geography = manifest.geography?.id === "mandatory-high" ? te("highResolution") : manifest.geography?.id === "mandatory-low" ? te("lowResolution") : te("existingGeography");
  const newData = main ? oldDataFolder(main) : null;
  const mono = { fontFamily: "var(--mantine-font-family-monospace)", fontSize: 13 };
  const compatible = (target: Target) => Boolean(wsl.data) && (target === "local" ? Boolean(wsl.data?.native) : wsl.data?.platform === "win32");

  return (
    <Stack gap={0}>
      <Sheet title={t("engine")} action={main && !active ? <SheetLink onClick={() => setWizard(true)}>{t("change")}</SheetLink> : undefined}>
        <SheetRows>
          {active ? (
            <InProgress row={active} onFollow={() => follow.mutate(active.id)} following={follow.isPending} />
          ) : main ? (
            <>
              <SheetRow label={t("machine")}>{main.name}</SheetRow>
              <SheetRow label={t("programs")}>{`WRF ${manifest.wrf_version} · WPS ${manifest.wps_version}`}</SheetRow>
              <SheetRow label={t("geography")}>{geography}</SheetRow>
              <SheetRow label={t("location")}><span style={mono}>{[where(main), main.install.wrf_dir].filter(Boolean).join(" · ")}</span></SheetRow>
              <SheetRow label={t("data")}>
                {newData ? (
                  <span><SheetDot ok={false} />{t("oldData")} · <SheetLink onClick={() => moveData.mutate(main.id)} disabled={moveData.isPending}>{t("moveData", { folder: newData })}</SheetLink></span>
                ) : (
                  <span style={mono}>{main.install.input_dir}</span>
                )}
              </SheetRow>
              <SheetRow label={t("state")}><SheetDot ok />{t("ready")}</SheetRow>
            </>
          ) : stopped ? (
            <SheetRow label={t("state")}><SheetDot ok={false} />{t("stopped")} · <SheetLink onClick={() => setResuming(stopped)}>{t("resume")}</SheetLink></SheetRow>
          ) : (
            <SheetRow label={t("state")}>{t("none")}</SheetRow>
          )}
        </SheetRows>
        {follow.error && <ErrorState error={follow.error} />}
        {moveData.error && <ErrorState error={moveData.error} />}
      </Sheet>
      {!main && !active && (
        <Sheet title={t("install")}>
          <SheetRows>
            {(["wsl", "local"] as const).map((target) => (
              <SheetRow key={target} label={t(target)}>
                {!compatible(target) ? (
                  <span style={{ color: "var(--ows-muted)" }}>{t("unavailable")}</span>
                ) : target === "wsl" && wsl.data?.managed_exists ? (
                  <SheetLink onClick={() => setWizard("wsl")}>{t("useExisting")}</SheetLink>
                ) : (
                  <SheetLink onClick={() => setWizard(target)}>{t("installHere")}</SheetLink>
                )}
              </SheetRow>
            ))}
          </SheetRows>
        </Sheet>
      )}
      {wizard && <EngineWizard taken={taken} target={wizard === true ? undefined : wizard} onClose={() => setWizard(null)} />}
      {resuming && <EngineWizard taken={taken} resume={resuming} onClose={() => setResuming(null)} />}
    </Stack>
  );
}

function InProgress({ row, onFollow, following }: { row: Installation; onFollow: () => void; following: boolean }) {
  const t = useT(messages);
  const te = useT(engineMessages);
  const percent = Math.round(Math.min(1, row.progress) * 100);
  const key = row.stage as keyof typeof engineMessages.en.stages;
  const stage = key in engineMessages.en.stages ? te(`stages.${key}`) : row.stage;
  return (
    <>
      <SheetRow label={t("state")}>
        <Stack gap={6}>
          <span><SheetDot ok />{t("installing", { percent })}</span>
          <Progress value={percent} size="xs" maw={360} />
        </Stack>
      </SheetRow>
      <SheetRow label={t("step")}>{row.detail ? `${stage} · ${row.detail}` : stage}</SheetRow>
      {!row.followed && <SheetRow label="">{<SheetLink onClick={onFollow} disabled={following}>{t("follow")}</SheetLink>}</SheetRow>}
    </>
  );
}
