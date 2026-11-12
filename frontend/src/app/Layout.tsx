/**
 * The frame of the application: a sidebar (project, search, the menu, the simulations, help,
 * settings, language and display) and the content in an inset "canvas" with its own top bar
 * (where you are). The sidebar folds down to its icons.
 */
import {
  ActionIcon,
  Alert,
  AppShell,
  Box,
  Burger,
  Group,
  NavLink,
  ScrollArea,
  SegmentedControl,
  Select,
  Stack,
  Text,
  Tooltip,
  UnstyledButton,
  useComputedColorScheme,
  useMantineColorScheme,
} from "@mantine/core";
import { useDisclosure, useLocalStorage, useMediaQuery } from "@mantine/hooks";
import {
  IconArrowBackUp,
  IconArrowForwardUp,
  IconChevronRight,
  IconFolder,
  IconLayoutSidebarLeftCollapse,
  IconLayoutSidebarLeftExpand,
  IconServerOff,
} from "@tabler/icons-react";
import { AnimatePresence, motion } from "motion/react";
import { type ComponentType, type MouseEvent, type ReactNode, useEffect, useId, useState } from "react";

import { useCases } from "../api/cases";
import { useHealth } from "../api/system";
import { common } from "../i18n/common";
import { defineMessages, type Lang, useLang, useT } from "../i18n";
import { href, navigate } from "../router";
import { SPRING, withViewTransition } from "../motion";
import { BrowserSession } from "../ui/BrowserSession";
import { CommandPalette } from "../ui/CommandPalette";
import { Glide, useGlide } from "../ui/Glide";
import { NavSnake } from "../ui/NavSnake";
import { PageIconContext } from "../ui/Page";
import { WorkflowGuide } from "../ui/WorkflowGuide";
import { useDraft } from "./CaseDraft";
import { GLOBAL_SECTIONS, PROJECT_SECTIONS, type ProjectSection, sectionMessages } from "./sections";

const messages = defineMessages({
  en: {
    switchProject: "Switch project",
    theme: "Light or dark display",
    language: "Language",
    skip: "Skip to content",
    unsaved: "Unsaved",
    saveRefused: "Not saved: {reason}",
    errorsCount: "{n|# error|# errors}",
    undo: "Undo (Ctrl+Z)",
    redo: "Redo (Ctrl+Y)",
    navigation: "Navigation",
    fold: "Fold the menu",
    unfold: "Unfold the menu",
    where: "You are here",
  },
  fr: {
    switchProject: "Changer de projet",
    theme: "Affichage clair ou sombre",
    language: "Langue",
    skip: "Aller au contenu",
    unsaved: "Non enregistré",
    saveRefused: "Non enregistré : {reason}",
    errorsCount: "{n|# erreur|# erreurs}",
    undo: "Annuler (Ctrl+Z)",
    redo: "Rétablir (Ctrl+Y)",
    navigation: "Navigation",
    fold: "Replier le menu",
    unfold: "Déplier le menu",
    where: "Fil d'Ariane",
  },
});

type Icon = ComponentType<{ size?: number; stroke?: number }>;

/** The sun and the moon turn into each other: the disc swells and is bitten into as the rays go in. */
function SunMoon({ moon }: { moon: boolean }) {
  const mask = `ows-bite-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;
  return (
    <svg className="ows-sunmoon" data-moon={moon || undefined} width={17} height={17} viewBox="0 0 24 24" aria-hidden="true">
      <mask id={mask}><rect width="24" height="24" fill="#fff" /><circle className="ows-sunmoon-bite" r="6" fill="#000" /></mask>
      <circle className="ows-sunmoon-disc" cx="12" cy="12" fill="currentColor" mask={`url(#${mask})`} />
      <g className="ows-sunmoon-rays" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round">
        {[0, 45, 90, 135, 180, 225, 270, 315].map((angle) => <line key={angle} x1="12" y1="2.6" x2="12" y2="4.6" transform={`rotate(${angle} 12 12)`} />)}
      </g>
    </svg>
  );
}

/** A message whose count rolls to its new value: up when it grows, down when it shrinks. */
function Counted({ text, n }: { text: string; n: number }) {
  const [shown, setShown] = useState({ n, way: "none" });
  if (shown.n !== n) setShown({ n, way: n > shown.n ? "up" : "down" });
  const digits = String(n);
  const at = text.indexOf(digits);
  if (at < 0) return <>{text}</>;
  return (
    <>
      {text.slice(0, at)}
      <span className="ows-roll"><span key={n} data-way={shown.way}>{digits}</span></span>
      {text.slice(at + digits.length)}
    </>
  );
}

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
        <SunMoon moon={computed !== "dark"} />
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
  return (
    <Select
      aria-label={t("switchProject")}
      size="sm"
      searchable
      allowDeselect={false}
      value={caseId}
      data={(cases.data ?? []).map((c) => ({ value: c.id, label: c.name }))}
      onChange={(value) => value && navigate(`projects/${value}/overview`)}
      leftSection={<IconFolder size={18} stroke={1.6} />}
      leftSectionWidth={38}
      className="ows-project-switcher"
    />
  );
}

/** The soft spring of the motion book: the bar stretches a little past its size and settles. */
const SOFT_SPRING = [0.25, 1.25, 0.5, 1] as const;

/** Save bar of a project, after the motion book: as soon as something changed, a dot appears at
    the bottom and stretches into a dark bar (its content shows once it has spread); saving turns
    the button into waves, then a tick is drawn and the bar shrinks back into the dot. */
function SaveBar() {
  const draft = useDraft();
  const t = useT(messages);
  const tc = useT(common);
  // A save that went through draws a tick in the button, then the bar leaves; nothing waits for it
  const [wasSaving, setWasSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  if (draft.saving !== wasSaving) {
    setWasSaving(draft.saving);
    if (wasSaving && !draft.saveError) setSaved(true);
  }
  useEffect(() => {
    if (!saved) return;
    const id = window.setTimeout(() => setSaved(false), 700);
    return () => window.clearTimeout(id);
  }, [saved]);
  const done = saved && !draft.dirty;
  const errors = draft.errors.length;
  return (
    <AnimatePresence>
      {(draft.dirty || done) && (
        <motion.div key="savebar" className="ows-savebar" data-done={done || undefined} role="region" aria-label={done ? tc("saved") : t("unsaved")} exit={{ opacity: 1 }}>
          <motion.span className="ows-savebar-blob" aria-hidden="true"
            initial={{ width: 14, height: 14, opacity: 0 }}
            animate={{ width: "100%", height: "100%", opacity: 1, transition: { opacity: { duration: 0.2 }, width: { delay: 0.16, duration: 0.52, ease: SOFT_SPRING }, height: { delay: 0.16, duration: 0.42, ease: SOFT_SPRING } } }}
            exit={{ width: 14, height: 14, opacity: 0, transition: { width: { duration: 0.52, ease: SOFT_SPRING }, height: { duration: 0.42, ease: SOFT_SPRING }, opacity: { delay: 0.42, duration: 0.2 } } }} />
          <motion.div className="ows-savebar-content"
            initial={{ opacity: 0, filter: "blur(4px)" }}
            animate={{ opacity: 1, filter: "blur(0px)", transition: { delay: 0.38, duration: 0.26 } }}
            exit={{ opacity: 0, filter: "blur(4px)", transition: { duration: 0.26 } }}>
            <div className="ows-savebar-row">
              <span className="ows-savebar-state">
                <span className="ows-savebar-text">{done ? tc("saved") : t("unsaved")}</span>
                {errors > 0 && <span className="ows-savebar-errors"><Counted text={t("errorsCount", { n: errors })} n={errors} /></span>}
              </span>
              <span className="ows-savebar-actions">
                <Tooltip label={t("undo")} withArrow><UnstyledButton className="ows-savebar-icon" aria-label={t("undo")} disabled={!draft.canUndo} onClick={draft.undo}><IconArrowBackUp size={17} /></UnstyledButton></Tooltip>
                <Tooltip label={t("redo")} withArrow><UnstyledButton className="ows-savebar-icon" aria-label={t("redo")} disabled={!draft.canRedo} onClick={draft.redo}><IconArrowForwardUp size={17} /></UnstyledButton></Tooltip>
                <UnstyledButton className="ows-savebar-discard" onClick={draft.discard}>{tc("discard")}</UnstyledButton>
                <UnstyledButton className="ows-savebtn" data-busy={draft.saving || undefined} data-done={done || undefined} aria-busy={draft.saving || undefined} aria-label={done ? tc("saved") : tc("save")}
                  onClick={() => { if (!done && !draft.saving) void draft.save(); }}>
                  <span className="ows-savebtn-label">{tc("save")}</span>
                  <span className="ows-savebtn-waves" aria-hidden="true"><i /><i /><i /></span>
                  {done && <svg className="ows-savebtn-check" width="16" height="16" viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8.5l3.2 3L13 4.5" /></svg>}
                </UnstyledButton>
              </span>
            </div>
            {draft.saveError && <div className="ows-savebar-refused">{t("saveRefused", { reason: draft.saveError })}</div>}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/** Where you are: the project (a link to its overview) and the page, at the top of the canvas. */
function Breadcrumb({ caseId, label, icon: Icon }: { caseId: string | null; label: string; icon: Icon | null }) {
  const t = useT(messages);
  // The list only names the open project: none asked for on the pages outside a project
  const cases = useCases(caseId !== null);
  const name = caseId ? (cases.data?.find((c) => c.id === caseId)?.name ?? caseId) : null;
  return (
    <nav aria-label={t("where")} className="ows-crumbs">
      {name && caseId && (
        <>
          <a href={href(`projects/${caseId}/overview`)} className="ows-crumb ows-crumb-link">{name}</a>
          <IconChevronRight size={14} className="ows-crumb-sep" aria-hidden="true" />
        </>
      )}
      {/* Keyed on the page: the old crumb rises and blurs away while the new one comes up */}
      <AnimatePresence mode="popLayout" initial={false}>
        <motion.span
          key={label}
          className="ows-crumb ows-crumb-current"
          aria-current="page"
          initial={{ opacity: 0, y: 9, filter: "blur(4px)" }}
          animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
          exit={{ opacity: 0, y: -9, filter: "blur(4px)" }}
          transition={SPRING.snappy}
        >
          {Icon && <Icon size={16} stroke={1.7} />}
          {label}
        </motion.span>
      </AnimatePresence>
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
        {!mobile && (
          <Group className="ows-sidebar-head" wrap="nowrap">
            <Tooltip label={t(narrow ? "unfold" : "fold")} position="right">
              <ActionIcon variant="subtle" color="gray" onClick={() => setFolded((value) => !value)} aria-label={t(narrow ? "unfold" : "fold")} className="ows-fold">
                {narrow ? <IconLayoutSidebarLeftExpand size={18} /> : <IconLayoutSidebarLeftCollapse size={18} />}
              </ActionIcon>
            </Tooltip>
          </Group>
        )}

        <Stack gap={8} px={narrow ? 10 : 12} pt={mobile ? 12 : 0} pb={8}>
          {caseId && !narrow && <ProjectSwitcher caseId={caseId} />}
          {caseId && narrow && (
            <Tooltip label={t("switchProject")} position="right">
              <UnstyledButton className="ows-project-mini" onClick={() => setFolded(false)} aria-label={t("switchProject")}>
                <IconFolder size={18} stroke={1.6} />
              </UnstyledButton>
            </Tooltip>
          )}
          <CommandPalette caseId={caseId} compact={narrow} />
        </Stack>

        <ScrollArea style={{ flex: 1 }} type="hover" scrollbarSize={6} className="ows-nav-scroll" px={narrow ? 10 : 12}>
          <Box ref={mainGlide.parent} pos="relative" pb="sm">
            <NavSnake parent={mainGlide.parentNode} />
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
            <NavSnake parent={footGlide.parentNode} />
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
                {/* None on the Projects page: the word in the middle says where you are */}
                {(caseId || section !== "projects") && <Breadcrumb caseId={caseId} label={currentLabel} icon={current?.icon ?? null} />}
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
