import { Box, Group, Stack, Title } from "@mantine/core";
import { type ComponentType, createContext, type ReactNode, useContext } from "react";

import { HelpLink } from "./Help";

/** The icon of the section being shown (from the menu), drawn beside the page title. */
export const PageIconContext = createContext<ComponentType<{ size?: number; stroke?: number }> | null>(null);

interface PageProps {
  className?: string;
  title: ReactNode;
  description?: ReactNode;
  /** Buttons on the right of the title */
  actions?: ReactNode;
  /** Documentation topic opened by the help button */
  help?: string;
  /** Wide pages (maps, tables) use the full width */
  fluid?: boolean;
  children: ReactNode;
}

/** The frame of every page: icon, title, actions, then the content. No sentence under the title
    by design; `description` is still accepted from callers but not shown. */
export function Page({ title, actions, help, fluid, children, className }: PageProps) {
  const Icon = useContext(PageIconContext);
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
              <Title order={1}>{title}</Title>
              {help && <HelpLink topic={help} />}
            </Group>
          </Stack>
        </Group>
        {actions && (
          <Group gap="xs" wrap="wrap" className="ows-page-actions">
            {actions}
          </Group>
        )}
      </Group>
      <Stack gap="xl" className="ows-page-content">{children}</Stack>
    </Box>
  );
}

interface SectionProps {
  className?: string;
  title?: ReactNode;
  description?: ReactNode;
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
