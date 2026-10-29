import { Alert, Anchor, Badge, Button, Group, PasswordInput, Stack, Text } from "@mantine/core";
import { useState } from "react";
import { useHealth, useSettings, useStorage } from "../../api/system";
import { defineMessages, useT } from "../../i18n";
import { Fold } from "../../ui/Fold";
import { ErrorState, QueryView } from "../../ui/States";
import { KeyValues } from "../../ui/Stat";
import { PathLine } from "./CopyPath";
import { useSetCdsKey } from "./queries";

export const settingsMessages = defineMessages({
  en: { description: "Appearance, data location and ERA5 access.", title: "ERA5 access", text: "Copernicus CDS token required only to download ERA5.", configured: "Token configured", missing: "No token configured", key: "Personal access token", save: "Save the token", saved: "Token saved", account: "Open the Climate Data Store", about: "About", version: "Application version", settingsFile: "Settings file" },
  fr: { description: "Apparence, emplacement des données et accès à ERA5.", title: "Accès à ERA5", text: "Jeton CDS Copernicus requis uniquement pour télécharger ERA5.", configured: "Jeton configuré", missing: "Aucun jeton configuré", key: "Jeton d'accès personnel", save: "Enregistrer le jeton", saved: "Jeton enregistré", account: "Ouvrir le Climate Data Store", about: "À propos", version: "Version de l'application", settingsFile: "Fichier de paramètres" },
});

export function AccessSection() {
  const t = useT(settingsMessages);
  const settings = useSettings();
  const save = useSetCdsKey();
  const [token, setToken] = useState("");
  return <Fold title={t("title")} description={t("text")} help="era5-access">
    <Stack gap="md">
      <QueryView query={settings}>{data => <Badge variant="light" color={data.cds_key_configured ? "teal" : "gray"}>{t(data.cds_key_configured ? "configured" : "missing")}</Badge>}</QueryView>
      <form onSubmit={e => { e.preventDefault(); if (token.trim()) save.mutate(token, { onSuccess: () => setToken("") }); }}>
        <Stack gap="sm">
          <PasswordInput label={t("key")} value={token} onChange={e => { setToken(e.currentTarget.value); save.reset(); }} autoComplete="off" maw={580} />
          <Group><Button type="submit" disabled={!token.trim()} loading={save.isPending}>{t("save")}</Button>{save.isSuccess && <Text size="sm" c="teal" role="status">{t("saved")}</Text>}</Group>
        </Stack>
      </form>
      {save.error && <ErrorState error={save.error} />}
      <Alert color="gray"><Anchor href="https://cds.climate.copernicus.eu/how-to-api" target="_blank" rel="noreferrer">{t("account")}</Anchor></Alert>
    </Stack>
  </Fold>;
}

export function AboutSection() {
  const t = useT(settingsMessages);
  const health = useHealth();
  const storage = useStorage();
  return <Fold title={t("about")}>
    <Stack><QueryView query={health}>{data => <KeyValues items={[[t("version"), data.version]]} />}</QueryView>
      <QueryView query={storage}>{data => <Stack gap={4}><Text size="sm" c="dimmed">{t("settingsFile")}</Text><PathLine path={data.settings_file} name={t("settingsFile")} /></Stack>}</QueryView>
    </Stack>
  </Fold>;
}
