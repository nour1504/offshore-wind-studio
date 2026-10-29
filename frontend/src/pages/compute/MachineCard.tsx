/**
 * One compute machine, as a row of the Compute sheet: its name, its state and versions, and its
 * actions written as links.
 */
import { Group, Stack, Text } from "@mantine/core";

import { useVerifyEngine } from "../../api/engine";
import type { ProfileWithStatus } from "../../api/types";
import { defineMessages, useT } from "../../i18n";
import { Confirm } from "../../ui/Inputs";
import { engineMessages } from "./engineMessages";
import { SheetDot, SheetLink, SheetRow } from "../../ui/Sheet";
import { installedEngine } from "./profile";

const messages = defineMessages({
  en: {
    ready: "Ready",
    missing: "{n|# setting|# settings} to complete",
    default: "Default",
    verify: "Check",
    edit: "Edit",
    makeDefault: "Use by default",
    delete: "Delete",
    deleteTitle: "Delete this machine?",
    deleteText: "Deletes the profile only. The installed engine is not touched.",
    details: "Details",
    where: "Where",
    geography: "Geography",
  },
  fr: {
    ready: "Prêt",
    missing: "{n|# réglage|# réglages} à compléter",
    default: "Par défaut",
    verify: "Vérifier",
    edit: "Modifier",
    makeDefault: "Utiliser par défaut",
    delete: "Supprimer",
    deleteTitle: "Supprimer cette machine ?",
    deleteText: "Supprime le profil uniquement. Le moteur installé n'est pas touché.",
    details: "Détails",
    where: "Où",
    geography: "Géographie",
  },
});

export function MachineCard({ profile, onEdit, onDefault, onDelete }: { profile: ProfileWithStatus; onEdit: () => void; onDefault: () => void; onDelete: () => void }) {
  const t = useT(messages);
  const te = useT(engineMessages);
  const verify = useVerifyEngine();
  const ready = profile.missing.length === 0;
  const installed = installedEngine(profile);
  const manifest = profile.engine_manifest ?? {};
  const summary = installed ? `WRF ${manifest.wrf_version} · WPS ${manifest.wps_version}` : null;
  return (
    <SheetRow label={<>{profile.name}{profile.default ? ` · ${t("default")}` : ""}</>}>
      <Stack gap={6}>
        <Group justify="space-between" wrap="wrap" gap="md">
          <span><SheetDot ok={ready} />{ready ? t("ready") : t("missing", { n: profile.missing.length })}{summary ? ` · ${summary}` : ""}</span>
          <Group gap="md" wrap="nowrap">
            {installed && <SheetLink onClick={() => verify.mutate(profile.id)} disabled={verify.isPending}>{t("verify")}</SheetLink>}
            <SheetLink onClick={onEdit}>{t("edit")}</SheetLink>
            {!profile.default && <SheetLink onClick={onDefault}>{t("makeDefault")}</SheetLink>}
            <Confirm title={t("deleteTitle")} text={t("deleteText")} confirmLabel={t("delete")} onConfirm={onDelete}>
              {(confirm) => <SheetLink danger onClick={confirm}>{t("delete")}</SheetLink>}
            </Confirm>
          </Group>
        </Group>
        {verify.data && <Text size="sm" c={verify.data.ok ? "dimmed" : "red"}>{verify.data.ok ? te("verifyOk") : verify.data.error}</Text>}
      </Stack>
    </SheetRow>
  );
}
