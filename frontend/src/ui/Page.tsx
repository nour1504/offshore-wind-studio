import { Box, Group, Stack, Title, UnstyledButton, VisuallyHidden } from "@mantine/core";
import { type ComponentType, createContext, type CSSProperties, type ReactNode, type RefObject, useContext, useEffect, useRef, useState } from "react";

import { defineMessages, useT } from "../i18n";
import { prefersReducedMotion } from "../motion";
import { HelpLink } from "./Help";

/** The icon of the section being shown (from the menu), drawn beside the page title. */
export const PageIconContext = createContext<ComponentType<{ size?: number; stroke?: number }> | null>(null);

interface PageProps {
  className?: string;
  title: ReactNode;
  /** Buttons on the right of the title */
  actions?: ReactNode;
  /** Documentation topic opened by the help button */
  help?: string;
  /** Wide pages (maps, tables) use the full width */
  fluid?: boolean;
  children: ReactNode;
}

/** A page title whose letters come out of a blur one after the other, once per title (page titles only); words never break. */
export function Letters({ text }: { text: string }) {
  let n = 0;
  return (
    <>
      <VisuallyHidden>{text}</VisuallyHidden>
      <span className="ows-letters" aria-hidden="true">
        {text.split(/(\s+)/).map((word, w) => /^\s+$/.test(word) ? word : (
          <span key={w} className="ows-letters-word">
            {[...word].map((letter) => <span key={n} style={{ "--i": n++ } as CSSProperties}>{letter}</span>)}
          </span>
        ))}
      </span>
    </>
  );
}

const messages = defineMessages({ en: { sections: "Sections" }, fr: { sections: "Sections" } });

/**
 * Long pages: one dash per section on the right edge, the one in view drawn longer; a click goes
 * to the section, the name shows on hover. Shown from four sections, on wide screens.
 */
function SectionDashes({ content }: { content: RefObject<HTMLDivElement | null> }) {
  const t = useT(messages);
  const [sections, setSections] = useState<{ node: HTMLElement; title: string }[]>([]);
  const [seen, setSeen] = useState(0);
  useEffect(() => {
    const root = content.current;
    if (!root) return;
    const read = () => {
      const found = [...root.querySelectorAll<HTMLElement>(":scope > .ows-disclosure, :scope > * > .ows-disclosure, :scope > .ows-section")]
        .map((node) => ({ node, title: node.querySelector(".ows-disclosure-title, h3")?.textContent?.trim() ?? "" }))
        .filter((s) => s.title);
      setSections((previous) => previous.length === found.length && previous.every((p, k) => p.node === found[k].node && p.title === found[k].title) ? previous : found);
    };
    read();
    const changes = new MutationObserver(read);
    changes.observe(root, { childList: true, subtree: false });
    return () => changes.disconnect();
  }, [content]);
  useEffect(() => {
    if (sections.length < 4) return;
    const shown = new Map<Element, number>();
    const watch = new IntersectionObserver((entries) => {
      entries.forEach((entry) => shown.set(entry.target, entry.isIntersecting ? entry.intersectionRatio : 0));
      let best = -1, at = 0;
      sections.forEach((s, k) => { const r = shown.get(s.node) ?? 0; if (r > best + 0.001) { best = r; at = k; } });
      setSeen(at);
    }, { threshold: [0, 0.25, 0.5, 0.75, 1], rootMargin: "-20% 0px -40% 0px" });
    sections.forEach((s) => watch.observe(s.node));
    return () => watch.disconnect();
  }, [sections]);
  if (sections.length < 4) return null;
  return (
    <nav className="ows-dashes" aria-label={t("sections")}>
      {sections.map((s, k) => (
        <UnstyledButton key={k} className="ows-dash" data-active={k === seen || undefined} aria-label={s.title} onClick={() => s.node.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "start" })}>
          <span className="ows-dash-line" />
          <span className="ows-dash-name">{s.title}</span>
        </UnstyledButton>
      ))}
    </nav>
  );
}

/** The frame of every page: icon, title, actions, then the content. They come out of a blur in
    three beats, the title letter by letter. No sentence under the title, by design. */
export function Page({ title, actions, help, fluid, children, className }: PageProps) {
  const Icon = useContext(PageIconContext);
  const content = useRef<HTMLDivElement>(null);
  return (
    <Box className={["ows-page", className].filter(Boolean).join(" ")} maw={fluid ? undefined : "var(--ows-page-max)"} mx="auto" w="100%">
      <Group justify="space-between" align="flex-start" mb={24} gap="md" wrap="wrap" className="ows-page-head">
        <Group gap="md" wrap="nowrap" align="flex-start" style={{ flex: "1 1 320px", minWidth: 0 }}>
          {Icon && (
            <span className="ows-page-icon" aria-hidden="true">
              <Icon size={22} stroke={1.6} />
            </span>
          )}
          <Stack gap={4} style={{ minWidth: 0 }}>
            <Group gap={6} wrap="nowrap">
              <Title order={1}>{typeof title === "string" ? <Letters key={title} text={title} /> : title}</Title>
              {help && <span className="ows-page-help"><HelpLink topic={help} /></span>}
            </Group>
          </Stack>
        </Group>
        {actions && (
          <Group gap="xs" wrap="wrap" className="ows-page-actions">
            {actions}
          </Group>
        )}
      </Group>
      <Stack ref={content} gap="xl" className="ows-page-content">{children}</Stack>
      {!fluid && <SectionDashes content={content} />}
    </Box>
  );
}

interface SectionProps {
  className?: string;
  title?: ReactNode;
  actions?: ReactNode;
  help?: string;
  children: ReactNode;
  /** No inner padding: for tables and maps that reach the border */
  flush?: boolean;
}

/** An open section: structure comes from type and spacing, rather than nested cards. */
export function Section({ title, actions, help, children, flush, className }: SectionProps) {
  return (
    <Box component="section" className={["ows-section", flush && "ows-section-flush", className].filter(Boolean).join(" ")}>
      {(title || actions) && (
        <Group justify="space-between" align="flex-start" gap="sm" pb="md" wrap="wrap" className="ows-section-head">
          <Stack gap={2} style={{ flex: "1 1 240px", minWidth: 0 }}>
            {title && (
              <Group gap={6} wrap="nowrap">
                <Title order={3}>{title}</Title>
                {help && <HelpLink topic={help} size={16} />}
              </Group>
            )}
          </Stack>
          {actions && <Group gap="xs">{actions}</Group>}
        </Group>
      )}
      {children}
    </Box>
  );
}
