/**
 * One compute machine, as a plain tile of the Compute page: its name, its state and versions on one
 * line, its actions as quiet links.
 */
import { Group, Text } from "@mantine/core";
import { useEffect } from "react";

import { unfinishedInstallation, useEngineOutputs, useInstallations, useVerifyEngine } from "../../api/engine";
import type { ProfileWithStatus } from "../../api/types";
import { defineMessages, useT } from "../../i18n";
import { Confirm } from "../../ui/Inputs";
import { engineMessages } from "./engineMessages";
import { SheetDot, SheetLink } from "../../ui/Sheet";
import { installedEngine, removedEngine } from "./profile";

const messages = defineMessages({
  en: {
    ready: "Ready",
    installing: "Installing",
    stopped: "Installation stopped",
    removed: "Engine removed",
    missing: "{n|# setting|# settings} to complete",
    default: "Default",
    verify: "Check",
    edit: "Edit",
    makeDefault: "Use by default",
    delete: "Delete",
    deleteTitle: "Delete this machine?",
    deleteText: "Deletes the profile only. The installed engine is not touched.",
  },
  fr: {
    ready: "Prêt",
    installing: "Installation en cours",
    stopped: "Installation interrompue",
    removed: "Moteur supprimé",
    missing: "{n|# réglage|# réglages} à compléter",
    default: "Par défaut",
    verify: "Vérifier",
    edit: "Modifier",
    makeDefault: "Utiliser par défaut",
    delete: "Supprimer",
    deleteTitle: "Supprimer cette machine ?",
    deleteText: "Supprime le profil uniquement. Le moteur installé n'est pas touché.",
  },
});

export function MachineCard({ profile, onEdit, onDefault, onDelete }: { profile: ProfileWithStatus; onEdit: () => void; onDefault: () => void; onDelete: () => void }) {
  const t = useT(messages);
  const te = useT(engineMessages);
  const verify = useVerifyEngine();
  const installations = useInstallations();
  // The installations of this profile, the latest first. Installed again at this moment: neither
  // removed nor ready; the latest one stopped before its end: to resume
  const own = (installations.data ?? []).filter((row) => row.profile.id === profile.id);
  const installing = own.some(unfinishedInstallation);
  const stopped = own[0]?.state === "failed" || own[0]?.state === "cancelled";
  const removed = removedEngine(profile);
  const installed = installedEngine(profile);
  // Ready is said of the engine as it is on its machine: not without its wrf.exe
  const outputs = useEngineOutputs(installed ? profile : undefined);
  const missingProgram = outputs.data?.tslist === "absent";
  const ready = profile.missing.length === 0 && !removed && !missingProgram;
  const manifest = profile.engine_manifest ?? {};
  const summary = installed ? `WRF ${manifest.wrf_version} · WPS ${manifest.wps_version}` : null;
  // What a check said holds for the engine it checked: not once that engine is removed or built again
  const engine = `${manifest.state ?? ""} ${manifest.created_at ?? ""}`;
  const { reset } = verify;
  useEffect(() => reset(), [reset, engine]);
  return (
    <div className="ows-machine-tile" data-ready={ready || undefined}>
      <div className="ows-machine-tile-head">
        <Text fw={600} truncate className="ows-machine-tile-name">{profile.name}</Text>
        {profile.default && <span className="ows-machine-tile-default">{t("default")}</span>}
      </div>
      <div className="ows-machine-tile-meta">
        <span><SheetDot ok={ready || installing} />{ready ? t("ready") : installing ? t("installing") : removed ? t(stopped ? "stopped" : "removed") : missingProgram ? te("noProgram") : t("missing", { n: profile.missing.length })}</span>
        {summary && <span className="ows-num">{summary}</span>}
      </div>
      <Group gap="md" wrap="wrap" className="ows-machine-tile-actions">
        {installed && <SheetLink onClick={() => verify.mutate(profile.id)} disabled={verify.isPending}>{t("verify")}</SheetLink>}
        <SheetLink onClick={onEdit}>{t("edit")}</SheetLink>
        {!profile.default && <SheetLink onClick={onDefault}>{t("makeDefault")}</SheetLink>}
        <Confirm title={t("deleteTitle")} text={t("deleteText")} confirmLabel={t("delete")} onConfirm={onDelete}>
          {(confirm) => <SheetLink danger onClick={confirm}>{t("delete")}</SheetLink>}
        </Confirm>
      </Group>
      {verify.data && <Text size="sm" c={verify.data.ok ? "dimmed" : "red"}>{verify.data.ok ? te("verifyOk") : verify.data.error}</Text>}
    </div>
  );
}
