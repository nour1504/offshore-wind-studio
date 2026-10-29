import { Button, FileButton } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconFileImport } from "@tabler/icons-react";
import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { caseKeys } from "../../api/cases";
import { withLanguage, withQuery } from "../../api/client";
import { defineMessages, useT } from "../../i18n";
import { navigate } from "../../router";

export const transferMessages = defineMessages({
  en: {
    import: "Import a project",
    export: "Export",
    imported: "Project imported: {name}",
    folders: "Weather files not found on this computer: {folders}. Choose them again in Period and data.",
    invalid: "This file is not an Offshore Wind Studio project",
  },
  fr: {
    import: "Importer un projet",
    export: "Exporter",
    imported: "Projet importé : {name}",
    folders: "Fichiers météo introuvables sur cet ordinateur : {folders}. Les choisir à nouveau dans Période et données.",
    invalid: "Ce fichier n'est pas un projet Offshore Wind Studio",
  },
});

/** Saves the project as a file (.owstudio.zip), through the browser's or the window's download. */
export function exportProject(caseId: string) {
  const link = document.createElement("a");
  link.href = `/api/cases/${encodeURIComponent(caseId)}/export`;
  link.download = "";
  document.body.append(link);
  link.click();
  link.remove();
}

/** Imports a project exported by the application (.zip) or a case.yaml, then opens it. */
export function ImportProjectButton() {
  const t = useT(transferMessages);
  const client = useQueryClient();
  const [busy, setBusy] = useState(false);
  const receive = async (file: File | null) => {
    if (!file) return;
    setBusy(true);
    try {
      const response = await fetch(withLanguage(withQuery("/api/cases/import", { filename: file.name })), { method: "POST", body: file });
      const body = (await response.json()) as { id?: string; name?: string; missing_folders?: string[]; detail?: unknown };
      if (!response.ok || !body.id) throw new Error(typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail));
      await client.invalidateQueries({ queryKey: caseKeys.list });
      notifications.show({ color: "teal", message: t("imported", { name: body.name ?? "" }) });
      if (body.missing_folders?.length) notifications.show({ color: "gray", autoClose: false, message: t("folders", { folders: body.missing_folders.join(", ") }) });
      navigate(`projects/${body.id}/overview`);
    } catch (error) {
      notifications.show({ color: "red", title: t("invalid"), message: (error as Error).message });
    } finally {
      setBusy(false);
    }
  };
  return (
    <FileButton onChange={(file) => void receive(file)} accept=".zip,.yaml,.yml">
      {(props) => <Button {...props} variant="default" loading={busy} leftSection={<IconFileImport size={18} />}>{t("import")}</Button>}
    </FileButton>
  );
}
