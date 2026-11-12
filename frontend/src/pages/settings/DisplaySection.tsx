import { Center, type MantineColorScheme, SegmentedControl, SimpleGrid, Stack, Text, useMantineColorScheme } from "@mantine/core";
import { IconDeviceDesktop, IconMoon, IconSun } from "@tabler/icons-react";
import { useId } from "react";

import { defineMessages, type Lang, useLang, useT } from "../../i18n";
import { Section } from "../../ui/Page";

const messages = defineMessages({
  en: {
    title: "Display",
    language: "Language",
    english: "English",
    french: "Français",
    scheme: "Color scheme",
    light: "Light",
    dark: "Dark",
    system: "System",
  },
  fr: {
    title: "Affichage",
    language: "Langue",
    english: "English",
    french: "Français",
    scheme: "Thème de couleurs",
    light: "Clair",
    dark: "Sombre",
    system: "Système",
  },
});

function Choice({ icon, label }: { icon: React.ReactNode; label: string }) {
  return (
    <Center style={{ gap: 6 }}>
      {icon}
      <span>{label}</span>
    </Center>
  );
}

/** Language and colour scheme. */
export function DisplaySection() {
  const t = useT(messages);
  const { lang, setLang } = useLang();
  const { colorScheme, setColorScheme } = useMantineColorScheme();
  const languageId = useId();
  const schemeId = useId();

  return (
    <Section title={t("title")}>
      <SimpleGrid cols={{ base: 1, md: 2 }} spacing="xl">
        <Stack gap={6}>
          <Text size="sm" fw={500} id={languageId}>
            {t("language")}
          </Text>
          <SegmentedControl<Lang>
            aria-labelledby={languageId}
            value={lang}
            onChange={setLang}
            data={[
              { value: "en", label: <span lang="en">{t("english")}</span> },
              { value: "fr", label: <span lang="fr">{t("french")}</span> },
            ]}
            fullWidth
            maw={360}
          />
        </Stack>
        <Stack gap={6}>
          <Text size="sm" fw={500} id={schemeId}>
            {t("scheme")}
          </Text>
          <SegmentedControl<MantineColorScheme>
            aria-labelledby={schemeId}
            value={colorScheme}
            onChange={setColorScheme}
            data={[
              { value: "light", label: <Choice icon={<IconSun size={16} aria-hidden />} label={t("light")} /> },
              { value: "dark", label: <Choice icon={<IconMoon size={16} aria-hidden />} label={t("dark")} /> },
              { value: "auto", label: <Choice icon={<IconDeviceDesktop size={16} aria-hidden />} label={t("system")} /> },
            ]}
            fullWidth
            maw={420}
          />
        </Stack>
      </SimpleGrid>
    </Section>
  );
}
