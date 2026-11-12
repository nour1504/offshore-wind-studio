/**
 * The top of the Compute page, as technical sheets: the engine in service, drawn as a machine
 * (or the installation in progress, a ring closing around it, or none), then where an engine can be
 * installed. The engine is installed again or removed from its sheet, with nothing to choose; any
 * other installation opens the wizard.
 */
import { Group, Stack } from "@mantine/core";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { type Installation, unfinishedInstallation, useEngineOutputs, useInstallationAction, useInstallations, useReinstallEngine, useRemoveEngine, useUpdateDataFolder, useWslStatus } from "../../api/engine";
import { keys } from "../../api/system";
import type { ProfileWithStatus } from "../../api/types";
import { defineMessages, useT } from "../../i18n";
import { Confirm } from "../../ui/Inputs";
import { Sheet, SheetDot, SheetLink, SheetRow, SheetRows } from "../../ui/Sheet";
import { ErrorState } from "../../ui/States";
import { EngineWizard, type Target } from "./EngineWizard";
import { engineMessages } from "./engineMessages";
import { installedEngine, localProfile, oldDataFolder, removedEngine, target as where } from "./profile";
import { useStage } from "./stage";

const messages = defineMessages({
  en: {
    engine: "Engine",
    install: "Install",
    change: "Change",
    machine: "Machine",
    programs: "Executables",
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
    tslist: "tslist outputs",
    tslistYes: "RMOL, BR, UST, PBLH, POWER, TKE",
    tslistNo: "No POWER or TKE: reinstall",
    reinstall: "Reinstall",
    reinstallTitle: "Reinstall the engine?",
    reinstallText: "WRF and WPS are compiled again: 15 minutes to 1 hour. No calculation meanwhile.",
    reinstallAllText: "The libraries are downloaded, WRF and WPS compiled: 20 minutes to 2 hours.",
    remove: "Remove",
    removeTitle: "Remove the engine?",
    removeText: "WRF, WPS and the libraries are removed. The geography, the input data and the calculations stay.",
    removing: "Removing",
    removed: "Removed",
  },
  fr: {
    engine: "Moteur",
    install: "Installer",
    change: "Changer",
    machine: "Machine",
    programs: "Exécutables",
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
    tslist: "Sorties tslist",
    tslistYes: "RMOL, BR, UST, PBLH, POWER, TKE",
    tslistNo: "Sans POWER ni TKE : réinstaller",
    reinstall: "Réinstaller",
    reinstallTitle: "Réinstaller le moteur ?",
    reinstallText: "WRF et WPS sont recompilés : 15 minutes à 1 heure. Aucun calcul pendant ce temps.",
    reinstallAllText: "Les bibliothèques sont téléchargées, WRF et WPS compilés : 20 minutes à 2 heures.",
    remove: "Supprimer",
    removeTitle: "Supprimer le moteur ?",
    removeText: "WRF, WPS et les bibliothèques sont supprimés. La géographie, les données d'entrée et les calculs restent.",
    removing: "Suppression",
    removed: "Supprimé",
  },
});

export function EngineHome({ profiles, taken }: { profiles: ProfileWithStatus[]; taken: string[] }) {
  const t = useT(messages);
  const te = useT(engineMessages);
  const installations = useInstallations();
  const follow = useInstallationAction("follow");
  const moveData = useUpdateDataFolder();
  const reinstall = useReinstallEngine();
  const remove = useRemoveEngine();
  const wsl = useWslStatus(true);
  const [wizard, setWizard] = useState<Target | true | null>(null);
  // A stopped installation is resumed from the window, where its geography can be chosen again
  const [resuming, setResuming] = useState<Installation | null>(null);
  const rows = (installations.data ?? []).filter((row) => localProfile(row.profile));
  // An installation that ends, or stops, changes the engine of its profile: the profiles are read again
  const client = useQueryClient();
  const states = rows.map((row) => `${row.id}:${row.state}`).join(" ");
  useEffect(() => {
    void client.invalidateQueries({ queryKey: keys.profiles });
  }, [client, states]);
  const active = rows.find(unfinishedInstallation);
  // The latest installation, when it stopped before its end
  const stopped = !active && (rows[0]?.state === "failed" || rows[0]?.state === "cancelled") ? rows[0] : undefined;
  const ready = profiles.filter((profile) => installedEngine(profile));
  const main = ready.find((p) => p.default) ?? ready[0];
  // An engine removed from its machine: its profile keeps what installing it again needs
  const removed = profiles.filter((profile) => removedEngine(profile));
  const gone = !main && !stopped ? (removed.find((p) => p.default) ?? removed[0]) : undefined;
  const shown = main ?? gone;
  const outputs = useEngineOutputs(main);
  const missingProgram = outputs.data?.tslist === "absent";
  const busy = reinstall.isPending || remove.isPending;
  const manifest = main?.engine_manifest ?? {};
  const geography = manifest.geography?.id === "mandatory-high" ? te("highResolution") : manifest.geography?.id === "mandatory-low" ? te("lowResolution") : te("existingGeography");
  const newData = main ? oldDataFolder(main) : null;
  const mono = { fontFamily: "var(--mantine-font-family-monospace)", fontSize: 13 };
  const compatible = (target: Target) => Boolean(wsl.data) && (target === "local" ? Boolean(wsl.data?.native) : wsl.data?.platform === "win32");

  return (
    <Stack gap={0}>
      <Sheet
        title={t("engine")}
        action={shown && !active ? (
          <Group gap="md" wrap="nowrap">
            <Confirm title={t("reinstallTitle")} text={t(main ? "reinstallText" : "reinstallAllText")} confirmLabel={t("reinstall")} color="orange" onConfirm={() => reinstall.mutate(shown.id)}>
              {(confirm) => <SheetLink onClick={confirm} disabled={busy}>{t("reinstall")}</SheetLink>}
            </Confirm>
            {main && (
              <Confirm title={t("removeTitle")} text={t("removeText")} confirmLabel={t("remove")} onConfirm={() => remove.mutate(main.id)}>
                {(confirm) => <SheetLink danger onClick={confirm} disabled={busy}>{t("remove")}</SheetLink>}
              </Confirm>
            )}
            <SheetLink onClick={() => setWizard(true)} disabled={busy}>{t("change")}</SheetLink>
          </Group>
        ) : undefined}
      >
        <SheetRows>
          {active ? (
            <InProgress row={active} onFollow={() => follow.mutate(active.id)} following={follow.isPending} />
          ) : main ? (
            <>
              <SheetRow label={t("machine")}>{main.name}</SheetRow>
              <SheetRow label={t("programs")}>{`WRF ${manifest.wrf_version} · WPS ${manifest.wps_version}`}</SheetRow>
              <SheetRow label={t("tslist")}>
                {outputs.data?.tslist === "yes" ? t("tslistYes")
                  : outputs.data?.tslist === "no" ? <span><SheetDot ok={false} />{t("tslistNo")}</span>
                  : "–"}
              </SheetRow>
              <SheetRow label={t("geography")}>{geography}</SheetRow>
              <SheetRow label={t("location")}><span style={mono}>{[where(main), main.install.wrf_dir].filter(Boolean).join(" · ")}</span></SheetRow>
              <SheetRow label={t("data")}>
                {newData ? (
                  <span><SheetDot ok={false} />{t("oldData")} · <SheetLink onClick={() => moveData.mutate(main.id)} disabled={moveData.isPending}>{t("moveData", { folder: newData })}</SheetLink></span>
                ) : (
                  <span style={mono}>{main.install.input_dir}</span>
                )}
              </SheetRow>
              {/* Ready is said of the engine as it is on its machine: not without its wrf.exe */}
              <SheetRow label={t("state")}>{remove.isPending ? <span className="ows-running">{t("removing")}</span> : missingProgram ? <><SheetDot ok={false} />{te("noProgram")}</> : <><SheetDot ok />{t("ready")}</>}</SheetRow>
            </>
          ) : stopped ? (
            <SheetRow label={t("state")}><SheetDot ok={false} />{t("stopped")} · <SheetLink onClick={() => setResuming(stopped)}>{t("resume")}</SheetLink></SheetRow>
          ) : gone ? (
            <>
              <SheetRow label={t("machine")}>{gone.name}</SheetRow>
              <SheetRow label={t("location")}><span style={mono}>{[where(gone), gone.engine_manifest.root].filter(Boolean).join(" · ")}</span></SheetRow>
              <SheetRow label={t("state")}><SheetDot ok={false} />{t("removed")}</SheetRow>
            </>
          ) : (
            <SheetRow label={t("state")}>{t("none")}</SheetRow>
          )}
        </SheetRows>
        {follow.error && <ErrorState error={follow.error} />}
        {moveData.error && <ErrorState error={moveData.error} />}
        {reinstall.error && <ErrorState error={reinstall.error} />}
        {remove.error && <ErrorState error={remove.error} />}
      </Sheet>
      {/* A reinstallation that stopped is resumed: no other installation is offered in its place */}
      {!main && !active && !gone && !stopped?.options.fresh && (
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
  const percent = Math.round(Math.min(1, row.progress) * 100);
  const stage = useStage()(row.stage, row.detail ?? "");
  return (
    <>
      <SheetRow label={t("state")}>
        <span className="ows-install-state"><span><SheetDot ok /><span className="ows-running">{t("installing", { percent })}</span></span><span className="ows-install-line"><span style={{ transform: `scaleX(${Math.max(0.01, Math.min(1, row.progress))})` }} /></span></span>
      </SheetRow>
      <SheetRow label={t("step")}>{stage.detail ? `${stage.label} · ${stage.detail}` : stage.label}</SheetRow>
      {!row.followed && <SheetRow label="">{<SheetLink onClick={onFollow} disabled={following}>{t("follow")}</SheetLink>}</SheetRow>}
    </>
  );
}
