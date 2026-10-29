import { ActionIcon, Button, Center, Modal, Stack, Text, Title, Tooltip } from "@mantine/core";
import { IconPower } from "@tabler/icons-react";
import { useEffect, useState } from "react";

import { post } from "../api/client";
import { useHealth } from "../api/system";
import { defineMessages, useT } from "../i18n";

const messages = defineMessages({
  en: {
    quit: "Quit Offshore Wind Studio",
    confirm: "Quit Offshore Wind Studio?",
    confirmText: "The application stops. Your projects are kept.",
    busy: "A task is running. Wait for it to finish.",
    yes: "Quit",
    cancel: "Cancel",
    closed: "Offshore Wind Studio is closed",
    closedText: "You can close this tab.",
  },
  fr: {
    quit: "Quitter Offshore Wind Studio",
    confirm: "Quitter Offshore Wind Studio ?",
    confirmText: "Le logiciel s'arrête. Vos projets sont conservés.",
    busy: "Une tâche est en cours. Attendre la fin.",
    yes: "Quitter",
    cancel: "Annuler",
    closed: "Offshore Wind Studio est fermé",
    closedText: "Vous pouvez fermer cet onglet.",
  },
});

/**
 * Linux without a window toolkit shows the application in the browser. The page tells the
 * local server it is still open (the server stops some time after the last page closes), and
 * offers a Quit button, since closing a browser tab does not stop a program.
 */
export function BrowserSession({ compact }: { compact?: boolean }) {
  const t = useT(messages);
  const health = useHealth();
  const browser = health.data?.mode === "browser";
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(false);
  const [closed, setClosed] = useState(false);
  useEffect(() => {
    if (!browser || closed) return;
    const beat = () => void post("/api/system/heartbeat").catch(() => undefined);
    beat();
    const timer = window.setInterval(beat, 15_000);
    return () => window.clearInterval(timer);
  }, [browser, closed]);
  if (!browser) return null;
  const quit = async () => {
    try {
      await post("/api/system/quit");
      setAsking(false);
      setClosed(true);
    } catch {
      setBusy(true);
    }
  };
  return (
    <>
      <Tooltip label={t("quit")} position="right" withArrow={false}>
        <ActionIcon variant="subtle" color="gray" size={compact ? "md" : "lg"} aria-label={t("quit")} onClick={() => { setBusy(false); setAsking(true); }}>
          <IconPower size={17} stroke={1.7} />
        </ActionIcon>
      </Tooltip>
      <Modal opened={asking} onClose={() => setAsking(false)} title={<Text fw={600}>{t("confirm")}</Text>} size="sm" centered>
        <Stack>
          <Text size="sm">{busy ? t("busy") : t("confirmText")}</Text>
          <Button.Group>
            <Button variant="default" onClick={() => setAsking(false)}>{t("cancel")}</Button>
            <Button color="red" disabled={busy} onClick={() => void quit()}>{t("yes")}</Button>
          </Button.Group>
        </Stack>
      </Modal>
      <Modal opened={closed} onClose={() => undefined} withCloseButton={false} fullScreen transitionProps={{ duration: 0 }}>
        <Center h="80vh">
          <Stack align="center" gap="xs">
            <Title order={2}>{t("closed")}</Title>
            <Text c="dimmed">{t("closedText")}</Text>
          </Stack>
        </Center>
      </Modal>
    </>
  );
}
