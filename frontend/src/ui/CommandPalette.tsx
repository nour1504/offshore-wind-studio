/**
 * Go anywhere from the keyboard (Ctrl+K, as in Raycast or Linear): every page of the open
 * project, the general pages, the other projects and a few display actions. Only a shortcut:
 * every destination stays where it is in the menu.
 */
import { Box, Group, Kbd, Modal, ScrollArea, Text, TextInput, Tooltip, UnstyledButton, useComputedColorScheme, useMantineColorScheme } from "@mantine/core";
import { useHotkeys, useOs } from "@mantine/hooks";
import { IconArrowRight, IconFolder, IconLanguage, IconMoon, IconSearch, IconSun } from "@tabler/icons-react";
import { type ComponentType, useEffect, useMemo, useRef, useState } from "react";

import { useCases } from "../api/cases";
import { GLOBAL_SECTIONS, PROJECT_SECTIONS, type ProjectSection, sectionMessages } from "../app/sections";
import { defineMessages, useLang, useT } from "../i18n";
import { navigate } from "../router";
import { Glide, useGlide } from "./Glide";
import { useMorphingDialog } from "./Morph";

const messages = defineMessages({
  en: {
    open: "Search",
    title: "Go to",
    placeholder: "A page, a project, an action…",
    groups: { project: "This project", general: "General", projects: "Projects", actions: "Display" },
    dark: "Switch to dark display",
    light: "Switch to light display",
    language: "Interface in French",
    none: "Nothing matches.",
    keys: "to choose",
    enter: "to open",
    escape: "to close",
  },
  fr: {
    open: "Rechercher",
    title: "Aller à",
    placeholder: "Une page, un projet, une action…",
    groups: { project: "Ce projet", general: "Général", projects: "Projets", actions: "Affichage" },
    dark: "Passer en affichage sombre",
    light: "Passer en affichage clair",
    language: "Interface en anglais",
    none: "Aucun résultat.",
    keys: "pour choisir",
    enter: "pour ouvrir",
    escape: "pour fermer",
  },
});

interface Item {
  key: string;
  group: "project" | "general" | "projects" | "actions";
  label: string;
  detail?: string;
  icon: ComponentType<{ size?: number; stroke?: number }>;
  run: () => void;
}

/** Lower case without accents, so that "periode" finds "Période". */
const plain = (text: string) => text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

/** compact: the folded sidebar shows only the magnifier. */
export function CommandPalette({ caseId, compact = false }: { caseId: string | null; compact?: boolean }) {
  const t = useT(messages);
  const ts = useT(sectionMessages);
  const os = useOs();
  const morph = useMorphingDialog();
  const cases = useCases();
  const { lang, setLang } = useLang();
  const { setColorScheme } = useMantineColorScheme();
  const scheme = useComputedColorScheme("light");
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const list = useRef<HTMLDivElement>(null);
  const glide = useGlide();

  useHotkeys([["mod+K", () => (morph.opened ? morph.close() : morph.open())]], []);

  const items = useMemo<Item[]>(() => {
    const all: Item[] = [];
    if (caseId) {
      for (const section of PROJECT_SECTIONS) {
        all.push({ key: `p:${section.key}`, group: "project", label: ts(`project.${section.key as ProjectSection}`), detail: ts(`groups.${section.group}`), icon: section.icon, run: () => navigate(`projects/${caseId}/${section.key}`) });
      }
    }
    for (const section of GLOBAL_SECTIONS) {
      all.push({ key: `g:${section.key}`, group: "general", label: ts(`global.${section.key}`), icon: section.icon, run: () => navigate(section.key) });
    }
    for (const item of cases.data ?? []) {
      if (item.id === caseId) continue;
      all.push({ key: `c:${item.id}`, group: "projects", label: item.name, detail: item.id, icon: IconFolder, run: () => navigate(`projects/${item.id}/overview`) });
    }
    all.push({ key: "a:scheme", group: "actions", label: t(scheme === "dark" ? "light" : "dark"), icon: scheme === "dark" ? IconSun : IconMoon, run: () => setColorScheme(scheme === "dark" ? "light" : "dark") });
    all.push({ key: "a:lang", group: "actions", label: t("language"), detail: lang === "fr" ? "EN" : "FR", icon: IconLanguage, run: () => setLang(lang === "fr" ? "en" : "fr") });
    return all;
  }, [caseId, cases.data, ts, t, scheme, setColorScheme, lang, setLang]);

  const shown = useMemo(() => {
    const words = plain(query).split(/\s+/).filter(Boolean);
    return words.length ? items.filter((item) => words.every((word) => plain(`${item.label} ${item.detail ?? ""}`).includes(word))) : items;
  }, [items, query]);
  const current = shown[Math.min(active, shown.length - 1)];

  useEffect(() => setActive(0), [query]);
  useEffect(() => {
    if (!morph.opened) setQuery("");
  }, [morph.opened]);
  useEffect(() => {
    if (current) list.current?.querySelector(`[data-key="${CSS.escape(current.key)}"]`)?.scrollIntoView({ block: "nearest" });
  }, [current]);

  // The palette disappears at once, then the page changes with its own transition
  const choose = (item: Item | undefined) => {
    if (!item) return;
    morph.dismiss();
    window.setTimeout(item.run, 0);
  };

  const groups = (["project", "general", "projects", "actions"] as const).filter((group) => shown.some((item) => item.group === group));

  return (
    <>
      <Tooltip label={`${t("open")} (${os === "macos" ? "⌘" : "Ctrl"} K)`} position="right" disabled={!compact}>
        <UnstyledButton
          ref={morph.trigger}
          onClick={morph.open}
          className="ows-search-button"
          data-compact={compact || undefined}
          aria-label={t("open")}
          aria-keyshortcuts="Control+K"
        >
          <IconSearch size={16} />
          {!compact && <span className="ows-search-label">{t("open")}</span>}
        </UnstyledButton>
      </Tooltip>
      <Modal
        {...morph.modalProps}
        withCloseButton={false}
        size={560}
        yOffset="12vh"
        centered={false}
        padding={0}
        aria-label={t("title")}
        className="ows-palette"
      >
        <TextInput
          data-autofocus
          variant="unstyled"
          size="md"
          px="md"
          py={6}
          leftSection={<IconSearch size={18} />}
          placeholder={t("placeholder")}
          value={query}
          onChange={(event) => setQuery(event.currentTarget.value)}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown") { event.preventDefault(); setActive((index) => Math.min(index + 1, shown.length - 1)); }
            else if (event.key === "ArrowUp") { event.preventDefault(); setActive((index) => Math.max(index - 1, 0)); }
            else if (event.key === "Enter") { event.preventDefault(); choose(current); }
          }}
          aria-controls="ows-palette-list"
          aria-activedescendant={current ? `ows-palette-${current.key}` : undefined}
          className="ows-palette-input"
        />
        <ScrollArea.Autosize mah="50vh" type="scroll" className="ows-palette-scroll">
          <Box ref={list} p={6} id="ows-palette-list" role="listbox">
            <Box ref={glide.parent} pos="relative">
              <Glide glide={glide} active={current?.key} duration={140} />
              {shown.length === 0 && <Text size="sm" c="dimmed" ta="center" py="lg">{t("none")}</Text>}
              {groups.map((group) => (
                <Box key={group} mb={4}>
                  <Text size="xs" c="dimmed" fw={600} px="sm" pt={8} pb={4}>{t(`groups.${group}`)}</Text>
                  {shown.filter((item) => item.group === group).map((item) => {
                    const index = shown.indexOf(item);
                    return (
                      <UnstyledButton
                        key={item.key}
                        ref={glide.item(item.key)}
                        id={`ows-palette-${item.key}`}
                        data-key={item.key}
                        role="option"
                        aria-selected={item === current}
                        className="ows-palette-item"
                        data-active={item === current || undefined}
                        onMouseMove={() => index !== active && setActive(index)}
                        onClick={() => choose(item)}
                        tabIndex={-1}
                      >
                        <item.icon size={18} stroke={1.6} />
                        <Text size="sm" fw={500} style={{ flex: 1 }} truncate>{item.label}</Text>
                        {item.detail && <Text size="xs" c="dimmed">{item.detail}</Text>}
                        <IconArrowRight size={14} className="ows-palette-arrow" />
                      </UnstyledButton>
                    );
                  })}
                </Box>
              ))}
            </Box>
          </Box>
        </ScrollArea.Autosize>
        <Group gap="md" px="md" py={8} className="ows-palette-foot">
          <Text size="xs" c="dimmed"><Kbd size="xs">↑</Kbd> <Kbd size="xs">↓</Kbd> {t("keys")}</Text>
          <Text size="xs" c="dimmed"><Kbd size="xs">↵</Kbd> {t("enter")}</Text>
          <Text size="xs" c="dimmed"><Kbd size="xs">Esc</Kbd> {t("escape")}</Text>
        </Group>
      </Modal>
    </>
  );
}
