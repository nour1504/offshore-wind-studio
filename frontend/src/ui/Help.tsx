import { ActionIcon, Anchor, Drawer, Group, Stack, Text, Tooltip } from "@mantine/core";
import { IconExternalLink, IconHelpCircle } from "@tabler/icons-react";
import { createContext, type ReactNode, useCallback, useContext, useMemo, useState } from "react";

import { useDocPage } from "../api/docs";
import { defineMessages, useLang, useT } from "../i18n";
import { Link } from "../router";
import { Markdown } from "./Markdown";
import { ErrorState, LoadingState } from "./States";

const messages = defineMessages({
  en: {
    open: "Help on this topic",
    full: "Open in the Help tab",
    related: "Related topics",
    missing: "This help topic is not available yet.",
  },
  fr: {
    open: "Aide sur ce sujet",
    full: "Ouvrir dans l'onglet Aide",
    related: "Sujets liés",
    missing: "Ce sujet d'aide n'est pas encore disponible.",
  },
});

const HelpContext = createContext<(topic: string) => void>(() => undefined);

/** Contextual help: a side panel showing one documentation topic without leaving the page. */
export function HelpProvider({ children }: { children: ReactNode }) {
  const [topic, setTopic] = useState<string | null>(null);
  const { lang } = useLang();
  const t = useT(messages);
  const page = useDocPage(topic, lang);
  const open = useCallback((id: string) => setTopic(id), []);
  const value = useMemo(() => open, [open]);

  return (
    <HelpContext.Provider value={value}>
      {children}
      <Drawer
        opened={topic !== null}
        onClose={() => setTopic(null)}
        position="right"
        size="lg"
        title={<Text fw={600}>{page.data?.title ?? t("open")}</Text>}
      >
        {page.isLoading && <LoadingState rows={6} />}
        {page.error ? (
          (page.error as { status?: number }).status === 404 ? (
            <Text c="dimmed">{t("missing")}</Text>
          ) : (
            <ErrorState error={page.error} />
          )
        ) : null}
        {page.data && (
          <Stack gap="md">
            <Markdown text={page.data.markdown} />
            {page.data.related.length > 0 && (
              <Stack gap={4}>
                <Text fw={600} size="sm">
                  {t("related")}
                </Text>
                {page.data.related.map((r) => (
                  <Anchor key={r.id} size="sm" onClick={() => setTopic(r.id)}>
                    {r.title}
                  </Anchor>
                ))}
              </Stack>
            )}
            <Group>
              <Anchor component={Link} to={`help/${topic}`} size="sm" onClick={() => setTopic(null)}>
                <Group gap={4}>
                  {t("full")} <IconExternalLink size={14} />
                </Group>
              </Anchor>
            </Group>
          </Stack>
        )}
      </Drawer>
    </HelpContext.Provider>
  );
}

export function useHelp(): (topic: string) => void {
  return useContext(HelpContext);
}

/** A small "?" next to a title or field that opens the matching help topic. */
export function HelpLink({ topic, size = 18 }: { topic: string; size?: number }) {
  const openHelp = useHelp();
  const t = useT(messages);
  return (
    <Tooltip label={t("open")}>
      <ActionIcon variant="subtle" color="gray" size="sm" aria-label={t("open")} onClick={() => openHelp(topic)}>
        <IconHelpCircle size={size} stroke={1.6} />
      </ActionIcon>
    </Tooltip>
  );
}
