import { Accordion, Group, Text } from "@mantine/core";
import { type ReactNode, useState } from "react";
import { HelpLink } from "./Help";

/**
 * A section that opens and closes: its title (and a short summary on the right) stays visible,
 * its content shows on demand. Closed at first unless `defaultOpen`. With `lazy`, the content is
 * created only once the section is opened (heavy views such as the 3D scene).
 */
export function Fold({ title, aside, children, defaultOpen = false, lazy = false, className, help, actions }: { title: ReactNode; aside?: ReactNode; children: ReactNode; defaultOpen?: boolean; lazy?: boolean; className?: string; help?: string; actions?: ReactNode; description?: ReactNode }) {
  const [opened, setOpened] = useState(defaultOpen);
  const [seen, setSeen] = useState(defaultOpen);
  return (
    <Accordion
      variant="contained"
      radius="lg"
      value={opened ? "content" : null}
      onChange={(value) => { const open = value === "content"; setOpened(open); if (open) setSeen(true); }}
      className={["ows-disclosure", className].filter(Boolean).join(" ")}
      styles={{ control: { paddingBlock: 18 }, content: { paddingTop: 12, paddingBottom: 24 } }}
    >
      <Accordion.Item value="content">
        <div className="ows-disclosure-bar">
          <Accordion.Control>
            <Group justify="space-between" gap="sm" pr="sm" className="ows-disclosure-heading">
              <Text fw={600} fz={17} className="ows-disclosure-title">{title}</Text>
              {aside && <Text size="sm" c="dimmed" component="span" className="ows-disclosure-summary">{aside}</Text>}
            </Group>
          </Accordion.Control>
          {help && opened && <span className="ows-disclosure-help"><HelpLink topic={help} /></span>}
        </div>
        <Accordion.Panel>{!lazy || seen ? <>{actions && <Group justify="flex-end" mb="lg">{actions}</Group>}{children}</> : null}</Accordion.Panel>
      </Accordion.Item>
    </Accordion>
  );
}
