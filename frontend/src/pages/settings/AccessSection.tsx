import { Anchor, Button, Group, PasswordInput, Stack, Text } from "@mantine/core";
import { useState } from "react";
import { useHealth, useSettings, useStorage } from "../../api/system";
import { defineMessages, useT } from "../../i18n";
import { Fold } from "../../ui/Fold";
import { ErrorState, QueryView } from "../../ui/States";
import { PathLine } from "./CopyPath";
import { useSetCdsKey } from "./queries";

const settingsMessages = defineMessages({
  en: { title: "ERA5 access", configured: "Configured", missing: "None", key: "Personal access token", save: "Save the token", saved: "Token saved", account: "Open the Climate Data Store", about: "About", settingsFile: "Settings file" },
  fr: { title: "Accès à ERA5", configured: "Configuré", missing: "Aucun", key: "Jeton d'accès personnel", save: "Enregistrer le jeton", saved: "Jeton enregistré", account: "Ouvrir le Climate Data Store", about: "À propos", settingsFile: "Fichier de paramètres" },
});

export function AccessSection() {
  const t = useT(settingsMessages);
  const settings = useSettings();
  const save = useSetCdsKey();
  const [token, setToken] = useState("");
  const state = settings.data ? t(settings.data.cds_key_configured ? "configured" : "missing") : "–";
  return <Fold title={t("title")} value={state} help="era5-access">
    <form onSubmit={e => { e.preventDefault(); if (token.trim()) save.mutate(token, { onSuccess: () => setToken("") }); }}>
      <Stack gap="sm">
        <PasswordInput label={t("key")} value={token} onChange={e => { setToken(e.currentTarget.value); save.reset(); }} autoComplete="off" maw={580} />
        <Group justify="space-between" maw={580}>
          <Group gap="sm"><Button type="submit" disabled={!token.trim()} loading={save.isPending}>{t("save")}</Button>{save.isSuccess && <Text size="sm" c="dimmed" role="status">{t("saved")}</Text>}</Group>
          <Anchor size="sm" href="https://cds.climate.copernicus.eu/how-to-api" target="_blank" rel="noreferrer">{t("account")}</Anchor>
        </Group>
      </Stack>
    </form>
    {settings.error && <ErrorState error={settings.error} />}
    {save.error && <ErrorState error={save.error} />}
  </Fold>;
}

export function AboutSection() {
  const t = useT(settingsMessages);
  const health = useHealth();
  const storage = useStorage();
  return <Fold title={t("about")} value={health.data?.version ?? "–"}>
    <QueryView query={storage}>{data => <Stack gap={4}><Text size="sm" c="dimmed">{t("settingsFile")}</Text><PathLine path={data.settings_file} name={t("settingsFile")} /></Stack>}</QueryView>
    {health.error && <ErrorState error={health.error} />}
  </Fold>;
}
