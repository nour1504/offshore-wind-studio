/**
 * The frame of the application: a sidebar (brand, project, search, the menu, the simulations,
 * help, settings, language and display) and the content in an inset "canvas" with its own top
 * bar (where you are). The sidebar folds down to its icons.
 */
import {
  ActionIcon,
  Alert,
  AppShell,
  Badge,
  Box,
  Burger,
  Button,
  Group,
  NavLink,
  ScrollArea,
  SegmentedControl,
  Select,
  Stack,
  Text,
  Tooltip,
  Transition,
  UnstyledButton,
  useComputedColorScheme,
  useMantineColorScheme,
} from "@mantine/core";
import { useDisclosure, useLocalStorage, useMediaQuery } from "@mantine/hooks";
import {
  IconAlertTriangle,
  IconArrowBackUp,
  IconArrowForwardUp,
  IconChevronRight,
  IconLayoutSidebarLeftCollapse,
  IconLayoutSidebarLeftExpand,
  IconMoon,
  IconServerOff,
  IconSun,
  IconWind,
} from "@tabler/icons-react";
import type { ComponentType, MouseEvent, ReactNode } from "react";

import { useCases } from "../api/cases";
import { useHealth } from "../api/system";
import { common } from "../i18n/common";
import { defineMessages, type Lang, useLang, useT } from "../i18n";
import { href, navigate } from "../router";
import { barIn, DURATION, EASE_OUT, withViewTransition } from "../motion";
import { BrowserSession } from "../ui/BrowserSession";
import { CommandPalette } from "../ui/CommandPalette";
import { Glide, useGlide } from "../ui/Glide";
import { PageIconContext } from "../ui/Page";
import { WorkflowGuide } from "../ui/WorkflowGuide";
import { useDraft } from "./CaseDraft";
import { GLOBAL_SECTIONS, PROJECT_SECTIONS, type ProjectSection, sectionMessages } from "./sections";

const messages = defineMessages({
  en: {
    project: "Project",
    switchProject: "Switch project",
    theme: "Light or dark display",
    language: "Language",
    skip: "Skip to content",
    unsaved: "Unsaved changes in this project",
    saveRefused: "Not saved: {reason}",
    errorsCount: "{n|# error|# errors} to fix",
    undo: "Undo (Ctrl+Z)",
    redo: "Redo (Ctrl+Y)",
    navigation: "Navigation",
    fold: "Fold the menu",
    unfold: "Unfold the menu",
    where: "You are here",
  },
  fr: {
    project: "Projet",
    switchProject: "Changer de projet",
    theme: "Affichage clair ou sombre",
    language: "Langue",
    skip: "Aller au contenu",
    unsaved: "Modifications non enregistrées dans ce projet",
    saveRefused: "Non enregistré : {reason}",
    errorsCount: "{n|# erreur|# erreurs} à corriger",
    undo: "Annuler (Ctrl+Z)",
    redo: "Rétablir (Ctrl+Y)",
    navigation: "Navigation",
    fold: "Replier le menu",
    unfold: "Déplier le menu",
    where: "Vous êtes ici",
  },
});

type Icon = ComponentType<{ size?: number; stroke?: number }>;

function ColorSchemeToggle() {
  const { setColorScheme } = useMantineColorScheme();
  const computed = useComputedColorScheme("light");
  const t = useT(messages);
  // The new look spreads in a circle from the button (a view transition, see styles.css)
  const toggle = (event: MouseEvent<HTMLButtonElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const x = box.left + box.width / 2;
    const y = box.top + box.height / 2;
    const root = document.documentElement.style;
    root.setProperty("--ows-reveal-x", `${x}px`);
    root.setProperty("--ows-reveal-y", `${y}px`);
    root.setProperty("--ows-reveal-r", `${Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y))}px`);
    withViewTransition("theme", () => setColorScheme(computed === "dark" ? "light" : "dark"));
  };
  return (
    <Tooltip label={t("theme")}>
      <ActionIcon variant="subtle" color="gray" aria-label={t("theme")} onClick={toggle} className="ows-theme-toggle">
        {computed === "dark" ? <IconSun key="sun" size={17} /> : <IconMoon key="moon" size={17} />}
      </ActionIcon>
    </Tooltip>
  );
}

function LanguageSwitch() {
  const { lang, setLang } = useLang();
  const t = useT(messages);
  return (
    <SegmentedControl
      size="xs"
      aria-label={t("language")}
      value={lang}
      onChange={(value) => setLang(value as Lang)}
      data={[
        { value: "fr", label: "FR" },
        { value: "en", label: "EN" },
      ]}
    />
  );
}

/** The open project, as a workspace selector at the top of the sidebar. */
function ProjectSwitcher({ caseId }: { caseId: string }) {
  const cases = useCases();
  const t = useT(messages);
  const name = cases.data?.find((c) => c.id === caseId)?.name ?? caseId;
  return (
    <Select
      aria-label={t("switchProject")}
      size="sm"
      searchable
      allowDeselect={false}
      value={caseId}
      data={(cases.data ?? []).map((c) => ({ value: c.id, label: c.name }))}
      onChange={(value) => value && navigate(`projects/${value}/overview`)}
      leftSection={<span className="ows-project-tile" aria-hidden="true">{name.slice(0, 1).toUpperCase()}</span>}
      leftSectionWidth={40}
      className="ows-project-switcher"
    />
  );
}

/** Save bar of a project: floats up from the bottom as soon as something changed. */
function SaveBar() {
  const draft = useDraft();
  const t = useT(messages);
  const tc = useT(common);
  return (
    <Transition mounted={draft.dirty} transition={barIn} duration={DURATION.dialog} exitDuration={DURATION.state} timingFunction={EASE_OUT}>
      {(style) => (
        <Box className="ows-savebar" style={style} role="region" aria-label={t("unsaved")}>
          <Group justify="space-between" gap="sm" wrap="nowrap">
            <Group gap="xs" wrap="nowrap" style={{ minWidth: 0 }}>
              <span className="ows-savebar-dot" aria-hidden="true" />
              <Text size="sm" fw={500} truncate>
                {t("unsaved")}
              </Text>
              {draft.errors.length > 0 && (
                <Badge color="red" variant="light" leftSection={<IconAlertTriangle size={12} />}>
                  {t("errorsCount", { n: draft.errors.length })}
                </Badge>
              )}
            </Group>
            <Group gap="xs" wrap="nowrap">
              <ActionIcon.Group>
                <Tooltip label={t("undo")} withArrow><ActionIcon variant="default" size="lg" aria-label={t("undo")} disabled={!draft.canUndo} onClick={draft.undo}><IconArrowBackUp size={17} /></ActionIcon></Tooltip>
                <Tooltip label={t("redo")} withArrow><ActionIcon variant="default" size="lg" aria-label={t("redo")} disabled={!draft.canRedo} onClick={draft.redo}><IconArrowForwardUp size={17} /></ActionIcon></Tooltip>
              </ActionIcon.Group>
              <Button variant="subtle" color="gray" onClick={draft.discard}>
                {tc("discard")}
              </Button>
              <Button onClick={() => void draft.save()} loading={draft.saving}>
                {tc("save")}
              </Button>
            </Group>
          </Group>
          {draft.saveError && (
            <Text size="sm" c="red" mt={6} style={{ whiteSpace: "pre-line" }} className="ows-value-in">
              {t("saveRefused", { reason: draft.saveError })}
            </Text>
          )}
        </Box>
      )}
    </Transition>
  );
}

/** Where you are: the project (a link to its overview) and the page, at the top of the canvas. */
function Breadcrumb({ caseId, label, icon: Icon }: { caseId: string | null; label: string; icon: Icon | null }) {
  const t = useT(messages);
  const cases = useCases();
  const name = caseId ? (cases.data?.find((c) => c.id === caseId)?.name ?? caseId) : null;
  return (
    <nav aria-label={t("where")} className="ows-crumbs">
      {name && caseId && (
        <>
          <a href={href(`projects/${caseId}/overview`)} className="ows-crumb ows-crumb-link">{name}</a>
          <IconChevronRight size={14} className="ows-crumb-sep" aria-hidden="true" />
        </>
      )}
      {/* Keyed on the page: the current crumb slides in when the page changes */}
      <span key={label} className="ows-crumb ows-crumb-current" aria-current="page">
        {Icon && <Icon size={16} stroke={1.7} />}
        {label}
      </span>
    </nav>
  );
}

interface LayoutProps {
  caseId: string | null;
  section: string;
  children: ReactNode;
}

export function Layout({ caseId, section, children }: LayoutProps) {
  const [opened, { toggle, close }] = useDisclosure();
  const [folded, setFolded] = useLocalStorage<boolean>({ key: "ows-sidebar-folded", defaultValue: false, getInitialValueInEffect: false });
  const mobile = useMediaQuery("(max-width: 48em)") ?? false;
  const t = useT(messages);
  const ts = useT(sectionMessages);
  const tc = useT(common);
  const health = useHealth();
  const groups = ["prepare", "run", "analyse"] as const;
  // On a phone the menu slides over the page at full width, never folded
  const narrow = folded && !mobile;
  // The highlight glides to the active entry (one per list: the main list scrolls on its own)
  const mainGlide = useGlide();
  const footGlide = useGlide();
  const activeKey = caseId ? `project:${section}` : `global:${section}`;
  const current = caseId
    ? PROJECT_SECTIONS.find((s) => s.key === section)
    : GLOBAL_SECTIONS.find((s) => s.key === section);
  const currentLabel = caseId ? ts(`project.${section as ProjectSection}`) : ts(`global.${section as (typeof GLOBAL_SECTIONS)[number]["key"]}`);

  const go = (path: string) => {
    navigate(path);
    close();
  };

  const entry = (key: string, path: string, label: string, Icon: Icon, active: boolean, glide: typeof mainGlide, index: number) => (
    <Tooltip key={key} label={label} position="right" disabled={!narrow} withArrow={false} offset={10}>
      <NavLink
        ref={glide.item(key) as never}
        href={href(path)}
        onClick={(e) => { e.preventDefault(); go(path); }}
        label={narrow ? null : label}
        aria-label={narrow ? label : undefined}
        leftSection={<Icon size={18} stroke={1.6} />}
        active={active}
        aria-current={active ? "page" : undefined}
        variant="light"
        className="ows-nav-link"
        style={{ "--ows-i": index } as never}
      />
    </Tooltip>
  );

  return (
    <AppShell
      className="ows-shell"
      data-folded={narrow || undefined}
      navbar={{ width: narrow ? 64 : 256, breakpoint: "sm", collapsed: { mobile: !opened } }}
      padding={0}
    >
      <a className="ows-skip-link" href="#ows-main" onClick={(e) => { e.preventDefault(); document.getElementById("ows-main")?.focus(); }}>
        {t("skip")}
      </a>

      <AppShell.Navbar aria-label={t("navigation")} className="ows-sidebar">
        <Group className="ows-sidebar-head" justify="space-between" wrap="nowrap" gap={4}>
          <a href={href("projects")} className="ows-brand" aria-label={tc("app")}>
            <span className="ows-brand-mark"><IconWind size={18} stroke={1.8} /></span>
            {!narrow && <span className="ows-brand-name">{tc("app")}</span>}
          </a>
          {!mobile && (
            <Tooltip label={t(narrow ? "unfold" : "fold")} position="right">
              <ActionIcon variant="subtle" color="gray" onClick={() => setFolded((value) => !value)} aria-label={t(narrow ? "unfold" : "fold")} className="ows-fold">
                {narrow ? <IconLayoutSidebarLeftExpand size={18} /> : <IconLayoutSidebarLeftCollapse size={18} />}
              </ActionIcon>
            </Tooltip>
          )}
        </Group>

        <Stack gap={8} px={narrow ? 10 : 12} pb={8}>
          {caseId && !narrow && <ProjectSwitcher caseId={caseId} />}
          {caseId && narrow && (
            <Tooltip label={t("switchProject")} position="right">
              <UnstyledButton className="ows-project-mini" onClick={() => setFolded(false)} aria-label={t("switchProject")}>
                <span className="ows-project-tile">{caseId.slice(0, 1).toUpperCase()}</span>
              </UnstyledButton>
            </Tooltip>
          )}
          <CommandPalette caseId={caseId} compact={narrow} />
        </Stack>

        <ScrollArea style={{ flex: 1 }} type="hover" scrollbarSize={6} className="ows-nav-scroll" px={narrow ? 10 : 12}>
          <Box ref={mainGlide.parent} pos="relative" pb="sm">
            <Glide glide={mainGlide} active={activeKey} className="ows-glide ows-nav-glide" />
            <Stack gap={2}>
              {GLOBAL_SECTIONS.filter((s) => s.key !== "settings" && s.key !== "help").map((s, i) =>
                entry(`global:${s.key}`, s.key, ts(`global.${s.key}`), s.icon, !caseId && section === s.key, mainGlide, i),
              )}
            </Stack>
            {caseId &&
              groups.map((group, g) => (
                <Stack key={group} gap={2} mt="md">
                  {narrow ? (
                    <span className="ows-nav-rule" aria-hidden="true" />
                  ) : (
                    <Text className="ows-nav-group">{ts(`groups.${group}`)}</Text>
                  )}
                  {PROJECT_SECTIONS.filter((s) => s.group === group).map((s, i) =>
                    entry(`project:${s.key}`, `projects/${caseId}/${s.key}`, ts(`project.${s.key as ProjectSection}`), s.icon, section === s.key, mainGlide, 3 + g * 4 + i),
                  )}
                </Stack>
              ))}
          </Box>
        </ScrollArea>

        <Box className="ows-sidebar-foot" px={narrow ? 10 : 12}>
          <Box ref={footGlide.parent} pos="relative">
            <Glide glide={footGlide} active={activeKey} className="ows-glide ows-nav-glide" />
            <Stack gap={2}>
              {GLOBAL_SECTIONS.filter((s) => s.key === "help" || s.key === "settings").map((s, i) =>
                entry(`global:${s.key}`, s.key, ts(`global.${s.key}`), s.icon, !caseId && section === s.key, footGlide, 18 + i),
              )}
            </Stack>
          </Box>
          <Group justify={narrow ? "center" : "space-between"} mt={8} gap={6} wrap="wrap">
            {!narrow && <LanguageSwitch />}
            <Group gap={2} wrap="nowrap">
              <BrowserSession compact={narrow} />
              <ColorSchemeToggle />
            </Group>
          </Group>
        </Box>
      </AppShell.Navbar>

      <AppShell.Main id="ows-main" tabIndex={-1} style={{ outline: "none" }}>
        <PageIconContext.Provider value={current?.icon ?? null}>
          <div className="ows-canvas">
            <header className="ows-topbar">
              <Group gap="xs" wrap="nowrap" style={{ minWidth: 0 }}>
                <Burger opened={opened} onClick={toggle} hiddenFrom="sm" size="sm" aria-label={t("navigation")} />
                <Breadcrumb caseId={caseId} label={currentLabel} icon={current?.icon ?? null} />
              </Group>
              <Group gap="xs" wrap="nowrap">
                {mobile && <LanguageSwitch />}
              </Group>
            </header>
            <div data-section={section} className={caseId ? "ows-canvas-body ows-canvas-body--project" : "ows-canvas-body"}>
              {health.isError && (
                <Alert color="red" icon={<IconServerOff size={18} />} mb="md">
                  {tc("offline")}
                </Alert>
              )}
              {caseId && <WorkflowGuide caseId={caseId} section={section} />}
              {/* The content area: what cross-fades when the page changes */}
              <div id="ows-page-root">{children}</div>
            </div>
          </div>
          {caseId && <SaveBar />}
        </PageIconContext.Provider>
      </AppShell.Main>
    </AppShell>
  );
}
